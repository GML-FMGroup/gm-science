from __future__ import annotations

import json
import io
import threading
import zipfile
from pathlib import Path

import pytest

from openppx.core.config import config_to_env, load_config
from openppx.gm_science.authoring import (
    CapabilityConflictError,
    CapabilityInUseError,
    CapabilityNotFoundError,
    GmScienceCapabilityAuthoringService,
)
from openppx.gm_science.bootstrap import ensure_gm_science_initialized
from openppx.gm_science.infrastructure import RegistryPermissionError
from openppx.gm_science.settings import GmScienceSettingsService
from openppx.gm_science.store import GmScienceStore


def _service(tmp_path: Path) -> tuple[GmScienceCapabilityAuthoringService, Path]:
    initialized = ensure_gm_science_initialized(root_dir=tmp_path / "data")
    return (
        GmScienceCapabilityAuthoringService(
            config_path=initialized.config_path,
            store=GmScienceStore(tmp_path / "data"),
        ),
        initialized.config_path,
    )


def test_skill_authoring_publishes_discoverable_skill_and_persists(tmp_path: Path) -> None:
    service, config_path = _service(tmp_path)

    capability = service.create_skill(
        {
            "id": "assay-quality",
            "name": "Assay Quality",
            "description": "Review assay quality controls and limitations.",
            "content": "# Workflow\n\n1. Inspect controls.\n2. Report limitations.",
            "version": "1.0.0",
            "license": "Private",
        }
    )

    assert capability["id"] == "assay-quality"
    assert capability["name"] == "Assay Quality"
    assert capability["description"] == "Review assay quality controls and limitations."
    assert capability["source"] == "local"
    assert capability["version"] == "1.0.0"
    assert capability["license"] == "Private"
    assert capability["default_enabled"] is False
    skill_file = config_path.parent / "skills" / "assay-quality" / "SKILL.md"
    assert skill_file.is_file()
    assert "# Workflow" in skill_file.read_text(encoding="utf-8")

    reloaded = GmScienceCapabilityAuthoringService(config_path=config_path)
    with pytest.raises(CapabilityConflictError, match="already exists"):
        reloaded.create_skill(
            {
                "id": "assay-quality",
                "name": "Duplicate",
                "description": "Duplicate skill.",
                "content": "# Duplicate",
            }
        )


@pytest.mark.parametrize("skill_id", ["Bad-ID", "two words", "../escape", "_hidden"])
def test_skill_authoring_rejects_unsafe_identifiers(tmp_path: Path, skill_id: str) -> None:
    service, _config_path = _service(tmp_path)

    with pytest.raises(ValueError, match="invalid format"):
        service.create_skill(
            {
                "id": skill_id,
                "name": "Unsafe",
                "description": "Unsafe ID.",
                "content": "# Unsafe",
            }
        )


def test_skill_authoring_enforces_publish_permission(tmp_path: Path) -> None:
    initialized = ensure_gm_science_initialized(root_dir=tmp_path / "data")
    shared_lock = threading.RLock()
    settings = GmScienceSettingsService(config_path=initialized.config_path, lock=shared_lock)
    service = GmScienceCapabilityAuthoringService(
        config_path=initialized.config_path,
        lock=shared_lock,
    )
    settings.update_settings({"permission_grants": {"publish_skill": False}})

    with pytest.raises(RegistryPermissionError, match="Publish skill"):
        service.create_skill(
            {
                "id": "blocked-skill",
                "name": "Blocked Skill",
                "description": "Must not be written.",
                "content": "# Blocked",
            }
        )
    assert not (initialized.config_path.parent / "skills" / "blocked-skill").exists()


def test_skill_draft_can_be_saved_resumed_published_and_deleted(tmp_path: Path) -> None:
    service, config_path = _service(tmp_path)

    incomplete = service.save_skill_draft(
        {
            "id": "assay-draft",
            "name": "Assay draft",
            "description": "",
            "content": "",
        }
    )
    assert incomplete["id"] == "assay-draft"
    assert service.list_skill_drafts() == [incomplete]
    draft_path = config_path.parent / "drafts" / "skills" / "assay-draft.json"
    assert draft_path.is_file()
    assert draft_path.stat().st_mode & 0o777 == 0o600

    complete = service.save_skill_draft(
        {
            "id": "assay-draft",
            "name": "Assay workflow",
            "description": "Review assay evidence.",
            "content": "# Workflow\n\nInspect controls.",
        }
    )
    assert complete["name"] == "Assay workflow"
    capability = service.publish_skill_draft("assay-draft")
    assert capability["id"] == "assay-draft"
    assert service.list_skill_drafts() == []
    assert (config_path.parent / "skills" / "assay-draft" / "SKILL.md").is_file()

    service.save_skill_draft({"id": "temporary", "name": "Temporary"})
    service.delete_skill_draft("temporary")
    with pytest.raises(CapabilityNotFoundError, match="was not found"):
        service.delete_skill_draft("temporary")


def test_connector_authoring_persists_safe_remote_server_metadata(tmp_path: Path) -> None:
    service, config_path = _service(tmp_path)

    capability = service.create_connector(
        {
            "id": "lab-search",
            "name": "Lab Search",
            "description": "Search the laboratory MCP service.",
            "connection_type": "remote",
            "url": "https://mcp.example.test/v1",
        }
    )

    assert capability["id"] == "mcp:lab-search"
    assert capability["name"] == "Lab Search"
    assert capability["description"] == "Search the laboratory MCP service."
    assert capability["metadata"]["transport"] == "http"
    config = load_config(config_path=config_path)
    assert config["tools"]["mcpServers"]["lab-search"] == {
        "enabled": True,
        "name": "Lab Search",
        "description": "Search the laboratory MCP service.",
            "url": "https://mcp.example.test/v1",
            "transport": "http",
            "managedBy": "gm-science",
        }


@pytest.mark.parametrize(
    "url",
    [
        "file:///tmp/server",
        "https://user:secret@mcp.example.test/v1",
        "https://mcp.example.test/v1?token=secret",
        "https://mcp.example.test/v1#secret",
    ],
)
def test_connector_authoring_rejects_unsafe_remote_urls(tmp_path: Path, url: str) -> None:
    service, _config_path = _service(tmp_path)

    with pytest.raises(ValueError, match="URL"):
        service.create_connector(
            {
                "id": "unsafe-remote",
                "name": "Unsafe Remote",
                "description": "Unsafe remote MCP.",
                "connection_type": "remote",
                "url": url,
            }
        )


def test_connector_authoring_parses_local_command_without_shell(tmp_path: Path) -> None:
    service, config_path = _service(tmp_path)

    capability = service.create_connector(
        {
            "id": "local-files",
            "name": "Local Files",
            "description": "Read explicitly selected local files.",
            "connection_type": "local",
            "command_line": "uvx mcp-server-filesystem '/tmp/Research Files'",
        }
    )

    assert capability["metadata"]["transport"] == "stdio"
    server = load_config(config_path=config_path)["tools"]["mcpServers"]["local-files"]
    assert server["command"] == "uvx"
    assert server["args"] == ["mcp-server-filesystem", "/tmp/Research Files"]
    assert "shell" not in server
    assert "env" not in server


def test_connector_authoring_persists_filters_confirmation_and_write_only_secrets(
    tmp_path: Path,
) -> None:
    service, config_path = _service(tmp_path)
    settings = GmScienceSettingsService(config_path=config_path)
    settings.update_settings(
        {
            "custom_credential": {
                "operation": "upsert",
                "id": "lab-token",
                "name": "Lab token",
                "value": "Bearer first-secret",
            }
        }
    )

    service.create_connector(
        {
            "id": "secured-lab",
            "name": "Secured Lab",
            "description": "Use an authenticated laboratory MCP service.",
            "connection_type": "remote",
            "url": "https://mcp.example.test/v1",
            "tool_filter": ["search", "fetch", "search"],
            "require_confirmation": True,
            "header_credential_refs": {"Authorization": "lab-token"},
        }
    )

    server = load_config(config_path=config_path)["tools"]["mcpServers"]["secured-lab"]
    assert server["toolFilter"] == ["search", "fetch"]
    assert server["requireConfirmation"] is True
    assert server["credentialBindings"] == {"headers": {"Authorization": "lab-token"}}
    assert "headers" not in server
    definition = service.get_definition("connector", "mcp:secured-lab")
    assert definition["tool_filter"] == ["search", "fetch"]
    assert definition["require_confirmation"] is True
    assert definition["header_credential_refs"] == {"Authorization": "lab-token"}
    assert definition["environment_credential_refs"] == {}
    assert "first-secret" not in repr(definition)
    runtime_servers = json.loads(config_to_env(load_config(config_path=config_path))["OPENPPX_MCP_SERVERS_JSON"])
    assert runtime_servers["secured-lab"]["headers"] == {
        "Authorization": "Bearer first-secret"
    }
    assert "credentialBindings" not in runtime_servers["secured-lab"]

    service.update_connector(
        "mcp:secured-lab",
        {
            "name": "Secured Lab",
            "description": "Use an authenticated laboratory MCP service.",
            "connection_type": "remote",
            "url": "https://mcp.example.test/v2",
            "tool_filter": ["search"],
            "require_confirmation": False,
            "header_credential_refs": {"Authorization": "lab-token"},
        },
    )
    updated = load_config(config_path=config_path)["tools"]["mcpServers"]["secured-lab"]
    assert updated["credentialBindings"] == {"headers": {"Authorization": "lab-token"}}
    assert updated["toolFilter"] == ["search"]
    assert updated.get("requireConfirmation", False) is False


def test_local_connector_environment_can_be_replaced_without_secret_echo(tmp_path: Path) -> None:
    service, config_path = _service(tmp_path)
    settings = GmScienceSettingsService(config_path=config_path)
    for credential_id, value in (("lab-token", "first"), ("lab-scope", "read")):
        settings.update_settings(
            {
                "custom_credential": {
                    "operation": "upsert",
                    "id": credential_id,
                    "name": credential_id.replace("-", " ").title(),
                    "value": value,
                }
            }
        )
    service.create_connector(
        {
            "id": "local-secure",
            "name": "Local Secure",
            "description": "Run a local authenticated MCP server.",
            "connection_type": "local",
            "command_line": "mcp-local --stdio",
            "environment_credential_refs": {
                "LAB_TOKEN": "lab-token",
                "LAB_SCOPE": "lab-scope",
            },
        }
    )

    definition = service.get_definition("connector", "local-secure")
    assert definition["environment_credential_refs"] == {
        "LAB_TOKEN": "lab-token",
        "LAB_SCOPE": "lab-scope",
    }
    assert "first" not in repr(definition)

    service.update_connector(
        "local-secure",
        {
            "name": "Local Secure",
            "description": "Run a local authenticated MCP server.",
            "connection_type": "local",
            "command_line": "mcp-local --stdio",
            "environment_credential_refs": {"LAB_TOKEN": "lab-token"},
        },
    )
    server = load_config(config_path=config_path)["tools"]["mcpServers"]["local-secure"]
    assert server["credentialBindings"] == {"env": {"LAB_TOKEN": "lab-token"}}
    runtime_servers = json.loads(config_to_env(load_config(config_path=config_path))["OPENPPX_MCP_SERVERS_JSON"])
    assert runtime_servers["local-secure"]["env"] == {"LAB_TOKEN": "first"}


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("header_credential_refs", {"Bad Header": "credential"}),
        ("header_credential_refs", {"Authorization": "missing"}),
        ("environment_credential_refs", {"BAD-NAME": "credential"}),
        ("environment_credential_refs", {"TOKEN": ""}),
    ],
)
def test_connector_authoring_rejects_invalid_secret_bindings(
    tmp_path: Path,
    field: str,
    value: dict[str, str],
) -> None:
    service, _config_path = _service(tmp_path)
    body = {
        "id": "invalid-secrets",
        "name": "Invalid Secrets",
        "description": "Reject invalid secret bindings.",
        "connection_type": "remote" if field == "header_credential_refs" else "local",
        "url": "https://mcp.example.test/v1",
        "command_line": "mcp-local",
        field: value,
    }

    with pytest.raises(ValueError):
        service.create_connector(body)


def test_specialist_authoring_persists_exact_available_assignments(tmp_path: Path) -> None:
    service, config_path = _service(tmp_path)
    service.create_skill(
        {
            "id": "assay-quality",
            "name": "Assay Quality",
            "description": "Review assay quality.",
            "content": "# Assay Quality",
        }
    )
    service.create_connector(
        {
            "id": "local-files",
            "name": "Local Files",
            "description": "Read local files.",
            "connection_type": "local",
            "command_line": "mcp-server-filesystem /tmp/research",
        }
    )

    capability = service.create_specialist(
        {
            "id": "assay_reviewer",
            "name": "Assay Reviewer",
            "description": "Review assay design and evidence quality.",
            "instructions": "Check controls, statistics, and limitations.",
            "skills": ["assay-quality"],
            "connectors": ["mcp:local-files"],
            "connector_tools": {"mcp:local-files": ["read_file", "list_directory"]},
        }
    )

    assert capability["id"] == "assay_reviewer"
    assert capability["name"] == "Assay Reviewer"
    assert capability["metadata"]["assigned_skills"] == ["assay-quality"]
    assert capability["metadata"]["assigned_connectors"] == ["mcp:local-files"]
    stored = load_config(config_path=config_path)["science"]["specialists"]["custom"]["assay_reviewer"]
    assert stored == {
        "title": "Assay Reviewer",
        "description": "Review assay design and evidence quality.",
        "enabled": True,
        "autoDispatch": False,
        "model": "",
        "instructions": "Check controls, statistics, and limitations.",
        "skills": ["assay-quality"],
        "connectors": ["mcp:local-files"],
        "connectorTools": {"mcp:local-files": ["read_file", "list_directory"]},
    }
    definition = service.get_definition("specialist", "assay_reviewer")
    assert definition["connector_tools"] == {
        "mcp:local-files": ["read_file", "list_directory"]
    }


def test_specialist_tool_filter_rejects_unassigned_or_native_connector(tmp_path: Path) -> None:
    service, _config_path = _service(tmp_path)
    service.create_connector(
        {
            "id": "lab-tools",
            "name": "Lab Tools",
            "description": "Use laboratory tools.",
            "connection_type": "local",
            "command_line": "lab-mcp",
        }
    )

    with pytest.raises(ValueError, match="unassigned Connector"):
        service.create_specialist(
            {
                "id": "invalid_tools",
                "name": "Invalid Tools",
                "description": "Has an invalid tool assignment.",
                "instructions": "Use assigned tools only.",
                "connectors": [],
                "connector_tools": {"mcp:lab-tools": ["search"]},
            }
        )

    with pytest.raises(ValueError, match="only for MCP Connectors"):
        service.create_specialist(
            {
                "id": "native_tools",
                "name": "Native Tools",
                "description": "Has an invalid native filter.",
                "instructions": "Use assigned tools only.",
                "connectors": ["pubmed"],
                "connector_tools": {"pubmed": ["search"]},
            }
        )


def test_specialist_authoring_rejects_unavailable_assignments_and_permission(tmp_path: Path) -> None:
    service, config_path = _service(tmp_path)

    with pytest.raises(ValueError, match="Unavailable skill capability: boltz"):
        service.create_specialist(
            {
                "id": "invalid_specialist",
                "name": "Invalid Specialist",
                "description": "References an unavailable capability.",
                "instructions": "Use Boltz.",
                "skills": ["boltz"],
            }
        )

    settings = GmScienceSettingsService(config_path=config_path)
    settings.update_settings({"permission_grants": {"create_agent": False}})
    with pytest.raises(RegistryPermissionError, match="Create agent"):
        service.create_specialist(
            {
                "id": "blocked_specialist",
                "name": "Blocked Specialist",
                "description": "Must not be saved.",
                "instructions": "Do not save this.",
            }
        )
    config = json.loads(config_path.read_text(encoding="utf-8"))
    assert "blocked_specialist" not in config["science"]["specialists"]["custom"]


def test_local_skill_update_definition_and_unreferenced_delete(tmp_path: Path) -> None:
    service, config_path = _service(tmp_path)
    service.create_skill(
        {
            "id": "assay-quality",
            "name": "Assay Quality",
            "description": "Initial description.",
            "content": "# Initial",
        }
    )

    updated = service.update_skill(
        "assay-quality",
        {
            "name": "Assay Quality Review",
            "description": "Updated description.",
            "content": "# Updated\n\nUse controls.",
            "version": "2.0",
            "license": "Private",
        },
    )

    assert updated["name"] == "Assay Quality Review"
    definition = service.get_definition("skill", "assay-quality")
    assert definition == {
        "id": "assay-quality",
        "kind": "skill",
        "name": "Assay Quality Review",
        "description": "Updated description.",
        "content": "# Updated\n\nUse controls.",
        "version": "2.0",
        "license": "Private",
    }

    service.delete_capability("skill", "assay-quality")
    assert not (config_path.parent / "skills" / "assay-quality").exists()
    with pytest.raises(CapabilityNotFoundError):
        service.get_definition("skill", "assay-quality")


def test_delete_rejects_project_and_specialist_references(tmp_path: Path) -> None:
    service, _config_path = _service(tmp_path)
    service.create_skill(
        {
            "id": "assay-quality",
            "name": "Assay Quality",
            "description": "Review assay quality.",
            "content": "# Assay Quality",
        }
    )
    project = service.store.create_project(
        name="Referenced Project",
        description="",
        agent_context="",
        enabled_skills=["assay-quality"],
    )

    with pytest.raises(CapabilityInUseError, match="Referenced Project"):
        service.delete_capability("skill", "assay-quality")

    service.store.update_project_capabilities(
        project.id,
        enabled_skills=[],
        enabled_connectors=[],
        enabled_specialists=[],
    )
    service.create_specialist(
        {
            "id": "assay_reviewer",
            "name": "Assay Reviewer",
            "description": "Review assay quality.",
            "instructions": "Check the assay.",
            "skills": ["assay-quality"],
        }
    )
    with pytest.raises(CapabilityInUseError, match="assay_reviewer"):
        service.delete_capability("skill", "assay-quality")


def test_managed_connector_and_specialist_can_be_edited_and_deleted(tmp_path: Path) -> None:
    service, config_path = _service(tmp_path)
    service.create_connector(
        {
            "id": "local-files",
            "name": "Local Files",
            "description": "Read files.",
            "connection_type": "local",
            "command_line": "mcp-files /tmp/one",
        }
    )
    connector = service.update_connector(
        "mcp:local-files",
        {
            "name": "Project Files",
            "description": "Read Project files.",
            "connection_type": "local",
            "command_line": "mcp-files '/tmp/two words'",
        },
    )
    assert connector["name"] == "Project Files"
    assert service.get_definition("connector", "mcp:local-files")["command_line"] == "mcp-files '/tmp/two words'"

    service.create_specialist(
        {
            "id": "assay_reviewer",
            "name": "Assay Reviewer",
            "description": "Review assays.",
            "instructions": "Review.",
        }
    )
    specialist = service.update_specialist(
        "assay_reviewer",
        {
            "name": "Evidence Reviewer",
            "description": "Review evidence.",
            "instructions": "Review evidence and limitations.",
            "connectors": ["mcp:local-files"],
        },
    )
    assert specialist["name"] == "Evidence Reviewer"
    assert specialist["metadata"]["assigned_connectors"] == ["mcp:local-files"]
    service.delete_capability("specialist", "assay_reviewer")
    service.delete_capability("connector", "mcp:local-files")
    config = load_config(config_path=config_path)
    assert "local-files" not in config["tools"]["mcpServers"]


def test_local_directory_skill_import_preserves_reference_files(tmp_path: Path) -> None:
    service, config_path = _service(tmp_path)
    source = tmp_path / "uploaded-skill"
    (source / "references").mkdir(parents=True)
    (source / "SKILL.md").write_text(
        "---\nname: uploaded-skill\ntitle: Uploaded Skill\ndescription: Imported workflow.\n---\n\n# Workflow\n",
        encoding="utf-8",
    )
    (source / "references" / "protocol.md").write_text("Protocol", encoding="utf-8")

    capability = service.import_skill({"source_path": str(source)})

    assert capability["id"] == "uploaded-skill"
    installed = config_path.parent / "skills" / "uploaded-skill"
    assert (installed / "references" / "protocol.md").read_text(encoding="utf-8") == "Protocol"
    origin = json.loads((installed / ".gm-science-origin.json").read_text(encoding="utf-8"))
    assert origin == {"type": "local_upload"}


def test_github_skill_import_uses_bounded_archive_and_records_origin(tmp_path: Path) -> None:
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w") as output:
        output.writestr(
            "repo-main/skills/evidence/SKILL.md",
            "---\nname: evidence-skill\ntitle: Evidence Skill\ndescription: Review evidence.\n---\n\n# Evidence\n",
        )
        output.writestr("repo-main/skills/evidence/references/checklist.md", "Checklist")
    initialized = ensure_gm_science_initialized(root_dir=tmp_path / "data")
    requested_urls: list[str] = []
    service = GmScienceCapabilityAuthoringService(
        config_path=initialized.config_path,
        store=GmScienceStore(tmp_path / "data"),
        github_downloader=lambda url: requested_urls.append(url) or archive.getvalue(),
    )

    capability = service.import_skill_from_github(
        {"url": "https://github.com/example/research-skills/tree/main/skills/evidence"}
    )

    assert capability["id"] == "evidence-skill"
    assert requested_urls == ["https://github.com/example/research-skills/archive/main.zip"]
    origin_path = initialized.config_path.parent / "skills" / "evidence-skill" / ".gm-science-origin.json"
    origin = json.loads(origin_path.read_text(encoding="utf-8"))
    assert origin["url"] == "https://github.com/example/research-skills/tree/main/skills/evidence"


def test_skill_zip_import_rejects_path_traversal(tmp_path: Path) -> None:
    service, _config_path = _service(tmp_path)
    archive_path = tmp_path / "unsafe.zip"
    with zipfile.ZipFile(archive_path, "w") as output:
        output.writestr("../SKILL.md", "unsafe")

    with pytest.raises(ValueError, match="unsafe path"):
        service.import_skill({"source_path": str(archive_path)})
