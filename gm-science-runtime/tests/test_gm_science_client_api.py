from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from openppx.gm_science.bootstrap import GM_SCIENCE_DEFAULT_AGENT_NAME
from openppx.runtime.client_api_service import ClientApiCoordinator, _ClientApiHandler


def _fake_handler(coordinator: ClientApiCoordinator) -> tuple[_ClientApiHandler, list[tuple[int, dict[str, object]]]]:
    sent: list[tuple[int, dict[str, object]]] = []
    handler = object.__new__(_ClientApiHandler)
    handler.server = SimpleNamespace(coordinator=coordinator)
    handler._send_json = lambda status, payload: sent.append((status, payload))
    return handler, sent


def test_handler_routes_expose_gm_science_project_and_artifact_api(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("GM_SCIENCE_DATA_DIR", str(tmp_path / "gm-science"))
    coordinator = ClientApiCoordinator(data_dir=tmp_path)
    handler, sent = _fake_handler(coordinator)

    handler._parse = lambda: (
        "/api/v1/gm-science/projects",
        ["api", "v1", "gm-science", "projects"],
        {},
    )
    handler._read_json_body = lambda: {"name": "HTTP project", "agent_context": "Cite every claim."}
    _ClientApiHandler.do_POST(handler)
    assert sent[-1][0] == 200
    created = sent[-1][1]
    assert created["ok"] is True
    project = created["data"]["project"]

    handler._parse = lambda: (
        "/api/v1/gm-science/projects",
        ["api", "v1", "gm-science", "projects"],
        {},
    )
    _ClientApiHandler.do_GET(handler)
    assert sent[-1][1]["data"]["items"] == [project]

    handler._parse = lambda: (
        f"/api/v1/gm-science/projects/{project['id']}/artifacts",
        ["api", "v1", "gm-science", "projects", project["id"], "artifacts"],
        {},
    )
    handler._read_json_body = lambda: {"type": "report", "title": "Draft", "path_or_url": "workspace/report.md"}
    _ClientApiHandler.do_POST(handler)
    assert sent[-1][0] == 200
    artifact = sent[-1][1]
    assert artifact["ok"] is True

    _ClientApiHandler.do_GET(handler)
    assert sent[-1][1]["data"]["items"] == [artifact["data"]["artifact"]]


def test_client_api_bootstraps_default_science_agent_in_gm_science_mode(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("GM_SCIENCE_MODE", "1")
    monkeypatch.setenv("GM_SCIENCE_DATA_DIR", str(tmp_path))

    coordinator = ClientApiCoordinator(data_dir=tmp_path)

    agents = coordinator.list_agents()
    assert agents["ok"] is True
    assert agents["data"]["items"][0]["id"] == GM_SCIENCE_DEFAULT_AGENT_NAME
    assert (tmp_path / GM_SCIENCE_DEFAULT_AGENT_NAME / "config.json").is_file()
    assert (tmp_path / "global_config.json").is_file()


def test_client_api_lists_and_creates_gm_science_projects(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("GM_SCIENCE_MODE", "1")
    monkeypatch.setenv("GM_SCIENCE_DATA_DIR", str(tmp_path))

    coordinator = ClientApiCoordinator(data_dir=tmp_path)
    before = coordinator.list_gm_science_projects()
    assert before == {"ok": True, "data": {"items": []}}

    created = coordinator.create_gm_science_project(
        {
            "name": "Protein design",
            "description": "Shown in the project list.",
            "agent_context": "Always keep citations attached to claims.",
        }
    )

    assert created["ok"] is True
    project = created["data"]["project"]
    assert project["id"].startswith("proj_")
    assert project["name"] == "Protein design"
    assert project["description"] == "Shown in the project list."
    assert project["agent_context"] == "Always keep citations attached to claims."
    assert project["enabled_skills"] == ["literature-review"]
    assert project["enabled_connectors"] == ["arxiv", "pubmed", "openalex"]
    assert project["enabled_specialists"] == ["paper_reader", "research_reviewer"]
    assert project["sessions_count"] == 0
    assert project["artifacts_count"] == 0

    listed = coordinator.list_gm_science_projects()
    assert listed["data"]["items"] == [project]


def test_client_api_project_explicit_empty_capabilities_override_defaults(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("GM_SCIENCE_MODE", "1")
    monkeypatch.setenv("GM_SCIENCE_DATA_DIR", str(tmp_path))
    coordinator = ClientApiCoordinator(data_dir=tmp_path)

    created = coordinator.create_gm_science_project(
        {
            "name": "Minimal project",
            "enabled_skills": [],
            "enabled_connectors": [],
            "enabled_specialists": [],
        }
    )

    assert created["ok"] is True
    project = created["data"]["project"]
    assert project["enabled_skills"] == []
    assert project["enabled_connectors"] == []
    assert project["enabled_specialists"] == []


def test_client_api_rejects_gm_science_project_without_name(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("GM_SCIENCE_DATA_DIR", str(tmp_path / "gm-science"))

    coordinator = ClientApiCoordinator(data_dir=tmp_path)
    payload = coordinator.create_gm_science_project({"description": "missing name"})

    assert payload["ok"] is False
    assert payload["error"]["code"] == "INVALID_REQUEST"


def test_client_api_lists_gm_science_artifacts(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("GM_SCIENCE_DATA_DIR", str(tmp_path / "gm-science"))

    coordinator = ClientApiCoordinator(data_dir=tmp_path)
    project = coordinator.create_gm_science_project({"name": "Literature"})["data"]["project"]
    artifact = coordinator.create_gm_science_artifact(
        project["id"],
        {
            "type": "paper",
            "title": "A useful paper",
            "path_or_url": "https://example.test/paper",
            "mime_type": "text/html",
            "metadata": {"source": "manual"},
            "provenance": {"created_by": "test"},
        },
    )

    assert artifact["ok"] is True
    listed = coordinator.list_gm_science_artifacts(project["id"])
    assert listed["ok"] is True
    assert listed["data"]["items"] == [artifact["data"]["artifact"]]


def test_client_api_project_run_injects_agent_context(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("GM_SCIENCE_DATA_DIR", str(tmp_path / "gm-science"))
    (tmp_path / "global_config.json").write_text(
        json.dumps({"agents": [{"name": "science-research", "enabled": True}]}),
        encoding="utf-8",
    )
    agent_dir = tmp_path / "science-research"
    agent_dir.mkdir()
    (agent_dir / "config.json").write_text(
        json.dumps({"agent": {"workspace": "workspace/science-research"}}),
        encoding="utf-8",
    )
    observed_cmd: list[str] = []

    class _ImmediateProcess:
        stdout = iter([json.dumps({"type": "final", "text": "ok"}) + "\n"])
        stderr = iter(())

        def poll(self) -> int:
            return 0

        def terminate(self) -> None:
            return None

        def wait(self) -> int:
            return 0

    def fake_popen(cmd: list[str], **_kwargs: object) -> _ImmediateProcess:
        observed_cmd.extend(cmd)
        return _ImmediateProcess()

    monkeypatch.setattr("openppx.runtime.client_api_service.subprocess.Popen", fake_popen)

    coordinator = ClientApiCoordinator(data_dir=tmp_path)
    project = coordinator.create_gm_science_project(
        {
            "name": "Context project",
            "agent_context": "Prefer reproducible scripts and cite sources.",
        }
    )["data"]["project"]

    payload = coordinator.create_gm_science_project_run(project["id"], "session_1", "Summarize the papers.")

    assert payload["ok"] is True
    message_index = observed_cmd.index("--message") + 1
    message = observed_cmd[message_index]
    assert "<gm_science_context>" in message
    assert f"<project_id>{project['id']}</project_id>" in message
    assert "<session_id>session_1</session_id>" in message
    assert f"<workspace>{project['workspace_path']}</workspace>" in message
    assert "arxiv:ok" in message
    assert "pubmed:needs_configuration" in message
    assert "openalex:needs_configuration" in message
    assert "paper_reader:ok" in message
    assert "research_reviewer:ok" in message
    assert "Project context:" in message
    assert "Prefer reproducible scripts and cite sources." in message
    assert "User request:" in message
    assert "Summarize the papers." in message
    project_index = observed_cmd.index("--project-id") + 1
    assert observed_cmd[project_index] == project["id"]


def test_client_api_project_run_injects_machine_context_without_custom_context(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("GM_SCIENCE_DATA_DIR", str(tmp_path / "gm-science"))
    (tmp_path / "global_config.json").write_text(
        json.dumps({"agents": [{"name": "science-research", "enabled": True}]}),
        encoding="utf-8",
    )
    agent_dir = tmp_path / "science-research"
    agent_dir.mkdir()
    (agent_dir / "config.json").write_text(
        json.dumps({"agent": {"workspace": "workspace/science-research"}}),
        encoding="utf-8",
    )
    observed_cmd: list[str] = []

    class _ImmediateProcess:
        stdout = iter([json.dumps({"type": "final", "text": "ok"}) + "\n"])
        stderr = iter(())

        def poll(self) -> int:
            return 0

        def terminate(self) -> None:
            return None

        def wait(self) -> int:
            return 0

    def fake_popen(cmd: list[str], **_kwargs: object) -> _ImmediateProcess:
        observed_cmd.extend(cmd)
        return _ImmediateProcess()

    monkeypatch.setattr("openppx.runtime.client_api_service.subprocess.Popen", fake_popen)
    coordinator = ClientApiCoordinator(data_dir=tmp_path)
    project = coordinator.create_gm_science_project({"name": "No custom context"})["data"]["project"]

    payload = coordinator.create_gm_science_project_run(project["id"], "session_2", "Search papers.")

    assert payload["ok"] is True
    message = observed_cmd[observed_cmd.index("--message") + 1]
    assert f"<project_id>{project['id']}</project_id>" in message
    assert "<session_id>session_2</session_id>" in message
    assert "User request:\nSearch papers." in message
