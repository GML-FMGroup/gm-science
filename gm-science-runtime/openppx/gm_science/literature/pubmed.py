"""PubMed E-utilities connector."""

from __future__ import annotations

import calendar
import xml.etree.ElementTree as ET

import httpx

from .config import LiteratureSourceConfig
from .http import LiteratureConnectorError, require_source, safe_get
from .models import PaperRecord
from .rate_limit import SourceRateLimiter


class PubMedConnector:
    """Search PubMed IDs and fetch normalized article metadata."""

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
        """Run ESearch followed by EFetch for full article metadata."""

        require_source("pubmed", enabled=self.config.enabled, api_base=self.config.api_base)
        if not self.config.email:
            raise LiteratureConnectorError(
                "pubmed",
                "needs_configuration",
                "Set science.literature.pubmed.email.",
            )
        common = {"tool": self.config.tool or "gm-science", "email": self.config.email}
        if self.config.api_key:
            common["api_key"] = self.config.api_key
        self.rate_limiter.wait("pubmed", self.config.min_interval_seconds)
        search_response = safe_get(
            self.client,
            f"{self.config.api_base}/esearch.fcgi",
            source="pubmed",
            params={
                **common,
                "db": "pubmed",
                "term": query.strip(),
                "retmax": max_results,
                "retmode": "json",
                "sort": "relevance",
            },
            timeout_seconds=self.timeout_seconds,
        )
        try:
            identifiers = search_response.json().get("esearchresult", {}).get("idlist", [])
        except (ValueError, AttributeError) as exc:
            raise LiteratureConnectorError("pubmed", "parse_error", "pubmed returned invalid JSON.") from exc
        identifiers = [str(value) for value in identifiers if value]
        if not identifiers:
            return []

        self.rate_limiter.wait("pubmed", self.config.min_interval_seconds)
        fetch_response = safe_get(
            self.client,
            f"{self.config.api_base}/efetch.fcgi",
            source="pubmed",
            params={
                **common,
                "db": "pubmed",
                "id": ",".join(identifiers),
                "retmode": "xml",
            },
            timeout_seconds=self.timeout_seconds,
        )
        try:
            root = ET.fromstring(fetch_response.content)
        except ET.ParseError as exc:
            raise LiteratureConnectorError("pubmed", "parse_error", "pubmed returned invalid XML.") from exc
        return [_parse_article(article, rank) for rank, article in enumerate(root.findall("PubmedArticle"), start=1)]


def _parse_article(article: ET.Element, rank: int) -> PaperRecord:
    article_node = article.find("./MedlineCitation/Article")
    if article_node is None:
        article_node = ET.Element("Article")
    identifiers = {
        node.get("IdType", ""): _text(node)
        for node in article.findall("./PubmedData/ArticleIdList/ArticleId")
    }
    pmid = identifiers.get("pubmed") or _find_text(article, "./MedlineCitation/PMID")
    date_node = article_node.find("./Journal/JournalIssue/PubDate")
    published_date, year = _publication_date(date_node)
    abstract_parts: list[str] = []
    for node in article_node.findall("./Abstract/AbstractText"):
        text = _text(node)
        label = (node.get("Label") or "").strip()
        abstract_parts.append(f"{label}: {text}" if label else text)
    authors: list[str] = []
    for author in article_node.findall("./AuthorList/Author"):
        collective = _find_text(author, "CollectiveName")
        if collective:
            authors.append(collective)
            continue
        name = " ".join(filter(None, [_find_text(author, "ForeName"), _find_text(author, "LastName")]))
        if name:
            authors.append(name)
    return PaperRecord.create(
        source_name="pubmed",
        source_rank=rank,
        title=_find_text(article_node, "ArticleTitle"),
        abstract=" ".join(abstract_parts),
        authors=authors,
        published_date=published_date,
        year=year,
        venue=_find_text(article_node, "./Journal/Title"),
        doi=identifiers.get("doi", ""),
        pmid=pmid,
        landing_page_url=f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/" if pmid else "",
        raw_identifiers=identifiers,
    )


def _text(node: ET.Element) -> str:
    return " ".join("".join(node.itertext()).split())


def _find_text(node: ET.Element, path: str) -> str:
    child = node.find(path)
    return "" if child is None else _text(child)


def _publication_date(node: ET.Element | None) -> tuple[str, int | None]:
    if node is None:
        return "", None
    year_text = _find_text(node, "Year")
    month_text = _find_text(node, "Month")
    day_text = _find_text(node, "Day")
    try:
        year = int(year_text)
    except ValueError:
        return _find_text(node, "MedlineDate"), None
    month = _month_number(month_text)
    try:
        day = int(day_text) if day_text else 1
    except ValueError:
        day = 1
    return f"{year:04d}-{month:02d}-{day:02d}", year


def _month_number(value: str) -> int:
    if not value:
        return 1
    try:
        return min(max(int(value), 1), 12)
    except ValueError:
        abbreviation = value[:3].title()
        return next((index for index, name in enumerate(calendar.month_abbr) if name == abbreviation), 1)
