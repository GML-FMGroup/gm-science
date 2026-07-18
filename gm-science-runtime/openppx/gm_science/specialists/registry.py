"""Specialist registry and public capability projection."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any, Callable

from pydantic import BaseModel

from ...core.mcp_registry import describe_mcp_server_config
from ...tooling.skills_adapter import get_registry
from ..literature.config import load_literature_config
from ..store import GmScienceStore
from .config import SpecialistConfig, load_specialist_config
from .models import (
    ConfiguredSpecialistInput,
    ConfiguredSpecialistOutput,
    PaperReaderInput,
    PaperReaderOutput,
    ReviewerInput,
    ReviewerOutput,
)
from .tools import science_read_paper_bundle, science_read_review_bundle

_MCP_SERVERS_ENV = "OPENPPX_MCP_SERVERS_JSON"


@dataclass(frozen=True, slots=True)
class SpecialistSpec:
    """Stable registry entry for one bounded specialist agent."""

    name: str
    title: str
    description: str
    input_schema: type[BaseModel]
    output_schema: type[BaseModel]
    read_tool: Callable[..., dict[str, Any]] | None
    auto_dispatch: bool
    enabled: bool
    read_only: bool = True
    network_access: bool = False
    shell_access: bool = False
    source: str = "built_in"
    model: str = ""
    instructions: str = ""
    skills: tuple[str, ...] = ()
    connectors: tuple[str, ...] = ()
    configuration_error: str = ""


def list_specialist_specs(config: SpecialistConfig | None = None) -> tuple[SpecialistSpec, ...]:
    """Return built-in and configured specialists in stable display order."""

    resolved = config or load_specialist_config()
    built_in = (
        SpecialistSpec(
            name="paper_reader",
            title="Paper Reader",
            description=(
                "Analyze saved paper artifacts using only their metadata, abstracts, and bounded "
                "Project-local text. Use for explicit paper reading and cross-paper comparison."
            ),
            input_schema=PaperReaderInput,
            output_schema=PaperReaderOutput,
            read_tool=science_read_paper_bundle,
            auto_dispatch=resolved.paper_reader.auto_dispatch,
            enabled=resolved.enabled and resolved.paper_reader.enabled,
        ),
        SpecialistSpec(
            name="research_reviewer",
            title="Research Reviewer",
            description=(
                "Review one saved report or reading note and return findings-first, actionable critique. "
                "Use for explicit review requests; automatic report review is handled by the host gate."
            ),
            input_schema=ReviewerInput,
            output_schema=ReviewerOutput,
            read_tool=science_read_review_bundle,
            auto_dispatch=resolved.reviewer.auto_dispatch,
            enabled=resolved.enabled and resolved.reviewer.enabled,
        ),
    )
    custom = tuple(
        SpecialistSpec(
            name=item.name,
            title=item.title,
            description=item.description,
            input_schema=ConfiguredSpecialistInput,
            output_schema=ConfiguredSpecialistOutput,
            read_tool=None,
            auto_dispatch=item.auto_dispatch,
            enabled=resolved.enabled and item.enabled,
            read_only=not any(
                connector.casefold().startswith("mcp:") for connector in item.connectors
            ),
            network_access=bool(item.connectors),
            source="local",
            model=item.model or resolved.model,
            instructions=item.instructions,
            skills=item.skills,
            connectors=item.connectors,
            configuration_error=item.configuration_error,
        )
        for item in resolved.custom
    )
    return built_in + custom


def specialist_configuration_issues(
    spec: SpecialistSpec,
    *,
    skill_ids: set[str],
    connector_ids: set[str],
) -> tuple[str, ...]:
    """Return stable configuration issues for one specialist definition."""

    issues = [spec.configuration_error] if spec.configuration_error else []
    available_skills = {item.casefold() for item in skill_ids}
    available_connectors = {item.casefold() for item in connector_ids}
    missing_skills = [item for item in spec.skills if item.casefold() not in available_skills]
    missing_connectors = [
        item for item in spec.connectors if item.casefold() not in available_connectors
    ]
    if missing_skills:
        issues.append(f"Missing Skills: {', '.join(missing_skills)}.")
    if missing_connectors:
        issues.append(f"Missing Connectors: {', '.join(missing_connectors)}.")
    return tuple(issues)


def specialist_runtime_capability_ids() -> tuple[set[str], set[str]]:
    """Return capability IDs that can back configured specialists in this process."""

    skill_ids = {item.name for item in get_registry().list_skills()}
    literature = load_literature_config()
    connector_ids = {
        source_id for source_id, source in literature.sources.items() if source.enabled
    }
    raw = os.getenv(_MCP_SERVERS_ENV, "").strip()
    try:
        mcp_servers = json.loads(raw) if raw else {}
    except (TypeError, ValueError):
        mcp_servers = {}
    if isinstance(mcp_servers, dict):
        for raw_name, raw_config in mcp_servers.items():
            name = str(raw_name)
            description = describe_mcp_server_config(name, raw_config)
            if description["available"] is True:
                connector_ids.add(f"mcp:{name}")
    return skill_ids, connector_ids


def science_list_specialists(project_id: str) -> dict[str, Any]:
    """List public specialist availability for one Project."""

    store = GmScienceStore()
    project = store.get_project(str(project_id or "").strip())
    if project is None:
        raise ValueError(f"Project '{project_id}' was not found.")
    enabled_for_project = set(project.enabled_specialists)
    skill_ids, connector_ids = specialist_runtime_capability_ids()
    specs = list_specialist_specs()
    payloads: list[dict[str, Any]] = []
    for spec in specs:
        issues = list(
            specialist_configuration_issues(
                spec,
                skill_ids=skill_ids,
                connector_ids=connector_ids,
            )
        )
        missing_project_skills = _missing_project_capabilities(spec.skills, project.enabled_skills)
        missing_project_connectors = _missing_project_capabilities(
            spec.connectors,
            project.enabled_connectors,
        )
        if missing_project_skills:
            issues.append(f"Project-disabled Skills: {', '.join(missing_project_skills)}.")
        if missing_project_connectors:
            issues.append(f"Project-disabled Connectors: {', '.join(missing_project_connectors)}.")
        project_enabled = spec.name in enabled_for_project
        if not spec.enabled:
            issues.append("Disabled by configuration.")
        if not project_enabled:
            issues.append("Not enabled for this Project.")
        available = spec.enabled and project_enabled and not issues
        payloads.append(
            {
                "name": spec.name,
                "title": spec.title,
                "description": spec.description,
                "enabled": spec.enabled,
                "project_enabled": project_enabled,
                "available": available,
                "status": "ready" if available else "unavailable",
                "status_detail": " ".join(issues),
                "auto_dispatch": spec.auto_dispatch,
                "read_only": spec.read_only,
                "source": spec.source,
                "skills": list(spec.skills),
                "connectors": list(spec.connectors),
            }
        )
    return {
        "project_id": project.id,
        "specialists": payloads,
    }


def _missing_project_capabilities(
    required: tuple[str, ...],
    enabled: list[str],
) -> list[str]:
    available = {item.casefold() for item in enabled}
    return [item for item in required if item.casefold() not in available]
