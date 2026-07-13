"""Multi-source literature search orchestration and result fusion."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Mapping, Protocol, Sequence

from ..paths import get_gm_science_data_dir
from .arxiv import ArxivConnector
from .cache import LiteratureCache
from .config import LiteratureConfig, SUPPORTED_LITERATURE_SOURCES
from .http import LiteratureConnectorError
from .models import PaperRecord
from .openalex import OpenAlexConnector
from .pubmed import PubMedConnector
from .rate_limit import SourceRateLimiter


RRF_K = 60


class LiteratureConnector(Protocol):
    """Minimal interface implemented by each native literature connector."""

    def search(self, query: str, *, max_results: int) -> list[PaperRecord]: ...


@dataclass(frozen=True, slots=True)
class SourceSearchStatus:
    """Public outcome of one source in a multi-source search."""

    status: str
    count: int = 0
    cached: bool = False
    message: str = ""
    status_code: int | None = None


@dataclass(frozen=True, slots=True)
class RankedPaper:
    """A merged paper and its Reciprocal Rank Fusion score."""

    paper: PaperRecord
    score: float


@dataclass(frozen=True, slots=True)
class LiteratureSearchResult:
    """Merged search results and per-source execution status."""

    query: str
    items: tuple[RankedPaper, ...]
    source_statuses: Mapping[str, SourceSearchStatus]

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-compatible tool result."""

        return {
            "query": self.query,
            "items": [{"paper": item.paper.to_dict(), "score": item.score} for item in self.items],
            "source_statuses": {
                source: {
                    "status": status.status,
                    "count": status.count,
                    "cached": status.cached,
                    "message": status.message,
                    "status_code": status.status_code,
                }
                for source, status in self.source_statuses.items()
            },
        }


class LiteratureSearchService:
    """Search configured sources sequentially and merge their paper records."""

    def __init__(
        self,
        config: LiteratureConfig,
        *,
        connectors: Mapping[str, LiteratureConnector] | None = None,
        cache: LiteratureCache | None = None,
        rate_limiter: SourceRateLimiter | None = None,
        cache_dir: Path | str | None = None,
    ) -> None:
        self.config = config
        self.rate_limiter = rate_limiter or SourceRateLimiter()
        self.connectors = dict(connectors) if connectors is not None else self._default_connectors()
        resolved_cache_dir = Path(cache_dir) if cache_dir is not None else get_gm_science_data_dir() / "cache" / "literature"
        self.cache = cache or LiteratureCache(resolved_cache_dir, ttl_seconds=config.cache_ttl_seconds)

    def search(
        self,
        query: str,
        *,
        sources: Sequence[str] | None = None,
        max_results_per_source: int | None = None,
    ) -> LiteratureSearchResult:
        """Execute configured searches with cache, pacing, and error isolation."""

        normalized_query = " ".join(str(query or "").split())
        if not normalized_query:
            raise ValueError("Literature query is required.")
        selected_sources = _normalize_sources(sources or self.config.default_sources)
        maximum = min(max(int(max_results_per_source or self.config.max_results_per_source), 1), 25)
        records_by_source: dict[str, list[PaperRecord]] = {}
        statuses: dict[str, SourceSearchStatus] = {}

        for source in selected_sources:
            source_config = self.config.sources[source]
            config_status, config_message = source_config.status()
            if config_status != "ok":
                statuses[source] = SourceSearchStatus(status=config_status, message=config_message)
                continue
            cached = self.cache.get(source, normalized_query, maximum)
            if cached is not None:
                records_by_source[source] = cached
                statuses[source] = SourceSearchStatus(status="ok", count=len(cached), cached=True)
                continue
            connector = self.connectors.get(source)
            if connector is None:
                statuses[source] = SourceSearchStatus(status="unavailable", message=f"{source} connector is unavailable.")
                continue
            try:
                records = connector.search(normalized_query, max_results=maximum)
            except LiteratureConnectorError as exc:
                statuses[source] = SourceSearchStatus(
                    status=exc.kind,
                    message=str(exc),
                    status_code=exc.status_code,
                )
                continue
            except Exception:
                statuses[source] = SourceSearchStatus(
                    status="internal_error",
                    message=f"{source} connector failed unexpectedly.",
                )
                continue
            records_by_source[source] = records
            statuses[source] = SourceSearchStatus(status="ok", count=len(records))
            self.cache.put(source, normalized_query, maximum, records)

        items = _merge_and_rank(records_by_source, selected_sources)
        return LiteratureSearchResult(query=normalized_query, items=items, source_statuses=statuses)

    def _default_connectors(self) -> dict[str, LiteratureConnector]:
        timeout = self.config.request_timeout_seconds
        return {
            "arxiv": ArxivConnector(
                self.config.sources["arxiv"], timeout_seconds=timeout, rate_limiter=self.rate_limiter
            ),
            "pubmed": PubMedConnector(
                self.config.sources["pubmed"], timeout_seconds=timeout, rate_limiter=self.rate_limiter
            ),
            "openalex": OpenAlexConnector(
                self.config.sources["openalex"], timeout_seconds=timeout, rate_limiter=self.rate_limiter
            ),
        }


def _normalize_sources(sources: Sequence[str]) -> tuple[str, ...]:
    normalized: list[str] = []
    for value in sources:
        source = str(value).strip().lower()
        if source not in SUPPORTED_LITERATURE_SOURCES:
            raise ValueError(f"Unsupported literature source: {source or value}")
        if source not in normalized:
            normalized.append(source)
    if not normalized:
        raise ValueError("At least one literature source is required.")
    return tuple(normalized)


def _merge_and_rank(
    records_by_source: Mapping[str, Sequence[PaperRecord]],
    source_order: Sequence[str],
) -> tuple[RankedPaper, ...]:
    merged: list[PaperRecord | None] = []
    aliases: dict[str, int] = {}
    for source in source_order:
        for paper in records_by_source.get(source, ()):
            keys = _dedup_keys(paper)
            matching_indices = sorted({aliases[key] for key in keys if key in aliases})
            if not matching_indices:
                target_index = len(merged)
                merged.append(paper)
            else:
                target_index = matching_indices[0]
                target = merged[target_index]
                if target is None:
                    raise RuntimeError("Literature deduplication index is inconsistent.")
                target = _merge_papers(target, paper)
                for duplicate_index in matching_indices[1:]:
                    duplicate = merged[duplicate_index]
                    if duplicate is not None:
                        target = _merge_papers(target, duplicate)
                        merged[duplicate_index] = None
                merged[target_index] = target
                duplicate_indices = set(matching_indices[1:])
                if duplicate_indices:
                    aliases = {
                        key: target_index if index in duplicate_indices else index
                        for key, index in aliases.items()
                    }
            target = merged[target_index]
            if target is None:
                raise RuntimeError("Literature deduplication target is missing.")
            for key in _dedup_keys(target):
                aliases[key] = target_index

    ranked = [
        RankedPaper(
            paper=paper,
            score=sum(1.0 / (RRF_K + rank) for rank in paper.source_ranks.values()),
        )
        for paper in merged
        if paper is not None
    ]
    ranked.sort(key=lambda item: item.paper.title.lower())
    ranked.sort(key=lambda item: item.paper.published_date, reverse=True)
    ranked.sort(key=lambda item: item.score, reverse=True)
    return tuple(ranked)


def _dedup_keys(paper: PaperRecord) -> tuple[str, ...]:
    keys = []
    for prefix, value in (
        ("doi", paper.doi),
        ("pmid", paper.pmid),
        ("arxiv", paper.arxiv_id.lower()),
        ("openalex", paper.openalex_id.lower()),
    ):
        if value:
            keys.append(f"{prefix}:{value}")
    title = " ".join(paper.title.lower().split())
    first_author = " ".join((paper.authors[0] if paper.authors else "").lower().split())
    fingerprint = hashlib.sha256(f"{title}|{first_author}|{paper.year or ''}".encode()).hexdigest()[:24]
    keys.append(f"title:{fingerprint}")
    return tuple(keys)


def _merge_papers(primary: PaperRecord, secondary: PaperRecord) -> PaperRecord:
    source_names = tuple(dict.fromkeys((*primary.source_names, *secondary.source_names)))
    source_ranks = {**primary.source_ranks, **secondary.source_ranks}
    raw_identifiers = {**primary.raw_identifiers, **secondary.raw_identifiers}
    merged = PaperRecord.create(
        source_name=source_names[0],
        source_rank=source_ranks[source_names[0]],
        title=primary.title or secondary.title,
        abstract=max((primary.abstract, secondary.abstract), key=len),
        authors=primary.authors or secondary.authors,
        published_date=primary.published_date or secondary.published_date,
        year=primary.year or secondary.year,
        venue=primary.venue or secondary.venue,
        doi=primary.doi or secondary.doi,
        pmid=primary.pmid or secondary.pmid,
        arxiv_id=primary.arxiv_id or secondary.arxiv_id,
        openalex_id=primary.openalex_id or secondary.openalex_id,
        landing_page_url=primary.landing_page_url or secondary.landing_page_url,
        pdf_url=primary.pdf_url or secondary.pdf_url,
        citation_count=_maximum(primary.citation_count, secondary.citation_count),
        is_retracted=primary.is_retracted or secondary.is_retracted,
        raw_identifiers=raw_identifiers,
    )
    return replace(merged, source_names=source_names, source_ranks=source_ranks)


def _maximum(first: int | None, second: int | None) -> int | None:
    values = [value for value in (first, second) if value is not None]
    return max(values) if values else None
