"""Local storage and usage observability for the gm-science workspace."""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from ..runtime.task_store import TaskStore
from ..runtime.token_usage_store import read_token_usage_stats


USAGE_WINDOWS_MS: dict[str, int] = {
    "24h": 24 * 60 * 60 * 1000,
    "7d": 7 * 24 * 60 * 60 * 1000,
    "30d": 30 * 24 * 60 * 60 * 1000,
}

_STORAGE_CATEGORIES: tuple[tuple[str, str], ...] = (
    ("workspaces", "Workspaces"),
    ("databases", "Databases"),
    ("cache", "Cache"),
    ("configuration", "Agent configuration"),
    ("logs", "Logs"),
    ("other", "Other"),
)


@dataclass(slots=True)
class _ScanBudget:
    """Shared limits for one recursive local storage scan."""

    max_entries: int
    deadline: float
    monotonic: Callable[[], float]
    entries_seen: int = 0
    complete: bool = True
    partial_reason: str | None = None

    def consume(self) -> bool:
        """Consume one filesystem entry or mark the scan partial."""

        if self.entries_seen >= self.max_entries:
            self.complete = False
            self.partial_reason = f"Scan stopped after {self.max_entries:,} filesystem entries."
            return False
        if self.monotonic() >= self.deadline:
            self.complete = False
            self.partial_reason = "Scan stopped after reaching its time budget."
            return False
        self.entries_seen += 1
        return True


class GmScienceObservabilityService:
    """Project local runtime facts into renderer-safe Storage and Usage snapshots."""

    def __init__(
        self,
        *,
        data_dir: Path,
        now_ms: Callable[[], int] | None = None,
        monotonic: Callable[[], float] | None = None,
    ) -> None:
        self.data_dir = Path(data_dir).expanduser().resolve(strict=False)
        self._now_ms = now_ms or (lambda: int(time.time() * 1000))
        self._monotonic = monotonic or time.monotonic

    def get_storage_snapshot(
        self,
        *,
        max_entries: int = 100_000,
        time_budget_seconds: float = 2.0,
    ) -> dict[str, Any]:
        """Measure non-overlapping local storage categories without following symlinks."""

        safe_max_entries = max(1, min(int(max_entries), 1_000_000))
        safe_time_budget = max(0.05, min(float(time_budget_seconds), 10.0))
        started = self._monotonic()
        budget = _ScanBudget(
            max_entries=safe_max_entries,
            deadline=started + safe_time_budget,
            monotonic=self._monotonic,
        )
        categories = {
            category_id: {
                "id": category_id,
                "name": name,
                "bytes": 0,
                "files": 0,
            }
            for category_id, name in _STORAGE_CATEGORIES
        }
        issues: list[str] = []

        if not self.data_dir.exists():
            return self._storage_payload(
                categories=categories,
                budget=budget,
                issues=["The configured gm-science data location does not exist."],
                writable=False,
                elapsed_ms=0,
            )

        try:
            top_level = _sorted_scandir(self.data_dir)
        except OSError as exc:
            return self._storage_payload(
                categories=categories,
                budget=budget,
                issues=[f"Unable to inspect the configured data location: {exc.strerror or exc}."],
                writable=os.access(self.data_dir, os.W_OK),
                elapsed_ms=int((self._monotonic() - started) * 1000),
            )

        for entry in top_level:
            if not budget.consume():
                break
            category_id = _classify_top_level_entry(entry.name)
            allocated_bytes, files = _scan_entry(
                entry,
                root=self.data_dir,
                budget=budget,
                issues=issues,
            )
            categories[category_id]["bytes"] += allocated_bytes
            categories[category_id]["files"] += files
            if not budget.complete:
                break

        return self._storage_payload(
            categories=categories,
            budget=budget,
            issues=issues,
            writable=os.access(self.data_dir, os.W_OK),
            elapsed_ms=int((self._monotonic() - started) * 1000),
        )

    def get_usage_snapshot(self, window: str = "7d") -> dict[str, Any]:
        """Return locally recorded model and TaskRun activity for one supported window."""

        normalized_window = str(window or "7d").strip().lower()
        if normalized_window not in USAGE_WINDOWS_MS:
            supported = ", ".join(USAGE_WINDOWS_MS)
            raise ValueError(f"Unsupported usage window '{window}'. Expected one of: {supported}.")

        until_ms = self._now_ms()
        since_ms = until_ms - USAGE_WINDOWS_MS[normalized_window]
        token_db_path = self.data_dir / "token_usage.db"
        task_db_path = self.data_dir / "database" / "tasks.db"

        if token_db_path.exists():
            token_stats = read_token_usage_stats(
                limit=10,
                since_ms=since_ms,
                until_ms=until_ms,
                db_path=token_db_path,
            )
        else:
            token_stats = _empty_token_stats(since_ms=since_ms, until_ms=until_ms)

        if task_db_path.exists():
            task_stats = TaskStore(db_path=task_db_path).read_usage_stats(
                since_ms=since_ms,
                until_ms=until_ms,
            )
        else:
            task_stats = _empty_task_stats(since_ms=since_ms, until_ms=until_ms)

        return {
            "window": normalized_window,
            "generated_at": _iso_from_ms(until_ms),
            "since": _iso_from_ms(since_ms),
            "until": _iso_from_ms(until_ms),
            "local_estimate": True,
            "cost": {
                "available": False,
                "reason": "Provider pricing and invoice reconciliation are not configured.",
            },
            "tokens": {
                "recording_started": token_db_path.exists(),
                "requests": int(token_stats["requests"]),
                "input_tokens": int(token_stats["request_tokens"]),
                "output_tokens": int(token_stats["response_tokens"]),
                "input_text_tokens": int(token_stats["request_text_tokens"]),
                "output_text_tokens": int(token_stats["response_text_tokens"]),
                "input_image_tokens": int(token_stats["request_image_tokens"]),
                "output_image_tokens": int(token_stats["response_image_tokens"]),
                "total_tokens": int(token_stats["total_tokens"]),
                "by_model": [
                    {
                        "provider": str(row.get("provider") or "unknown"),
                        "model": str(row.get("model") or "unknown"),
                        "requests": int(row.get("requests") or 0),
                        "input_tokens": int(row.get("request_tokens") or 0),
                        "output_tokens": int(row.get("response_tokens") or 0),
                        "total_tokens": int(row.get("total_tokens") or 0),
                    }
                    for row in token_stats.get("by_model", [])
                ],
            },
            "runs": {
                "recording_started": task_db_path.exists(),
                "runs": int(task_stats["runs"]),
                "active_runs": int(task_stats["active_runs"]),
                "terminal_runs": int(task_stats["terminal_runs"]),
                "runtime_ms": int(task_stats["runtime_ms"]),
                "by_status": [dict(row) for row in task_stats["by_status"]],
                "by_kind": [dict(row) for row in task_stats["by_kind"]],
            },
        }

    def _storage_payload(
        self,
        *,
        categories: dict[str, dict[str, Any]],
        budget: _ScanBudget,
        issues: list[str],
        writable: bool,
        elapsed_ms: int,
    ) -> dict[str, Any]:
        """Build the stable Storage snapshot projection."""

        category_items = [categories[category_id] for category_id, _name in _STORAGE_CATEGORIES]
        return {
            "data_location": str(self.data_dir),
            "exists": self.data_dir.exists(),
            "writable": bool(writable),
            "scanned_at": _iso_from_ms(self._now_ms()),
            "scan_complete": budget.complete and not issues and self.data_dir.exists(),
            "partial_reason": budget.partial_reason or (
                "Some filesystem entries could not be inspected." if issues else None
            ),
            "entries_scanned": budget.entries_seen,
            "elapsed_ms": max(0, int(elapsed_ms)),
            "total_bytes": sum(int(item["bytes"]) for item in category_items),
            "total_files": sum(int(item["files"]) for item in category_items),
            "categories": category_items,
            "issues": issues[:20],
            "cloud_storage": {
                "supported": False,
                "configured": False,
                "detail": "No cloud storage adapter is available in this build.",
            },
        }


def _classify_top_level_entry(name: str) -> str:
    """Map one top-level data-root entry to a non-overlapping category."""

    normalized = name.strip().lower()
    if normalized == "workspaces":
        return "workspaces"
    if normalized == "database" or normalized.startswith(("gm-science.db", "token_usage.db")):
        return "databases"
    if normalized == "cache":
        return "cache"
    if normalized == "logs" or normalized.endswith(".log"):
        return "logs"
    if normalized == "science-research" or normalized == "global_config.json":
        return "configuration"
    return "other"


def _scan_entry(
    entry: os.DirEntry[str],
    *,
    root: Path,
    budget: _ScanBudget,
    issues: list[str],
) -> tuple[int, int]:
    """Recursively measure one entry without traversing symbolic links."""

    allocated_bytes = 0
    files = 0
    stack: list[os.DirEntry[str]] = [entry]
    first = True
    while stack:
        current = stack.pop()
        if not first and not budget.consume():
            break
        first = False
        try:
            stat_result = current.stat(follow_symlinks=False)
            allocated_bytes += _allocated_size(stat_result)
            if current.is_symlink() or not current.is_dir(follow_symlinks=False):
                files += 1
                continue
            children = _sorted_scandir(Path(current.path), reverse=True)
            stack.extend(children)
        except OSError as exc:
            if len(issues) < 20:
                try:
                    relative = Path(current.path).resolve(strict=False).relative_to(root)
                except ValueError:
                    relative = Path(current.name)
                issues.append(f"Unable to inspect '{relative}': {exc.strerror or exc}.")
    return allocated_bytes, files


def _allocated_size(stat_result: os.stat_result) -> int:
    """Return allocated filesystem bytes with an apparent-size fallback."""

    blocks = int(getattr(stat_result, "st_blocks", 0) or 0)
    if blocks > 0:
        return blocks * 512
    return max(0, int(stat_result.st_size))


def _sorted_scandir(path: Path, *, reverse: bool = False) -> list[os.DirEntry[str]]:
    """Read and close one directory iterator before returning stable entries."""

    with os.scandir(path) as entries:
        return sorted(entries, key=lambda entry: entry.name.lower(), reverse=reverse)


def _empty_token_stats(*, since_ms: int, until_ms: int) -> dict[str, Any]:
    """Return a zero-value token snapshot without creating a database."""

    return {
        "requests": 0,
        "request_tokens": 0,
        "response_tokens": 0,
        "request_text_tokens": 0,
        "response_text_tokens": 0,
        "request_image_tokens": 0,
        "response_image_tokens": 0,
        "total_tokens": 0,
        "since_ms": since_ms,
        "until_ms": until_ms,
        "recent": [],
        "by_model": [],
    }


def _empty_task_stats(*, since_ms: int, until_ms: int) -> dict[str, Any]:
    """Return a zero-value TaskRun snapshot without creating a database."""

    return {
        "runs": 0,
        "active_runs": 0,
        "terminal_runs": 0,
        "runtime_ms": 0,
        "since_ms": since_ms,
        "until_ms": until_ms,
        "by_status": [],
        "by_kind": [],
    }


def _iso_from_ms(value: int) -> str:
    """Format epoch milliseconds as a stable UTC ISO timestamp."""

    return datetime.fromtimestamp(int(value) / 1000, tz=timezone.utc).isoformat().replace("+00:00", "Z")
