from __future__ import annotations

import json
import os
from types import SimpleNamespace
from unittest.mock import patch

from google.adk.agents.run_config import StreamingMode

from openppx.gm_science.resources.context import ResolvedResourceContext
from openppx.gm_science.resources.models import ResourceRef
from openppx.runtime.client_api_worker import (
    ResolvedReferenceContext,
    _build_project_memory_service,
    _build_adk_user_content,
    _build_interactive_run_config,
    _restrict_mcp_servers_env,
    _reviewer_tool_for_policy,
    _session_title,
)


def test_reviewer_policy_uses_existing_subagent_or_rebuilds_with_main_model() -> None:
    existing = SimpleNamespace(name="research_reviewer")
    rebuilt = SimpleNamespace(name="research_reviewer")
    root = SimpleNamespace(tools=[existing])

    assert _reviewer_tool_for_policy(root, "default") is existing
    assert _reviewer_tool_for_policy(root, "subagent") is existing
    with (
        patch("openppx.core.provider.build_adk_model_from_env", return_value="main-model"),
        patch(
            "openppx.gm_science.specialists.agents.build_specialist_tools",
            return_value=[rebuilt],
        ) as build_tools,
    ):
        assert _reviewer_tool_for_policy(root, "main") is rebuilt
    build_tools.assert_called_once_with(model="main-model")


def test_project_memory_service_is_only_built_for_project_runs(tmp_path) -> None:
    from openppx.gm_science.memory import ProjectScopedMemoryService

    assert (
        _build_project_memory_service(
            project_id="",
            session_id="session-generic",
            data_dir=tmp_path,
        )
        is None
    )
    service = _build_project_memory_service(
        project_id="project-1",
        session_id="session-1",
        data_dir=tmp_path,
    )
    assert isinstance(service, ProjectScopedMemoryService)
    assert service.project_id == "project-1"
    assert service.session_id == "session-1"
    assert service.backend._db_path == tmp_path / "database" / "memory.db"


def test_interactive_run_config_uses_adk_native_sse_streaming() -> None:
    run_config = _build_interactive_run_config("proj_1")

    assert run_config.streaming_mode == StreamingMode.SSE
    assert run_config.custom_metadata == {
        "profile": "full",
        "transport": "client_api",
        "project_id": "proj_1",
    }


def test_session_title_uses_visible_request_after_gm_science_context() -> None:
    event = SimpleNamespace(
        author="user",
        content=SimpleNamespace(
            parts=[
                SimpleNamespace(
                    text=(
                        "[Request context]\n"
                        "<gm_science_context>\n"
                        "<project_id>proj_test</project_id>\n"
                        "</gm_science_context>\n\n"
                        "Project context:\nKeep claims bounded.\n\n"
                        "User request:\nCompare the saved papers."
                    )
                )
            ]
        ),
    )

    assert _session_title([event]) == "Compare the saved papers."


def test_session_title_ignores_resource_context_parts() -> None:
    event = SimpleNamespace(
        author="user",
        content=SimpleNamespace(
            parts=[
                SimpleNamespace(text="Compare the saved papers.", part_metadata=None),
                SimpleNamespace(
                    text="private resource content",
                    part_metadata={"gm_science_resource": {"id": "project_file:abc"}},
                ),
            ]
        ),
    )

    assert _session_title([event]) == "Compare the saved papers."


def test_build_adk_user_content_uses_native_parts_and_provenance() -> None:
    resource = ResourceRef(
        id="project_file:abc",
        kind="project_file",
        project_id="proj_1",
        session_id=None,
        display_name="notes.md",
        artifact_type="project_file",
        mime_type="text/markdown",
        version_or_hash="1:10",
        access_mode="read",
        source="workspace",
        artifact_id="",
        relative_path="notes.md",
        url="",
        size_bytes=10,
        created_at="2026-07-18T00:00:00+00:00",
        updated_at="2026-07-18T00:00:00+00:00",
    )
    context = ResolvedResourceContext(
        resource=resource,
        content="# Notes",
        content_status="included",
        content_included=True,
        truncated=False,
    )

    request = _build_adk_user_content("Compare this note.", [context])

    assert len(request.parts) == 2
    assert request.parts[0].text == "Compare this note."
    assert "untrusted research data" in request.parts[1].text
    assert request.parts[1].part_metadata["gm_science_resource"]["id"] == "project_file:abc"
    assert request.parts[1].part_metadata["gm_science_resource"]["content_chars"] == 7


def test_build_adk_user_content_preserves_structured_session_and_skill_metadata() -> None:
    request = _build_adk_user_content(
        "Compare prior findings.",
        [
            ResolvedReferenceContext(
                text="Referenced Session: Earlier work\nUser: Measure X",
                metadata_key="gm_science_session_ref",
                metadata_value={"id": "session-2", "display_name": "Earlier work", "truncated": False},
            ),
            ResolvedReferenceContext(
                text="Referenced Skill: literature-review\nUse primary sources.",
                metadata_key="gm_science_skill_ref",
                metadata_value={"id": "literature-review", "display_name": "Literature Review", "truncated": False},
            ),
        ],
    )

    assert [part.text for part in request.parts] == [
        "Compare prior findings.",
        "Referenced Session: Earlier work\nUser: Measure X",
        "Referenced Skill: literature-review\nUse primary sources.",
    ]
    assert request.parts[1].part_metadata["gm_science_session_ref"]["id"] == "session-2"
    assert request.parts[2].part_metadata["gm_science_skill_ref"]["id"] == "literature-review"


def test_restrict_mcp_servers_env_keeps_only_explicit_project_selection(monkeypatch) -> None:
    monkeypatch.setenv(
        "OPENPPX_MCP_SERVERS_JSON",
        json.dumps(
            {
                "filesystem": {"command": "mcp-filesystem", "env": {"TOKEN": "secret"}},
                "remote-lab": {"url": "https://mcp.example.test"},
            }
        ),
    )

    _restrict_mcp_servers_env('["remote-lab", "missing"]')

    assert json.loads(os.environ["OPENPPX_MCP_SERVERS_JSON"]) == {
        "remote-lab": {"url": "https://mcp.example.test"}
    }


def test_restrict_mcp_servers_env_rejects_invalid_selection_payload(monkeypatch) -> None:
    monkeypatch.setenv("OPENPPX_MCP_SERVERS_JSON", '{"filesystem":{"command":"mcp-filesystem"}}')

    _restrict_mcp_servers_env('{"filesystem": true}')

    assert json.loads(os.environ["OPENPPX_MCP_SERVERS_JSON"]) == {}
