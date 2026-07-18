"""Controlled artifact writers for specialist outputs."""

from __future__ import annotations

import re
import uuid
from pathlib import Path
from typing import Any

from ..models import ArtifactRecord
from ..store import GmScienceStore
from .models import ConfiguredSpecialistOutput, PaperReaderOutput, ReviewerOutput

READING_NOTE_MIME_TYPE = "application/vnd.gm-science.reading-note+json"
CRITIQUE_REPORT_MIME_TYPE = "application/vnd.gm-science.critique+json"
SPECIALIST_REPORT_MIME_TYPE = "application/vnd.gm-science.specialist-report+json"


def save_reading_note(
    store: GmScienceStore,
    *,
    project_id: str,
    session_id: str,
    output: PaperReaderOutput,
    source_artifact_ids: list[str],
    focus: str,
    comparison_question: str,
    model_name: str,
) -> ArtifactRecord:
    """Persist a validated paper-reader result as Markdown plus metadata."""

    project = _project(store, project_id)
    path = _artifact_path(project.workspace_path, "reading-notes", output.title)
    path.write_text(render_reading_note(output), encoding="utf-8")
    payload = output.model_dump(mode="json")
    unique_sources = list(dict.fromkeys(source_artifact_ids))
    payload.update(
        {
            "source_artifact_ids": unique_sources,
            "evidence_scopes": list(dict.fromkeys(item.evidence_scope for item in output.readings)),
            "focus": focus,
            "comparison_question": comparison_question,
        }
    )
    return store.create_artifact(
        project_id=project.id,
        artifact_type="reading_note",
        title=output.title,
        path_or_url=str(path),
        mime_type=READING_NOTE_MIME_TYPE,
        session_id=session_id or None,
        metadata=payload,
        provenance={
            "created_by": "paper_reader",
            "model": model_name,
            "session_id": session_id,
            "source_artifact_ids": unique_sources,
        },
    )


def save_critique_report(
    store: GmScienceStore,
    *,
    project_id: str,
    session_id: str,
    output: ReviewerOutput,
    target_artifact_id: str,
    trigger: str,
    review_focus: str,
    model_name: str,
) -> ArtifactRecord:
    """Persist a validated reviewer result as Markdown plus findings metadata."""

    project = _project(store, project_id)
    path = _artifact_path(project.workspace_path, "critiques", output.title)
    path.write_text(render_critique_report(output), encoding="utf-8")
    payload = output.model_dump(mode="json")
    payload["target_artifact_id"] = target_artifact_id
    payload["review_focus"] = review_focus
    return store.create_artifact(
        project_id=project.id,
        artifact_type="critique_report",
        title=output.title,
        path_or_url=str(path),
        mime_type=CRITIQUE_REPORT_MIME_TYPE,
        session_id=session_id or None,
        metadata=payload,
        provenance={
            "created_by": "research_reviewer",
            "model": model_name,
            "session_id": session_id,
            "target_artifact_id": target_artifact_id,
            "trigger": trigger,
        },
    )


def save_specialist_report(
    store: GmScienceStore,
    *,
    project_id: str,
    session_id: str,
    specialist_id: str,
    output: ConfiguredSpecialistOutput,
    objective: str,
    model_name: str,
    skills: tuple[str, ...],
    connectors: tuple[str, ...],
) -> ArtifactRecord:
    """Persist one configured specialist result with capability provenance."""

    project = _project(store, project_id)
    path = _artifact_path(project.workspace_path, "specialist-reports", output.title)
    path.write_text(render_specialist_report(output, specialist_id=specialist_id), encoding="utf-8")
    payload = output.model_dump(mode="json")
    payload.update({"specialist_id": specialist_id, "objective": objective})
    return store.create_artifact(
        project_id=project.id,
        artifact_type="specialist_report",
        title=output.title,
        path_or_url=str(path),
        mime_type=SPECIALIST_REPORT_MIME_TYPE,
        session_id=session_id or None,
        metadata=payload,
        provenance={
            "created_by": specialist_id,
            "model": model_name,
            "session_id": session_id,
            "assigned_skills": list(skills),
            "assigned_connectors": list(connectors),
        },
    )


def render_reading_note(output: PaperReaderOutput) -> str:
    """Render one structured reading result as reviewable Markdown."""

    lines = [f"# {output.title}", "", output.synthesis, ""]
    for reading in output.readings:
        lines.extend(
            [
                f"## {reading.title}",
                "",
                f"- Paper artifact: `{reading.paper_artifact_id}`",
                f"- Evidence scope: `{reading.evidence_scope}`",
                f"- Confidence: `{reading.confidence}`",
                "",
                "### Contribution",
                "",
                reading.contribution,
                "",
            ]
        )
        _append_list(lines, "Methods", reading.methods)
        _append_list(lines, "Results", reading.results)
        _append_list(lines, "Limitations", reading.limitations)
        _append_list(lines, "Reproducibility clues", reading.reproducibility_clues)
    _append_list(lines, "Agreements", output.agreements)
    _append_list(lines, "Conflicts", output.conflicts)
    _append_list(lines, "Open questions", output.open_questions)
    lines.extend(["## Confidence note", "", output.confidence_note, ""])
    return "\n".join(lines).rstrip() + "\n"


def render_critique_report(output: ReviewerOutput) -> str:
    """Render findings-first reviewer output as Markdown."""

    lines = [f"# {output.title}", "", f"**Verdict:** `{output.verdict}`", "", "## Findings", ""]
    if not output.findings:
        lines.extend(["No actionable findings.", ""])
    for index, finding in enumerate(output.findings, start=1):
        lines.extend(
            [
                f"### {index}. [{finding.severity}] {finding.category}",
                "",
                f"- Claim: {finding.claim}",
                f"- Issue: {finding.issue}",
                f"- Evidence: {finding.evidence}",
                f"- Recommendation: {finding.recommendation}",
                "",
            ]
        )
    _append_list(lines, "Strengths", output.strengths)
    _append_list(lines, "Unsupported claims", output.unsupported_claims)
    _append_list(lines, "Missing evidence", output.missing_evidence)
    _append_list(lines, "Evidence scopes", list(output.evidence_scopes))
    _append_list(lines, "Review limitations", output.review_limitations)
    lines.extend(["## Summary", "", output.summary, ""])
    return "\n".join(lines).rstrip() + "\n"


def render_specialist_report(output: ConfiguredSpecialistOutput, *, specialist_id: str) -> str:
    """Render one custom specialist result as reviewable Markdown."""

    lines = [
        f"# {output.title}",
        "",
        f"- Specialist: `{specialist_id}`",
        f"- Confidence: `{output.confidence}`",
        "",
        "## Findings",
        "",
    ]
    lines.extend(f"- {finding}" for finding in output.findings)
    if not output.findings:
        lines.append("None recorded.")
    lines.append("")
    _append_list(lines, "Recommendations", output.recommendations)
    _append_list(lines, "Limitations", output.limitations)
    lines.extend(["## Summary", "", output.summary, ""])
    return "\n".join(lines).rstrip() + "\n"


def artifact_payload(artifact: ArtifactRecord) -> dict[str, Any]:
    """Return a stable JSON projection for a specialist-created artifact."""

    return {
        "id": artifact.id,
        "project_id": artifact.project_id,
        "session_id": artifact.session_id,
        "type": artifact.type,
        "title": artifact.title,
        "path_or_url": artifact.path_or_url,
        "mime_type": artifact.mime_type,
        "metadata": dict(artifact.metadata),
        "provenance": dict(artifact.provenance),
        "created_at": artifact.created_at,
        "updated_at": artifact.updated_at,
    }


def _project(store: GmScienceStore, project_id: str):
    project = store.get_project(project_id)
    if project is None:
        raise ValueError(f"Project '{project_id}' was not found.")
    return project


def _artifact_path(workspace_path: str, category: str, title: str) -> Path:
    directory = Path(workspace_path).expanduser().resolve(strict=False) / "artifacts" / category
    directory.mkdir(parents=True, exist_ok=True)
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:48] or category
    return directory / f"{slug}-{uuid.uuid4().hex[:8]}.md"


def _append_list(lines: list[str], title: str, values: list[str]) -> None:
    lines.extend([f"## {title}", ""])
    lines.extend(f"- {value}" for value in values)
    if not values:
        lines.append("None recorded.")
    lines.append("")
