"""Configuration parsing for Project dataset import and profiling."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ...core.config import load_config, normalize_config
from ...core.env_utils import is_enabled


@dataclass(frozen=True, slots=True)
class DatasetConfig:
    """Validated limits for local tabular dataset handling."""

    enabled: bool
    max_file_size_bytes: int
    profile_row_limit: int
    preview_rows: int
    max_columns: int
    top_values_limit: int


def parse_dataset_config(config: Mapping[str, Any] | None) -> DatasetConfig:
    """Normalize an openppx configuration payload into dataset settings."""

    normalized = normalize_config(dict(config or {}))
    science = _mapping(normalized.get("science"))
    data = _mapping(science.get("data"))
    return DatasetConfig(
        enabled=is_enabled(data.get("enabled"), default=True),
        max_file_size_bytes=_bounded_int(data.get("maxFileSizeBytes"), 100_000_000, 1_024, 2_000_000_000),
        profile_row_limit=_bounded_int(data.get("profileRowLimit"), 50_000, 100, 1_000_000),
        preview_rows=_bounded_int(data.get("previewRows"), 20, 1, 200),
        max_columns=_bounded_int(data.get("maxColumns"), 200, 1, 10_000),
        top_values_limit=_bounded_int(data.get("topValuesLimit"), 10, 1, 100),
    )


def load_dataset_config(config_path: Path | None = None) -> DatasetConfig:
    """Load dataset settings from the active science-agent configuration."""

    return parse_dataset_config(load_config(config_path=config_path))


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _bounded_int(value: Any, default: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return min(max(parsed, minimum), maximum)
