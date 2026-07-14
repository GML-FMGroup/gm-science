"""Configuration parsing for gm-science literature connectors."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ...core.config import load_config, normalize_config

SUPPORTED_LITERATURE_SOURCES = ("arxiv", "pubmed", "openalex")


@dataclass(frozen=True, slots=True)
class LiteratureSourceConfig:
    """Resolved configuration for one literature source."""

    name: str
    enabled: bool
    api_base: str
    min_interval_seconds: float = 0.0
    tool: str = ""
    email: str = ""
    api_key: str = ""

    def status(self) -> tuple[str, str]:
        """Return public availability state and an actionable message."""

        if not self.enabled:
            return "disabled", ""
        if self.name == "pubmed" and not self.email:
            return "needs_configuration", "Set science.literature.pubmed.email."
        if self.name == "openalex" and not self.api_key:
            return "needs_configuration", "Set science.literature.openalex.apiKey."
        return "ok", ""


@dataclass(frozen=True, slots=True)
class LiteratureConfig:
    """Validated gm-science literature search configuration."""

    default_sources: tuple[str, ...]
    max_results_per_source: int
    request_timeout_seconds: float
    cache_ttl_seconds: int
    sources: Mapping[str, LiteratureSourceConfig]

    def public_source_statuses(self) -> dict[str, dict[str, Any]]:
        """Project source availability without exposing credentials or identity."""

        statuses: dict[str, dict[str, Any]] = {}
        for name in SUPPORTED_LITERATURE_SOURCES:
            source = self.sources[name]
            status, message = source.status()
            statuses[name] = {
                "enabled": source.enabled,
                "status": status,
                "configuration_message": message,
                "api_base": source.api_base,
            }
        return statuses


@dataclass(frozen=True, slots=True)
class LiteratureSourceSelection:
    """Literature sources allowed by a request and its Project policy."""

    requested: tuple[str, ...]
    allowed: tuple[str, ...]
    project_disabled: tuple[str, ...]


def parse_literature_config(config: Mapping[str, Any] | None) -> LiteratureConfig:
    """Normalize an openppx config payload into literature connector settings."""

    normalized = normalize_config(dict(config or {}))
    science = _mapping(normalized.get("science"))
    literature = _mapping(science.get("literature"))

    raw_sources = literature.get("defaultSources")
    default_sources = _normalize_sources(raw_sources)
    if not default_sources:
        default_sources = SUPPORTED_LITERATURE_SOURCES

    sources = {
        "arxiv": _source_config("arxiv", _mapping(literature.get("arxiv"))),
        "pubmed": _source_config("pubmed", _mapping(literature.get("pubmed"))),
        "openalex": _source_config("openalex", _mapping(literature.get("openalex"))),
    }
    return LiteratureConfig(
        default_sources=default_sources,
        max_results_per_source=_bounded_int(literature.get("maxResultsPerSource"), 10, 1, 25),
        request_timeout_seconds=_bounded_float(literature.get("requestTimeoutSeconds"), 20.0, 1.0, 120.0),
        cache_ttl_seconds=_bounded_int(literature.get("cacheTtlSeconds"), 86400, 0, 31_536_000),
        sources=sources,
    )


def load_literature_config(config_path: Path | None = None) -> LiteratureConfig:
    """Load literature connector settings from the active agent config."""

    return parse_literature_config(load_config(config_path=config_path))


def select_literature_sources(
    config: LiteratureConfig,
    *,
    requested_sources: Sequence[str] | None = None,
    enabled_connectors: Sequence[str] | None = None,
) -> LiteratureSourceSelection:
    """Apply strict request validation and a Project connector allowlist."""

    requested = config.default_sources if requested_sources is None else _strict_sources(requested_sources)
    if not requested:
        raise ValueError("At least one literature source is required.")
    if enabled_connectors is None:
        return LiteratureSourceSelection(requested=requested, allowed=requested, project_disabled=())
    configured_connectors = tuple(str(value).strip().lower() for value in enabled_connectors if str(value).strip())
    project_enabled = set(configured_connectors).intersection(SUPPORTED_LITERATURE_SOURCES)
    allowed = tuple(source for source in requested if source in project_enabled)
    disabled = tuple(source for source in requested if source not in project_enabled)
    return LiteratureSourceSelection(requested=requested, allowed=allowed, project_disabled=disabled)


def _source_config(name: str, raw: Mapping[str, Any]) -> LiteratureSourceConfig:
    """Build one source config from normalized fields."""

    return LiteratureSourceConfig(
        name=name,
        enabled=bool(raw.get("enabled", True)),
        api_base=str(raw.get("apiBase") or "").strip().rstrip("/"),
        min_interval_seconds=max(0.0, _float(raw.get("minIntervalSeconds"), 0.0)),
        tool=str(raw.get("tool") or "").strip(),
        email=str(raw.get("email") or "").strip(),
        api_key=str(raw.get("apiKey") or "").strip(),
    )


def _normalize_sources(value: Any) -> tuple[str, ...]:
    """Return supported source names once, preserving caller order."""

    if not isinstance(value, list):
        return ()
    normalized: list[str] = []
    for item in value:
        name = str(item or "").strip().lower()
        if name not in SUPPORTED_LITERATURE_SOURCES or name in normalized:
            continue
        normalized.append(name)
    return tuple(normalized)


def _strict_sources(values: Sequence[str]) -> tuple[str, ...]:
    normalized: list[str] = []
    for value in values:
        source = str(value).strip().lower()
        if source not in SUPPORTED_LITERATURE_SOURCES:
            raise ValueError(f"Unsupported literature source: {source or value}")
        if source not in normalized:
            normalized.append(source)
    return tuple(normalized)


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _bounded_float(value: Any, default: float, minimum: float, maximum: float) -> float:
    return min(max(_float(value, default), minimum), maximum)


def _bounded_int(value: Any, default: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return min(max(parsed, minimum), maximum)
