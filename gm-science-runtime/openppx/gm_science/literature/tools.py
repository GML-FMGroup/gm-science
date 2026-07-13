"""ADK-callable literature tools for gm-science projects."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..models import ArtifactRecord
from ..store import GmScienceStore
from .config import LiteratureConfig, load_literature_config, select_literature_sources
from .models import PaperRecord
from .service import LiteratureSearchService, SourceSearchStatus


PAPER_MIME_TYPE = "application/vnd.gm-science.paper+json"


def science_list_sources() -> dict[str, Any]:
    """List configured literature sources without returning email or credentials."""

    config = load_literature_config()
    return {"sources": config.public_source_statuses()}


def science_search(
    query: str,
    project_id: str,
    session_id: str = "",
    sources: list[str] | None = None,
    max_results: int = 10,
    save: bool = True,
) -> dict[str, Any]:
    """Search scholarly sources and optionally save reusable paper artifacts.

    Args:
        query: Scholarly search query.
        project_id: Current gm-science project identifier.
        session_id: Current conversation session identifier.
        sources: Optional subset of arxiv, pubmed, and openalex.
        max_results: Maximum number of merged papers to return, from 1 to 50.
        save: Whether to create or reuse paper artifacts in the project.
    """

    store = GmScienceStore()
    project = store.get_project(str(project_id or "").strip())
    if project is None:
        raise ValueError(f"Project '{project_id}' was not found.")
    limit = min(max(int(max_results), 1), 50)
    config = load_literature_config()
    per_source_limit = min(limit, config.max_results_per_source)
    selection = select_literature_sources(
        config,
        requested_sources=sources,
        enabled_connectors=project.enabled_connectors,
    )
    normalized_query = " ".join(str(query or "").split())
    if not normalized_query:
        raise ValueError("Literature query is required.")
    if selection.allowed:
        result = _build_search_service(config).search(
            normalized_query,
            sources=list(selection.allowed),
            max_results_per_source=per_source_limit,
        )
        ranked_items = result.items
        source_statuses = dict(result.source_statuses)
    else:
        ranked_items = ()
        source_statuses = {}
    for source in selection.project_disabled:
        source_statuses[source] = SourceSearchStatus(
            status="disabled",
            message=f"{source} is disabled for this Project.",
        )

    items: list[dict[str, Any]] = []
    for ranked in ranked_items[:limit]:
        artifact_id = ""
        if save:
            artifact = _save_paper_artifact(
                store,
                project_id=project.id,
                session_id=session_id,
                query=normalized_query,
                paper=ranked.paper,
                score=ranked.score,
            )
            artifact_id = artifact.id
        items.append(
            {
                "paper": ranked.paper.to_dict(),
                "score": ranked.score,
                "artifact_id": artifact_id,
            }
        )
    return {
        "query": normalized_query,
        "items": items,
        "source_statuses": {
            source: _source_status_payload(
                source_statuses.get(
                    source,
                    SourceSearchStatus(
                        status="unavailable",
                        message=f"{source} did not return a search status.",
                    ),
                )
            )
            for source in selection.requested
        },
    }


def science_register_review(
    project_id: str,
    session_id: str,
    title: str,
    path: str,
    paper_artifact_ids: list[str],
) -> dict[str, Any]:
    """Register a workspace report and citation links to project papers.

    Args:
        project_id: Current gm-science project identifier.
        session_id: Current conversation session identifier.
        title: Human-readable review title.
        path: Existing report path inside the project workspace.
        paper_artifact_ids: Paper artifact identifiers cited by the report.
    """

    store = GmScienceStore()
    project = store.get_project(str(project_id or "").strip())
    if project is None:
        raise ValueError(f"Project '{project_id}' was not found.")
    report_title = str(title or "").strip()
    if not report_title:
        raise ValueError("Review title is required.")
    report_path = _resolve_workspace_file(project.workspace_path, path)
    unique_paper_ids = tuple(dict.fromkeys(str(value).strip() for value in paper_artifact_ids if str(value).strip()))
    papers = [_project_paper(store, project.id, artifact_id) for artifact_id in unique_paper_ids]

    report = store.create_artifact(
        project_id=project.id,
        artifact_type="report",
        title=report_title,
        path_or_url=str(report_path),
        mime_type="text/markdown" if report_path.suffix.lower() in {".md", ".markdown"} else "application/octet-stream",
        session_id=str(session_id or "") or None,
        metadata={"paper_artifact_ids": list(unique_paper_ids)},
        provenance={"created_by": "science_register_review", "session_id": str(session_id or "")},
    )
    citations = [
        _save_citation(
            store,
            project_id=project.id,
            session_id=session_id,
            report=report,
            paper=paper,
        )
        for paper in papers
    ]
    report = store.update_artifact_metadata(
        report.id,
        {
            "paper_artifact_ids": list(unique_paper_ids),
            "citation_artifact_ids": [citation.id for citation in citations],
        },
    )
    return {
        "report": _artifact_payload(report),
        "citations": [_artifact_payload(citation) for citation in citations],
    }


def _build_search_service(config: LiteratureConfig) -> LiteratureSearchService:
    """Build a search service while keeping the public tool easy to test."""

    return LiteratureSearchService(config)


def _save_paper_artifact(
    store: GmScienceStore,
    *,
    project_id: str,
    session_id: str,
    query: str,
    paper: PaperRecord,
    score: float,
) -> ArtifactRecord:
    existing = store.find_paper_artifact(project_id, paper.canonical_id)
    if existing is not None:
        return existing
    metadata = paper.to_dict()
    metadata["fusion_score"] = score
    return store.create_artifact(
        project_id=project_id,
        artifact_type="paper",
        title=paper.title,
        path_or_url=paper.landing_page_url or paper.pdf_url,
        mime_type=PAPER_MIME_TYPE,
        session_id=str(session_id or "") or None,
        metadata=metadata,
        provenance={
            "created_by": "science_search",
            "query": query,
            "session_id": str(session_id or ""),
            "sources": list(paper.source_names),
        },
    )


def _resolve_workspace_file(workspace_path: str, requested_path: str) -> Path:
    workspace = Path(workspace_path).expanduser().resolve(strict=False)
    raw = Path(str(requested_path or "").strip()).expanduser()
    resolved = (raw if raw.is_absolute() else workspace / raw).resolve(strict=False)
    if not resolved.is_relative_to(workspace):
        raise ValueError("Review path must be inside the project workspace.")
    if not resolved.is_file():
        raise ValueError("Review path must reference an existing file inside the project workspace.")
    return resolved


def _project_paper(store: GmScienceStore, project_id: str, artifact_id: str) -> ArtifactRecord:
    artifact = store.get_artifact(artifact_id)
    if artifact is None:
        raise ValueError(f"Paper artifact '{artifact_id}' was not found.")
    if artifact.project_id != project_id or artifact.type != "paper":
        raise ValueError(f"Paper artifact '{artifact_id}' does not belong to project '{project_id}'.")
    return artifact


def _save_citation(
    store: GmScienceStore,
    *,
    project_id: str,
    session_id: str,
    report: ArtifactRecord,
    paper: ArtifactRecord,
) -> ArtifactRecord:
    existing = store.find_citation_artifact(project_id, report.id, paper.id)
    if existing is not None:
        return existing
    return store.create_artifact(
        project_id=project_id,
        artifact_type="citation",
        title=paper.title,
        path_or_url=paper.path_or_url,
        mime_type="application/vnd.citationstyles.csl+json",
        session_id=str(session_id or "") or None,
        metadata={
            "paper_artifact_id": paper.id,
            "report_artifact_id": report.id,
            "csl": _csl_payload(paper),
        },
        provenance={
            "created_by": "science_register_review",
            "session_id": str(session_id or ""),
            "paper_artifact_id": paper.id,
            "report_artifact_id": report.id,
        },
    )


def _csl_payload(paper: ArtifactRecord) -> dict[str, Any]:
    metadata = paper.metadata
    authors = metadata.get("authors") if isinstance(metadata.get("authors"), list) else []
    csl: dict[str, Any] = {
        "id": paper.id,
        "type": "article-journal",
        "title": paper.title,
        "author": [{"literal": str(author)} for author in authors if str(author).strip()],
    }
    year = metadata.get("year")
    if isinstance(year, int):
        csl["issued"] = {"date-parts": [[year]]}
    for source_key, csl_key in (
        ("doi", "DOI"),
        ("pmid", "PMID"),
        ("venue", "container-title"),
    ):
        value = metadata.get(source_key)
        if isinstance(value, str) and value:
            csl[csl_key] = value
    if paper.path_or_url:
        csl["URL"] = paper.path_or_url
    return csl


def _artifact_payload(artifact: ArtifactRecord) -> dict[str, Any]:
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


def _source_status_payload(status: SourceSearchStatus) -> dict[str, Any]:
    return {
        "status": status.status,
        "count": status.count,
        "cached": status.cached,
        "message": status.message,
        "status_code": status.status_code,
    }
