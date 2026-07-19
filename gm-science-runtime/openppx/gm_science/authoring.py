"""Durable authoring operations for local gm-science capabilities."""

from __future__ import annotations

import json
import io
import os
import re
import shlex
import shutil
import tempfile
import threading
import urllib.request
import uuid
import zipfile
from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Callable, Literal
from urllib.parse import quote, urlsplit

from ..core.config import load_config, save_config
from .capabilities import build_capability_catalog, normalize_capability_selection
from .infrastructure import parse_network_policy, require_registry_permissions
from .store import GmScienceStore

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
_MAX_CONNECTOR_SECRETS = 50
_MAX_SECRET_NAME_CHARS = 128
_ENV_NAME_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_HEADER_NAME_PATTERN = re.compile(r"^[!#$%&'*+\-.^_`|~0-9A-Za-z]+$")
_MAX_IMPORT_FILES = 500
_MAX_IMPORT_BYTES = 50 * 1024 * 1024
_MAX_GITHUB_DOWNLOAD_BYTES = 25 * 1024 * 1024
_MAX_SKILL_DRAFTS = 100
_MANAGED_MARKER = "gm-science"


class CapabilityConflictError(ValueError):
    """Raised when a requested durable capability identifier already exists."""


class CapabilityNotFoundError(ValueError):
    """Raised when a requested user-owned capability does not exist."""


class CapabilityInUseError(ValueError):
    """Raised when deleting a capability would break durable references."""


class GmScienceCapabilityAuthoringService:
    """Create local capabilities in the registries consumed by gm-science."""

    def __init__(
        self,
        *,
        config_path: Path,
        store: GmScienceStore | None = None,
        lock: Any | None = None,
        github_downloader: Callable[[str], bytes] | None = None,
    ) -> None:
        self.config_path = config_path
        self.store = store
        self._lock = lock or threading.RLock()
        self._github_downloader = github_downloader or _download_github_archive

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

    def import_skill(self, body: Mapping[str, Any]) -> dict[str, Any]:
        """Import one local directory, ``SKILL.md``, or zip bundle."""

        _require_body(body)
        raw_source_path = str(body.get("source_path") or body.get("sourcePath") or "").strip()
        if not raw_source_path:
            raise ValueError("Skill source path is required.")
        source_path = Path(raw_source_path).expanduser()
        if not source_path.exists():
            raise ValueError("Skill source path does not exist.")
        with self._lock:
            config = load_config(config_path=self.config_path)
            require_registry_permissions(config, ["publish_skill"])
            with tempfile.TemporaryDirectory(prefix="gm-science-skill-import-") as temporary:
                temporary_root = Path(temporary)
                bundle_root = _prepare_local_skill_bundle(source_path, temporary_root)
                return self._install_skill_bundle(
                    bundle_root,
                    requested_id=body.get("id") or body.get("skill_id"),
                    origin={"type": "local_upload"},
                )

    def import_skill_from_github(self, body: Mapping[str, Any]) -> dict[str, Any]:
        """Import one Skill bundle from a public GitHub repository URL."""

        _require_body(body)
        source = _parse_github_skill_url(body.get("url"))
        with self._lock:
            config = load_config(config_path=self.config_path)
            require_registry_permissions(config, ["publish_skill"])
            decision = parse_network_policy(config).evaluate_url(
                source["archive_url"],
                purpose="GitHub Skill import",
            )
            if not decision.allowed:
                raise ValueError(decision.reason)
            archive = self._github_downloader(source["archive_url"])
            if len(archive) > _MAX_GITHUB_DOWNLOAD_BYTES:
                raise ValueError("GitHub Skill archive exceeds the supported download size.")
            with tempfile.TemporaryDirectory(prefix="gm-science-github-skill-") as temporary:
                temporary_root = Path(temporary)
                _extract_skill_zip(archive, temporary_root)
                bundle_root = _find_archive_skill_root(temporary_root, source["subdirectory"])
                return self._install_skill_bundle(
                    bundle_root,
                    requested_id=body.get("id") or body.get("skill_id"),
                    origin={
                        "type": "github",
                        "url": source["public_url"],
                        "ref": source["ref"],
                        "subdirectory": source["subdirectory"],
                    },
                )

    def list_skill_drafts(self) -> list[dict[str, Any]]:
        """Return durable local Skill drafts ordered by most recent update."""

        with self._lock:
            drafts: list[dict[str, Any]] = []
            draft_dir = self._skill_draft_dir
            if not draft_dir.is_dir():
                return drafts
            for path in sorted(draft_dir.glob("*.json"))[:_MAX_SKILL_DRAFTS]:
                try:
                    raw = json.loads(path.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError):
                    continue
                if isinstance(raw, dict) and str(raw.get("id") or "") == path.stem:
                    drafts.append(raw)
            return sorted(
                drafts,
                key=lambda item: str(item.get("updated_at") or ""),
                reverse=True,
            )

    def save_skill_draft(self, body: Mapping[str, Any]) -> dict[str, Any]:
        """Create or replace one incomplete local Skill draft."""

        _require_body(body)
        draft_id = _identifier(body.get("id") or body.get("skill_id"), "Skill ID", _SKILL_ID_PATTERN)
        name = _single_line_text(body.get("name"), "Name", _MAX_NAME_CHARS)
        description = _optional_multiline_text(body.get("description"), "Description", _MAX_DESCRIPTION_CHARS)
        content = _optional_multiline_text(body.get("content"), "Content", _MAX_SKILL_CONTENT_CHARS)
        version = _optional_single_line_text(body.get("version"), "Version", 80)
        license_name = _optional_single_line_text(body.get("license"), "License", 120)
        payload = {
            "id": draft_id,
            "name": name,
            "description": description,
            "content": content,
            "version": version,
            "license": license_name,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        with self._lock:
            draft_dir = self._skill_draft_dir
            draft_dir.mkdir(parents=True, exist_ok=True)
            if not (draft_dir / f"{draft_id}.json").exists():
                existing_count = sum(1 for _ in draft_dir.glob("*.json"))
                if existing_count >= _MAX_SKILL_DRAFTS:
                    raise ValueError(f"At most {_MAX_SKILL_DRAFTS} Skill drafts are supported.")
            _write_private_json(draft_dir / f"{draft_id}.json", payload)
        return payload

    def delete_skill_draft(self, draft_id: str) -> None:
        """Delete one durable local Skill draft."""

        normalized_id = _identifier(draft_id, "Skill ID", _SKILL_ID_PATTERN)
        with self._lock:
            path = self._skill_draft_dir / f"{normalized_id}.json"
            if not path.is_file():
                raise CapabilityNotFoundError(f"Skill draft '{normalized_id}' was not found.")
            path.unlink()

    def publish_skill_draft(self, draft_id: str) -> dict[str, Any]:
        """Publish one complete draft through the canonical Skill registry."""

        normalized_id = _identifier(draft_id, "Skill ID", _SKILL_ID_PATTERN)
        with self._lock:
            draft = next(
                (item for item in self.list_skill_drafts() if item.get("id") == normalized_id),
                None,
            )
            if draft is None:
                raise CapabilityNotFoundError(f"Skill draft '{normalized_id}' was not found.")
            capability = self.create_skill(draft)
            self.delete_skill_draft(normalized_id)
            return capability

    @property
    def _skill_draft_dir(self) -> Path:
        """Return the private authoring directory outside the live Skill registry."""

        return self.config_path.parent / "drafts" / "skills"

    def get_definition(self, kind: CapabilityAuthoringKind, capability_id: str) -> dict[str, Any]:
        """Return one editable local definition without secret values."""

        normalized_kind = _authoring_kind(kind)
        with self._lock:
            if normalized_kind == "skill":
                return self._skill_definition(capability_id)
            config = load_config(config_path=self.config_path)
            if normalized_kind == "connector":
                return _connector_definition(config, capability_id)
            return _specialist_definition(config, capability_id)

    def update_skill(self, skill_id: str, body: Mapping[str, Any]) -> dict[str, Any]:
        """Replace editable fields of one Agent-local Skill."""

        normalized_id = _identifier(skill_id, "Skill ID", _SKILL_ID_PATTERN)
        _require_body(body)
        name = _single_line_text(body.get("name"), "Name", _MAX_NAME_CHARS)
        description = _single_line_text(body.get("description"), "Description", _MAX_DESCRIPTION_CHARS)
        content = _multiline_text(body.get("content"), "Content", _MAX_SKILL_CONTENT_CHARS)
        version = _optional_single_line_text(body.get("version"), "Version", 80)
        license_name = _optional_single_line_text(body.get("license"), "License", 120)
        with self._lock:
            config = load_config(config_path=self.config_path)
            require_registry_permissions(config, ["edit_skill"])
            skill_file = self._local_skill_file(normalized_id)
            _write_skill_file(
                skill_file,
                skill_id=normalized_id,
                name=name,
                description=description,
                content=content,
                version=version,
                license_name=license_name,
            )
            return _catalog_item(self.config_path, "skill", normalized_id)

    def update_connector(self, connector_id: str, body: Mapping[str, Any]) -> dict[str, Any]:
        """Replace one managed MCP Connector while keeping its stable ID."""

        normalized_id = _connector_registry_id(connector_id)
        _require_body(body)
        name = _single_line_text(body.get("name"), "Name", _MAX_NAME_CHARS)
        description = _single_line_text(body.get("description"), "Description", _MAX_DESCRIPTION_CHARS)
        with self._lock:
            config = load_config(config_path=self.config_path)
            credentials = _custom_credentials(config)
            connection_type = str(
                body.get("connection_type") or body.get("connectionType") or ""
            ).strip().lower()
            servers = _mcp_servers(config)
            existing_key = _mapping_key(servers, normalized_id)
            if existing_key is None or not _is_managed_connector(servers[existing_key]):
                raise CapabilityNotFoundError(f"Managed Connector '{normalized_id}' was not found.")
            if connection_type == "remote":
                server_config = _remote_connector_config(
                    body,
                    name=name,
                    description=description,
                    credentials=credentials,
                )
            elif connection_type == "local":
                server_config = _local_connector_config(
                    body,
                    name=name,
                    description=description,
                    credentials=credentials,
                )
            else:
                raise ValueError("Connection type must be 'remote' or 'local'.")
            server_config["managedBy"] = _MANAGED_MARKER
            servers[existing_key] = server_config
            save_config(config, config_path=self.config_path)
            return _catalog_item(self.config_path, "connector", f"mcp:{existing_key}")

    def update_specialist(self, specialist_id: str, body: Mapping[str, Any]) -> dict[str, Any]:
        """Replace editable fields and capability assignments of one custom Specialist."""

        normalized_id = _identifier(specialist_id, "Agent ID", _SPECIALIST_ID_PATTERN)
        _require_body(body)
        name = _single_line_text(body.get("name"), "Name", _MAX_NAME_CHARS)
        description = _single_line_text(body.get("description"), "Description", _MAX_DESCRIPTION_CHARS)
        instructions = _multiline_text(body.get("instructions"), "Instructions", _MAX_INSTRUCTIONS_CHARS)
        raw_skills = _string_list(body.get("skills"), "Skills")
        raw_connectors = _string_list(body.get("connectors"), "Connectors")
        with self._lock:
            config = load_config(config_path=self.config_path)
            require_registry_permissions(config, ["update_agent"])
            custom = _custom_specialists(config)
            existing_key = _mapping_key(custom, normalized_id)
            if existing_key is None:
                raise CapabilityNotFoundError(f"Custom Specialist '{normalized_id}' was not found.")
            catalog = build_capability_catalog(config_path=self.config_path)
            skills = normalize_capability_selection(kind="skill", values=raw_skills, catalog=catalog)
            connectors = normalize_capability_selection(kind="connector", values=raw_connectors, catalog=catalog)
            connector_tools = _specialist_connector_tools(body, connectors)
            custom[existing_key] = {
                "title": name,
                "description": description,
                "enabled": True,
                "autoDispatch": False,
                "model": "",
                "instructions": instructions,
                "skills": skills,
                "connectors": connectors,
                "connectorTools": connector_tools,
            }
            save_config(config, config_path=self.config_path)
            return _catalog_item(self.config_path, "specialist", existing_key)

    def delete_capability(self, kind: CapabilityAuthoringKind, capability_id: str) -> None:
        """Delete one unreferenced user-owned capability."""

        normalized_kind = _authoring_kind(kind)
        with self._lock:
            config = load_config(config_path=self.config_path)
            if normalized_kind == "skill":
                normalized_id = _identifier(capability_id, "Skill ID", _SKILL_ID_PATTERN)
                require_registry_permissions(config, ["edit_skill"])
                target = self._local_skill_file(normalized_id).parent
            elif normalized_kind == "connector":
                normalized_id = _connector_registry_id(capability_id)
                servers = _mcp_servers(config)
                existing_key = _mapping_key(servers, normalized_id)
                if existing_key is None or not _is_managed_connector(servers[existing_key]):
                    raise CapabilityNotFoundError(f"Managed Connector '{normalized_id}' was not found.")
                target = None
                normalized_id = f"mcp:{existing_key}"
            else:
                normalized_id = _identifier(capability_id, "Agent ID", _SPECIALIST_ID_PATTERN)
                require_registry_permissions(config, ["update_agent"])
                custom = _custom_specialists(config)
                existing_key = _mapping_key(custom, normalized_id)
                if existing_key is None:
                    raise CapabilityNotFoundError(f"Custom Specialist '{normalized_id}' was not found.")
                target = None
                normalized_id = existing_key

            usages = self._capability_usages(normalized_kind, normalized_id, config)
            if usages:
                raise CapabilityInUseError(
                    f"{normalized_kind.title()} '{normalized_id}' is still in use by {', '.join(usages)}."
                )
            if normalized_kind == "skill":
                _remove_directory_atomically(target)
            elif normalized_kind == "connector":
                del _mcp_servers(config)[normalized_id.removeprefix("mcp:")]
                save_config(config, config_path=self.config_path)
            else:
                del _custom_specialists(config)[normalized_id]
                save_config(config, config_path=self.config_path)

    def _install_skill_bundle(
        self,
        bundle_root: Path,
        *,
        requested_id: Any,
        origin: Mapping[str, Any],
    ) -> dict[str, Any]:
        skill_file = bundle_root / "SKILL.md"
        metadata, _content = _read_skill_document(skill_file)
        skill_id = _identifier(requested_id or metadata.get("name") or bundle_root.name, "Skill ID", _SKILL_ID_PATTERN)
        description = str(metadata.get("description") or "").strip()
        if not description:
            raise ValueError("Imported SKILL.md requires a description in frontmatter.")
        catalog = build_capability_catalog(config_path=self.config_path)
        if any(str(item["id"]).casefold() == skill_id.casefold() for item in catalog):
            raise CapabilityConflictError(f"Skill ID '{skill_id}' already exists or is reserved.")
        skills_dir = self.config_path.parent / "skills"
        skills_dir.mkdir(parents=True, exist_ok=True)
        target = skills_dir / skill_id
        if target.exists():
            raise CapabilityConflictError(f"Skill ID '{skill_id}' already exists.")
        _validate_skill_bundle(bundle_root)
        staging = Path(tempfile.mkdtemp(prefix=f".{skill_id}.", dir=skills_dir))
        try:
            _copy_skill_bundle(bundle_root, staging)
            (staging / ".gm-science-origin.json").write_text(
                json.dumps(dict(origin), ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            os.replace(staging, target)
        except Exception:
            shutil.rmtree(staging, ignore_errors=True)
            raise
        return _catalog_item(self.config_path, "skill", skill_id)

    def _local_skill_file(self, skill_id: str) -> Path:
        skill_file = self.config_path.parent / "skills" / skill_id / "SKILL.md"
        if not skill_file.is_file():
            raise CapabilityNotFoundError(f"Local Skill '{skill_id}' was not found.")
        return skill_file

    def _skill_definition(self, skill_id: str) -> dict[str, Any]:
        normalized_id = _identifier(skill_id, "Skill ID", _SKILL_ID_PATTERN)
        metadata, content = _read_skill_document(self._local_skill_file(normalized_id))
        return {
            "id": normalized_id,
            "kind": "skill",
            "name": metadata.get("title") or normalized_id,
            "description": metadata.get("description") or "",
            "content": content,
            "version": metadata.get("version") or "",
            "license": metadata.get("license") or "",
        }

    def _capability_usages(
        self,
        kind: CapabilityAuthoringKind,
        capability_id: str,
        config: Mapping[str, Any],
    ) -> list[str]:
        usages: list[str] = []
        if self.store is not None:
            for project in self.store.list_projects():
                selected = {
                    "skill": project.enabled_skills,
                    "connector": project.enabled_connectors,
                    "specialist": project.enabled_specialists,
                }[kind]
                if capability_id.casefold() in {item.casefold() for item in selected}:
                    usages.append(f"Project '{project.name}'")
                if kind == "specialist":
                    for association in self.store.list_project_sessions(project.id):
                        if str(association.policy.get("specialist") or "").casefold() == capability_id.casefold():
                            usages.append(f"Session '{association.session_id}'")
        if kind in {"skill", "connector"}:
            key = "skills" if kind == "skill" else "connectors"
            for raw_name, raw_specialist in _custom_specialists(dict(config)).items():
                assigned = raw_specialist.get(key) if isinstance(raw_specialist, Mapping) else []
                if isinstance(assigned, list) and capability_id.casefold() in {
                    str(item).casefold() for item in assigned
                }:
                    usages.append(f"Specialist '{raw_name}'")
        return list(dict.fromkeys(usages))

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
        with self._lock:
            config = load_config(config_path=self.config_path)
            connection_type = str(
                body.get("connection_type") or body.get("connectionType") or ""
            ).strip().lower()
            credentials = _custom_credentials(config)
            if connection_type == "remote":
                server_config = _remote_connector_config(
                    body,
                    name=name,
                    description=description,
                    credentials=credentials,
                )
            elif connection_type == "local":
                server_config = _local_connector_config(
                    body,
                    name=name,
                    description=description,
                    credentials=credentials,
                )
            else:
                raise ValueError("Connection type must be 'remote' or 'local'.")
            tools = _mutable_mapping(config, "tools")
            servers = _mutable_mapping(tools, "mcpServers")
            if any(str(existing).casefold() == connector_id.casefold() for existing in servers):
                raise CapabilityConflictError(f"Connector ID '{connector_id}' already exists.")
            server_config["managedBy"] = _MANAGED_MARKER
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
            connector_tools = _specialist_connector_tools(body, connectors)

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
                "connectorTools": connector_tools,
            }
            save_config(config, config_path=self.config_path)
            return _catalog_item(self.config_path, "specialist", specialist_id)


def _require_body(body: Mapping[str, Any]) -> None:
    if not isinstance(body, Mapping):
        raise ValueError("Capability request must be a JSON object.")


def _specialist_connector_tools(
    body: Mapping[str, Any],
    selected_connectors: list[str],
) -> dict[str, list[str]]:
    """Validate bounded MCP tool allowlists assigned to one Specialist."""

    raw = body.get("connector_tools", body.get("connectorTools", {}))
    if raw in (None, {}):
        return {}
    if not isinstance(raw, Mapping):
        raise ValueError("Connector tools must be an object.")
    selected = {connector.casefold(): connector for connector in selected_connectors}
    normalized: dict[str, list[str]] = {}
    for raw_connector_id, raw_tools in raw.items():
        connector_id = str(raw_connector_id or "").strip()
        canonical = selected.get(connector_id.casefold())
        if canonical is None:
            raise ValueError(f"Connector tool filter references unassigned Connector '{connector_id}'.")
        if not canonical.casefold().startswith("mcp:"):
            raise ValueError("Tool-level filters are supported only for MCP Connectors.")
        tools = _string_list(raw_tools, f"Tools for {canonical}")
        if len(tools) > 256 or any(len(tool) > 256 or "\n" in tool or "\r" in tool for tool in tools):
            raise ValueError(f"Tools for {canonical} exceed the supported limits.")
        deduplicated = list(dict.fromkeys(tools))
        if deduplicated:
            normalized[canonical] = deduplicated
    return normalized


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


def _optional_multiline_text(value: Any, label: str, maximum: int) -> str:
    normalized = str(value or "").strip()
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


def _connector_options(body: Mapping[str, Any]) -> dict[str, Any]:
    tool_filter = _string_list(body.get("tool_filter", body.get("toolFilter")), "Tool filter")
    if len(tool_filter) > 256:
        raise ValueError("Tool filter may contain at most 256 entries.")
    if any(len(value) > 256 or "\n" in value or "\r" in value for value in tool_filter):
        raise ValueError("Tool filter entries must be single-line values of at most 256 characters.")
    options: dict[str, Any] = {}
    if tool_filter:
        options["toolFilter"] = list(dict.fromkeys(tool_filter))
    if bool(body.get("require_confirmation", body.get("requireConfirmation", False))):
        options["requireConfirmation"] = True
    return options


def _connector_credential_bindings(
    value: Any,
    *,
    label: str,
    name_pattern: re.Pattern[str],
    credentials: Mapping[str, Any],
) -> dict[str, str]:
    """Validate Connector target names mapped to write-only credential IDs."""

    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be an object.")
    if len(value) > _MAX_CONNECTOR_SECRETS:
        raise ValueError(f"{label} may contain at most {_MAX_CONNECTOR_SECRETS} entries.")
    normalized: dict[str, str] = {}
    for raw_name, raw_credential_id in value.items():
        name = str(raw_name or "").strip()
        credential_id = str(raw_credential_id or "").strip()
        if (
            not name
            or len(name) > _MAX_SECRET_NAME_CHARS
            or name_pattern.fullmatch(name) is None
        ):
            raise ValueError(f"{label} contains an invalid name.")
        credential = credentials.get(credential_id)
        if not credential_id or not isinstance(credential, Mapping):
            raise ValueError(f"{label} references unknown credential '{credential_id}'.")
        if not str(credential.get("value") or ""):
            raise ValueError(f"{label} references unconfigured credential '{credential_id}'.")
        normalized[name] = credential_id
    return normalized


def _remote_connector_config(
    body: Mapping[str, Any],
    *,
    name: str,
    description: str,
    credentials: Mapping[str, Any],
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
    header_bindings = _connector_credential_bindings(
        body.get("header_credential_refs", body.get("headerCredentialRefs")),
        label="Header credential bindings",
        name_pattern=_HEADER_NAME_PATTERN,
        credentials=credentials,
    )
    config = {
        "enabled": True,
        "name": name,
        "description": description,
        "url": raw_url,
        "transport": "http",
        **_connector_options(body),
    }
    if header_bindings:
        config["credentialBindings"] = {"headers": header_bindings}
    return config


def _local_connector_config(
    body: Mapping[str, Any],
    *,
    name: str,
    description: str,
    credentials: Mapping[str, Any],
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
    environment_bindings = _connector_credential_bindings(
        body.get("environment_credential_refs", body.get("environmentCredentialRefs")),
        label="Environment credential bindings",
        name_pattern=_ENV_NAME_PATTERN,
        credentials=credentials,
    )
    config = {
        "enabled": True,
        "name": name,
        "description": description,
        "command": argv[0],
        "args": argv[1:],
        **_connector_options(body),
    }
    if environment_bindings:
        config["credentialBindings"] = {"env": environment_bindings}
    return config


def _mutable_mapping(parent: dict[str, Any], key: str) -> dict[str, Any]:
    current = parent.get(key)
    if current is None:
        current = {}
        parent[key] = current
    if not isinstance(current, dict):
        raise ValueError(f"Configuration field '{key}' must be an object.")
    return current


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


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


def _write_private_json(path: Path, payload: Mapping[str, Any]) -> None:
    """Atomically persist one authoring record with owner-only permissions."""

    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary_path = Path(handle.name)
            handle.write(json.dumps(dict(payload), ensure_ascii=False, indent=2) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        temporary_path.chmod(0o600)
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


def _authoring_kind(value: Any) -> CapabilityAuthoringKind:
    normalized = str(value or "").strip().lower().removesuffix("s")
    if normalized not in {"skill", "connector", "specialist"}:
        raise ValueError(f"Unsupported capability kind '{value}'.")
    return normalized  # type: ignore[return-value]


def _connector_registry_id(value: Any) -> str:
    normalized = str(value or "").strip()
    if normalized.casefold().startswith("mcp:"):
        normalized = normalized[4:]
    return _identifier(normalized, "Connector ID", _REGISTRY_ID_PATTERN)


def _mapping_key(values: Mapping[str, Any], requested: str) -> str | None:
    target = requested.casefold()
    return next((str(key) for key in values if str(key).casefold() == target), None)


def _mcp_servers(config: dict[str, Any]) -> dict[str, Any]:
    return _mutable_mapping(_mutable_mapping(config, "tools"), "mcpServers")


def _custom_specialists(config: dict[str, Any]) -> dict[str, Any]:
    science = _mutable_mapping(config, "science")
    specialists = _mutable_mapping(science, "specialists")
    return _mutable_mapping(specialists, "custom")


def _custom_credentials(config: dict[str, Any]) -> dict[str, Any]:
    science = _mutable_mapping(config, "science")
    credentials = _mutable_mapping(science, "credentials")
    return _mutable_mapping(credentials, "custom")


def _is_managed_connector(value: Any) -> bool:
    return isinstance(value, Mapping) and str(value.get("managedBy") or "") == _MANAGED_MARKER


def _connector_definition(config: dict[str, Any], capability_id: str) -> dict[str, Any]:
    connector_id = _connector_registry_id(capability_id)
    servers = _mcp_servers(config)
    existing_key = _mapping_key(servers, connector_id)
    if existing_key is None or not _is_managed_connector(servers[existing_key]):
        raise CapabilityNotFoundError(f"Managed Connector '{connector_id}' was not found.")
    raw = servers[existing_key]
    command = str(raw.get("command") or "").strip()
    args = raw.get("args") if isinstance(raw.get("args"), list) else []
    if command:
        connection_type = "local"
        command_line = shlex.join([command, *(str(value) for value in args)])
        url = ""
    else:
        connection_type = "remote"
        command_line = ""
        url = str(raw.get("url") or "").strip()
    return {
        "id": f"mcp:{existing_key}",
        "kind": "connector",
        "name": str(raw.get("name") or existing_key),
        "description": str(raw.get("description") or ""),
        "connection_type": connection_type,
        "url": url,
        "command_line": command_line,
        "tool_filter": _string_list(raw.get("toolFilter", raw.get("tool_filter")), "Tool filter"),
        "require_confirmation": bool(
            raw.get("requireConfirmation", raw.get("require_confirmation", False))
        ),
        "header_credential_refs": dict(
            _mapping(_mapping(raw.get("credentialBindings")).get("headers"))
        ),
        "environment_credential_refs": dict(
            _mapping(_mapping(raw.get("credentialBindings")).get("env"))
        ),
    }


def _specialist_definition(config: dict[str, Any], capability_id: str) -> dict[str, Any]:
    specialist_id = _identifier(capability_id, "Agent ID", _SPECIALIST_ID_PATTERN)
    custom = _custom_specialists(config)
    existing_key = _mapping_key(custom, specialist_id)
    if existing_key is None:
        raise CapabilityNotFoundError(f"Custom Specialist '{specialist_id}' was not found.")
    raw = custom[existing_key]
    if not isinstance(raw, Mapping):
        raise ValueError(f"Custom Specialist '{specialist_id}' has an invalid configuration.")
    return {
        "id": existing_key,
        "kind": "specialist",
        "name": str(raw.get("title") or raw.get("name") or existing_key),
        "description": str(raw.get("description") or ""),
        "instructions": str(raw.get("instructions") or ""),
        "skills": _string_list(raw.get("skills"), "Skills"),
        "connectors": _string_list(raw.get("connectors"), "Connectors"),
        "connector_tools": {
            str(connector_id): _string_list(tools, f"Tools for {connector_id}")
            for connector_id, tools in raw.get("connectorTools", {}).items()
        } if isinstance(raw.get("connectorTools"), Mapping) else {},
    }


def _read_skill_document(path: Path) -> tuple[dict[str, str], str]:
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise ValueError("SKILL.md must be readable UTF-8 text.") from exc
    if len(text) > _MAX_SKILL_CONTENT_CHARS + 20_000:
        raise ValueError("SKILL.md exceeds the supported size.")
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        raise ValueError("SKILL.md requires YAML frontmatter.")
    closing_index = next((index for index, line in enumerate(lines[1:], start=1) if line.strip() == "---"), None)
    if closing_index is None:
        raise ValueError("SKILL.md frontmatter is not closed.")
    metadata: dict[str, str] = {}
    for line in lines[1:closing_index]:
        key, separator, value = line.partition(":")
        normalized_key = key.strip().lower()
        if separator and normalized_key in {"name", "title", "description", "version", "license"}:
            metadata[normalized_key] = _frontmatter_value(value)
    content = "\n".join(lines[closing_index + 1 :]).strip()
    if len(content) > _MAX_SKILL_CONTENT_CHARS:
        raise ValueError(f"Content must be at most {_MAX_SKILL_CONTENT_CHARS} characters.")
    return metadata, content


def _frontmatter_value(value: str) -> str:
    stripped = value.strip()
    if stripped.startswith('"') and stripped.endswith('"'):
        try:
            decoded = json.loads(stripped)
        except (TypeError, ValueError):
            pass
        else:
            return str(decoded)
    return stripped.strip("\"'")


def _prepare_local_skill_bundle(source_path: Path, temporary_root: Path) -> Path:
    resolved = source_path.resolve()
    if resolved.is_dir():
        if not (resolved / "SKILL.md").is_file():
            raise ValueError("Selected Skill directory must contain SKILL.md at its root.")
        return resolved
    if not resolved.is_file():
        raise ValueError("Skill source must be a directory, SKILL.md, or zip archive.")
    if resolved.name == "SKILL.md":
        bundle = temporary_root / "bundle"
        bundle.mkdir()
        shutil.copy2(resolved, bundle / "SKILL.md")
        return bundle
    if resolved.suffix.lower() == ".zip":
        _extract_skill_zip(resolved.read_bytes(), temporary_root)
        return _find_archive_skill_root(temporary_root, "")
    raise ValueError("Skill upload supports a directory, SKILL.md, or .zip archive.")


def _extract_skill_zip(archive_bytes: bytes, destination: Path) -> None:
    if len(archive_bytes) > _MAX_GITHUB_DOWNLOAD_BYTES:
        raise ValueError("Skill archive exceeds the supported compressed size.")
    try:
        archive = zipfile.ZipFile(io.BytesIO(archive_bytes))
    except zipfile.BadZipFile as exc:
        raise ValueError("Skill archive is not a valid zip file.") from exc
    with archive:
        infos = [info for info in archive.infolist() if not info.is_dir()]
        if len(infos) > _MAX_IMPORT_FILES:
            raise ValueError("Skill archive contains too many files.")
        if sum(info.file_size for info in infos) > _MAX_IMPORT_BYTES:
            raise ValueError("Skill archive exceeds the supported extracted size.")
        for info in archive.infolist():
            relative = PurePosixPath(info.filename)
            if relative.is_absolute() or ".." in relative.parts or not relative.parts:
                raise ValueError("Skill archive contains an unsafe path.")
            unix_mode = (info.external_attr >> 16) & 0o170000
            if unix_mode == 0o120000:
                raise ValueError("Skill archive must not contain symbolic links.")
            target = destination.joinpath(*relative.parts)
            if info.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(info) as source, target.open("wb") as output:
                shutil.copyfileobj(source, output)


def _find_archive_skill_root(extracted: Path, subdirectory: str) -> Path:
    top_level = [path for path in extracted.iterdir() if path.is_dir()]
    repository_root = top_level[0] if len(top_level) == 1 else extracted
    if subdirectory:
        requested = repository_root.joinpath(*PurePosixPath(subdirectory).parts)
        if not (requested / "SKILL.md").is_file():
            raise ValueError("GitHub Skill path does not contain SKILL.md.")
        return requested
    candidates = [path.parent for path in repository_root.rglob("SKILL.md") if path.is_file()]
    if not candidates:
        raise ValueError("Skill archive does not contain SKILL.md.")
    if len(candidates) > 1:
        raise ValueError("Skill archive contains multiple Skills; use a GitHub tree URL for one Skill directory.")
    return candidates[0]


def _validate_skill_bundle(root: Path) -> None:
    files = 0
    total_bytes = 0
    for path in root.rglob("*"):
        if path.is_symlink():
            raise ValueError("Skill bundle must not contain symbolic links.")
        if path.is_dir():
            continue
        if not path.is_file():
            raise ValueError("Skill bundle contains an unsupported filesystem entry.")
        files += 1
        total_bytes += path.stat().st_size
        if files > _MAX_IMPORT_FILES:
            raise ValueError("Skill bundle contains too many files.")
        if total_bytes > _MAX_IMPORT_BYTES:
            raise ValueError("Skill bundle exceeds the supported extracted size.")


def _copy_skill_bundle(source: Path, destination: Path) -> None:
    for path in source.rglob("*"):
        relative = path.relative_to(source)
        target = destination / relative
        if path.is_dir():
            target.mkdir(parents=True, exist_ok=True)
        elif path.is_file():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)


def _remove_directory_atomically(target: Path | None) -> None:
    if target is None or not target.is_dir():
        raise CapabilityNotFoundError("Local Skill was not found.")
    tombstone = target.with_name(f".{target.name}.deleting.{uuid.uuid4().hex}")
    os.replace(target, tombstone)
    shutil.rmtree(tombstone)


def _parse_github_skill_url(value: Any) -> dict[str, str]:
    raw_url = str(value or "").strip()
    if not raw_url or len(raw_url) > _MAX_URL_CHARS:
        raise ValueError("GitHub repository URL is required.")
    try:
        parsed = urlsplit(raw_url)
    except ValueError as exc:
        raise ValueError("GitHub repository URL is invalid.") from exc
    if (
        parsed.scheme != "https"
        or (parsed.hostname or "").casefold() != "github.com"
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("GitHub Skill URL must be a credential-free https://github.com URL.")
    parts = [part for part in parsed.path.split("/") if part]
    if len(parts) < 2:
        raise ValueError("GitHub Skill URL must identify an owner and repository.")
    owner, repository = parts[0], parts[1].removesuffix(".git")
    if not re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})", owner) or not re.fullmatch(r"[A-Za-z0-9_.-]{1,100}", repository):
        raise ValueError("GitHub owner or repository name is invalid.")
    ref = "HEAD"
    subdirectory = ""
    if len(parts) > 2:
        if len(parts) < 4 or parts[2] != "tree":
            raise ValueError("GitHub Skill URL must reference the repository or a /tree/<ref>/<path> directory.")
        ref = parts[3]
        subdirectory = "/".join(parts[4:])
    if any(part in {"", ".", ".."} for part in PurePosixPath(subdirectory).parts):
        raise ValueError("GitHub Skill subdirectory is invalid.")
    encoded_ref = quote(ref, safe="")
    archive_url = f"https://github.com/{owner}/{repository}/archive/{encoded_ref}.zip"
    public_path = f"/{owner}/{repository}"
    if ref != "HEAD":
        public_path += f"/tree/{quote(ref, safe='')}"
        if subdirectory:
            public_path += f"/{'/'.join(quote(part, safe='') for part in PurePosixPath(subdirectory).parts)}"
    return {
        "archive_url": archive_url,
        "public_url": f"https://github.com{public_path}",
        "ref": ref,
        "subdirectory": subdirectory,
    }


def _download_github_archive(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "gm-science-skill-import/1"})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310 - validated GitHub URL
            raw_length = response.headers.get("Content-Length")
            if raw_length and int(raw_length) > _MAX_GITHUB_DOWNLOAD_BYTES:
                raise ValueError("GitHub Skill archive exceeds the supported download size.")
            payload = response.read(_MAX_GITHUB_DOWNLOAD_BYTES + 1)
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError(f"GitHub Skill download failed: {exc}") from exc
    if len(payload) > _MAX_GITHUB_DOWNLOAD_BYTES:
        raise ValueError("GitHub Skill archive exceeds the supported download size.")
    return payload
