from __future__ import annotations

from pathlib import Path

from openppx.gm_science.analysis import tools
from openppx.gm_science.data.config import DatasetConfig
from openppx.gm_science.data.service import DatasetService
from openppx.gm_science.store import GmScienceStore


def test_analysis_tools_list_data_and_create_approval_only_draft(tmp_path: Path, monkeypatch) -> None:
    state = tmp_path / "state"
    monkeypatch.setenv("GM_SCIENCE_DATA_DIR", str(state))
    store = GmScienceStore(state)
    project = store.create_project(name="Tool test", description="", agent_context="")
    source = tmp_path / "measurements.csv"
    source.write_text("group,value\nA,1\nB,2\n", encoding="utf-8")
    dataset = DatasetService(
        store=store,
        config=DatasetConfig(
            enabled=True,
            max_file_size_bytes=1_000_000,
            profile_row_limit=1_000,
            preview_rows=10,
            max_columns=50,
            top_values_limit=10,
        ),
    ).import_dataset(project_id=project.id, source_path=str(source))

    listed = tools.science_list_datasets(project.id)
    draft = tools.science_plan_data_analysis(
        "Compare groups and summarize values.",
        project.id,
        [dataset["artifact_id"]],
    )

    assert listed["datasets"][0]["artifact_id"] == dataset["artifact_id"]
    assert "path" not in listed["datasets"][0]
    assert draft["status"] == "draft"
    assert draft["approval_required"] is True
    assert "source" not in draft
    assert store.list_science_runs(project.id) == []
