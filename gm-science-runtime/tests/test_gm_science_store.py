from __future__ import annotations

from pathlib import Path

import pytest

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


def test_update_project_capabilities_persists_allowlists(tmp_path: Path) -> None:
    store = GmScienceStore(tmp_path)
    project = store.create_project(
        name="Configurable project",
        description="",
        agent_context="",
        enabled_skills=["literature-review"],
        enabled_connectors=["arxiv", "pubmed"],
        enabled_specialists=["paper_reader", "research_reviewer"],
    )

    updated = store.update_project_capabilities(
        project.id,
        enabled_skills=[],
        enabled_connectors=["arxiv"],
        enabled_specialists=["research_reviewer"],
    )

    assert updated.enabled_skills == []
    assert updated.enabled_connectors == ["arxiv"]
    assert updated.enabled_specialists == ["research_reviewer"]
    assert updated.updated_at >= project.updated_at
    assert store.get_project(project.id) == updated


def test_project_session_association_counts_and_rejects_cross_project_relink(tmp_path: Path) -> None:
    store = GmScienceStore(tmp_path)
    project = store.create_project(name="Primary", description="", agent_context="")
    other_project = store.create_project(name="Other", description="", agent_context="")

    linked = store.link_project_session(
        project_id=project.id,
        session_id="session-1",
        agent_id="science-research",
    )
    repeated = store.link_project_session(
        project_id=project.id,
        session_id="session-1",
        agent_id="science-research",
    )

    assert linked.project_id == project.id
    assert repeated.created_at == linked.created_at
    assert store.get_project_session("session-1") == repeated
    assert store.list_project_sessions(project.id) == [repeated]
    assert store.count_project_sessions(project.id) == 1

    with pytest.raises(ValueError, match="already belongs"):
        store.link_project_session(
            project_id=other_project.id,
            session_id="session-1",
            agent_id="science-research",
        )


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


def test_science_run_association_round_trips_without_task_status(tmp_path: Path) -> None:
    store = GmScienceStore(tmp_path)
    project = store.create_project(name="Python research", description="", agent_context="")
    store.link_project_session(
        project_id=project.id,
        session_id="session-1",
        agent_id="science-research",
    )

    run = store.create_science_run(
        task_id="task-1",
        project_id=project.id,
        session_id="session-1",
        parent_task_id=None,
        kind="local_python",
        title="Check environment",
        source_path="runs/run-1/main.py",
        working_directory="runs/run-1",
        input_payload={"argv": ["--quick"]},
    )

    assert run.task_id == "task-1"
    assert run.project_id == project.id
    assert run.session_id == "session-1"
    assert run.input_payload == {"argv": ["--quick"]}
    assert not hasattr(run, "status")
    assert store.get_science_run("task-1") == run
    assert store.list_science_runs(project.id) == [run]


def test_science_run_rejects_session_from_another_project(tmp_path: Path) -> None:
    store = GmScienceStore(tmp_path)
    project = store.create_project(name="Primary", description="", agent_context="")
    other = store.create_project(name="Other", description="", agent_context="")
    store.link_project_session(
        project_id=other.id,
        session_id="session-other",
        agent_id="science-research",
    )

    with pytest.raises(ValueError, match="does not belong"):
        store.create_science_run(
            task_id="task-cross-project",
            project_id=project.id,
            session_id="session-other",
            kind="local_python",
            title="Invalid",
            source_path="main.py",
            working_directory="runs/run-invalid",
        )


def test_analysis_draft_round_trips_and_links_project_run(tmp_path: Path) -> None:
    store = GmScienceStore(tmp_path)
    project = store.create_project(name="Analysis", description="", agent_context="")
    dataset = store.create_artifact(
        project_id=project.id,
        artifact_type="dataset",
        title="Measurements",
        path_or_url="datasets/source.csv",
    )
    draft = store.create_analysis_draft(
        project_id=project.id,
        title="Compare measurements",
        objective="Compare group means.",
        dataset_artifact_ids=[dataset.id, dataset.id],
        plan={"operations": ["group_comparison"]},
        source="print('analysis')",
    )

    assert draft.dataset_artifact_ids == [dataset.id]
    assert draft.task_id is None
    assert not hasattr(draft, "status")
    assert store.get_analysis_draft(draft.id) == draft
    assert store.list_analysis_drafts(project.id) == [draft]

    store.create_science_run(
        task_id="task-analysis",
        project_id=project.id,
        kind="data_analysis",
        title=draft.title,
        source_path="runs/task-analysis/main.py",
        working_directory="runs/task-analysis",
        input_payload={"analysis_id": draft.id},
    )
    linked = store.link_analysis_task(draft.id, "task-analysis")

    assert linked.task_id == "task-analysis"
    assert store.find_analysis_by_task("task-analysis") == linked


def test_analysis_draft_rejects_cross_project_session_and_run(tmp_path: Path) -> None:
    store = GmScienceStore(tmp_path)
    project = store.create_project(name="Primary", description="", agent_context="")
    other = store.create_project(name="Other", description="", agent_context="")
    dataset = store.create_artifact(
        project_id=project.id,
        artifact_type="dataset",
        title="Data",
        path_or_url="data.csv",
    )
    store.link_project_session(
        project_id=other.id,
        session_id="session-other-analysis",
        agent_id="science-research",
    )

    with pytest.raises(ValueError, match="does not belong"):
        store.create_analysis_draft(
            project_id=project.id,
            session_id="session-other-analysis",
            title="Invalid",
            objective="Analyze data.",
            dataset_artifact_ids=[dataset.id],
            plan={},
            source="pass",
        )

    draft = store.create_analysis_draft(
        project_id=project.id,
        title="Valid",
        objective="Analyze data.",
        dataset_artifact_ids=[dataset.id],
        plan={},
        source="pass",
    )
    store.create_science_run(
        task_id="task-other-analysis",
        project_id=other.id,
        kind="data_analysis",
        title="Other",
        source_path="other.py",
        working_directory="runs/other",
    )

    with pytest.raises(ValueError, match="does not belong"):
        store.link_analysis_task(draft.id, "task-other-analysis")


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
