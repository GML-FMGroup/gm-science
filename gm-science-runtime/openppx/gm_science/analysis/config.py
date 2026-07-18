"""Configuration parsing for reviewable dataset analysis."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ...core.config import load_config, normalize_config
from ...core.env_utils import is_enabled


@dataclass(frozen=True, slots=True)
class AnalysisConfig:
    """Validated limits for analysis-plan compilation."""

    enabled: bool
    max_datasets: int
    max_objective_chars: int
    max_numeric_columns: int
    max_group_categories: int


def parse_analysis_config(config: Mapping[str, Any] | None) -> AnalysisConfig:
    """Normalize an openppx configuration payload into analysis settings."""

    normalized = normalize_config(dict(config or {}))
    science = _mapping(normalized.get("science"))
    analysis = _mapping(science.get("analysis"))
    return AnalysisConfig(
        enabled=is_enabled(analysis.get("enabled"), default=True),
        max_datasets=_bounded_int(analysis.get("maxDatasets"), 3, 1, 20),
        max_objective_chars=_bounded_int(analysis.get("maxObjectiveChars"), 4_000, 100, 100_000),
        max_numeric_columns=_bounded_int(analysis.get("maxNumericColumns"), 20, 1, 200),
        max_group_categories=_bounded_int(analysis.get("maxGroupCategories"), 20, 2, 1_000),
    )


def load_analysis_config(config_path: Path | None = None) -> AnalysisConfig:
    """Load analysis settings from the active science-agent configuration."""

    return parse_analysis_config(load_config(config_path=config_path))


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _bounded_int(value: Any, default: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return min(max(parsed, minimum), maximum)
