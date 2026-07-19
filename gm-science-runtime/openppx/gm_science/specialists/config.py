"""Configuration parsing for gm-science specialist agents."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ...core.config import load_config, normalize_config
from ...core.env_utils import is_enabled

SUPPORTED_SPECIALISTS = ("paper_reader", "research_reviewer")
SUPPORTED_REVIEW_GATES = ("off", "annotate")
_SPECIALIST_ID_PATTERN = re.compile(r"^[a-z][a-z0-9_]{0,63}$")


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
class CustomSpecialistConfig:
    """One user-defined specialist loaded from the local agent configuration."""

    name: str
    title: str
    description: str
    enabled: bool
    auto_dispatch: bool
    model: str
    instructions: str
    skills: tuple[str, ...]
    connectors: tuple[str, ...]
    connector_tools: dict[str, tuple[str, ...]]
    configuration_error: str = ""


@dataclass(frozen=True, slots=True)
class SpecialistConfig:
    """Validated specialist configuration for one science agent."""

    enabled: bool
    model: str
    max_skill_chars: int
    project_defaults: ProjectCapabilityDefaults
    paper_reader: PaperReaderConfig
    reviewer: ResearchReviewerConfig
    custom: tuple[CustomSpecialistConfig, ...]

    def public_statuses(self) -> dict[str, dict[str, Any]]:
        """Return user-visible availability without internal prompts or limits."""

        statuses = {
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
        statuses.update(
            {
                specialist.name: {
                    "enabled": self.enabled
                    and specialist.enabled
                    and not specialist.configuration_error,
                    "auto_dispatch": specialist.auto_dispatch,
                }
                for specialist in self.custom
            }
        )
        return statuses


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
        max_skill_chars=_bounded_int(specialists.get("maxSkillChars"), 60_000, 1_000, 200_000),
        project_defaults=ProjectCapabilityDefaults(
            enabled_skills=_normalize_names(defaults.get("enabledSkills")),
            enabled_connectors=_normalize_names(defaults.get("enabledConnectors")),
            enabled_specialists=_normalize_names(defaults.get("enabledSpecialists")),
        ),
        paper_reader=PaperReaderConfig(
            enabled=is_enabled(paper_reader.get("enabled"), default=True),
            auto_dispatch=is_enabled(paper_reader.get("autoDispatch"), default=True),
            max_papers=_bounded_int(paper_reader.get("maxPapers"), 6, 1, 20),
            max_source_chars=_bounded_int(
                paper_reader.get("maxSourceChars"),
                30_000,
                1_000,
                200_000,
            ),
        ),
        reviewer=ResearchReviewerConfig(
            enabled=is_enabled(reviewer.get("enabled"), default=True),
            auto_dispatch=is_enabled(reviewer.get("autoDispatch"), default=True),
            review_gate=review_gate,
            max_findings=_bounded_int(reviewer.get("maxFindings"), 20, 1, 100),
            max_source_chars=_bounded_int(reviewer.get("maxSourceChars"), 60_000, 1_000, 200_000),
        ),
        custom=_parse_custom_specialists(specialists.get("custom")),
    )


def load_specialist_config(config_path: Path | None = None) -> SpecialistConfig:
    """Load specialist settings from the active agent config."""

    return parse_specialist_config(load_config(config_path=config_path))


def _normalize_names(value: Any) -> tuple[str, ...]:
    """Normalize capability names once while preserving configured order."""

    if not isinstance(value, list):
        return ()
    normalized: list[str] = []
    for item in value:
        name = str(item or "").strip().lower()
        if not name or name in normalized:
            continue
        normalized.append(name)
    return tuple(normalized)


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _parse_custom_specialists(value: Any) -> tuple[CustomSpecialistConfig, ...]:
    """Parse custom specialists while retaining invalid entries for diagnostics."""

    if not isinstance(value, Mapping):
        return ()
    parsed: list[CustomSpecialistConfig] = []
    for index, raw_name in enumerate(sorted(value, key=lambda item: str(item).casefold())):
        configured_name = str(raw_name or "").strip()
        name = configured_name or f"invalid_specialist_{index + 1}"
        raw_config = value[raw_name]
        errors: list[str] = []
        if not configured_name or not _SPECIALIST_ID_PATTERN.fullmatch(configured_name):
            errors.append("Agent ID must match ^[a-z][a-z0-9_]{0,63}$.")
        if name in SUPPORTED_SPECIALISTS:
            errors.append("Agent ID conflicts with a built-in specialist.")
        if not isinstance(raw_config, Mapping):
            errors.append("Specialist configuration must be an object.")
        item = _mapping(raw_config)
        title = str(item.get("title") or item.get("name") or _display_name(name)).strip()
        description = str(item.get("description") or "").strip()
        if not title:
            errors.append("Specialist title is required.")
        if not description:
            errors.append("Specialist description is required.")
        parsed.append(
            CustomSpecialistConfig(
                name=name,
                title=title or name or "Invalid specialist",
                description=description,
                enabled=is_enabled(item.get("enabled"), default=True),
                auto_dispatch=is_enabled(item.get("autoDispatch"), default=False),
                model=str(item.get("model") or "").strip(),
                instructions=str(item.get("instructions") or "").strip(),
                skills=_normalize_capability_ids(item.get("skills")),
                connectors=_normalize_capability_ids(item.get("connectors")),
                connector_tools=_normalize_connector_tools(item.get("connectorTools")),
                configuration_error=" ".join(errors),
            )
        )
    return tuple(parsed)


def _normalize_capability_ids(value: Any) -> tuple[str, ...]:
    """Normalize capability IDs without changing case-sensitive MCP server names."""

    if not isinstance(value, list):
        return ()
    normalized: list[str] = []
    seen: set[str] = set()
    for item in value:
        capability_id = str(item or "").strip()
        key = capability_id.casefold()
        if not capability_id or key in seen:
            continue
        seen.add(key)
        normalized.append(capability_id)
    return tuple(normalized)


def _normalize_connector_tools(value: Any) -> dict[str, tuple[str, ...]]:
    """Normalize per-Connector tool allowlists without widening invalid entries."""

    if not isinstance(value, Mapping):
        return {}
    normalized: dict[str, tuple[str, ...]] = {}
    for raw_connector_id, raw_tools in value.items():
        connector_id = str(raw_connector_id or "").strip()
        if not connector_id or not isinstance(raw_tools, list):
            continue
        tools: list[str] = []
        seen: set[str] = set()
        for raw_tool in raw_tools:
            tool = str(raw_tool or "").strip()
            key = tool.casefold()
            if not tool or key in seen:
                continue
            seen.add(key)
            tools.append(tool)
        if tools:
            normalized[connector_id] = tuple(tools)
    return normalized


def _display_name(value: str) -> str:
    return " ".join(token.capitalize() for token in value.replace("-", "_").split("_") if token)


def _bounded_int(value: Any, default: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return min(max(parsed, minimum), maximum)
