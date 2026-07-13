"""Normalized data models shared by literature connectors."""

from __future__ import annotations

import hashlib
import re
from dataclasses import asdict, dataclass, field
from typing import Any, Iterable, Mapping
from urllib.parse import urlparse


_ARXIV_VERSION = re.compile(r"v\d+$", re.IGNORECASE)


@dataclass(frozen=True, slots=True)
class PaperRecord:
    """A source-independent scholarly work returned by a connector."""

    canonical_id: str
    title: str
    abstract: str = ""
    authors: tuple[str, ...] = ()
    published_date: str = ""
    year: int | None = None
    venue: str = ""
    doi: str = ""
    pmid: str = ""
    arxiv_id: str = ""
    openalex_id: str = ""
    landing_page_url: str = ""
    pdf_url: str = ""
    citation_count: int | None = None
    is_retracted: bool = False
    source_names: tuple[str, ...] = ()
    source_ranks: Mapping[str, int] = field(default_factory=dict)
    raw_identifiers: Mapping[str, str] = field(default_factory=dict)

    @classmethod
    def create(
        cls,
        *,
        source_name: str,
        source_rank: int,
        title: str,
        abstract: str = "",
        authors: Iterable[str] = (),
        published_date: str = "",
        year: int | None = None,
        venue: str = "",
        doi: str = "",
        pmid: str = "",
        arxiv_id: str = "",
        openalex_id: str = "",
        landing_page_url: str = "",
        pdf_url: str = "",
        citation_count: int | None = None,
        is_retracted: bool = False,
        raw_identifiers: Mapping[str, str] | None = None,
    ) -> PaperRecord:
        """Create a record with normalized text and stable identifiers."""

        normalized_title = _text(title)
        normalized_authors = tuple(author for author in (_text(value) for value in authors) if author)
        normalized_doi = _doi(doi)
        normalized_pmid = _pmid(pmid)
        normalized_arxiv = _arxiv_id(arxiv_id)
        normalized_openalex = _openalex_id(openalex_id)
        canonical_id = _canonical_id(
            doi=normalized_doi,
            pmid=normalized_pmid,
            arxiv_id=normalized_arxiv,
            openalex_id=normalized_openalex,
            title=normalized_title,
            first_author=normalized_authors[0] if normalized_authors else "",
            year=year,
        )
        source = _text(source_name).lower()
        return cls(
            canonical_id=canonical_id,
            title=normalized_title,
            abstract=_text(abstract),
            authors=normalized_authors,
            published_date=_text(published_date),
            year=year,
            venue=_text(venue),
            doi=normalized_doi,
            pmid=normalized_pmid,
            arxiv_id=normalized_arxiv,
            openalex_id=normalized_openalex,
            landing_page_url=_text(landing_page_url),
            pdf_url=_text(pdf_url),
            citation_count=citation_count,
            is_retracted=bool(is_retracted),
            source_names=(source,),
            source_ranks={source: max(1, int(source_rank))},
            raw_identifiers=dict(raw_identifiers or {}),
        )

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-compatible representation of the paper."""

        value = asdict(self)
        value["authors"] = list(self.authors)
        value["source_names"] = list(self.source_names)
        return value

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> PaperRecord:
        """Restore a paper from trusted-shape JSON data with type normalization."""

        title = value.get("title")
        source_names = value.get("source_names")
        source_ranks = value.get("source_ranks")
        if not isinstance(title, str) or not isinstance(source_names, list) or not isinstance(source_ranks, Mapping):
            raise ValueError("Invalid paper cache record.")
        paper = cls.create(
            source_name=str(source_names[0]) if source_names else "cache",
            source_rank=min((int(rank) for rank in source_ranks.values()), default=1),
            title=title,
            abstract=str(value.get("abstract") or ""),
            authors=value.get("authors") if isinstance(value.get("authors"), list) else (),
            published_date=str(value.get("published_date") or ""),
            year=_optional_int(value.get("year")),
            venue=str(value.get("venue") or ""),
            doi=str(value.get("doi") or ""),
            pmid=str(value.get("pmid") or ""),
            arxiv_id=str(value.get("arxiv_id") or ""),
            openalex_id=str(value.get("openalex_id") or ""),
            landing_page_url=str(value.get("landing_page_url") or ""),
            pdf_url=str(value.get("pdf_url") or ""),
            citation_count=_optional_int(value.get("citation_count")),
            is_retracted=bool(value.get("is_retracted", False)),
            raw_identifiers=value.get("raw_identifiers") if isinstance(value.get("raw_identifiers"), Mapping) else {},
        )
        normalized_names = tuple(str(name) for name in source_names if str(name))
        normalized_ranks = {str(name): int(rank) for name, rank in source_ranks.items()}
        return cls(
            canonical_id=paper.canonical_id,
            title=paper.title,
            abstract=paper.abstract,
            authors=paper.authors,
            published_date=paper.published_date,
            year=paper.year,
            venue=paper.venue,
            doi=paper.doi,
            pmid=paper.pmid,
            arxiv_id=paper.arxiv_id,
            openalex_id=paper.openalex_id,
            landing_page_url=paper.landing_page_url,
            pdf_url=paper.pdf_url,
            citation_count=paper.citation_count,
            is_retracted=paper.is_retracted,
            source_names=normalized_names,
            source_ranks=normalized_ranks,
            raw_identifiers=paper.raw_identifiers,
        )


def _text(value: Any) -> str:
    return " ".join(str(value or "").split())


def _doi(value: str) -> str:
    normalized = _text(value).lower()
    for prefix in ("https://doi.org/", "http://doi.org/", "doi:"):
        if normalized.startswith(prefix):
            normalized = normalized[len(prefix) :]
            break
    return normalized.strip().rstrip(".")


def _pmid(value: str) -> str:
    normalized = _text(value)
    if "://" in normalized:
        normalized = urlparse(normalized).path.strip("/").split("/")[-1]
    if normalized.lower().startswith("pmid:"):
        normalized = normalized[5:]
    return normalized.strip()


def _arxiv_id(value: str) -> str:
    normalized = _text(value)
    if "://" in normalized:
        normalized = urlparse(normalized).path.rstrip("/").split("/")[-1]
    if normalized.lower().startswith("arxiv:"):
        normalized = normalized[6:]
    return _ARXIV_VERSION.sub("", normalized.strip())


def _openalex_id(value: str) -> str:
    normalized = _text(value)
    if "://" in normalized:
        normalized = urlparse(normalized).path.strip("/").split("/")[-1]
    return normalized.upper()


def _canonical_id(
    *,
    doi: str,
    pmid: str,
    arxiv_id: str,
    openalex_id: str,
    title: str,
    first_author: str,
    year: int | None,
) -> str:
    if doi:
        return f"doi:{doi}"
    if pmid:
        return f"pmid:{pmid}"
    if arxiv_id:
        return f"arxiv:{arxiv_id.lower()}"
    if openalex_id:
        return f"openalex:{openalex_id.lower()}"
    fingerprint = hashlib.sha256(
        f"{title.lower()}|{first_author.lower()}|{year or ''}".encode()
    ).hexdigest()[:24]
    return f"title:{fingerprint}"


def _optional_int(value: Any) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None
