"""Public resource reference models for Project files and outputs."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

ResourceKind = Literal["artifact", "dataset", "run_output", "project_file"]
ResourceAccessMode = Literal["read", "external", "metadata_only"]
ResourceSource = Literal["artifact", "workspace"]
ResourceContentStatus = Literal[
    "included",
    "binary_descriptor_only",
    "external_descriptor_only",
    "metadata_descriptor_only",
    "budget_exhausted_descriptor_only",
    "unavailable_descriptor_only",
]
ArtifactRelationDirection = Literal["outgoing", "incoming"]


@dataclass(frozen=True, slots=True)
class ResourceSelection:
    """Optimistic reference to one exact version of a Project resource."""

    id: str
    version_or_hash: str

    def to_dict(self) -> dict[str, str]:
        """Return the compact worker/client-api representation."""

        return {"id": self.id, "version_or_hash": self.version_or_hash}


@dataclass(frozen=True, slots=True)
class ResourceRef:
    """A stable, path-safe reference to one Project-owned research resource."""

    id: str
    kind: ResourceKind
    project_id: str
    session_id: str | None
    display_name: str
    artifact_type: str
    mime_type: str
    version_or_hash: str
    access_mode: ResourceAccessMode
    source: ResourceSource
    artifact_id: str
    relative_path: str
    url: str
    size_bytes: int | None
    created_at: str
    updated_at: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Return the stable public snake_case representation used by client-api."""

        return asdict(self)


@dataclass(frozen=True, slots=True)
class ResourcePreview:
    """A bounded text preview or an explicit descriptor-only status."""

    content: str
    content_status: ResourceContentStatus
    content_included: bool
    truncated: bool

    def to_dict(self) -> dict[str, Any]:
        """Return the public preview representation used by client-api."""

        return {
            "content": self.content,
            "content_status": self.content_status,
            "content_included": self.content_included,
            "content_chars": len(self.content),
            "truncated": self.truncated,
        }


@dataclass(frozen=True, slots=True)
class ArtifactDetail:
    """A path-safe public view of one durable Artifact."""

    id: str
    session_id: str | None
    type: str
    title: str
    mime_type: str
    metadata: dict[str, Any]
    provenance: dict[str, Any]
    created_at: str
    updated_at: str

    def to_dict(self) -> dict[str, Any]:
        """Return the public Artifact detail representation."""

        return asdict(self)


@dataclass(frozen=True, slots=True)
class ArtifactRelation:
    """A resolved, Project-local relationship between two Artifacts."""

    artifact_id: str
    resource_id: str
    session_id: str | None
    title: str
    artifact_type: str
    relation: str
    direction: ArtifactRelationDirection

    def to_dict(self) -> dict[str, Any]:
        """Return the public relation representation."""

        return asdict(self)


@dataclass(frozen=True, slots=True)
class ResourceDetail:
    """The complete read-only inspection payload for one Project resource."""

    resource: ResourceRef
    preview: ResourcePreview
    artifact: ArtifactDetail | None
    relations: tuple[ArtifactRelation, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        """Return the public resource detail representation used by client-api."""

        return {
            "resource": self.resource.to_dict(),
            "preview": self.preview.to_dict(),
            "artifact": self.artifact.to_dict() if self.artifact is not None else None,
            "relations": [relation.to_dict() for relation in self.relations],
        }
