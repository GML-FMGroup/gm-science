from __future__ import annotations

import asyncio
from pathlib import Path

from openppx.gm_science.specialists.config import parse_specialist_config
from openppx.gm_science.store import GmScienceStore
from openppx.runtime import client_api_worker


class FakeReviewerTool:
    name = "research_reviewer"

    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    async def run_async(self, *, args, tool_context):
        self.calls.append(dict(args))
        return {
            "output": {"verdict": "revise"},
            "artifact": {"id": "art_critique", "type": "critique_report"},
        }


def test_report_review_gate_reviews_only_latest_new_report(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("GM_SCIENCE_DATA_DIR", str(tmp_path))
    store = GmScienceStore(tmp_path)
    project = store.create_project(
        name="Review",
        description="",
        agent_context="",
        enabled_specialists=["research_reviewer"],
    )
    old = store.create_artifact(
        project_id=project.id,
        artifact_type="report",
        title="Old",
        path_or_url="",
        session_id="session-1",
    )
    before_ids = {old.id}
    store.create_artifact(
        project_id=project.id,
        artifact_type="report",
        title="First new",
        path_or_url="",
        session_id="session-1",
    )
    latest = store.create_artifact(
        project_id=project.id,
        artifact_type="report",
        title="Latest new",
        path_or_url="",
        session_id="session-1",
    )
    tool = FakeReviewerTool()
    monkeypatch.setattr(
        client_api_worker,
        "load_specialist_config",
        lambda: parse_specialist_config({}),
    )

    result = asyncio.run(
        client_api_worker.run_report_review_gate(
            project_id=project.id,
            session_id="session-1",
            user_id="user-1",
            app_name="openppx",
            before_artifact_ids=before_ids,
            reviewer_tool=tool,
        )
    )

    assert result.status == "completed"
    assert result.verdict == "revise"
    assert result.target_artifact_id == latest.id
    assert tool.calls == [
        {
            "project_id": project.id,
            "session_id": "session-1",
            "target_artifact_id": latest.id,
            "review_focus": "Check evidence support, citation integrity, reasoning, and reproducibility.",
            "trigger": "gate",
        }
    ]


def test_report_review_gate_skips_off_chat_and_already_reviewed_reports(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("GM_SCIENCE_DATA_DIR", str(tmp_path))
    store = GmScienceStore(tmp_path)
    project = store.create_project(
        name="Review",
        description="",
        agent_context="",
        enabled_specialists=["research_reviewer"],
    )
    tool = FakeReviewerTool()
    monkeypatch.setattr(
        client_api_worker,
        "load_specialist_config",
        lambda: parse_specialist_config({"science": {"specialists": {"reviewer": {"reviewGate": "off"}}}}),
    )

    off = asyncio.run(
        client_api_worker.run_report_review_gate(
            project_id=project.id,
            session_id="session-1",
            user_id="user-1",
            app_name="openppx",
            before_artifact_ids=set(),
            reviewer_tool=tool,
        )
    )
    assert off.status == "skipped"

    monkeypatch.setattr(client_api_worker, "load_specialist_config", lambda: parse_specialist_config({}))
    chat = asyncio.run(
        client_api_worker.run_report_review_gate(
            project_id=project.id,
            session_id="session-1",
            user_id="user-1",
            app_name="openppx",
            before_artifact_ids=set(),
            reviewer_tool=tool,
        )
    )
    assert chat.status == "skipped"

    report = store.create_artifact(
        project_id=project.id,
        artifact_type="report",
        title="Reviewed",
        path_or_url="",
        session_id="session-1",
    )
    store.create_artifact(
        project_id=project.id,
        artifact_type="critique_report",
        title="Critique",
        path_or_url="",
        session_id="session-1",
        metadata={"target_artifact_id": report.id},
    )
    reviewed = asyncio.run(
        client_api_worker.run_report_review_gate(
            project_id=project.id,
            session_id="session-1",
            user_id="user-1",
            app_name="openppx",
            before_artifact_ids=set(),
            reviewer_tool=tool,
        )
    )
    assert reviewed.status == "skipped"
    assert tool.calls == []


def test_report_review_gate_failure_preserves_main_result_note(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("GM_SCIENCE_DATA_DIR", str(tmp_path))
    store = GmScienceStore(tmp_path)
    project = store.create_project(
        name="Review",
        description="",
        agent_context="",
        enabled_specialists=["research_reviewer"],
    )
    store.create_artifact(
        project_id=project.id,
        artifact_type="report",
        title="Draft",
        path_or_url="",
        session_id="session-1",
    )
    monkeypatch.setattr(client_api_worker, "load_specialist_config", lambda: parse_specialist_config({}))

    class FailingReviewer:
        name = "research_reviewer"

        async def run_async(self, *, args, tool_context):
            raise RuntimeError("review unavailable")

    gate = asyncio.run(
        client_api_worker.run_report_review_gate(
            project_id=project.id,
            session_id="session-1",
            user_id="user-1",
            app_name="openppx",
            before_artifact_ids=set(),
            reviewer_tool=FailingReviewer(),
        )
    )
    text = client_api_worker.append_review_gate_note("Main answer", gate)

    assert gate.status == "failed"
    assert text.startswith("Main answer")
    assert "review could not be completed" in text
    assert "review unavailable" not in text
