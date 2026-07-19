"""Durable authoring operations for local gm-science capabilities."""

from __future__ import annotations

import json
import os
import re
import shlex
import tempfile
import threading
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlsplit

from ..core.config import load_config, save_config
from .capabilities import build_capability_catalog, normalize_capability_selection
from .infrastructure import require_registry_permissions

CapabilityAuthoringKind = Literal["skill", "connector", "specialist"]

_SKILL_ID_PATTERN = re.compile(r"^[a-z][a-z0-9-]{0,63}$")
_REGISTRY_ID_PATTERN = re.compile(r"^[a-z][a-z0-9_-]{0,63}$")
_SPECIALIST_ID_PATTERN = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
_MAX_NAME_CHARS = 120
_MAX_DESCRIPTION_CHARS = 2_000
_MAX_INSTRUCTIONS_CHARS = 100_000
_MAX_SKILL_CONTENT_CHARS = 200_000
_MAX_COMMAND_LINE_CHARS = 8_192
_MAX_COMMAND_ARGS = 100
_MAX_COMMAND_ARG_CHARS = 2_048
_MAX_URL_CHARS = 4_096


class CapabilityConflictError(ValueError):
    """Raised when a requested durable capability identifier already exists."""


class GmScienceCapabilityAuthoringService:
    """Create local capabilities in the registries consumed by gm-science."""

    def __init__(self, *, config_path: Path, lock: Any | None = None) -> None:
        self.config_path = config_path
        self._lock = lock or threading.RLock()

    def create_skill(self, body: Mapping[str, Any]) -> dict[str, Any]:
        """Publish one local ``SKILL.md`` and return its catalog projection."""

        _require_body(body)
        skill_id = _identifier(body.get("id") or body.get("skill_id"), "Skill ID", _SKILL_ID_PATTERN)
        name = _single_line_text(body.get("name"), "Name", _MAX_NAME_CHARS)
        description = _single_line_text(
            body.get("description"),
            "Description",
            _MAX_DESCRIPTION_CHARS,
        )
        content = _multiline_text(body.get("content"), "Content", _MAX_SKILL_CONTENT_CHARS)
        version = _optional_single_line_text(body.get("version"), "Version", 80)
        license_name = _optional_single_line_text(body.get("license"), "License", 120)

        with self._lock:
            config = load_config(config_path=self.config_path)
            require_registry_permissions(config, ["publish_skill"])
            catalog = build_capability_catalog(config_path=self.config_path)
            if any(str(item["id"]).casefold() == skill_id.casefold() for item in catalog):
                raise CapabilityConflictError(f"Skill ID '{skill_id}' already exists or is reserved.")

            skills_dir = self.config_path.parent / "skills"
            skills_dir.mkdir(parents=True, exist_ok=True)
            skill_dir = skills_dir / skill_id
            try:
                skill_dir.mkdir(mode=0o755, exist_ok=False)
            except FileExistsError as exc:
                raise CapabilityConflictError(f"Skill ID '{skill_id}' already exists.") from exc

            try:
                _write_skill_file(
                    skill_dir / "SKILL.md",
                    skill_id=skill_id,
                    name=name,
                    description=description,
                    content=content,
                    version=version,
                    license_name=license_name,
                )
            except Exception:
                try:
                    skill_dir.rmdir()
                except OSError:
                    pass
                raise
            return _catalog_item(self.config_path, "skill", skill_id)

    def create_connector(self, body: Mapping[str, Any]) -> dict[str, Any]:
        """Persist one explicit local or remote MCP server configuration."""

        _require_body(body)
        connector_id = _identifier(
            body.get("id") or body.get("connector_id"),
            "Connector ID",
            _REGISTRY_ID_PATTERN,
        )
        name = _single_line_text(body.get("name"), "Name", _MAX_NAME_CHARS)
        description = _single_line_text(
            body.get("description"),
            "Description",
            _MAX_DESCRIPTION_CHARS,
        )
        connection_type = str(body.get("connection_type") or body.get("connectionType") or "").strip().lower()
        if connection_type == "remote":
            server_config = _remote_connector_config(body, name=name, description=description)
        elif connection_type == "local":
            server_config = _local_connector_config(body, name=name, description=description)
        else:
            raise ValueError("Connection type must be 'remote' or 'local'.")

        with self._lock:
            config = load_config(config_path=self.config_path)
            tools = _mutable_mapping(config, "tools")
            servers = _mutable_mapping(tools, "mcpServers")
            if any(str(existing).casefold() == connector_id.casefold() for existing in servers):
                raise CapabilityConflictError(f"Connector ID '{connector_id}' already exists.")
            servers[connector_id] = server_config
            save_config(config, config_path=self.config_path)
            return _catalog_item(self.config_path, "connector", f"mcp:{connector_id}")

    def create_specialist(self, body: Mapping[str, Any]) -> dict[str, Any]:
        """Create one custom specialist with explicitly selected capabilities."""

        _require_body(body)
        specialist_id = _identifier(
            body.get("id") or body.get("agent_id"),
            "Agent ID",
            _SPECIALIST_ID_PATTERN,
        )
        name = _single_line_text(body.get("name"), "Name", _MAX_NAME_CHARS)
        description = _single_line_text(
            body.get("description"),
            "Description",
            _MAX_DESCRIPTION_CHARS,
        )
        instructions = _multiline_text(
            body.get("instructions"),
            "Instructions",
            _MAX_INSTRUCTIONS_CHARS,
        )
        raw_skills = _string_list(body.get("skills"), "Skills")
        raw_connectors = _string_list(body.get("connectors"), "Connectors")

        with self._lock:
            config = load_config(config_path=self.config_path)
            require_registry_permissions(config, ["create_agent"])
            catalog = build_capability_catalog(config_path=self.config_path)
            if any(
                item["kind"] == "specialist"
                and str(item["id"]).casefold() == specialist_id.casefold()
                for item in catalog
            ):
                raise CapabilityConflictError(
                    f"Agent ID '{specialist_id}' already exists or is reserved."
                )
            skills = normalize_capability_selection(kind="skill", values=raw_skills, catalog=catalog)
            connectors = normalize_capability_selection(
                kind="connector",
                values=raw_connectors,
                catalog=catalog,
            )

            science = _mutable_mapping(config, "science")
            specialists = _mutable_mapping(science, "specialists")
            custom = _mutable_mapping(specialists, "custom")
            if any(str(existing).casefold() == specialist_id.casefold() for existing in custom):
                raise CapabilityConflictError(f"Agent ID '{specialist_id}' already exists.")
            custom[specialist_id] = {
                "title": name,
                "description": description,
                "enabled": True,
                "autoDispatch": False,
                "model": "",
                "instructions": instructions,
                "skills": skills,
                "connectors": connectors,
            }
            save_config(config, config_path=self.config_path)
            return _catalog_item(self.config_path, "specialist", specialist_id)


def _require_body(body: Mapping[str, Any]) -> None:
    if not isinstance(body, Mapping):
        raise ValueError("Capability request must be a JSON object.")


def _identifier(value: Any, label: str, pattern: re.Pattern[str]) -> str:
    normalized = str(value or "").strip()
    if not pattern.fullmatch(normalized):
        raise ValueError(f"{label} has an invalid format.")
    return normalized


def _single_line_text(value: Any, label: str, maximum: int) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        raise ValueError(f"{label} is required.")
    if len(normalized) > maximum:
        raise ValueError(f"{label} must be at most {maximum} characters.")
    if "\n" in normalized or "\r" in normalized or not all(char.isprintable() for char in normalized):
        raise ValueError(f"{label} must contain printable text on one line.")
    return normalized


def _optional_single_line_text(value: Any, label: str, maximum: int) -> str:
    if value is None or not str(value).strip():
        return ""
    return _single_line_text(value, label, maximum)


def _multiline_text(value: Any, label: str, maximum: int) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        raise ValueError(f"{label} is required.")
    if len(normalized) > maximum:
        raise ValueError(f"{label} must be at most {maximum} characters.")
    if "\x00" in normalized:
        raise ValueError(f"{label} must not contain null characters.")
    return normalized


def _string_list(value: Any, label: str) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError(f"{label} must be a list.")
    normalized: list[str] = []
    for item in value:
        candidate = str(item or "").strip()
        if not candidate:
            raise ValueError(f"{label} must not contain empty values.")
        normalized.append(candidate)
    return normalized


def _remote_connector_config(
    body: Mapping[str, Any],
    *,
    name: str,
    description: str,
) -> dict[str, Any]:
    raw_url = str(body.get("url") or "").strip()
    if not raw_url:
        raise ValueError("Remote MCP server URL is required.")
    if len(raw_url) > _MAX_URL_CHARS or "\x00" in raw_url:
        raise ValueError("Remote MCP server URL is invalid.")
    try:
        parsed = urlsplit(raw_url)
    except ValueError as exc:
        raise ValueError("Remote MCP server URL is invalid.") from exc
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("Remote MCP server URL must use HTTP(S) and include a hostname.")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("Remote MCP server URL must not contain credentials, query parameters, or fragments.")
    return {
        "enabled": True,
        "name": name,
        "description": description,
        "url": raw_url,
        "transport": "http",
    }


def _local_connector_config(
    body: Mapping[str, Any],
    *,
    name: str,
    description: str,
) -> dict[str, Any]:
    command_line = str(body.get("command_line") or body.get("commandLine") or "").strip()
    if not command_line:
        raise ValueError("Command line is required.")
    if len(command_line) > _MAX_COMMAND_LINE_CHARS or "\x00" in command_line:
        raise ValueError("Command line is invalid.")
    try:
        argv = shlex.split(command_line, posix=True)
    except ValueError as exc:
        raise ValueError(f"Command line could not be parsed: {exc}") from exc
    if not argv:
        raise ValueError("Command line is required.")
    if len(argv) - 1 > _MAX_COMMAND_ARGS:
        raise ValueError(f"Command line may contain at most {_MAX_COMMAND_ARGS} arguments.")
    if any(len(value) > _MAX_COMMAND_ARG_CHARS for value in argv):
        raise ValueError(f"Command line entries must be at most {_MAX_COMMAND_ARG_CHARS} characters.")
    return {
        "enabled": True,
        "name": name,
        "description": description,
        "command": argv[0],
        "args": argv[1:],
    }


def _mutable_mapping(parent: dict[str, Any], key: str) -> dict[str, Any]:
    current = parent.get(key)
    if current is None:
        current = {}
        parent[key] = current
    if not isinstance(current, dict):
        raise ValueError(f"Configuration field '{key}' must be an object.")
    return current


def _write_skill_file(
    path: Path,
    *,
    skill_id: str,
    name: str,
    description: str,
    content: str,
    version: str,
    license_name: str,
) -> None:
    frontmatter = [
        "---",
        f"name: {json.dumps(skill_id, ensure_ascii=False)}",
        f"title: {json.dumps(name, ensure_ascii=False)}",
        f"description: {json.dumps(description, ensure_ascii=False)}",
    ]
    if version:
        frontmatter.append(f"version: {json.dumps(version, ensure_ascii=False)}")
    if license_name:
        frontmatter.append(f"license: {json.dumps(license_name, ensure_ascii=False)}")
    rendered = "\n".join([*frontmatter, "---", "", content, ""])
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=".SKILL.md.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary_path = Path(handle.name)
            handle.write(rendered)
            handle.flush()
            os.fsync(handle.fileno())
        temporary_path.chmod(0o644)
        os.replace(temporary_path, path)
        temporary_path = None
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def _catalog_item(config_path: Path, kind: CapabilityAuthoringKind, capability_id: str) -> dict[str, Any]:
    for item in build_capability_catalog(config_path=config_path):
        if item["kind"] == kind and str(item["id"]).casefold() == capability_id.casefold():
            return item
    raise RuntimeError(f"Created {kind} capability '{capability_id}' was not discoverable.")
