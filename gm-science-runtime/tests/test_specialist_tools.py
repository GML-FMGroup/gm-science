from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from openppx.gm_science.specialists import tools
from openppx.gm_science.store import GmScienceStore


def test_paper_bundle_marks_metadata_abstract_evidence(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("GM_SCIENCE_DATA_DIR", str(tmp_path))
    store = GmScienceStore(tmp_path)
    project = store.create_project(name="Review", description="", agent_context="")
    paper = store.create_artifact(
        project_id=project.id,
        artifact_type="paper",
        title="Abstract-only paper",
        path_or_url="https://example.test/paper",
        metadata={"abstract": "Only the abstract is available.", "doi": "10.1000/test"},
    )

    bundle = tools.science_read_paper_bundle(project.id, [paper.id])

    assert bundle["papers"][0]["evidence_scope"] == "metadata_abstract"
    assert bundle["papers"][0]["source_text"] == "Only the abstract is available."
    assert bundle["papers"][0]["metadata"]["doi"] == "10.1000/test"


def test_paper_bundle_reads_only_bounded_project_workspace_text(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("GM_SCIENCE_DATA_DIR", str(tmp_path))
    store = GmScienceStore(tmp_path)
    project = store.create_project(name="Review", description="", agent_context="")
    source = Path(project.workspace_path) / "papers" / "paper.txt"
    source.parent.mkdir(parents=True)
    source.write_text("A" * 2_000, encoding="utf-8")
    paper = store.create_artifact(
        project_id=project.id,
        artifact_type="paper",
        title="Local text paper",
        path_or_url=str(source),
        metadata={"abstract": "Short abstract"},
    )
    monkeypatch.setattr(tools, "_paper_reader_limits", lambda: (6, 1_000))

    bundle = tools.science_read_paper_bundle(project.id, [paper.id])

    evidence = bundle["papers"][0]
    assert evidence["evidence_scope"] == "local_text"
    assert len(evidence["source_text"]) == 1_000
    assert evidence["truncated"] is True


def test_paper_bundle_rejects_cross_project_and_outside_workspace_text(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("GM_SCIENCE_DATA_DIR", str(tmp_path))
    store = GmScienceStore(tmp_path)
    project = store.create_project(name="Review", description="", agent_context="")
    other = store.create_project(name="Other", description="", agent_context="")
    other_paper = store.create_artifact(
        project_id=other.id,
        artifact_type="paper",
        title="Other paper",
        path_or_url="",
        metadata={"abstract": "Other"},
    )
    outside = tmp_path / "outside.txt"
    outside.write_text("outside", encoding="utf-8")
    outside_paper = store.create_artifact(
        project_id=project.id,
        artifact_type="paper",
        title="Outside paper",
        path_or_url=str(outside),
        metadata={"abstract": "Fallback must not hide an unsafe path."},
    )

    with pytest.raises(ValueError, match="does not belong"):
        tools.science_read_paper_bundle(project.id, [other_paper.id])
    with pytest.raises(ValueError, match="workspace"):
        tools.science_read_paper_bundle(project.id, [outside_paper.id])


def test_review_bundle_accepts_report_and_reading_note_only(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("GM_SCIENCE_DATA_DIR", str(tmp_path))
    store = GmScienceStore(tmp_path)
    project = store.create_project(name="Review", description="", agent_context="")
    report_path = Path(project.workspace_path) / "reports" / "draft.md"
    report_path.parent.mkdir(parents=True)
    report_path.write_text("# Draft\nA claim.", encoding="utf-8")
    report = store.create_artifact(
        project_id=project.id,
        artifact_type="report",
        title="Draft",
        path_or_url=str(report_path),
        metadata={"paper_artifact_ids": []},
    )
    paper = store.create_artifact(
        project_id=project.id,
        artifact_type="paper",
        title="Paper",
        path_or_url="",
    )

    bundle = tools.science_read_review_bundle(project.id, report.id)

    assert bundle["artifact_id"] == report.id
    assert bundle["content"].startswith("# Draft")
    with pytest.raises(ValueError, match="report or reading_note"):
        tools.science_read_review_bundle(project.id, paper.id)


def test_review_bundle_includes_bounded_linked_paper_evidence(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("GM_SCIENCE_DATA_DIR", str(tmp_path))
    store = GmScienceStore(tmp_path)
    project = store.create_project(name="Review", description="", agent_context="")
    report_path = Path(project.workspace_path) / "reports" / "draft.md"
    report_path.parent.mkdir(parents=True)
    report_path.write_text("# Draft\nA claim.", encoding="utf-8")
    paper = store.create_artifact(
        project_id=project.id,
        artifact_type="paper",
        title="Linked paper",
        path_or_url="https://example.test/paper",
        metadata={"abstract": "A" * 1_000, "doi": "10.1000/linked"},
    )
    report = store.create_artifact(
        project_id=project.id,
        artifact_type="report",
        title="Draft",
        path_or_url=str(report_path),
        metadata={"paper_artifact_ids": [paper.id]},
    )
    config = tools.load_specialist_config()
    monkeypatch.setattr(
        tools,
        "load_specialist_config",
        lambda: replace(config, reviewer=replace(config.reviewer, max_source_chars=100)),
    )

    bundle = tools.science_read_review_bundle(project.id, report.id)

    assert bundle["content"].startswith("# Draft")
    assert bundle["papers"] == [
        {
            "artifact_id": paper.id,
            "title": "Linked paper",
            "evidence_scope": "metadata_abstract",
            "metadata": {"doi": "10.1000/linked"},
            "source_text": "A" * 84,
            "source_chars": 84,
            "truncated": True,
        }
    ]
    assert bundle["total_source_chars"] == 100
    assert bundle["truncated"] is True
