"""Contracts for gm-science local Storage and Usage observability."""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path

import pytest

from openppx.gm_science.observability import GmScienceObservabilityService
from openppx.runtime.task_store import TaskStore
from openppx.runtime.token_usage_store import write_token_usage_event


def test_storage_snapshot_uses_non_overlapping_categories_and_does_not_follow_symlinks(
    tmp_path: Path,
) -> None:
    data_dir = tmp_path / "gm-science"
    (data_dir / "workspaces" / "science-research").mkdir(parents=True)
    (data_dir / "database").mkdir()
    (data_dir / "cache").mkdir()
    (data_dir / "science-research").mkdir()
    (data_dir / "logs").mkdir()
    (data_dir / "workspaces" / "science-research" / "report.md").write_text("report", encoding="utf-8")
    (data_dir / "database" / "tasks.db").write_bytes(b"db")
    (data_dir / "cache" / "paper.json").write_text("{}", encoding="utf-8")
    (data_dir / "science-research" / "config.json").write_text("{}", encoding="utf-8")
    (data_dir / "logs" / "runtime.log").write_text("log", encoding="utf-8")
    (data_dir / "unclassified.txt").write_text("other", encoding="utf-8")
    outside = tmp_path / "outside.bin"
    outside.write_bytes(b"x" * 1024 * 1024)
    os.symlink(outside, data_dir / "workspaces" / "science-research" / "outside-link")

    snapshot = GmScienceObservabilityService(
        data_dir=data_dir,
        now_ms=lambda: 1_800_000_000_000,
    ).get_storage_snapshot()

    by_id = {item["id"]: item for item in snapshot["categories"]}
    assert snapshot["data_location"] == str(data_dir.resolve())
    assert snapshot["scan_complete"] is True
    assert snapshot["total_files"] == sum(item["files"] for item in snapshot["categories"])
    assert by_id["workspaces"]["files"] == 2
    assert by_id["databases"]["files"] == 1
    assert by_id["cache"]["files"] == 1
    assert by_id["configuration"]["files"] == 1
    assert by_id["logs"]["files"] == 1
    assert by_id["other"]["files"] == 1
    assert by_id["workspaces"]["bytes"] < outside.stat().st_size
    assert snapshot["cloud_storage"]["supported"] is False


def test_storage_snapshot_returns_partial_results_when_entry_budget_is_exhausted(tmp_path: Path) -> None:
    data_dir = tmp_path / "gm-science"
    data_dir.mkdir()
    for index in range(5):
        (data_dir / f"file-{index}.txt").write_text(str(index), encoding="utf-8")

    snapshot = GmScienceObservabilityService(data_dir=data_dir).get_storage_snapshot(max_entries=2)

    assert snapshot["scan_complete"] is False
    assert snapshot["entries_scanned"] == 2
    assert "2 filesystem entries" in snapshot["partial_reason"]


def test_storage_snapshot_does_not_create_a_missing_data_root(tmp_path: Path) -> None:
    data_dir = tmp_path / "missing"

    snapshot = GmScienceObservabilityService(data_dir=data_dir).get_storage_snapshot()

    assert snapshot["exists"] is False
    assert snapshot["total_bytes"] == 0
    assert not data_dir.exists()


def test_usage_snapshot_aggregates_local_tokens_and_task_runtime(tmp_path: Path) -> None:
    data_dir = tmp_path / "gm-science"
    data_dir.mkdir()
    now_ms = 1_800_000_000_000
    write_token_usage_event(
        {
            "request_at": "2027-01-15T07:59:58Z",
            "request_at_ms": now_ms - 2_000,
            "response_at": "2027-01-15T07:59:59Z",
            "response_at_ms": now_ms - 1_000,
            "provider": "openai_codex",
            "model": "openai-codex/gpt-5.5",
            "session_id": "session-1",
            "invocation_id": "invocation-1",
            "request_tokens": 120,
            "response_tokens": 30,
            "request_text_tokens": 120,
            "response_text_tokens": 30,
            "request_image_tokens": 0,
            "response_image_tokens": 0,
            "total_tokens": 150,
            "raw_usage": {},
        },
        data_dir / "token_usage.db",
    )
    task_store = TaskStore(db_path=data_dir / "database" / "tasks.db")
    completed = task_store.create_task(kind="data_analysis", title="Analysis", status="completed")
    running = task_store.create_task(kind="local_python", title="Simulation", status="running")
    with sqlite3.connect(task_store.db_path) as conn:
        conn.execute(
            "UPDATE task_runs SET created_at_ms = ?, updated_at_ms = ?, ended_at_ms = ? WHERE task_id = ?",
            (now_ms - 10_000, now_ms - 5_000, now_ms - 5_000, completed.task_id),
        )
        conn.execute(
            "UPDATE task_runs SET created_at_ms = ?, updated_at_ms = ?, ended_at_ms = NULL WHERE task_id = ?",
            (now_ms - 3_000, now_ms - 1_000, running.task_id),
        )

    snapshot = GmScienceObservabilityService(
        data_dir=data_dir,
        now_ms=lambda: now_ms,
    ).get_usage_snapshot("24h")

    assert snapshot["window"] == "24h"
    assert snapshot["local_estimate"] is True
    assert snapshot["cost"]["available"] is False
    assert snapshot["tokens"] == {
        "recording_started": True,
        "requests": 1,
        "input_tokens": 120,
        "output_tokens": 30,
        "input_text_tokens": 120,
        "output_text_tokens": 30,
        "input_image_tokens": 0,
        "output_image_tokens": 0,
        "total_tokens": 150,
        "by_model": [
            {
                "provider": "openai_codex",
                "model": "openai-codex/gpt-5.5",
                "requests": 1,
                "input_tokens": 120,
                "output_tokens": 30,
                "total_tokens": 150,
            }
        ],
    }
    assert snapshot["runs"]["runs"] == 2
    assert snapshot["runs"]["active_runs"] == 1
    assert snapshot["runs"]["terminal_runs"] == 1
    assert snapshot["runs"]["runtime_ms"] == 8_000
    assert {item["status"]: item["runs"] for item in snapshot["runs"]["by_status"]} == {
        "completed": 1,
        "running": 1,
    }


def test_usage_snapshot_is_read_only_when_event_stores_do_not_exist(tmp_path: Path) -> None:
    data_dir = tmp_path / "gm-science"
    data_dir.mkdir()

    snapshot = GmScienceObservabilityService(data_dir=data_dir).get_usage_snapshot("7d")

    assert snapshot["tokens"]["recording_started"] is False
    assert snapshot["runs"]["recording_started"] is False
    assert snapshot["tokens"]["total_tokens"] == 0
    assert snapshot["runs"]["runs"] == 0
    assert not (data_dir / "token_usage.db").exists()
    assert not (data_dir / "database" / "tasks.db").exists()


def test_usage_snapshot_rejects_unknown_windows(tmp_path: Path) -> None:
    service = GmScienceObservabilityService(data_dir=tmp_path)

    with pytest.raises(ValueError, match="Unsupported usage window"):
        service.get_usage_snapshot("90d")
