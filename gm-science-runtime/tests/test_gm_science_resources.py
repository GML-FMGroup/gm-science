from __future__ import annotations

import json
from pathlib import Path

import pytest

from openppx.gm_science.resources.config import ResourceCatalogConfig, parse_resource_catalog_config
from openppx.gm_science.resources.context import ResourceContextService
from openppx.gm_science.resources.detail import ResourceDetailService
from openppx.gm_science.resources.models import ResourceSelection
from openppx.gm_science.resources.service import ResourceCatalogService
from openppx.gm_science.store import GmScienceStore


def _service(
    tmp_path: Path,
    *,
    max_workspace_files: int = 100,
    max_scan_depth: int = 6,
) -> tuple[ResourceCatalogService, GmScienceStore, str, Path]:
    store = GmScienceStore(tmp_path / "state")
    project = store.create_project(name="Resources", description="", agent_context="")
    config = ResourceCatalogConfig(
        enabled=True,
        max_workspace_files=max_workspace_files,
        max_scan_depth=max_scan_depth,
        include_hidden=False,
        excluded_directories=(".git", ".venv", "__pycache__", "node_modules", "datasets", "runs"),
        max_selected_resources=8,
        max_context_chars_per_resource=30_000,
        max_context_chars_total=100_000,
    )
    return ResourceCatalogService(store=store, config=config), store, project.id, Path(project.workspace_path)


def test_resource_config_is_bounded_and_reads_science_resources() -> None:
    parsed = parse_resource_catalog_config(
        {
            "science": {
                "resources": {
                    "enabled": False,
                    "maxWorkspaceFiles": 0,
                    "maxScanDepth": 999,
                    "includeHidden": True,
                    "excludedDirectories": ["runs", "runs", "  custom  ", ""],
                    "maxSelectedResources": 999,
                    "maxContextCharsPerResource": 0,
                    "maxContextCharsTotal": 9_999_999,
                }
            }
        }
    )

    assert parsed.enabled is False
    assert parsed.max_workspace_files == 1
    assert parsed.max_scan_depth == 20
    assert parsed.include_hidden is True
    assert parsed.excluded_directories == ("runs", "custom")
    assert parsed.max_selected_resources == 32
    assert parsed.max_context_chars_per_resource == 256
    assert parsed.max_context_chars_total == 1_000_000


def test_catalog_projects_artifacts_datasets_run_outputs_and_workspace_files(tmp_path: Path) -> None:
    service, store, project_id, workspace = _service(tmp_path)
    report_path = workspace / "reports" / "summary.md"
    report_path.parent.mkdir(parents=True)
    report_path.write_text("# Summary\n", encoding="utf-8")
    dataset_path = workspace / "datasets" / "dataset_one" / "source.csv"
    dataset_path.parent.mkdir(parents=True)
    dataset_path.write_text("x\n1\n", encoding="utf-8")
    output_path = workspace / "runs" / "run_one" / "outputs" / "figure.png"
    output_path.parent.mkdir(parents=True)
    output_path.write_bytes(b"png")
    note_path = workspace / "notes" / "hypothesis.txt"
    note_path.parent.mkdir(parents=True)
    note_path.write_text("testable hypothesis", encoding="utf-8")
    (workspace / ".hidden.txt").write_text("hidden", encoding="utf-8")
    (workspace / "runs" / "run_one" / "manifest.json").write_text("{}", encoding="utf-8")

    report = store.create_artifact(
        project_id=project_id,
        artifact_type="report",
        title="Summary report",
        path_or_url=str(report_path),
        mime_type="text/markdown",
    )
    dataset = store.create_artifact(
        project_id=project_id,
        artifact_type="dataset",
        title="Measurements",
        path_or_url=str(dataset_path),
        mime_type="text/csv",
        metadata={"sha256": "dataset-sha"},
    )
    run_output = store.create_artifact(
        project_id=project_id,
        artifact_type="figure",
        title="Result figure",
        path_or_url=str(output_path),
        mime_type="image/png",
        metadata={"science_run_role": "output", "task_id": "task-1"},
        provenance={"task_id": "task-1"},
    )

    resources = service.list_resources(project_id)
    by_id = {resource.id: resource for resource in resources}

    assert {resource.kind for resource in resources} == {"artifact", "dataset", "run_output", "project_file"}
    assert by_id[f"artifact:{report.id}"].relative_path == "reports/summary.md"
    assert by_id[f"artifact:{dataset.id}"].version_or_hash == "dataset-sha"
    assert by_id[f"artifact:{run_output.id}"].metadata == {
        "science_run_role": "output",
        "task_id": "task-1",
    }
    project_files = [resource for resource in resources if resource.kind == "project_file"]
    assert [resource.relative_path for resource in project_files] == ["notes/hypothesis.txt"]
    assert all(resource.access_mode == "read" for resource in resources)

    public_json = json.dumps([resource.to_dict() for resource in resources], ensure_ascii=False)
    assert str(workspace) not in public_json
    assert "path_or_url" not in public_json
    assert "manifest.json" not in public_json
    assert ".hidden.txt" not in public_json


def test_catalog_search_is_case_insensitive_and_deterministic(tmp_path: Path) -> None:
    service, store, project_id, workspace = _service(tmp_path)
    notes = workspace / "notes"
    notes.mkdir()
    (notes / "Alpha Protocol.md").write_text("alpha", encoding="utf-8")
    (notes / "beta.txt").write_text("beta", encoding="utf-8")
    store.create_artifact(
        project_id=project_id,
        artifact_type="report",
        title="Gamma Review",
        path_or_url="https://example.org/gamma",
        mime_type="text/html",
    )

    first = service.list_resources(project_id)
    second = service.list_resources(project_id)

    assert [item.id for item in first] == [item.id for item in second]
    assert [item.display_name for item in service.list_resources(project_id, query="ALPHA")] == [
        "Alpha Protocol.md"
    ]
    assert [item.display_name for item in service.list_resources(project_id, query="report")] == [
        "Gamma Review"
    ]
    with pytest.raises(ValueError, match="Search query"):
        service.list_resources(project_id, query="x" * 201)


def test_workspace_scan_is_bounded_and_does_not_follow_symlinks(tmp_path: Path) -> None:
    service, _store, project_id, workspace = _service(
        tmp_path,
        max_workspace_files=1,
        max_scan_depth=1,
    )
    (workspace / "a.txt").write_text("a", encoding="utf-8")
    (workspace / "b.txt").write_text("b", encoding="utf-8")
    deep = workspace / "level-one" / "level-two"
    deep.mkdir(parents=True)
    (deep / "deep.txt").write_text("deep", encoding="utf-8")
    outside = tmp_path / "outside.txt"
    outside.write_text("outside", encoding="utf-8")
    (workspace / "outside-link.txt").symlink_to(outside)

    resources = service.list_resources(project_id)

    assert [(item.kind, item.relative_path) for item in resources] == [("project_file", "a.txt")]


def test_catalog_redacts_outside_paths_and_tolerates_malformed_urls(tmp_path: Path) -> None:
    service, store, project_id, workspace = _service(tmp_path)
    outside = tmp_path / "private" / "credentials.txt"
    outside.parent.mkdir()
    outside.write_text("secret", encoding="utf-8")
    local = store.create_artifact(
        project_id=project_id,
        artifact_type="note",
        title="Outside note",
        path_or_url=str(outside),
    )
    malformed = store.create_artifact(
        project_id=project_id,
        artifact_type="link",
        title="Malformed link",
        path_or_url="https://example.org:invalid/review?token=secret",
    )

    resources = {item.id: item for item in service.list_resources(project_id)}

    assert resources[f"artifact:{local.id}"].access_mode == "metadata_only"
    assert resources[f"artifact:{local.id}"].relative_path == ""
    assert resources[f"artifact:{malformed.id}"].access_mode == "metadata_only"
    assert resources[f"artifact:{malformed.id}"].url == ""
    serialized = json.dumps([item.to_dict() for item in resources.values()])
    assert str(workspace) not in serialized
    assert str(outside) not in serialized
    assert "secret" not in serialized


def test_catalog_rejects_unknown_or_disabled_projects(tmp_path: Path) -> None:
    service, store, project_id, _workspace = _service(tmp_path)

    with pytest.raises(ValueError, match="was not found"):
        service.list_resources("missing")

    disabled = ResourceCatalogService(
        store=store,
        config=ResourceCatalogConfig(
            enabled=False,
            max_workspace_files=10,
            max_scan_depth=2,
            include_hidden=False,
            excluded_directories=(),
            max_selected_resources=8,
            max_context_chars_per_resource=30_000,
            max_context_chars_total=100_000,
        ),
    )
    with pytest.raises(ValueError, match="disabled"):
        disabled.list_resources(project_id)


def test_context_resolves_bounded_text_and_descriptor_only_resources(tmp_path: Path) -> None:
    catalog, store, project_id, workspace = _service(tmp_path)
    protocol_path = workspace / "protocol.md"
    protocol_path.write_text("0123456789abcdefghij", encoding="utf-8")
    image_path = workspace / "figure.png"
    image_path.write_bytes(b"not-text")
    external = store.create_artifact(
        project_id=project_id,
        artifact_type="paper",
        title="External paper",
        path_or_url="https://example.org/paper",
        mime_type="text/html",
    )
    config = ResourceCatalogConfig(
        enabled=True,
        max_workspace_files=100,
        max_scan_depth=6,
        include_hidden=False,
        excluded_directories=(),
        max_selected_resources=4,
        max_context_chars_per_resource=10,
        max_context_chars_total=10,
    )
    service = ResourceContextService(
        catalog=ResourceCatalogService(store=store, config=config),
        config=config,
    )
    resources = {item.display_name: item for item in service.catalog.list_resources(project_id)}

    contexts = service.resolve_contexts(
        project_id,
        [
            ResourceSelection(
                id=resources["protocol.md"].id,
                version_or_hash=resources["protocol.md"].version_or_hash,
            ),
            ResourceSelection(
                id=resources["figure.png"].id,
                version_or_hash=resources["figure.png"].version_or_hash,
            ),
            ResourceSelection(
                id=f"artifact:{external.id}",
                version_or_hash=resources["External paper"].version_or_hash,
            ),
        ],
    )

    assert contexts[0].content == "0123456789"
    assert contexts[0].content_included is True
    assert contexts[0].truncated is True
    assert contexts[0].metadata()["gm_science_resource"]["id"] == resources["protocol.md"].id
    assert "untrusted research data" in contexts[0].render_text()
    assert contexts[1].content == ""
    assert contexts[1].content_included is False
    assert contexts[1].content_status == "binary_descriptor_only"
    assert contexts[2].content_status == "external_descriptor_only"
    assert "https://example.org/paper" in contexts[2].render_text()


def test_context_rejects_stale_duplicate_unknown_and_excess_selections(tmp_path: Path) -> None:
    catalog, store, project_id, workspace = _service(tmp_path)
    (workspace / "note.txt").write_text("note", encoding="utf-8")
    resource = catalog.list_resources(project_id)[0]
    service = ResourceContextService(catalog=catalog, config=catalog.config)
    selection = ResourceSelection(id=resource.id, version_or_hash=resource.version_or_hash)

    assert service.validate_selections(project_id, [selection]) == [selection]
    with pytest.raises(ValueError, match="selected more than once"):
        service.validate_selections(project_id, [selection, selection])
    with pytest.raises(ValueError, match="has changed"):
        service.validate_selections(
            project_id,
            [ResourceSelection(id=resource.id, version_or_hash="stale-version")],
        )
    with pytest.raises(ValueError, match="was not found"):
        service.validate_selections(
            project_id,
            [ResourceSelection(id="project_file:missing", version_or_hash="1")],
        )

    limited_config = ResourceCatalogConfig(
        enabled=True,
        max_workspace_files=100,
        max_scan_depth=6,
        include_hidden=False,
        excluded_directories=(),
        max_selected_resources=1,
        max_context_chars_per_resource=30_000,
        max_context_chars_total=100_000,
    )
    limited = ResourceContextService(
        catalog=ResourceCatalogService(store=store, config=limited_config),
        config=limited_config,
    )
    with pytest.raises(ValueError, match="At most 1"):
        limited.validate_selections(project_id, [selection, selection])


def test_context_selection_payload_requires_stable_id_and_version(tmp_path: Path) -> None:
    catalog, _store, project_id, workspace = _service(tmp_path)
    (workspace / "note.txt").write_text("note", encoding="utf-8")
    resource = catalog.list_resources(project_id)[0]
    service = ResourceContextService(catalog=catalog, config=catalog.config)

    assert service.validate_selections(
        project_id,
        [{"id": resource.id, "version_or_hash": resource.version_or_hash}],
    ) == [ResourceSelection(id=resource.id, version_or_hash=resource.version_or_hash)]
    with pytest.raises(ValueError, match="must be a list"):
        service.validate_selections(project_id, {"id": resource.id})
    with pytest.raises(ValueError, match="non-empty 'version_or_hash'"):
        service.validate_selections(project_id, [{"id": resource.id}])


def test_empty_context_selection_does_not_scan_the_resource_catalog(tmp_path: Path, monkeypatch) -> None:
    catalog, _store, project_id, _workspace = _service(tmp_path)
    service = ResourceContextService(catalog=catalog, config=catalog.config)
    monkeypatch.setattr(catalog, "list_resources", lambda *_args, **_kwargs: pytest.fail("unexpected scan"))

    assert service.validate_selections(project_id, []) == []


def test_detail_returns_bounded_preview_safe_provenance_and_relations(tmp_path: Path) -> None:
    catalog, store, project_id, workspace = _service(tmp_path)
    paper = store.create_artifact(
        project_id=project_id,
        artifact_type="paper",
        title="Evidence paper",
        path_or_url="https://example.org/paper?token=secret",
        mime_type="text/html",
        metadata={"doi": "10.1000/example", "abstract": "Evidence summary."},
    )
    report_path = workspace / "reports" / "summary.md"
    report_path.parent.mkdir(parents=True)
    report_path.write_text("# Summary\nSupported claim.\n", encoding="utf-8")
    report = store.create_artifact(
        project_id=project_id,
        artifact_type="report",
        title="Summary report",
        path_or_url=str(report_path),
        mime_type="text/markdown",
        session_id="session-report",
        metadata={
            "paper_artifact_ids": [paper.id],
            "summary": "Supported claim.",
            "profile_path": str(tmp_path / "private" / "profile.json"),
        },
        provenance={
            "created_by": "literature_review",
            "model": "openai-codex/gpt-5.5",
            "session_id": "session-report",
            "source_artifact_ids": [paper.id],
            "credential": "must-not-leak",
            "stdout_path": str(tmp_path / "private" / "stdout.log"),
        },
    )
    detail_service = ResourceDetailService(catalog=catalog)

    detail = detail_service.get_detail(project_id, f"artifact:{report.id}").to_dict()

    assert detail["resource"]["relative_path"] == "reports/summary.md"
    assert detail["preview"] == {
        "content": "# Summary\nSupported claim.\n",
        "content_status": "included",
        "content_included": True,
        "content_chars": 27,
        "truncated": False,
    }
    assert detail["artifact"] == {
        "id": report.id,
        "session_id": "session-report",
        "type": "report",
        "title": "Summary report",
        "mime_type": "text/markdown",
        "metadata": {
            "paper_artifact_ids": [paper.id],
            "summary": "Supported claim.",
        },
        "provenance": {
            "created_by": "literature_review",
            "model": "openai-codex/gpt-5.5",
            "session_id": "session-report",
            "source_artifact_ids": [paper.id],
        },
        "created_at": report.created_at,
        "updated_at": report.updated_at,
    }
    assert detail["relations"] == [
        {
            "artifact_id": paper.id,
            "resource_id": f"artifact:{paper.id}",
            "session_id": None,
            "title": "Evidence paper",
            "artifact_type": "paper",
            "relation": "paper",
            "direction": "outgoing",
        },
    ]
    serialized = json.dumps(detail)
    assert str(workspace) not in serialized
    assert str(tmp_path / "private") not in serialized
    assert "must-not-leak" not in serialized


def test_detail_uses_descriptor_status_for_external_and_binary_resources(tmp_path: Path) -> None:
    catalog, store, project_id, workspace = _service(tmp_path)
    external = store.create_artifact(
        project_id=project_id,
        artifact_type="paper",
        title="External paper",
        path_or_url="https://user:secret@example.org/paper?token=secret#page",
        mime_type="text/html",
    )
    image_path = workspace / "figure.png"
    image_path.write_bytes(b"png")
    image = store.create_artifact(
        project_id=project_id,
        artifact_type="figure",
        title="Result figure",
        path_or_url=str(image_path),
        mime_type="image/png",
    )
    service = ResourceDetailService(catalog=catalog)

    external_detail = service.get_detail(project_id, f"artifact:{external.id}").to_dict()
    image_detail = service.get_detail(project_id, f"artifact:{image.id}").to_dict()

    assert external_detail["resource"]["url"] == "https://example.org/paper"
    assert external_detail["preview"]["content_status"] == "external_descriptor_only"
    assert external_detail["preview"]["content"] == ""
    assert image_detail["preview"]["content_status"] == "binary_descriptor_only"
    assert image_detail["preview"]["content"] == ""


def test_detail_rejects_unknown_cross_project_and_invalid_resource_ids(tmp_path: Path) -> None:
    catalog, store, project_id, workspace = _service(tmp_path)
    (workspace / "note.txt").write_text("note", encoding="utf-8")
    resource = catalog.list_resources(project_id)[0]
    other_project = store.create_project(name="Other", description="", agent_context="")
    service = ResourceDetailService(catalog=catalog)

    with pytest.raises(LookupError, match="was not found"):
        service.get_detail(other_project.id, resource.id)
    with pytest.raises(LookupError, match="was not found"):
        service.get_detail(project_id, "project_file:missing")
    with pytest.raises(ValueError, match="required"):
        service.get_detail(project_id, "")
    with pytest.raises(ValueError, match="exceeds"):
        service.get_detail(project_id, "x" * 513)
