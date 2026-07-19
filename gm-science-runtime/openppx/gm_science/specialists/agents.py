"""Google ADK agent factories for gm-science specialists."""

from __future__ import annotations

import json
import os
from typing import Any

from google.adk.agents import LlmAgent
from loguru import logger

from ...core.mcp_registry import build_mcp_toolsets
from ...core.provider import build_adk_model_from_env
from ...tooling.skills_adapter import get_registry
from ..infrastructure import filter_mcp_servers_by_network
from ..literature.tools import science_search
from .agent_tool import ConfiguredSpecialistTool, ProjectSpecialistTool
from .config import SpecialistConfig, load_specialist_config
from .registry import (
    SpecialistSpec,
    list_specialist_specs,
    specialist_configuration_issues,
    specialist_runtime_capability_ids,
)

_NATIVE_CONNECTORS = {"arxiv", "pubmed", "openalex"}
_MCP_SERVERS_ENV = "OPENPPX_MCP_SERVERS_JSON"

_PAPER_READER_INSTRUCTION = """You are the gm-science paper-reader specialist.
Call science_read_paper_bundle with exactly the project_id and paper_artifact_ids in the input.
Use only the returned evidence. Never fetch URLs, infer access to a full paper, or claim that an
abstract proves details that are not present. Preserve each evidence_scope exactly. Return the
required structured reading output, including limitations and confidence.
"""

_REVIEWER_INSTRUCTION = """You are the gm-science research-reviewer specialist.
Call science_read_review_bundle with exactly the project_id and target_artifact_id in the input.
Review only the returned artifact evidence. Put actionable findings before summary. Distinguish
blocking, major, and minor issues. Do not edit the target, call another specialist, or invent
citations. Explicitly list unsupported claims, missing evidence, evidence scopes, and review
limitations, including truncation or abstract-only evidence. Return the required structured output.
"""


def build_specialist_tools(
    *,
    config: SpecialistConfig | None = None,
    model: Any | None = None,
) -> list[ProjectSpecialistTool | ConfiguredSpecialistTool]:
    """Build enabled specialist agents as Project-aware ADK AgentTools."""

    resolved = config or load_specialist_config()
    if not resolved.enabled:
        return []
    specs = list_specialist_specs(resolved)
    tools: list[ProjectSpecialistTool | ConfiguredSpecialistTool] = []
    built_in_model: Any | None = model
    skill_ids, connector_ids = specialist_runtime_capability_ids()
    for spec in specs:
        if not spec.enabled:
            continue
        if spec.source == "built_in":
            if built_in_model is None:
                built_in_model = build_adk_model_from_env(resolved.model or None)
            tools.append(
                ProjectSpecialistTool(
                    spec=spec,
                    agent=_build_specialist_agent(spec, built_in_model),
                )
            )
            continue
        issues = specialist_configuration_issues(
            spec,
            skill_ids=skill_ids,
            connector_ids=connector_ids,
        )
        if not issues:
            custom_tools, tool_issues = _configured_specialist_tools(spec)
            issues += tool_issues
        else:
            custom_tools = []
        if issues:
            logger.warning(
                "Skipping custom specialist '{}': {}",
                spec.name,
                " ".join(dict.fromkeys(issues)),
            )
            continue
        custom_model = (
            model
            if model is not None
            else build_adk_model_from_env(spec.model or resolved.model or None)
        )
        agent = _build_configured_specialist_agent(
            spec,
            custom_model,
            tools=custom_tools,
            max_skill_chars=resolved.max_skill_chars,
        )
        tools.append(ConfiguredSpecialistTool(spec=spec, agent=agent))
    return tools


def specialist_dispatch_guidance(config: SpecialistConfig | None = None) -> str:
    """Build concise parent-agent routing rules from public specialist policy."""

    resolved = config or load_specialist_config()
    if not resolved.enabled:
        return ""
    specs = {spec.name: spec for spec in list_specialist_specs(resolved)}
    skill_ids, connector_ids = specialist_runtime_capability_ids()
    lines = [
        "# gm-science Specialists",
        "",
        "Use science_list_specialists with the current project_id before specialist "
        "dispatch when availability is unclear.",
        "Pass only explicit Project/session IDs, artifact IDs, and the user's requested "
        "focus; never pass hidden reasoning.",
        "Preserve evidence_scope exactly and describe metadata_abstract analysis as "
        "abstract-level evidence, not full-text reading.",
    ]
    if resolved.paper_reader.enabled and resolved.paper_reader.auto_dispatch:
        lines.append(
            "Use paper_reader for requests to read, compare, or synthesize saved paper artifacts."
        )
    if resolved.reviewer.enabled and resolved.reviewer.auto_dispatch:
        lines.append(
            "Use research_reviewer for explicit requests to critique a saved report or "
            "reading note."
        )
    for specialist in resolved.custom:
        spec = specs.get(specialist.name)
        issues = (
            specialist_configuration_issues(
                spec,
                skill_ids=skill_ids,
                connector_ids=connector_ids,
            )
            if spec is not None
            else ("Specialist definition is unavailable.",)
        )
        if specialist.enabled and specialist.auto_dispatch and not issues:
            lines.append(
                f"Use {specialist.name} when the request matches this configured role: "
                f"{specialist.description}"
            )
    lines.append(
        "The host handles automatic report review separately; do not recursively review "
        "critique_report artifacts."
    )
    return "\n".join(lines) + "\n"


def _build_specialist_agent(spec: SpecialistSpec, model: Any) -> LlmAgent:
    instruction = (
        _PAPER_READER_INSTRUCTION if spec.name == "paper_reader" else _REVIEWER_INSTRUCTION
    )
    return LlmAgent(
        name=spec.name,
        description=spec.description,
        model=model,
        instruction=instruction,
        tools=[spec.read_tool],
        input_schema=spec.input_schema,
        output_schema=spec.output_schema,
        include_contents="none",
        disallow_transfer_to_parent=True,
        disallow_transfer_to_peers=True,
    )


def _build_configured_specialist_agent(
    spec: SpecialistSpec,
    model: Any,
    *,
    tools: list[Any],
    max_skill_chars: int,
) -> LlmAgent:
    """Build one config-defined specialist with only its assigned capabilities."""

    instruction = f"""You are the gm-science custom specialist `{spec.name}` ({spec.title}).
Work only on the structured objective and context supplied in the input. Do not claim access to
tools, data, files, or evidence that are not explicitly available in this child run. Return the
required structured specialist output with findings, recommendations, limitations, and confidence.
"""
    if spec.instructions:
        instruction += f"\n# Additional instructions\n\n{spec.instructions}\n"
    skill_context = _assigned_skill_context(spec.skills, max_chars=max_skill_chars)
    if skill_context:
        instruction += "\n# Assigned Skill reference material\n\n" + skill_context
    return LlmAgent(
        name=spec.name,
        description=spec.description,
        model=model,
        instruction=instruction,
        tools=tools,
        input_schema=spec.input_schema,
        output_schema=spec.output_schema,
        include_contents="none",
        disallow_transfer_to_parent=True,
        disallow_transfer_to_peers=True,
    )


def _configured_specialist_tools(spec: SpecialistSpec) -> tuple[list[Any], tuple[str, ...]]:
    """Build the configured native and MCP tools for one custom specialist."""

    tools: list[Any] = []
    issues: list[str] = []
    native_sources = tuple(
        connector.casefold()
        for connector in spec.connectors
        if connector.casefold() in _NATIVE_CONNECTORS
    )
    if native_sources:
        tools.append(_literature_search_tool(native_sources))

    raw_servers, _blocked_servers = filter_mcp_servers_by_network(_mcp_servers_from_env())
    selected_server_names = {
        connector.split(":", 1)[1].casefold()
        for connector in spec.connectors
        if connector.casefold().startswith("mcp:") and ":" in connector
    }
    selected_servers = {
        name: value
        for name, value in raw_servers.items()
        if str(name).casefold() in selected_server_names
    }
    tools.extend(build_mcp_toolsets(selected_servers, log_registered=False))
    built_server_names = {str(tool.meta.name).casefold() for tool in tools if hasattr(tool, "meta")}
    missing_servers = sorted(selected_server_names.difference(built_server_names))
    if missing_servers:
        issues.append(f"Unavailable MCP servers: {', '.join(missing_servers)}.")
    return tools, tuple(issues)


def _literature_search_tool(allowed_sources: tuple[str, ...]):
    """Return a literature-search tool restricted to assigned native Connectors."""

    def search_assigned_literature(
        query: str,
        project_id: str,
        session_id: str = "",
        sources: list[str] | None = None,
        max_results: int = 10,
        save: bool = True,
    ) -> dict[str, Any]:
        """Search only the scholarly sources assigned to this specialist."""

        requested = (
            list(allowed_sources)
            if sources is None
            else [str(item).strip().lower() for item in sources]
        )
        unsupported = [item for item in requested if item not in allowed_sources]
        if unsupported:
            raise ValueError(
                f"Sources are not assigned to this specialist: {', '.join(unsupported)}."
            )
        return science_search(
            query=query,
            project_id=project_id,
            session_id=session_id,
            sources=requested,
            max_results=max_results,
            save=save,
        )

    search_assigned_literature.__name__ = "science_search"
    return search_assigned_literature


def _assigned_skill_context(skill_ids: tuple[str, ...], *, max_chars: int) -> str:
    """Load a bounded set of assigned SKILL.md files without exposing file paths."""

    if not skill_ids:
        return ""
    registry = get_registry()
    available = {item.name.casefold(): item.name for item in registry.list_skills()}
    remaining = max_chars
    sections: list[str] = []
    for requested in skill_ids:
        canonical = available.get(requested.casefold())
        if canonical is None or remaining <= 0:
            continue
        content = registry.read_skill(canonical)
        excerpt = content[:remaining]
        sections.append(f"<skill name=\"{canonical}\">\n{excerpt}\n</skill>")
        remaining -= len(excerpt)
    return "\n\n".join(sections) + ("\n" if sections else "")


def _mcp_servers_from_env() -> dict[str, Any]:
    raw = os.getenv(_MCP_SERVERS_ENV, "").strip()
    if not raw:
        return {}
    try:
        payload = json.loads(raw)
    except (TypeError, ValueError):
        return {}
    return payload if isinstance(payload, dict) else {}
