"""arXiv Atom API connector."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from urllib.parse import urlparse

import httpx

from .config import LiteratureSourceConfig
from .http import LiteratureConnectorError, require_source, safe_get
from .models import PaperRecord
from .rate_limit import SourceRateLimiter


ATOM = "http://www.w3.org/2005/Atom"
ARXIV = "http://arxiv.org/schemas/atom"


class ArxivConnector:
    """Search arXiv and normalize Atom entries into paper records."""

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
        """Search all arXiv fields and return results in source order."""

        require_source("arxiv", enabled=self.config.enabled, api_base=self.config.api_base)
        self.rate_limiter.wait("arxiv", self.config.min_interval_seconds)
        response = safe_get(
            self.client,
            self.config.api_base,
            source="arxiv",
            params={
                "search_query": f"all:{query.strip()}",
                "start": 0,
                "max_results": max_results,
                "sortBy": "relevance",
                "sortOrder": "descending",
            },
            timeout_seconds=self.timeout_seconds,
        )
        try:
            root = ET.fromstring(response.content)
        except ET.ParseError as exc:
            raise LiteratureConnectorError("arxiv", "parse_error", "arxiv returned invalid XML.") from exc

        papers: list[PaperRecord] = []
        for rank, entry in enumerate(root.findall(f"{{{ATOM}}}entry"), start=1):
            entry_id = _node_text(entry, f"{{{ATOM}}}id")
            landing_page_url = entry_id
            pdf_url = ""
            for link in entry.findall(f"{{{ATOM}}}link"):
                href = link.get("href", "")
                if link.get("rel") == "alternate":
                    landing_page_url = href
                if link.get("type") == "application/pdf" or link.get("title") == "pdf":
                    pdf_url = href
            published = _node_text(entry, f"{{{ATOM}}}published")[:10]
            papers.append(
                PaperRecord.create(
                    source_name="arxiv",
                    source_rank=rank,
                    title=_node_text(entry, f"{{{ATOM}}}title"),
                    abstract=_node_text(entry, f"{{{ATOM}}}summary"),
                    authors=[_node_text(author, f"{{{ATOM}}}name") for author in entry.findall(f"{{{ATOM}}}author")],
                    published_date=published,
                    year=_year(published),
                    venue=_node_text(entry, f"{{{ARXIV}}}journal_ref"),
                    doi=_node_text(entry, f"{{{ARXIV}}}doi"),
                    arxiv_id=_path_identifier(entry_id),
                    landing_page_url=landing_page_url,
                    pdf_url=pdf_url,
                )
            )
        return papers


def _node_text(node: ET.Element, path: str) -> str:
    child = node.find(path)
    return "" if child is None else "".join(child.itertext())


def _path_identifier(value: str) -> str:
    return urlparse(value).path.rstrip("/").split("/")[-1]


def _year(value: str) -> int | None:
    try:
        return int(value[:4])
    except ValueError:
        return None
