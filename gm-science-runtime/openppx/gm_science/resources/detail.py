"""Path-safe Artifact and Project-file inspection for the desktop workspace."""

from __future__ import annotations

import csv
import io
import json
from collections.abc import Iterable, Mapping
from pathlib import PurePosixPath
from typing import Any

from ..models import ArtifactRecord
from .context import ResourceContextService
from .models import (
    ArtifactDetail,
    ArtifactRelation,
    ArtifactRelationDirection,
    ResourceDetail,
    ResourcePreview,
    ResourcePreviewMode,
    ResourceSelection,
    ResourceTablePreview,
)
from .service import ResourceCatalogService

_MAX_RESOURCE_ID_CHARS = 512
_MAX_SAFE_STRING_CHARS = 8_000
_MAX_SAFE_LIST_ITEMS = 100
_MAX_SAFE_MAPPING_ITEMS = 50
_MAX_SAFE_DEPTH = 4
_MAX_TABLE_COLUMNS = 50
_MAX_TABLE_ROWS = 100
_MAX_RENDERED_JSON_CHARS = 100_000

_SAFE_METADATA_KEYS = frozenset(
    {
        "abstract",
        "analysis_id",
        "authors",
        "canonical_id",
        "citation_artifact_ids",
        "column_count",
        "column_names",
        "confidence",
        "dataset_artifact_id",
        "dataset_artifact_ids",
        "dataset_format",
        "doi",
        "evidence_scope",
        "evidence_scopes",
        "findings",
        "fusion_score",
        "limitations",
        "missing_evidence",
        "objective",
        "paper_artifact_id",
        "paper_artifact_ids",
        "pmid",
        "profile_artifact_id",
        "profiled_row_count",
        "published_date",
        "report_artifact_id",
        "review_focus",
        "review_limitations",
        "row_count",
        "science_run_role",
        "sha256",
        "size_bytes",
        "source_artifact_id",
        "source_artifact_ids",
        "source_name",
        "source_sha256",
        "specialist_id",
        "status",
        "summary",
        "target_artifact_id",
        "task_id",
        "title",
        "unsupported_claims",
        "venue",
        "verdict",
        "year",
    }
)
_SAFE_PROVENANCE_KEYS = frozenset(
    {
        "analysis_id",
        "citation_artifact_ids",
        "connectors",
        "created_by",
        "dataset_artifact_id",
        "dataset_artifact_ids",
        "model",
        "paper_artifact_id",
        "paper_artifact_ids",
        "parent_task_id",
        "query",
        "report_artifact_id",
        "session_id",
        "skills",
        "source_artifact_id",
        "source_artifact_ids",
        "source_sha256",
        "sources",
        "specialist_id",
        "target_artifact_id",
        "task_id",
        "trigger",
    }
)
_RELATION_FIELDS = {
    "citation_artifact_ids": "citation",
    "dataset_artifact_id": "dataset",
    "dataset_artifact_ids": "dataset",
    "paper_artifact_id": "paper",
    "paper_artifact_ids": "paper",
    "profile_artifact_id": "profile",
    "report_artifact_id": "report",
    "source_artifact_id": "source",
    "source_artifact_ids": "source",
    "target_artifact_id": "target",
}


class ResourceDetailService:
    """Build bounded, path-safe inspection payloads from the resource catalog."""

    def __init__(
        self,
        *,
        catalog: ResourceCatalogService,
        context: ResourceContextService | None = None,
    ) -> None:
        self.catalog = catalog
        self.context = context or ResourceContextService(catalog=catalog)

    def get_detail(self, project_id: str, resource_id: str) -> ResourceDetail:
        """Return one current Project resource with preview and safe provenance."""

        normalized_id = str(resource_id or "").strip()
        if not normalized_id:
            raise ValueError("Field 'resource_id' is required.")
        if len(normalized_id) > _MAX_RESOURCE_ID_CHARS:
            raise ValueError(f"Field 'resource_id' exceeds {_MAX_RESOURCE_ID_CHARS} characters.")

        resource = next(
            (item for item in self.catalog.list_resources(project_id) if item.id == normalized_id),
            None,
        )
        if resource is None:
            raise LookupError(f"Resource '{normalized_id}' was not found in Project '{project_id}'.")

        resolved = self.context.resolve_contexts(
            project_id,
            [ResourceSelection(id=resource.id, version_or_hash=resource.version_or_hash)],
        )[0]
        content, display_mode, table, structure_truncated = _structured_preview(
            resource.mime_type,
            resource.relative_path or resource.display_name,
            resolved.content,
            content_included=resolved.content_included,
        )
        preview = ResourcePreview(
            content=content,
            content_status=resolved.content_status,
            content_included=resolved.content_included,
            truncated=resolved.truncated or structure_truncated,
            display_mode=display_mode,
            table=table,
        )
        artifact = None
        relations: tuple[ArtifactRelation, ...] = ()
        if resource.artifact_id:
            record = self.catalog.store.get_artifact(resource.artifact_id)
            if record is None or record.project_id != project_id:
                raise LookupError(f"Artifact '{resource.artifact_id}' is unavailable in Project '{project_id}'.")
            artifact = _artifact_detail(record)
            relations = _artifact_relations(record, self.catalog.store.list_artifacts(project_id))
        return ResourceDetail(
            resource=resource,
            preview=preview,
            artifact=artifact,
            relations=relations,
        )


def _structured_preview(
    mime_type: str,
    path_or_name: str,
    content: str,
    *,
    content_included: bool,
) -> tuple[str, ResourcePreviewMode, ResourceTablePreview | None, bool]:
    """Parse bounded JSON and delimited-text previews without reading beyond context limits."""

    if not content_included:
        return content, "text", None, False
    normalized_mime = str(mime_type or "").split(";", 1)[0].strip().lower()
    suffix = PurePosixPath(path_or_name).suffix.lower()
    if normalized_mime == "text/markdown" or suffix in {".md", ".markdown"}:
        return content, "markdown", None, False
    if normalized_mime in {"application/json", "application/ld+json"} or suffix == ".json":
        try:
            rendered = json.dumps(json.loads(content), ensure_ascii=False, indent=2)
        except (json.JSONDecodeError, TypeError, ValueError):
            return content, "text", None, False
        truncated = len(rendered) > _MAX_RENDERED_JSON_CHARS
        return rendered[:_MAX_RENDERED_JSON_CHARS], "json", None, truncated
    delimiter = None
    if normalized_mime in {"text/csv", "application/csv"} or suffix == ".csv":
        delimiter = ","
    elif normalized_mime in {"text/tab-separated-values", "text/tsv"} or suffix in {".tsv", ".tab"}:
        delimiter = "\t"
    if delimiter is None:
        return content, "text", None, False
    try:
        reader = csv.reader(io.StringIO(content), delimiter=delimiter)
        parsed: list[tuple[str, ...]] = []
        truncated = False
        for index, raw_row in enumerate(reader):
            if index > _MAX_TABLE_ROWS:
                truncated = True
                break
            if len(raw_row) > _MAX_TABLE_COLUMNS:
                truncated = True
            parsed.append(tuple(str(value) for value in raw_row[:_MAX_TABLE_COLUMNS]))
    except csv.Error:
        return content, "text", None, False
    if not parsed:
        return content, "table", ResourceTablePreview(columns=(), rows=(), truncated=False), False
    columns = tuple(value or f"Column {index + 1}" for index, value in enumerate(parsed[0]))
    width = len(columns)
    rows = tuple((row + ("",) * max(0, width - len(row)))[:width] for row in parsed[1:])
    table = ResourceTablePreview(columns=columns, rows=rows, truncated=truncated)
    return content, "table", table, truncated


def _artifact_detail(artifact: ArtifactRecord) -> ArtifactDetail:
    return ArtifactDetail(
        id=artifact.id,
        session_id=artifact.session_id,
        type=artifact.type,
        title=artifact.title,
        mime_type=artifact.mime_type,
        metadata=_safe_projection(artifact.metadata, _SAFE_METADATA_KEYS),
        provenance=_safe_projection(artifact.provenance, _SAFE_PROVENANCE_KEYS),
        created_at=artifact.created_at,
        updated_at=artifact.updated_at,
    )


def _safe_projection(raw: Mapping[str, Any], allowed_keys: frozenset[str]) -> dict[str, Any]:
    projected: dict[str, Any] = {}
    for key in sorted(allowed_keys):
        if key not in raw:
            continue
        safe_value = _bounded_value(raw[key], depth=0)
        if safe_value is not None:
            projected[key] = safe_value
    return projected


def _bounded_value(value: Any, *, depth: int) -> Any:
    if depth >= _MAX_SAFE_DEPTH:
        return None
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        return value[:_MAX_SAFE_STRING_CHARS]
    if isinstance(value, Mapping):
        result: dict[str, Any] = {}
        for raw_key, raw_value in list(value.items())[:_MAX_SAFE_MAPPING_ITEMS]:
            key = str(raw_key)[:200]
            bounded = _bounded_value(raw_value, depth=depth + 1)
            if bounded is not None:
                result[key] = bounded
        return result
    if isinstance(value, Iterable) and not isinstance(value, (bytes, bytearray)):
        result = []
        for raw_value in list(value)[:_MAX_SAFE_LIST_ITEMS]:
            bounded = _bounded_value(raw_value, depth=depth + 1)
            if bounded is not None:
                result.append(bounded)
        return result
    return str(value)[:_MAX_SAFE_STRING_CHARS]


def _artifact_relations(
    selected: ArtifactRecord,
    project_artifacts: list[ArtifactRecord],
) -> tuple[ArtifactRelation, ...]:
    by_id = {artifact.id: artifact for artifact in project_artifacts}
    relations: list[ArtifactRelation] = []
    seen: set[tuple[str, str]] = set()

    for relation, artifact_id in _relation_targets(selected):
        target = by_id.get(artifact_id)
        if target is not None and target.id != selected.id:
            _append_relation(relations, seen, target, relation, "outgoing")

    for candidate in project_artifacts:
        if candidate.id == selected.id:
            continue
        for relation, artifact_id in _relation_targets(candidate):
            if artifact_id == selected.id:
                _append_relation(relations, seen, candidate, relation, "incoming")

    return tuple(
        sorted(
            relations,
            key=lambda item: (item.direction, item.relation, item.title.casefold(), item.artifact_id),
        )
    )


def _relation_targets(artifact: ArtifactRecord) -> Iterable[tuple[str, str]]:
    for source in (artifact.metadata, artifact.provenance):
        for field, relation in _RELATION_FIELDS.items():
            raw = source.get(field)
            values = raw if isinstance(raw, list) else [raw]
            for value in values:
                artifact_id = str(value or "").strip()
                if artifact_id:
                    yield relation, artifact_id


def _append_relation(
    relations: list[ArtifactRelation],
    seen: set[tuple[str, str]],
    artifact: ArtifactRecord,
    relation: str,
    direction: ArtifactRelationDirection,
) -> None:
    key = (artifact.id, direction)
    if key in seen:
        return
    seen.add(key)
    relations.append(
        ArtifactRelation(
            artifact_id=artifact.id,
            resource_id=f"artifact:{artifact.id}",
            session_id=artifact.session_id,
            title=artifact.title,
            artifact_type=artifact.type,
            relation=relation,
            direction=direction,
        )
    )
