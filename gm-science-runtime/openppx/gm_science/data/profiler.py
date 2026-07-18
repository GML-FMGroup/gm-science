"""Deterministic profiling for bounded local tabular datasets."""

from __future__ import annotations

import csv
import datetime as dt
import json
import math
import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Iterator

from .config import DatasetConfig

_INTEGER_RE = re.compile(r"^[+-]?(?:0|[1-9][0-9]*)$")
_FLOAT_RE = re.compile(
    r"^[+-]?(?:(?:[0-9]+\.[0-9]*)|(?:[0-9]*\.[0-9]+)|(?:[0-9]+[eE][+-]?[0-9]+)|(?:[0-9]+\.[0-9]*[eE][+-]?[0-9]+))$"
)
_NULL_TEXT = {"", "na", "n/a", "null", "none", "nan"}
_SUPPORTED_SUFFIXES = {
    ".csv": "csv",
    ".tsv": "tsv",
    ".json": "json",
    ".jsonl": "jsonl",
    ".ndjson": "jsonl",
}


@dataclass(slots=True)
class _ColumnStats:
    """Bounded streaming statistics for one logical column."""

    name: str
    observed_count: int = 0
    missing_count: int = 0
    type_counts: Counter[str] = field(default_factory=Counter)
    unique_values: set[str] = field(default_factory=set)
    unique_capped: bool = False
    top_values: Counter[str] = field(default_factory=Counter)
    numeric_count: int = 0
    numeric_mean: float = 0.0
    numeric_m2: float = 0.0
    numeric_min: float | None = None
    numeric_max: float | None = None

    def observe(self, value: Any) -> None:
        normalized, value_type, numeric = _normalize_value(value)
        if value_type == "null":
            self.missing_count += 1
            return
        self.observed_count += 1
        self.type_counts[value_type] += 1
        key = _display_value(normalized)
        if len(self.unique_values) < 10_000:
            self.unique_values.add(key)
        elif key not in self.unique_values:
            self.unique_capped = True
        if key in self.top_values or len(self.top_values) < 1_000:
            self.top_values[key] += 1
        if numeric is None or not math.isfinite(numeric):
            return
        self.numeric_count += 1
        delta = numeric - self.numeric_mean
        self.numeric_mean += delta / self.numeric_count
        self.numeric_m2 += delta * (numeric - self.numeric_mean)
        self.numeric_min = numeric if self.numeric_min is None else min(self.numeric_min, numeric)
        self.numeric_max = numeric if self.numeric_max is None else max(self.numeric_max, numeric)

    def payload(self, *, total_rows: int, top_values_limit: int) -> dict[str, Any]:
        inferred_type = _inferred_type(self.type_counts)
        payload: dict[str, Any] = {
            "name": self.name,
            "inferred_type": inferred_type,
            "non_null_count": self.observed_count,
            "missing_count": self.missing_count + max(0, total_rows - self.observed_count - self.missing_count),
            "missing_fraction": round(
                (self.missing_count + max(0, total_rows - self.observed_count - self.missing_count))
                / max(1, total_rows),
                6,
            ),
            "type_counts": dict(sorted(self.type_counts.items())),
            "unique_count": len(self.unique_values),
            "unique_count_capped": self.unique_capped,
            "top_values": [
                {"value": value, "count": count}
                for value, count in sorted(self.top_values.items(), key=lambda item: (-item[1], item[0]))[
                    :top_values_limit
                ]
            ],
        }
        if self.numeric_count:
            variance = self.numeric_m2 / (self.numeric_count - 1) if self.numeric_count > 1 else 0.0
            payload["numeric"] = {
                "count": self.numeric_count,
                "min": _finite_round(self.numeric_min),
                "max": _finite_round(self.numeric_max),
                "mean": _finite_round(self.numeric_mean),
                "standard_deviation": _finite_round(math.sqrt(max(0.0, variance))),
            }
        return payload


def detect_dataset_format(path: Path) -> str:
    """Return the supported logical format for one file path."""

    dataset_format = _SUPPORTED_SUFFIXES.get(path.suffix.lower())
    if dataset_format is None:
        supported = ", ".join(sorted(_SUPPORTED_SUFFIXES))
        raise ValueError(f"Unsupported dataset format '{path.suffix or '<none>'}'. Supported: {supported}.")
    return dataset_format


def profile_dataset(path: Path, dataset_format: str, config: DatasetConfig) -> dict[str, Any]:
    """Profile one supported table file with bounded memory and stable output."""

    columns: list[str] = []
    stats: dict[str, _ColumnStats] = {}
    preview: list[dict[str, Any]] = []
    warnings: list[str] = []
    total_rows = 0
    profiled_rows = 0
    for row in _iter_rows(path, dataset_format, warnings):
        total_rows += 1
        for raw_name in row:
            name = str(raw_name)
            if name in stats:
                continue
            if len(columns) >= config.max_columns:
                raise ValueError(f"Dataset exceeds the configured {config.max_columns}-column limit.")
            columns.append(name)
            stats[name] = _ColumnStats(name=name)
        if len(preview) < config.preview_rows:
            preview.append({name: _json_value(row.get(name)) for name in columns})
        if profiled_rows >= config.profile_row_limit:
            continue
        profiled_rows += 1
        for name in columns:
            stats[name].observe(row.get(name))

    if not columns:
        raise ValueError("Dataset does not contain any columns.")
    if total_rows == 0:
        warnings.append("Dataset contains a header but no data rows.")
    if total_rows > profiled_rows:
        warnings.append(
            f"Statistics use the first {profiled_rows} rows out of {total_rows}; row count remains exact."
        )
    column_payloads = [
        stats[name].payload(total_rows=profiled_rows, top_values_limit=config.top_values_limit)
        for name in columns
    ]
    return {
        "version": 1,
        "format": dataset_format,
        "row_count": total_rows,
        "profiled_row_count": profiled_rows,
        "column_count": len(columns),
        "columns": column_payloads,
        "preview": preview,
        "warnings": list(dict.fromkeys(warnings)),
    }


def profile_markdown(title: str, profile: dict[str, Any]) -> str:
    """Render one deterministic human-readable profile summary."""

    lines = [
        f"# {title}",
        "",
        f"- Format: `{profile['format']}`",
        f"- Rows: {profile['row_count']}",
        f"- Profiled rows: {profile['profiled_row_count']}",
        f"- Columns: {profile['column_count']}",
        "",
        "## Schema",
        "",
        "| Column | Type | Missing | Unique | Numeric mean |",
        "| --- | --- | ---: | ---: | ---: |",
    ]
    for column in profile["columns"]:
        numeric = column.get("numeric") or {}
        unique = f">={column['unique_count']}" if column["unique_count_capped"] else str(column["unique_count"])
        lines.append(
            "| "
            + " | ".join(
                [
                    str(column["name"]).replace("|", "\\|"),
                    str(column["inferred_type"]),
                    str(column["missing_count"]),
                    unique,
                    str(numeric.get("mean", "")),
                ]
            )
            + " |"
        )
    warnings = profile.get("warnings") or []
    if warnings:
        lines.extend(["", "## Warnings", ""])
        lines.extend(f"- {warning}" for warning in warnings)
    return "\n".join(lines) + "\n"


def _iter_rows(path: Path, dataset_format: str, warnings: list[str]) -> Iterator[dict[str, Any]]:
    if dataset_format in {"csv", "tsv"}:
        yield from _iter_delimited_rows(path, "\t" if dataset_format == "tsv" else ",", warnings)
        return
    if dataset_format == "jsonl":
        yield from _iter_jsonl_rows(path)
        return
    yield from _iter_json_rows(path)


def _iter_delimited_rows(path: Path, delimiter: str, warnings: list[str]) -> Iterator[dict[str, Any]]:
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.reader(handle, delimiter=delimiter)
            raw_header = next(reader)
            header = _normalized_header(raw_header, warnings)
            for row_number, values in enumerate(reader, start=2):
                if not values or all(not str(value).strip() for value in values):
                    continue
                if len(values) > len(header):
                    warnings.append(f"Rows with extra values were truncated, first seen at row {row_number}.")
                yield {name: values[index] if index < len(values) else None for index, name in enumerate(header)}
    except StopIteration as exc:
        raise ValueError("Dataset is empty.") from exc
    except UnicodeDecodeError as exc:
        raise ValueError("Dataset must be UTF-8 encoded.") from exc


def _iter_json_rows(path: Path) -> Iterator[dict[str, Any]]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except UnicodeDecodeError as exc:
        raise ValueError("Dataset must be UTF-8 encoded.") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON dataset at line {exc.lineno}, column {exc.colno}.") from exc
    if isinstance(payload, dict) and isinstance(payload.get("data"), list):
        payload = payload["data"]
    elif isinstance(payload, dict):
        payload = [payload]
    if not isinstance(payload, list):
        raise ValueError("JSON dataset must be an array of objects or an object containing a 'data' array.")
    for index, item in enumerate(payload, start=1):
        if not isinstance(item, dict):
            raise ValueError(f"JSON dataset row {index} is not an object.")
        yield _normalized_json_row(item)


def _iter_jsonl_rows(path: Path) -> Iterator[dict[str, Any]]:
    try:
        with path.open("r", encoding="utf-8-sig") as handle:
            for line_number, line in enumerate(handle, start=1):
                if not line.strip():
                    continue
                try:
                    item = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise ValueError(f"Invalid JSONL dataset at line {line_number}.") from exc
                if not isinstance(item, dict):
                    raise ValueError(f"JSONL dataset row {line_number} is not an object.")
                yield _normalized_json_row(item)
    except UnicodeDecodeError as exc:
        raise ValueError("Dataset must be UTF-8 encoded.") from exc


def _normalized_header(raw_header: list[str], warnings: list[str]) -> list[str]:
    if not raw_header:
        raise ValueError("Dataset header is empty.")
    normalized: list[str] = []
    counts: Counter[str] = Counter()
    for index, raw_name in enumerate(raw_header, start=1):
        base = str(raw_name).strip() or f"column_{index}"
        counts[base] += 1
        name = base if counts[base] == 1 else f"{base}_{counts[base]}"
        normalized.append(name)
    if normalized != [str(value).strip() for value in raw_header]:
        warnings.append("Blank or duplicate column names were normalized for profiling.")
    return normalized


def _normalized_json_row(row: dict[str, Any]) -> dict[str, Any]:
    normalized: dict[str, Any] = {}
    for key, value in row.items():
        name = str(key)
        normalized[name] = json.dumps(value, ensure_ascii=False, sort_keys=True) if isinstance(value, (dict, list)) else value
    return normalized


def _normalize_value(value: Any) -> tuple[Any, str, float | None]:
    if value is None:
        return None, "null", None
    if isinstance(value, bool):
        return value, "boolean", None
    if isinstance(value, int):
        return value, "integer", float(value)
    if isinstance(value, float):
        if math.isnan(value):
            return None, "null", None
        return value, "number", value
    text = str(value).strip()
    if text.lower() in _NULL_TEXT:
        return None, "null", None
    lowered = text.lower()
    if lowered in {"true", "false"}:
        return lowered == "true", "boolean", None
    if _INTEGER_RE.fullmatch(text):
        return int(text), "integer", float(text)
    if _FLOAT_RE.fullmatch(text):
        number = float(text)
        return number, "number", number
    if _is_iso_datetime(text):
        return text, "datetime", None
    return text, "string", None


def _is_iso_datetime(value: str) -> bool:
    if len(value) < 8 or not any(character in value for character in "-T:"):
        return False
    try:
        dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        try:
            dt.date.fromisoformat(value)
        except ValueError:
            return False
    return True


def _inferred_type(counts: Counter[str]) -> str:
    kinds = set(counts)
    if not kinds:
        return "unknown"
    if kinds <= {"integer"}:
        return "integer"
    if kinds <= {"integer", "number"}:
        return "number"
    if len(kinds) == 1:
        return next(iter(kinds))
    return "string"


def _display_value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float):
        return str(_finite_round(value))
    return str(value)


def _json_value(value: Any) -> Any:
    normalized, value_type, _numeric = _normalize_value(value)
    return None if value_type == "null" else normalized


def _finite_round(value: float | None) -> float | None:
    if value is None or not math.isfinite(value):
        return None
    return round(value, 8)
