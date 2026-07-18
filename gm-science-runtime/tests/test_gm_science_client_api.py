from __future__ import annotations

import json
import time
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


def _write_test_skill(root: Path, name: str, description: str) -> None:
    """Create a minimal Skill fixture under the requested registry root."""

    skill_dir = root / name
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: {description}\n---\n\n# {name}\n",
        encoding="utf-8",
    )


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


def test_handler_routes_expose_project_python_runs(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("GM_SCIENCE_MODE", "1")
    monkeypatch.setenv("GM_SCIENCE_DATA_DIR", str(tmp_path))
    coordinator = ClientApiCoordinator(data_dir=tmp_path)
    project = coordinator.create_gm_science_project({"name": "Run API"})["data"]["project"]
    session = coordinator.create_session(
        GM_SCIENCE_DEFAULT_AGENT_NAME,
        project_id=project["id"],
    )["data"]["session"]
    handler, sent = _fake_handler(coordinator)
    handler._parse = lambda: (
        f"/api/v1/gm-science/projects/{project['id']}/runs",
        ["api", "v1", "gm-science", "projects", project["id"], "runs"],
        {},
    )
    handler._read_json_body = lambda: {
        "title": "HTTP Python",
        "session_id": session["id"],
        "source": "print('http python')",
        "input": {"argv": []},
    }

    _ClientApiHandler.do_POST(handler)
    assert sent[-1][0] == 200
    created = sent[-1][1]["data"]["run"]
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        payload = coordinator.get_gm_science_run(project["id"], created["task_id"])
        if payload["data"]["run"]["status"] in {"completed", "failed"}:
            break
        time.sleep(0.05)
    assert payload["data"]["run"]["status"] == "completed"

    _ClientApiHandler.do_GET(handler)
    assert sent[-1][0] == 200
    assert sent[-1][1]["data"]["items"][0]["task_id"] == created["task_id"]

    handler._parse = lambda: (
        f"/api/v1/gm-science/projects/{project['id']}/runs/{created['task_id']}",
        ["api", "v1", "gm-science", "projects", project["id"], "runs", created["task_id"]],
        {},
    )
    _ClientApiHandler.do_GET(handler)
    assert sent[-1][0] == 200
    assert "http python" in sent[-1][1]["data"]["run"]["log_preview"]

    handler._parse = lambda: (
        f"/api/v1/gm-science/projects/{project['id']}/runs/{created['task_id']}/retry",
        [
            "api",
            "v1",
            "gm-science",
            "projects",
            project["id"],
            "runs",
            created["task_id"],
            "retry",
        ],
        {},
    )
    handler._read_json_body = lambda: {}
    _ClientApiHandler.do_POST(handler)
    assert sent[-1][0] == 200
    assert sent[-1][1]["data"]["run"]["parent_task_id"] == created["task_id"]


def test_handler_routes_expose_dataset_and_review_before_run_analysis(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("GM_SCIENCE_MODE", "1")
    monkeypatch.setenv("GM_SCIENCE_DATA_DIR", str(tmp_path))
    coordinator = ClientApiCoordinator(data_dir=tmp_path)
    project = coordinator.create_gm_science_project({"name": "Data API"})["data"]["project"]
    source = tmp_path / "study.csv"
    source.write_text("group,x,y\nA,1,2\nA,2,4\nB,3,6\n", encoding="utf-8")
    handler, sent = _fake_handler(coordinator)

    handler._parse = lambda: (
        f"/api/v1/gm-science/projects/{project['id']}/datasets/import",
        ["api", "v1", "gm-science", "projects", project["id"], "datasets", "import"],
        {},
    )
    handler._read_json_body = lambda: {"source_path": str(source), "title": "Study"}
    _ClientApiHandler.do_POST(handler)
    assert sent[-1][0] == 200
    dataset = sent[-1][1]["data"]["dataset"]

    handler._parse = lambda: (
        f"/api/v1/gm-science/projects/{project['id']}/datasets/{dataset['artifact_id']}",
        ["api", "v1", "gm-science", "projects", project["id"], "datasets", dataset["artifact_id"]],
        {},
    )
    _ClientApiHandler.do_GET(handler)
    assert sent[-1][0] == 200
    assert sent[-1][1]["data"]["dataset"]["profile"]["row_count"] == 3

    handler._parse = lambda: (
        f"/api/v1/gm-science/projects/{project['id']}/analyses",
        ["api", "v1", "gm-science", "projects", project["id"], "analyses"],
        {},
    )
    handler._read_json_body = lambda: {
        "objective": "Compare groups and inspect correlations.",
        "dataset_artifact_ids": [dataset["artifact_id"]],
    }
    _ClientApiHandler.do_POST(handler)
    assert sent[-1][0] == 200
    draft = sent[-1][1]["data"]["analysis"]
    assert draft["status"] == "draft"
    assert "Generated by gm-science" in draft["source"]

    handler._parse = lambda: (
        f"/api/v1/gm-science/projects/{project['id']}/analyses/{draft['id']}/run",
        ["api", "v1", "gm-science", "projects", project["id"], "analyses", draft["id"], "run"],
        {},
    )
    handler._read_json_body = lambda: {}
    _ClientApiHandler.do_POST(handler)
    assert sent[-1][0] == 200
    started = sent[-1][1]["data"]["analysis"]
    assert started["task_id"]

    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        detail = coordinator.get_gm_science_analysis(project["id"], draft["id"])["data"]["analysis"]
        if detail["status"] in {"completed", "failed"}:
            break
        time.sleep(0.05)
    assert detail["status"] == "completed"

    retried = coordinator.retry_gm_science_run(project["id"], started["task_id"])
    assert retried["ok"] is True
    retry_task_id = retried["data"]["run"]["task_id"]
    assert retry_task_id != started["task_id"]
    relinked = coordinator.get_gm_science_analysis(project["id"], draft["id"])["data"]["analysis"]
    assert relinked["task_id"] == retry_task_id


def test_handler_routes_expose_project_capability_api(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("GM_SCIENCE_MODE", "1")
    monkeypatch.setenv("GM_SCIENCE_DATA_DIR", str(tmp_path))
    coordinator = ClientApiCoordinator(data_dir=tmp_path)
    project = coordinator.create_gm_science_project({"name": "Capabilities"})["data"]["project"]
    handler, sent = _fake_handler(coordinator)

    handler._parse = lambda: (
        f"/api/v1/gm-science/projects/{project['id']}/capabilities",
        ["api", "v1", "gm-science", "projects", project["id"], "capabilities"],
        {},
    )
    _ClientApiHandler.do_GET(handler)
    assert sent[-1][0] == 200
    assert sent[-1][1]["data"]["project_id"] == project["id"]

    handler._read_json_body = lambda: {
        "enabled_skills": [],
        "enabled_connectors": ["arxiv"],
        "enabled_specialists": ["research_reviewer"],
    }
    _ClientApiHandler.do_PATCH(handler)
    assert sent[-1][0] == 200
    assert sent[-1][1]["data"]["project"]["enabled_connectors"] == ["arxiv"]


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


def test_client_api_associates_sessions_with_projects_and_reports_counts(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("GM_SCIENCE_MODE", "1")
    monkeypatch.setenv("GM_SCIENCE_DATA_DIR", str(tmp_path))
    coordinator = ClientApiCoordinator(data_dir=tmp_path)
    project = coordinator.create_gm_science_project({"name": "Session project"})["data"]["project"]

    created = coordinator.create_session(
        GM_SCIENCE_DEFAULT_AGENT_NAME,
        project_id=project["id"],
    )

    assert created["ok"] is True
    session = created["data"]["session"]
    assert session["project_id"] == project["id"]
    listed_sessions = coordinator.list_sessions(GM_SCIENCE_DEFAULT_AGENT_NAME)
    assert listed_sessions["data"]["items"][0]["project_id"] == project["id"]
    listed_projects = coordinator.list_gm_science_projects()
    assert listed_projects["data"]["items"][0]["sessions_count"] == 1


def test_client_api_rejects_project_run_for_unassociated_session(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("GM_SCIENCE_MODE", "1")
    monkeypatch.setenv("GM_SCIENCE_DATA_DIR", str(tmp_path))
    coordinator = ClientApiCoordinator(data_dir=tmp_path)
    project = coordinator.create_gm_science_project({"name": "Bound sessions"})["data"]["project"]

    payload = coordinator.create_gm_science_project_run(project["id"], "orphan-session", "Do work.")

    assert payload["ok"] is False
    assert payload["error"]["code"] == "SESSION_NOT_IN_PROJECT"


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


def test_client_api_normalizes_capabilities_when_creating_project(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("GM_SCIENCE_MODE", "1")
    monkeypatch.setenv("GM_SCIENCE_DATA_DIR", str(tmp_path))
    coordinator = ClientApiCoordinator(data_dir=tmp_path)

    created = coordinator.create_gm_science_project(
        {
            "name": "Ordered project",
            "enabled_skills": [],
            "enabled_connectors": ["openalex", "arxiv", "openalex"],
            "enabled_specialists": ["research_reviewer"],
        }
    )

    assert created["ok"] is True
    project = created["data"]["project"]
    assert project["enabled_connectors"] == ["arxiv", "openalex"]
    assert project["enabled_specialists"] == ["research_reviewer"]


def test_client_api_rejects_unknown_capability_when_creating_project(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("GM_SCIENCE_MODE", "1")
    monkeypatch.setenv("GM_SCIENCE_DATA_DIR", str(tmp_path))
    coordinator = ClientApiCoordinator(data_dir=tmp_path)

    payload = coordinator.create_gm_science_project(
        {
            "name": "Invalid project",
            "enabled_skills": ["unknown-skill"],
        }
    )

    assert payload["ok"] is False
    assert payload["error"]["code"] == "INVALID_REQUEST"
    assert "unknown-skill" in payload["error"]["message"]


def test_client_api_lists_capabilities_with_global_and_project_status(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("GM_SCIENCE_MODE", "1")
    monkeypatch.setenv("GM_SCIENCE_DATA_DIR", str(tmp_path))
    coordinator = ClientApiCoordinator(data_dir=tmp_path)
    project = coordinator.create_gm_science_project({"name": "Catalog"})["data"]["project"]

    payload = coordinator.list_gm_science_capabilities(project["id"])

    assert payload["ok"] is True
    assert payload["data"]["project_id"] == project["id"]
    items = {item["id"]: item for item in payload["data"]["items"]}
    ordered_ids = list(items)
    assert "docx" in ordered_ids
    assert "literature-review" in ordered_ids
    arxiv_index = ordered_ids.index("arxiv")
    assert ordered_ids[arxiv_index : arxiv_index + 3] == ["arxiv", "pubmed", "openalex"]
    assert ordered_ids[-2:] == ["paper_reader", "research_reviewer"]
    assert items["literature-review"] == {
        "id": "literature-review",
        "kind": "skill",
        "name": "Literature Review",
        "description": "Search scholarly sources, build an evidence matrix, and register a cited review in gm-science.",
        "source": "built_in",
        "version": "",
        "license": "",
        "files": ["SKILL.md"],
        "available": True,
        "default_enabled": True,
        "project_enabled": True,
        "status": "ready",
        "status_detail": "",
        "metadata": {
            "registry_source": "builtin",
            "file_count": 1,
            "files_truncated": False,
        },
    }
    assert items["arxiv"]["source"] == "built_in"
    assert items["arxiv"]["files"] == []
    assert items["arxiv"]["status"] == "ready"
    assert items["pubmed"]["status"] == "needs_configuration"
    assert items["pubmed"]["status_detail"] == "Set science.literature.pubmed.email."
    assert items["openalex"]["status"] == "needs_configuration"
    assert items["paper_reader"]["metadata"]["auto_dispatch"] is True
    assert "api_key" not in json.dumps(payload)


def test_client_api_discovers_and_selects_agent_local_skills(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("GM_SCIENCE_MODE", "1")
    monkeypatch.setenv("GM_SCIENCE_DATA_DIR", str(tmp_path))
    bundled_dir = tmp_path / "test-bundled-skills"
    _write_test_skill(
        bundled_dir,
        "literature-review",
        "Search scholarly sources and register a cited review.",
    )
    _write_test_skill(bundled_dir, "docx", "Create and edit Word documents.")
    monkeypatch.setenv("OPENPPX_BUILTIN_SKILLS_DIR", str(bundled_dir))
    coordinator = ClientApiCoordinator(data_dir=tmp_path)
    _write_test_skill(
        tmp_path / GM_SCIENCE_DEFAULT_AGENT_NAME / "skills",
        "local-analysis",
        "Analyze local tabular datasets.",
    )

    created = coordinator.create_gm_science_project(
        {
            "name": "Local skills",
            "enabled_skills": ["local-analysis", "docx"],
            "enabled_connectors": [],
            "enabled_specialists": [],
        }
    )

    assert created["ok"] is True
    project = created["data"]["project"]
    assert project["enabled_skills"] == ["docx", "local-analysis"]
    payload = coordinator.list_gm_science_capabilities(project["id"])
    skills = {
        item["id"]: item
        for item in payload["data"]["items"]
        if item["kind"] == "skill"
    }
    assert list(skills) == ["docx", "literature-review", "local-analysis"]
    assert skills["local-analysis"]["source"] == "local"
    assert skills["local-analysis"]["project_enabled"] is True


def test_client_api_updates_project_capabilities_in_catalog_order(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("GM_SCIENCE_MODE", "1")
    monkeypatch.setenv("GM_SCIENCE_DATA_DIR", str(tmp_path))
    coordinator = ClientApiCoordinator(data_dir=tmp_path)
    project = coordinator.create_gm_science_project({"name": "Catalog"})["data"]["project"]

    payload = coordinator.update_gm_science_project_capabilities(
        project["id"],
        {
            "enabled_skills": [],
            "enabled_connectors": ["openalex", "arxiv", "openalex"],
            "enabled_specialists": ["research_reviewer"],
        },
    )

    assert payload["ok"] is True
    updated = payload["data"]["project"]
    assert updated["enabled_skills"] == []
    assert updated["enabled_connectors"] == ["arxiv", "openalex"]
    assert updated["enabled_specialists"] == ["research_reviewer"]
    statuses = {item["id"]: item for item in payload["data"]["capabilities"]}
    assert statuses["pubmed"]["project_enabled"] is False
    assert statuses["openalex"]["project_enabled"] is True


def test_client_api_rejects_unknown_project_capability(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("GM_SCIENCE_MODE", "1")
    monkeypatch.setenv("GM_SCIENCE_DATA_DIR", str(tmp_path))
    coordinator = ClientApiCoordinator(data_dir=tmp_path)
    project = coordinator.create_gm_science_project({"name": "Catalog"})["data"]["project"]

    payload = coordinator.update_gm_science_project_capabilities(
        project["id"],
        {
            "enabled_skills": ["unknown-skill"],
            "enabled_connectors": [],
            "enabled_specialists": [],
        },
    )

    assert payload["ok"] is False
    assert payload["error"]["code"] == "INVALID_REQUEST"
    assert "unknown-skill" in payload["error"]["message"]


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
    coordinator._gm_science_store.link_project_session(
        project_id=project["id"],
        session_id="session_1",
        agent_id=GM_SCIENCE_DEFAULT_AGENT_NAME,
    )

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
    coordinator._gm_science_store.link_project_session(
        project_id=project["id"],
        session_id="session_2",
        agent_id=GM_SCIENCE_DEFAULT_AGENT_NAME,
    )

    payload = coordinator.create_gm_science_project_run(project["id"], "session_2", "Search papers.")

    assert payload["ok"] is True
    message = observed_cmd[observed_cmd.index("--message") + 1]
    assert f"<project_id>{project['id']}</project_id>" in message
    assert "<session_id>session_2</session_id>" in message
    assert "User request:\nSearch papers." in message
