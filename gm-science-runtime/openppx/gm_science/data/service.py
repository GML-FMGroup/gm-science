"""Project-scoped dataset import, profiling, and Artifact projection."""

from __future__ import annotations

import hashlib
import json
import mimetypes
import shutil
import uuid
from pathlib import Path
from typing import Any

from ..models import ArtifactRecord, ProjectRecord
from ..store import GmScienceStore
from .config import DatasetConfig, load_dataset_config
from .profiler import detect_dataset_format, profile_dataset, profile_markdown


class DatasetService:
    """Import supported local tables into durable Project-owned Artifacts."""

    def __init__(
        self,
        *,
        store: GmScienceStore,
        config_path: Path | None = None,
        config: DatasetConfig | None = None,
    ) -> None:
        self.store = store
        self.config = config or load_dataset_config(config_path)

    def import_dataset(
        self,
        *,
        project_id: str,
        source_path: str,
        title: str = "",
        session_id: str | None = None,
    ) -> dict[str, Any]:
        """Copy, profile, and register one local table inside a Project workspace."""

        if not self.config.enabled:
            raise ValueError("Dataset import is disabled by configuration.")
        project = self._project(project_id)
        normalized_session_id = self._session(project, session_id)
        source = Path(str(source_path or "").strip()).expanduser().resolve(strict=False)
        if not source.is_file():
            raise ValueError(f"Dataset file '{source_path}' was not found.")
        dataset_format = detect_dataset_format(source)
        size_bytes = source.stat().st_size
        if size_bytes > self.config.max_file_size_bytes:
            raise ValueError(
                f"Dataset is {size_bytes} bytes; configured limit is {self.config.max_file_size_bytes} bytes."
            )

        dataset_key = f"dataset_{uuid.uuid4().hex[:16]}"
        workspace = Path(project.workspace_path).expanduser().resolve(strict=False)
        dataset_dir = (workspace / "datasets" / dataset_key).resolve(strict=False)
        self._require_within(dataset_dir, workspace)
        source_copy = dataset_dir / f"source{source.suffix.lower()}"
        try:
            dataset_dir.mkdir(parents=True, exist_ok=False)
            shutil.copy2(source, source_copy)
            profile = profile_dataset(source_copy, dataset_format, self.config)
            profile_path = dataset_dir / "profile.json"
            profile_path.write_text(
                json.dumps(profile, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            profile_markdown_path = dataset_dir / "profile.md"
            resolved_title = str(title or "").strip() or source.stem
            profile_markdown_path.write_text(
                profile_markdown(f"{resolved_title} profile", profile),
                encoding="utf-8",
            )
        except Exception:
            shutil.rmtree(dataset_dir, ignore_errors=True)
            raise

        source_hash = hashlib.sha256(source_copy.read_bytes()).hexdigest()
        dataset = self.store.create_artifact(
            project_id=project.id,
            session_id=normalized_session_id,
            artifact_type="dataset",
            title=resolved_title,
            path_or_url=str(source_copy),
            mime_type=mimetypes.guess_type(source_copy.name)[0] or "application/octet-stream",
            metadata={
                "dataset_key": dataset_key,
                "dataset_format": dataset_format,
                "source_name": source.name,
                "size_bytes": size_bytes,
                "sha256": source_hash,
                "row_count": profile["row_count"],
                "profiled_row_count": profile["profiled_row_count"],
                "column_count": profile["column_count"],
                "column_names": [column["name"] for column in profile["columns"]],
                "profile_path": str(profile_path),
                "profile_markdown_path": str(profile_markdown_path),
            },
            provenance={
                "created_by": "dataset_importer",
                "source_sha256": source_hash,
            },
        )
        profile_artifact = self.store.create_artifact(
            project_id=project.id,
            session_id=normalized_session_id,
            artifact_type="dataset_profile",
            title=f"{resolved_title} profile",
            path_or_url=str(profile_markdown_path),
            mime_type="text/markdown",
            metadata={
                "dataset_artifact_id": dataset.id,
                "profile_json_path": str(profile_path),
                "row_count": profile["row_count"],
                "column_count": profile["column_count"],
            },
            provenance={
                "created_by": "dataset_profiler",
                "source_artifact_ids": [dataset.id],
                "source_sha256": source_hash,
            },
        )
        dataset = self.store.update_artifact_metadata(
            dataset.id,
            {**dataset.metadata, "profile_artifact_id": profile_artifact.id},
        )
        return self._payload(project, dataset, include_profile=True)

    def list_datasets(self, project_id: str) -> list[dict[str, Any]]:
        """List Project datasets with compact profile summaries."""

        project = self._project(project_id)
        return [
            self._payload(project, artifact, include_profile=False)
            for artifact in reversed(self.store.list_artifacts(project.id))
            if artifact.type == "dataset"
        ]

    def get_dataset(self, project_id: str, artifact_id: str) -> dict[str, Any]:
        """Return one Project dataset with its full persisted profile."""

        project = self._project(project_id)
        artifact = self.store.get_artifact(str(artifact_id or "").strip())
        if artifact is None or artifact.project_id != project.id or artifact.type != "dataset":
            raise ValueError(f"Dataset artifact '{artifact_id}' was not found in Project '{project.id}'.")
        return self._payload(project, artifact, include_profile=True)

    def _payload(
        self,
        project: ProjectRecord,
        artifact: ArtifactRecord,
        *,
        include_profile: bool,
    ) -> dict[str, Any]:
        payload = {
            "artifact_id": artifact.id,
            "project_id": artifact.project_id,
            "session_id": artifact.session_id or "",
            "title": artifact.title,
            "path": artifact.path_or_url,
            "mime_type": artifact.mime_type,
            "format": str(artifact.metadata.get("dataset_format") or ""),
            "source_name": str(artifact.metadata.get("source_name") or ""),
            "size_bytes": int(artifact.metadata.get("size_bytes") or 0),
            "row_count": int(artifact.metadata.get("row_count") or 0),
            "profiled_row_count": int(artifact.metadata.get("profiled_row_count") or 0),
            "column_count": int(artifact.metadata.get("column_count") or 0),
            "column_names": list(artifact.metadata.get("column_names") or []),
            "profile_artifact_id": str(artifact.metadata.get("profile_artifact_id") or ""),
            "created_at": artifact.created_at,
            "updated_at": artifact.updated_at,
        }
        if include_profile:
            profile_path = Path(str(artifact.metadata.get("profile_path") or "")).expanduser().resolve(strict=False)
            workspace = Path(project.workspace_path).expanduser().resolve(strict=False)
            self._require_within(profile_path, workspace)
            if not profile_path.is_file():
                raise ValueError(f"Profile for Dataset artifact '{artifact.id}' was not found.")
            try:
                profile = json.loads(profile_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                raise ValueError(f"Profile for Dataset artifact '{artifact.id}' is invalid.") from exc
            payload["profile"] = profile
        return payload

    def _project(self, project_id: str) -> ProjectRecord:
        project = self.store.get_project(str(project_id or "").strip())
        if project is None:
            raise ValueError(f"Project '{project_id}' was not found.")
        return project

    def _session(self, project: ProjectRecord, session_id: str | None) -> str | None:
        normalized = str(session_id or "").strip() or None
        if normalized:
            association = self.store.get_project_session(normalized)
            if association is None or association.project_id != project.id:
                raise ValueError(f"Session '{normalized}' does not belong to Project '{project.id}'.")
        return normalized

    @staticmethod
    def _require_within(path: Path, root: Path) -> None:
        try:
            path.resolve(strict=False).relative_to(root.resolve(strict=False))
        except ValueError as exc:
            raise ValueError(f"Dataset path '{path}' is outside Project workspace '{root}'.") from exc
