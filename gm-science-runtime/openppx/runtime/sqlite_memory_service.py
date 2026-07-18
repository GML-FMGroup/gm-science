"""SQLite-backed long-term memory service for openppx."""

from __future__ import annotations

import json
import sqlite3
import threading
import time
import hashlib
import uuid
from collections.abc import Mapping
from collections.abc import Sequence
from dataclasses import asdict
from dataclasses import is_dataclass
from pathlib import Path
from typing import Any

from google.adk.memory.base_memory_service import BaseMemoryService, SearchMemoryResponse
from google.adk.memory.memory_entry import MemoryEntry
from google.genai import types

from .adk_storage_meta import ensure_adk_storage_meta_for_sqlite_path
from .memory_shared import (
    build_fact_key,
    content_text_for_memory,
    event_text_for_history,
    event_text_for_memory,
    event_timestamp_iso,
    infer_fact_category,
    is_user_author,
    memory_entry_text,
    now_iso,
    tokenize,
)

_UNKNOWN_SESSION_ID = "__unknown_session_id__"
_SEARCH_LIMIT = 12


def _now_ms() -> int:
    """Return current wall-clock milliseconds."""
    return int(time.time() * 1000)


def _connect(db_path: Path) -> sqlite3.Connection:
    """Open one SQLite connection with pragmatic defaults."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn


def _workspace_fallback_db_path(db_path: Path) -> Path:
    """Return the workspace-local fallback path for one SQLite database."""
    fallback = (Path.cwd() / ".openppx" / "database" / db_path.name).resolve(strict=False)
    fallback.parent.mkdir(parents=True, exist_ok=True)
    return fallback


def _prepare_db_path(db_path: Path) -> Path:
    """Return a writable SQLite path, falling back to workspace-local storage."""
    candidate = db_path.expanduser().resolve(strict=False)
    try:
        candidate.parent.mkdir(parents=True, exist_ok=True)
        return candidate
    except PermissionError:
        return _workspace_fallback_db_path(candidate)


def _json_dumps(payload: Any) -> str:
    """Serialize one JSON payload with permissive fallback behavior."""
    return json.dumps(payload, ensure_ascii=False, default=str)


def _json_loads(raw: str | None, *, default: Any) -> Any:
    """Deserialize JSON text with a caller-provided fallback."""
    if not raw:
        return default
    try:
        return json.loads(raw)
    except Exception:
        return default


def _serialize_content(content: object) -> str:
    """Serialize one content-like object to JSON when possible."""
    if content is None:
        return ""
    payload: Any
    if hasattr(content, "model_dump"):
        payload = content.model_dump(mode="json")
    elif is_dataclass(content):
        payload = asdict(content)
    elif isinstance(content, Mapping):
        payload = dict(content)
    else:
        return ""
    return _json_dumps(payload)


def _fallback_content(*, text: str, author: str | None) -> types.Content:
    """Build a plain text content object when structured content is unavailable."""
    role = "user" if is_user_author(author or "") else "model"
    return types.Content(role=role, parts=[types.Part(text=text)])


def _deserialize_content(*, raw_json: str, fallback_text: str, author: str | None) -> types.Content:
    """Deserialize stored content JSON or fall back to plain text content."""
    payload = _json_loads(raw_json, default=None)
    if isinstance(payload, dict):
        try:
            return types.Content.model_validate(payload)
        except Exception:
            pass
    return _fallback_content(text=fallback_text, author=author)


def _event_key(
    *,
    app_name: str,
    user_id: str,
    session_id: str,
    event_id: str,
    author: str,
    timestamp: str,
    text: str,
) -> str:
    """Build a stable event archive key for dedupe."""
    raw = "\n".join([app_name, user_id, session_id, event_id, author, timestamp, text])
    if event_id:
        return f"{app_name}:{user_id}:{session_id}:{event_id}"
    return f"archive:{hashlib.sha1(raw.encode('utf-8')).hexdigest()[:40]}"


def _scoped_fact_id(*, app_name: str, user_id: str, fact_key: str) -> str:
    """Build a fact ID that cannot collide across ADK memory scopes."""

    raw = "\n".join([app_name, user_id, fact_key])
    return f"fact:{hashlib.sha1(raw.encode('utf-8')).hexdigest()[:40]}"


def _memory_row_payload(row: sqlite3.Row) -> dict[str, Any]:
    """Project one managed fact row without exposing storage internals."""

    metadata = _json_loads(row["custom_metadata_json"], default={})
    if not isinstance(metadata, dict):
        metadata = {}
    return {
        "id": str(row["id"]),
        "app_name": str(row["app_name"]),
        "user_id": str(row["user_id"]),
        "session_id": str(row["session_id"] or ""),
        "category": str(row["category"]),
        "text": str(row["text"]),
        "timestamp": str(row["timestamp"] or ""),
        "metadata": metadata,
        "created_at_ms": int(row["created_at_ms"]),
        "updated_at_ms": int(row["updated_at_ms"]),
    }


def _candidate_row_payload(row: sqlite3.Row) -> dict[str, Any]:
    """Project one reviewable candidate row."""

    return {
        "id": str(row["id"]),
        "app_name": str(row["app_name"]),
        "target_user_id": str(row["target_user_id"]),
        "scope": str(row["scope"]),
        "project_id": str(row["project_id"] or ""),
        "category": str(row["category"]),
        "text": str(row["text"]),
        "rationale": str(row["rationale"]),
        "status": str(row["status"]),
        "source_session_id": str(row["source_session_id"] or ""),
        "source_user_id": str(row["source_user_id"] or ""),
        "model": str(row["model"] or ""),
        "approved_fact_id": str(row["approved_fact_id"] or ""),
        "created_at_ms": int(row["created_at_ms"]),
        "reviewed_at_ms": int(row["reviewed_at_ms"] or 0),
    }


class SQLiteMemoryService(BaseMemoryService):
    """SQLite-backed ADK memory service with facts plus raw archive index."""

    def __init__(self, *, db_path: str | Path):
        self._db_path = _prepare_db_path(Path(db_path))
        ensure_adk_storage_meta_for_sqlite_path(self._db_path)
        self._lock = threading.Lock()
        try:
            self._ensure_schema()
        except sqlite3.OperationalError:
            fallback = _workspace_fallback_db_path(self._db_path)
            if fallback == self._db_path:
                raise
            self._db_path = fallback
            self._ensure_schema()

    def _ensure_schema(self) -> None:
        """Create SQLite tables and indexes when missing."""
        with _connect(self._db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS memory_facts (
                    id TEXT PRIMARY KEY,
                    app_name TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    session_id TEXT,
                    fact_key TEXT NOT NULL,
                    author TEXT,
                    category TEXT NOT NULL,
                    text TEXT NOT NULL,
                    timestamp TEXT,
                    custom_metadata_json TEXT NOT NULL,
                    created_at_ms INTEGER NOT NULL,
                    updated_at_ms INTEGER NOT NULL,
                    UNIQUE(app_name, user_id, fact_key)
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS memory_archive_index (
                    id TEXT PRIMARY KEY,
                    app_name TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    session_id TEXT,
                    event_id TEXT,
                    author TEXT,
                    text TEXT NOT NULL,
                    timestamp TEXT,
                    content_json TEXT,
                    custom_metadata_json TEXT NOT NULL,
                    created_at_ms INTEGER NOT NULL
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_memory_facts_scope "
                "ON memory_facts(app_name, user_id, updated_at_ms DESC)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_memory_archive_scope "
                "ON memory_archive_index(app_name, user_id, created_at_ms DESC)"
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS memory_candidates (
                    id TEXT PRIMARY KEY,
                    app_name TEXT NOT NULL,
                    target_user_id TEXT NOT NULL,
                    scope TEXT NOT NULL,
                    project_id TEXT,
                    category TEXT NOT NULL,
                    text TEXT NOT NULL,
                    rationale TEXT NOT NULL,
                    status TEXT NOT NULL,
                    source_session_id TEXT,
                    source_user_id TEXT,
                    model TEXT,
                    approved_fact_id TEXT,
                    created_at_ms INTEGER NOT NULL,
                    reviewed_at_ms INTEGER
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_memory_candidates_scope "
                "ON memory_candidates(app_name, target_user_id, status, created_at_ms DESC)"
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS memory_recall_audit (
                    id TEXT PRIMARY KEY,
                    app_name TEXT NOT NULL,
                    requester_user_id TEXT NOT NULL,
                    project_id TEXT,
                    session_id TEXT,
                    query TEXT NOT NULL,
                    memory_ids_json TEXT NOT NULL,
                    created_at_ms INTEGER NOT NULL
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_memory_recall_notes "
                "ON memory_recall_audit(app_name, requester_user_id, created_at_ms DESC)"
            )

    @staticmethod
    def _upsert_managed_memory(
        conn: sqlite3.Connection,
        *,
        app_name: str,
        user_id: str,
        category: str,
        text: str,
        metadata: Mapping[str, object],
        note_id: str | None = None,
        created_at_ms: int | None = None,
    ) -> str:
        """Insert or update one approved fact and return its stable ID."""

        fact_key = build_fact_key(category=category, text=text)
        existing = conn.execute(
            "SELECT id, created_at_ms FROM memory_facts WHERE app_name = ? AND user_id = ? AND fact_key = ?",
            (app_name, user_id, fact_key),
        ).fetchone()
        resolved_id = str(existing["id"]) if existing is not None else (
            note_id or _scoped_fact_id(app_name=app_name, user_id=user_id, fact_key=fact_key)
        )
        resolved_created_at = (
            int(existing["created_at_ms"])
            if existing is not None
            else int(created_at_ms or _now_ms())
        )
        now_ms = _now_ms()
        timestamp = str(metadata.get("timestamp") or now_iso())
        session_id = str(metadata.get("session_id") or _UNKNOWN_SESSION_ID)
        conn.execute(
            """
            INSERT INTO memory_facts (
                id, app_name, user_id, session_id, fact_key, author, category,
                text, timestamp, custom_metadata_json, created_at_ms, updated_at_ms
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(app_name, user_id, fact_key) DO UPDATE SET
                session_id=excluded.session_id,
                author=excluded.author,
                category=excluded.category,
                text=excluded.text,
                timestamp=excluded.timestamp,
                custom_metadata_json=excluded.custom_metadata_json,
                updated_at_ms=excluded.updated_at_ms
            """,
            (
                resolved_id,
                app_name,
                user_id,
                session_id,
                fact_key,
                "memory",
                category,
                text,
                timestamp,
                _json_dumps(dict(metadata)),
                resolved_created_at,
                now_ms,
            ),
        )
        return resolved_id

    def create_managed_memory(
        self,
        *,
        app_name: str,
        user_id: str,
        category: str,
        text: str,
        metadata: Mapping[str, object] | None = None,
    ) -> dict[str, Any]:
        """Create one approved fact through the durable ADK memory store."""

        with self._lock, _connect(self._db_path) as conn:
            note_id = self._upsert_managed_memory(
                conn,
                app_name=app_name,
                user_id=user_id,
                category=category,
                text=text,
                metadata=metadata or {},
            )
            row = conn.execute("SELECT * FROM memory_facts WHERE id = ?", (note_id,)).fetchone()
        if row is None:  # pragma: no cover - transaction invariant
            raise RuntimeError("Managed memory was not persisted.")
        return _memory_row_payload(row)

    def list_managed_memories(
        self,
        *,
        app_name: str,
        user_ids: Sequence[str],
        limit: int = 500,
    ) -> list[dict[str, Any]]:
        """List approved facts for explicit ADK scopes."""

        scopes = [str(value).strip() for value in user_ids if str(value).strip()]
        if not app_name or not scopes or limit <= 0:
            return []
        placeholders = ", ".join("?" for _ in scopes)
        with self._lock, _connect(self._db_path) as conn:
            rows = conn.execute(
                f"SELECT * FROM memory_facts WHERE app_name = ? AND user_id IN ({placeholders}) "
                "ORDER BY updated_at_ms DESC LIMIT ?",
                [app_name, *scopes, int(limit)],
            ).fetchall()
        return [_memory_row_payload(row) for row in rows]

    def update_managed_memory(
        self,
        *,
        app_name: str,
        allowed_user_ids: Sequence[str],
        note_id: str,
        category: str,
        text: str,
        metadata: Mapping[str, object] | None = None,
    ) -> dict[str, Any] | None:
        """Update an approved fact while preserving its stable ID."""

        scopes = [str(value).strip() for value in allowed_user_ids if str(value).strip()]
        if not scopes:
            return None
        placeholders = ", ".join("?" for _ in scopes)
        with self._lock, _connect(self._db_path) as conn:
            current = conn.execute(
                f"SELECT * FROM memory_facts WHERE id = ? AND app_name = ? AND user_id IN ({placeholders})",
                [note_id, app_name, *scopes],
            ).fetchone()
            if current is None:
                return None
            fact_key = build_fact_key(category=category, text=text)
            duplicate = conn.execute(
                "SELECT id FROM memory_facts WHERE app_name = ? AND user_id = ? AND fact_key = ? AND id <> ?",
                (app_name, current["user_id"], fact_key, note_id),
            ).fetchone()
            if duplicate is not None:
                raise ValueError("An identical memory note already exists in this scope.")
            merged_metadata = _json_loads(current["custom_metadata_json"], default={})
            if not isinstance(merged_metadata, dict):
                merged_metadata = {}
            merged_metadata.update(dict(metadata or {}))
            conn.execute(
                """
                UPDATE memory_facts
                SET fact_key = ?, category = ?, text = ?, timestamp = ?,
                    custom_metadata_json = ?, updated_at_ms = ?
                WHERE id = ?
                """,
                (
                    fact_key,
                    category,
                    text,
                    now_iso(),
                    _json_dumps(merged_metadata),
                    _now_ms(),
                    note_id,
                ),
            )
            conn.execute(
                "DELETE FROM memory_archive_index WHERE app_name = ? AND user_id = ? AND event_id = ?",
                (app_name, current["user_id"], note_id),
            )
            row = conn.execute("SELECT * FROM memory_facts WHERE id = ?", (note_id,)).fetchone()
        return _memory_row_payload(row) if row is not None else None

    def delete_managed_memory(
        self,
        *,
        app_name: str,
        allowed_user_ids: Sequence[str],
        note_id: str,
    ) -> bool:
        """Delete one approved fact and its explicit-memory archive row."""

        scopes = [str(value).strip() for value in allowed_user_ids if str(value).strip()]
        if not scopes:
            return False
        placeholders = ", ".join("?" for _ in scopes)
        with self._lock, _connect(self._db_path) as conn:
            row = conn.execute(
                f"SELECT user_id FROM memory_facts WHERE id = ? AND app_name = ? AND user_id IN ({placeholders})",
                [note_id, app_name, *scopes],
            ).fetchone()
            if row is None:
                return False
            conn.execute("DELETE FROM memory_facts WHERE id = ?", (note_id,))
            conn.execute(
                "DELETE FROM memory_archive_index WHERE app_name = ? AND user_id = ? AND event_id = ?",
                (app_name, row["user_id"], note_id),
            )
        return True

    def clear_managed_memories(self, *, app_name: str, user_id: str) -> int:
        """Delete all approved facts for exactly one ADK memory scope."""

        with self._lock, _connect(self._db_path) as conn:
            fact_ids = [
                str(row["id"])
                for row in conn.execute(
                    "SELECT id FROM memory_facts WHERE app_name = ? AND user_id = ?",
                    (app_name, user_id),
                ).fetchall()
            ]
            conn.execute(
                "DELETE FROM memory_facts WHERE app_name = ? AND user_id = ?",
                (app_name, user_id),
            )
            if fact_ids:
                placeholders = ", ".join("?" for _ in fact_ids)
                conn.execute(
                    f"DELETE FROM memory_archive_index WHERE app_name = ? AND user_id = ? AND event_id IN ({placeholders})",
                    [app_name, user_id, *fact_ids],
                )
        return len(fact_ids)

    def create_memory_candidate(
        self,
        *,
        app_name: str,
        target_user_id: str,
        scope: str,
        project_id: str,
        category: str,
        text: str,
        rationale: str,
        source_session_id: str,
        source_user_id: str,
        model: str,
    ) -> dict[str, Any]:
        """Persist a reviewable candidate without making it recallable."""

        with self._lock, _connect(self._db_path) as conn:
            existing = conn.execute(
                """
                SELECT * FROM memory_candidates
                WHERE app_name = ? AND target_user_id = ? AND category = ? AND text = ? AND status = 'pending'
                ORDER BY created_at_ms DESC LIMIT 1
                """,
                (app_name, target_user_id, category, text),
            ).fetchone()
            if existing is not None:
                return _candidate_row_payload(existing)
            candidate_id = f"memory_candidate:{uuid.uuid4().hex}"
            conn.execute(
                """
                INSERT INTO memory_candidates (
                    id, app_name, target_user_id, scope, project_id, category,
                    text, rationale, status, source_session_id, source_user_id,
                    model, approved_fact_id, created_at_ms, reviewed_at_ms
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?, ?, '', ?, NULL)
                """,
                (
                    candidate_id,
                    app_name,
                    target_user_id,
                    scope,
                    project_id,
                    category,
                    text,
                    rationale,
                    source_session_id,
                    source_user_id,
                    model,
                    _now_ms(),
                ),
            )
            row = conn.execute("SELECT * FROM memory_candidates WHERE id = ?", (candidate_id,)).fetchone()
        if row is None:  # pragma: no cover - transaction invariant
            raise RuntimeError("Memory candidate was not persisted.")
        return _candidate_row_payload(row)

    def list_memory_candidates(
        self,
        *,
        app_name: str,
        target_user_ids: Sequence[str],
        limit: int = 500,
    ) -> list[dict[str, Any]]:
        """List candidate lifecycle records for explicit target scopes."""

        scopes = [str(value).strip() for value in target_user_ids if str(value).strip()]
        if not scopes or limit <= 0:
            return []
        placeholders = ", ".join("?" for _ in scopes)
        with self._lock, _connect(self._db_path) as conn:
            rows = conn.execute(
                f"SELECT * FROM memory_candidates WHERE app_name = ? AND target_user_id IN ({placeholders}) "
                "ORDER BY created_at_ms DESC LIMIT ?",
                [app_name, *scopes, int(limit)],
            ).fetchall()
        return [_candidate_row_payload(row) for row in rows]

    def review_memory_candidate(
        self,
        *,
        app_name: str,
        allowed_target_user_ids: Sequence[str],
        candidate_id: str,
        decision: str,
    ) -> dict[str, Any] | None:
        """Approve or reject one pending candidate atomically."""

        scopes = [str(value).strip() for value in allowed_target_user_ids if str(value).strip()]
        if not scopes:
            return None
        placeholders = ", ".join("?" for _ in scopes)
        with self._lock, _connect(self._db_path) as conn:
            row = conn.execute(
                f"SELECT * FROM memory_candidates WHERE id = ? AND app_name = ? AND target_user_id IN ({placeholders})",
                [candidate_id, app_name, *scopes],
            ).fetchone()
            if row is None:
                return None
            if row["status"] != "pending":
                raise ValueError("Memory candidate has already been reviewed.")
            approved_fact_id = ""
            if decision == "approve":
                approved_fact_id = self._upsert_managed_memory(
                    conn,
                    app_name=app_name,
                    user_id=str(row["target_user_id"]),
                    category=str(row["category"]),
                    text=str(row["text"]),
                    metadata={
                        "source": "candidate_review",
                        "candidate_id": candidate_id,
                        "session_id": str(row["source_session_id"] or ""),
                        "project_id": str(row["project_id"] or ""),
                        "model": str(row["model"] or ""),
                        "rationale": str(row["rationale"] or ""),
                    },
                )
            conn.execute(
                "UPDATE memory_candidates SET status = ?, approved_fact_id = ?, reviewed_at_ms = ? WHERE id = ?",
                ("approved" if decision == "approve" else "rejected", approved_fact_id, _now_ms(), candidate_id),
            )
            reviewed = conn.execute("SELECT * FROM memory_candidates WHERE id = ?", (candidate_id,)).fetchone()
        return _candidate_row_payload(reviewed) if reviewed is not None else None

    def record_memory_recall(
        self,
        *,
        app_name: str,
        requester_user_id: str,
        project_id: str,
        session_id: str,
        query: str,
        memory_ids: Sequence[str],
    ) -> None:
        """Record which approved facts were supplied to one Session recall."""

        normalized_ids = list(dict.fromkeys(str(value) for value in memory_ids if str(value)))
        if not normalized_ids:
            return
        with self._lock, _connect(self._db_path) as conn:
            conn.execute(
                """
                INSERT INTO memory_recall_audit (
                    id, app_name, requester_user_id, project_id, session_id,
                    query, memory_ids_json, created_at_ms
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    f"memory_recall:{uuid.uuid4().hex}",
                    app_name,
                    requester_user_id,
                    project_id,
                    session_id,
                    query,
                    _json_dumps(normalized_ids),
                    _now_ms(),
                ),
            )

    def memory_usage(self, *, app_name: str, note_ids: Sequence[str]) -> dict[str, dict[str, Any]]:
        """Return bounded Session-level recall provenance for approved facts."""

        requested = {str(value) for value in note_ids if str(value)}
        result = {note_id: {"count": 0, "session_ids": [], "last_used_at_ms": 0} for note_id in requested}
        if not requested:
            return result
        with self._lock, _connect(self._db_path) as conn:
            rows = conn.execute(
                "SELECT session_id, memory_ids_json, created_at_ms FROM memory_recall_audit "
                "WHERE app_name = ? ORDER BY created_at_ms DESC LIMIT 1000",
                (app_name,),
            ).fetchall()
        sessions: dict[str, set[str]] = {note_id: set() for note_id in requested}
        for row in rows:
            memory_ids = _json_loads(row["memory_ids_json"], default=[])
            if not isinstance(memory_ids, list):
                continue
            for note_id in requested.intersection(str(value) for value in memory_ids):
                result[note_id]["count"] += 1
                result[note_id]["last_used_at_ms"] = max(
                    int(result[note_id]["last_used_at_ms"]), int(row["created_at_ms"])
                )
                session_id = str(row["session_id"] or "")
                if session_id:
                    sessions[note_id].add(session_id)
        for note_id in requested:
            result[note_id]["session_ids"] = sorted(sessions[note_id])
        return result

    async def add_session_to_memory(self, session: object) -> None:
        """Ingest all events from one session."""
        await self.add_events_to_memory(
            app_name=getattr(session, "app_name", ""),
            user_id=getattr(session, "user_id", ""),
            session_id=getattr(session, "id", None),
            events=getattr(session, "events", []),
        )

    async def add_events_to_memory(
        self,
        *,
        app_name: str,
        user_id: str,
        events: Sequence[object],
        session_id: str | None = None,
        custom_metadata: Mapping[str, object] | None = None,
    ) -> None:
        """Ingest incremental event deltas into facts and raw archive tables."""
        if not app_name or not user_id or not events:
            return

        scoped_session_id = (session_id or _UNKNOWN_SESSION_ID).strip() or _UNKNOWN_SESSION_ID
        metadata_json = _json_dumps(dict(custom_metadata or {}))
        now_ms = _now_ms()

        with self._lock, _connect(self._db_path) as conn:
            for event in events:
                archive_text = event_text_for_history(event)
                fact_text = event_text_for_memory(event)
                if not archive_text and not fact_text:
                    continue

                timestamp = event_timestamp_iso(event)
                author = str(getattr(event, "author", "") or "").strip() or "unknown"
                event_id = str(getattr(event, "id", "") or "").strip()
                event_key = _event_key(
                    app_name=app_name,
                    user_id=user_id,
                    session_id=scoped_session_id,
                    event_id=event_id,
                    author=author,
                    timestamp=timestamp,
                    text=archive_text or fact_text,
                )
                conn.execute(
                    """
                    INSERT OR IGNORE INTO memory_archive_index (
                        id,
                        app_name,
                        user_id,
                        session_id,
                        event_id,
                        author,
                        text,
                        timestamp,
                        content_json,
                        custom_metadata_json,
                        created_at_ms
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        event_key,
                        app_name,
                        user_id,
                        scoped_session_id,
                        event_id or None,
                        author,
                        archive_text or fact_text,
                        timestamp,
                        _serialize_content(getattr(event, "content", None)),
                        metadata_json,
                        now_ms,
                    ),
                )

                if not fact_text or not is_user_author(author):
                    continue
                category = infer_fact_category(fact_text)
                if not category:
                    continue
                fact_key = build_fact_key(category=category, text=fact_text)
                fact_id = _scoped_fact_id(
                    app_name=app_name,
                    user_id=user_id,
                    fact_key=fact_key,
                )
                conn.execute(
                    """
                    INSERT INTO memory_facts (
                        id,
                        app_name,
                        user_id,
                        session_id,
                        fact_key,
                        author,
                        category,
                        text,
                        timestamp,
                        custom_metadata_json,
                        created_at_ms,
                        updated_at_ms
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(app_name, user_id, fact_key) DO UPDATE SET
                        session_id=excluded.session_id,
                        author=excluded.author,
                        text=excluded.text,
                        timestamp=excluded.timestamp,
                        custom_metadata_json=excluded.custom_metadata_json,
                        updated_at_ms=excluded.updated_at_ms
                    """,
                    (
                        fact_id,
                        app_name,
                        user_id,
                        scoped_session_id,
                        fact_key,
                        author,
                        category,
                        fact_text,
                        timestamp,
                        metadata_json,
                        now_ms,
                        now_ms,
                    ),
                )

    async def add_memory(
        self,
        *,
        app_name: str,
        user_id: str,
        memories: Sequence[MemoryEntry],
        custom_metadata: Mapping[str, object] | None = None,
    ) -> None:
        """Persist explicit memory entries directly into the facts table."""
        if not app_name or not user_id or not memories:
            return

        write_metadata = dict(custom_metadata or {})
        base_session_id = str(write_metadata.get("session_id", _UNKNOWN_SESSION_ID) or _UNKNOWN_SESSION_ID)
        base_timestamp = str(write_metadata.get("dialogue_timestamp", "") or "").strip()
        now_ms = _now_ms()

        with self._lock, _connect(self._db_path) as conn:
            for memory in memories:
                text = memory_entry_text(memory)
                if not text:
                    continue
                if isinstance(memory, MemoryEntry):
                    merged_metadata = dict(write_metadata)
                    merged_metadata.update(memory.custom_metadata or {})
                    author = str(memory.author or "memory")
                    timestamp = str(memory.timestamp or base_timestamp or now_iso())
                    content_json = _serialize_content(memory.content)
                else:
                    merged_metadata = dict(write_metadata)
                    author = "memory"
                    timestamp = base_timestamp or now_iso()
                    content_json = ""
                category = str(merged_metadata.get("category") or infer_fact_category(text) or "context")
                fact_key = build_fact_key(category=category, text=text)
                fact_id = _scoped_fact_id(
                    app_name=app_name,
                    user_id=user_id,
                    fact_key=fact_key,
                )
                session_id = str(merged_metadata.get("session_id") or base_session_id)
                metadata_json = _json_dumps(merged_metadata)
                conn.execute(
                    """
                    INSERT INTO memory_facts (
                        id,
                        app_name,
                        user_id,
                        session_id,
                        fact_key,
                        author,
                        category,
                        text,
                        timestamp,
                        custom_metadata_json,
                        created_at_ms,
                        updated_at_ms
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(app_name, user_id, fact_key) DO UPDATE SET
                        session_id=excluded.session_id,
                        author=excluded.author,
                        text=excluded.text,
                        timestamp=excluded.timestamp,
                        custom_metadata_json=excluded.custom_metadata_json,
                        updated_at_ms=excluded.updated_at_ms
                    """,
                    (
                        fact_id,
                        app_name,
                        user_id,
                        session_id,
                        fact_key,
                        author,
                        category,
                        text,
                        timestamp,
                        metadata_json,
                        now_ms,
                        now_ms,
                    ),
                )
                if content_json:
                    archive_id = f"memory:{fact_key}"
                    conn.execute(
                        """
                        INSERT OR IGNORE INTO memory_archive_index (
                            id,
                            app_name,
                            user_id,
                            session_id,
                            event_id,
                            author,
                            text,
                            timestamp,
                            content_json,
                            custom_metadata_json,
                            created_at_ms
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            archive_id,
                            app_name,
                            user_id,
                            session_id,
                            fact_id,
                            author,
                            text,
                            timestamp,
                            content_json,
                            metadata_json,
                            now_ms,
                        ),
                    )

    async def search_memory(self, *, app_name: str, user_id: str, query: str) -> SearchMemoryResponse:
        """Search facts first, then fall back to raw archive text for self recall."""
        response = SearchMemoryResponse()
        query_tokens = tokenize(query)
        if not app_name or not user_id or not query_tokens:
            return response

        seen_ids: set[str] = set()
        with self._lock, _connect(self._db_path) as conn:
            fact_rows = conn.execute(
                """
                SELECT id, author, category, text, timestamp, custom_metadata_json
                FROM memory_facts
                WHERE app_name = ? AND user_id = ?
                ORDER BY updated_at_ms DESC
                LIMIT 200
                """,
                (app_name, user_id),
            ).fetchall()
            for row in fact_rows:
                text = str(row["text"] or "")
                if query_tokens.isdisjoint(tokenize(text)):
                    continue
                memory_id = str(row["id"])
                if memory_id in seen_ids:
                    continue
                metadata = _json_loads(row["custom_metadata_json"], default={})
                if not isinstance(metadata, dict):
                    metadata = {}
                metadata.setdefault("source", "fact")
                metadata.setdefault("category", row["category"])
                response.memories.append(
                    MemoryEntry(
                        id=memory_id,
                        author=row["author"],
                        timestamp=row["timestamp"],
                        custom_metadata=metadata,
                        content=_fallback_content(text=text, author=row["author"]),
                    )
                )
                seen_ids.add(memory_id)
                if len(response.memories) >= _SEARCH_LIMIT:
                    return response

            if response.memories:
                return response

            archive_rows = conn.execute(
                """
                SELECT id, author, text, timestamp, content_json, custom_metadata_json
                FROM memory_archive_index
                WHERE app_name = ? AND user_id = ?
                ORDER BY created_at_ms DESC
                LIMIT 300
                """,
                (app_name, user_id),
            ).fetchall()
            for row in archive_rows:
                text = str(row["text"] or "")
                if query_tokens.isdisjoint(tokenize(text)):
                    continue
                memory_id = str(row["id"])
                if memory_id in seen_ids:
                    continue
                metadata = _json_loads(row["custom_metadata_json"], default={})
                if not isinstance(metadata, dict):
                    metadata = {}
                metadata.setdefault("source", "archive")
                response.memories.append(
                    MemoryEntry(
                        id=memory_id,
                        author=row["author"],
                        timestamp=row["timestamp"],
                        custom_metadata=metadata,
                        content=_deserialize_content(
                            raw_json=str(row["content_json"] or ""),
                            fallback_text=text,
                            author=row["author"],
                        ),
                    )
                )
                seen_ids.add(memory_id)
                if len(response.memories) >= _SEARCH_LIMIT:
                    break

        return response
