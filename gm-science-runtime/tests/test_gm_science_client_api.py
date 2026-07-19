from __future__ import annotations

import json
import time
from pathlib import Path
from types import SimpleNamespace

from openppx.gm_science.bootstrap import GM_SCIENCE_DEFAULT_AGENT_NAME
from openppx.gm_science.catalog import BUILTIN_SCIENCE_SKILLS, SCIENCE_CONNECTORS
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


def test_handler_decodes_encoded_domain_ids_in_path_segments() -> None:
    handler = object.__new__(_ClientApiHandler)
    handler.path = (
        "/api/v1/gm-science/projects/proj_1/memory/notes/"
        "fact%3Aabc123?user_id=researcher"
    )

    _path, segments, query = handler._parse()

    assert segments[-1] == "fact:abc123"
    assert query == {"user_id": "researcher"}


def test_handler_rejects_invalid_json_without_dispatching() -> None:
    handler = object.__new__(_ClientApiHandler)
    sent: list[tuple[int, dict[str, object]]] = []
    handler._parse = lambda: (
        "/api/v1/gm-science/projects",
        ["api", "v1", "gm-science", "projects"],
        {},
    )
    handler._read_json_body = lambda: (_ for _ in ()).throw(
        json.JSONDecodeError("invalid JSON", "{", 1)
    )
    handler._send_json = lambda status, payload: sent.append((status, payload))

    _ClientApiHandler.do_POST(handler)

    assert sent == [
        (
            400,
            {
                "ok": False,
                "error": {
                    "code": "INVALID_REQUEST",
                    "message": "Request body must contain a valid JSON object.",
                    "details": {},
                },
            },
        )
    ]


def test_handler_routes_create_local_capabilities_with_stable_statuses(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("GM_SCIENCE_MODE", "1")
    monkeypatch.setenv("GM_SCIENCE_DATA_DIR", str(tmp_path))
    coordinator = ClientApiCoordinator(data_dir=tmp_path)
    handler, sent = _fake_handler(coordinator)

    handler._parse = lambda: (
        "/api/v1/gm-science/capabilities/skills",
        ["api", "v1", "gm-science", "capabilities", "skills"],
        {},
    )
    handler._read_json_body = lambda: {
        "id": "assay-quality",
        "name": "Assay Quality",
        "description": "Review assay quality.",
        "content": "# Assay Quality",
    }
    _ClientApiHandler.do_POST(handler)
    assert sent[-1][0] == 200
    assert sent[-1][1]["data"]["capability"]["id"] == "assay-quality"

    _ClientApiHandler.do_POST(handler)
    assert sent[-1][0] == 409
    assert sent[-1][1]["error"]["code"] == "CAPABILITY_CONFLICT"

    handler._parse = lambda: (
        "/api/v1/gm-science/capabilities/connectors",
        ["api", "v1", "gm-science", "capabilities", "connectors"],
        {},
    )
    handler._read_json_body = lambda: {
        "id": "local-files",
        "name": "Local Files",
        "description": "Read local files.",
        "connection_type": "local",
        "command_line": "mcp-server-filesystem /tmp/research",
    }
    _ClientApiHandler.do_POST(handler)
    assert sent[-1][0] == 200
    assert sent[-1][1]["data"]["capability"]["id"] == "mcp:local-files"

    handler._parse = lambda: (
        "/api/v1/gm-science/capabilities/specialists",
        ["api", "v1", "gm-science", "capabilities", "specialists"],
        {},
    )
    handler._read_json_body = lambda: {
        "id": "assay_reviewer",
        "name": "Assay Reviewer",
        "description": "Review assay quality.",
        "instructions": "Check controls and limitations.",
        "skills": ["assay-quality"],
        "connectors": ["mcp:local-files"],
    }
    _ClientApiHandler.do_POST(handler)
    assert sent[-1][0] == 200
    specialist = sent[-1][1]["data"]["capability"]
    assert specialist["id"] == "assay_reviewer"
    assert specialist["metadata"]["assigned_skills"] == ["assay-quality"]


def test_handler_maps_capability_authoring_permission_denials_to_403(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("GM_SCIENCE_MODE", "1")
    monkeypatch.setenv("GM_SCIENCE_DATA_DIR", str(tmp_path))
    coordinator = ClientApiCoordinator(data_dir=tmp_path)
    coordinator.update_gm_science_settings(
        {"permission_grants": {"publish_skill": False}}
    )
    handler, sent = _fake_handler(coordinator)
    handler._parse = lambda: (
        "/api/v1/gm-science/capabilities/skills",
        ["api", "v1", "gm-science", "capabilities", "skills"],
        {},
    )
    handler._read_json_body = lambda: {
        "id": "blocked-skill",
        "name": "Blocked Skill",
        "description": "Must not be created.",
        "content": "# Blocked",
    }

    _ClientApiHandler.do_POST(handler)

    assert sent[-1][0] == 403
    assert sent[-1][1]["error"]["code"] == "PERMISSION_DENIED"


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


def test_handler_routes_expose_local_storage_and_usage_snapshots(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("GM_SCIENCE_MODE", "1")
    monkeypatch.setenv("GM_SCIENCE_DATA_DIR", str(tmp_path))
    coordinator = ClientApiCoordinator(data_dir=tmp_path)
    handler, sent = _fake_handler(coordinator)

    handler._parse = lambda: (
        "/api/v1/gm-science/storage",
        ["api", "v1", "gm-science", "storage"],
        {},
    )
    _ClientApiHandler.do_GET(handler)
    assert sent[-1][0] == 200
    storage = sent[-1][1]["data"]["storage"]
    assert storage["data_location"] == str(tmp_path.resolve())
    assert storage["scan_complete"] is True
    assert {item["id"] for item in storage["categories"]} == {
        "workspaces",
        "databases",
        "cache",
        "configuration",
        "logs",
        "other",
    }

    handler._parse = lambda: (
        "/api/v1/gm-science/usage?window=24h",
        ["api", "v1", "gm-science", "usage"],
        {"window": "24h"},
    )
    _ClientApiHandler.do_GET(handler)
    assert sent[-1][0] == 200
    usage = sent[-1][1]["data"]["usage"]
    assert usage["window"] == "24h"
    assert usage["local_estimate"] is True
    assert usage["cost"]["available"] is False

    handler._parse = lambda: (
        "/api/v1/gm-science/usage?window=90d",
        ["api", "v1", "gm-science", "usage"],
        {"window": "90d"},
    )
    _ClientApiHandler.do_GET(handler)
    assert sent[-1][0] == 400
    assert sent[-1][1]["error"]["code"] == "INVALID_REQUEST"


def test_handler_routes_manage_reviewable_project_memory(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("GM_SCIENCE_MODE", "1")
    monkeypatch.setenv("GM_SCIENCE_DATA_DIR", str(tmp_path / "gm-science"))
    coordinator = ClientApiCoordinator(data_dir=tmp_path)
    project = coordinator.create_gm_science_project({"name": "Memory API"})["data"]["project"]
    handler, sent = _fake_handler(coordinator)
    user_id = "researcher"

    handler._parse = lambda: (
        f"/api/v1/gm-science/projects/{project['id']}/memory/notes",
        ["api", "v1", "gm-science", "projects", project["id"], "memory", "notes"],
        {},
    )
    handler._read_json_body = lambda: {
        "user_id": user_id,
        "scope": "user",
        "category": "Preferences",
        "text": "Prefer concise uncertainty summaries.",
    }
    _ClientApiHandler.do_POST(handler)
    assert sent[-1][0] == 200
    note = sent[-1][1]["data"]["note"]

    handler._parse = lambda: (
        f"/api/v1/gm-science/projects/{project['id']}/memory/notes/{note['id']}",
        [
            "api",
            "v1",
            "gm-science",
            "projects",
            project["id"],
            "memory",
            "notes",
            note["id"],
        ],
        {},
    )
    handler._read_json_body = lambda: {
        "user_id": user_id,
        "category": "Preferences",
        "text": "Prefer concise summaries with uncertainty labels.",
    }
    _ClientApiHandler.do_PATCH(handler)
    assert sent[-1][1]["data"]["note"]["text"].endswith("uncertainty labels.")

    candidate = coordinator._gm_science_memory.propose_candidate(
        project_id=project["id"],
        user_id=user_id,
        session_id="session-memory",
        scope="project",
        category="Project context",
        text="Use GRCh38 for genome references.",
        rationale="A durable Project convention.",
        model="openai-codex/gpt-5.5",
    )
    handler._parse = lambda: (
        f"/api/v1/gm-science/projects/{project['id']}/memory/candidates/{candidate['id']}/review",
        [
            "api",
            "v1",
            "gm-science",
            "projects",
            project["id"],
            "memory",
            "candidates",
            candidate["id"],
            "review",
        ],
        {},
    )
    handler._read_json_body = lambda: {"user_id": user_id, "decision": "approve"}
    _ClientApiHandler.do_POST(handler)
    assert sent[-1][1]["data"]["candidate"]["status"] == "approved"

    handler._parse = lambda: (
        f"/api/v1/gm-science/projects/{project['id']}/memory",
        ["api", "v1", "gm-science", "projects", project["id"], "memory"],
        {"user_id": user_id},
    )
    _ClientApiHandler.do_GET(handler)
    workspace = sent[-1][1]["data"]["memory"]
    assert {item["scope"] for item in workspace["notes"]} == {"user", "project"}
    assert next(item for item in workspace["candidates"] if item["id"] == candidate["id"])["status"] == "approved"

    handler._parse = lambda: (
        f"/api/v1/gm-science/projects/{project['id']}/memory?scope=project",
        ["api", "v1", "gm-science", "projects", project["id"], "memory"],
        {"user_id": user_id, "scope": "project"},
    )
    _ClientApiHandler.do_DELETE(handler)
    assert sent[-1][1]["data"]["deleted_count"] == 1

    handler._parse = lambda: (
        f"/api/v1/gm-science/projects/{project['id']}/memory/notes/{note['id']}",
        [
            "api",
            "v1",
            "gm-science",
            "projects",
            project["id"],
            "memory",
            "notes",
            note["id"],
        ],
        {"user_id": user_id},
    )
    _ClientApiHandler.do_DELETE(handler)
    assert sent[-1][1]["data"] == {"deleted": True, "note_id": note["id"]}


def test_session_policy_api_validates_project_specialists_and_persists(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("GM_SCIENCE_MODE", "1")
    monkeypatch.setenv("GM_SCIENCE_DATA_DIR", str(tmp_path / "gm-science"))
    coordinator = ClientApiCoordinator(data_dir=tmp_path)
    project = coordinator.create_gm_science_project(
        {
            "name": "Policy API",
            "enabled_specialists": ["paper_reader", "research_reviewer"],
        }
    )["data"]["project"]
    session = coordinator.create_session(
        GM_SCIENCE_DEFAULT_AGENT_NAME,
        project_id=project["id"],
    )["data"]["session"]

    initial = coordinator.get_gm_science_session_policy(session["id"])
    assert initial["data"]["policy"]["delegation_enabled"] is False
    assert initial["data"]["policy"]["memory_enabled"] is False
    assert initial["data"]["policy"]["reviewer_available"] is True
    assert {item["id"] for item in initial["data"]["policy"]["specialists"]} == {
        "paper_reader"
    }

    updated = coordinator.update_gm_science_session_policy(
        session["id"],
        {
            "delegation_enabled": True,
            "auto_review_enabled": True,
            "memory_enabled": True,
            "specialist_id": "paper_reader",
        },
    )
    policy = updated["data"]["policy"]
    assert policy["delegation_enabled"] is True
    assert policy["auto_review_enabled"] is True
    assert policy["memory_enabled"] is True
    assert policy["specialist_id"] == "paper_reader"
    assert coordinator.get_gm_science_session_policy(session["id"])["data"]["policy"] == policy

    rejected = coordinator.update_gm_science_session_policy(
        session["id"],
        {"specialist_id": "research_reviewer"},
    )
    assert rejected["error"]["code"] == "SESSION_POLICY_UNAVAILABLE"


def test_handler_routes_session_policy_get_and_patch(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("GM_SCIENCE_MODE", "1")
    monkeypatch.setenv("GM_SCIENCE_DATA_DIR", str(tmp_path / "gm-science"))
    coordinator = ClientApiCoordinator(data_dir=tmp_path)
    project = coordinator.create_gm_science_project({"name": "Policy routes"})["data"]["project"]
    session = coordinator.create_session(
        GM_SCIENCE_DEFAULT_AGENT_NAME,
        project_id=project["id"],
    )["data"]["session"]
    handler, sent = _fake_handler(coordinator)
    handler._parse = lambda: (
        f"/api/v1/gm-science/sessions/{session['id']}/policy",
        ["api", "v1", "gm-science", "sessions", session["id"], "policy"],
        {},
    )

    _ClientApiHandler.do_GET(handler)
    assert sent[-1][0] == 200
    assert sent[-1][1]["data"]["policy"]["compute_target"] == "local"

    handler._read_json_body = lambda: {"memory_enabled": True}
    _ClientApiHandler.do_PATCH(handler)
    assert sent[-1][0] == 200
    assert sent[-1][1]["data"]["policy"]["memory_enabled"] is True


def test_handler_routes_expose_path_safe_searchable_project_resources(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("GM_SCIENCE_MODE", "1")
    monkeypatch.setenv("GM_SCIENCE_DATA_DIR", str(tmp_path))
    coordinator = ClientApiCoordinator(data_dir=tmp_path)
    project = coordinator.create_gm_science_project({"name": "Resource API"})["data"]["project"]
    workspace = Path(project["workspace_path"])
    note = workspace / "notes" / "protocol.md"
    note.parent.mkdir(parents=True)
    note.write_text("# Protocol\n", encoding="utf-8")
    coordinator.create_gm_science_artifact(
        project["id"],
        {
            "type": "report",
            "title": "External review",
            "path_or_url": "https://user:secret@example.org/review?token=secret#page",
            "mime_type": "text/html",
        },
    )
    handler, sent = _fake_handler(coordinator)
    handler._parse = lambda: (
        f"/api/v1/gm-science/projects/{project['id']}/resources",
        ["api", "v1", "gm-science", "projects", project["id"], "resources"],
        {"q": "review"},
    )

    _ClientApiHandler.do_GET(handler)

    assert sent[-1][0] == 200
    resources = sent[-1][1]["data"]["items"]
    assert [item["display_name"] for item in resources] == ["External review"]
    assert resources[0]["url"] == "https://example.org/review"
    serialized = json.dumps(sent[-1][1])
    assert str(workspace) not in serialized
    assert "secret" not in serialized

    handler._parse = lambda: (
        f"/api/v1/gm-science/projects/{project['id']}/resources",
        ["api", "v1", "gm-science", "projects", project["id"], "resources"],
        {"q": "x" * 201},
    )
    _ClientApiHandler.do_GET(handler)
    assert sent[-1][0] == 400
    assert sent[-1][1]["error"]["code"] == "INVALID_REQUEST"


def test_handler_routes_expose_bounded_path_safe_resource_detail(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("GM_SCIENCE_MODE", "1")
    monkeypatch.setenv("GM_SCIENCE_DATA_DIR", str(tmp_path))
    coordinator = ClientApiCoordinator(data_dir=tmp_path)
    project = coordinator.create_gm_science_project({"name": "Resource detail API"})["data"]["project"]
    workspace = Path(project["workspace_path"])
    report_path = workspace / "reports" / "summary.md"
    report_path.parent.mkdir(parents=True)
    report_path.write_text("# Summary\n", encoding="utf-8")
    artifact = coordinator.create_gm_science_artifact(
        project["id"],
        {
            "type": "report",
            "title": "Summary report",
            "path_or_url": str(report_path),
            "mime_type": "text/markdown",
            "session_id": "session-1",
            "metadata": {"summary": "One result", "profile_path": str(tmp_path / "private.json")},
            "provenance": {"created_by": "agent", "credential": "secret"},
        },
    )["data"]["artifact"]
    handler, sent = _fake_handler(coordinator)
    handler._parse = lambda: (
        f"/api/v1/gm-science/projects/{project['id']}/resource-detail",
        ["api", "v1", "gm-science", "projects", project["id"], "resource-detail"],
        {"resource_id": f"artifact:{artifact['id']}"},
    )

    _ClientApiHandler.do_GET(handler)

    assert sent[-1][0] == 200
    detail = sent[-1][1]["data"]["detail"]
    assert detail["resource"]["relative_path"] == "reports/summary.md"
    assert detail["preview"]["content"] == "# Summary\n"
    assert detail["artifact"]["session_id"] == "session-1"
    serialized = json.dumps(detail)
    assert str(workspace) not in serialized
    assert "profile_path" not in serialized
    assert "secret" not in serialized

    handler._parse = lambda: (
        f"/api/v1/gm-science/projects/{project['id']}/resource-detail",
        ["api", "v1", "gm-science", "projects", project["id"], "resource-detail"],
        {"resource_id": "artifact:missing"},
    )
    _ClientApiHandler.do_GET(handler)
    assert sent[-1][0] == 404
    assert sent[-1][1]["error"]["code"] == "RESOURCE_NOT_FOUND"

    handler._parse = lambda: (
        f"/api/v1/gm-science/projects/{project['id']}/resource-detail",
        ["api", "v1", "gm-science", "projects", project["id"], "resource-detail"],
        {},
    )
    _ClientApiHandler.do_GET(handler)
    assert sent[-1][0] == 400
    assert sent[-1][1]["error"]["code"] == "INVALID_REQUEST"


def test_handler_forwards_structured_resource_refs_to_project_run() -> None:
    observed: dict[str, object] = {}

    class _Coordinator:
        def create_gm_science_project_run(
            self,
            project_id: str,
            session_id: str,
            text: str,
            **kwargs: object,
        ) -> dict[str, object]:
            observed.update(
                {
                    "project_id": project_id,
                    "session_id": session_id,
                    "text": text,
                    **kwargs,
                }
            )
            return {"ok": True, "data": {"run": {"id": "run-resource"}}}

    handler, sent = _fake_handler(_Coordinator())  # type: ignore[arg-type]
    handler._parse = lambda: (
        "/api/v1/gm-science/projects/proj_1/sessions/session_1/runs",
        ["api", "v1", "gm-science", "projects", "proj_1", "sessions", "session_1", "runs"],
        {},
    )
    handler._read_json_body = lambda: {
        "text": "Compare results.",
        "agent_id": "science-research",
        "resource_refs": [{"id": "project_file:abc", "version_or_hash": "1:20"}],
    }

    _ClientApiHandler.do_POST(handler)

    assert sent[-1][0] == 200
    assert observed == {
        "project_id": "proj_1",
        "session_id": "session_1",
        "text": "Compare results.",
        "user_id": "ppx-client-user",
        "agent_id": "science-research",
        "resource_refs": [{"id": "project_file:abc", "version_or_hash": "1:20"}],
    }


def test_project_run_handler_preserves_http_error_semantics() -> None:
    class _Coordinator:
        error_code = "INVALID_RESOURCE_REFS"

        def create_gm_science_project_run(self, *_args: object, **_kwargs: object) -> dict[str, object]:
            return {
                "ok": False,
                "error": {"code": self.error_code, "message": "Rejected for test."},
            }

    coordinator = _Coordinator()
    handler, sent = _fake_handler(coordinator)  # type: ignore[arg-type]
    handler._parse = lambda: (
        "/api/v1/gm-science/projects/proj_1/sessions/session_1/runs",
        ["api", "v1", "gm-science", "projects", "proj_1", "sessions", "session_1", "runs"],
        {},
    )
    handler._read_json_body = lambda: {"text": "Compare results."}

    expected_statuses = {
        "INVALID_RESOURCE_REFS": 400,
        "SESSION_AGENT_MISMATCH": 400,
        "ACCESS_DENIED": 403,
        "AGENT_NOT_FOUND": 404,
        "PROJECT_NOT_FOUND": 404,
        "SESSION_NOT_FOUND": 404,
        "SESSION_NOT_IN_PROJECT": 404,
    }
    for error_code, expected_status in expected_statuses.items():
        coordinator.error_code = error_code
        _ClientApiHandler.do_POST(handler)
        assert sent[-1][0] == expected_status


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


def test_handler_routes_expose_safe_config_backed_settings(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("GM_SCIENCE_MODE", "1")
    monkeypatch.setenv("GM_SCIENCE_DATA_DIR", str(tmp_path))
    coordinator = ClientApiCoordinator(data_dir=tmp_path)
    project = coordinator.create_gm_science_project({"name": "Settings API"})["data"]["project"]
    handler, sent = _fake_handler(coordinator)

    handler._parse = lambda: (
        "/api/v1/gm-science/settings",
        ["api", "v1", "gm-science", "settings"],
        {},
    )
    _ClientApiHandler.do_GET(handler)
    assert sent[-1][0] == 200
    assert sent[-1][1]["data"]["settings"]["model"]["provider"] == "openai_codex"

    handler._read_json_body = lambda: {
        "project_id": project["id"],
        "model": {"provider": "openai", "model": "openai/gpt-5.5"},
        "provider_api_key": {"operation": "replace", "value": "provider-secret"},
        "pubmed_email": "settings@example.org",
        "openalex_api_key": {"operation": "replace", "value": "openalex-secret"},
    }
    _ClientApiHandler.do_PATCH(handler)
    assert sent[-1][0] == 200
    data = sent[-1][1]["data"]
    assert data["settings"]["model"] == {"provider": "openai", "model": "openai/gpt-5.5"}
    assert data["agent"]["provider"] == "openai"
    assert data["agent"]["model"] == "openai/gpt-5.5"
    assert data["project_id"] == project["id"]
    openalex = next(item for item in data["capabilities"] if item["id"] == "openalex")
    assert openalex["status"] == "ready"
    serialized = json.dumps(sent[-1][1])
    assert "provider-secret" not in serialized
    assert "openalex-secret" not in serialized

    handler._read_json_body = lambda: {
        "model": {"provider": "deepseek", "model": "deepseek-v4"},
    }
    _ClientApiHandler.do_PATCH(handler)
    assert sent[-1][0] == 400
    assert sent[-1][1]["error"]["code"] == "INVALID_REQUEST"

    handler._parse = lambda: (
        "/api/v1/gm-science/settings/compute/check",
        ["api", "v1", "gm-science", "settings", "compute", "check"],
        {},
    )
    handler._read_json_body = lambda: {"target_id": "local"}
    _ClientApiHandler.do_POST(handler)
    assert sent[-1][0] == 200
    assert sent[-1][1]["data"]["health"]["reachable"] is True
    assert sent[-1][1]["data"]["health"]["executable"] is True


def test_client_api_bootstraps_default_science_agent_in_gm_science_mode(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("GM_SCIENCE_MODE", "1")
    monkeypatch.setenv("GM_SCIENCE_DATA_DIR", str(tmp_path))

    coordinator = ClientApiCoordinator(data_dir=tmp_path)

    agents = coordinator.list_agents()
    assert agents["ok"] is True
    profile = agents["data"]["items"][0]
    assert profile["id"] == GM_SCIENCE_DEFAULT_AGENT_NAME
    assert profile["name"] == "gm-science"
    assert profile["provider"] == "openai_codex"
    assert profile["model"] == "openai-codex/gpt-5.5"
    assert profile["tags"] == ["local", "science"]
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
    assert project["enabled_connectors"] == ["pubmed", "arxiv", "openalex"]
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
    assert session["title"] == "New session"
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
    assert "docx" not in ordered_ids
    assert "literature-review" in ordered_ids
    connector_ids = [definition.id for definition in SCIENCE_CONNECTORS]
    connector_start = ordered_ids.index(connector_ids[0])
    assert ordered_ids[connector_start : connector_start + len(connector_ids)] == connector_ids
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
            "catalog_group": "featured",
            "implementation_status": "installed",
            "file_count": 1,
            "files_truncated": False,
        },
    }
    assert items["arxiv"]["source"] == "external"
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
            "enabled_skills": ["local-analysis"],
            "enabled_connectors": [],
            "enabled_specialists": [],
        }
    )

    assert created["ok"] is True
    project = created["data"]["project"]
    assert project["enabled_skills"] == ["local-analysis"]
    payload = coordinator.list_gm_science_capabilities(project["id"])
    skills = {
        item["id"]: item
        for item in payload["data"]["items"]
        if item["kind"] == "skill"
    }
    assert list(skills) == [
        *(definition.id for definition in BUILTIN_SCIENCE_SKILLS),
        "local-analysis",
    ]
    assert "docx" not in skills
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


def test_client_api_enforces_revoked_registry_permissions_on_project_capabilities(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("GM_SCIENCE_MODE", "1")
    monkeypatch.setenv("GM_SCIENCE_DATA_DIR", str(tmp_path))
    coordinator = ClientApiCoordinator(data_dir=tmp_path)
    project = coordinator.create_gm_science_project(
        {
            "name": "Permission boundary",
            "enabled_skills": [],
            "enabled_connectors": [],
            "enabled_specialists": [],
        }
    )["data"]["project"]
    coordinator.update_gm_science_settings(
        {"permission_grants": {"attach_skill": False, "attach_connector": False}}
    )

    skill = coordinator.update_gm_science_project_capabilities(
        project["id"],
        {
            "enabled_skills": ["literature-review"],
            "enabled_connectors": [],
            "enabled_specialists": [],
        },
    )
    connector = coordinator.update_gm_science_project_capabilities(
        project["id"],
        {
            "enabled_skills": [],
            "enabled_connectors": ["arxiv"],
            "enabled_specialists": [],
        },
    )

    assert skill["ok"] is False
    assert skill["error"]["code"] == "PERMISSION_DENIED"
    assert "Attach skill" in skill["error"]["message"]
    assert connector["ok"] is False
    assert connector["error"]["code"] == "PERMISSION_DENIED"


def test_client_api_requires_attach_permissions_for_initial_project_capabilities(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("GM_SCIENCE_MODE", "1")
    monkeypatch.setenv("GM_SCIENCE_DATA_DIR", str(tmp_path))
    coordinator = ClientApiCoordinator(data_dir=tmp_path)
    coordinator.update_gm_science_settings({"permission_grants": {"attach_connector": False}})

    payload = coordinator.create_gm_science_project(
        {
            "name": "Blocked defaults",
            "enabled_skills": [],
            "enabled_connectors": ["arxiv"],
            "enabled_specialists": [],
        }
    )

    assert payload["ok"] is False
    assert payload["error"]["code"] == "PERMISSION_DENIED"


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

    resource_path = Path(project["workspace_path"]) / "papers.md"
    resource_path.write_text("# Saved papers\n", encoding="utf-8")
    resource = coordinator.list_gm_science_resources(project["id"])["data"]["items"][0]

    payload = coordinator.create_gm_science_project_run(
        project["id"],
        "session_1",
        "Summarize the papers.",
        resource_refs=[{"id": resource["id"], "version_or_hash": resource["version_or_hash"]}],
    )

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
    assert "paper_reader:disabled" in message
    assert "research_reviewer:disabled" in message
    assert '"delegation_enabled":false' in message
    assert "Project context:" in message
    assert "Prefer reproducible scripts and cite sources." in message
    assert "User request:" in message
    assert "Summarize the papers." in message
    project_index = observed_cmd.index("--project-id") + 1
    assert observed_cmd[project_index] == project["id"]
    mcp_index = observed_cmd.index("--enabled-mcp-servers-json") + 1
    assert json.loads(observed_cmd[mcp_index]) == []
    skills_index = observed_cmd.index("--enabled-skills-json") + 1
    assert json.loads(observed_cmd[skills_index]) == ["literature-review"]
    resource_index = observed_cmd.index("--resource-refs-json") + 1
    assert json.loads(observed_cmd[resource_index]) == [
        {"id": resource["id"], "version_or_hash": resource["version_or_hash"]}
    ]

    stale = coordinator.create_gm_science_project_run(
        project["id"],
        "session_1",
        "Summarize the papers.",
        resource_refs=[{"id": resource["id"], "version_or_hash": "stale"}],
    )
    assert stale["ok"] is False
    assert stale["error"]["code"] == "INVALID_RESOURCE_REFS"


def test_client_api_project_run_passes_only_selected_available_mcp_servers(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("GM_SCIENCE_DATA_DIR", str(tmp_path / "gm-science"))
    (tmp_path / "global_config.json").write_text(
        json.dumps({"agents": [{"name": "science-research", "enabled": True}]}),
        encoding="utf-8",
    )
    agent_dir = tmp_path / "science-research"
    agent_dir.mkdir()
    (agent_dir / "config.json").write_text(
        json.dumps(
            {
                "agent": {"workspace": "workspace/science-research"},
                "tools": {
                    "mcpServers": {
                        "filesystem": {"command": "mcp-filesystem"},
                        "remote-lab": {"url": "https://mcp.example.test"},
                        "disabled-server": {"enabled": False, "command": "disabled-command"},
                    }
                },
            }
        ),
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
            "name": "MCP project",
            "enabled_connectors": ["arxiv", "mcp:remote-lab"],
        }
    )["data"]["project"]
    coordinator._gm_science_store.link_project_session(
        project_id=project["id"],
        session_id="session_mcp",
        agent_id=GM_SCIENCE_DEFAULT_AGENT_NAME,
    )

    payload = coordinator.create_gm_science_project_run(project["id"], "session_mcp", "Query the lab tools.")

    assert payload["ok"] is True
    mcp_index = observed_cmd.index("--enabled-mcp-servers-json") + 1
    assert json.loads(observed_cmd[mcp_index]) == ["remote-lab"]
    assert "filesystem" not in observed_cmd[mcp_index]
    assert "disabled-server" not in observed_cmd[mcp_index]


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
