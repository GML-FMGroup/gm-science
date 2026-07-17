from __future__ import annotations

import time
from pathlib import Path

import pytest

from openppx.gm_science.execution.config import ScienceExecutionConfig
from openppx.gm_science.execution.service import ScienceExecutionService
from openppx.gm_science.store import GmScienceStore


def _service(tmp_path: Path) -> tuple[ScienceExecutionService, GmScienceStore, str, str]:
    store = GmScienceStore(tmp_path)
    project = store.create_project(name="Execution", description="", agent_context="")
    session_id = "session-execution"
    store.link_project_session(
        project_id=project.id,
        session_id=session_id,
        agent_id="science-research",
    )
    service = ScienceExecutionService(
        data_dir=tmp_path,
        store=store,
        config=ScienceExecutionConfig(
            enabled=True,
            python_executable="",
            max_concurrent_runs=2,
            default_timeout_seconds=10,
            max_source_chars=20_000,
            max_log_preview_chars=6_000,
        ),
    )
    return service, store, project.id, session_id


def _wait_for_terminal(service: ScienceExecutionService, project_id: str, task_id: str) -> dict:
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        payload = service.get_run(project_id, task_id)
        if payload["status"] in {"completed", "failed", "cancelled", "lost"}:
            return payload
        time.sleep(0.05)
    raise AssertionError(f"Task {task_id} did not finish")


def test_local_python_run_persists_logs_outputs_and_artifacts(tmp_path: Path) -> None:
    service, store, project_id, session_id = _service(tmp_path)
    source = """
import os
from pathlib import Path

print("analysis started")
output = Path(os.environ["GM_SCIENCE_OUTPUT_DIR"]) / "result.txt"
output.write_text("42\\n", encoding="utf-8")
print("analysis finished")
"""

    created = service.submit_python_run(
        project_id=project_id,
        session_id=session_id,
        title="Small analysis",
        source=source,
        input_payload={"argv": []},
    )
    finished = _wait_for_terminal(service, project_id, created["task_id"])

    assert finished["status"] == "completed"
    assert "analysis finished" in finished["log_preview"]
    assert store.get_science_run(finished["task_id"]) is not None
    artifacts = [
        artifact
        for artifact in store.list_artifacts(project_id)
        if artifact.provenance.get("task_id") == finished["task_id"]
    ]
    assert {artifact.type for artifact in artifacts} == {"code", "experiment_log", "artifact_file"}
    assert next(artifact for artifact in artifacts if artifact.type == "artifact_file").path_or_url.endswith("result.txt")


def test_failed_python_run_can_be_retried_from_saved_source(tmp_path: Path) -> None:
    service, store, project_id, session_id = _service(tmp_path)
    created = service.submit_python_run(
        project_id=project_id,
        session_id=session_id,
        title="Expected failure",
        source="raise RuntimeError('expected failure')",
    )
    failed = _wait_for_terminal(service, project_id, created["task_id"])

    assert failed["status"] == "failed"
    assert failed["can_retry"] is True
    retried = service.retry_run(project_id, failed["task_id"])
    retry_finished = _wait_for_terminal(service, project_id, retried["task_id"])

    assert retry_finished["status"] == "failed"
    retry_record = store.get_science_run(retry_finished["task_id"])
    assert retry_record is not None
    assert retry_record.parent_task_id == failed["task_id"]


def test_running_python_run_can_be_cancelled_and_keeps_partial_outputs(tmp_path: Path) -> None:
    service, store, project_id, session_id = _service(tmp_path)
    created = service.submit_python_run(
        project_id=project_id,
        session_id=session_id,
        title="Long run",
        source="""
import os
import time
from pathlib import Path

(Path(os.environ["GM_SCIENCE_OUTPUT_DIR"]) / "partial.txt").write_text("saved", encoding="utf-8")
print("waiting", flush=True)
time.sleep(30)
""",
    )

    record = store.get_science_run(created["task_id"])
    assert record is not None
    partial_output = Path(record.working_directory) / "outputs" / "partial.txt"
    deadline = time.monotonic() + 5
    while not partial_output.is_file() and time.monotonic() < deadline:
        time.sleep(0.02)
    assert partial_output.is_file()

    cancelled = service.cancel_run(project_id, created["task_id"])

    assert cancelled["status"] == "cancelled"
    assert cancelled["can_retry"] is True
    assert "waiting" in cancelled["log_preview"] or cancelled["log_preview"] == ""
    output_artifacts = [
        artifact
        for artifact in store.list_artifacts(project_id)
        if artifact.provenance.get("task_id") == created["task_id"] and artifact.type == "artifact_file"
    ]
    assert [Path(artifact.path_or_url).name for artifact in output_artifacts] == ["partial.txt"]


def test_invalid_python_executable_does_not_create_a_run_directory(tmp_path: Path) -> None:
    service, store, project_id, session_id = _service(tmp_path)
    service.config = ScienceExecutionConfig(
        enabled=True,
        python_executable=str(tmp_path / "missing-python"),
        max_concurrent_runs=1,
        default_timeout_seconds=10,
        max_source_chars=20_000,
        max_log_preview_chars=6_000,
    )
    project = store.get_project(project_id)
    assert project is not None

    with pytest.raises(ValueError, match="was not found"):
        service.submit_python_run(
            project_id=project_id,
            session_id=session_id,
            title="Invalid runtime",
            source="print('never runs')",
        )

    assert not (Path(project.workspace_path) / "runs").exists()
