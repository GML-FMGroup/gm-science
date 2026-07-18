"""Project-scoped local Python execution built on openppx TaskRun."""

from __future__ import annotations

import hashlib
import json
import mimetypes
import os
import shutil
import sys
import threading
import uuid
from pathlib import Path
from typing import Any

from ...runtime.task_execution import (
    ProcessExecutionSupervisor,
    TaskController,
    TaskInvocationContext,
)
from ...runtime.task_store import (
    TASK_ACTIVE_STATUSES,
    TASK_TERMINAL_STATUSES,
    TaskEventStore,
    TaskStore,
    ToolCallRecordStore,
)
from ..models import ScienceRunRecord
from ..store import GmScienceStore
from .config import ScienceExecutionConfig, load_execution_config


class ScienceExecutionService:
    """Submit and inspect Project-scoped Python runs through openppx TaskRun."""

    def __init__(
        self,
        *,
        data_dir: Path,
        store: GmScienceStore | None = None,
        config_path: Path | None = None,
        config: ScienceExecutionConfig | None = None,
    ) -> None:
        self.data_dir = Path(data_dir).expanduser()
        self.store = store or GmScienceStore(self.data_dir)
        self.config = config or load_execution_config(config_path)
        task_store = TaskStore(db_path=self.data_dir / "database" / "tasks.db")
        event_store = TaskEventStore(db_path=task_store.db_path)
        self.controller = TaskController(task_store=task_store, event_store=event_store)
        self.supervisor = ProcessExecutionSupervisor(
            task_store=task_store,
            event_store=event_store,
            tool_call_store=ToolCallRecordStore(db_path=task_store.db_path),
        )
        self._submission_lock = threading.Lock()
        self._pending_submissions: dict[str, int] = {}

    def submit_python_run(
        self,
        *,
        project_id: str,
        title: str,
        source: str,
        session_id: str | None = None,
        input_payload: dict[str, Any] | None = None,
        user_id: str = "ppx-client-user",
        parent_task_id: str | None = None,
        kind: str = "local_python",
    ) -> dict[str, Any]:
        """Create a run directory, submit Python, and return the Project run payload."""

        if not self.config.enabled:
            raise ValueError("Local science execution is disabled by configuration.")
        project = self.store.get_project(project_id)
        if project is None:
            raise ValueError(f"Project '{project_id}' was not found.")
        normalized_session_id = str(session_id or "").strip() or None
        if normalized_session_id:
            association = self.store.get_project_session(normalized_session_id)
            if association is None or association.project_id != project.id:
                raise ValueError(
                    f"Session '{normalized_session_id}' does not belong to Project '{project.id}'."
                )
        normalized_source = str(source or "")
        if not normalized_source.strip():
            raise ValueError("Python source is required.")
        if len(normalized_source) > self.config.max_source_chars:
            raise ValueError(
                f"Python source exceeds the configured {self.config.max_source_chars}-character limit."
            )
        payload = dict(input_payload or {})
        normalized_kind = str(kind or "").strip()
        if normalized_kind not in {"local_python", "data_analysis"}:
            raise ValueError(f"Unsupported science run kind '{kind}'.")
        raw_argv = payload.get("argv", [])
        if not isinstance(raw_argv, list) or any(not isinstance(item, (str, int, float)) for item in raw_argv):
            raise ValueError("Run input 'argv' must be an array of scalar values.")

        python_executable = self._python_executable()
        runner_path = Path(__file__).with_name("runner.py").resolve(strict=True)
        self._reserve_submission(project.id)
        execution_id = f"run_{uuid.uuid4().hex[:16]}"
        workspace = Path(project.workspace_path).expanduser().resolve(strict=False)
        run_dir = (workspace / "runs" / execution_id).resolve(strict=False)
        try:
            self._require_within(run_dir, workspace)
            try:
                run_dir.mkdir(parents=True, exist_ok=False)
                source_path = run_dir / "main.py"
                source_path.write_text(normalized_source.rstrip() + "\n", encoding="utf-8")
                (run_dir / "input.json").write_text(
                    json.dumps(payload, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
                (run_dir / "outputs").mkdir()
                invocation_id = f"science-run:{execution_id}"
                result = self.supervisor.invoke_process(
                    title=str(title or "Python run").strip() or "Python run",
                    argv=[
                        python_executable,
                        "-u",
                        str(runner_path),
                        "--run-dir",
                        str(run_dir),
                        "--timeout-seconds",
                        str(self.config.default_timeout_seconds),
                    ],
                    cwd=run_dir,
                    env={**os.environ, "PYTHONUNBUFFERED": "1"},
                    context=TaskInvocationContext(
                        user_id=user_id,
                        session_id=normalized_session_id or "",
                        thread_id=normalized_session_id or project.id,
                        turn_id=invocation_id,
                        invocation_id=invocation_id,
                        function_call_id=invocation_id,
                        tool_call_id=invocation_id,
                        owner_key=user_id,
                    ),
                    scope_key=None,
                    task_kind=f"science_{normalized_kind}",
                    runner_payload={
                        "science_run_id": execution_id,
                        "project_id": project.id,
                        "run_dir": str(run_dir),
                        "source_path": str(source_path),
                        "source_sha256": hashlib.sha256(normalized_source.encode("utf-8")).hexdigest(),
                        "timeout_seconds": self.config.default_timeout_seconds,
                    },
                    always_task=True,
                )
            except Exception:
                shutil.rmtree(run_dir, ignore_errors=True)
                raise
            if result.task is None:
                shutil.rmtree(run_dir, ignore_errors=True)
                raise RuntimeError(result.error or "Local Python execution did not create a TaskRun.")
            try:
                self.store.create_science_run(
                    task_id=result.task.task_id,
                    project_id=project.id,
                    session_id=normalized_session_id,
                    parent_task_id=parent_task_id,
                    kind=normalized_kind,
                    title=str(title or "Python run").strip() or "Python run",
                    source_path=str(source_path),
                    working_directory=str(run_dir),
                    input_payload=payload,
                )
            except Exception:
                self.controller.cancel_task(result.task.task_id)
                shutil.rmtree(run_dir, ignore_errors=True)
                raise
            return self.get_run(project.id, result.task.task_id)
        finally:
            self._release_submission(project.id)

    def _reserve_submission(self, project_id: str) -> None:
        """Atomically enforce the configured Project concurrency limit."""

        with self._submission_lock:
            active = self._active_run_count(project_id)
            pending = self._pending_submissions.get(project_id, 0)
            if active + pending >= self.config.max_concurrent_runs:
                raise ValueError(
                    f"Project already has {active + pending} active run(s); "
                    f"configured limit is {self.config.max_concurrent_runs}."
                )
            self._pending_submissions[project_id] = pending + 1

    def _release_submission(self, project_id: str) -> None:
        """Release one in-flight submission reservation."""

        with self._submission_lock:
            remaining = self._pending_submissions.get(project_id, 0) - 1
            if remaining > 0:
                self._pending_submissions[project_id] = remaining
            else:
                self._pending_submissions.pop(project_id, None)

    def _active_run_count(self, project_id: str) -> int:
        """Return the synchronized active TaskRun count for one Project."""

        active = 0
        for record in self.store.list_science_runs(project_id):
            task = self._synchronized_task(record.task_id)
            if task is not None and task.status in TASK_ACTIVE_STATUSES:
                active += 1
        return active

    def list_runs(self, project_id: str) -> list[dict[str, Any]]:
        """List synchronized Project runs in newest-first order."""

        if self.store.get_project(project_id) is None:
            raise ValueError(f"Project '{project_id}' was not found.")
        return [self._run_payload(record) for record in self.store.list_science_runs(project_id)]

    def get_run(self, project_id: str, task_id: str) -> dict[str, Any]:
        """Return one synchronized Project run with controls and durable log preview."""

        record = self._project_run(project_id, task_id)
        return self._run_payload(record, include_events=True)

    def cancel_run(self, project_id: str, task_id: str) -> dict[str, Any]:
        """Cancel one active Project run using the openppx task controller."""

        record = self._project_run(project_id, task_id)
        result = self.controller.cancel_task(record.task_id)
        if not result.get("ok"):
            raise RuntimeError(str(result.get("error") or result.get("message") or "Task cancellation failed."))
        return self._run_payload(record, include_events=True)

    def retry_run(
        self,
        project_id: str,
        task_id: str,
        *,
        user_id: str = "ppx-client-user",
    ) -> dict[str, Any]:
        """Create a new TaskRun from one terminal run's saved source and input."""

        record = self._project_run(project_id, task_id)
        task = self._synchronized_task(record.task_id)
        if task is None:
            raise RuntimeError(f"Task '{task_id}' was not found.")
        if task.status not in TASK_TERMINAL_STATUSES and task.status != "interrupted":
            raise ValueError(f"Task '{task_id}' is still {task.status} and cannot be retried.")
        source_path = Path(record.source_path)
        if not source_path.is_file():
            raise ValueError(f"Saved Python source for Task '{task_id}' was not found.")
        return self.submit_python_run(
            project_id=record.project_id,
            session_id=record.session_id,
            title=record.title,
            source=source_path.read_text(encoding="utf-8"),
            input_payload=record.input_payload,
            user_id=user_id,
            parent_task_id=record.task_id,
            kind=record.kind,
        )

    def _project_run(self, project_id: str, task_id: str) -> ScienceRunRecord:
        record = self.store.get_science_run(task_id)
        if record is None or record.project_id != project_id:
            raise ValueError(f"Science run '{task_id}' was not found in Project '{project_id}'.")
        return record

    def _synchronized_task(self, task_id: str):
        task = self.controller.sync_task(task_id)
        if task is not None and task.status == "stale":
            task = self.controller.reconcile_stale_task(task_id, stale_lost_after_ms=0)
        return task

    def _run_payload(self, record: ScienceRunRecord, *, include_events: bool = False) -> dict[str, Any]:
        task = self._synchronized_task(record.task_id)
        if task is None:
            raise RuntimeError(f"Task '{record.task_id}' was not found.")
        if task.status in TASK_TERMINAL_STATUSES or task.status == "interrupted":
            self._promote_artifacts(record, task.status)
        else:
            self._ensure_source_artifact(record)
        shown = self.controller.show_task(record.task_id)
        if not shown.get("ok"):
            raise RuntimeError(str(shown.get("error") or f"Task '{record.task_id}' was not found."))
        task_payload = dict(shown["task"])
        artifacts = self._gm_artifacts_for_task(record.project_id, record.task_id)
        payload = {
            "task_id": record.task_id,
            "project_id": record.project_id,
            "session_id": record.session_id or "",
            "parent_task_id": record.parent_task_id or "",
            "kind": record.kind,
            "title": record.title,
            "status": task_payload.get("status", ""),
            "progress_summary": task_payload.get("progress_summary", ""),
            "terminal_summary": task_payload.get("terminal_summary", ""),
            "last_error": task_payload.get("last_error", ""),
            "created_at": record.created_at,
            "updated_at": record.updated_at,
            "created_at_ms": task_payload.get("created_at_ms", 0),
            "updated_at_ms": task_payload.get("updated_at_ms", 0),
            "ended_at_ms": task_payload.get("ended_at_ms"),
            "controls": task_payload.get("controls", {}),
            "can_retry": task_payload.get("status") in TASK_TERMINAL_STATUSES or task_payload.get("status") == "interrupted",
            "log_preview": self._log_preview(Path(record.working_directory) / "run.log"),
            "artifact_ids": [artifact.id for artifact in artifacts],
        }
        if include_events:
            payload["events"] = list(shown.get("events") or [])
        return payload

    def _promote_artifacts(self, record: ScienceRunRecord, status: str) -> None:
        self._ensure_source_artifact(record)
        existing_roles = {
            str(artifact.metadata.get("science_run_role") or "")
            for artifact in self._gm_artifacts_for_task(record.project_id, record.task_id)
        }
        run_dir = Path(record.working_directory).resolve(strict=False)
        log_path = run_dir / "run.log"
        if log_path.is_file() and "log" not in existing_roles:
            self._create_run_artifact(
                record,
                artifact_type="experiment_log",
                title=f"{record.title} log",
                path=log_path,
                mime_type="text/plain",
                role="log",
                metadata={
                    "status": status,
                    "stdout_path": str(run_dir / "stdout.log"),
                    "stderr_path": str(run_dir / "stderr.log"),
                    "manifest_path": str(run_dir / "manifest.json"),
                },
            )
        output_dir = (run_dir / "outputs").resolve(strict=False)
        for item in self._declared_outputs(run_dir, output_dir):
            relative = str(item["relative_path"])
            role = f"output:{relative}"
            if role in existing_roles:
                continue
            path = (output_dir / relative).resolve(strict=False)
            self._require_within(path, output_dir)
            if not path.is_file():
                continue
            mime_type = str(item.get("media_type") or mimetypes.guess_type(path.name)[0] or "application/octet-stream")
            self._create_run_artifact(
                record,
                artifact_type=self._artifact_type(path, mime_type),
                title=path.name,
                path=path,
                mime_type=mime_type,
                role=role,
                metadata={"relative_path": relative, "status": status},
            )

    def _ensure_source_artifact(self, record: ScienceRunRecord) -> None:
        existing_roles = {
            str(artifact.metadata.get("science_run_role") or "")
            for artifact in self._gm_artifacts_for_task(record.project_id, record.task_id)
        }
        if "source" in existing_roles:
            return
        source_path = Path(record.source_path)
        if source_path.is_file():
            self._create_run_artifact(
                record,
                artifact_type="code",
                title=f"{record.title} source",
                path=source_path,
                mime_type="text/x-python",
                role="source",
                metadata={"source_sha256": hashlib.sha256(source_path.read_bytes()).hexdigest()},
            )

    def _create_run_artifact(
        self,
        record: ScienceRunRecord,
        *,
        artifact_type: str,
        title: str,
        path: Path,
        mime_type: str,
        role: str,
        metadata: dict[str, Any],
    ) -> None:
        analysis_id = str(record.input_payload.get("analysis_id") or "")
        dataset_artifact_ids = [
            str(value)
            for value in record.input_payload.get("dataset_artifact_ids", [])
            if str(value).strip()
        ]
        artifact = self.store.create_artifact(
            project_id=record.project_id,
            session_id=record.session_id,
            artifact_type=artifact_type,
            title=title,
            path_or_url=str(path),
            mime_type=mime_type,
            metadata={
                **metadata,
                "science_run_role": role,
                "task_id": record.task_id,
                "analysis_id": analysis_id,
                "source_artifact_ids": dataset_artifact_ids,
            },
            provenance={
                "created_by": "experiment_runner",
                "task_id": record.task_id,
                "parent_task_id": record.parent_task_id or "",
                "analysis_id": analysis_id,
                "source_artifact_ids": dataset_artifact_ids,
            },
        )
        existing_task_paths = {
            item.path for item in self.controller.artifact_store.list_artifacts(record.task_id, limit=500)
        }
        if str(path) not in existing_task_paths:
            self.controller.artifact_store.record_artifact(
                task_id=record.task_id,
                artifact_type=artifact_type,
                label=title,
                media_type=mime_type,
                path=str(path),
                size_bytes=path.stat().st_size,
                metadata={"gm_science_artifact_id": artifact.id, "project_id": record.project_id, "role": role},
            )

    def _declared_outputs(self, run_dir: Path, output_dir: Path) -> list[dict[str, Any]]:
        manifest_path = run_dir / "manifest.json"
        if manifest_path.is_file():
            try:
                payload = json.loads(manifest_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                payload = {}
            outputs = payload.get("outputs") if isinstance(payload, dict) else None
            if isinstance(outputs, list) and payload.get("status") in {"completed", "failed"}:
                return [dict(item) for item in outputs if isinstance(item, dict) and item.get("relative_path")]
        return [
            {
                "relative_path": path.relative_to(output_dir).as_posix(),
                "media_type": mimetypes.guess_type(path.name)[0] or "application/octet-stream",
                "size_bytes": path.stat().st_size,
            }
            for path in sorted(item for item in output_dir.rglob("*") if item.is_file() and not item.is_symlink())
        ]

    def _gm_artifacts_for_task(self, project_id: str, task_id: str):
        return [
            artifact
            for artifact in self.store.list_artifacts(project_id)
            if str(artifact.provenance.get("task_id") or artifact.metadata.get("task_id") or "") == task_id
        ]

    def _log_preview(self, path: Path) -> str:
        if not path.is_file():
            return ""
        text = path.read_text(encoding="utf-8", errors="replace")
        return text[-self.config.max_log_preview_chars :]

    def _python_executable(self) -> str:
        configured = self.config.python_executable
        if not configured:
            return sys.executable
        expanded = Path(configured).expanduser()
        if expanded.is_absolute():
            if not expanded.is_file():
                raise ValueError(f"Configured Python executable '{configured}' was not found.")
            return str(expanded)
        resolved = shutil.which(configured)
        if not resolved:
            raise ValueError(f"Configured Python executable '{configured}' was not found on PATH.")
        return resolved

    @staticmethod
    def _artifact_type(path: Path, mime_type: str) -> str:
        if mime_type.startswith("image/"):
            return "figure"
        if path.suffix.lower() in {".csv", ".tsv"}:
            return "table"
        if path.suffix.lower() in {".md", ".markdown"}:
            return "report"
        if path.suffix.lower() == ".py":
            return "code"
        return "artifact_file"

    @staticmethod
    def _require_within(path: Path, root: Path) -> None:
        try:
            path.resolve(strict=False).relative_to(root.resolve(strict=False))
        except ValueError as exc:
            raise ValueError(f"Execution path '{path}' is outside Project workspace '{root}'.") from exc
