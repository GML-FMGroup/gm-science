"""Read-only projection of Project artifacts and local files."""

from __future__ import annotations

import datetime as dt
import hashlib
import mimetypes
import os
from pathlib import Path
from typing import Any
from urllib.parse import SplitResult, urlsplit, urlunsplit

from ..models import ArtifactRecord
from ..store import GmScienceStore
from .config import ResourceCatalogConfig, load_resource_catalog_config
from .models import ResourceAccessMode, ResourceKind, ResourceRef

_MAX_SEARCH_QUERY_CHARS = 200


class ResourceCatalogService:
    """Build bounded, path-safe resource references from durable Project state."""

    def __init__(
        self,
        *,
        store: GmScienceStore,
        config_path: Path | None = None,
        config: ResourceCatalogConfig | None = None,
    ) -> None:
        self.store = store
        self.config = config or load_resource_catalog_config(config_path)

    def list_resources(self, project_id: str, *, query: str = "") -> list[ResourceRef]:
        """List and optionally search one Project's unified resource catalog."""

        if not self.config.enabled:
            raise ValueError("Project resource catalog is disabled by configuration.")
        project = self.store.get_project(project_id)
        if project is None:
            raise ValueError(f"Project '{project_id}' was not found.")
        normalized_query = str(query or "").strip()
        if len(normalized_query) > _MAX_SEARCH_QUERY_CHARS:
            raise ValueError(f"Search query exceeds {_MAX_SEARCH_QUERY_CHARS} characters.")

        workspace = Path(project.workspace_path).expanduser().resolve(strict=False)
        artifacts = self.store.list_artifacts(project.id)
        resources: list[ResourceRef] = []
        represented_paths: set[Path] = set()
        for artifact in artifacts:
            resource, represented_path = self._artifact_resource(artifact, workspace)
            if represented_path is not None:
                represented_paths.add(represented_path)
            if artifact.metadata.get("gm_science_hidden") is not True:
                resources.append(resource)
        resources.extend(self._workspace_resources(project.id, workspace, represented_paths))

        if normalized_query:
            needle = normalized_query.casefold()
            resources = [resource for resource in resources if needle in self._search_text(resource)]
        return sorted(resources, key=lambda item: (item.updated_at, item.id), reverse=True)

    def _artifact_resource(self, artifact: ArtifactRecord, workspace: Path) -> tuple[ResourceRef, Path | None]:
        """Project one durable Artifact without exposing its raw local path."""

        raw_location = str(artifact.path_or_url or "").strip()
        relative_path = ""
        public_url = ""
        represented_path: Path | None = None
        size_bytes: int | None = None
        access_mode: ResourceAccessMode = "metadata_only"
        parsed_url = urlsplit(raw_location)
        if parsed_url.scheme.lower() in {"http", "https"} and parsed_url.hostname:
            public_url = _safe_public_url(parsed_url)
            if public_url:
                access_mode = "external"
        elif raw_location:
            candidate = Path(raw_location).expanduser()
            if not candidate.is_absolute():
                candidate = workspace / candidate
            candidate = candidate.resolve(strict=False)
            if _is_within(candidate, workspace):
                represented_path = candidate
                relative_path = candidate.relative_to(workspace).as_posix()
                if candidate.is_file() and not candidate.is_symlink():
                    access_mode = "read"
                    try:
                        size_bytes = candidate.stat().st_size
                    except OSError:
                        size_bytes = None

        metadata = _safe_artifact_metadata(artifact)
        version_or_hash = _artifact_version(artifact)
        kind: ResourceKind = "artifact"
        if artifact.type == "dataset":
            kind = "dataset"
        elif metadata.get("task_id") or metadata.get("science_run_role"):
            kind = "run_output"
        return (
            ResourceRef(
                id=f"artifact:{artifact.id}",
                kind=kind,
                project_id=artifact.project_id,
                session_id=artifact.session_id,
                display_name=artifact.title,
                artifact_type=artifact.type,
                mime_type=artifact.mime_type,
                version_or_hash=version_or_hash,
                access_mode=access_mode,
                source="artifact",
                artifact_id=artifact.id,
                relative_path=relative_path,
                url=public_url,
                size_bytes=size_bytes,
                created_at=artifact.created_at,
                updated_at=artifact.updated_at,
                metadata=metadata,
            ),
            represented_path,
        )

    def _workspace_resources(
        self,
        project_id: str,
        workspace: Path,
        represented_paths: set[Path],
    ) -> list[ResourceRef]:
        """Discover ordinary Project files with deterministic traversal and strict bounds."""

        if not workspace.is_dir():
            return []
        resources: list[ResourceRef] = []
        inspected_files = 0

        def scan(directory: Path, depth: int) -> bool:
            nonlocal inspected_files
            try:
                with os.scandir(directory) as scanner:
                    entries = sorted(scanner, key=lambda item: item.name.casefold())
            except OSError:
                return False
            for entry in entries:
                if inspected_files >= self.config.max_workspace_files:
                    return True
                if entry.is_symlink():
                    continue
                if not self.config.include_hidden and entry.name.startswith("."):
                    continue
                if entry.is_dir(follow_symlinks=False):
                    if entry.name in self.config.excluded_directories:
                        continue
                    if depth < self.config.max_scan_depth and scan(Path(entry.path), depth + 1):
                        return True
                    continue
                if not entry.is_file(follow_symlinks=False):
                    continue
                inspected_files += 1
                path = Path(entry.path).resolve(strict=False)
                if not _is_within(path, workspace) or path in represented_paths:
                    continue
                try:
                    stat = path.stat()
                except OSError:
                    continue
                relative_path = path.relative_to(workspace).as_posix()
                timestamp = dt.datetime.fromtimestamp(stat.st_mtime, tz=dt.timezone.utc).isoformat()
                resource_id = hashlib.sha256(relative_path.encode("utf-8")).hexdigest()[:24]
                resources.append(
                    ResourceRef(
                        id=f"project_file:{resource_id}",
                        kind="project_file",
                        project_id=project_id,
                        session_id=None,
                        display_name=path.name,
                        artifact_type="project_file",
                        mime_type=mimetypes.guess_type(path.name)[0] or "application/octet-stream",
                        version_or_hash=f"{stat.st_mtime_ns}:{stat.st_size}",
                        access_mode="read",
                        source="workspace",
                        artifact_id="",
                        relative_path=relative_path,
                        url="",
                        size_bytes=stat.st_size,
                        created_at=timestamp,
                        updated_at=timestamp,
                    )
                )
            return False

        scan(workspace, 0)
        return resources

    @staticmethod
    def _search_text(resource: ResourceRef) -> str:
        return " ".join(
            (
                resource.display_name,
                resource.kind,
                resource.artifact_type,
                resource.mime_type,
                resource.relative_path,
            )
        ).casefold()


def _safe_artifact_metadata(artifact: ArtifactRecord) -> dict[str, Any]:
    metadata: dict[str, Any] = {}
    role = str(artifact.metadata.get("science_run_role") or "").strip()
    task_id = str(artifact.metadata.get("task_id") or artifact.provenance.get("task_id") or "").strip()
    if role:
        metadata["science_run_role"] = role
    if task_id:
        metadata["task_id"] = task_id
    if artifact.metadata.get("gm_science_starred") is True:
        metadata["starred"] = True
    return metadata


def _artifact_version(artifact: ArtifactRecord) -> str:
    for source in (artifact.metadata, artifact.provenance):
        for key in ("sha256", "source_sha256"):
            value = str(source.get(key) or "").strip()
            if value:
                return value
    return artifact.updated_at


def _safe_public_url(parsed: SplitResult) -> str:
    host = parsed.hostname or ""
    if ":" in host and not host.startswith("["):
        host = f"[{host}]"
    try:
        port = parsed.port
    except ValueError:
        return ""
    netloc = f"{host}:{port}" if port else host
    return urlunsplit((parsed.scheme.lower(), netloc, parsed.path, "", ""))


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True
