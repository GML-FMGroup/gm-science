from __future__ import annotations

import json
from pathlib import Path

from openppx.gm_science.bootstrap import ensure_gm_science_initialized
from openppx.gm_science.capabilities import build_capability_catalog
from openppx.tooling.skills_adapter import SkillRegistry


def _write_skill(
    root: Path,
    name: str,
    *,
    description: str,
    version: str = "",
    license_name: str = "",
) -> Path:
    """Create a minimal test Skill and return its SKILL.md path."""

    skill_dir = root / name
    skill_dir.mkdir(parents=True, exist_ok=True)
    frontmatter = ["---", f"name: {name}", f"description: {description}"]
    if version:
        frontmatter.append(f"version: {version}")
    if license_name:
        frontmatter.append(f"license: {license_name}")
    frontmatter.extend(["---", "", f"# {name}", ""])
    skill_file = skill_dir / "SKILL.md"
    skill_file.write_text("\n".join(frontmatter), encoding="utf-8")
    return skill_file


def test_capability_catalog_projects_discovered_skills_without_absolute_paths(tmp_path: Path) -> None:
    initialized = ensure_gm_science_initialized(root_dir=tmp_path / "data")
    bundled_dir = tmp_path / "bundled-skills"
    literature_file = _write_skill(
        bundled_dir,
        "literature-review",
        description="Search scholarly sources and register a cited review.",
        version="1.2.3",
        license_name="Apache-2.0",
    )
    reference_file = literature_file.parent / "references" / "guide.md"
    reference_file.parent.mkdir()
    reference_file.write_text("# Guide\n", encoding="utf-8")
    _write_skill(
        bundled_dir,
        "docx",
        description="Create and edit Word documents.",
    )
    _write_skill(
        initialized.config_path.parent / "skills",
        "local-analysis",
        description="Analyze local tabular datasets.",
        license_name="Private",
    )
    registry = SkillRegistry(
        agent_home=initialized.config_path.parent,
        builtin_skills_dir=bundled_dir,
    )

    catalog = build_capability_catalog(
        config_path=initialized.config_path,
        skill_registry=registry,
    )

    skills = [item for item in catalog if item["kind"] == "skill"]
    assert [item["id"] for item in skills] == ["docx", "literature-review", "local-analysis"]
    by_id = {item["id"]: item for item in skills}
    assert by_id["literature-review"] == {
        "id": "literature-review",
        "kind": "skill",
        "name": "Literature Review",
        "description": "Search scholarly sources and register a cited review.",
        "source": "built_in",
        "version": "1.2.3",
        "license": "Apache-2.0",
        "files": ["references/guide.md", "SKILL.md"],
        "available": True,
        "default_enabled": True,
        "project_enabled": None,
        "status": "ready",
        "status_detail": "",
        "metadata": {
            "registry_source": "builtin",
            "file_count": 2,
            "files_truncated": False,
        },
    }
    assert by_id["docx"]["name"] == "DOCX"
    assert by_id["docx"]["source"] == "built_in"
    assert by_id["local-analysis"]["source"] == "local"
    assert by_id["local-analysis"]["license"] == "Private"
    assert by_id["local-analysis"]["default_enabled"] is False
    serialized = json.dumps(catalog)
    assert str(tmp_path) not in serialized


def test_capability_catalog_marks_skill_aliases_without_exposing_the_target_path(tmp_path: Path) -> None:
    initialized = ensure_gm_science_initialized(root_dir=tmp_path / "data")
    bundled_dir = tmp_path / "bundled-skills"
    _write_skill(
        bundled_dir,
        "self-observe",
        description="Maintain durable memory.",
    )
    registry = SkillRegistry(
        agent_home=initialized.config_path.parent,
        builtin_skills_dir=bundled_dir,
    )

    catalog = build_capability_catalog(
        config_path=initialized.config_path,
        skill_registry=registry,
    )

    skills = {item["id"]: item for item in catalog if item["kind"] == "skill"}
    assert skills["memory"]["metadata"]["alias_of"] == "self-observe"
    assert "alias_of" not in skills["self-observe"]["metadata"]
    assert str(tmp_path) not in json.dumps(skills)


def test_capability_catalog_projects_configured_mcp_connectors_with_redacted_metadata(tmp_path: Path) -> None:
    initialized = ensure_gm_science_initialized(root_dir=tmp_path / "data")
    config = json.loads(initialized.config_path.read_text(encoding="utf-8"))
    config["tools"]["mcpServers"] = {
        "remote-lab": {
            "url": "https://scientist:password@mcp.example.test/api?token=remote-secret",
            "headers": {"Authorization": "Bearer remote-secret"},
            "runtimeHeaders": {"X-Project-Id": "state.project_id"},
            "toolFilter": ["search", "fetch"],
            "requireConfirmation": True,
        },
        "filesystem": {
            "command": "/opt/tools/mcp-filesystem",
            "args": ["--token", "stdio-secret"],
            "env": {"FILESYSTEM_TOKEN": "stdio-secret", "WORKSPACE_ROOT": "/private/workspace"},
            "toolNamePrefix": "science_fs_",
            "progressEvents": True,
            "longTaskProxy": False,
        },
        "disabled-server": {
            "enabled": False,
            "command": "disabled-command",
        },
        "broken-server": {"enabled": True},
        "invalid-server": "not-an-object",
        "windows-command": {
            "command": "C:\\Users\\secret-user\\bin\\mcp-windows.exe",
        },
    }
    initialized.config_path.write_text(json.dumps(config), encoding="utf-8")

    catalog = build_capability_catalog(config_path=initialized.config_path)

    connectors = [item for item in catalog if item["kind"] == "connector"]
    assert [item["id"] for item in connectors] == [
        "arxiv",
        "pubmed",
        "openalex",
        "mcp:broken-server",
        "mcp:disabled-server",
        "mcp:filesystem",
        "mcp:invalid-server",
        "mcp:remote-lab",
        "mcp:windows-command",
    ]
    by_id = {item["id"]: item for item in connectors}
    assert by_id["mcp:filesystem"]["source"] == "local"
    assert by_id["mcp:filesystem"]["available"] is True
    assert by_id["mcp:filesystem"]["default_enabled"] is False
    assert by_id["mcp:filesystem"]["status"] == "ready"
    assert by_id["mcp:filesystem"]["metadata"] == {
        "connector_type": "mcp",
        "server_name": "filesystem",
        "transport": "stdio",
        "tool_prefix": "science_fs",
        "tool_filter": [],
        "require_confirmation": False,
        "progress_events": True,
        "long_task_proxy": False,
        "inline_budget_ms": 5000,
        "job_protocol": False,
        "command_name": "mcp-filesystem",
        "endpoint_origin": "",
        "configured_env_names": ["FILESYSTEM_TOKEN", "WORKSPACE_ROOT"],
        "configured_header_names": [],
        "runtime_header_names": [],
    }
    assert by_id["mcp:remote-lab"]["metadata"]["transport"] == "http"
    assert by_id["mcp:remote-lab"]["metadata"]["endpoint_origin"] == "https://mcp.example.test"
    assert by_id["mcp:remote-lab"]["metadata"]["configured_header_names"] == ["Authorization"]
    assert by_id["mcp:remote-lab"]["metadata"]["runtime_header_names"] == ["X-Project-Id"]
    assert by_id["mcp:remote-lab"]["metadata"]["tool_filter"] == ["search", "fetch"]
    assert by_id["mcp:remote-lab"]["metadata"]["require_confirmation"] is True
    assert by_id["mcp:disabled-server"]["status"] == "disabled"
    assert by_id["mcp:disabled-server"]["available"] is False
    assert by_id["mcp:broken-server"]["status"] == "needs_configuration"
    assert by_id["mcp:invalid-server"]["status"] == "needs_configuration"
    assert by_id["mcp:windows-command"]["metadata"]["command_name"] == "mcp-windows.exe"

    serialized = json.dumps(connectors)
    assert "remote-secret" not in serialized
    assert "stdio-secret" not in serialized
    assert "scientist" not in serialized
    assert "password" not in serialized
    assert "/private/workspace" not in serialized
    assert "/opt/tools" not in serialized
    assert "secret-user" not in serialized


def test_capability_catalog_projects_configured_specialists_and_dependency_status(tmp_path: Path) -> None:
    initialized = ensure_gm_science_initialized(root_dir=tmp_path / "data")
    bundled_dir = tmp_path / "bundled-skills"
    _write_skill(
        bundled_dir,
        "literature-review",
        description="Search and synthesize scholarly evidence.",
    )
    registry = SkillRegistry(
        agent_home=initialized.config_path.parent,
        builtin_skills_dir=bundled_dir,
    )
    config = json.loads(initialized.config_path.read_text(encoding="utf-8"))
    config["science"]["projectDefaults"]["enabledSpecialists"].append("literature_scout")
    config["science"]["specialists"]["custom"] = {
        "literature_scout": {
            "title": "Literature Scout",
            "description": "Find focused research evidence.",
            "autoDispatch": True,
            "instructions": "Prefer primary sources.",
            "skills": ["literature-review"],
            "connectors": ["ARXIV"],
        },
        "broken_specialist": {
            "description": "References missing capabilities.",
            "skills": ["not-installed"],
            "connectors": ["mcp:not-configured"],
        },
    }
    initialized.config_path.write_text(json.dumps(config), encoding="utf-8")

    catalog = build_capability_catalog(
        config_path=initialized.config_path,
        skill_registry=registry,
    )

    specialists = {item["id"]: item for item in catalog if item["kind"] == "specialist"}
    scout = specialists["literature_scout"]
    assert scout["source"] == "local"
    assert scout["available"] is True
    assert scout["default_enabled"] is True
    assert scout["metadata"]["registry_source"] == "custom"
    assert scout["metadata"]["assigned_skills"] == ["literature-review"]
    assert scout["metadata"]["assigned_connectors"] == ["ARXIV"]
    assert scout["metadata"]["additional_instructions"] == "Prefer primary sources."
    broken = specialists["broken_specialist"]
    assert broken["available"] is False
    assert broken["status"] == "needs_configuration"
    assert "Missing Skills: not-installed" in broken["status_detail"]
    assert "Missing Connectors: mcp:not-configured" in broken["status_detail"]
