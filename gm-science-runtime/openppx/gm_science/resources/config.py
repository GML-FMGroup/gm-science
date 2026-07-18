"""Configuration parsing for the unified Project resource catalog."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ...core.config import load_config, normalize_config
from ...core.env_utils import is_enabled


@dataclass(frozen=True, slots=True)
class ResourceCatalogConfig:
    """Validated limits for Project resource discovery and model context."""

    enabled: bool
    max_workspace_files: int
    max_scan_depth: int
    include_hidden: bool
    excluded_directories: tuple[str, ...]
    max_selected_resources: int
    max_context_chars_per_resource: int
    max_context_chars_total: int


def parse_resource_catalog_config(config: Mapping[str, Any] | None) -> ResourceCatalogConfig:
    """Normalize an openppx configuration payload into resource catalog settings."""

    normalized = normalize_config(dict(config or {}))
    science = _mapping(normalized.get("science"))
    resources = _mapping(science.get("resources"))
    raw_exclusions = resources.get("excludedDirectories")
    exclusions = _string_tuple(raw_exclusions) if isinstance(raw_exclusions, list) else ()
    return ResourceCatalogConfig(
        enabled=is_enabled(resources.get("enabled"), default=True),
        max_workspace_files=_bounded_int(resources.get("maxWorkspaceFiles"), 1_000, 1, 100_000),
        max_scan_depth=_bounded_int(resources.get("maxScanDepth"), 6, 0, 20),
        include_hidden=is_enabled(resources.get("includeHidden"), default=False),
        excluded_directories=exclusions,
        max_selected_resources=_bounded_int(resources.get("maxSelectedResources"), 8, 1, 32),
        max_context_chars_per_resource=_bounded_int(
            resources.get("maxContextCharsPerResource"),
            30_000,
            256,
            200_000,
        ),
        max_context_chars_total=_bounded_int(
            resources.get("maxContextCharsTotal"),
            100_000,
            256,
            1_000_000,
        ),
    )


def load_resource_catalog_config(config_path: Path | None = None) -> ResourceCatalogConfig:
    """Load resource catalog settings from the active science-agent configuration."""

    return parse_resource_catalog_config(load_config(config_path=config_path))


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _bounded_int(value: Any, default: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return min(max(parsed, minimum), maximum)


def _string_tuple(values: list[Any]) -> tuple[str, ...]:
    normalized: list[str] = []
    seen: set[str] = set()
    for value in values:
        item = str(value or "").strip().strip("/\\")
        if not item or item in seen:
            continue
        seen.add(item)
        normalized.append(item)
    return tuple(normalized)
