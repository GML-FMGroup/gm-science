"""Google ADK agent factories for gm-science specialists."""

from __future__ import annotations

from typing import Any

from google.adk.agents import LlmAgent

from ...core.provider import build_adk_model_from_env
from .agent_tool import ProjectSpecialistTool
from .config import SpecialistConfig, load_specialist_config
from .registry import SpecialistSpec, list_specialist_specs

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
) -> list[ProjectSpecialistTool]:
    """Build enabled specialist agents as Project-aware ADK AgentTools."""

    resolved = config or load_specialist_config()
    if not resolved.enabled:
        return []
    resolved_model = model if model is not None else build_adk_model_from_env(resolved.model or None)
    return [
        ProjectSpecialistTool(spec=spec, agent=_build_specialist_agent(spec, resolved_model))
        for spec in list_specialist_specs(resolved)
        if spec.enabled
    ]


def specialist_dispatch_guidance(config: SpecialistConfig | None = None) -> str:
    """Build concise parent-agent routing rules from public specialist policy."""

    resolved = config or load_specialist_config()
    if not resolved.enabled:
        return ""
    lines = [
        "# gm-science Specialists",
        "",
        "Use science_list_specialists with the current project_id before specialist dispatch when availability is unclear.",
        "Pass only explicit Project/session IDs, artifact IDs, and the user's requested focus; never pass hidden reasoning.",
        "Preserve evidence_scope exactly and describe metadata_abstract analysis as abstract-level evidence, not full-text reading.",
    ]
    if resolved.paper_reader.enabled and resolved.paper_reader.auto_dispatch:
        lines.append(
            "Use paper_reader for requests to read, compare, or synthesize saved paper artifacts."
        )
    if resolved.reviewer.enabled and resolved.reviewer.auto_dispatch:
        lines.append(
            "Use research_reviewer for explicit requests to critique a saved report or reading note."
        )
    lines.append("The host handles automatic report review separately; do not recursively review critique_report artifacts.")
    return "\n".join(lines) + "\n"


def _build_specialist_agent(spec: SpecialistSpec, model: Any) -> LlmAgent:
    instruction = _PAPER_READER_INSTRUCTION if spec.name == "paper_reader" else _REVIEWER_INSTRUCTION
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
