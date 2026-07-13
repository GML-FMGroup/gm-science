from __future__ import annotations

from pathlib import Path

from openppx.gm_science.paths import get_gm_science_data_dir
from openppx.gm_science.store import GmScienceStore


def test_gm_science_data_dir_can_be_overridden(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("GM_SCIENCE_DATA_DIR", str(tmp_path / "science-home"))

    assert get_gm_science_data_dir() == tmp_path / "science-home"


def test_create_project_persists_context_and_workspace(tmp_path: Path) -> None:
    store = GmScienceStore(tmp_path)

    project = store.create_project(
        name="RAG for science",
        description="Shown in project lists only.",
        agent_context="Always cite paper URLs before making claims.",
    )

    assert project.id.startswith("proj_")
    assert project.name == "RAG for science"
    assert project.description == "Shown in project lists only."
    assert project.agent_context == "Always cite paper URLs before making claims."
    assert Path(project.workspace_path).is_dir()

    loaded = store.get_project(project.id)
    assert loaded == project
    assert store.list_projects() == [project]


def test_create_and_list_project_artifacts_round_trips_metadata(tmp_path: Path) -> None:
    store = GmScienceStore(tmp_path)
    project = store.create_project(
        name="Literature review",
        description="",
        agent_context="Use short summaries.",
    )

    artifact = store.create_artifact(
        project_id=project.id,
        artifact_type="paper",
        title="Attention Is All You Need",
        path_or_url="https://example.test/paper",
        mime_type="text/html",
        session_id="session-1",
        metadata={"source": "manual", "year": 2017},
        provenance={"created_by": "science-research", "run_id": "run-1"},
    )

    assert artifact.id.startswith("art_")
    assert artifact.project_id == project.id
    assert artifact.session_id == "session-1"
    assert artifact.type == "paper"
    assert artifact.metadata == {"source": "manual", "year": 2017}
    assert artifact.provenance == {"created_by": "science-research", "run_id": "run-1"}
    assert store.list_artifacts(project.id) == [artifact]


def test_find_project_paper_and_artifact_by_id(tmp_path: Path) -> None:
    store = GmScienceStore(tmp_path)
    project = store.create_project(name="Review", description="", agent_context="")
    other_project = store.create_project(name="Other", description="", agent_context="")
    paper = store.create_artifact(
        project_id=project.id,
        artifact_type="paper",
        title="Reliable Protein Folding",
        path_or_url="https://doi.org/10.1000/folding",
        metadata={"canonical_id": "doi:10.1000/folding"},
    )
    store.create_artifact(
        project_id=other_project.id,
        artifact_type="paper",
        title="Other copy",
        path_or_url="",
        metadata={"canonical_id": "doi:10.1000/folding"},
    )

    assert store.get_artifact(paper.id) == paper
    assert store.find_paper_artifact(project.id, "doi:10.1000/folding") == paper
    assert store.find_paper_artifact(project.id, "doi:missing") is None


def test_find_citation_is_scoped_to_report_and_paper(tmp_path: Path) -> None:
    store = GmScienceStore(tmp_path)
    project = store.create_project(name="Review", description="", agent_context="")
    paper = store.create_artifact(
        project_id=project.id,
        artifact_type="paper",
        title="Paper",
        path_or_url="",
    )
    report = store.create_artifact(
        project_id=project.id,
        artifact_type="report",
        title="Report",
        path_or_url="report.md",
    )
    citation = store.create_artifact(
        project_id=project.id,
        artifact_type="citation",
        title="Citation",
        path_or_url="",
        metadata={"paper_artifact_id": paper.id, "report_artifact_id": report.id},
    )

    assert store.find_citation_artifact(project.id, report.id, paper.id) == citation
    assert store.find_citation_artifact(project.id, report.id, "art_missing") is None


def test_update_artifact_metadata_replaces_metadata(tmp_path: Path) -> None:
    store = GmScienceStore(tmp_path)
    project = store.create_project(name="Review", description="", agent_context="")
    artifact = store.create_artifact(
        project_id=project.id,
        artifact_type="report",
        title="Report",
        path_or_url="report.md",
        metadata={"paper_artifact_ids": []},
    )

    updated = store.update_artifact_metadata(
        artifact.id,
        {"paper_artifact_ids": ["art-paper"], "citation_artifact_ids": ["art-citation"]},
    )

    assert updated.metadata == {
        "paper_artifact_ids": ["art-paper"],
        "citation_artifact_ids": ["art-citation"],
    }
    assert updated.updated_at >= artifact.updated_at
