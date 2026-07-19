"""Durable Project file and folder imports for the Files surface."""

from __future__ import annotations

import datetime as dt
import json
import os
import re
import shutil
import threading
import uuid
from pathlib import Path
from typing import Any, Literal

from ..store import GmScienceStore

ProjectSourceKind = Literal["file", "folder"]

_MAX_IMPORTED_FILES = 2_000
_MAX_IMPORTED_BYTES = 512 * 1024 * 1024
_MANIFEST_SCHEMA_VERSION = 1
_SOURCE_LOCK = threading.RLock()


class ProjectSourceService:
    """Copy user-selected local sources into a Project-owned durable workspace."""

    def __init__(self, *, store: GmScienceStore) -> None:
        self.store = store

    def list_sources(self, project_id: str) -> list[dict[str, Any]]:
        """Return safe metadata for imported Project sources."""

        workspace = self._workspace(project_id)
        with _SOURCE_LOCK:
            sources = self._read_manifest(workspace)
        return [self._public_source(workspace, source) for source in sources]

    def import_source(
        self,
        project_id: str,
        source_path: str,
        *,
        kind: ProjectSourceKind,
    ) -> dict[str, Any]:
        """Copy one file or directory into the Project and record its durable source."""

        workspace = self._workspace(project_id)
        try:
            source = Path(str(source_path or "").strip()).expanduser().resolve(strict=True)
        except OSError as exc:
            raise ValueError("The selected source is unavailable.") from exc
        normalized_kind = str(kind or "").strip().lower()
        if normalized_kind not in {"file", "folder"}:
            raise ValueError("Field 'kind' must be 'file' or 'folder'.")
        if source.is_symlink():
            raise ValueError("Symbolic-link sources are not supported.")
        if normalized_kind == "file" and not source.is_file():
            raise ValueError("The selected source is not a regular file.")
        if normalized_kind == "folder" and not source.is_dir():
            raise ValueError("The selected source is not a directory.")
        if _paths_overlap(source, workspace):
            raise ValueError("Select a source outside the Project workspace.")

        source_id = f"source_{uuid.uuid4().hex[:16]}"
        label = source.name or ("Imported file" if normalized_kind == "file" else "Imported folder")
        slug = _safe_slug(source.stem if normalized_kind == "file" else label)
        relative_root = Path("references") / f"{slug}-{source_id[-8:]}"
        target = workspace / relative_root
        temporary = target.with_name(f".{target.name}.importing")
        imported_at = dt.datetime.now(dt.timezone.utc).astimezone().isoformat()

        with _SOURCE_LOCK:
            if temporary.exists():
                shutil.rmtree(temporary)
            temporary.mkdir(parents=True, exist_ok=False)
            try:
                if normalized_kind == "file":
                    file_count, size_bytes = self._copy_file(source, temporary / source.name)
                else:
                    file_count, size_bytes = self._copy_directory(source, temporary)
                if file_count == 0:
                    raise ValueError("The selected source contains no importable regular files.")
                target.parent.mkdir(parents=True, exist_ok=True)
                os.replace(temporary, target)
                source_record = {
                    "id": source_id,
                    "kind": normalized_kind,
                    "label": label[:240],
                    "relative_root": relative_root.as_posix(),
                    "file_count": file_count,
                    "size_bytes": size_bytes,
                    "imported_at": imported_at,
                }
                sources = self._read_manifest(workspace)
                sources.append(source_record)
                self._write_manifest(workspace, sources)
            except Exception:
                if temporary.exists():
                    shutil.rmtree(temporary, ignore_errors=True)
                if target.exists() and not any(
                    item.get("relative_root") == relative_root.as_posix()
                    for item in self._read_manifest(workspace)
                ):
                    shutil.rmtree(target, ignore_errors=True)
                raise
        return self._public_source(workspace, source_record)

    def delete_source(self, project_id: str, source_id: str) -> None:
        """Delete one imported source and its Project-owned copied files."""

        workspace = self._workspace(project_id)
        normalized_id = str(source_id or "").strip()
        with _SOURCE_LOCK:
            sources = self._read_manifest(workspace)
            source = next((item for item in sources if item.get("id") == normalized_id), None)
            if source is None:
                raise LookupError(f"Project source '{normalized_id}' was not found.")
            target = (workspace / str(source.get("relative_root") or "")).resolve(strict=False)
            if not _is_within(target, workspace / "references"):
                raise RuntimeError("Project source manifest contains an invalid path.")
            if target.exists():
                shutil.rmtree(target)
            self._write_manifest(
                workspace,
                [item for item in sources if item.get("id") != normalized_id],
            )

    def _workspace(self, project_id: str) -> Path:
        project = self.store.get_project(project_id)
        if project is None:
            raise ValueError(f"Project '{project_id}' was not found.")
        return Path(project.workspace_path).expanduser().resolve(strict=False)

    @staticmethod
    def _copy_file(source: Path, target: Path) -> tuple[int, int]:
        size = source.stat().st_size
        if size > _MAX_IMPORTED_BYTES:
            raise ValueError(f"Imported sources may contain at most {_MAX_IMPORTED_BYTES} bytes.")
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        return 1, size

    def _copy_directory(self, source: Path, target: Path) -> tuple[int, int]:
        file_count = 0
        size_bytes = 0
        for current, directory_names, file_names in os.walk(source, followlinks=False):
            current_path = Path(current)
            directory_names[:] = sorted(
                name
                for name in directory_names
                if not (current_path / name).is_symlink()
            )
            for file_name in sorted(file_names, key=str.casefold):
                candidate = current_path / file_name
                if candidate.is_symlink() or not candidate.is_file():
                    continue
                file_count += 1
                if file_count > _MAX_IMPORTED_FILES:
                    raise ValueError(f"Imported folders may contain at most {_MAX_IMPORTED_FILES} files.")
                size_bytes += candidate.stat().st_size
                if size_bytes > _MAX_IMPORTED_BYTES:
                    raise ValueError(f"Imported sources may contain at most {_MAX_IMPORTED_BYTES} bytes.")
                relative = candidate.relative_to(source)
                self._copy_file(candidate, target / relative)
        return file_count, size_bytes

    @staticmethod
    def _manifest_path(workspace: Path) -> Path:
        return workspace / ".gm-science" / "sources.json"

    def _read_manifest(self, workspace: Path) -> list[dict[str, Any]]:
        manifest = self._manifest_path(workspace)
        if not manifest.is_file():
            return []
        try:
            payload = json.loads(manifest.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise RuntimeError("Project source manifest is unreadable.") from exc
        if not isinstance(payload, dict) or payload.get("schema_version") != _MANIFEST_SCHEMA_VERSION:
            raise RuntimeError("Project source manifest has an unsupported schema.")
        sources = payload.get("sources")
        if not isinstance(sources, list) or not all(isinstance(item, dict) for item in sources):
            raise RuntimeError("Project source manifest is invalid.")
        return [dict(item) for item in sources]

    def _write_manifest(self, workspace: Path, sources: list[dict[str, Any]]) -> None:
        manifest = self._manifest_path(workspace)
        manifest.parent.mkdir(parents=True, exist_ok=True)
        temporary = manifest.with_suffix(".tmp")
        temporary.write_text(
            json.dumps(
                {"schema_version": _MANIFEST_SCHEMA_VERSION, "sources": sources},
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        os.chmod(temporary, 0o600)
        os.replace(temporary, manifest)

    @staticmethod
    def _public_source(workspace: Path, source: dict[str, Any]) -> dict[str, Any]:
        relative_root = str(source.get("relative_root") or "")
        target = (workspace / relative_root).resolve(strict=False)
        return {
            "id": str(source.get("id") or ""),
            "kind": str(source.get("kind") or "folder"),
            "label": str(source.get("label") or "Imported source"),
            "relative_root": relative_root,
            "file_count": int(source.get("file_count") or 0),
            "size_bytes": int(source.get("size_bytes") or 0),
            "imported_at": str(source.get("imported_at") or ""),
            "available": target.is_dir(),
        }


def _safe_slug(value: str) -> str:
    normalized = re.sub(r"[^a-zA-Z0-9._-]+", "-", str(value or "").strip()).strip("-._")
    return (normalized or "source")[:80]


def _paths_overlap(left: Path, right: Path) -> bool:
    return _is_within(left, right) or _is_within(right, left)


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.resolve(strict=False).relative_to(root.resolve(strict=False))
    except ValueError:
        return False
    return True
