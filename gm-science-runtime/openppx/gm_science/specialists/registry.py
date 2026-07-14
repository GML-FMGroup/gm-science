"""Built-in specialist registry and public capability projection."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from pydantic import BaseModel

from ..store import GmScienceStore
from .config import SpecialistConfig, load_specialist_config
from .models import PaperReaderInput, PaperReaderOutput, ReviewerInput, ReviewerOutput
from .tools import science_read_paper_bundle, science_read_review_bundle


@dataclass(frozen=True, slots=True)
class SpecialistSpec:
    """Stable registry entry for one bounded specialist agent."""

    name: str
    title: str
    description: str
    input_schema: type[BaseModel]
    output_schema: type[BaseModel]
    read_tool: Callable[..., dict[str, Any]]
    auto_dispatch: bool
    enabled: bool
    read_only: bool = True
    network_access: bool = False
    shell_access: bool = False


def list_specialist_specs(config: SpecialistConfig | None = None) -> tuple[SpecialistSpec, ...]:
    """Return the built-in specialist registry in stable display order."""

    resolved = config or load_specialist_config()
    return (
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


def science_list_specialists(project_id: str) -> dict[str, Any]:
    """List public specialist availability for one Project."""

    store = GmScienceStore()
    project = store.get_project(str(project_id or "").strip())
    if project is None:
        raise ValueError(f"Project '{project_id}' was not found.")
    enabled_for_project = set(project.enabled_specialists)
    return {
        "project_id": project.id,
        "specialists": [
            {
                "name": spec.name,
                "title": spec.title,
                "description": spec.description,
                "enabled": spec.enabled,
                "project_enabled": spec.name in enabled_for_project,
                "available": spec.enabled and spec.name in enabled_for_project,
                "auto_dispatch": spec.auto_dispatch,
                "read_only": spec.read_only,
            }
            for spec in list_specialist_specs()
        ],
    }
