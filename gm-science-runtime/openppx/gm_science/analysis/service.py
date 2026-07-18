"""Project-scoped reviewable analysis drafts backed by ScienceExecutionService."""

from __future__ import annotations

import hashlib
import threading
from pathlib import Path
from typing import Any

from ..data.service import DatasetService
from ..execution.service import ScienceExecutionService
from ..models import AnalysisDraftRecord, ArtifactRecord, ProjectRecord
from ..store import GmScienceStore
from .config import AnalysisConfig, load_analysis_config
from .planner import compile_analysis_plan
from .source import build_analysis_source


class AnalysisService:
    """Create transparent analysis drafts and execute them only after approval."""

    def __init__(
        self,
        *,
        store: GmScienceStore,
        dataset_service: DatasetService,
        execution_service: ScienceExecutionService,
        config_path: Path | None = None,
        config: AnalysisConfig | None = None,
    ) -> None:
        self.store = store
        self.datasets = dataset_service
        self.execution = execution_service
        self.config = config or load_analysis_config(config_path)
        self._run_lock = threading.Lock()

    def create_draft(
        self,
        *,
        project_id: str,
        objective: str,
        dataset_artifact_ids: list[str],
        title: str = "",
        session_id: str | None = None,
    ) -> dict[str, Any]:
        """Compile and persist one analysis draft without starting a TaskRun."""

        if not self.config.enabled:
            raise ValueError("Data analysis is disabled by configuration.")
        normalized_objective = str(objective or "").strip()
        if not normalized_objective:
            raise ValueError("Analysis objective is required.")
        if len(normalized_objective) > self.config.max_objective_chars:
            raise ValueError(
                f"Analysis objective exceeds the configured {self.config.max_objective_chars}-character limit."
            )
        artifact_ids = list(
            dict.fromkeys(str(value or "").strip() for value in dataset_artifact_ids if str(value or "").strip())
        )
        if not artifact_ids:
            raise ValueError("At least one dataset artifact is required.")
        if len(artifact_ids) > self.config.max_datasets:
            raise ValueError(f"Analysis accepts at most {self.config.max_datasets} datasets.")
        datasets = [self.datasets.get_dataset(project_id, artifact_id) for artifact_id in artifact_ids]
        plan = compile_analysis_plan(normalized_objective, datasets, self.config)
        source = build_analysis_source(plan)
        resolved_title = str(title or "").strip() or self._title(normalized_objective)
        draft = self.store.create_analysis_draft(
            project_id=project_id,
            session_id=session_id,
            title=resolved_title,
            objective=normalized_objective,
            dataset_artifact_ids=artifact_ids,
            plan=plan,
            source=source,
        )
        return self._payload(draft, include_source=True)

    def list_analyses(self, project_id: str) -> list[dict[str, Any]]:
        """List analysis drafts with derived TaskRun status."""

        self._project(project_id)
        return [self._payload(record) for record in self.store.list_analysis_drafts(project_id)]

    def get_analysis(self, project_id: str, analysis_id: str) -> dict[str, Any]:
        """Return one Project analysis with plan, source, run, and outputs."""

        return self._payload(self._analysis(project_id, analysis_id), include_source=True)

    def run_analysis(
        self,
        project_id: str,
        analysis_id: str,
        *,
        user_id: str = "ppx-client-user",
    ) -> dict[str, Any]:
        """Approve one draft by creating its first TaskRun exactly once."""

        with self._run_lock:
            draft = self._analysis(project_id, analysis_id)
            if draft.task_id:
                raise ValueError(f"Analysis '{analysis_id}' has already been approved for execution.")
            dataset_payloads = [self.datasets.get_dataset(project_id, artifact_id) for artifact_id in draft.dataset_artifact_ids]
            plan_datasets = {item["artifact_id"]: item for item in draft.plan.get("datasets") or []}
            execution_datasets = []
            for dataset in dataset_payloads:
                artifact = self._dataset_artifact(project_id, dataset["artifact_id"])
                self._verify_dataset_source(artifact)
                planned = plan_datasets.get(dataset["artifact_id"], {})
                execution_datasets.append(
                    {
                        "artifact_id": dataset["artifact_id"],
                        "title": dataset["title"],
                        "path": dataset["path"],
                        "format": dataset["format"],
                        "numeric_columns": list(planned.get("numeric_columns") or []),
                        "categorical_columns": list(planned.get("categorical_columns") or []),
                    }
                )
            input_payload = {
                "argv": [],
                "analysis_id": draft.id,
                "title": draft.title,
                "objective": draft.objective,
                "dataset_artifact_ids": list(draft.dataset_artifact_ids),
                "operations": list(draft.plan.get("operations") or []),
                "warnings": list(draft.plan.get("warnings") or []),
                "datasets": execution_datasets,
            }
            run = self.execution.submit_python_run(
                project_id=project_id,
                session_id=draft.session_id,
                title=draft.title,
                source=draft.source,
                input_payload=input_payload,
                user_id=user_id,
                kind="data_analysis",
            )
            linked = self.store.link_analysis_task(draft.id, run["task_id"])
        return self._payload(linked, include_source=True)

    def relink_retry(self, previous_task_id: str, new_task_id: str) -> None:
        """Move an analysis association when its TaskRun is retried."""

        draft = self.store.find_analysis_by_task(previous_task_id)
        if draft is not None:
            self.store.link_analysis_task(draft.id, new_task_id)

    def _payload(self, draft: AnalysisDraftRecord, *, include_source: bool = False) -> dict[str, Any]:
        run = self.execution.get_run(draft.project_id, draft.task_id) if draft.task_id else None
        artifacts = self._task_artifacts(draft.project_id, draft.task_id) if draft.task_id else []
        report = next((artifact for artifact in artifacts if artifact.type == "report"), None)
        figures = [artifact.id for artifact in artifacts if artifact.type == "figure"]
        payload: dict[str, Any] = {
            "id": draft.id,
            "project_id": draft.project_id,
            "session_id": draft.session_id or "",
            "title": draft.title,
            "objective": draft.objective,
            "dataset_artifact_ids": list(draft.dataset_artifact_ids),
            "plan": draft.plan,
            "task_id": draft.task_id or "",
            "status": str(run["status"]) if run is not None else "draft",
            "run": run,
            "report_artifact_id": report.id if report is not None else "",
            "figure_artifact_ids": figures,
            "artifact_ids": [artifact.id for artifact in artifacts],
            "created_at": draft.created_at,
            "updated_at": draft.updated_at,
        }
        if include_source:
            payload["source"] = draft.source
        return payload

    def _analysis(self, project_id: str, analysis_id: str) -> AnalysisDraftRecord:
        draft = self.store.get_analysis_draft(str(analysis_id or "").strip())
        if draft is None or draft.project_id != project_id:
            raise ValueError(f"Analysis '{analysis_id}' was not found in Project '{project_id}'.")
        return draft

    def _project(self, project_id: str) -> ProjectRecord:
        project = self.store.get_project(str(project_id or "").strip())
        if project is None:
            raise ValueError(f"Project '{project_id}' was not found.")
        return project

    def _dataset_artifact(self, project_id: str, artifact_id: str) -> ArtifactRecord:
        artifact = self.store.get_artifact(artifact_id)
        if artifact is None or artifact.project_id != project_id or artifact.type != "dataset":
            raise ValueError(f"Dataset artifact '{artifact_id}' was not found in Project '{project_id}'.")
        return artifact

    @staticmethod
    def _verify_dataset_source(artifact: ArtifactRecord) -> None:
        path = Path(artifact.path_or_url)
        if not path.is_file():
            raise ValueError(f"Dataset source for Artifact '{artifact.id}' was not found.")
        expected = str(artifact.metadata.get("sha256") or "")
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        if expected and actual != expected:
            raise ValueError(f"Dataset source for Artifact '{artifact.id}' changed after profiling.")

    def _task_artifacts(self, project_id: str, task_id: str | None) -> list[ArtifactRecord]:
        return [
            artifact
            for artifact in self.store.list_artifacts(project_id)
            if task_id and str(artifact.provenance.get("task_id") or artifact.metadata.get("task_id") or "") == task_id
        ]

    @staticmethod
    def _title(objective: str) -> str:
        compact = " ".join(objective.split())
        return compact if len(compact) <= 80 else compact[:77].rstrip() + "..."
