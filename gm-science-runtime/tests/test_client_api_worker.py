from __future__ import annotations

import json
import os
from types import SimpleNamespace

from openppx.gm_science.resources.context import ResolvedResourceContext
from openppx.gm_science.resources.models import ResourceRef
from openppx.runtime.client_api_worker import _build_adk_user_content, _restrict_mcp_servers_env, _session_title


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
