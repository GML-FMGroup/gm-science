from __future__ import annotations

from pathlib import Path

from openppx.gm_science.specialists.artifacts import save_critique_report, save_reading_note
from openppx.gm_science.specialists.models import (
    PaperReading,
    PaperReaderOutput,
    ReviewerFinding,
    ReviewerOutput,
)
from openppx.gm_science.store import GmScienceStore


def test_save_reading_note_writes_markdown_and_artifact_links(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("GM_SCIENCE_DATA_DIR", str(tmp_path))
    store = GmScienceStore(tmp_path)
    project = store.create_project(name="Review", description="", agent_context="")
    paper = store.create_artifact(
        project_id=project.id,
        artifact_type="paper",
        title="Paper",
        path_or_url="",
    )
    output = PaperReaderOutput(
        title="Reading note",
        synthesis="The abstract supports a narrow conclusion.",
        readings=[
            PaperReading(
                paper_artifact_id=paper.id,
                title="Paper",
                evidence_scope="metadata_abstract",
                contribution="A contribution.",
                methods=["Method"],
                results=["Result"],
                limitations=["Abstract only"],
                reproducibility_clues=[],
                confidence="medium",
            )
        ],
        agreements=[],
        conflicts=[],
        open_questions=["Need full text"],
        confidence_note="Limited to abstract metadata.",
    )

    artifact = save_reading_note(
        store,
        project_id=project.id,
        session_id="session-1",
        output=output,
        source_artifact_ids=[paper.id],
        focus="protein folding",
        comparison_question="Which method is more reproducible?",
        model_name="openai-codex/gpt-5.5",
    )

    assert artifact.type == "reading_note"
    assert artifact.metadata["source_artifact_ids"] == [paper.id]
    assert artifact.metadata["evidence_scopes"] == ["metadata_abstract"]
    assert artifact.metadata["focus"] == "protein folding"
    assert artifact.metadata["comparison_question"] == "Which method is more reproducible?"
    assert artifact.provenance["created_by"] == "paper_reader"
    assert artifact.provenance["model"] == "openai-codex/gpt-5.5"
    markdown = Path(artifact.path_or_url)
    assert markdown.is_relative_to(Path(project.workspace_path))
    assert "Limited to abstract metadata" in markdown.read_text(encoding="utf-8")


def test_save_critique_report_links_target_and_structured_findings(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("GM_SCIENCE_DATA_DIR", str(tmp_path))
    store = GmScienceStore(tmp_path)
    project = store.create_project(name="Review", description="", agent_context="")
    report = store.create_artifact(
        project_id=project.id,
        artifact_type="report",
        title="Draft",
        path_or_url="",
    )
    output = ReviewerOutput(
        title="Critique",
        verdict="revise",
        summary="One major issue.",
        strengths=["Clear question"],
        findings=[
            ReviewerFinding(
                severity="major",
                category="evidence",
                claim="The central claim lacks support.",
                issue="The report overstates the available abstract evidence.",
                evidence="No linked paper supports it.",
                recommendation="Add a citation or narrow the claim.",
            )
        ],
        unsupported_claims=["The central claim"],
        missing_evidence=["A linked primary source"],
        evidence_scopes=["metadata_abstract"],
        review_limitations=["Only abstract metadata was available."],
    )

    artifact = save_critique_report(
        store,
        project_id=project.id,
        session_id="session-1",
        output=output,
        target_artifact_id=report.id,
        trigger="explicit",
        review_focus="citation integrity",
        model_name="openai-codex/gpt-5.5",
    )

    assert artifact.type == "critique_report"
    assert artifact.metadata["target_artifact_id"] == report.id
    assert artifact.metadata["verdict"] == "revise"
    assert artifact.metadata["findings"][0]["severity"] == "major"
    assert artifact.metadata["review_focus"] == "citation integrity"
    assert artifact.provenance["trigger"] == "explicit"
    assert artifact.provenance["model"] == "openai-codex/gpt-5.5"
    assert "One major issue" in Path(artifact.path_or_url).read_text(encoding="utf-8")
