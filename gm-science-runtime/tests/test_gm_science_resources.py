from __future__ import annotations

import json
from pathlib import Path

import pytest

from openppx.gm_science.resources.config import ResourceCatalogConfig, parse_resource_catalog_config
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
                }
            }
        }
    )

    assert parsed.enabled is False
    assert parsed.max_workspace_files == 1
    assert parsed.max_scan_depth == 20
    assert parsed.include_hidden is True
    assert parsed.excluded_directories == ("runs", "custom")


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
        ),
    )
    with pytest.raises(ValueError, match="disabled"):
        disabled.list_resources(project_id)
