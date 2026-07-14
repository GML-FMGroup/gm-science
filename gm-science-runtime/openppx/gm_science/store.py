"""SQLite-backed store for gm-science projects and artifacts."""

from __future__ import annotations

import datetime as dt
import json
import sqlite3
import uuid
from pathlib import Path
from typing import Any, Iterator

from .models import ArtifactRecord, ProjectRecord
from .paths import get_gm_science_data_dir


def _utc_now() -> str:
    """Return the current UTC timestamp as ISO 8601 text."""

    return dt.datetime.now(dt.timezone.utc).isoformat()


def _json_dumps(value: Any) -> str:
    """Serialize JSON values deterministically for storage."""

    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _json_loads_dict(value: str | None) -> dict[str, Any]:
    """Load a JSON object from storage, returning an empty object on blanks."""

    if not value:
        return {}
    parsed = json.loads(value)
    return parsed if isinstance(parsed, dict) else {}


def _json_loads_list(value: str | None) -> list[str]:
    """Load a JSON string list from storage, returning an empty list on blanks."""

    if not value:
        return []
    parsed = json.loads(value)
    if not isinstance(parsed, list):
        return []
    return [str(item) for item in parsed]


class GmScienceStore:
    """Persist gm-science project and artifact metadata on local disk."""

    def __init__(self, root_dir: Path | str | None = None) -> None:
        self.root_dir = Path(root_dir).expanduser() if root_dir is not None else get_gm_science_data_dir()
        self.root_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = self.root_dir / "gm-science.db"
        self.workspaces_dir = self.root_dir / "workspaces"
        self.workspaces_dir.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def create_project(
        self,
        *,
        name: str,
        description: str,
        agent_context: str,
        workspace_path: str | None = None,
        enabled_skills: list[str] | None = None,
        enabled_connectors: list[str] | None = None,
        enabled_specialists: list[str] | None = None,
    ) -> ProjectRecord:
        """Create and persist one local research project."""

        project_name = str(name or "").strip()
        if not project_name:
            raise ValueError("Project name is required.")

        project_id = f"proj_{uuid.uuid4().hex[:16]}"
        workspace = Path(workspace_path).expanduser() if workspace_path else self.workspaces_dir / project_id
        workspace.mkdir(parents=True, exist_ok=True)
        timestamp = _utc_now()
        record = ProjectRecord(
            id=project_id,
            name=project_name,
            description=str(description or ""),
            agent_context=str(agent_context or ""),
            workspace_path=str(workspace),
            created_at=timestamp,
            updated_at=timestamp,
            enabled_skills=list(enabled_skills or []),
            enabled_connectors=list(enabled_connectors or []),
            enabled_specialists=list(enabled_specialists or []),
        )
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO gm_science_projects (
                    id, name, description, agent_context, workspace_path,
                    created_at, updated_at, enabled_skills, enabled_connectors,
                    enabled_specialists
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.id,
                    record.name,
                    record.description,
                    record.agent_context,
                    record.workspace_path,
                    record.created_at,
                    record.updated_at,
                    _json_dumps(record.enabled_skills),
                    _json_dumps(record.enabled_connectors),
                    _json_dumps(record.enabled_specialists),
                ),
            )
        return record

    def get_project(self, project_id: str) -> ProjectRecord | None:
        """Return one project by id, or None when it does not exist."""

        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM gm_science_projects WHERE id = ?",
                (project_id,),
            ).fetchone()
        return _project_from_row(row) if row is not None else None

    def list_projects(self) -> list[ProjectRecord]:
        """List projects ordered by most recent update first."""

        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM gm_science_projects ORDER BY updated_at DESC, created_at DESC"
            ).fetchall()
        return [_project_from_row(row) for row in rows]

    def update_project_capabilities(
        self,
        project_id: str,
        *,
        enabled_skills: list[str],
        enabled_connectors: list[str],
        enabled_specialists: list[str],
    ) -> ProjectRecord:
        """Replace one Project's capability allowlists and return the updated record."""

        if self.get_project(project_id) is None:
            raise ValueError(f"Project '{project_id}' was not found.")
        timestamp = _utc_now()
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE gm_science_projects
                SET enabled_skills = ?, enabled_connectors = ?, enabled_specialists = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    _json_dumps(enabled_skills),
                    _json_dumps(enabled_connectors),
                    _json_dumps(enabled_specialists),
                    timestamp,
                    project_id,
                ),
            )
        updated = self.get_project(project_id)
        if updated is None:
            raise RuntimeError(f"Project '{project_id}' disappeared during update.")
        return updated

    def create_artifact(
        self,
        *,
        project_id: str,
        artifact_type: str,
        title: str,
        path_or_url: str,
        mime_type: str = "",
        session_id: str | None = None,
        metadata: dict[str, Any] | None = None,
        provenance: dict[str, Any] | None = None,
    ) -> ArtifactRecord:
        """Create and persist one artifact for a project."""

        if self.get_project(project_id) is None:
            raise ValueError(f"Project '{project_id}' was not found.")
        normalized_type = str(artifact_type or "").strip()
        if not normalized_type:
            raise ValueError("Artifact type is required.")
        artifact_id = f"art_{uuid.uuid4().hex[:16]}"
        timestamp = _utc_now()
        record = ArtifactRecord(
            id=artifact_id,
            project_id=project_id,
            session_id=str(session_id) if session_id else None,
            type=normalized_type,
            title=str(title or "").strip() or normalized_type,
            path_or_url=str(path_or_url or ""),
            mime_type=str(mime_type or ""),
            metadata=dict(metadata or {}),
            provenance=dict(provenance or {}),
            created_at=timestamp,
            updated_at=timestamp,
        )
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO gm_science_artifacts (
                    id, project_id, session_id, type, title, path_or_url,
                    mime_type, metadata, provenance, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.id,
                    record.project_id,
                    record.session_id,
                    record.type,
                    record.title,
                    record.path_or_url,
                    record.mime_type,
                    _json_dumps(record.metadata),
                    _json_dumps(record.provenance),
                    record.created_at,
                    record.updated_at,
                ),
            )
            conn.execute(
                "UPDATE gm_science_projects SET updated_at = ? WHERE id = ?",
                (timestamp, project_id),
            )
        return record

    def list_artifacts(self, project_id: str) -> list[ArtifactRecord]:
        """List artifacts for one project ordered by creation time."""

        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM gm_science_artifacts
                WHERE project_id = ?
                ORDER BY created_at ASC, id ASC
                """,
                (project_id,),
            ).fetchall()
        return [_artifact_from_row(row) for row in rows]

    def get_artifact(self, artifact_id: str) -> ArtifactRecord | None:
        """Return one artifact by id, or None when it does not exist."""

        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM gm_science_artifacts WHERE id = ?",
                (artifact_id,),
            ).fetchone()
        return _artifact_from_row(row) if row is not None else None

    def update_artifact_metadata(self, artifact_id: str, metadata: dict[str, Any]) -> ArtifactRecord:
        """Replace artifact metadata and return the updated record."""

        artifact = self.get_artifact(artifact_id)
        if artifact is None:
            raise ValueError(f"Artifact '{artifact_id}' was not found.")
        timestamp = _utc_now()
        with self._connect() as conn:
            conn.execute(
                "UPDATE gm_science_artifacts SET metadata = ?, updated_at = ? WHERE id = ?",
                (_json_dumps(dict(metadata)), timestamp, artifact_id),
            )
            conn.execute(
                "UPDATE gm_science_projects SET updated_at = ? WHERE id = ?",
                (timestamp, artifact.project_id),
            )
        updated = self.get_artifact(artifact_id)
        if updated is None:
            raise RuntimeError(f"Artifact '{artifact_id}' disappeared during update.")
        return updated

    def find_paper_artifact(self, project_id: str, canonical_id: str) -> ArtifactRecord | None:
        """Find a canonical paper artifact within one project."""

        target = str(canonical_id or "").strip()
        if not target:
            return None
        return next(
            (
                artifact
                for artifact in self.list_artifacts(project_id)
                if artifact.type == "paper" and artifact.metadata.get("canonical_id") == target
            ),
            None,
        )

    def find_citation_artifact(
        self,
        project_id: str,
        report_artifact_id: str,
        paper_artifact_id: str,
    ) -> ArtifactRecord | None:
        """Find a citation linking one project report and paper."""

        return next(
            (
                artifact
                for artifact in self.list_artifacts(project_id)
                if artifact.type == "citation"
                and artifact.metadata.get("report_artifact_id") == report_artifact_id
                and artifact.metadata.get("paper_artifact_id") == paper_artifact_id
            ),
            None,
        )

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS gm_science_projects (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    description TEXT NOT NULL,
                    agent_context TEXT NOT NULL,
                    workspace_path TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    enabled_skills TEXT NOT NULL,
                    enabled_connectors TEXT NOT NULL,
                    enabled_specialists TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS gm_science_artifacts (
                    id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    session_id TEXT,
                    type TEXT NOT NULL,
                    title TEXT NOT NULL,
                    path_or_url TEXT NOT NULL,
                    mime_type TEXT NOT NULL,
                    metadata TEXT NOT NULL,
                    provenance TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY(project_id) REFERENCES gm_science_projects(id) ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS idx_gm_science_artifacts_project
                ON gm_science_artifacts(project_id, created_at);
                """
            )


def _project_from_row(row: sqlite3.Row) -> ProjectRecord:
    """Project one SQLite row into a ProjectRecord."""

    return ProjectRecord(
        id=str(row["id"]),
        name=str(row["name"]),
        description=str(row["description"]),
        agent_context=str(row["agent_context"]),
        workspace_path=str(row["workspace_path"]),
        created_at=str(row["created_at"]),
        updated_at=str(row["updated_at"]),
        enabled_skills=_json_loads_list(row["enabled_skills"]),
        enabled_connectors=_json_loads_list(row["enabled_connectors"]),
        enabled_specialists=_json_loads_list(row["enabled_specialists"]),
    )


def _artifact_from_row(row: sqlite3.Row) -> ArtifactRecord:
    """Project one SQLite row into an ArtifactRecord."""

    return ArtifactRecord(
        id=str(row["id"]),
        project_id=str(row["project_id"]),
        session_id=str(row["session_id"]) if row["session_id"] is not None else None,
        type=str(row["type"]),
        title=str(row["title"]),
        path_or_url=str(row["path_or_url"]),
        mime_type=str(row["mime_type"]),
        metadata=_json_loads_dict(row["metadata"]),
        provenance=_json_loads_dict(row["provenance"]),
        created_at=str(row["created_at"]),
        updated_at=str(row["updated_at"]),
    )
