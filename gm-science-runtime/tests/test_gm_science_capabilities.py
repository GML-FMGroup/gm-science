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
