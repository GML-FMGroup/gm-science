"""Configuration parsing for gm-science specialist agents."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ...core.config import load_config, normalize_config
from ...core.env_utils import is_enabled

SUPPORTED_SPECIALISTS = ("paper_reader", "research_reviewer")
SUPPORTED_REVIEW_GATES = ("off", "annotate")


@dataclass(frozen=True, slots=True)
class ProjectCapabilityDefaults:
    """Default capability allowlists applied to newly created Projects."""

    enabled_skills: tuple[str, ...]
    enabled_connectors: tuple[str, ...]
    enabled_specialists: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class PaperReaderConfig:
    """Runtime limits for the bounded paper-reader specialist."""

    enabled: bool
    auto_dispatch: bool
    max_papers: int
    max_source_chars: int


@dataclass(frozen=True, slots=True)
class ResearchReviewerConfig:
    """Runtime limits and gate policy for the research reviewer."""

    enabled: bool
    auto_dispatch: bool
    review_gate: str
    max_findings: int
    max_source_chars: int


@dataclass(frozen=True, slots=True)
class SpecialistConfig:
    """Validated specialist configuration for one science agent."""

    enabled: bool
    model: str
    project_defaults: ProjectCapabilityDefaults
    paper_reader: PaperReaderConfig
    reviewer: ResearchReviewerConfig

    def public_statuses(self) -> dict[str, dict[str, Any]]:
        """Return user-visible availability without internal prompts or limits."""

        return {
            "paper_reader": {
                "enabled": self.enabled and self.paper_reader.enabled,
                "auto_dispatch": self.paper_reader.auto_dispatch,
            },
            "research_reviewer": {
                "enabled": self.enabled and self.reviewer.enabled,
                "auto_dispatch": self.reviewer.auto_dispatch,
                "review_gate": self.reviewer.review_gate,
            },
        }


def parse_specialist_config(config: Mapping[str, Any] | None) -> SpecialistConfig:
    """Normalize an openppx config payload into specialist settings."""

    normalized = normalize_config(dict(config or {}))
    science = _mapping(normalized.get("science"))
    defaults = _mapping(science.get("projectDefaults"))
    specialists = _mapping(science.get("specialists"))
    paper_reader = _mapping(specialists.get("paperReader"))
    reviewer = _mapping(specialists.get("reviewer"))

    review_gate = str(reviewer.get("reviewGate") or "").strip().lower()
    if review_gate not in SUPPORTED_REVIEW_GATES:
        review_gate = "annotate"

    return SpecialistConfig(
        enabled=is_enabled(specialists.get("enabled"), default=True),
        model=str(specialists.get("model") or "").strip(),
        project_defaults=ProjectCapabilityDefaults(
            enabled_skills=_normalize_names(defaults.get("enabledSkills")),
            enabled_connectors=_normalize_names(defaults.get("enabledConnectors")),
            enabled_specialists=_normalize_names(
                defaults.get("enabledSpecialists"),
                allowed=SUPPORTED_SPECIALISTS,
            ),
        ),
        paper_reader=PaperReaderConfig(
            enabled=is_enabled(paper_reader.get("enabled"), default=True),
            auto_dispatch=is_enabled(paper_reader.get("autoDispatch"), default=True),
            max_papers=_bounded_int(paper_reader.get("maxPapers"), 6, 1, 20),
            max_source_chars=_bounded_int(paper_reader.get("maxSourceChars"), 30_000, 1_000, 200_000),
        ),
        reviewer=ResearchReviewerConfig(
            enabled=is_enabled(reviewer.get("enabled"), default=True),
            auto_dispatch=is_enabled(reviewer.get("autoDispatch"), default=True),
            review_gate=review_gate,
            max_findings=_bounded_int(reviewer.get("maxFindings"), 20, 1, 100),
            max_source_chars=_bounded_int(reviewer.get("maxSourceChars"), 60_000, 1_000, 200_000),
        ),
    )


def load_specialist_config(config_path: Path | None = None) -> SpecialistConfig:
    """Load specialist settings from the active agent config."""

    return parse_specialist_config(load_config(config_path=config_path))


def _normalize_names(value: Any, *, allowed: tuple[str, ...] | None = None) -> tuple[str, ...]:
    """Normalize capability names once while preserving configured order."""

    if not isinstance(value, list):
        return ()
    normalized: list[str] = []
    for item in value:
        name = str(item or "").strip().lower()
        if not name or name in normalized or (allowed is not None and name not in allowed):
            continue
        normalized.append(name)
    return tuple(normalized)


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _bounded_int(value: Any, default: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return min(max(parsed, minimum), maximum)
