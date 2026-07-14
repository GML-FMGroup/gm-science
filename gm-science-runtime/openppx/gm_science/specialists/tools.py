"""Read-only evidence tools available to gm-science specialists."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from ..models import ArtifactRecord, ProjectRecord
from ..store import GmScienceStore
from .config import load_specialist_config

_TEXT_SUFFIXES = {".json", ".md", ".markdown", ".txt"}
_PAPER_METADATA_KEYS = (
    "canonical_id",
    "doi",
    "pmid",
    "arxiv_id",
    "openalex_id",
    "authors",
    "year",
    "publication_date",
    "venue",
    "source_names",
    "citation_count",
)
_REVIEW_METADATA_KEYS = (
    "paper_artifact_ids",
    "citation_artifact_ids",
    "source_artifact_ids",
    "evidence_scopes",
    "focus",
    "comparison_question",
    "confidence_note",
)


def science_read_paper_bundle(project_id: str, paper_artifact_ids: list[str]) -> dict[str, Any]:
    """Read saved paper metadata and bounded local text for one Project."""

    store = GmScienceStore()
    project = _project(store, project_id)
    max_papers, max_source_chars = _paper_reader_limits()
    artifact_ids = _artifact_ids(paper_artifact_ids)
    if len(artifact_ids) > max_papers:
        raise ValueError(f"paper-reader accepts at most {max_papers} papers per call.")

    remaining = max_source_chars
    papers: list[dict[str, Any]] = []
    for artifact_id in artifact_ids:
        artifact = _project_artifact(store, project.id, artifact_id, allowed_types={"paper"})
        evidence = _paper_evidence(project, artifact, remaining)
        consumed = evidence["source_chars"]
        remaining = max(0, remaining - consumed)
        papers.append(evidence)
    return {
        "project_id": project.id,
        "papers": papers,
        "total_source_chars": sum(item["source_chars"] for item in papers),
        "max_source_chars": max_source_chars,
    }


def science_read_review_bundle(project_id: str, target_artifact_id: str) -> dict[str, Any]:
    """Read one report or reading note through the reviewer evidence boundary."""

    store = GmScienceStore()
    project = _project(store, project_id)
    artifact = _project_artifact(
        store,
        project.id,
        target_artifact_id,
        allowed_types={"report", "reading_note"},
        type_error="Reviewer target must be a report or reading_note artifact.",
    )
    max_source_chars = load_specialist_config().reviewer.max_source_chars
    raw_content, target_original_chars = _required_workspace_text(
        project,
        artifact.path_or_url,
        max_source_chars,
    )
    content = raw_content[:max_source_chars]
    remaining = max(0, max_source_chars - len(content))
    linked_ids = _artifact_ids_or_empty(
        artifact.metadata.get(
            "paper_artifact_ids" if artifact.type == "report" else "source_artifact_ids"
        )
    )
    papers: list[dict[str, Any]] = []
    for paper_id in linked_ids:
        paper = _project_artifact(store, project.id, paper_id, allowed_types={"paper"})
        evidence = _paper_evidence(project, paper, remaining)
        remaining = max(0, remaining - evidence["source_chars"])
        papers.append(evidence)
    truncated = target_original_chars > len(content) or any(item["truncated"] for item in papers)
    return {
        "project_id": project.id,
        "artifact_id": artifact.id,
        "artifact_type": artifact.type,
        "title": artifact.title,
        "content": content,
        "metadata": {
            key: artifact.metadata[key]
            for key in _REVIEW_METADATA_KEYS
            if key in artifact.metadata
        },
        "papers": papers,
        "source_chars": len(content),
        "total_source_chars": len(content) + sum(item["source_chars"] for item in papers),
        "max_source_chars": max_source_chars,
        "truncated": truncated,
    }


def validate_specialist_artifacts(
    store: GmScienceStore,
    *,
    project_id: str,
    artifact_ids: list[str],
    allowed_types: set[str],
) -> list[ArtifactRecord]:
    """Validate artifact ownership and types before a child agent is started."""

    return [
        _project_artifact(store, project_id, artifact_id, allowed_types=allowed_types)
        for artifact_id in _artifact_ids(artifact_ids)
    ]


def _paper_reader_limits() -> tuple[int, int]:
    config = load_specialist_config().paper_reader
    return config.max_papers, config.max_source_chars


def _project(store: GmScienceStore, project_id: str) -> ProjectRecord:
    project = store.get_project(str(project_id or "").strip())
    if project is None:
        raise ValueError(f"Project '{project_id}' was not found.")
    return project


def _artifact_ids(values: list[str]) -> list[str]:
    artifact_ids = list(dict.fromkeys(str(value or "").strip() for value in values if str(value or "").strip()))
    if not artifact_ids:
        raise ValueError("At least one artifact is required.")
    return artifact_ids


def _artifact_ids_or_empty(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return list(dict.fromkeys(str(item).strip() for item in value if str(item).strip()))


def _paper_evidence(
    project: ProjectRecord,
    artifact: ArtifactRecord,
    limit: int,
) -> dict[str, Any]:
    """Build one bounded paper evidence record without duplicating its abstract."""

    local_text = _optional_workspace_text(project, artifact.path_or_url, limit)
    abstract = str(artifact.metadata.get("abstract") or "").strip()
    if local_text is None:
        source_text = abstract[:limit]
        evidence_scope = "metadata_abstract"
        original_chars = len(abstract)
    else:
        source_text, original_chars = local_text
        evidence_scope = "local_text"
    return {
        "artifact_id": artifact.id,
        "title": artifact.title,
        "evidence_scope": evidence_scope,
        "metadata": {
            key: artifact.metadata[key]
            for key in _PAPER_METADATA_KEYS
            if key in artifact.metadata
        },
        "source_text": source_text,
        "source_chars": len(source_text),
        "truncated": original_chars > len(source_text),
    }


def _project_artifact(
    store: GmScienceStore,
    project_id: str,
    artifact_id: str,
    *,
    allowed_types: set[str],
    type_error: str = "Artifact type is not supported by this specialist.",
) -> ArtifactRecord:
    artifact = store.get_artifact(artifact_id)
    if artifact is None:
        raise ValueError(f"Artifact '{artifact_id}' was not found.")
    if artifact.project_id != project_id:
        raise ValueError(f"Artifact '{artifact_id}' does not belong to project '{project_id}'.")
    if artifact.type not in allowed_types:
        raise ValueError(type_error)
    return artifact


def _optional_workspace_text(
    project: ProjectRecord,
    path_or_url: str,
    limit: int,
) -> tuple[str, int] | None:
    raw = str(path_or_url or "").strip()
    if not raw or _is_web_url(raw):
        return None
    path = Path(raw).expanduser()
    if path.suffix.lower() not in _TEXT_SUFFIXES:
        return None
    return _workspace_text(project, path, limit)


def _required_workspace_text(
    project: ProjectRecord,
    path_or_url: str,
    limit: int,
) -> tuple[str, int]:
    raw = str(path_or_url or "").strip()
    if not raw or _is_web_url(raw):
        raise ValueError("Review target must reference a local Project workspace text file.")
    path = Path(raw).expanduser()
    if path.suffix.lower() not in _TEXT_SUFFIXES:
        raise ValueError("Review target must be Markdown, text, or JSON.")
    return _workspace_text(project, path, limit)


def _workspace_text(project: ProjectRecord, path: Path, limit: int) -> tuple[str, int]:
    workspace = Path(project.workspace_path).expanduser().resolve(strict=False)
    resolved = (path if path.is_absolute() else workspace / path).resolve(strict=False)
    if not resolved.is_relative_to(workspace):
        raise ValueError("Specialist source path must be inside the Project workspace.")
    if not resolved.is_file():
        raise ValueError("Specialist source path must reference an existing file.")
    text = resolved.read_text(encoding="utf-8")
    return text[: max(0, limit)], len(text)


def _is_web_url(value: str) -> bool:
    return urlparse(value).scheme.lower() in {"http", "https"}
