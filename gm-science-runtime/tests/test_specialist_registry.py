from __future__ import annotations

from openppx.gm_science.specialists.agents import build_specialist_tools
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
    assert "model" not in str(payload)
