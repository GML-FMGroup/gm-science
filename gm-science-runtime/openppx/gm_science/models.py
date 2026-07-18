"""Data models for gm-science projects, sessions, runs, and artifacts."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class ProjectRecord:
    """A local gm-science research project."""

    id: str
    name: str
    description: str
    agent_context: str
    workspace_path: str
    created_at: str
    updated_at: str
    enabled_skills: list[str] = field(default_factory=list)
    enabled_connectors: list[str] = field(default_factory=list)
    enabled_specialists: list[str] = field(default_factory=list)
    session_policy_defaults: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ProjectSessionRecord:
    """A durable association between one Project and one ADK Session."""

    project_id: str
    session_id: str
    agent_id: str
    policy: dict[str, Any]
    created_at: str
    updated_at: str


@dataclass(frozen=True, slots=True)
class ScienceRunRecord:
    """A Project-facing association for one openppx TaskRun."""

    task_id: str
    project_id: str
    session_id: str | None
    parent_task_id: str | None
    kind: str
    title: str
    source_path: str
    working_directory: str
    input_payload: dict[str, Any]
    created_at: str
    updated_at: str


@dataclass(frozen=True, slots=True)
class AnalysisDraftRecord:
    """A reviewable data-analysis intent with optional TaskRun linkage."""

    id: str
    project_id: str
    session_id: str | None
    title: str
    objective: str
    dataset_artifact_ids: list[str]
    plan: dict[str, Any]
    source: str
    task_id: str | None
    created_at: str
    updated_at: str


@dataclass(frozen=True, slots=True)
class ArtifactRecord:
    """A durable research artifact attached to a gm-science project."""

    id: str
    project_id: str
    session_id: str | None
    type: str
    title: str
    path_or_url: str
    mime_type: str
    metadata: dict[str, Any]
    provenance: dict[str, Any]
    created_at: str
    updated_at: str
