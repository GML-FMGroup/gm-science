from pathlib import Path

from openppx.tooling.skills_adapter import SkillRegistry


def test_literature_review_skill_is_discoverable_and_preserves_evidence_chain() -> None:
    registry = SkillRegistry(workspace=Path("/tmp/nonexistent-openppx-workspace"))
    names = {skill.name for skill in registry.list_skills()}

    assert "literature-review" in names
    content = registry.read_skill("literature-review")
    assert "science_list_sources" in content
    assert "science_search" in content
    assert "science_register_review" in content
    assert "paper artifact ID" in content
    assert "Do not invent DOI, PMID, arXiv ID" in content
    assert "evidence matrix" in content.lower()
