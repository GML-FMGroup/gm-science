"""Structured literature search for gm-science."""

from .config import (
    LiteratureConfig,
    LiteratureSourceConfig,
    LiteratureSourceSelection,
    load_literature_config,
    parse_literature_config,
    select_literature_sources,
)
from .http import LiteratureConnectorError
from .models import PaperRecord
from .service import LiteratureSearchResult, LiteratureSearchService, RankedPaper, SourceSearchStatus

__all__ = [
    "LiteratureConfig",
    "LiteratureConnectorError",
    "LiteratureSourceConfig",
    "LiteratureSourceSelection",
    "LiteratureSearchResult",
    "LiteratureSearchService",
    "PaperRecord",
    "RankedPaper",
    "SourceSearchStatus",
    "load_literature_config",
    "parse_literature_config",
    "select_literature_sources",
]
