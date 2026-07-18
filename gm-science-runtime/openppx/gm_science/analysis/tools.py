"""ADK-callable dataset discovery and reviewable analysis planning tools."""

from __future__ import annotations

from typing import Any

from ..data.service import DatasetService
from ..execution.service import ScienceExecutionService
from ..store import GmScienceStore
from .service import AnalysisService


def science_list_datasets(project_id: str) -> dict[str, Any]:
    """List imported datasets that are available to one gm-science Project.

    Args:
        project_id: Current gm-science project identifier.
    """

    store = GmScienceStore()
    datasets = DatasetService(store=store).list_datasets(project_id)
    return {
        "project_id": project_id,
        "datasets": [_public_dataset(dataset) for dataset in datasets],
    }


def science_plan_data_analysis(
    objective: str,
    project_id: str,
    dataset_artifact_ids: list[str],
    session_id: str = "",
    title: str = "",
) -> dict[str, Any]:
    """Create a transparent analysis draft without executing it.

    The user must review and approve the draft in the Data panel before any
    local Python process starts.

    Args:
        objective: Natural-language analysis goal.
        project_id: Current gm-science project identifier.
        dataset_artifact_ids: Imported dataset Artifact IDs to analyze.
        session_id: Current conversation session identifier.
        title: Optional short analysis title.
    """

    store = GmScienceStore()
    datasets = DatasetService(store=store)
    execution = ScienceExecutionService(data_dir=store.root_dir, store=store)
    analysis = AnalysisService(
        store=store,
        dataset_service=datasets,
        execution_service=execution,
    )
    draft = analysis.create_draft(
        project_id=project_id,
        objective=objective,
        dataset_artifact_ids=dataset_artifact_ids,
        session_id=str(session_id or "").strip() or None,
        title=title,
    )
    draft.pop("source", None)
    draft["approval_required"] = True
    draft["next_action"] = "Ask the user to review and approve this draft in the Data panel."
    return draft


def _public_dataset(dataset: dict[str, Any]) -> dict[str, Any]:
    """Remove workspace paths while preserving fields needed for planning."""

    return {
        "artifact_id": dataset["artifact_id"],
        "title": dataset["title"],
        "format": dataset["format"],
        "row_count": dataset["row_count"],
        "profiled_row_count": dataset["profiled_row_count"],
        "column_count": dataset["column_count"],
        "column_names": dataset["column_names"],
        "created_at": dataset["created_at"],
    }
