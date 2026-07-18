from __future__ import annotations

import json
from pathlib import Path

import pytest

from openppx.gm_science.data.config import DatasetConfig, parse_dataset_config
from openppx.gm_science.data.service import DatasetService
from openppx.gm_science.store import GmScienceStore


def _service(tmp_path: Path, **overrides: int | bool) -> tuple[DatasetService, GmScienceStore, str]:
    store = GmScienceStore(tmp_path / "state")
    project = store.create_project(name="Data", description="", agent_context="")
    values = {
        "enabled": True,
        "max_file_size_bytes": 1_000_000,
        "profile_row_limit": 100,
        "preview_rows": 2,
        "max_columns": 20,
        "top_values_limit": 3,
        **overrides,
    }
    return DatasetService(store=store, config=DatasetConfig(**values)), store, project.id


def test_dataset_config_is_bounded_and_reads_science_data() -> None:
    parsed = parse_dataset_config(
        {
            "science": {
                "data": {
                    "enabled": False,
                    "maxFileSizeBytes": 10,
                    "profileRowLimit": 5,
                    "previewRows": 999,
                    "maxColumns": 0,
                    "topValuesLimit": 0,
                }
            }
        }
    )

    assert parsed.enabled is False
    assert parsed.max_file_size_bytes == 1_024
    assert parsed.profile_row_limit == 100
    assert parsed.preview_rows == 200
    assert parsed.max_columns == 1
    assert parsed.top_values_limit == 1


def test_import_csv_copies_profiles_and_registers_traceable_artifacts(tmp_path: Path) -> None:
    service, store, project_id = _service(tmp_path)
    source = tmp_path / "measurements.csv"
    source.write_text(
        "group,value,measured_at,note\nA,1.5,2026-01-01,ok\nA,,2026-01-02,\nB,3.5,2026-01-03,good\n",
        encoding="utf-8",
    )

    dataset = service.import_dataset(project_id=project_id, source_path=str(source), title="Measurements")

    assert dataset["format"] == "csv"
    assert dataset["row_count"] == 3
    assert dataset["column_count"] == 4
    assert dataset["path"] != str(source)
    assert Path(dataset["path"]).is_file()
    profile = dataset["profile"]
    columns = {column["name"]: column for column in profile["columns"]}
    assert columns["value"]["inferred_type"] == "number"
    assert columns["value"]["missing_count"] == 1
    assert columns["value"]["numeric"]["mean"] == 2.5
    assert columns["measured_at"]["inferred_type"] == "datetime"
    assert len(profile["preview"]) == 2

    artifacts = store.list_artifacts(project_id)
    assert [artifact.type for artifact in artifacts] == ["dataset", "dataset_profile"]
    assert artifacts[0].metadata["profile_artifact_id"] == artifacts[1].id
    assert artifacts[1].provenance["source_artifact_ids"] == [artifacts[0].id]
    assert "measurements.csv" not in artifacts[0].provenance
    assert service.list_datasets(project_id)[0]["artifact_id"] == artifacts[0].id
    assert service.get_dataset(project_id, artifacts[0].id)["profile"] == profile


@pytest.mark.parametrize(
    ("suffix", "content", "expected_rows"),
    [
        (".tsv", "name\tvalue\na\t1\nb\t2\n", 2),
        (".json", json.dumps([{"name": "a", "value": 1}, {"name": "b", "value": 2}]), 2),
        (".jsonl", '{"name":"a","value":1}\n{"name":"b","value":2}\n', 2),
    ],
)
def test_import_supported_table_formats(
    tmp_path: Path,
    suffix: str,
    content: str,
    expected_rows: int,
) -> None:
    service, _store, project_id = _service(tmp_path)
    source = tmp_path / f"table{suffix}"
    source.write_text(content, encoding="utf-8")

    dataset = service.import_dataset(project_id=project_id, source_path=str(source))

    assert dataset["row_count"] == expected_rows
    assert dataset["profile"]["preview"][0]["name"] == "a"


def test_profile_limit_keeps_exact_row_count_and_reports_sampling(tmp_path: Path) -> None:
    service, _store, project_id = _service(tmp_path, profile_row_limit=100)
    source = tmp_path / "large.csv"
    source.write_text("value\n" + "".join(f"{index}\n" for index in range(105)), encoding="utf-8")

    dataset = service.import_dataset(project_id=project_id, source_path=str(source))

    assert dataset["row_count"] == 105
    assert dataset["profiled_row_count"] == 100
    assert "first 100 rows out of 105" in dataset["profile"]["warnings"][0]


def test_import_rejects_unsupported_oversized_and_malformed_files(tmp_path: Path) -> None:
    service, store, project_id = _service(tmp_path, max_file_size_bytes=1_024)
    unsupported = tmp_path / "table.xlsx"
    unsupported.write_bytes(b"not xlsx")
    oversized = tmp_path / "large.csv"
    oversized.write_text("a\n" + "x" * 2_000, encoding="utf-8")
    malformed = tmp_path / "bad.jsonl"
    malformed.write_text('{"a": 1}\nnot-json\n', encoding="utf-8")

    with pytest.raises(ValueError, match="Unsupported dataset format"):
        service.import_dataset(project_id=project_id, source_path=str(unsupported))
    with pytest.raises(ValueError, match="configured limit"):
        service.import_dataset(project_id=project_id, source_path=str(oversized))
    with pytest.raises(ValueError, match="line 2"):
        service.import_dataset(project_id=project_id, source_path=str(malformed))

    assert store.list_artifacts(project_id) == []


def test_import_rejects_cross_project_session(tmp_path: Path) -> None:
    service, store, project_id = _service(tmp_path)
    other = store.create_project(name="Other", description="", agent_context="")
    store.link_project_session(
        project_id=other.id,
        session_id="other-session",
        agent_id="science-research",
    )
    source = tmp_path / "data.csv"
    source.write_text("value\n1\n", encoding="utf-8")

    with pytest.raises(ValueError, match="does not belong"):
        service.import_dataset(
            project_id=project_id,
            source_path=str(source),
            session_id="other-session",
        )


@pytest.mark.parametrize("suffix", [".csv", ".jsonl"])
def test_import_reports_invalid_utf8_as_stable_validation_error(tmp_path: Path, suffix: str) -> None:
    service, store, project_id = _service(tmp_path)
    source = tmp_path / f"invalid{suffix}"
    source.write_bytes(b"name\n\xff\n")

    with pytest.raises(ValueError, match="must be UTF-8 encoded"):
        service.import_dataset(project_id=project_id, source_path=str(source))

    assert store.list_artifacts(project_id) == []
