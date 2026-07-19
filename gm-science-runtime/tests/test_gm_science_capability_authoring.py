from __future__ import annotations

import json
import threading
from pathlib import Path

import pytest

from openppx.core.config import load_config
from openppx.gm_science.authoring import (
    CapabilityConflictError,
    GmScienceCapabilityAuthoringService,
)
from openppx.gm_science.bootstrap import ensure_gm_science_initialized
from openppx.gm_science.infrastructure import RegistryPermissionError
from openppx.gm_science.settings import GmScienceSettingsService


def _service(tmp_path: Path) -> tuple[GmScienceCapabilityAuthoringService, Path]:
    initialized = ensure_gm_science_initialized(root_dir=tmp_path / "data")
    return (
        GmScienceCapabilityAuthoringService(config_path=initialized.config_path),
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
    }


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
