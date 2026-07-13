"""Local file cache for normalized literature search results."""

from __future__ import annotations

import hashlib
import json
import os
import time
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

from .models import PaperRecord


class LiteratureCache:
    """Persist source query results as expiring JSON files."""

    def __init__(
        self,
        root_dir: Path | str,
        *,
        ttl_seconds: int,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.root_dir = Path(root_dir).expanduser()
        self.ttl_seconds = max(0, int(ttl_seconds))
        self.clock = clock

    def get(self, source: str, query: str, max_results: int) -> list[PaperRecord] | None:
        """Return fresh cached records, or None for any cache miss."""

        if self.ttl_seconds == 0:
            return None
        path = self._path(source, query, max_results)
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            created_at = float(payload["created_at"])
            records = payload["records"]
            if self.clock() - created_at > self.ttl_seconds or not isinstance(records, list):
                return None
            return [PaperRecord.from_dict(record) for record in records if isinstance(record, dict)]
        except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError):
            return None

    def put(self, source: str, query: str, max_results: int, records: Sequence[PaperRecord]) -> None:
        """Atomically cache normalized records when caching is enabled."""

        if self.ttl_seconds == 0:
            return
        self.root_dir.mkdir(parents=True, exist_ok=True)
        path = self._path(source, query, max_results)
        temporary = path.with_suffix(f".{os.getpid()}.tmp")
        payload: dict[str, Any] = {
            "created_at": self.clock(),
            "records": [record.to_dict() for record in records],
        }
        temporary.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True), encoding="utf-8")
        temporary.replace(path)

    def _path(self, source: str, query: str, max_results: int) -> Path:
        key = json.dumps(
            {
                "source": str(source).strip().lower(),
                "query": " ".join(str(query).lower().split()),
                "max_results": int(max_results),
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        digest = hashlib.sha256(key.encode()).hexdigest()
        return self.root_dir / f"{digest}.json"
