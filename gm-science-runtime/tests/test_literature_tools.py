from __future__ import annotations

from pathlib import Path

import pytest

from openppx.gm_science.literature.config import LiteratureConfig, LiteratureSourceConfig
from openppx.gm_science.literature.models import PaperRecord
from openppx.gm_science.literature.service import (
    LiteratureSearchResult,
    RankedPaper,
    SourceSearchStatus,
)
from openppx.gm_science.literature import tools
from openppx.gm_science.store import GmScienceStore


def _config() -> LiteratureConfig:
    return LiteratureConfig(
        default_sources=("arxiv", "pubmed", "openalex"),
        max_results_per_source=10,
        request_timeout_seconds=20,
        cache_ttl_seconds=3600,
        sources={
            "arxiv": LiteratureSourceConfig("arxiv", True, "https://arxiv.test", 3),
            "pubmed": LiteratureSourceConfig("pubmed", True, "https://pubmed.test", email="me@example.test"),
            "openalex": LiteratureSourceConfig("openalex", True, "https://openalex.test", api_key="secret"),
        },
    )


def _search_result() -> LiteratureSearchResult:
    paper = PaperRecord.create(
        source_name="arxiv",
        source_rank=1,
        title="Reliable Protein Folding",
        abstract="A reproducible workflow.",
        authors=["Ada Lovelace"],
        year=2024,
        doi="10.1000/folding",
        landing_page_url="https://doi.org/10.1000/folding",
    )
    return LiteratureSearchResult(
        query="protein folding",
        items=(RankedPaper(paper=paper, score=0.016),),
        source_statuses={"arxiv": SourceSearchStatus(status="ok", count=1)},
    )


class FakeSearchService:
    def __init__(self, result: LiteratureSearchResult) -> None:
        self.result = result
        self.calls: list[dict[str, object]] = []

    def search(self, query: str, *, sources: list[str] | None, max_results_per_source: int) -> LiteratureSearchResult:
        self.calls.append(
            {"query": query, "sources": sources, "max_results_per_source": max_results_per_source}
        )
        return self.result


def test_science_list_sources_never_exposes_identity_or_keys(monkeypatch) -> None:
    monkeypatch.setattr(tools, "load_literature_config", lambda: _config())

    result = tools.science_list_sources()

    assert result["sources"]["openalex"]["status"] == "ok"
    assert "secret" not in str(result)
    assert "me@example.test" not in str(result)


def test_science_search_saves_and_reuses_project_paper_artifacts(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("GM_SCIENCE_DATA_DIR", str(tmp_path))
    store = GmScienceStore(tmp_path)
    project = store.create_project(name="Review", description="", agent_context="")
    service = FakeSearchService(_search_result())
    monkeypatch.setattr(tools, "load_literature_config", lambda: _config())
    monkeypatch.setattr(tools, "_build_search_service", lambda _config: service)

    first = tools.science_search(
        "protein folding",
        project.id,
        session_id="session-1",
        sources=["arxiv"],
        max_results=20,
    )
    second = tools.science_search("protein folding", project.id, session_id="session-2")

    assert first["items"][0]["artifact_id"].startswith("art_")
    assert second["items"][0]["artifact_id"] == first["items"][0]["artifact_id"]
    assert len(store.list_artifacts(project.id)) == 1
    artifact = store.list_artifacts(project.id)[0]
    assert artifact.type == "paper"
    assert artifact.metadata["canonical_id"] == "doi:10.1000/folding"
    assert artifact.provenance["created_by"] == "science_search"
    assert service.calls[0]["max_results_per_source"] == 10
    assert len(first["items"]) == 1


def test_science_search_can_skip_saving(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("GM_SCIENCE_DATA_DIR", str(tmp_path))
    store = GmScienceStore(tmp_path)
    project = store.create_project(name="Review", description="", agent_context="")
    monkeypatch.setattr(tools, "load_literature_config", lambda: _config())
    monkeypatch.setattr(tools, "_build_search_service", lambda _config: FakeSearchService(_search_result()))

    result = tools.science_search("protein folding", project.id, save=False)

    assert result["items"][0]["artifact_id"] == ""
    assert store.list_artifacts(project.id) == []


def test_science_search_applies_project_connector_policy(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("GM_SCIENCE_DATA_DIR", str(tmp_path))
    store = GmScienceStore(tmp_path)
    project = store.create_project(
        name="Review",
        description="",
        agent_context="",
        enabled_connectors=["arxiv"],
    )
    service = FakeSearchService(_search_result())
    monkeypatch.setattr(tools, "load_literature_config", lambda: _config())
    monkeypatch.setattr(tools, "_build_search_service", lambda _config: service)

    result = tools.science_search("protein folding", project.id, save=False)

    assert service.calls[0]["sources"] == ["arxiv"]
    assert result["source_statuses"]["arxiv"]["status"] == "ok"
    assert result["source_statuses"]["pubmed"]["status"] == "disabled"
    assert result["source_statuses"]["openalex"]["status"] == "disabled"


def test_science_search_returns_disabled_status_when_project_allows_no_requested_source(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("GM_SCIENCE_DATA_DIR", str(tmp_path))
    store = GmScienceStore(tmp_path)
    project = store.create_project(
        name="Review",
        description="",
        agent_context="",
        enabled_connectors=["pubmed"],
    )
    monkeypatch.setattr(tools, "load_literature_config", lambda: _config())
    monkeypatch.setattr(
        tools,
        "_build_search_service",
        lambda _config: pytest.fail("Search service should not be created."),
    )

    result = tools.science_search("protein folding", project.id, sources=["arxiv"], save=False)

    assert result["items"] == []
    assert result["source_statuses"]["arxiv"]["status"] == "disabled"


def test_science_register_review_creates_report_and_reuses_citations(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("GM_SCIENCE_DATA_DIR", str(tmp_path))
    store = GmScienceStore(tmp_path)
    project = store.create_project(name="Review", description="", agent_context="")
    report_path = Path(project.workspace_path) / "reviews" / "folding.md"
    report_path.parent.mkdir(parents=True)
    report_path.write_text("# Review", encoding="utf-8")
    paper = store.create_artifact(
        project_id=project.id,
        artifact_type="paper",
        title="Reliable Protein Folding",
        path_or_url="https://doi.org/10.1000/folding",
        metadata={"canonical_id": "doi:10.1000/folding"},
    )

    result = tools.science_register_review(
        project.id,
        "session-1",
        "Folding review",
        "reviews/folding.md",
        [paper.id, paper.id],
    )

    assert result["report"]["type"] == "report"
    assert result["report"]["metadata"]["citation_artifact_ids"] == [result["citations"][0]["id"]]
    assert len(result["citations"]) == 1
    artifacts = store.list_artifacts(project.id)
    assert [artifact.type for artifact in artifacts] == ["paper", "report", "citation"]
    citation = artifacts[-1]
    assert citation.mime_type == "application/vnd.citationstyles.csl+json"
    assert citation.metadata["paper_artifact_id"] == paper.id
    assert citation.metadata["report_artifact_id"] == result["report"]["id"]
    assert citation.metadata["csl"]["title"] == "Reliable Protein Folding"


def test_science_register_review_rejects_outside_path_and_cross_project_paper(
    tmp_path: Path, monkeypatch
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
    )
    inside = Path(project.workspace_path) / "review.md"
    inside.write_text("# Review", encoding="utf-8")
    outside = tmp_path / "outside.md"
    outside.write_text("# Outside", encoding="utf-8")

    with pytest.raises(ValueError, match="workspace"):
        tools.science_register_review(project.id, "session-1", "Review", str(outside), [])
    with pytest.raises(ValueError, match="does not belong"):
        tools.science_register_review(project.id, "session-1", "Review", str(inside), [other_paper.id])

    assert store.list_artifacts(project.id) == []
