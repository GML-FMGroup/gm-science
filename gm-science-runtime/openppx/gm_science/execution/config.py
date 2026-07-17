"""Configuration parsing for gm-science local execution."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ...core.config import load_config, normalize_config
from ...core.env_utils import is_enabled


@dataclass(frozen=True, slots=True)
class ScienceExecutionConfig:
    """Validated local execution limits for one science agent."""

    enabled: bool
    python_executable: str
    max_concurrent_runs: int
    default_timeout_seconds: int
    max_source_chars: int
    max_log_preview_chars: int


def parse_execution_config(config: Mapping[str, Any] | None) -> ScienceExecutionConfig:
    """Normalize an openppx configuration payload into execution settings."""

    normalized = normalize_config(dict(config or {}))
    science = _mapping(normalized.get("science"))
    execution = _mapping(science.get("execution"))
    return ScienceExecutionConfig(
        enabled=is_enabled(execution.get("enabled"), default=True),
        python_executable=str(execution.get("pythonExecutable") or "").strip(),
        max_concurrent_runs=_bounded_int(execution.get("maxConcurrentRuns"), 1, 1, 16),
        default_timeout_seconds=_bounded_int(execution.get("defaultTimeoutSeconds"), 900, 1, 86_400),
        max_source_chars=_bounded_int(execution.get("maxSourceChars"), 200_000, 1_000, 2_000_000),
        max_log_preview_chars=_bounded_int(execution.get("maxLogPreviewChars"), 6_000, 1_000, 100_000),
    )


def load_execution_config(config_path: Path | None = None) -> ScienceExecutionConfig:
    """Load local execution settings from the active agent configuration."""

    return parse_execution_config(load_config(config_path=config_path))


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _bounded_int(value: Any, default: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return min(max(parsed, minimum), maximum)
