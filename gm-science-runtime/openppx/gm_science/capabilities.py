"""Public capability catalog for gm-science projects."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable, Literal

from .literature.config import load_literature_config
from .models import ProjectRecord
from .specialists.config import load_specialist_config
from .specialists.registry import list_specialist_specs

CapabilityKind = Literal["skill", "connector", "specialist"]

_SKILL_DESCRIPTIONS = {
    "literature-review": "Search scholarly sources, synthesize evidence, and register a cited review.",
}
_CONNECTOR_NAMES = {
    "arxiv": "arXiv",
    "pubmed": "PubMed",
    "openalex": "OpenAlex",
}
_CONNECTOR_DESCRIPTIONS = {
    "arxiv": "Search open-access preprints across scientific and technical fields.",
    "pubmed": "Search biomedical literature indexed by the NCBI PubMed service.",
    "openalex": "Search scholarly works and citation metadata from OpenAlex.",
}


def build_capability_catalog(
    *,
    config_path: Path,
    project: ProjectRecord | None = None,
) -> list[dict[str, Any]]:
    """Build the stable public capability catalog for an optional Project."""

    literature = load_literature_config(config_path)
    specialists = load_specialist_config(config_path)
    defaults = specialists.project_defaults
    project_values = _project_capability_sets(project)

    items: list[dict[str, Any]] = []
    skill_path = Path(__file__).resolve().parents[1] / "skills" / "literature-review" / "SKILL.md"
    skill_available = skill_path.is_file()
    items.append(
        _capability_payload(
            capability_id="literature-review",
            kind="skill",
            name="Literature Review",
            description=_SKILL_DESCRIPTIONS["literature-review"],
            available=skill_available,
            default_enabled="literature-review" in defaults.enabled_skills,
            project_enabled=_project_enabled(project_values, "skill", "literature-review"),
            status="ready" if skill_available else "disabled",
            status_detail="" if skill_available else "The bundled literature-review skill is unavailable.",
            metadata={"source": "built_in"},
        )
    )

    source_statuses = literature.public_source_statuses()
    for source_id in ("arxiv", "pubmed", "openalex"):
        source = source_statuses[source_id]
        raw_status = str(source["status"])
        items.append(
            _capability_payload(
                capability_id=source_id,
                kind="connector",
                name=_CONNECTOR_NAMES[source_id],
                description=_CONNECTOR_DESCRIPTIONS[source_id],
                available=bool(source["enabled"]),
                default_enabled=source_id in defaults.enabled_connectors,
                project_enabled=_project_enabled(project_values, "connector", source_id),
                status="ready" if raw_status == "ok" else raw_status,
                status_detail=str(source["configuration_message"] or ""),
                metadata={"source": "built_in", "api_base": str(source["api_base"])},
            )
        )

    for spec in list_specialist_specs(specialists):
        items.append(
            _capability_payload(
                capability_id=spec.name,
                kind="specialist",
                name=spec.title,
                description=spec.description,
                available=spec.enabled,
                default_enabled=spec.name in defaults.enabled_specialists,
                project_enabled=_project_enabled(project_values, "specialist", spec.name),
                status="ready" if spec.enabled else "disabled",
                status_detail="" if spec.enabled else "Disabled in science.specialists configuration.",
                metadata={
                    "source": "built_in",
                    "auto_dispatch": spec.auto_dispatch,
                    "read_only": spec.read_only,
                },
            )
        )
    return items


def normalize_capability_selection(
    *,
    kind: CapabilityKind,
    values: Iterable[Any],
    catalog: list[dict[str, Any]],
) -> list[str]:
    """Validate capability IDs and return them in stable catalog order."""

    selected = {str(value or "").strip().lower() for value in values if str(value or "").strip()}
    allowed = [str(item["id"]) for item in catalog if item["kind"] == kind]
    unknown = sorted(selected.difference(allowed))
    if unknown:
        rendered = ", ".join(unknown)
        raise ValueError(f"Unsupported {kind} capability: {rendered}")
    return [capability_id for capability_id in allowed if capability_id in selected]


def _capability_payload(
    *,
    capability_id: str,
    kind: CapabilityKind,
    name: str,
    description: str,
    available: bool,
    default_enabled: bool,
    project_enabled: bool | None,
    status: str,
    status_detail: str,
    metadata: dict[str, Any],
) -> dict[str, Any]:
    """Build one serializable public capability record."""

    return {
        "id": capability_id,
        "kind": kind,
        "name": name,
        "description": description,
        "available": available,
        "default_enabled": default_enabled,
        "project_enabled": project_enabled,
        "status": status,
        "status_detail": status_detail,
        "metadata": metadata,
    }


def _project_capability_sets(project: ProjectRecord | None) -> dict[CapabilityKind, set[str]] | None:
    if project is None:
        return None
    return {
        "skill": set(project.enabled_skills),
        "connector": set(project.enabled_connectors),
        "specialist": set(project.enabled_specialists),
    }


def _project_enabled(
    project_values: dict[CapabilityKind, set[str]] | None,
    kind: CapabilityKind,
    capability_id: str,
) -> bool | None:
    if project_values is None:
        return None
    return capability_id in project_values[kind]
