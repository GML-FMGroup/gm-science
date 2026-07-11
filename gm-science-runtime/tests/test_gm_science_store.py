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
