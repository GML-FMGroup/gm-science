from __future__ import annotations

import json
from pathlib import Path

from openppx.gm_science.literature.cache import LiteratureCache
from openppx.gm_science.literature.models import PaperRecord
from openppx.gm_science.literature.rate_limit import SourceRateLimiter


def _paper() -> PaperRecord:
    return PaperRecord.create(
        source_name="arxiv",
        source_rank=1,
        title="Reliable Protein Folding",
        year=2024,
        arxiv_id="2401.01234",
    )


def test_cache_round_trips_records_with_normalized_key(tmp_path: Path) -> None:
    now = [100.0]
    cache = LiteratureCache(tmp_path, ttl_seconds=60, clock=lambda: now[0])

    cache.put("arxiv", "  Protein   Folding ", 10, [_paper()])

    assert cache.get("arxiv", "protein folding", 10) == [_paper()]
    assert len(list(tmp_path.glob("*.json"))) == 1


def test_cache_ttl_and_corrupt_entry_degrade_to_miss(tmp_path: Path) -> None:
    now = [100.0]
    cache = LiteratureCache(tmp_path, ttl_seconds=10, clock=lambda: now[0])
    cache.put("arxiv", "protein folding", 10, [_paper()])
    path = next(tmp_path.glob("*.json"))

    now[0] = 111.0
    assert cache.get("arxiv", "protein folding", 10) is None

    path.write_text(json.dumps({"created_at": 111.0, "records": "invalid"}), encoding="utf-8")
    assert cache.get("arxiv", "protein folding", 10) is None


def test_zero_ttl_disables_cache(tmp_path: Path) -> None:
    cache = LiteratureCache(tmp_path, ttl_seconds=0)

    cache.put("arxiv", "protein folding", 10, [_paper()])

    assert cache.get("arxiv", "protein folding", 10) is None
    assert list(tmp_path.glob("*.json")) == []


def test_source_rate_limiter_waits_only_for_remaining_interval() -> None:
    now = [10.0]
    sleeps: list[float] = []

    def sleep(seconds: float) -> None:
        sleeps.append(seconds)
        now[0] += seconds

    limiter = SourceRateLimiter(clock=lambda: now[0], sleep=sleep)

    limiter.wait("arxiv", 3.0)
    now[0] += 1.25
    limiter.wait("arxiv", 3.0)
    limiter.wait("pubmed", 0.34)

    assert sleeps == [1.75]
