"""Public resource reference models for Project files and outputs."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

ResourceKind = Literal["artifact", "dataset", "run_output", "project_file"]
ResourceAccessMode = Literal["read", "external", "metadata_only"]
ResourceSource = Literal["artifact", "workspace"]


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
