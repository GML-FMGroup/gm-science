from __future__ import annotations

import json
from unittest.mock import patch

from openppx.gm_science.specialists.agents import (
    _specialist_server_config,
    build_specialist_tools,
    specialist_dispatch_guidance,
)
from openppx.gm_science.specialists.config import parse_specialist_config
from openppx.gm_science.specialists.registry import list_specialist_specs, science_list_specialists
from openppx.gm_science.store import GmScienceStore


def test_registry_exposes_two_bounded_builtin_specialists() -> None:
    specs = list_specialist_specs(parse_specialist_config({}))

    assert [spec.name for spec in specs] == ["paper_reader", "research_reviewer"]
    assert all(spec.read_only for spec in specs)
    assert all(spec.network_access is False for spec in specs)
    assert all(spec.shell_access is False for spec in specs)


def test_specialist_agents_receive_only_their_read_tool() -> None:
    specialist_tools = build_specialist_tools(
        config=parse_specialist_config({}),
        model="gemini-2.0-flash",
    )

    child_tools = {
        tool.name: [getattr(item, "__name__", getattr(item, "name", "")) for item in tool.agent.tools]
        for tool in specialist_tools
    }
    assert child_tools == {
        "paper_reader": ["science_read_paper_bundle"],
        "research_reviewer": ["science_read_review_bundle"],
    }


def test_registry_and_agent_factory_build_configured_specialist_with_assigned_tools() -> None:
    config = parse_specialist_config(
        {
            "science": {
                "specialists": {
                    "paperReader": {"enabled": False},
                    "reviewer": {"enabled": False},
                    "custom": {
                        "literature_scout": {
                            "title": "Literature Scout",
                            "description": "Find focused literature evidence.",
                            "instructions": "Prefer primary sources.",
                            "connectors": ["pubmed", "openalex"],
                        }
                    },
                }
            }
        }
    )

    specs = list_specialist_specs(config)
    assert [spec.name for spec in specs] == [
        "paper_reader",
        "research_reviewer",
        "literature_scout",
    ]
    assert specs[-1].source == "local"
    assert specs[-1].connectors == ("pubmed", "openalex")
    assert specs[-1].instructions == "Prefer primary sources."

    specialist_tools = build_specialist_tools(config=config, model="gemini-2.0-flash")

    assert [tool.name for tool in specialist_tools] == ["literature_scout"]
    assert [getattr(item, "__name__", "") for item in specialist_tools[0].agent.tools] == [
        "science_search"
    ]


def test_agent_factory_skips_custom_specialist_with_missing_skill() -> None:
    config = parse_specialist_config(
        {
            "science": {
                "specialists": {
                    "paperReader": {"enabled": False},
                    "reviewer": {"enabled": False},
                    "custom": {
                        "broken_specialist": {
                            "description": "References a missing capability.",
                            "skills": ["not-installed"],
                        }
                    },
                }
            }
        }
    )

    assert build_specialist_tools(config=config, model="gemini-2.0-flash") == []


def test_dispatch_guidance_skips_custom_specialist_with_missing_dependency() -> None:
    config = parse_specialist_config(
        {
            "science": {
                "specialists": {
                    "paperReader": {"enabled": False},
                    "reviewer": {"enabled": False},
                    "custom": {
                        "broken_specialist": {
                            "description": "References a missing capability.",
                            "skills": ["not-installed"],
                            "autoDispatch": True,
                        }
                    },
                }
            }
        }
    )

    with patch(
        "openppx.gm_science.specialists.agents.specialist_runtime_capability_ids",
        return_value=(set(), set()),
    ):
        guidance = specialist_dispatch_guidance(config)

    assert "Use broken_specialist" not in guidance


def test_dispatch_guidance_includes_available_custom_specialist() -> None:
    config = parse_specialist_config(
        {
            "science": {
                "specialists": {
                    "paperReader": {"enabled": False},
                    "reviewer": {"enabled": False},
                    "custom": {
                        "literature_scout": {
                            "description": "Find focused literature evidence.",
                            "skills": ["literature-review"],
                            "connectors": ["pubmed"],
                            "autoDispatch": True,
                        }
                    },
                }
            }
        }
    )

    with patch(
        "openppx.gm_science.specialists.agents.specialist_runtime_capability_ids",
        return_value=({"literature-review"}, {"pubmed"}),
    ):
        guidance = specialist_dispatch_guidance(config)

    assert "Use literature_scout" in guidance


def test_agent_factory_mounts_only_selected_mcp_connector(monkeypatch) -> None:
    monkeypatch.setenv(
        "OPENPPX_MCP_SERVERS_JSON",
        json.dumps(
            {
                "lab": {"command": "lab-mcp"},
                "unassigned": {"command": "other-mcp"},
            }
        ),
    )
    config = parse_specialist_config(
        {
            "science": {
                "specialists": {
                    "paperReader": {"enabled": False},
                    "reviewer": {"enabled": False},
                    "custom": {
                        "lab_specialist": {
                            "description": "Use one assigned laboratory connector.",
                            "connectors": ["mcp:lab"],
                        }
                    },
                }
            }
        }
    )

    specialist_tools = build_specialist_tools(config=config, model="gemini-2.0-flash")

    child_toolsets = specialist_tools[0].agent.tools
    assert [tool.meta.name for tool in child_toolsets] == ["lab"]


def test_specialist_tool_filter_intersects_connector_policy() -> None:
    assert _specialist_server_config(
        {"command": "lab-mcp", "toolFilter": ["read", "search"]},
        ("search", "write"),
    ) == {"command": "lab-mcp", "toolFilter": ["search"]}
    assert _specialist_server_config(
        {"command": "lab-mcp"},
        ("search", "write"),
    ) == {"command": "lab-mcp", "toolFilter": ["search", "write"]}


def test_public_specialist_list_applies_project_allowlist(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("GM_SCIENCE_DATA_DIR", str(tmp_path))
    store = GmScienceStore(tmp_path)
    project = store.create_project(
        name="Review",
        description="",
        agent_context="",
        enabled_specialists=["paper_reader"],
    )

    payload = science_list_specialists(project.id)

    statuses = {item["name"]: item for item in payload["specialists"]}
    assert statuses["paper_reader"]["available"] is True
    assert statuses["research_reviewer"]["available"] is False
    assert statuses["research_reviewer"]["status_detail"] == "Not enabled for this Project."
    assert "model" not in str(payload)


def test_public_specialist_list_applies_assigned_capability_allowlists(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("GM_SCIENCE_DATA_DIR", str(tmp_path))
    config = parse_specialist_config(
        {
            "science": {
                "specialists": {
                    "custom": {
                        "literature_scout": {
                            "description": "Find focused literature evidence.",
                            "skills": ["literature-review"],
                            "connectors": ["pubmed"],
                        }
                    }
                }
            }
        }
    )
    store = GmScienceStore(tmp_path)
    project = store.create_project(
        name="Scout",
        description="",
        agent_context="",
        enabled_skills=["literature-review"],
        enabled_connectors=[],
        enabled_specialists=["literature_scout"],
    )

    with patch(
        "openppx.gm_science.specialists.registry.load_specialist_config",
        return_value=config,
    ):
        with patch(
            "openppx.gm_science.specialists.registry.specialist_runtime_capability_ids",
            return_value=({"literature-review"}, {"pubmed"}),
        ):
            payload = science_list_specialists(project.id)

    scout = next(item for item in payload["specialists"] if item["name"] == "literature_scout")
    assert scout["project_enabled"] is True
    assert scout["available"] is False
    assert scout["status"] == "unavailable"
    assert scout["status_detail"] == "Project-disabled Connectors: pubmed."
