"""Product-contract tests for reviewable gm-science Memory."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from openppx.gm_science.memory import (
    GM_SCIENCE_MEMORY_APP_NAME,
    GM_SCIENCE_PROJECT_ID_ENV,
    GmScienceMemoryService,
    ProjectScopedMemoryService,
    science_propose_memory,
)
from openppx.gm_science.store import GmScienceStore
from openppx.runtime.sqlite_memory_service import SQLiteMemoryService


def _project(store: GmScienceStore, name: str = "Memory project"):
    return store.create_project(
        name=name,
        description="",
        agent_context="",
    )


def test_manual_note_crud_uses_existing_memory_database(tmp_path: Path) -> None:
    store = GmScienceStore(tmp_path)
    project = _project(store)
    backend = SQLiteMemoryService(db_path=tmp_path / "database" / "memory.db")
    service = GmScienceMemoryService(store=store, backend=backend)

    created = service.create_note(
        project_id=project.id,
        user_id="researcher",
        scope="user",
        category="About you",
        text="Prefer concise experimental summaries.",
    )
    updated = service.update_note(
        project_id=project.id,
        user_id="researcher",
        note_id=created["id"],
        category="Preferences",
        text="Prefer concise summaries with uncertainty labels.",
    )

    assert updated["id"] == created["id"]
    assert updated["scope"] == "user"
    assert updated["category"] == "Preferences"
    assert updated["provenance"]["source"] == "manual"
    assert updated["provenance"]["session_id"] == ""
    payload = service.get_workspace(project_id=project.id, user_id="researcher")
    assert [item["text"] for item in payload["notes"]] == [
        "Prefer concise summaries with uncertainty labels."
    ]
    assert payload["categories"] == ["Preferences"]

    service.delete_note(
        project_id=project.id,
        user_id="researcher",
        note_id=created["id"],
    )
    assert service.get_workspace(project_id=project.id, user_id="researcher")["notes"] == []


def test_candidate_requires_review_before_recall(tmp_path: Path) -> None:
    store = GmScienceStore(tmp_path)
    project = _project(store)
    backend = SQLiteMemoryService(db_path=tmp_path / "database" / "memory.db")
    service = GmScienceMemoryService(store=store, backend=backend)

    candidate = service.propose_candidate(
        project_id=project.id,
        user_id="researcher",
        session_id="session-1",
        scope="project",
        category="Project context",
        text="Use GRCh38 for all genome references.",
        rationale="The user stated a durable project convention.",
        model="openai-codex/gpt-5.5",
    )

    before = asyncio.run(
        backend.search_memory(
            app_name=GM_SCIENCE_MEMORY_APP_NAME,
            user_id=f"project:{project.id}",
            query="GRCh38",
        )
    )
    assert before.memories == []
    assert candidate["status"] == "pending"

    approved = service.review_candidate(
        project_id=project.id,
        user_id="researcher",
        candidate_id=candidate["id"],
        decision="approve",
    )
    assert approved["status"] == "approved"
    assert approved["approved_note_id"]

    after = asyncio.run(
        backend.search_memory(
            app_name=GM_SCIENCE_MEMORY_APP_NAME,
            user_id=f"project:{project.id}",
            query="GRCh38",
        )
    )
    assert len(after.memories) == 1
    assert after.memories[0].custom_metadata["candidate_id"] == candidate["id"]

    with pytest.raises(ValueError, match="already been reviewed"):
        service.review_candidate(
            project_id=project.id,
            user_id="researcher",
            candidate_id=candidate["id"],
            decision="approve",
        )


def test_project_scoped_service_merges_user_and_current_project_only(tmp_path: Path) -> None:
    store = GmScienceStore(tmp_path)
    first = _project(store, "First")
    second = _project(store, "Second")
    backend = SQLiteMemoryService(db_path=tmp_path / "database" / "memory.db")
    product = GmScienceMemoryService(store=store, backend=backend)
    product.create_note(
        project_id=first.id,
        user_id="researcher",
        scope="user",
        category="About you",
        text="Use metric units in research reports.",
    )
    product.create_note(
        project_id=first.id,
        user_id="researcher",
        scope="project",
        category="Project context",
        text="The cohort is called metric discovery.",
    )
    product.create_note(
        project_id=second.id,
        user_id="researcher",
        scope="project",
        category="Project context",
        text="The second project contains metric controls.",
    )

    scoped = ProjectScopedMemoryService(
        backend=backend,
        project_id=first.id,
        session_id="session-1",
    )
    response = asyncio.run(
        scoped.search_memory(app_name=GM_SCIENCE_MEMORY_APP_NAME, user_id="researcher", query="metric")
    )

    texts = [memory.content.parts[0].text for memory in response.memories]
    assert "Use metric units in research reports." in texts
    assert "The cohort is called metric discovery." in texts
    assert "The second project contains metric controls." not in texts
    assert {memory.custom_metadata["memory_scope"] for memory in response.memories} == {
        "user",
        "project",
    }


def test_scoped_service_does_not_auto_ingest_and_records_recall(tmp_path: Path) -> None:
    store = GmScienceStore(tmp_path)
    project = _project(store)
    backend = SQLiteMemoryService(db_path=tmp_path / "database" / "memory.db")
    product = GmScienceMemoryService(store=store, backend=backend)
    note = product.create_note(
        project_id=project.id,
        user_id="researcher",
        scope="user",
        category="About you",
        text="The preferred marker is CXCL8.",
    )
    scoped = ProjectScopedMemoryService(
        backend=backend,
        project_id=project.id,
        session_id="session-2",
    )

    asyncio.run(
        scoped.add_events_to_memory(
            app_name=GM_SCIENCE_MEMORY_APP_NAME,
            user_id="researcher",
            session_id="session-2",
            events=[object()],
        )
    )
    response = asyncio.run(
        scoped.search_memory(app_name=GM_SCIENCE_MEMORY_APP_NAME, user_id="researcher", query="CXCL8")
    )

    assert [memory.id for memory in response.memories] == [note["id"]]
    workspace = product.get_workspace(project_id=project.id, user_id="researcher")
    recalled_note = next(item for item in workspace["notes"] if item["id"] == note["id"])
    assert recalled_note["usage"]["session_ids"] == ["session-2"]
    assert recalled_note["usage"]["count"] == 1


def test_project_note_cannot_be_managed_through_another_project(tmp_path: Path) -> None:
    store = GmScienceStore(tmp_path)
    first = _project(store, "First")
    second = _project(store, "Second")
    backend = SQLiteMemoryService(db_path=tmp_path / "database" / "memory.db")
    service = GmScienceMemoryService(store=store, backend=backend)
    note = service.create_note(
        project_id=first.id,
        user_id="researcher",
        scope="project",
        category="Project context",
        text="Private first-project context.",
    )

    with pytest.raises(ValueError, match="not found"):
        service.update_note(
            project_id=second.id,
            user_id="researcher",
            note_id=note["id"],
            category="Project context",
            text="Cross-project edit.",
        )


def test_adk_tool_creates_pending_candidate_without_implicit_recall(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = GmScienceStore(tmp_path)
    project = _project(store)
    backend = SQLiteMemoryService(db_path=tmp_path / "database" / "memory.db")
    monkeypatch.setattr("openppx.gm_science.memory.GmScienceStore", lambda: store)
    monkeypatch.setattr("openppx.gm_science.memory.SQLiteMemoryService", lambda **_kwargs: backend)
    monkeypatch.setattr("openppx.gm_science.memory.get_gm_science_data_dir", lambda: tmp_path)
    monkeypatch.setenv("OPENPPX_MEMORY_ENABLED", "1")
    monkeypatch.setenv(GM_SCIENCE_PROJECT_ID_ENV, project.id)
    monkeypatch.setenv(
        "GM_SCIENCE_SESSION_POLICY_JSON",
        '{"memory_enabled":true}',
    )
    monkeypatch.setenv("OPENPPX_MODEL", "openai-codex/gpt-5.5")
    tool_context = type(
        "FakeToolContext",
        (),
        {"user_id": "researcher", "session": type("Session", (), {"id": "session-tool"})()},
    )()

    result = science_propose_memory(
        scope="project",
        category="Project context",
        text="Use GRCh38 for all genome references.",
        rationale="A durable convention for this Project.",
        tool_context=tool_context,
    )

    assert result["status"] == "pending_review"
    assert result["candidate"]["status"] == "pending"
    recall = asyncio.run(
        backend.search_memory(
            app_name=GM_SCIENCE_MEMORY_APP_NAME,
            user_id=f"project:{project.id}",
            query="GRCh38",
        )
    )
    assert recall.memories == []


def test_adk_tool_rejects_candidate_when_global_memory_is_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENPPX_MEMORY_ENABLED", "0")

    with pytest.raises(ValueError, match="disabled globally"):
        science_propose_memory(
            scope="user",
            category="About you",
            text="Prefer concise summaries.",
            rationale="A durable response preference.",
            tool_context=object(),
        )
