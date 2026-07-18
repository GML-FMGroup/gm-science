"""Public capability catalog for gm-science projects."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Iterable, Literal

from ..tooling.skills_adapter import SkillInfo, SkillRegistry
from .literature.config import load_literature_config
from .models import ProjectRecord
from .specialists.config import load_specialist_config
from .specialists.registry import list_specialist_specs

CapabilityKind = Literal["skill", "connector", "specialist"]
CapabilitySource = Literal["built_in", "local", "external"]

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
_DISPLAY_TOKENS = {
    "api": "API",
    "cli": "CLI",
    "docx": "DOCX",
    "github": "GitHub",
    "imap": "IMAP",
    "minimax": "MiniMax",
    "opencv": "OpenCV",
    "pptx": "PPTX",
    "smtp": "SMTP",
    "ui": "UI",
    "ux": "UX",
    "xlsx": "XLSX",
}
_MAX_PUBLIC_SKILL_FILES = 100


def build_capability_catalog(
    *,
    config_path: Path,
    project: ProjectRecord | None = None,
    skill_registry: SkillRegistry | None = None,
) -> list[dict[str, Any]]:
    """Build the stable public capability catalog for an optional Project."""

    literature = load_literature_config(config_path)
    specialists = load_specialist_config(config_path)
    defaults = specialists.project_defaults
    project_values = _project_capability_sets(project)

    items: list[dict[str, Any]] = []
    registry = skill_registry or _skill_registry_for_config(config_path)
    for skill in registry.list_skills():
        items.append(
            _skill_capability_payload(
                skill=skill,
                default_enabled=skill.name in defaults.enabled_skills,
                project_enabled=_project_enabled(project_values, "skill", skill.name),
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
                source="built_in",
                available=bool(source["enabled"]),
                default_enabled=source_id in defaults.enabled_connectors,
                project_enabled=_project_enabled(project_values, "connector", source_id),
                status="ready" if raw_status == "ok" else raw_status,
                status_detail=str(source["configuration_message"] or ""),
                metadata={"api_base": str(source["api_base"])},
            )
        )

    for spec in list_specialist_specs(specialists):
        items.append(
            _capability_payload(
                capability_id=spec.name,
                kind="specialist",
                name=spec.title,
                description=spec.description,
                source="built_in",
                available=spec.enabled,
                default_enabled=spec.name in defaults.enabled_specialists,
                project_enabled=_project_enabled(project_values, "specialist", spec.name),
                status="ready" if spec.enabled else "disabled",
                status_detail="" if spec.enabled else "Disabled in science.specialists configuration.",
                metadata={
                    "auto_dispatch": spec.auto_dispatch,
                    "read_only": spec.read_only,
                },
            )
        )
    return items


def _skill_registry_for_config(config_path: Path) -> SkillRegistry:
    """Build the Skill registry used by the configured gm-science agent."""

    builtin_raw = os.getenv("OPENPPX_BUILTIN_SKILLS_DIR", "").strip()
    builtin_dir = Path(builtin_raw).expanduser() if builtin_raw else None
    return SkillRegistry(
        agent_home=config_path.parent,
        builtin_skills_dir=builtin_dir,
    )


def _skill_capability_payload(
    *,
    skill: SkillInfo,
    default_enabled: bool,
    project_enabled: bool | None,
) -> dict[str, Any]:
    """Project one discovered Skill into the public capability contract."""

    frontmatter = _read_public_skill_frontmatter(skill.path)
    files, file_count = _public_skill_files(skill.path.parent)
    source = "local" if skill.source == "workspace" else "built_in"
    metadata: dict[str, Any] = {
        "registry_source": skill.source,
        "file_count": file_count,
        "files_truncated": file_count > len(files),
    }
    canonical_name = skill.path.parent.name
    if skill.name != canonical_name:
        metadata["alias_of"] = canonical_name
    return _capability_payload(
        capability_id=skill.name,
        kind="skill",
        name=_display_skill_name(skill.name),
        description=skill.description,
        source=source,
        version=frontmatter.get("version", ""),
        license_name=frontmatter.get("license", ""),
        files=files,
        available=True,
        default_enabled=default_enabled,
        project_enabled=project_enabled,
        status="ready",
        status_detail="",
        metadata=metadata,
    )


def _display_skill_name(name: str) -> str:
    """Render a stable human-readable name from a Skill identifier."""

    tokens = name.replace("_", "-").split("-")
    return " ".join(_DISPLAY_TOKENS.get(token.lower(), token.capitalize()) for token in tokens if token)


def _read_public_skill_frontmatter(skill_path: Path) -> dict[str, str]:
    """Read selected scalar metadata without exposing arbitrary frontmatter."""

    try:
        lines = skill_path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return {}
    if not lines or lines[0].strip() != "---":
        return {}
    selected: dict[str, str] = {}
    for line in lines[1:]:
        if line.strip() == "---":
            break
        key, separator, value = line.partition(":")
        normalized_key = key.strip().lower()
        if not separator or normalized_key not in {"version", "license"}:
            continue
        selected[normalized_key] = value.strip().strip("\"'")
    return selected


def _public_skill_files(skill_dir: Path) -> tuple[list[str], int]:
    """Return a bounded relative file inventory for one Skill directory."""

    relative_files = sorted(
        (
            path.relative_to(skill_dir).as_posix()
            for path in skill_dir.rglob("*")
            if path.is_file()
        ),
        key=str.casefold,
    )
    return relative_files[:_MAX_PUBLIC_SKILL_FILES], len(relative_files)


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
    source: CapabilitySource,
    version: str = "",
    license_name: str = "",
    files: list[str] | None = None,
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
        "source": source,
        "version": version,
        "license": license_name,
        "files": list(files or []),
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
