"""Public capability catalog for gm-science projects."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Iterable, Literal

from ..core.config import load_config
from ..core.mcp_registry import describe_mcp_server_config
from ..tooling.skills_adapter import SkillInfo, SkillRegistry
from .catalog import (
    BUILTIN_SCIENCE_SKILLS,
    SCIENCE_CONNECTORS,
    ScienceCapabilityDefinition,
)
from .literature.config import load_literature_config
from .infrastructure import parse_network_policy
from .models import ProjectRecord
from .specialists.config import load_specialist_config
from .specialists.registry import list_specialist_specs, specialist_configuration_issues

CapabilityKind = Literal["skill", "connector", "specialist"]
CapabilitySource = Literal["built_in", "local", "external"]

_DISPLAY_TOKENS = {
    "api": "API",
    "cli": "CLI",
    "docx": "DOCX",
    "github": "GitHub",
    "imap": "IMAP",
    "minimax": "MiniMax",
    "mcp": "MCP",
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
    config = load_config(config_path=config_path)
    network_policy = parse_network_policy(config)
    defaults = specialists.project_defaults
    project_values = _project_capability_sets(project)

    items: list[dict[str, Any]] = []
    registry = skill_registry or _skill_registry_for_config(config_path)
    discovered_skills = {skill.name.casefold(): skill for skill in registry.list_skills()}
    emitted_skill_ids: set[str] = set()
    for definition in BUILTIN_SCIENCE_SKILLS:
        skill = discovered_skills.get(definition.id.casefold())
        if skill is None:
            items.append(
                _unavailable_product_capability(
                    definition=definition,
                    kind="skill",
                    default_enabled=definition.id in defaults.enabled_skills,
                    project_enabled=_project_enabled(project_values, "skill", definition.id),
                )
            )
        else:
            items.append(
                _skill_capability_payload(
                    skill=skill,
                    definition=definition,
                    default_enabled=definition.id in defaults.enabled_skills,
                    project_enabled=_project_enabled(project_values, "skill", definition.id),
                )
            )
        emitted_skill_ids.add(definition.id.casefold())

    for skill in registry.list_skills():
        if skill.source != "workspace" or skill.name.casefold() in emitted_skill_ids:
            continue
        items.append(
            _skill_capability_payload(
                skill=skill,
                definition=None,
                default_enabled=skill.name in defaults.enabled_skills,
                project_enabled=_project_enabled(project_values, "skill", skill.name),
            )
        )

    source_statuses = literature.public_source_statuses()
    for definition in SCIENCE_CONNECTORS:
        source = source_statuses.get(definition.id)
        if source is None:
            items.append(
                _unavailable_product_capability(
                    definition=definition,
                    kind="connector",
                    default_enabled=definition.id in defaults.enabled_connectors,
                    project_enabled=_project_enabled(project_values, "connector", definition.id),
                )
            )
            continue
        raw_status = str(source["status"])
        items.append(
            _capability_payload(
                capability_id=definition.id,
                kind="connector",
                name=definition.name,
                description=definition.description,
                source=definition.source,
                available=bool(source["enabled"]),
                default_enabled=definition.id in defaults.enabled_connectors,
                project_enabled=_project_enabled(project_values, "connector", definition.id),
                status="ready" if raw_status == "ok" else raw_status,
                status_detail=str(source["configuration_message"] or ""),
                metadata={
                    "api_base": str(source["api_base"]),
                    "catalog_group": definition.group,
                    "implementation_status": "native",
                    "registry_source": "product_catalog",
                },
            )
        )

    tools = config.get("tools")
    mcp_servers = tools.get("mcpServers", {}) if isinstance(tools, dict) else {}
    if isinstance(mcp_servers, dict):
        for raw_server_name in sorted(mcp_servers, key=lambda value: str(value).casefold()):
            server_name = str(raw_server_name)
            raw_server = mcp_servers[raw_server_name]
            description = describe_mcp_server_config(server_name, raw_server)
            metadata = dict(description["metadata"])
            metadata["catalog_group"] = "custom"
            transport = str(metadata.get("transport") or "")
            available = bool(description["available"])
            status = str(description["status"])
            status_detail = str(description["status_detail"])
            server_url = str(raw_server.get("url") or "").strip() if isinstance(raw_server, dict) else ""
            configured_name = _public_configured_text(raw_server, "name", maximum=120)
            configured_description = _public_configured_text(
                raw_server,
                "description",
                maximum=2_000,
            )
            if available and server_url:
                network_decision = network_policy.evaluate_url(
                    server_url,
                    purpose=f"MCP server '{server_name}'",
                )
                if not network_decision.allowed:
                    available = False
                    status = "disabled"
                    status_detail = network_decision.reason
                    metadata["network_policy"] = "blocked"
            items.append(
                _capability_payload(
                    capability_id=f"mcp:{server_name}",
                    kind="connector",
                    name=configured_name or _display_skill_name(server_name) or "MCP Server",
                    description=configured_description or (
                        f"Configured MCP server over {transport}."
                        if transport
                        else "MCP server configuration requires attention."
                    ),
                    source="local",
                    available=available,
                    default_enabled=f"mcp:{server_name}" in defaults.enabled_connectors,
                    project_enabled=_project_enabled(project_values, "connector", f"mcp:{server_name}"),
                    status=status,
                    status_detail=status_detail,
                    metadata=metadata,
                )
            )

    skill_ids = {
        str(item["id"])
        for item in items
        if item["kind"] == "skill" and item["available"] is True
    }
    connector_items = {
        str(item["id"]).casefold(): item for item in items if item["kind"] == "connector"
    }
    connector_ids = {
        str(item["id"])
        for item in connector_items.values()
        if item["available"] is True
    }
    for spec in list_specialist_specs(specialists):
        issues = list(
            specialist_configuration_issues(
                spec,
                skill_ids=skill_ids,
                connector_ids=connector_ids,
            )
        )
        unavailable_connectors = [
            connector_id
            for connector_id in spec.connectors
            if connector_id.casefold() in connector_items
            and connector_items[connector_id.casefold()]["available"] is not True
        ]
        if unavailable_connectors:
            issues.append(f"Unavailable Connectors: {', '.join(unavailable_connectors)}.")
        available = spec.enabled and not issues
        if not spec.enabled:
            status = "disabled"
            status_detail = "Disabled in science.specialists configuration."
        elif issues:
            status = "needs_configuration"
            status_detail = " ".join(issues)
        else:
            status = "ready"
            status_detail = ""
        metadata = {
            "registry_source": "custom" if spec.source == "local" else "built_in",
            "catalog_group": "custom" if spec.source == "local" else "built_in",
            "auto_dispatch": spec.auto_dispatch,
            "read_only": spec.read_only,
            "network_access": spec.network_access,
            "shell_access": spec.shell_access,
            "model": spec.model or "inherit",
            "assigned_skills": list(spec.skills),
            "assigned_connectors": list(spec.connectors),
            "execution_mode": "agent_tool",
        }
        if spec.source == "local":
            metadata["additional_instructions"] = spec.instructions
        items.append(
            _capability_payload(
                capability_id=spec.name,
                kind="specialist",
                name=spec.title,
                description=spec.description,
                source="local" if spec.source == "local" else "built_in",
                available=available,
                default_enabled=spec.name in defaults.enabled_specialists,
                project_enabled=_project_enabled(project_values, "specialist", spec.name),
                status=status,
                status_detail=status_detail,
                metadata=metadata,
            )
        )
    return items


def _public_configured_text(value: Any, key: str, *, maximum: int) -> str:
    """Return one bounded single-line display field from local configuration."""

    if not isinstance(value, dict):
        return ""
    text = str(value.get(key) or "").strip()
    if not text or len(text) > maximum or "\n" in text or "\r" in text:
        return ""
    if not all(character.isprintable() for character in text):
        return ""
    return text


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
    definition: ScienceCapabilityDefinition | None,
    default_enabled: bool,
    project_enabled: bool | None,
) -> dict[str, Any]:
    """Project one discovered Skill into the public capability contract."""

    frontmatter = _read_public_skill_frontmatter(skill.path)
    files, file_count = _public_skill_files(skill.path.parent)
    source = "local" if skill.source == "workspace" else "built_in"
    metadata: dict[str, Any] = {
        "registry_source": skill.source,
        "catalog_group": definition.group if definition is not None else "personal",
        "implementation_status": "installed",
        "file_count": file_count,
        "files_truncated": file_count > len(files),
    }
    canonical_name = skill.path.parent.name
    if skill.name != canonical_name:
        metadata["alias_of"] = canonical_name
    return _capability_payload(
        capability_id=skill.name,
        kind="skill",
        name=(
            definition.name
            if definition is not None
            else frontmatter.get("title") or _display_skill_name(skill.name)
        ),
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


def _unavailable_product_capability(
    *,
    definition: ScienceCapabilityDefinition,
    kind: CapabilityKind,
    default_enabled: bool,
    project_enabled: bool | None,
) -> dict[str, Any]:
    """Project a stable product candidate whose implementation is not installed."""

    return _capability_payload(
        capability_id=definition.id,
        kind=kind,
        name=definition.name,
        description=definition.description,
        source=definition.source,
        available=False,
        default_enabled=default_enabled,
        project_enabled=project_enabled,
        status="disabled",
        status_detail="Not available in this gm-science build.",
        metadata={
            "catalog_group": definition.group,
            "implementation_status": "not_installed",
            "registry_source": "product_catalog",
        },
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
        if not separator or normalized_key not in {"title", "version", "license"}:
            continue
        selected[normalized_key] = _frontmatter_scalar(value)
    return selected


def _frontmatter_scalar(value: str) -> str:
    """Decode the JSON-compatible scalars emitted by local Skill authoring."""

    stripped = value.strip()
    if stripped.startswith('"') and stripped.endswith('"'):
        try:
            decoded = json.loads(stripped)
        except (TypeError, ValueError):
            pass
        else:
            return str(decoded)
    return stripped.strip("\"'")


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

    selected = {str(value or "").strip().casefold() for value in values if str(value or "").strip()}
    known = [str(item["id"]) for item in catalog if item["kind"] == kind]
    known_normalized = {capability_id.casefold() for capability_id in known}
    unknown = sorted(selected.difference(known_normalized))
    if unknown:
        rendered = ", ".join(unknown)
        raise ValueError(f"Unsupported {kind} capability: {rendered}")
    allowed = [
        str(item["id"])
        for item in catalog
        if item["kind"] == kind and item["available"] is True
    ]
    allowed_normalized = {capability_id.casefold() for capability_id in allowed}
    unavailable = sorted(selected.difference(allowed_normalized))
    if unavailable:
        rendered = ", ".join(unavailable)
        raise ValueError(f"Unavailable {kind} capability: {rendered}")
    return [capability_id for capability_id in allowed if capability_id.casefold() in selected]


def selected_mcp_server_names(
    connector_ids: Iterable[str],
    catalog: list[dict[str, Any]],
) -> list[str]:
    """Return available configured MCP server names selected by one Project."""

    selected = {str(value) for value in connector_ids}
    names: list[str] = []
    for item in catalog:
        metadata = item.get("metadata")
        if (
            item.get("kind") != "connector"
            or item.get("id") not in selected
            or item.get("available") is not True
            or not isinstance(metadata, dict)
            or metadata.get("connector_type") != "mcp"
        ):
            continue
        server_name = str(metadata.get("server_name") or "")
        if server_name:
            names.append(server_name)
    return names


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
