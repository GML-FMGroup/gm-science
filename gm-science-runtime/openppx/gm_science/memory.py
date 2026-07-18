"""Reviewable User and Project Memory on top of the ADK memory backend."""

from __future__ import annotations

import os
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from typing import Any

from google.adk.memory.base_memory_service import BaseMemoryService, SearchMemoryResponse
from google.adk.memory.memory_entry import MemoryEntry
from google.adk.tools.tool_context import ToolContext

from ..core.env_utils import env_enabled
from ..runtime.sqlite_memory_service import SQLiteMemoryService
from .paths import get_gm_science_data_dir
from .session_policy import session_policy_from_env
from .store import GmScienceStore

GM_SCIENCE_MEMORY_APP_NAME = "gm_science"
GM_SCIENCE_PROJECT_ID_ENV = "GM_SCIENCE_PROJECT_ID"
_MEMORY_SCOPES = frozenset({"user", "project"})
_MEMORY_DECISIONS = frozenset({"approve", "reject"})
_MAX_CATEGORY_CHARS = 80
_MAX_TEXT_CHARS = 4000
_MAX_RATIONALE_CHARS = 1200
_ADK_UNKNOWN_SESSION_ID = "__unknown_session_id__"


def project_memory_user_id(project_id: str) -> str:
    """Return the stable ADK user scope reserved for one Project."""

    return f"project:{project_id}"


def _iso_from_ms(value: int) -> str:
    if value <= 0:
        return ""
    return datetime.fromtimestamp(value / 1000, tz=timezone.utc).isoformat()


def _bounded_text(raw: Any, *, field: str, limit: int) -> str:
    value = str(raw or "").strip()
    if not value:
        raise ValueError(f"{field} is required.")
    if len(value) > limit or any(ord(char) < 32 and char not in "\n\t" for char in value):
        raise ValueError(f"{field} must be at most {limit} printable characters.")
    return value


class GmScienceMemoryService:
    """Manage reviewable product Memory through the durable ADK backend."""

    def __init__(
        self,
        *,
        store: GmScienceStore,
        backend: SQLiteMemoryService,
        app_name: str = GM_SCIENCE_MEMORY_APP_NAME,
    ) -> None:
        self.store = store
        self.backend = backend
        self.app_name = app_name

    def _project(self, project_id: str):
        project = self.store.get_project(str(project_id or "").strip())
        if project is None:
            raise ValueError(f"Project '{project_id}' was not found.")
        return project

    @staticmethod
    def _scope(raw: Any) -> str:
        scope = str(raw or "").strip().lower()
        if scope not in _MEMORY_SCOPES:
            raise ValueError("Memory scope must be user or project.")
        return scope

    def _target_user_id(self, *, project_id: str, user_id: str, scope: str) -> str:
        return user_id if scope == "user" else project_memory_user_id(project_id)

    def _allowed_user_ids(self, *, project_id: str, user_id: str) -> tuple[str, str]:
        return user_id, project_memory_user_id(project_id)

    @staticmethod
    def _scope_for_user_id(*, project_id: str, user_id: str, target_user_id: str) -> str:
        if target_user_id == user_id:
            return "user"
        if target_user_id == project_memory_user_id(project_id):
            return "project"
        raise ValueError("Memory note was not found in this Project.")

    def _note_payload(
        self,
        row: Mapping[str, Any],
        *,
        project_id: str,
        user_id: str,
        usage: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        scope = self._scope_for_user_id(
            project_id=project_id,
            user_id=user_id,
            target_user_id=str(row["user_id"]),
        )
        metadata = dict(row.get("metadata") or {})
        source_session_id = str(metadata.get("session_id") or row.get("session_id") or "")
        if source_session_id == _ADK_UNKNOWN_SESSION_ID:
            source_session_id = ""
        return {
            "id": str(row["id"]),
            "scope": scope,
            "category": str(row["category"]),
            "text": str(row["text"]),
            "created_at": _iso_from_ms(int(row["created_at_ms"])),
            "updated_at": _iso_from_ms(int(row["updated_at_ms"])),
            "provenance": {
                "source": str(metadata.get("source") or "manual"),
                "project_id": str(metadata.get("project_id") or (project_id if scope == "project" else "")),
                "session_id": source_session_id,
                "model": str(metadata.get("model") or ""),
                "candidate_id": str(metadata.get("candidate_id") or ""),
                "rationale": str(metadata.get("rationale") or ""),
            },
            "usage": dict(usage or {"count": 0, "session_ids": [], "last_used_at_ms": 0}),
        }

    def _candidate_payload(self, row: Mapping[str, Any]) -> dict[str, Any]:
        return {
            "id": str(row["id"]),
            "scope": str(row["scope"]),
            "category": str(row["category"]),
            "text": str(row["text"]),
            "rationale": str(row["rationale"]),
            "status": str(row["status"]),
            "project_id": str(row["project_id"]),
            "source_session_id": str(row["source_session_id"]),
            "model": str(row["model"]),
            "approved_note_id": str(row["approved_fact_id"]),
            "created_at": _iso_from_ms(int(row["created_at_ms"])),
            "reviewed_at": _iso_from_ms(int(row["reviewed_at_ms"])),
        }

    def get_workspace(self, *, project_id: str, user_id: str) -> dict[str, Any]:
        """Return User and current-Project notes plus review candidates."""

        project = self._project(project_id)
        principal = _bounded_text(user_id, field="user_id", limit=300)
        allowed = self._allowed_user_ids(project_id=project.id, user_id=principal)
        rows = self.backend.list_managed_memories(
            app_name=self.app_name,
            user_ids=allowed,
        )
        usage = self.backend.memory_usage(
            app_name=self.app_name,
            note_ids=[str(row["id"]) for row in rows],
        )
        notes = [
            self._note_payload(
                row,
                project_id=project.id,
                user_id=principal,
                usage=usage.get(str(row["id"])),
            )
            for row in rows
        ]
        candidate_rows = self.backend.list_memory_candidates(
            app_name=self.app_name,
            target_user_ids=allowed,
        )
        candidates = [self._candidate_payload(row) for row in candidate_rows]
        categories = sorted({str(item["category"]) for item in [*notes, *candidates]})
        return {
            "project_id": project.id,
            "notes": notes,
            "candidates": candidates,
            "categories": categories,
        }

    def create_note(
        self,
        *,
        project_id: str,
        user_id: str,
        scope: str,
        category: str,
        text: str,
    ) -> dict[str, Any]:
        """Create an explicitly approved manual Memory note."""

        project = self._project(project_id)
        principal = _bounded_text(user_id, field="user_id", limit=300)
        resolved_scope = self._scope(scope)
        resolved_category = _bounded_text(category, field="Memory category", limit=_MAX_CATEGORY_CHARS)
        resolved_text = _bounded_text(text, field="Memory text", limit=_MAX_TEXT_CHARS)
        row = self.backend.create_managed_memory(
            app_name=self.app_name,
            user_id=self._target_user_id(
                project_id=project.id,
                user_id=principal,
                scope=resolved_scope,
            ),
            category=resolved_category,
            text=resolved_text,
            metadata={
                "source": "manual",
                "project_id": project.id if resolved_scope == "project" else "",
            },
        )
        return self._note_payload(row, project_id=project.id, user_id=principal)

    def update_note(
        self,
        *,
        project_id: str,
        user_id: str,
        note_id: str,
        category: str,
        text: str,
    ) -> dict[str, Any]:
        """Edit one note visible in the User/current-Project workspace."""

        project = self._project(project_id)
        principal = _bounded_text(user_id, field="user_id", limit=300)
        row = self.backend.update_managed_memory(
            app_name=self.app_name,
            allowed_user_ids=self._allowed_user_ids(project_id=project.id, user_id=principal),
            note_id=_bounded_text(note_id, field="Memory note ID", limit=300),
            category=_bounded_text(category, field="Memory category", limit=_MAX_CATEGORY_CHARS),
            text=_bounded_text(text, field="Memory text", limit=_MAX_TEXT_CHARS),
        )
        if row is None:
            raise ValueError("Memory note was not found in this Project.")
        return self._note_payload(row, project_id=project.id, user_id=principal)

    def delete_note(self, *, project_id: str, user_id: str, note_id: str) -> None:
        """Delete one note visible in the User/current-Project workspace."""

        project = self._project(project_id)
        principal = _bounded_text(user_id, field="user_id", limit=300)
        deleted = self.backend.delete_managed_memory(
            app_name=self.app_name,
            allowed_user_ids=self._allowed_user_ids(project_id=project.id, user_id=principal),
            note_id=_bounded_text(note_id, field="Memory note ID", limit=300),
        )
        if not deleted:
            raise ValueError("Memory note was not found in this Project.")

    def clear_scope(self, *, project_id: str, user_id: str, scope: str) -> int:
        """Clear all approved notes in exactly one User or Project scope."""

        project = self._project(project_id)
        principal = _bounded_text(user_id, field="user_id", limit=300)
        resolved_scope = self._scope(scope)
        return self.backend.clear_managed_memories(
            app_name=self.app_name,
            user_id=self._target_user_id(
                project_id=project.id,
                user_id=principal,
                scope=resolved_scope,
            ),
        )

    def propose_candidate(
        self,
        *,
        project_id: str,
        user_id: str,
        session_id: str,
        scope: str,
        category: str,
        text: str,
        rationale: str,
        model: str,
    ) -> dict[str, Any]:
        """Create a reviewable candidate that is not yet recallable."""

        project = self._project(project_id)
        principal = _bounded_text(user_id, field="user_id", limit=300)
        resolved_scope = self._scope(scope)
        row = self.backend.create_memory_candidate(
            app_name=self.app_name,
            target_user_id=self._target_user_id(
                project_id=project.id,
                user_id=principal,
                scope=resolved_scope,
            ),
            scope=resolved_scope,
            project_id=project.id,
            category=_bounded_text(category, field="Memory category", limit=_MAX_CATEGORY_CHARS),
            text=_bounded_text(text, field="Memory text", limit=_MAX_TEXT_CHARS),
            rationale=_bounded_text(rationale, field="Memory rationale", limit=_MAX_RATIONALE_CHARS),
            source_session_id=_bounded_text(session_id, field="Session ID", limit=300),
            source_user_id=principal,
            model=str(model or "").strip()[:300],
        )
        return self._candidate_payload(row)

    def review_candidate(
        self,
        *,
        project_id: str,
        user_id: str,
        candidate_id: str,
        decision: str,
    ) -> dict[str, Any]:
        """Approve or reject a candidate visible in this workspace."""

        project = self._project(project_id)
        principal = _bounded_text(user_id, field="user_id", limit=300)
        resolved_decision = str(decision or "").strip().lower()
        if resolved_decision not in _MEMORY_DECISIONS:
            raise ValueError("Memory candidate decision must be approve or reject.")
        row = self.backend.review_memory_candidate(
            app_name=self.app_name,
            allowed_target_user_ids=self._allowed_user_ids(project_id=project.id, user_id=principal),
            candidate_id=_bounded_text(candidate_id, field="Memory candidate ID", limit=300),
            decision=resolved_decision,
        )
        if row is None:
            raise ValueError("Memory candidate was not found in this Project.")
        if row["scope"] == "project" and row["project_id"] != project.id:
            raise ValueError("Memory candidate was not found in this Project.")
        return self._candidate_payload(row)


class ProjectScopedMemoryService(BaseMemoryService):
    """ADK MemoryService view that merges one User with one Project scope.

    Event ingestion is intentionally a no-op: gm-science only persists manual
    notes or user-approved candidates.
    """

    def __init__(
        self,
        *,
        backend: SQLiteMemoryService,
        project_id: str,
        session_id: str,
    ) -> None:
        self.backend = backend
        self.project_id = project_id
        self.session_id = session_id

    async def add_session_to_memory(self, session: object) -> None:
        """Ignore automatic Session ingestion in review-before-save mode."""

        _ = session

    async def add_events_to_memory(
        self,
        *,
        app_name: str,
        user_id: str,
        events: Sequence[object],
        session_id: str | None = None,
        custom_metadata: Mapping[str, object] | None = None,
    ) -> None:
        """Ignore automatic event ingestion in review-before-save mode."""

        _ = (app_name, user_id, events, session_id, custom_metadata)

    async def add_memory(
        self,
        *,
        app_name: str,
        user_id: str,
        memories: Sequence[MemoryEntry],
        custom_metadata: Mapping[str, object] | None = None,
    ) -> None:
        """Delegate explicit ADK writes to the User scope."""

        await self.backend.add_memory(
            app_name=app_name,
            user_id=user_id,
            memories=memories,
            custom_metadata=custom_metadata,
        )

    @staticmethod
    def _annotate(memory: MemoryEntry, *, scope: str, project_id: str) -> MemoryEntry:
        metadata = dict(memory.custom_metadata or {})
        metadata["memory_scope"] = scope
        if scope == "project":
            metadata["project_id"] = project_id
        return MemoryEntry(
            id=memory.id,
            author=memory.author,
            timestamp=memory.timestamp,
            content=memory.content,
            custom_metadata=metadata,
        )

    async def search_memory(self, *, app_name: str, user_id: str, query: str) -> SearchMemoryResponse:
        """Merge User and current Project recall and record Session provenance."""

        user_response = await self.backend.search_memory(
            app_name=app_name,
            user_id=user_id,
            query=query,
        )
        project_response = await self.backend.search_memory(
            app_name=app_name,
            user_id=project_memory_user_id(self.project_id),
            query=query,
        )
        merged: list[MemoryEntry] = []
        seen: set[str] = set()
        for scope, response in (("user", user_response), ("project", project_response)):
            for memory in response.memories:
                memory_id = str(memory.id or "")
                if memory_id in seen:
                    continue
                seen.add(memory_id)
                merged.append(self._annotate(memory, scope=scope, project_id=self.project_id))
        merged.sort(key=lambda item: str(item.timestamp or ""), reverse=True)
        merged = merged[:12]
        self.backend.record_memory_recall(
            app_name=app_name,
            requester_user_id=user_id,
            project_id=self.project_id,
            session_id=self.session_id,
            query=query,
            memory_ids=[str(memory.id or "") for memory in merged],
        )
        return SearchMemoryResponse(memories=merged)


def science_propose_memory(
    scope: str,
    category: str,
    text: str,
    rationale: str,
    tool_context: ToolContext,
) -> dict[str, Any]:
    """Propose a User or Project Memory note for explicit user review.

    Args:
        scope: `user` for a personal preference/fact, or `project` for a
            convention that applies only to the current research Project.
        category: Short user-facing category such as `About you`,
            `Preferences`, or `Project context`.
        text: One self-contained durable fact or convention.
        rationale: Why this information is likely useful in future Sessions.

    Returns:
        A pending candidate. The candidate is not recallable until the user
        approves it in Memory settings.
    """

    if not env_enabled("OPENPPX_MEMORY_ENABLED", default=True):
        raise ValueError("Memory is disabled globally.")
    if not session_policy_from_env()["memory_enabled"]:
        raise ValueError("Memory is disabled for this Session.")
    project_id = str(os.getenv(GM_SCIENCE_PROJECT_ID_ENV, "") or "").strip()
    if not project_id:
        raise ValueError("Memory candidates require a current gm-science Project.")
    user_id = str(getattr(tool_context, "user_id", "") or "").strip()
    session = getattr(tool_context, "session", None)
    session_id = str(getattr(session, "id", "") or "").strip()
    if not user_id or not session_id:
        raise ValueError("Memory candidates require an active user and Session.")
    service = GmScienceMemoryService(
        store=GmScienceStore(),
        backend=SQLiteMemoryService(
            db_path=get_gm_science_data_dir() / "database" / "memory.db"
        ),
    )
    candidate = service.propose_candidate(
        project_id=project_id,
        user_id=user_id,
        session_id=session_id,
        scope=scope,
        category=category,
        text=text,
        rationale=rationale,
        model=str(os.getenv("OPENPPX_MODEL", "") or ""),
    )
    return {
        "status": "pending_review",
        "message": "Memory candidate created. It will not be recalled until the user approves it.",
        "candidate": candidate,
    }
