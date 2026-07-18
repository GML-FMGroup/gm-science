from __future__ import annotations

import json
import os
from types import SimpleNamespace

from openppx.runtime.client_api_worker import _restrict_mcp_servers_env, _session_title


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
