"""OpenAlex works API connector."""

from __future__ import annotations

from typing import Any, Mapping

import httpx

from .config import LiteratureSourceConfig
from .http import LiteratureConnectorError, require_source, safe_get
from .models import PaperRecord
from .rate_limit import SourceRateLimiter


OPENALEX_SELECT = ",".join(
    (
        "id",
        "doi",
        "display_name",
        "publication_year",
        "publication_date",
        "cited_by_count",
        "is_retracted",
        "ids",
        "abstract_inverted_index",
        "authorships",
        "primary_location",
    )
)


class OpenAlexConnector:
    """Search OpenAlex works and normalize result metadata."""

    def __init__(
        self,
        config: LiteratureSourceConfig,
        *,
        client: httpx.Client | None = None,
        timeout_seconds: float = 20.0,
        rate_limiter: SourceRateLimiter | None = None,
    ) -> None:
        self.config = config
        self.client = client or httpx.Client()
        self.timeout_seconds = timeout_seconds
        self.rate_limiter = rate_limiter or SourceRateLimiter()

    def search(self, query: str, *, max_results: int) -> list[PaperRecord]:
        """Search OpenAlex using its full-text works search."""

        require_source("openalex", enabled=self.config.enabled, api_base=self.config.api_base)
        if not self.config.api_key:
            raise LiteratureConnectorError(
                "openalex",
                "needs_configuration",
                "Set science.literature.openalex.apiKey.",
            )
        self.rate_limiter.wait("openalex", self.config.min_interval_seconds)
        response = safe_get(
            self.client,
            f"{self.config.api_base}/works",
            source="openalex",
            params={
                "search": query.strip(),
                "per_page": max_results,
                "api_key": self.config.api_key,
                "select": OPENALEX_SELECT,
            },
            timeout_seconds=self.timeout_seconds,
        )
        try:
            results = response.json().get("results", [])
        except (ValueError, AttributeError) as exc:
            raise LiteratureConnectorError("openalex", "parse_error", "openalex returned invalid JSON.") from exc
        if not isinstance(results, list):
            raise LiteratureConnectorError("openalex", "parse_error", "openalex returned invalid results.")
        return [_parse_work(work, rank) for rank, work in enumerate(results, start=1) if isinstance(work, Mapping)]


def _parse_work(work: Mapping[str, Any], rank: int) -> PaperRecord:
    identifiers = work.get("ids") if isinstance(work.get("ids"), Mapping) else {}
    location = work.get("primary_location") if isinstance(work.get("primary_location"), Mapping) else {}
    source = location.get("source") if isinstance(location.get("source"), Mapping) else {}
    authorships = work.get("authorships") if isinstance(work.get("authorships"), list) else []
    authors = []
    for authorship in authorships:
        if not isinstance(authorship, Mapping) or not isinstance(authorship.get("author"), Mapping):
            continue
        authors.append(str(authorship["author"].get("display_name") or ""))
    return PaperRecord.create(
        source_name="openalex",
        source_rank=rank,
        title=str(work.get("display_name") or ""),
        abstract=_abstract(work.get("abstract_inverted_index")),
        authors=authors,
        published_date=str(work.get("publication_date") or ""),
        year=_integer(work.get("publication_year")),
        venue=str(source.get("display_name") or ""),
        doi=str(work.get("doi") or identifiers.get("doi") or ""),
        pmid=str(identifiers.get("pmid") or ""),
        openalex_id=str(work.get("id") or identifiers.get("openalex") or ""),
        landing_page_url=str(location.get("landing_page_url") or ""),
        pdf_url=str(location.get("pdf_url") or ""),
        citation_count=_integer(work.get("cited_by_count")),
        is_retracted=bool(work.get("is_retracted", False)),
        raw_identifiers={str(key): str(value) for key, value in identifiers.items()},
    )


def _abstract(value: Any) -> str:
    if not isinstance(value, Mapping):
        return ""
    tokens: list[tuple[int, str]] = []
    for word, positions in value.items():
        if not isinstance(positions, list):
            continue
        for position in positions:
            if isinstance(position, int):
                tokens.append((position, str(word)))
    return " ".join(word for _, word in sorted(tokens))


def _integer(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
