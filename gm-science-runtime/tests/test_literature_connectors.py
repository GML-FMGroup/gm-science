from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from openppx.gm_science.literature.arxiv import ArxivConnector
from openppx.gm_science.literature.config import LiteratureSourceConfig
from openppx.gm_science.literature.http import LiteratureConnectorError
from openppx.gm_science.literature.models import PaperRecord
from openppx.gm_science.literature.openalex import OpenAlexConnector
from openppx.gm_science.literature.pubmed import PubMedConnector

FIXTURES = Path(__file__).parent / "fixtures" / "literature"


class RecordingLimiter:
    def __init__(self) -> None:
        self.calls: list[tuple[str, float]] = []

    def wait(self, source: str, min_interval_seconds: float) -> None:
        self.calls.append((source, min_interval_seconds))


def test_paper_record_normalizes_stable_identifiers() -> None:
    paper = PaperRecord.create(
        source_name="arxiv",
        source_rank=1,
        title="  Reliable   Protein Folding  ",
        authors=["Ada Lovelace"],
        year=2024,
        doi="https://doi.org/10.1000/FOLDING.2024.1",
        arxiv_id="2401.01234v3",
    )

    assert paper.canonical_id == "doi:10.1000/folding.2024.1"
    assert paper.title == "Reliable Protein Folding"
    assert paper.doi == "10.1000/folding.2024.1"
    assert paper.arxiv_id == "2401.01234"
    assert paper.source_names == ("arxiv",)
    assert paper.source_ranks == {"arxiv": 1}


def test_arxiv_connector_builds_query_and_parses_atom_fixture() -> None:
    xml = (FIXTURES / "arxiv-search.xml").read_text(encoding="utf-8")
    limiter = RecordingLimiter()

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["search_query"] == "all:protein folding"
        assert request.url.params["max_results"] == "3"
        assert request.url.params["sortBy"] == "relevance"
        assert request.headers["User-Agent"].startswith("gm-science/")
        return httpx.Response(200, text=xml)

    connector = ArxivConnector(
        LiteratureSourceConfig(
            name="arxiv",
            enabled=True,
            api_base="https://arxiv.test/api/query",
            min_interval_seconds=3,
        ),
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        timeout_seconds=5,
        rate_limiter=limiter,
    )

    papers = connector.search("protein folding", max_results=3)

    assert len(papers) == 1
    paper = papers[0]
    assert paper.canonical_id == "doi:10.1000/folding.2024.1"
    assert paper.arxiv_id == "2401.01234"
    assert paper.authors == ("Ada Lovelace", "Grace Hopper")
    assert paper.published_date == "2024-01-03"
    assert paper.venue == "Journal of Reliable Science 12 (2024)"
    assert paper.pdf_url == "https://arxiv.org/pdf/2401.01234v2"
    assert limiter.calls == [("arxiv", 3)]


def test_pubmed_connector_searches_then_fetches_xml() -> None:
    search_payload = (FIXTURES / "pubmed-search.json").read_text(encoding="utf-8")
    fetch_payload = (FIXTURES / "pubmed-fetch.xml").read_text(encoding="utf-8")
    requests: list[str] = []
    limiter = RecordingLimiter()

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request.url.path)
        assert request.url.params["tool"] == "gm-science-test"
        assert request.url.params["email"] == "researcher@example.test"
        assert request.url.params["api_key"] == "pubmed-secret"
        if request.url.path.endswith("/esearch.fcgi"):
            assert request.url.params["db"] == "pubmed"
            assert request.url.params["term"] == "protein folding"
            assert request.url.params["retmax"] == "5"
            return httpx.Response(200, text=search_payload)
        assert request.url.path.endswith("/efetch.fcgi")
        assert request.url.params["id"] == "12345678"
        return httpx.Response(200, text=fetch_payload)

    connector = PubMedConnector(
        LiteratureSourceConfig(
            name="pubmed",
            enabled=True,
            api_base="https://pubmed.test/eutils",
            min_interval_seconds=0.34,
            tool="gm-science-test",
            email="researcher@example.test",
            api_key="pubmed-secret",
        ),
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        timeout_seconds=5,
        rate_limiter=limiter,
    )

    papers = connector.search("protein folding", max_results=5)

    assert requests == ["/eutils/esearch.fcgi", "/eutils/efetch.fcgi"]
    assert len(papers) == 1
    paper = papers[0]
    assert paper.pmid == "12345678"
    assert paper.doi == "10.1000/folding.2024.1"
    assert paper.authors == ("Ada Lovelace", "Reliable Science Consortium")
    assert paper.abstract == "BACKGROUND: We evaluate a reproducible RESULTS: folding workflow."
    assert paper.landing_page_url == "https://pubmed.ncbi.nlm.nih.gov/12345678/"
    assert limiter.calls == [("pubmed", 0.34), ("pubmed", 0.34)]


def test_openalex_connector_uses_required_key_and_parses_works() -> None:
    payload = (FIXTURES / "openalex-works.json").read_text(encoding="utf-8")
    limiter = RecordingLimiter()

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/works"
        assert request.url.params["search"] == "protein folding"
        assert request.url.params["per_page"] == "4"
        assert request.url.params["api_key"] == "openalex-secret"
        assert "abstract_inverted_index" in request.url.params["select"]
        return httpx.Response(200, text=payload)

    connector = OpenAlexConnector(
        LiteratureSourceConfig(
            name="openalex",
            enabled=True,
            api_base="https://openalex.test",
            api_key="openalex-secret",
        ),
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        timeout_seconds=5,
        rate_limiter=limiter,
    )

    papers = connector.search("protein folding", max_results=4)

    assert len(papers) == 1
    paper = papers[0]
    assert paper.openalex_id == "W1234567890"
    assert paper.pmid == "12345678"
    assert paper.abstract == "We evaluate a reproducible folding workflow."
    assert paper.citation_count == 17
    assert paper.venue == "Journal of Reliable Science"
    assert limiter.calls == [("openalex", 0.0)]


@pytest.mark.parametrize("status_code,kind", [(429, "rate_limited"), (503, "http_error")])
def test_connector_http_errors_have_stable_safe_kinds(status_code: int, kind: str) -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code, text="secret upstream response")

    connector = OpenAlexConnector(
        LiteratureSourceConfig(
            name="openalex",
            enabled=True,
            api_base="https://openalex.test",
            api_key="openalex-secret",
        ),
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        timeout_seconds=5,
    )

    with pytest.raises(LiteratureConnectorError) as caught:
        connector.search("protein folding", max_results=2)

    assert caught.value.kind == kind
    assert caught.value.status_code == status_code
    assert "secret upstream response" not in str(caught.value)
    assert "openalex-secret" not in str(caught.value)


def test_connector_network_policy_blocks_before_transport(monkeypatch) -> None:
    requested = False

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal requested
        requested = True
        return httpx.Response(200, json={"results": []})

    monkeypatch.setenv(
        "GM_SCIENCE_NETWORK_POLICY_JSON",
        json.dumps({
            "enabled": True,
            "enforce_allowlist": True,
            "allow_private_networks": False,
            "allowed_domains": ["allowed.example.test"],
        }),
    )
    connector = OpenAlexConnector(
        LiteratureSourceConfig(
            name="openalex",
            enabled=True,
            api_base="https://blocked.example.test",
            api_key="openalex-secret",
        ),
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        timeout_seconds=5,
    )

    with pytest.raises(LiteratureConnectorError) as caught:
        connector.search("protein folding", max_results=2)

    assert caught.value.kind == "network_blocked"
    assert requested is False


def test_openalex_rejects_missing_key_without_network_request() -> None:
    requested = False

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal requested
        requested = True
        return httpx.Response(200, json={"results": []})

    connector = OpenAlexConnector(
        LiteratureSourceConfig(name="openalex", enabled=True, api_base="https://openalex.test"),
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        timeout_seconds=5,
    )

    with pytest.raises(LiteratureConnectorError) as caught:
        connector.search("protein folding", max_results=2)

    assert caught.value.kind == "needs_configuration"
    assert requested is False
