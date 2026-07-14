from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from openppx.gm_science.specialists.agent_tool import ProjectSpecialistTool, child_session_state
from openppx.gm_science.specialists.agents import build_specialist_tools
from openppx.gm_science.specialists.config import parse_specialist_config
from openppx.gm_science.specialists.models import PaperReading, PaperReaderOutput
from openppx.gm_science.store import GmScienceStore


def _paper_output(paper_id: str) -> PaperReaderOutput:
    return PaperReaderOutput(
        title="Reading note",
        synthesis="A bounded synthesis.",
        readings=[
            PaperReading(
                paper_artifact_id=paper_id,
                title="Paper",
                evidence_scope="metadata_abstract",
                contribution="Contribution",
                methods=[],
                results=[],
                limitations=["Abstract only"],
                reproducibility_clues=[],
                confidence="medium",
            )
        ],
        agreements=[],
        conflicts=[],
        open_questions=[],
        confidence_note="Abstract evidence only.",
    )


def test_child_session_state_is_fresh() -> None:
    assert child_session_state({"secret": "parent", "project_id": "proj_1"}) == {}


def test_project_specialist_tool_rejects_project_allowlist_before_child_run(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("GM_SCIENCE_DATA_DIR", str(tmp_path))
    store = GmScienceStore(tmp_path)
    project = store.create_project(
        name="Review",
        description="",
        agent_context="",
        enabled_specialists=[],
    )
    paper = store.create_artifact(
        project_id=project.id,
        artifact_type="paper",
        title="Paper",
        path_or_url="",
    )
    config = parse_specialist_config({})
    tool = build_specialist_tools(config=config, model="gemini-2.0-flash")[0]

    with patch(
        "openppx.gm_science.specialists.agent_tool.load_specialist_config",
        return_value=config,
    ):
        with patch.object(ProjectSpecialistTool, "_run_isolated", new=AsyncMock()) as run_child:
            with pytest.raises(ValueError, match="not enabled"):
                asyncio.run(
                    tool.run_async(
                        args={
                            "project_id": project.id,
                            "session_id": "session-1",
                            "paper_artifact_ids": [paper.id],
                        },
                        tool_context=SimpleNamespace(),
                    )
                )

    run_child.assert_not_awaited()


def test_project_specialist_tool_validates_output_and_saves_artifact(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("GM_SCIENCE_DATA_DIR", str(tmp_path))
    store = GmScienceStore(tmp_path)
    project = store.create_project(
        name="Review",
        description="",
        agent_context="",
        enabled_specialists=["paper_reader"],
    )
    paper = store.create_artifact(
        project_id=project.id,
        artifact_type="paper",
        title="Paper",
        path_or_url="",
    )
    config = parse_specialist_config({})
    tool = build_specialist_tools(config=config, model="gemini-2.0-flash")[0]
    output = _paper_output(paper.id)

    with patch(
        "openppx.gm_science.specialists.agent_tool.load_specialist_config",
        return_value=config,
    ):
        with patch.object(
            ProjectSpecialistTool,
            "_run_isolated",
            new=AsyncMock(return_value=output.model_dump(mode="json")),
        ):
            result = asyncio.run(
                tool.run_async(
                    args={
                        "project_id": project.id,
                        "session_id": "session-1",
                        "paper_artifact_ids": [paper.id],
                    },
                    tool_context=SimpleNamespace(),
                )
            )

    assert result["output"]["title"] == "Reading note"
    assert result["artifact"]["type"] == "reading_note"
    assert [artifact.type for artifact in store.list_artifacts(project.id)] == ["paper", "reading_note"]
