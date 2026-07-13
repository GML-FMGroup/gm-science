from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from openppx.gm_science.literature.cache import LiteratureCache
from openppx.gm_science.literature.config import LiteratureConfig, LiteratureSourceConfig
from openppx.gm_science.literature.http import LiteratureConnectorError
from openppx.gm_science.literature.models import PaperRecord
from openppx.gm_science.literature.service import LiteratureSearchService


class FakeConnector:
    def __init__(self, result: list[PaperRecord] | Exception) -> None:
        self.result = result
        self.calls: list[tuple[str, int]] = []

    def search(self, query: str, *, max_results: int) -> list[PaperRecord]:
        self.calls.append((query, max_results))
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


def _config() -> LiteratureConfig:
    return LiteratureConfig(
        default_sources=("arxiv", "pubmed", "openalex"),
        max_results_per_source=10,
        request_timeout_seconds=20,
        cache_ttl_seconds=3600,
        sources={
            "arxiv": LiteratureSourceConfig("arxiv", True, "https://arxiv.test", 3),
            "pubmed": LiteratureSourceConfig(
                "pubmed", True, "https://pubmed.test", 0.34, tool="gm-science", email="me@example.test"
            ),
            "openalex": LiteratureSourceConfig(
                "openalex", True, "https://openalex.test", api_key="openalex-secret"
            ),
        },
    )


def _paper(
    source: str,
    rank: int,
    title: str,
    *,
    doi: str = "",
    pmid: str = "",
    arxiv_id: str = "",
    abstract: str = "",
) -> PaperRecord:
    return PaperRecord.create(
        source_name=source,
        source_rank=rank,
        title=title,
        year=2024,
        doi=doi,
        pmid=pmid,
        arxiv_id=arxiv_id,
        abstract=abstract,
    )


def test_service_merges_cross_source_duplicates_and_uses_rrf(tmp_path: Path) -> None:
    shared_arxiv = _paper(
        "arxiv",
        1,
        "Reliable Protein Folding",
        doi="10.1000/folding",
        arxiv_id="2401.01234",
        abstract="Short abstract.",
    )
    arxiv_only = _paper("arxiv", 2, "Agent Benchmarks", arxiv_id="2401.09999")
    shared_pubmed = _paper(
        "pubmed",
        2,
        "Reliable Protein Folding",
        doi="https://doi.org/10.1000/FOLDING",
        pmid="12345678",
        abstract="A longer and more useful abstract for this paper.",
    )
    pubmed_first = _paper("pubmed", 1, "Clinical Agent Study", pmid="87654321")
    service = LiteratureSearchService(
        _config(),
        connectors={
            "arxiv": FakeConnector([shared_arxiv, arxiv_only]),
            "pubmed": FakeConnector([pubmed_first, shared_pubmed]),
            "openalex": FakeConnector([]),
        },
        cache=LiteratureCache(tmp_path / "cache", ttl_seconds=3600),
    )

    result = service.search("protein folding")

    assert [item.paper.title for item in result.items] == [
        "Reliable Protein Folding",
        "Clinical Agent Study",
        "Agent Benchmarks",
    ]
    shared = result.items[0].paper
    assert shared.source_names == ("arxiv", "pubmed")
    assert shared.source_ranks == {"arxiv": 1, "pubmed": 2}
    assert shared.pmid == "12345678"
    assert shared.abstract == "A longer and more useful abstract for this paper."
    assert result.source_statuses["arxiv"].status == "ok"


def test_service_uses_title_year_fallback_when_identifiers_are_missing(tmp_path: Path) -> None:
    first = _paper("arxiv", 1, "A Shared   Paper")
    second = _paper("pubmed", 1, "a shared paper")
    service = LiteratureSearchService(
        _config(),
        connectors={
            "arxiv": FakeConnector([first]),
            "pubmed": FakeConnector([second]),
            "openalex": FakeConnector([]),
        },
        cache=LiteratureCache(tmp_path / "cache", ttl_seconds=3600),
    )

    result = service.search("shared")

    assert len(result.items) == 1
    assert result.items[0].paper.source_names == ("arxiv", "pubmed")


def test_service_does_not_merge_same_title_year_with_different_first_authors(tmp_path: Path) -> None:
    first = PaperRecord.create(
        source_name="arxiv",
        source_rank=1,
        title="A Shared Paper",
        authors=["Ada Lovelace"],
        year=2024,
    )
    second = PaperRecord.create(
        source_name="pubmed",
        source_rank=1,
        title="A Shared Paper",
        authors=["Grace Hopper"],
        year=2024,
    )
    service = LiteratureSearchService(
        _config(),
        connectors={
            "arxiv": FakeConnector([first]),
            "pubmed": FakeConnector([second]),
            "openalex": FakeConnector([]),
        },
        cache=LiteratureCache(tmp_path / "cache", ttl_seconds=3600),
    )

    result = service.search("shared")

    assert len(result.items) == 2


def test_service_merges_existing_groups_when_a_record_bridges_identifiers(tmp_path: Path) -> None:
    doi_only = _paper("arxiv", 1, "Preprint title", doi="10.1000/bridge")
    pmid_only = _paper("pubmed", 1, "Journal title", pmid="12345678")
    bridge = _paper(
        "openalex",
        1,
        "Indexed title",
        doi="10.1000/bridge",
        pmid="12345678",
    )
    service = LiteratureSearchService(
        _config(),
        connectors={
            "arxiv": FakeConnector([doi_only]),
            "pubmed": FakeConnector([pmid_only]),
            "openalex": FakeConnector([bridge]),
        },
        cache=LiteratureCache(tmp_path / "cache", ttl_seconds=3600),
    )

    result = service.search("identifier bridge")

    assert len(result.items) == 1
    assert result.items[0].paper.source_names == ("arxiv", "openalex", "pubmed")
    assert result.items[0].paper.doi == "10.1000/bridge"
    assert result.items[0].paper.pmid == "12345678"


def test_service_isolates_failures_and_skips_unavailable_sources(tmp_path: Path) -> None:
    config = _config()
    config = replace(
        config,
        sources={
            **config.sources,
            "pubmed": replace(config.sources["pubmed"], email=""),
            "openalex": replace(config.sources["openalex"], enabled=False),
        },
    )
    arxiv = FakeConnector(LiteratureConnectorError("arxiv", "rate_limited", "safe error", status_code=429))
    pubmed = FakeConnector([])
    openalex = FakeConnector([])
    service = LiteratureSearchService(
        config,
        connectors={"arxiv": arxiv, "pubmed": pubmed, "openalex": openalex},
        cache=LiteratureCache(tmp_path / "cache", ttl_seconds=3600),
    )

    result = service.search("protein folding")

    assert result.items == ()
    assert result.source_statuses["arxiv"].status == "rate_limited"
    assert result.source_statuses["pubmed"].status == "needs_configuration"
    assert result.source_statuses["openalex"].status == "disabled"
    assert pubmed.calls == []
    assert openalex.calls == []


def test_service_reuses_cache_without_calling_connector(tmp_path: Path) -> None:
    cache = LiteratureCache(tmp_path / "cache", ttl_seconds=3600)
    cached = _paper("arxiv", 1, "Cached Result", arxiv_id="2401.01010")
    cache.put("arxiv", "protein folding", 3, [cached])
    arxiv = FakeConnector([_paper("arxiv", 1, "Network Result")])
    service = LiteratureSearchService(
        _config(),
        connectors={"arxiv": arxiv},
        cache=cache,
    )

    result = service.search("protein folding", sources=["arxiv"], max_results_per_source=3)

    assert result.items[0].paper.title == "Cached Result"
    assert result.source_statuses["arxiv"].cached is True
    assert arxiv.calls == []


def test_service_rejects_empty_query_and_unknown_sources(tmp_path: Path) -> None:
    service = LiteratureSearchService(
        _config(),
        connectors={},
        cache=LiteratureCache(tmp_path / "cache", ttl_seconds=3600),
    )

    with pytest.raises(ValueError, match="Literature query is required"):
        service.search(" ")
    with pytest.raises(ValueError, match="unknown"):
        service.search("protein folding", sources=["unknown"])
