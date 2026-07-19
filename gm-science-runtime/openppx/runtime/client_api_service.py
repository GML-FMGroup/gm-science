"""Local HTTP + SSE client API service for openppx."""

from __future__ import annotations

import datetime as dt
import asyncio
import json
import os
import queue
import subprocess
import sys
import threading
import time
import urllib.parse
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from ..core.config import config_to_env, get_data_dir, load_config
from ..core.logging_utils import debug_logging_enabled, emit_debug
from ..gm_science.bootstrap import GM_SCIENCE_DEFAULT_AGENT_NAME, ensure_gm_science_initialized
from ..gm_science.authoring import (
    CapabilityConflictError,
    GmScienceCapabilityAuthoringService,
)
from ..gm_science.capabilities import (
    build_capability_catalog,
    normalize_capability_selection,
    selected_mcp_server_names,
)
from ..gm_science.analysis import AnalysisService
from ..gm_science.data import DatasetService
from ..gm_science.execution import ScienceExecutionService
from ..gm_science.infrastructure import RegistryPermissionError
from ..gm_science.literature.config import load_literature_config, select_literature_sources
from ..gm_science.memory import GmScienceMemoryService
from ..gm_science.models import ArtifactRecord, ProjectRecord, ProjectSessionRecord
from ..gm_science.observability import GmScienceObservabilityService
from ..gm_science.resources import (
    ResourceCatalogService,
    ResourceContextService,
    ResourceDetailService,
    ResourceSelection,
)
from ..gm_science.session_policy import normalize_session_policy, update_session_policy
from ..gm_science.settings import GmScienceSettingsService
from ..gm_science.specialists.config import load_specialist_config
from ..gm_science.store import GmScienceStore
from .access_policy import AccessPolicy
from .agent_access_runtime import ensure_access_principal
from .agent_access_runtime import ensure_agent_access_record
from .agent_access_store import AgentAccessStore, AgentMembership, AgentRecord
from .identity_models import ResolvedPrincipal
from .identity_store import IdentityStore
from .memory_query_service import MemoryQueryService
from .memory_shared import memory_entry_text
from .session_service import SessionConfig, create_session_service
from .sqlite_memory_service import SQLiteMemoryService


def _iso_now() -> str:
    """Return the current timestamp as an ISO 8601 string."""

    return dt.datetime.now().astimezone().isoformat()


def _worker_process_env(
    base_env: dict[str, str] | None = None,
    *,
    startup_cwd: Path | None = None,
) -> dict[str, str]:
    """Build a worker environment with cwd-independent runtime imports."""

    env = dict(os.environ if base_env is None else base_env)
    origin = (startup_cwd or Path.cwd()).resolve(strict=False)
    package_root = Path(__file__).resolve().parents[2]
    python_paths = [package_root]
    for raw in str(env.get("PYTHONPATH") or "").split(os.pathsep):
        if not raw.strip():
            continue
        candidate = Path(raw).expanduser()
        if not candidate.is_absolute():
            candidate = origin / candidate
        candidate = candidate.resolve(strict=False)
        if candidate not in python_paths:
            python_paths.append(candidate)
    env["PYTHONPATH"] = os.pathsep.join(str(path) for path in python_paths)
    return env


def _json_bytes(payload: dict[str, Any]) -> bytes:
    """Encode one JSON payload using UTF-8."""

    return json.dumps(payload, ensure_ascii=False).encode("utf-8")


def _ok(data: dict[str, Any]) -> dict[str, Any]:
    """Build a success envelope."""

    return {"ok": True, "data": data}


def _error(code: str, message: str, details: dict[str, Any] | None = None) -> dict[str, Any]:
    """Build an error envelope."""

    return {
        "ok": False,
        "error": {
            "code": code,
            "message": message,
            "details": details or {},
        },
    }


def _project_run_http_status(payload: dict[str, Any]) -> int:
    """Map Project run results to stable HTTP status semantics."""

    if payload.get("ok"):
        return 200
    code = str(payload.get("error", {}).get("code") or "")
    if code == "ACCESS_DENIED":
        return 403
    if code in {"AGENT_NOT_FOUND", "PROJECT_NOT_FOUND", "SESSION_NOT_FOUND", "SESSION_NOT_IN_PROJECT"}:
        return 404
    return 400


def _normalize_agent_name(value: str) -> str:
    """Normalize one agent id using the existing filesystem-safe convention."""

    normalized = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "-" for ch in value.strip().lower())
    return normalized.strip("-_")


def _project_capability_values(
    body: dict[str, Any],
    snake_case_key: str,
    camel_case_key: str,
    defaults: tuple[str, ...],
) -> list[str]:
    """Resolve one optional Project allowlist, preserving explicit empty lists."""

    if snake_case_key in body:
        raw = body[snake_case_key]
    elif camel_case_key in body:
        raw = body[camel_case_key]
    else:
        return list(defaults)
    if not isinstance(raw, list):
        raise ValueError(f"Field '{snake_case_key}' must be an array.")
    return [str(item).strip() for item in raw if str(item).strip()]


def _default_capability_ids(kind: str, catalog: list[dict[str, Any]]) -> tuple[str, ...]:
    """Return default-enabled capability IDs of one kind in catalog order."""

    return tuple(
        str(item["id"])
        for item in catalog
        if (
            item.get("kind") == kind
            and item.get("default_enabled") is True
            and item.get("available") is True
        )
    )


_MUTATION_AUDIT_ACTIONS = (
    "set_owner",
    "upsert_membership",
    "delete_membership",
    "batch_add_participants",
    "batch_remove_participants",
    "sync_participants",
)
_GM_SCIENCE_DEFAULT_AGENT_ID = "science-research"


def _gm_science_mode_enabled() -> bool:
    """Return whether the local client-api should bootstrap gm-science defaults."""

    return os.getenv("GM_SCIENCE_MODE", "").strip().lower() in {"1", "true", "yes", "on"}


def _normalize_principal_id_list(values: list[str] | tuple[str, ...] | None) -> list[str]:
    """Normalize one list of principal ids while preserving stable order."""
    normalized: list[str] = []
    seen: set[str] = set()
    for raw in values or ():
        principal_id = str(raw or "").strip()
        if not principal_id or principal_id in seen:
            continue
        seen.add(principal_id)
        normalized.append(principal_id)
    return normalized


def _normalize_access_audit_category(value: str | None) -> str:
    """Normalize one admin-audit category selector."""
    normalized = str(value or "all").strip().lower()
    if normalized in {"", "all", "admin"}:
        return "all"
    if normalized == "mutation":
        return "mutation"
    raise ValueError("Query parameter 'category' must be 'all' or 'mutation'.")


def _actions_for_access_audit_category(category: str) -> tuple[str, ...] | None:
    """Return the audit actions included in one category filter."""
    normalized = _normalize_access_audit_category(category)
    if normalized == "all":
        return None
    return _MUTATION_AUDIT_ACTIONS


def global_config_path(data_dir: Path | None = None) -> Path:
    """Return the global multi-agent config path."""

    root = data_dir or get_data_dir()
    return root / "global_config.json"


def agent_config_path(agent_name: str, data_dir: Path | None = None) -> Path:
    """Return the per-agent config path."""

    root = data_dir or get_data_dir()
    return root / agent_name / "config.json"


def list_enabled_agent_names(data_dir: Path | None = None) -> list[str]:
    """Read enabled agent names from the global config file."""

    path = global_config_path(data_dir)
    if not path.exists():
        return []
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []
    if not isinstance(raw, dict):
        return []
    agents_raw = raw.get("agents")
    if isinstance(agents_raw, list):
        entries = agents_raw
    elif isinstance(agents_raw, dict) and isinstance(agents_raw.get("list"), list):
        entries = agents_raw["list"]
    else:
        entries = []

    names: list[str] = []
    seen: set[str] = set()
    for item in entries:
        enabled = True
        if isinstance(item, str):
            name = _normalize_agent_name(item)
        elif isinstance(item, dict):
            name = _normalize_agent_name(str(item.get("name") or item.get("id") or ""))
            raw_enabled = item.get("enabled")
            enabled = raw_enabled is not False
        else:
            continue
        if not name or not enabled or name in seen:
            continue
        seen.add(name)
        names.append(name)
    return names


def build_agent_profile(agent_name: str, data_dir: Path | None = None) -> dict[str, Any]:
    """Build one client-facing agent profile from config files."""

    config_path = agent_config_path(agent_name, data_dir)
    cfg = load_config(config_path=config_path)
    agent_cfg = cfg.get("agent") if isinstance(cfg.get("agent"), dict) else {}
    workspace = str(agent_cfg.get("workspace") or "").strip()
    runtime_env = config_to_env(cfg)
    is_science_agent = _gm_science_mode_enabled() and agent_name == GM_SCIENCE_DEFAULT_AGENT_NAME
    description = (
        "Local personal research agent"
        if is_science_agent
        else f"Workspace: {workspace}" if workspace else "Local openppx agent"
    )
    return {
        "id": agent_name,
        "name": "gm-science" if is_science_agent else agent_name,
        "description": description,
        "provider": runtime_env.get("OPENPPX_PROVIDER", ""),
        "model": runtime_env.get("OPENPPX_MODEL", ""),
        "enabled": True,
        "status": "healthy" if config_path.exists() else "disabled",
        "workspace": workspace or None,
        "avatar": None,
        "tags": ["local", "science"] if is_science_agent else ["local", "openppx"],
    }


def _run_worker_command(*, config_path: Path, args: list[str]) -> dict[str, Any]:
    """Run one worker action and parse its final NDJSON line."""

    cmd = [sys.executable, "-m", "openppx.runtime.client_api_worker", *args]
    proc = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        cwd=str(config_path.parent),
    )
    if proc.returncode != 0:
        message = proc.stderr.strip() or proc.stdout.strip() or f"worker exited with code {proc.returncode}"
        raise RuntimeError(message)
    lines = [line.strip() for line in proc.stdout.splitlines() if line.strip()]
    if not lines:
        return {}
    return json.loads(lines[-1])


def _session_db_url_for_config_path(config_path: Path) -> str:
    """Build the per-agent SQLite session DB URL without mutating process env."""

    db_path = config_path.parent / "database" / "sessions.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return f"sqlite+aiosqlite:///{db_path}"


def _preview_value(value: Any, fallback: str) -> str:
    if isinstance(value, str):
        stripped = value.strip()
        return stripped or fallback
    try:
        dumped = json.dumps(value if value is not None else {}, ensure_ascii=False, indent=2)
    except Exception:
        dumped = str(value)
    dumped = dumped.strip()
    if not dumped or dumped == "{}":
        return fallback
    return dumped[:320] + ("..." if len(dumped) > 320 else "")


def _gm_science_project_payload(
    project: ProjectRecord,
    *,
    sessions_count: int = 0,
    artifacts_count: int = 0,
) -> dict[str, Any]:
    """Project one gm-science project into a client API payload."""

    return {
        "id": project.id,
        "name": project.name,
        "description": project.description,
        "agent_context": project.agent_context,
        "workspace_path": project.workspace_path,
        "created_at": project.created_at,
        "updated_at": project.updated_at,
        "enabled_skills": list(project.enabled_skills),
        "enabled_connectors": list(project.enabled_connectors),
        "enabled_specialists": list(project.enabled_specialists),
        "session_policy_defaults": dict(project.session_policy_defaults),
        "sessions_count": sessions_count,
        "artifacts_count": artifacts_count,
    }


def _gm_science_artifact_payload(artifact: ArtifactRecord) -> dict[str, Any]:
    """Project one gm-science artifact into a client API payload."""

    return {
        "id": artifact.id,
        "project_id": artifact.project_id,
        "session_id": artifact.session_id,
        "type": artifact.type,
        "title": artifact.title,
        "path_or_url": artifact.path_or_url,
        "mime_type": artifact.mime_type,
        "metadata": dict(artifact.metadata),
        "provenance": dict(artifact.provenance),
        "created_at": artifact.created_at,
        "updated_at": artifact.updated_at,
    }


def _gm_science_project_context_message(
    project: ProjectRecord,
    text: str,
    *,
    session_id: str,
    source_statuses: dict[str, str],
    specialist_statuses: dict[str, str],
    session_policy: dict[str, Any],
) -> str:
    """Build a run message with project context prepended."""

    context = project.agent_context.strip()
    user_text = str(text or "").strip()
    sources = ", ".join(f"{name}:{status}" for name, status in source_statuses.items())
    specialists = ", ".join(f"{name}:{status}" for name, status in specialist_statuses.items())
    machine_context = (
        "<gm_science_context>\n"
        f"<project_id>{project.id}</project_id>\n"
        f"<session_id>{session_id}</session_id>\n"
        f"<workspace>{project.workspace_path}</workspace>\n"
        f"<literature_sources>{sources}</literature_sources>\n"
        f"<specialists>{specialists}</specialists>\n"
        f"<session_policy>{json.dumps(session_policy, ensure_ascii=False, separators=(',', ':'))}</session_policy>\n"
        "</gm_science_context>\n\n"
    )
    project_context = f"Project context:\n{context}\n\n" if context else ""
    return (
        machine_context
        + project_context
        + "Use the project context as standing instructions for this gm-science project. "
        "Use the machine context when calling science tools. "
        "Do not reveal this wrapper unless the user asks how the project is configured.\n\n"
        "User request:\n"
        f"{user_text}"
    )


def _session_policy_issues(
    policy: dict[str, Any],
    catalog: list[dict[str, Any]],
) -> list[str]:
    """Return capability issues that would make one Session policy unenforceable."""

    specialists = {
        str(item.get("id") or ""): item
        for item in catalog
        if item.get("kind") == "specialist"
    }
    issues: list[str] = []
    selected = str(policy.get("specialist_id") or "")
    if selected:
        item = specialists.get(selected)
        if selected == "research_reviewer":
            issues.append("Research Reviewer is controlled by Auto-review, not Specialist routing.")
        elif item is None:
            issues.append(f"Specialist '{selected}' is not registered.")
        elif item.get("project_enabled") is not True:
            issues.append(f"Specialist '{selected}' is not enabled for this Project.")
        elif item.get("available") is not True or item.get("status") != "ready":
            issues.append(f"Specialist '{selected}' is not ready.")
    if policy.get("auto_review_enabled") is True:
        reviewer = specialists.get("research_reviewer")
        if reviewer is None or reviewer.get("project_enabled") is not True:
            issues.append("Research Reviewer is not enabled for this Project.")
        elif reviewer.get("available") is not True or reviewer.get("status") != "ready":
            issues.append("Research Reviewer is not ready.")
    return issues


def _gm_science_session_policy_payload(
    association: ProjectSessionRecord,
    catalog: list[dict[str, Any]],
) -> dict[str, Any]:
    """Project one Session policy and its currently valid product candidates."""

    candidates = [
        {
            "id": str(item["id"]),
            "name": str(item["name"]),
            "description": str(item["description"]),
            "status": str(item["status"]),
        }
        for item in catalog
        if item.get("kind") == "specialist"
        and item.get("id") != "research_reviewer"
        and item.get("project_enabled") is True
        and item.get("available") is True
        and item.get("status") == "ready"
    ]
    reviewer = next(
        (
            item
            for item in catalog
            if item.get("kind") == "specialist" and item.get("id") == "research_reviewer"
        ),
        None,
    )
    return {
        "session_id": association.session_id,
        "project_id": association.project_id,
        **dict(association.policy),
        "specialists": candidates,
        "reviewer_available": bool(
            reviewer
            and reviewer.get("project_enabled") is True
            and reviewer.get("available") is True
            and reviewer.get("status") == "ready"
        ),
        "reviewer_models": [{"id": "default", "name": "Default"}],
        "compute_targets": [{"id": "local", "name": "Local"}],
        "issues": _session_policy_issues(association.policy, catalog),
    }


def _strip_request_time_prefix(text: str) -> str:
    """Remove runtime-injected request-time guidance from persisted user text."""

    stripped = text.strip()
    if not stripped.startswith("Current request time: "):
        return text

    lines = stripped.splitlines()
    if len(lines) < 2 or "Use this as the reference 'now' for relative time expressions" not in lines[1]:
        return text

    body_lines = lines[2:]
    while body_lines and not body_lines[0].strip():
        body_lines = body_lines[1:]
    return "\n".join(body_lines).strip()


def _visible_user_request(text: str) -> str:
    """Extract the user-authored request from gm-science's internal context wrapper."""

    if "<gm_science_context>" not in text:
        return text
    marker = "\nUser request:\n"
    if marker not in text:
        return text
    return text.rsplit(marker, 1)[1].strip()


def _step_ref_payload(*, step_id: str, title: str, status: str, detail: str) -> dict[str, Any]:
    """Build one client-facing step part payload."""

    return {
        "type": "step_ref",
        "step_id": step_id,
        "title": title,
        "status": status,
        "detail": detail,
    }


def _message_payload(
    *,
    message_id: str,
    session_id: str,
    role: str,
    parts: list[dict[str, Any]],
    status: str,
) -> dict[str, Any]:
    """Build one client-facing message payload."""

    return {
        "id": message_id,
        "session_id": session_id,
        "role": role,
        "parts": parts,
        "status": status,
        "created_at": _iso_now(),
        "metadata": {},
    }


def _error_part_payload(*, code: str, text: str) -> dict[str, Any]:
    """Build one client-facing error part payload."""

    return {
        "type": "error",
        "error_code": code,
        "text": text,
    }


def _tool_result_payload(*, tool_name: str, summary: str, detail: str, raw_text: str) -> dict[str, Any]:
    """Build one client-facing tool result part payload."""

    return {
        "type": "tool_result",
        "tool_name": tool_name,
        "summary": summary,
        "detail": detail,
        "raw_text": raw_text,
    }


def _tool_result_summary(tool_name: str, response: Any) -> str:
    """Build a short human-readable summary for one tool response."""

    if isinstance(response, dict):
        message = response.get("message")
        if isinstance(message, str) and message.strip():
            return message.strip()
        summary = response.get("summary")
        if isinstance(summary, str) and summary.strip():
            return summary.strip()
        ok = response.get("ok")
        if isinstance(ok, bool):
            return f"{tool_name} returned successfully." if ok else f"{tool_name} reported a failure."
        keys = list(response.keys())
        if keys:
            return f"{tool_name} returned {len(keys)} fields."
    if isinstance(response, str) and response.strip():
        return response.strip()[:140]
    return f"{tool_name} returned a result."


def _event_preview_text(event: dict[str, Any]) -> str:
    """Build a lightweight session preview string from one serialized event."""

    content = event.get("content") if isinstance(event.get("content"), dict) else {}
    raw_parts = content.get("parts") if isinstance(content.get("parts"), list) else []
    texts: list[str] = []
    for raw_part in raw_parts:
        if not isinstance(raw_part, dict):
            continue
        if bool(raw_part.get("thought")):
            continue
        if _resource_part_metadata(raw_part) is not None:
            continue
        text = raw_part.get("text")
        if isinstance(text, str) and text.strip():
            normalized_text = _strip_request_time_prefix(text)
            if normalized_text.strip():
                texts.append(normalized_text.strip())
    return " ".join(texts).strip()


def _compact_session_title(text: str, *, limit: int = 64) -> str:
    """Return a single-line session title derived from user-visible text."""
    normalized = " ".join(str(text or "").split())
    if len(normalized) <= limit:
        return normalized
    return normalized[: max(0, limit - 3)].rstrip() + "..."


def _session_title_from_events(events: list[dict[str, Any]]) -> str:
    """Return the first user message as the stable client-facing session title."""
    for event in events:
        if str(event.get("author") or "").strip().lower() != "user":
            continue
        title = _compact_session_title(_visible_user_request(_event_preview_text(event)))
        if title:
            return title
    return ""


def _debug(tag: str, payload: Any) -> None:
    """Emit one structured debug log when client-api debugging is enabled."""

    if not debug_logging_enabled():
        return
    emit_debug(tag, payload, depth=3)


def project_session_event(event: dict[str, Any], session_id: str) -> dict[str, Any] | None:
    """Project one ADK session event into the client chat message schema."""

    author = str(event.get("author") or "").strip().lower()
    role = "assistant"
    if author == "user":
        role = "user"
    elif author == "tool":
        role = "tool"
    elif author == "system":
        role = "system"

    timestamp = event.get("timestamp")
    if isinstance(timestamp, (int, float)):
        created_at = dt.datetime.fromtimestamp(timestamp, tz=dt.timezone.utc).astimezone().isoformat()
    else:
        created_at = _iso_now()

    content = event.get("content") if isinstance(event.get("content"), dict) else {}
    raw_parts = content.get("parts") if isinstance(content, dict) and isinstance(content.get("parts"), list) else []
    parts: list[dict[str, Any]] = []
    for raw_part in raw_parts:
        if not isinstance(raw_part, dict):
            continue
        if bool(raw_part.get("thought")):
            continue
        resource_metadata = _resource_part_metadata(raw_part)
        if resource_metadata is not None:
            parts.append(_resource_ref_message_part(resource_metadata))
            continue
        text = raw_part.get("text")
        if isinstance(text, str) and text.strip():
            normalized_text = _strip_request_time_prefix(text)
            if role == "user":
                normalized_text = _visible_user_request(normalized_text)
            if normalized_text.strip():
                parts.append({"type": "markdown", "text": normalized_text})
        function_call = raw_part.get("function_call")
        if isinstance(function_call, dict):
            parts.append(
                {
                    "type": "step_ref",
                    "step_id": str(function_call.get("id") or "step"),
                    "title": str(function_call.get("name") or "tool"),
                    "status": "completed",
                    "detail": _preview_value(function_call.get("args"), "No tool arguments"),
                }
            )
        function_response = raw_part.get("function_response")
        if isinstance(function_response, dict):
            step_id = str(function_response.get("id") or function_response.get("name") or "tool")
            tool_name = str(function_response.get("name") or "tool")
            response = function_response.get("response") or {}
            parts.append(
                {
                    "type": "step_ref",
                    "step_id": step_id,
                    "title": tool_name,
                    "status": "completed",
                    "detail": _preview_value(response, "Tool returned without a payload"),
                }
            )
            parts.append(
                _tool_result_payload(
                    tool_name=tool_name,
                    summary=_tool_result_summary(tool_name, response),
                    detail=_preview_value(response, "Tool returned without a payload"),
                    raw_text=json.dumps(response, ensure_ascii=False, indent=2),
                )
            )
    if not parts:
        return None
    return {
        "id": str(event.get("id") or f"msg_{session_id}"),
        "session_id": session_id,
        "role": role,
        "parts": parts,
        "status": "completed",
        "created_at": created_at,
        "metadata": {},
    }


def _resource_part_metadata(raw_part: dict[str, Any]) -> dict[str, Any] | None:
    """Return validated gm-science metadata from one serialized ADK Part."""

    raw_metadata = raw_part.get("part_metadata") or raw_part.get("partMetadata")
    if not isinstance(raw_metadata, dict):
        return None
    resource = raw_metadata.get("gm_science_resource")
    if not isinstance(resource, dict) or not str(resource.get("id") or "").strip():
        return None
    return resource


def _resource_ref_message_part(resource: dict[str, Any]) -> dict[str, Any]:
    """Project safe resource metadata into the renderer message contract."""

    return {
        "type": "resource_ref",
        "resource_id": str(resource.get("id") or ""),
        "display_name": str(resource.get("display_name") or "Project resource"),
        "kind": str(resource.get("kind") or "artifact"),
        "version_or_hash": str(resource.get("version_or_hash") or ""),
        "mime_type": str(resource.get("mime_type") or ""),
        "relative_path": str(resource.get("relative_path") or ""),
        "url": str(resource.get("url") or ""),
        "content_status": str(resource.get("content_status") or "metadata_descriptor_only"),
        "truncated": bool(resource.get("truncated")),
    }


@dataclass(slots=True)
class RunEnvelope:
    """One replayable SSE event payload."""

    event_id: str
    seq: int
    event: str
    payload: dict[str, Any]


@dataclass(slots=True)
class _TimedCacheEntry:
    """One short-lived in-memory cache entry."""

    value: Any
    expires_at: float


class RunHandle:
    """Track one running worker subprocess and its replayable SSE events."""

    def __init__(self, *, run_id: str, agent_id: str, session_id: str, process: subprocess.Popen[str]) -> None:
        self.run_id = run_id
        self.agent_id = agent_id
        self.session_id = session_id
        self.process = process
        self.assistant_message_id = f"msg_{run_id}_assistant"
        self._history: list[RunEnvelope] = []
        self._subscribers: list[queue.Queue[RunEnvelope | None]] = []
        self._lock = threading.Lock()
        self._seq = 0
        self._stderr_lines: list[str] = []
        self.done = threading.Event()
        self.failed = False
        self.started_at_monotonic = time.monotonic()
        self.first_delta_at_monotonic: float | None = None

    def elapsed_ms(self) -> float:
        """Return milliseconds elapsed since the worker run was created."""

        return round((time.monotonic() - self.started_at_monotonic) * 1000, 1)

    def mark_first_delta(self) -> bool:
        """Record the first user-visible text update and report whether it was new."""

        if self.first_delta_at_monotonic is not None:
            return False
        self.first_delta_at_monotonic = time.monotonic()
        return True

    def publish(self, event: str, payload: dict[str, Any]) -> None:
        """Store and fan out one SSE event."""

        with self._lock:
            self._seq += 1
            envelope = RunEnvelope(
                event_id=f"{self.run_id}:{self._seq}",
                seq=self._seq,
                event=event,
                payload=payload,
            )
            self._history.append(envelope)
            subscribers = list(self._subscribers)
        for subscriber in subscribers:
            subscriber.put(envelope)

    def finish(self) -> None:
        """Mark the run as completed and close subscribers."""

        with self._lock:
            self.done.set()
            subscribers = list(self._subscribers)
            self._subscribers.clear()
        for subscriber in subscribers:
            subscriber.put(None)

    def append_stderr_line(self, line: str) -> None:
        """Retain a bounded stderr history for later debug reporting."""

        with self._lock:
            self._stderr_lines.append(line)
            if len(self._stderr_lines) > 20:
                self._stderr_lines = self._stderr_lines[-20:]

    def stderr_text(self) -> str:
        """Return the retained stderr snapshot."""

        with self._lock:
            return "\n".join(self._stderr_lines)

    def cancel(self) -> bool:
        """Terminate the subprocess if it is still running."""

        if self.done.is_set():
            return False
        if self.process.poll() is None:
            self.process.terminate()
        self.publish(
            "message.cancelled",
            {
                "run_id": self.run_id,
                "agent_id": self.agent_id,
                "session_id": self.session_id,
                "message_id": self.assistant_message_id,
                "status": "cancelled",
            },
        )
        self.publish(
            "run.cancelled",
            {
                "run_id": self.run_id,
                "agent_id": self.agent_id,
                "session_id": self.session_id,
                "message_id": self.assistant_message_id,
                "status": "cancelled",
            },
        )
        self.finish()
        return True

    def subscribe(self, last_event_id: str | None = None) -> queue.Queue[RunEnvelope | None]:
        """Create one subscriber queue and replay retained history."""

        q: queue.Queue[RunEnvelope | None] = queue.Queue()
        with self._lock:
            replay = list(self._history)
            if last_event_id:
                replay = [item for item in replay if item.event_id > last_event_id]
            if not self.done.is_set():
                self._subscribers.append(q)
            done = self.done.is_set()
        for item in replay:
            q.put(item)
        if done:
            q.put(None)
        return q


class ClientApiCoordinator:
    """Coordinate local client-facing HTTP requests and background run streams."""

    _CACHE_TTL_SECONDS = 5.0

    def __init__(
        self,
        *,
        data_dir: Path | None = None,
        identity_store: IdentityStore | None = None,
        agent_access_store: AgentAccessStore | None = None,
        access_policy: AccessPolicy | None = None,
        memory_query_service: MemoryQueryService | None = None,
    ) -> None:
        self.data_dir = data_dir or get_data_dir()
        self._gm_science_mode = _gm_science_mode_enabled()
        if self._gm_science_mode:
            ensure_gm_science_initialized(root_dir=self.data_dir)
        default_identity_db_path = self.data_dir / "database" / "identity.db"
        self._identity_store = identity_store or IdentityStore(db_path=default_identity_db_path)
        self._agent_access_store = agent_access_store or AgentAccessStore(db_path=default_identity_db_path)
        self._access_policy = access_policy or AccessPolicy(
            identity_store=self._identity_store,
            agent_access_store=self._agent_access_store,
        )
        local_memory_db_path = self.data_dir / "database" / "memory.db"
        self._gm_science_memory_backend = SQLiteMemoryService(db_path=local_memory_db_path)
        if memory_query_service is None:
            self._memory_query_service = MemoryQueryService(
                identity_store=self._identity_store,
                access_policy=self._access_policy,
                memory_service=self._gm_science_memory_backend,
                audit_db_path=local_memory_db_path,
            )
        else:
            self._memory_query_service = memory_query_service
        self._session_agents: dict[str, str] = {}
        self._session_owners: dict[str, str] = {}
        self._runs: dict[str, RunHandle] = {}
        self._lock = threading.Lock()
        self._gm_science_config_lock = threading.RLock()
        self._sessions_cache: dict[tuple[str, str], _TimedCacheEntry] = {}
        self._messages_cache: dict[tuple[str, str], _TimedCacheEntry] = {}
        self._gm_science_store = GmScienceStore(self.data_dir)
        self._gm_science_memory = GmScienceMemoryService(
            store=self._gm_science_store,
            backend=self._gm_science_memory_backend,
        )
        self._science_execution = ScienceExecutionService(
            data_dir=self.data_dir,
            store=self._gm_science_store,
            config_path=agent_config_path(GM_SCIENCE_DEFAULT_AGENT_NAME, self.data_dir),
        )
        self._gm_science_settings = GmScienceSettingsService(
            config_path=agent_config_path(GM_SCIENCE_DEFAULT_AGENT_NAME, self.data_dir),
            lock=self._gm_science_config_lock,
        )
        self._gm_science_authoring = GmScienceCapabilityAuthoringService(
            config_path=agent_config_path(GM_SCIENCE_DEFAULT_AGENT_NAME, self.data_dir),
            lock=self._gm_science_config_lock,
        )
        self._gm_science_observability = GmScienceObservabilityService(data_dir=self.data_dir)
        self._dataset_service = DatasetService(
            store=self._gm_science_store,
            config_path=agent_config_path(GM_SCIENCE_DEFAULT_AGENT_NAME, self.data_dir),
        )
        self._resource_catalog = ResourceCatalogService(
            store=self._gm_science_store,
            config_path=agent_config_path(GM_SCIENCE_DEFAULT_AGENT_NAME, self.data_dir),
        )
        self._resource_context = ResourceContextService(catalog=self._resource_catalog)
        self._resource_detail = ResourceDetailService(
            catalog=self._resource_catalog,
            context=self._resource_context,
        )
        self._analysis_service = AnalysisService(
            store=self._gm_science_store,
            dataset_service=self._dataset_service,
            execution_service=self._science_execution,
            config_path=agent_config_path(GM_SCIENCE_DEFAULT_AGENT_NAME, self.data_dir),
        )

    def _ensure_requester_principal(self, user_id: str) -> ResolvedPrincipal:
        """Return a persisted requester principal for client-api operations."""
        principal_id = str(user_id or "ppx-client-user").strip() or "ppx-client-user"
        existing = self._identity_store.get_principal(principal_id)
        if existing is not None:
            return existing
        principal = ResolvedPrincipal(
            principal_id=principal_id,
            principal_type="human",
            privilege_level="minimal",
            account_kind="local_client",
            display_name=principal_id,
            authenticated=True,
            external_subject_id=principal_id,
            external_display_id=principal_id,
            metadata={"source": "client_api"},
        )
        return self._identity_store.put_principal(principal)

    def _ensure_agent_access_state(self, agent_id: str) -> Path | None:
        """Ensure access rows exist for one configured agent before evaluation."""
        config_path = agent_config_path(agent_id, self.data_dir)
        if not config_path.exists():
            return None
        ensure_agent_access_record(
            agent_id=agent_id,
            agent_name=agent_id,
            identity_store=self._identity_store,
            agent_access_store=self._agent_access_store,
            config_path=config_path,
            apply_env_overrides=False,
        )
        return config_path

    def _visible_principal_ids(self, requester_principal_id: str, *, agent_id: str, access_kind: str) -> tuple[Any, tuple[str, ...]]:
        """Resolve the effective visible principal ids for one request."""
        decision = self._access_policy.decide_agent_scope(
            requester_principal_id=requester_principal_id,
            agent_id=agent_id,
            access_kind=access_kind,
        )
        if not decision.allow:
            return decision, ()
        visible_principal_ids = decision.resolved_scope(self._identity_store.list_principal_ids())
        if visible_principal_ids:
            return decision, visible_principal_ids
        return decision, (requester_principal_id,)

    def _read_cache(self, cache: dict[tuple[str, str], _TimedCacheEntry], key: tuple[str, str]) -> Any | None:
        now_ts = dt.datetime.now().timestamp()
        with self._lock:
            entry = cache.get(key)
            if entry is None:
                return None
            if entry.expires_at < now_ts:
                cache.pop(key, None)
                return None
            return entry.value

    def _write_cache(self, cache: dict[tuple[str, str], _TimedCacheEntry], key: tuple[str, str], value: Any) -> None:
        with self._lock:
            cache[key] = _TimedCacheEntry(
                value=value,
                expires_at=dt.datetime.now().timestamp() + self._CACHE_TTL_SECONDS,
            )

    def _invalidate_agent_cache(self, agent_id: str, *, user_id: str) -> None:
        with self._lock:
            self._sessions_cache.pop((agent_id, user_id), None)

    def _invalidate_session_cache(self, session_id: str, *, user_id: str) -> None:
        with self._lock:
            self._messages_cache.pop((session_id, user_id), None)

    def _invalidate_agent_access_caches(self, agent_id: str) -> None:
        """Drop cached views that may become stale after access mutations."""
        with self._lock:
            self._sessions_cache = {
                key: value for key, value in self._sessions_cache.items() if key[0] != agent_id
            }
            affected_session_ids = {
                session_id
                for session_id, cached_agent_id in self._session_agents.items()
                if cached_agent_id == agent_id
            }
            self._messages_cache = {
                key: value for key, value in self._messages_cache.items() if key[0] not in affected_session_ids
            }

    def _record_admin_audit(
        self,
        *,
        agent_id: str,
        requester: ResolvedPrincipal,
        action: str,
        relation_to_agent: str,
        target_principal_id: str = "",
        details: dict[str, Any] | None = None,
    ) -> None:
        """Persist one admin-surface audit event without raising to callers."""
        try:
            self._agent_access_store.record_audit(
                agent_id=agent_id,
                actor_principal_id=requester.principal_id,
                actor_relation=relation_to_agent,
                action=action,
                target_principal_id=target_principal_id,
                details=details,
            )
        except Exception:
            return

    def _validate_membership_management(
        self,
        *,
        agent_id: str,
        requester: ResolvedPrincipal,
        access_kind: str = "membership_write",
        denied_action: str,
        denied_target_principal_id: str = "",
        denied_details: dict[str, Any] | None = None,
    ) -> tuple[Path | None, Any, dict[str, Any] | None]:
        """Validate one membership-management request and prebuild deny payloads."""
        config_path = self._ensure_agent_access_state(agent_id)
        if config_path is None:
            return None, None, _error("AGENT_NOT_FOUND", f"Agent '{agent_id}' was not found.")
        decision = self._access_policy.decide_agent_management(
            requester_principal_id=requester.principal_id,
            agent_id=agent_id,
            access_kind=access_kind,
        )
        if decision.allow:
            return config_path, decision, None
        self._record_admin_audit(
            agent_id=agent_id,
            requester=requester,
            action=denied_action,
            relation_to_agent=decision.relation_to_agent,
            target_principal_id=denied_target_principal_id,
            details={
                "allowed": False,
                "reason": decision.reason,
                **dict(denied_details or {}),
            },
        )
        return config_path, decision, _error(
            "ACCESS_DENIED",
            f"Principal '{requester.principal_id}' cannot change memberships for agent '{agent_id}'.",
            {"reason": decision.reason},
        )

    def _read_sessions_direct(self, config_path: Path, *, user_id: str) -> list[dict[str, Any]]:
        """Read session summaries directly from the per-agent SQLite store."""

        async def _load() -> list[dict[str, Any]]:
            service = create_session_service(SessionConfig(db_url=_session_db_url_for_config_path(config_path)))
            async with service:
                response = await service.list_sessions(app_name="openppx", user_id=user_id)
                items: list[dict[str, Any]] = []
                for session in response.sessions:
                    detail = await service.get_session(
                        app_name="openppx",
                        user_id=user_id,
                        session_id=session.id,
                    )
                    events = [event.model_dump(mode="json") for event in (detail.events if detail else [])]
                    items.append(
                        {
                            "id": session.id,
                            "last_update_time": (detail.last_update_time if detail else session.last_update_time),
                            "title": _session_title_from_events(events),
                            "last_preview": _event_preview_text(events[-1]) if events else "",
                        }
                    )
                return items

        return asyncio.run(_load())

    def _read_sessions_worker(self, config_path: Path, *, user_id: str) -> list[dict[str, Any]]:
        """Read session summaries through the worker fallback path."""
        response = _run_worker_command(
            config_path=config_path,
            args=[
                "list_sessions",
                "--config-path",
                str(config_path),
                "--user-id",
                user_id,
            ],
        )
        return [item for item in response.get("sessions", []) if isinstance(item, dict)]

    def _create_session_direct(self, config_path: Path, *, user_id: str, session_id: str) -> dict[str, Any]:
        """Create one session directly in the per-agent SQLite store."""

        async def _create() -> dict[str, Any]:
            service = create_session_service(SessionConfig(db_url=_session_db_url_for_config_path(config_path)))
            async with service:
                session = await service.create_session(
                    app_name="openppx",
                    user_id=user_id,
                    session_id=session_id,
                )
            return {
                "id": session.id,
                "last_update_time": session.last_update_time,
            }

        return asyncio.run(_create())

    def _get_session_direct(self, config_path: Path, *, user_id: str, session_id: str) -> dict[str, Any] | None:
        """Read one session with events directly from the per-agent SQLite store."""

        async def _load() -> dict[str, Any] | None:
            service = create_session_service(SessionConfig(db_url=_session_db_url_for_config_path(config_path)))
            async with service:
                session = await service.get_session(
                    app_name="openppx",
                    user_id=user_id,
                    session_id=session_id,
                )
            if session is None:
                return None
            return {
                "id": session.id,
                "last_update_time": session.last_update_time,
                "events": [event.model_dump(mode="json") for event in session.events],
            }

        return asyncio.run(_load())

    def _get_session_worker(self, config_path: Path, *, user_id: str, session_id: str) -> dict[str, Any] | None:
        """Read one session through the worker fallback path."""
        response = _run_worker_command(
            config_path=config_path,
            args=[
                "get_session",
                "--config-path",
                str(config_path),
                "--session-id",
                session_id,
                "--user-id",
                user_id,
            ],
        )
        session = response.get("session")
        return session if isinstance(session, dict) else None

    def _read_sessions_for_principal(self, config_path: Path, *, user_id: str) -> list[dict[str, Any]]:
        """Read one principal-scoped session list with worker fallback."""
        try:
            return self._read_sessions_direct(config_path, user_id=user_id)
        except Exception as exc:
            _debug(
                "client_api.list_sessions.direct_failed",
                {
                    "config_path": str(config_path),
                    "user_id": user_id,
                    "error": str(exc),
                },
            )
            return self._read_sessions_worker(config_path, user_id=user_id)

    def _get_session_for_principal(
        self,
        config_path: Path,
        *,
        user_id: str,
        session_id: str,
    ) -> dict[str, Any] | None:
        """Read one principal-scoped session with worker fallback."""
        try:
            return self._get_session_direct(config_path, user_id=user_id, session_id=session_id)
        except Exception as exc:
            _debug(
                "client_api.get_session.direct_failed",
                {
                    "config_path": str(config_path),
                    "session_id": session_id,
                    "user_id": user_id,
                    "error": str(exc),
                },
            )
            return self._get_session_worker(config_path, user_id=user_id, session_id=session_id)

    def _collect_visible_sessions(
        self,
        *,
        agent_id: str,
        requester_principal_id: str,
    ) -> tuple[Any, list[tuple[str, dict[str, Any]]]] | dict[str, Any]:
        """Collect session rows visible to one requester for one agent."""
        config_path = self._ensure_agent_access_state(agent_id)
        if config_path is None:
            return _error("AGENT_NOT_FOUND", f"Agent '{agent_id}' was not found.")
        decision, visible_principal_ids = self._visible_principal_ids(
            requester_principal_id,
            agent_id=agent_id,
            access_kind="session_list",
        )
        if not decision.allow:
            return _error(
                "ACCESS_DENIED",
                f"Principal '{requester_principal_id}' cannot list sessions for agent '{agent_id}'.",
                {"reason": decision.reason},
            )

        rows: list[tuple[str, dict[str, Any]]] = []
        for subject_principal_id in visible_principal_ids:
            try:
                sessions = self._read_sessions_for_principal(config_path, user_id=subject_principal_id)
            except Exception as exc:
                return _error("RUNTIME_UNAVAILABLE", str(exc))
            for session in sessions:
                rows.append((subject_principal_id, session))
        return decision, rows

    def _find_session_owner(
        self,
        *,
        session_id: str,
        requester_principal_id: str,
    ) -> tuple[str, str] | dict[str, Any]:
        """Resolve the agent id and owner principal for one visible session."""
        agent_id = self._session_agents.get(session_id)
        subject_principal_id = self._session_owners.get(session_id)
        if agent_id and subject_principal_id:
            decision = self._access_policy.decide_subject_access(
                requester_principal_id=requester_principal_id,
                agent_id=agent_id,
                subject_principal_id=subject_principal_id,
                access_kind="session_read",
            )
            if decision.allow:
                return agent_id, subject_principal_id
            return _error(
                "ACCESS_DENIED",
                f"Principal '{requester_principal_id}' cannot read session '{session_id}'.",
                {"reason": decision.reason},
            )

        for candidate in list_enabled_agent_names(self.data_dir):
            visible = self._collect_visible_sessions(
                agent_id=candidate,
                requester_principal_id=requester_principal_id,
            )
            if isinstance(visible, dict):
                if visible.get("error", {}).get("code") == "ACCESS_DENIED":
                    continue
                return visible
            _decision, rows = visible
            for owner_principal_id, session in rows:
                candidate_session_id = str(session.get("id") or "")
                if candidate_session_id != session_id:
                    continue
                self._session_agents[session_id] = candidate
                self._session_owners[session_id] = owner_principal_id
                return candidate, owner_principal_id
        return _error("SESSION_NOT_FOUND", f"Session '{session_id}' was not found.")

    def health(self) -> dict[str, Any]:
        """Return a lightweight health payload."""

        return _ok(
            {
                "service": "openppx-client-api",
                "state": "healthy",
                "data_dir": str(self.data_dir),
                "agents": len(list_enabled_agent_names(self.data_dir)),
                "timestamp": _iso_now(),
            }
        )

    def runtime_status(self) -> dict[str, Any]:
        """Return a client-facing runtime status payload."""

        return _ok(
            {
                "target": {
                    "id": "local-default",
                    "type": "local",
                    "name": "This Mac",
                },
                "state": "healthy",
                "summary": "Local client-api gateway is ready.",
                "detail": "The desktop client can use HTTP for queries and SSE for run events.",
            }
        )

    def list_agents(self) -> dict[str, Any]:
        """Return enabled local agent profiles."""

        agents = [build_agent_profile(name, self.data_dir) for name in list_enabled_agent_names(self.data_dir)]
        return _ok({"items": agents})

    def list_gm_science_projects(self) -> dict[str, Any]:
        """Return local gm-science projects."""

        items = [
            _gm_science_project_payload(
                project,
                sessions_count=self._gm_science_store.count_project_sessions(project.id),
                artifacts_count=len(self._gm_science_store.list_artifacts(project.id)),
            )
            for project in self._gm_science_store.list_projects()
        ]
        return _ok({"items": items})

    def create_gm_science_project(self, body: dict[str, Any]) -> dict[str, Any]:
        """Create one local gm-science project."""

        name = str(body.get("name") or "").strip()
        if not name:
            return _error("INVALID_REQUEST", "Field 'name' is required.")
        try:
            config_path = agent_config_path(GM_SCIENCE_DEFAULT_AGENT_NAME, self.data_dir)
            catalog = build_capability_catalog(config_path=config_path)
            enabled_skills = normalize_capability_selection(
                kind="skill",
                values=_project_capability_values(
                    body,
                    "enabled_skills",
                    "enabledSkills",
                    _default_capability_ids("skill", catalog),
                ),
                catalog=catalog,
            )
            enabled_connectors = normalize_capability_selection(
                kind="connector",
                values=_project_capability_values(
                    body,
                    "enabled_connectors",
                    "enabledConnectors",
                    _default_capability_ids("connector", catalog),
                ),
                catalog=catalog,
            )
            enabled_specialists = normalize_capability_selection(
                kind="specialist",
                values=_project_capability_values(
                    body,
                    "enabled_specialists",
                    "enabledSpecialists",
                    _default_capability_ids("specialist", catalog),
                ),
                catalog=catalog,
            )
            required_permissions: list[str] = []
            if enabled_skills:
                required_permissions.append("attach_skill")
            if enabled_connectors:
                required_permissions.append("attach_connector")
            if enabled_specialists:
                required_permissions.append("update_agent")
            self._gm_science_settings.require_permissions(required_permissions)
            project = self._gm_science_store.create_project(
                name=name,
                description=str(body.get("description") or ""),
                agent_context=str(body.get("agent_context") or body.get("agentContext") or ""),
                enabled_skills=enabled_skills,
                enabled_connectors=enabled_connectors,
                enabled_specialists=enabled_specialists,
                session_policy_defaults=normalize_session_policy(
                    body.get("session_policy_defaults")
                    or body.get("sessionPolicyDefaults")
                    or None
                ),
            )
        except RegistryPermissionError as exc:
            return _error("PERMISSION_DENIED", str(exc))
        except ValueError as exc:
            return _error("INVALID_REQUEST", str(exc))
        return _ok({"project": _gm_science_project_payload(project)})

    def get_gm_science_project(self, project_id: str) -> dict[str, Any]:
        """Return one local gm-science project."""

        project = self._gm_science_store.get_project(project_id)
        if project is None:
            return _error("PROJECT_NOT_FOUND", f"Project '{project_id}' was not found.")
        return _ok(
            {
                "project": _gm_science_project_payload(
                    project,
                    sessions_count=self._gm_science_store.count_project_sessions(project.id),
                    artifacts_count=len(self._gm_science_store.list_artifacts(project.id)),
                )
            }
        )

    def list_gm_science_capabilities(self, project_id: str | None = None) -> dict[str, Any]:
        """Return the public capability catalog for the system or one Project."""

        project = None
        if project_id:
            project = self._gm_science_store.get_project(project_id)
            if project is None:
                return _error("PROJECT_NOT_FOUND", f"Project '{project_id}' was not found.")
        config_path = agent_config_path(GM_SCIENCE_DEFAULT_AGENT_NAME, self.data_dir)
        return _ok(
            {
                "project_id": project.id if project is not None else None,
                "items": build_capability_catalog(config_path=config_path, project=project),
            }
        )

    def create_gm_science_capability(
        self,
        kind: str,
        body: dict[str, Any],
    ) -> dict[str, Any]:
        """Create one local Skill, MCP Connector, or Specialist definition."""

        creators = {
            "skills": self._gm_science_authoring.create_skill,
            "connectors": self._gm_science_authoring.create_connector,
            "specialists": self._gm_science_authoring.create_specialist,
        }
        creator = creators.get(str(kind or "").strip().lower())
        if creator is None:
            return _error("INVALID_REQUEST", f"Unsupported capability kind '{kind}'.")
        try:
            capability = creator(body)
        except RegistryPermissionError as exc:
            return _error("PERMISSION_DENIED", str(exc))
        except CapabilityConflictError as exc:
            return _error("CAPABILITY_CONFLICT", str(exc))
        except ValueError as exc:
            return _error("INVALID_REQUEST", str(exc))
        return _ok({"capability": capability})

    def get_gm_science_session_policy(self, session_id: str) -> dict[str, Any]:
        """Return one Project Session's effective policy and valid candidates."""

        association = self._gm_science_store.get_project_session(session_id)
        if association is None:
            return _error(
                "SESSION_NOT_IN_PROJECT",
                f"Session '{session_id}' is not attached to a Project.",
            )
        project = self._gm_science_store.get_project(association.project_id)
        if project is None:
            return _error("PROJECT_NOT_FOUND", f"Project '{association.project_id}' was not found.")
        catalog = build_capability_catalog(
            config_path=agent_config_path(association.agent_id, self.data_dir),
            project=project,
        )
        return _ok({"policy": _gm_science_session_policy_payload(association, catalog)})

    def update_gm_science_session_policy(
        self,
        session_id: str,
        body: dict[str, Any],
    ) -> dict[str, Any]:
        """Validate and replace mutable fields in one Project Session policy."""

        association = self._gm_science_store.get_project_session(session_id)
        if association is None:
            return _error(
                "SESSION_NOT_IN_PROJECT",
                f"Session '{session_id}' is not attached to a Project.",
            )
        project = self._gm_science_store.get_project(association.project_id)
        if project is None:
            return _error("PROJECT_NOT_FOUND", f"Project '{association.project_id}' was not found.")
        try:
            policy = update_session_policy(association.policy, body)
        except ValueError as exc:
            return _error("INVALID_REQUEST", str(exc))
        catalog = build_capability_catalog(
            config_path=agent_config_path(association.agent_id, self.data_dir),
            project=project,
        )
        issues = _session_policy_issues(policy, catalog)
        if issues:
            return _error("SESSION_POLICY_UNAVAILABLE", " ".join(issues))
        updated = self._gm_science_store.update_project_session_policy(session_id, policy)
        return _ok({"policy": _gm_science_session_policy_payload(updated, catalog)})

    def get_gm_science_settings(self) -> dict[str, Any]:
        """Return renderer-safe global settings for the gm-science agent."""

        return _ok({"settings": self._gm_science_settings.get_settings()})

    def update_gm_science_settings(self, body: dict[str, Any]) -> dict[str, Any]:
        """Persist global settings and return refreshed runtime projections."""

        project_id = str(body.get("project_id") or body.get("projectId") or "").strip()
        project = self._gm_science_store.get_project(project_id) if project_id else None
        if project_id and project is None:
            return _error("PROJECT_NOT_FOUND", f"Project '{project_id}' was not found.")
        settings_update = {
            key: value
            for key, value in body.items()
            if key not in {"project_id", "projectId"}
        }
        try:
            settings = self._gm_science_settings.update_settings(settings_update)
        except ValueError as exc:
            return _error("INVALID_REQUEST", str(exc))

        config_path = agent_config_path(GM_SCIENCE_DEFAULT_AGENT_NAME, self.data_dir)
        return _ok(
            {
                "settings": settings,
                "agent": build_agent_profile(GM_SCIENCE_DEFAULT_AGENT_NAME, self.data_dir),
                "project_id": project_id or None,
                "capabilities": build_capability_catalog(config_path=config_path, project=project),
            }
        )

    def check_gm_science_compute_target(self, body: dict[str, Any]) -> dict[str, Any]:
        """Run one explicit bounded Compute Target health check."""

        target_id = str(body.get("target_id") or body.get("targetId") or "").strip()
        if not target_id:
            return _error("INVALID_REQUEST", "Field 'target_id' is required.")
        try:
            health = self._gm_science_settings.check_compute_target(target_id)
        except ValueError as exc:
            return _error("COMPUTE_TARGET_NOT_FOUND", str(exc))
        return _ok({"health": health})

    def get_gm_science_storage(self) -> dict[str, Any]:
        """Return a bounded read-only snapshot of local gm-science storage."""

        return _ok({"storage": self._gm_science_observability.get_storage_snapshot()})

    def get_gm_science_usage(self, window: str = "7d") -> dict[str, Any]:
        """Return locally recorded model and TaskRun usage for one window."""

        try:
            usage = self._gm_science_observability.get_usage_snapshot(window)
        except ValueError as exc:
            return _error("INVALID_REQUEST", str(exc))
        return _ok({"usage": usage})

    def get_gm_science_memory(self, project_id: str, *, user_id: str) -> dict[str, Any]:
        """Return reviewable User and current-Project Memory state."""

        try:
            workspace = self._gm_science_memory.get_workspace(
                project_id=project_id,
                user_id=user_id,
            )
        except ValueError as exc:
            return _error("PROJECT_NOT_FOUND", str(exc))
        return _ok({"memory": workspace})

    def create_gm_science_memory_note(
        self,
        project_id: str,
        body: dict[str, Any],
    ) -> dict[str, Any]:
        """Create one explicitly approved User or Project Memory note."""

        try:
            note = self._gm_science_memory.create_note(
                project_id=project_id,
                user_id=str(body.get("user_id") or "ppx-client-user"),
                scope=str(body.get("scope") or ""),
                category=str(body.get("category") or ""),
                text=str(body.get("text") or ""),
            )
        except ValueError as exc:
            code = "PROJECT_NOT_FOUND" if self._gm_science_store.get_project(project_id) is None else "INVALID_REQUEST"
            return _error(code, str(exc))
        return _ok({"note": note})

    def update_gm_science_memory_note(
        self,
        project_id: str,
        note_id: str,
        body: dict[str, Any],
    ) -> dict[str, Any]:
        """Update one note visible in the current Memory workspace."""

        try:
            note = self._gm_science_memory.update_note(
                project_id=project_id,
                user_id=str(body.get("user_id") or "ppx-client-user"),
                note_id=note_id,
                category=str(body.get("category") or ""),
                text=str(body.get("text") or ""),
            )
        except ValueError as exc:
            code = "PROJECT_NOT_FOUND" if self._gm_science_store.get_project(project_id) is None else "MEMORY_NOTE_NOT_FOUND"
            return _error(code, str(exc))
        return _ok({"note": note})

    def delete_gm_science_memory_note(
        self,
        project_id: str,
        note_id: str,
        *,
        user_id: str,
    ) -> dict[str, Any]:
        """Delete one note visible in the current Memory workspace."""

        try:
            self._gm_science_memory.delete_note(
                project_id=project_id,
                user_id=user_id,
                note_id=note_id,
            )
        except ValueError as exc:
            code = "PROJECT_NOT_FOUND" if self._gm_science_store.get_project(project_id) is None else "MEMORY_NOTE_NOT_FOUND"
            return _error(code, str(exc))
        return _ok({"deleted": True, "note_id": note_id})

    def clear_gm_science_memory(
        self,
        project_id: str,
        *,
        user_id: str,
        scope: str,
    ) -> dict[str, Any]:
        """Clear approved notes from exactly one selected Memory scope."""

        try:
            deleted_count = self._gm_science_memory.clear_scope(
                project_id=project_id,
                user_id=user_id,
                scope=scope,
            )
        except ValueError as exc:
            code = "PROJECT_NOT_FOUND" if self._gm_science_store.get_project(project_id) is None else "INVALID_REQUEST"
            return _error(code, str(exc))
        return _ok({"deleted_count": deleted_count, "scope": scope})

    def review_gm_science_memory_candidate(
        self,
        project_id: str,
        candidate_id: str,
        body: dict[str, Any],
    ) -> dict[str, Any]:
        """Approve or reject one pending Memory candidate."""

        try:
            candidate = self._gm_science_memory.review_candidate(
                project_id=project_id,
                user_id=str(body.get("user_id") or "ppx-client-user"),
                candidate_id=candidate_id,
                decision=str(body.get("decision") or ""),
            )
        except ValueError as exc:
            code = "PROJECT_NOT_FOUND" if self._gm_science_store.get_project(project_id) is None else "INVALID_REQUEST"
            return _error(code, str(exc))
        return _ok({"candidate": candidate})

    def update_gm_science_project_capabilities(
        self,
        project_id: str,
        body: dict[str, Any],
    ) -> dict[str, Any]:
        """Validate and persist one Project's capability allowlists."""

        project = self._gm_science_store.get_project(project_id)
        if project is None:
            return _error("PROJECT_NOT_FOUND", f"Project '{project_id}' was not found.")
        config_path = agent_config_path(GM_SCIENCE_DEFAULT_AGENT_NAME, self.data_dir)
        catalog = build_capability_catalog(config_path=config_path, project=project)
        try:
            skills = _project_capability_values(body, "enabled_skills", "enabledSkills", tuple(project.enabled_skills))
            connectors = _project_capability_values(
                body,
                "enabled_connectors",
                "enabledConnectors",
                tuple(project.enabled_connectors),
            )
            specialists = _project_capability_values(
                body,
                "enabled_specialists",
                "enabledSpecialists",
                tuple(project.enabled_specialists),
            )
            enabled_skills = normalize_capability_selection(kind="skill", values=skills, catalog=catalog)
            enabled_connectors = normalize_capability_selection(
                kind="connector",
                values=connectors,
                catalog=catalog,
            )
            enabled_specialists = normalize_capability_selection(
                kind="specialist",
                values=specialists,
                catalog=catalog,
            )
            required_permissions: list[str] = []
            if set(enabled_skills).difference(project.enabled_skills):
                required_permissions.append("attach_skill")
            if set(project.enabled_skills).difference(enabled_skills):
                required_permissions.append("detach_skill")
            if set(enabled_connectors).difference(project.enabled_connectors):
                required_permissions.append("attach_connector")
            if set(project.enabled_connectors).difference(enabled_connectors):
                required_permissions.append("detach_connector")
            if set(enabled_specialists) != set(project.enabled_specialists):
                required_permissions.append("update_agent")
            self._gm_science_settings.require_permissions(required_permissions)
            updated = self._gm_science_store.update_project_capabilities(
                project_id,
                enabled_skills=enabled_skills,
                enabled_connectors=enabled_connectors,
                enabled_specialists=enabled_specialists,
            )
        except RegistryPermissionError as exc:
            return _error("PERMISSION_DENIED", str(exc))
        except ValueError as exc:
            return _error("INVALID_REQUEST", str(exc))
        updated_catalog = build_capability_catalog(config_path=config_path, project=updated)
        return _ok(
            {
                "project": _gm_science_project_payload(
                    updated,
                    sessions_count=self._gm_science_store.count_project_sessions(updated.id),
                    artifacts_count=len(self._gm_science_store.list_artifacts(updated.id)),
                ),
                "capabilities": updated_catalog,
            }
        )

    def list_gm_science_artifacts(self, project_id: str) -> dict[str, Any]:
        """Return artifacts attached to one gm-science project."""

        if self._gm_science_store.get_project(project_id) is None:
            return _error("PROJECT_NOT_FOUND", f"Project '{project_id}' was not found.")
        return _ok(
            {
                "items": [
                    _gm_science_artifact_payload(artifact)
                    for artifact in self._gm_science_store.list_artifacts(project_id)
                ]
            }
        )

    def create_gm_science_artifact(self, project_id: str, body: dict[str, Any]) -> dict[str, Any]:
        """Create one artifact attached to a gm-science project."""

        if self._gm_science_store.get_project(project_id) is None:
            return _error("PROJECT_NOT_FOUND", f"Project '{project_id}' was not found.")
        artifact_type = str(body.get("type") or body.get("artifact_type") or "").strip()
        if not artifact_type:
            return _error("INVALID_REQUEST", "Field 'type' is required.")
        metadata = body.get("metadata")
        provenance = body.get("provenance")
        try:
            artifact = self._gm_science_store.create_artifact(
                project_id=project_id,
                artifact_type=artifact_type,
                title=str(body.get("title") or ""),
                path_or_url=str(body.get("path_or_url") or body.get("pathOrUrl") or ""),
                mime_type=str(body.get("mime_type") or body.get("mimeType") or ""),
                session_id=str(body.get("session_id") or body.get("sessionId") or "") or None,
                metadata=metadata if isinstance(metadata, dict) else {},
                provenance=provenance if isinstance(provenance, dict) else {},
            )
        except ValueError as exc:
            return _error("INVALID_REQUEST", str(exc))
        return _ok({"artifact": _gm_science_artifact_payload(artifact)})

    def list_gm_science_resources(self, project_id: str, query: str = "") -> dict[str, Any]:
        """Return one Project's unified, path-safe resource catalog."""

        if self._gm_science_store.get_project(project_id) is None:
            return _error("PROJECT_NOT_FOUND", f"Project '{project_id}' was not found.")
        if not self._resource_catalog.config.enabled:
            return _error("RESOURCE_CATALOG_UNAVAILABLE", "Project resource catalog is disabled by configuration.")
        try:
            resources = self._resource_catalog.list_resources(project_id, query=query)
        except ValueError as exc:
            return _error("INVALID_REQUEST", str(exc))
        return _ok({"items": [resource.to_dict() for resource in resources]})

    def get_gm_science_resource_detail(self, project_id: str, resource_id: str) -> dict[str, Any]:
        """Return bounded preview and provenance for one Project resource."""

        if self._gm_science_store.get_project(project_id) is None:
            return _error("PROJECT_NOT_FOUND", f"Project '{project_id}' was not found.")
        if not self._resource_catalog.config.enabled:
            return _error("RESOURCE_CATALOG_UNAVAILABLE", "Project resource catalog is disabled by configuration.")
        try:
            detail = self._resource_detail.get_detail(project_id, resource_id)
        except LookupError as exc:
            return _error("RESOURCE_NOT_FOUND", str(exc))
        except ValueError as exc:
            return _error("INVALID_REQUEST", str(exc))
        return _ok({"detail": detail.to_dict()})

    def list_gm_science_datasets(self, project_id: str) -> dict[str, Any]:
        """Return imported datasets for one gm-science Project."""

        try:
            return _ok({"items": self._dataset_service.list_datasets(project_id)})
        except ValueError as exc:
            return _error("PROJECT_NOT_FOUND", str(exc))

    def get_gm_science_dataset(self, project_id: str, artifact_id: str) -> dict[str, Any]:
        """Return one imported dataset and its persisted profile."""

        try:
            return _ok({"dataset": self._dataset_service.get_dataset(project_id, artifact_id)})
        except ValueError as exc:
            return _error("DATASET_NOT_FOUND", str(exc))

    def import_gm_science_dataset(self, project_id: str, body: dict[str, Any]) -> dict[str, Any]:
        """Import one local file into a gm-science Project workspace."""

        source_path = str(body.get("source_path") or body.get("sourcePath") or "").strip()
        if not source_path:
            return _error("INVALID_REQUEST", "Field 'source_path' is required.")
        try:
            dataset = self._dataset_service.import_dataset(
                project_id=project_id,
                source_path=source_path,
                title=str(body.get("title") or ""),
                session_id=str(body.get("session_id") or body.get("sessionId") or "") or None,
            )
        except ValueError as exc:
            return _error("INVALID_REQUEST", str(exc))
        return _ok({"dataset": dataset})

    def list_gm_science_analyses(self, project_id: str) -> dict[str, Any]:
        """Return reviewable analyses for one gm-science Project."""

        try:
            return _ok({"items": self._analysis_service.list_analyses(project_id)})
        except ValueError as exc:
            return _error("PROJECT_NOT_FOUND", str(exc))
        except RuntimeError as exc:
            return _error("EXECUTION_UNAVAILABLE", str(exc))

    def get_gm_science_analysis(self, project_id: str, analysis_id: str) -> dict[str, Any]:
        """Return one analysis draft, derived run status, and output links."""

        try:
            return _ok({"analysis": self._analysis_service.get_analysis(project_id, analysis_id)})
        except ValueError as exc:
            return _error("ANALYSIS_NOT_FOUND", str(exc))
        except RuntimeError as exc:
            return _error("EXECUTION_UNAVAILABLE", str(exc))

    def create_gm_science_analysis(self, project_id: str, body: dict[str, Any]) -> dict[str, Any]:
        """Compile a natural-language objective into a reviewable analysis draft."""

        raw_dataset_ids = body.get("dataset_artifact_ids", body.get("datasetArtifactIds"))
        if not isinstance(raw_dataset_ids, list):
            return _error("INVALID_REQUEST", "Field 'dataset_artifact_ids' must be an array.")
        try:
            analysis = self._analysis_service.create_draft(
                project_id=project_id,
                session_id=str(body.get("session_id") or body.get("sessionId") or "") or None,
                title=str(body.get("title") or ""),
                objective=str(body.get("objective") or ""),
                dataset_artifact_ids=[str(value) for value in raw_dataset_ids],
            )
        except ValueError as exc:
            return _error("INVALID_REQUEST", str(exc))
        return _ok({"analysis": analysis})

    def run_gm_science_analysis(
        self,
        project_id: str,
        analysis_id: str,
        *,
        user_id: str = "ppx-client-user",
    ) -> dict[str, Any]:
        """Approve one persisted analysis draft and submit its TaskRun."""

        try:
            analysis = self._analysis_service.run_analysis(
                project_id,
                analysis_id,
                user_id=user_id,
            )
        except ValueError as exc:
            return _error("INVALID_REQUEST", str(exc))
        except RuntimeError as exc:
            return _error("EXECUTION_UNAVAILABLE", str(exc))
        return _ok({"analysis": analysis})

    def list_gm_science_runs(self, project_id: str) -> dict[str, Any]:
        """Return synchronized local execution runs for one gm-science Project."""

        try:
            return _ok({"items": self._science_execution.list_runs(project_id)})
        except ValueError as exc:
            return _error("PROJECT_NOT_FOUND", str(exc))
        except RuntimeError as exc:
            return _error("EXECUTION_UNAVAILABLE", str(exc))

    def get_gm_science_run(self, project_id: str, task_id: str) -> dict[str, Any]:
        """Return one synchronized local execution run."""

        try:
            return _ok({"run": self._science_execution.get_run(project_id, task_id)})
        except ValueError as exc:
            return _error("RUN_NOT_FOUND", str(exc))
        except RuntimeError as exc:
            return _error("EXECUTION_UNAVAILABLE", str(exc))

    def create_gm_science_python_run(self, project_id: str, body: dict[str, Any]) -> dict[str, Any]:
        """Submit one Project-scoped local Python TaskRun."""

        source = str(body.get("source") or "")
        if not source.strip():
            return _error("INVALID_REQUEST", "Field 'source' is required.")
        raw_input = body.get("input") if "input" in body else body.get("input_payload")
        if raw_input is not None and not isinstance(raw_input, dict):
            return _error("INVALID_REQUEST", "Field 'input' must be a JSON object.")
        try:
            run = self._science_execution.submit_python_run(
                project_id=project_id,
                session_id=str(body.get("session_id") or body.get("sessionId") or "") or None,
                title=str(body.get("title") or "Python run"),
                source=source,
                input_payload=raw_input if isinstance(raw_input, dict) else {},
                user_id=str(body.get("user_id") or "ppx-client-user"),
            )
        except ValueError as exc:
            return _error("INVALID_REQUEST", str(exc))
        except RuntimeError as exc:
            return _error("EXECUTION_UNAVAILABLE", str(exc))
        return _ok({"run": run})

    def cancel_gm_science_run(self, project_id: str, task_id: str) -> dict[str, Any]:
        """Cancel one active Project-scoped local execution run."""

        try:
            return _ok({"run": self._science_execution.cancel_run(project_id, task_id)})
        except ValueError as exc:
            return _error("RUN_NOT_FOUND", str(exc))
        except RuntimeError as exc:
            return _error("EXECUTION_UNAVAILABLE", str(exc))

    def retry_gm_science_run(
        self,
        project_id: str,
        task_id: str,
        *,
        user_id: str = "ppx-client-user",
    ) -> dict[str, Any]:
        """Create a new local execution run from one terminal run's saved intent."""

        try:
            run = self._science_execution.retry_run(
                project_id,
                task_id,
                user_id=user_id,
            )
            self._analysis_service.relink_retry(task_id, str(run["task_id"]))
            return _ok({"run": run})
        except ValueError as exc:
            return _error("INVALID_REQUEST", str(exc))
        except RuntimeError as exc:
            return _error("EXECUTION_UNAVAILABLE", str(exc))

    def create_gm_science_project_run(
        self,
        project_id: str,
        session_id: str,
        text: str,
        *,
        user_id: str = "ppx-client-user",
        agent_id: str = _GM_SCIENCE_DEFAULT_AGENT_ID,
        resource_refs: object | None = None,
    ) -> dict[str, Any]:
        """Create one run for a gm-science project using the default research agent."""

        project = self._gm_science_store.get_project(project_id)
        if project is None:
            return _error("PROJECT_NOT_FOUND", f"Project '{project_id}' was not found.")
        association = self._gm_science_store.get_project_session(session_id)
        if association is None or association.project_id != project.id:
            return _error(
                "SESSION_NOT_IN_PROJECT",
                f"Session '{session_id}' does not belong to Project '{project.id}'.",
            )
        if association.agent_id != agent_id:
            return _error(
                "SESSION_AGENT_MISMATCH",
                f"Session '{session_id}' belongs to agent '{association.agent_id}', not '{agent_id}'.",
            )
        try:
            resource_selections = self._resource_context.validate_selections(
                project.id,
                [] if resource_refs is None else resource_refs,
            )
        except ValueError as exc:
            return _error("INVALID_RESOURCE_REFS", str(exc))
        literature_config = load_literature_config(agent_config_path(agent_id, self.data_dir))
        source_selection = select_literature_sources(
            literature_config,
            enabled_connectors=project.enabled_connectors,
        )
        source_statuses = {
            name: (
                "disabled"
                if name in source_selection.project_disabled
                else str(status["status"])
            )
            for name, status in literature_config.public_source_statuses().items()
        }
        specialist_config = load_specialist_config(agent_config_path(agent_id, self.data_dir))
        specialist_statuses = {
            name: (
                "ok"
                if status["enabled"] and name in project.enabled_specialists
                else "disabled"
            )
            for name, status in specialist_config.public_statuses().items()
        }
        capability_catalog = build_capability_catalog(
            config_path=agent_config_path(agent_id, self.data_dir),
            project=project,
        )
        policy_issues = _session_policy_issues(association.policy, capability_catalog)
        if policy_issues:
            return _error("SESSION_POLICY_UNAVAILABLE", " ".join(policy_issues))
        routed_specialists = (
            {str(association.policy["specialist_id"])}
            if association.policy.get("specialist_id")
            else set(project.enabled_specialists)
            if association.policy.get("delegation_enabled")
            else set()
        )
        if association.policy.get("auto_review_enabled"):
            routed_specialists.add("research_reviewer")
        specialist_statuses = {
            name: status if name in routed_specialists else "disabled"
            for name, status in specialist_statuses.items()
        }
        enabled_mcp_servers = selected_mcp_server_names(
            project.enabled_connectors,
            capability_catalog,
        )
        message = _gm_science_project_context_message(
            project,
            text,
            session_id=session_id,
            source_statuses=source_statuses,
            specialist_statuses=specialist_statuses,
            session_policy=association.policy,
        )
        return self.create_run(
            agent_id,
            session_id,
            message,
            user_id=user_id,
            project_id=project.id,
            enabled_skills=list(project.enabled_skills),
            enabled_mcp_servers=enabled_mcp_servers,
            resource_refs=resource_selections,
            session_policy=association.policy,
        )

    def list_sessions(self, agent_id: str, *, user_id: str = "ppx-client-user") -> dict[str, Any]:
        """Return projected session summaries for one agent."""

        requester = self._ensure_requester_principal(user_id)
        config_path = agent_config_path(agent_id, self.data_dir)
        if not config_path.exists():
            return _error("AGENT_NOT_FOUND", f"Agent '{agent_id}' was not found.")
        cache_key = (agent_id, requester.principal_id)
        cached = self._read_cache(self._sessions_cache, cache_key)
        if cached is not None:
            _debug(
                "client_api.list_sessions.cache_hit",
                {
                    "agent_id": agent_id,
                    "user_id": requester.principal_id,
                    "count": len(cached),
                },
            )
            return _ok({"items": cached})
        visible = self._collect_visible_sessions(
            agent_id=agent_id,
            requester_principal_id=requester.principal_id,
        )
        if isinstance(visible, dict):
            return visible
        _decision, session_rows = visible
        items = []
        for subject_principal_id, session in session_rows:
            session_id = str(session.get("id") or "")
            if not session_id:
                continue
            self._session_agents[session_id] = agent_id
            self._session_owners[session_id] = subject_principal_id
            updated_raw = session.get("last_update_time")
            if isinstance(updated_raw, (int, float)):
                updated_at = dt.datetime.fromtimestamp(updated_raw, tz=dt.timezone.utc).astimezone().isoformat()
            else:
                updated_at = _iso_now()
            items.append(
                {
                    "id": session_id,
                    "agent_id": agent_id,
                    "project_id": (
                        association.project_id
                        if (association := self._gm_science_store.get_project_session(session_id)) is not None
                        else ""
                    ),
                    "subject_principal_id": subject_principal_id,
                    "title": str(session.get("title") or "").strip() or f"Session {session_id[:8]}",
                    "updated_at": updated_at,
                    "last_message_preview": str(session.get("last_preview") or "OpenPPX session"),
                    "archived": False,
                }
            )
        items.sort(key=lambda item: item["updated_at"], reverse=True)
        self._write_cache(self._sessions_cache, cache_key, items)
        return _ok({"items": items})

    def create_session(
        self,
        agent_id: str,
        *,
        user_id: str = "ppx-client-user",
        project_id: str = "",
    ) -> dict[str, Any]:
        """Create one session and optionally associate it with a gm-science Project."""

        requester = self._ensure_requester_principal(user_id)
        normalized_project_id = str(project_id or "").strip()
        if normalized_project_id and self._gm_science_store.get_project(normalized_project_id) is None:
            return _error("PROJECT_NOT_FOUND", f"Project '{normalized_project_id}' was not found.")
        config_path = self._ensure_agent_access_state(agent_id)
        if config_path is None:
            return _error("AGENT_NOT_FOUND", f"Agent '{agent_id}' was not found.")
        session_id = f"{agent_id}-{os.urandom(8).hex()}"
        try:
            session = self._create_session_direct(
                config_path,
                user_id=requester.principal_id,
                session_id=session_id,
            )
        except Exception as exc:
            _debug(
                "client_api.create_session.direct_failed",
                {
                    "agent_id": agent_id,
                    "session_id": session_id,
                    "error": str(exc),
                },
            )
            try:
                response = _run_worker_command(
                    config_path=config_path,
                    args=[
                        "create_session",
                        "--config-path",
                        str(config_path),
                        "--session-id",
                        session_id,
                        "--user-id",
                        requester.principal_id,
                    ],
                )
                session = response.get("session") if isinstance(response.get("session"), dict) else {}
            except Exception as fallback_exc:
                return _error("RUNTIME_UNAVAILABLE", str(fallback_exc))
        session_id = str(session.get("id") or session_id)
        if normalized_project_id:
            try:
                self._gm_science_store.link_project_session(
                    project_id=normalized_project_id,
                    session_id=session_id,
                    agent_id=agent_id,
                )
            except ValueError as exc:
                return _error("INVALID_REQUEST", str(exc))
        self._session_agents[session_id] = agent_id
        self._session_owners[session_id] = requester.principal_id
        self._invalidate_agent_cache(agent_id, user_id=requester.principal_id)
        self._invalidate_session_cache(session_id, user_id=requester.principal_id)
        updated_raw = session.get("last_update_time")
        if isinstance(updated_raw, (int, float)):
            updated_at = dt.datetime.fromtimestamp(updated_raw, tz=dt.timezone.utc).astimezone().isoformat()
        else:
            updated_at = _iso_now()
        return _ok(
            {
                "session": {
                    "id": session_id,
                    "agent_id": agent_id,
                    "project_id": normalized_project_id,
                    "subject_principal_id": requester.principal_id,
                    "title": "New session",
                    "updated_at": updated_at,
                    "last_message_preview": "",
                    "archived": False,
                }
            }
        )

    def get_session_messages(self, session_id: str, *, user_id: str = "ppx-client-user") -> dict[str, Any]:
        """Return projected message history for one session."""

        requester = self._ensure_requester_principal(user_id)
        cache_key = (session_id, requester.principal_id)
        cached = self._read_cache(self._messages_cache, cache_key)
        if cached is not None:
            _debug(
                "client_api.get_session.cache_hit",
                {
                    "session_id": session_id,
                    "user_id": requester.principal_id,
                    "count": len(cached),
                },
            )
            return _ok({"items": cached})
        location = self._find_session_owner(
            session_id=session_id,
            requester_principal_id=requester.principal_id,
        )
        if isinstance(location, dict):
            return location
        agent_id, subject_principal_id = location
        config_path = agent_config_path(agent_id, self.data_dir)
        try:
            session = self._get_session_for_principal(
                config_path,
                user_id=subject_principal_id,
                session_id=session_id,
            )
        except Exception as exc:
            return _error("RUNTIME_UNAVAILABLE", str(exc))
        if session is None:
            return _error("SESSION_NOT_FOUND", f"Session '{session_id}' was not found.")
        events = session.get("events") if isinstance(session.get("events"), list) else []
        messages = [
            message
            for event in events
            if isinstance(event, dict)
            for message in [project_session_event(event, session_id)]
            if message is not None
        ]
        for message in messages:
            metadata = message.setdefault("metadata", {})
            metadata["subject_principal_id"] = subject_principal_id
        self._write_cache(self._messages_cache, cache_key, messages)
        return _ok({"items": messages})

    def get_agent_access(self, agent_id: str, *, user_id: str = "ppx-client-user") -> dict[str, Any]:
        """Return the requester's visible access snapshot for one agent."""

        requester = self._ensure_requester_principal(user_id)
        if self._ensure_agent_access_state(agent_id) is None:
            return _error("AGENT_NOT_FOUND", f"Agent '{agent_id}' was not found.")
        decision = self._access_policy.decide_agent_scope(
            requester_principal_id=requester.principal_id,
            agent_id=agent_id,
            access_kind="agent_access_read",
        )
        if not decision.allow:
            self._record_admin_audit(
                agent_id=agent_id,
                requester=requester,
                action="read_access",
                relation_to_agent=decision.relation_to_agent,
                details={"allowed": False, "reason": decision.reason},
            )
            return _error(
                "ACCESS_DENIED",
                f"Principal '{requester.principal_id}' cannot read access state for agent '{agent_id}'.",
                {"reason": decision.reason},
            )

        record = self._agent_access_store.get_agent_record(agent_id)
        if record is None:
            return _error("RUNTIME_UNAVAILABLE", f"Agent '{agent_id}' access record is unavailable.")

        visible_principal_ids = set(decision.resolved_scope(self._identity_store.list_principal_ids()))
        memberships = []
        for membership in self._agent_access_store.list_memberships(agent_id=agent_id):
            if membership.principal_id not in visible_principal_ids and decision.scope_kind != "all":
                continue
            principal = self._identity_store.get_principal(membership.principal_id)
            memberships.append(
                {
                    "principal_id": membership.principal_id,
                    "relation": membership.relation,
                    "joined_at_ms": membership.joined_at_ms,
                    "metadata": dict(membership.metadata),
                    "display_name": principal.display_name if principal is not None else membership.principal_id,
                    "principal_type": principal.principal_type if principal is not None else "unknown",
                    "privilege_level": principal.privilege_level if principal is not None else "",
                }
            )

        owner_visible = bool(record.owner_principal_id) and decision.allows_principal(record.owner_principal_id)
        payload = _ok(
            {
                "agent": {
                    "id": record.agent_id,
                    "name": record.name,
                    "privilege_level": record.privilege_level,
                    "owner_principal_id": record.owner_principal_id if owner_visible else None,
                    "owner_configured": bool(record.owner_principal_id),
                    "status": record.status,
                    "config_ref": record.config_ref or None,
                    "metadata": dict(record.metadata),
                },
                "requester": {
                    "principal_id": requester.principal_id,
                    "relation": decision.relation_to_agent,
                    "reason": decision.reason,
                    "scope_kind": decision.scope_kind,
                    "capabilities": {
                        "can_manage_memberships": self._access_policy.decide_agent_management(
                            requester_principal_id=requester.principal_id,
                            agent_id=agent_id,
                            access_kind="membership_write",
                        ).allow,
                        "can_read_access_audit": self._access_policy.decide_agent_management(
                            requester_principal_id=requester.principal_id,
                            agent_id=agent_id,
                            access_kind="access_audit_read",
                        ).allow,
                        "can_read_admin_audit": self._access_policy.decide_agent_management(
                            requester_principal_id=requester.principal_id,
                            agent_id=agent_id,
                            access_kind="access_audit_read",
                        ).allow,
                        "can_change_owner": self._access_policy.decide_agent_management(
                            requester_principal_id=requester.principal_id,
                            agent_id=agent_id,
                            access_kind="ownership_write",
                        ).allow,
                    },
                },
                "memberships": memberships,
            }
        )
        self._record_admin_audit(
            agent_id=agent_id,
            requester=requester,
            action="read_access",
            relation_to_agent=decision.relation_to_agent,
            details={
                "allowed": True,
                "reason": decision.reason,
                "visible_membership_count": len(memberships),
                "owner_visible": owner_visible,
            },
        )
        return payload

    def set_agent_owner(
        self,
        agent_id: str,
        owner_principal_id: str,
        *,
        user_id: str = "ppx-client-user",
    ) -> dict[str, Any]:
        """Set one agent owner through the managed access layer."""

        requester = self._ensure_requester_principal(user_id)
        if self._ensure_agent_access_state(agent_id) is None:
            return _error("AGENT_NOT_FOUND", f"Agent '{agent_id}' was not found.")
        decision = self._access_policy.decide_agent_management(
            requester_principal_id=requester.principal_id,
            agent_id=agent_id,
            access_kind="ownership_write",
        )
        if not decision.allow:
            self._record_admin_audit(
                agent_id=agent_id,
                requester=requester,
                action="set_owner",
                relation_to_agent=decision.relation_to_agent,
                target_principal_id=str(owner_principal_id or "").strip(),
                details={"allowed": False, "reason": decision.reason, "source": "client_api"},
            )
            return _error(
                "ACCESS_DENIED",
                f"Principal '{requester.principal_id}' cannot change owner for agent '{agent_id}'.",
                {"reason": decision.reason},
            )

        normalized_owner_principal_id = str(owner_principal_id or "").strip()
        if not normalized_owner_principal_id:
            return _error("INVALID_REQUEST", "Field 'owner_principal_id' is required.")

        owner_principal = ensure_access_principal(
            self._identity_store,
            principal_id=normalized_owner_principal_id,
            source="client_api_access_mutation",
            account_kind="managed_access",
        )
        record = self._agent_access_store.get_agent_record(agent_id)
        if owner_principal is None or record is None:
            return _error("RUNTIME_UNAVAILABLE", f"Agent '{agent_id}' access record is unavailable.")
        previous_owner_principal_id = record.owner_principal_id

        updated = self._agent_access_store.upsert_agent_record(
            AgentRecord(
                agent_id=record.agent_id,
                name=record.name,
                privilege_level=record.privilege_level,
                owner_principal_id=owner_principal.principal_id,
                status=record.status,
                config_ref=record.config_ref,
                metadata={
                    **dict(record.metadata),
                    "owner_source": "client_api",
                },
            )
        )
        self._agent_access_store.record_audit(
            agent_id=agent_id,
            actor_principal_id=requester.principal_id,
            actor_relation=decision.relation_to_agent,
            action="set_owner",
            target_principal_id=owner_principal.principal_id,
            details={
                "allowed": True,
                "reason": decision.reason,
                "previous_owner_principal_id": previous_owner_principal_id,
                "owner_principal_id": owner_principal.principal_id,
                "changed": previous_owner_principal_id != owner_principal.principal_id,
                "source": "client_api",
            },
        )
        self._invalidate_agent_access_caches(agent_id)
        return _ok(
            {
                "agent": {
                    "id": updated.agent_id,
                    "owner_principal_id": updated.owner_principal_id,
                    "metadata": dict(updated.metadata),
                }
            }
        )

    def upsert_agent_membership(
        self,
        agent_id: str,
        principal_id: str,
        *,
        relation: str = "participant",
        user_id: str = "ppx-client-user",
    ) -> dict[str, Any]:
        """Create or update one agent membership through the managed access layer."""

        requester = self._ensure_requester_principal(user_id)
        _config_path, decision, denied = self._validate_membership_management(
            agent_id=agent_id,
            requester=requester,
            denied_action="upsert_membership",
            denied_target_principal_id=str(principal_id or "").strip(),
            denied_details={"source": "client_api", "relation": str(relation or "").strip().lower()},
        )
        if denied is not None:
            return denied

        normalized_principal_id = str(principal_id or "").strip()
        normalized_relation = str(relation or "").strip().lower()
        if not normalized_principal_id:
            return _error("INVALID_REQUEST", "Field 'principal_id' is required.")
        if normalized_relation != "participant":
            return _error("INVALID_REQUEST", "Field 'relation' must currently be 'participant'.")

        principal = ensure_access_principal(
            self._identity_store,
            principal_id=normalized_principal_id,
            source="client_api_access_mutation",
            account_kind="managed_access",
        )
        if principal is None:
            return _error("RUNTIME_UNAVAILABLE", "Could not ensure the target principal.")
        previous_membership = self._agent_access_store.get_membership(
            agent_id=agent_id,
            principal_id=principal.principal_id,
        )

        membership = self._agent_access_store.upsert_membership(
            AgentMembership(
                agent_id=agent_id,
                principal_id=principal.principal_id,
                relation=normalized_relation,
                metadata={"source": "client_api"},
            )
        )
        self._agent_access_store.record_audit(
            agent_id=agent_id,
            actor_principal_id=requester.principal_id,
            actor_relation=decision.relation_to_agent,
            action="upsert_membership",
            target_principal_id=membership.principal_id,
            details={
                "allowed": True,
                "reason": decision.reason,
                "relation": membership.relation,
                "previous_relation": previous_membership.relation if previous_membership is not None else None,
                "changed": previous_membership is None
                or previous_membership.relation != membership.relation
                or dict(previous_membership.metadata) != dict(membership.metadata),
                "joined_at_ms": membership.joined_at_ms,
                "source": "client_api",
            },
        )
        self._invalidate_agent_access_caches(agent_id)
        return _ok(
            {
                "membership": {
                    "agent_id": membership.agent_id,
                    "principal_id": membership.principal_id,
                    "relation": membership.relation,
                    "joined_at_ms": membership.joined_at_ms,
                    "metadata": dict(membership.metadata),
                }
            }
        )

    def delete_agent_membership(
        self,
        agent_id: str,
        principal_id: str,
        *,
        user_id: str = "ppx-client-user",
    ) -> dict[str, Any]:
        """Delete one agent membership through the managed access layer."""

        requester = self._ensure_requester_principal(user_id)
        _config_path, decision, denied = self._validate_membership_management(
            agent_id=agent_id,
            requester=requester,
            denied_action="delete_membership",
            denied_target_principal_id=str(principal_id or "").strip(),
            denied_details={"source": "client_api"},
        )
        if denied is not None:
            return denied

        normalized_principal_id = str(principal_id or "").strip()
        if not normalized_principal_id:
            return _error("INVALID_REQUEST", "Field 'principal_id' is required.")
        previous_membership = self._agent_access_store.get_membership(
            agent_id=agent_id,
            principal_id=normalized_principal_id,
        )

        deleted = self._agent_access_store.delete_membership(
            agent_id=agent_id,
            principal_id=normalized_principal_id,
        )
        self._agent_access_store.record_audit(
            agent_id=agent_id,
            actor_principal_id=requester.principal_id,
            actor_relation=decision.relation_to_agent,
            action="delete_membership",
            target_principal_id=normalized_principal_id,
            details={
                "allowed": True,
                "reason": decision.reason,
                "deleted": deleted,
                "previous_relation": previous_membership.relation if previous_membership is not None else None,
                "source": "client_api",
            },
        )
        self._invalidate_agent_access_caches(agent_id)
        return _ok({"deleted": deleted, "principal_id": normalized_principal_id})

    def batch_add_participants(
        self,
        agent_id: str,
        principal_ids: list[str] | tuple[str, ...],
        *,
        user_id: str = "ppx-client-user",
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """Add multiple participant memberships in one managed operation."""
        return self._batch_manage_participants(
            agent_id=agent_id,
            principal_ids=principal_ids,
            operation="add",
            user_id=user_id,
            dry_run=dry_run,
        )

    def batch_remove_participants(
        self,
        agent_id: str,
        principal_ids: list[str] | tuple[str, ...],
        *,
        user_id: str = "ppx-client-user",
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """Remove multiple participant memberships in one managed operation."""
        return self._batch_manage_participants(
            agent_id=agent_id,
            principal_ids=principal_ids,
            operation="remove",
            user_id=user_id,
            dry_run=dry_run,
        )

    def sync_participants(
        self,
        agent_id: str,
        principal_ids: list[str] | tuple[str, ...],
        *,
        user_id: str = "ppx-client-user",
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """Synchronize participant memberships to exactly the requested set."""
        return self._batch_manage_participants(
            agent_id=agent_id,
            principal_ids=principal_ids,
            operation="sync",
            user_id=user_id,
            dry_run=dry_run,
        )

    def _batch_manage_participants(
        self,
        *,
        agent_id: str,
        principal_ids: list[str] | tuple[str, ...],
        operation: str,
        user_id: str,
        dry_run: bool,
    ) -> dict[str, Any]:
        """Apply one batch participant management operation with one summary audit row."""
        requester = self._ensure_requester_principal(user_id)
        normalized_principal_ids = _normalize_principal_id_list(principal_ids)
        if not normalized_principal_ids:
            return _error("INVALID_REQUEST", "Field 'principal_ids' must contain at least one principal id.")

        action_name = {
            "add": "batch_add_participants",
            "remove": "batch_remove_participants",
            "sync": "sync_participants",
        }.get(operation, "")
        if not action_name:
            return _error("INVALID_REQUEST", f"Unsupported batch operation '{operation}'.")

        _config_path, decision, denied = self._validate_membership_management(
            agent_id=agent_id,
            requester=requester,
            denied_action=action_name,
            denied_details={
                "source": "client_api",
                "dry_run": bool(dry_run),
                "requested_principal_ids": normalized_principal_ids,
            },
        )
        if denied is not None:
            return denied

        current_memberships = self._agent_access_store.list_memberships(
            agent_id=agent_id,
            relations=("participant",),
        )
        current_ids = {membership.principal_id for membership in current_memberships}
        requested_ids = set(normalized_principal_ids)

        if operation == "add":
            added_ids = [principal_id for principal_id in normalized_principal_ids if principal_id not in current_ids]
            removed_ids: list[str] = []
            unchanged_ids = [principal_id for principal_id in normalized_principal_ids if principal_id in current_ids]
        elif operation == "remove":
            added_ids = []
            removed_ids = [principal_id for principal_id in normalized_principal_ids if principal_id in current_ids]
            unchanged_ids = [principal_id for principal_id in normalized_principal_ids if principal_id not in current_ids]
        else:
            added_ids = [principal_id for principal_id in normalized_principal_ids if principal_id not in current_ids]
            removed_ids = sorted(principal_id for principal_id in current_ids if principal_id not in requested_ids)
            unchanged_ids = [principal_id for principal_id in normalized_principal_ids if principal_id in current_ids]

        if not dry_run:
            for principal_id in added_ids:
                principal = ensure_access_principal(
                    self._identity_store,
                    principal_id=principal_id,
                    source="client_api_access_mutation",
                    account_kind="managed_access",
                )
                if principal is None:
                    return _error("RUNTIME_UNAVAILABLE", f"Could not ensure principal '{principal_id}'.")
                self._agent_access_store.upsert_membership(
                    AgentMembership(
                        agent_id=agent_id,
                        principal_id=principal.principal_id,
                        relation="participant",
                        metadata={"source": "client_api_batch"},
                    )
                )
            for principal_id in removed_ids:
                self._agent_access_store.delete_membership(agent_id=agent_id, principal_id=principal_id)
            if added_ids or removed_ids:
                self._invalidate_agent_access_caches(agent_id)

        audit_details = {
            "allowed": True,
            "reason": decision.reason,
            "source": "client_api",
            "dry_run": bool(dry_run),
            "applied": not dry_run,
            "requested_principal_ids": normalized_principal_ids,
            "added_principal_ids": added_ids,
            "removed_principal_ids": removed_ids,
            "unchanged_principal_ids": unchanged_ids,
            "requested_count": len(normalized_principal_ids),
            "added_count": len(added_ids),
            "removed_count": len(removed_ids),
            "unchanged_count": len(unchanged_ids),
        }
        self._record_admin_audit(
            agent_id=agent_id,
            requester=requester,
            action=action_name,
            relation_to_agent=decision.relation_to_agent,
            details=audit_details,
        )
        return _ok(
            {
                "operation": action_name,
                "dry_run": bool(dry_run),
                "applied": not dry_run,
                "requested_principal_ids": normalized_principal_ids,
                "added_principal_ids": added_ids,
                "removed_principal_ids": removed_ids,
                "unchanged_principal_ids": unchanged_ids,
                "summary": {
                    "requested_count": len(normalized_principal_ids),
                    "added_count": len(added_ids),
                    "removed_count": len(removed_ids),
                    "unchanged_count": len(unchanged_ids),
                },
            }
        )

    def create_run(
        self,
        agent_id: str,
        session_id: str,
        text: str,
        *,
        user_id: str = "ppx-client-user",
        project_id: str = "",
        enabled_skills: list[str] | None = None,
        enabled_mcp_servers: list[str] | None = None,
        resource_refs: list[ResourceSelection] | None = None,
        session_policy: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Create one streaming run and start consuming worker events in background."""

        requester = self._ensure_requester_principal(user_id)
        config_path = self._ensure_agent_access_state(agent_id)
        if config_path is None:
            return _error("AGENT_NOT_FOUND", f"Agent '{agent_id}' was not found.")
        location = self._find_session_owner(
            session_id=session_id,
            requester_principal_id=requester.principal_id,
        )
        if isinstance(location, dict):
            error_code = location.get("error", {}).get("code")
            if error_code == "SESSION_NOT_FOUND":
                located_agent_id = agent_id
                subject_principal_id = requester.principal_id
            else:
                return location
        else:
            located_agent_id, subject_principal_id = location
            if located_agent_id != agent_id:
                return _error("SESSION_NOT_FOUND", f"Session '{session_id}' was not found for agent '{agent_id}'.")
            if subject_principal_id != requester.principal_id:
                return _error(
                    "ACCESS_DENIED",
                    f"Principal '{requester.principal_id}' cannot start a run in session '{session_id}'.",
                    {"reason": "run_requires_session_owner"},
                )
        run_id = f"run_{os.urandom(8).hex()}"
        cmd = [
            sys.executable,
            "-m",
            "openppx.runtime.client_api_worker",
            "run",
            "--config-path",
            str(config_path),
            "--session-id",
            session_id,
            "--message",
            text,
            "--user-id",
            requester.principal_id,
        ]
        if project_id:
            cmd.extend(["--project-id", project_id])
        if enabled_skills is not None:
            cmd.extend(
                [
                    "--enabled-skills-json",
                    json.dumps(enabled_skills, ensure_ascii=False, separators=(",", ":")),
                ]
            )
        if enabled_mcp_servers is not None:
            cmd.extend(
                [
                    "--enabled-mcp-servers-json",
                    json.dumps(enabled_mcp_servers, ensure_ascii=False, separators=(",", ":")),
                ]
            )
        if resource_refs:
            if not project_id:
                return _error("INVALID_RESOURCE_REFS", "Project resources require a Project run.")
            cmd.extend(
                [
                    "--resource-refs-json",
                    json.dumps(
                        [selection.to_dict() for selection in resource_refs],
                        ensure_ascii=False,
                        separators=(",", ":"),
                    ),
                ]
            )
        if session_policy is not None:
            cmd.extend(
                [
                    "--session-policy-json",
                    json.dumps(
                        normalize_session_policy(session_policy),
                        ensure_ascii=False,
                        separators=(",", ":"),
                    ),
                ]
            )
        process = subprocess.Popen(
            cmd,
            cwd=str(config_path.parent),
            env=_worker_process_env(),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )
        handle = RunHandle(run_id=run_id, agent_id=agent_id, session_id=session_id, process=process)
        with self._lock:
            self._runs[run_id] = handle
        self._session_agents[session_id] = agent_id
        self._session_owners[session_id] = requester.principal_id
        self._invalidate_agent_cache(agent_id, user_id=requester.principal_id)
        self._invalidate_session_cache(session_id, user_id=requester.principal_id)
        _debug(
            "client_api.create_run",
            {
                "run_id": run_id,
                "agent_id": agent_id,
                "session_id": session_id,
                "user_id": requester.principal_id,
                "text_preview": text[:240] + ("..." if len(text) > 240 else ""),
                "worker_cmd": cmd,
            },
        )
        handle.publish(
            "run.started",
            {
                "run_id": run_id,
                "agent_id": agent_id,
                "session_id": session_id,
                "created_at": _iso_now(),
            },
        )
        handle.publish(
            "message.created",
            {
                "run_id": run_id,
                "agent_id": agent_id,
                "session_id": session_id,
                "message_id": handle.assistant_message_id,
                "message": _message_payload(
                    message_id=handle.assistant_message_id,
                    session_id=session_id,
                    role="assistant",
                    parts=[],
                    status="streaming",
                ),
            },
        )
        thread = threading.Thread(
            target=self._consume_run_process,
            args=(handle,),
            daemon=True,
        )
        thread.start()
        stderr_thread = threading.Thread(
            target=self._consume_run_stderr,
            args=(handle,),
            daemon=True,
        )
        stderr_thread.start()
        return _ok(
            {
                "run": {
                    "id": run_id,
                    "agent_id": agent_id,
                    "session_id": session_id,
                    "status": "running",
                    "events_url": f"/api/v1/runs/{run_id}/events",
                }
            }
        )

    def search_memory(self, agent_id: str, query: str, *, user_id: str = "ppx-client-user") -> dict[str, Any]:
        """Run one explicit memory query through the access-controlled query layer."""
        requester = self._ensure_requester_principal(user_id)
        if self._ensure_agent_access_state(agent_id) is None:
            return _error("AGENT_NOT_FOUND", f"Agent '{agent_id}' was not found.")
        try:
            result = asyncio.run(
                self._memory_query_service.search(
                    agent_id=agent_id,
                    requester_principal_id=requester.principal_id,
                    query=query,
                )
            )
        except Exception as exc:
            return _error("RUNTIME_UNAVAILABLE", str(exc))
        if not result.decision.allow:
            return _error(
                "ACCESS_DENIED",
                f"Principal '{requester.principal_id}' cannot query memory for agent '{agent_id}'.",
                {"reason": result.decision.reason},
            )
        return _ok(
            {
                "items": [
                    {
                        "id": memory.id,
                        "author": memory.author,
                        "timestamp": memory.timestamp,
                        "text": memory_entry_text(memory),
                        "subject_principal_id": memory.custom_metadata.get("subject_principal_id"),
                        "metadata": dict(memory.custom_metadata),
                    }
                    for memory in result.memories
                ]
            }
        )

    def get_memory_audit(
        self,
        agent_id: str,
        *,
        user_id: str = "ppx-client-user",
        limit: int = 50,
    ) -> dict[str, Any]:
        """Return visible explicit-memory audit rows for one requester and agent."""
        requester = self._ensure_requester_principal(user_id)
        if self._ensure_agent_access_state(agent_id) is None:
            return _error("AGENT_NOT_FOUND", f"Agent '{agent_id}' was not found.")
        try:
            result = self._memory_query_service.list_audit(
                agent_id=agent_id,
                requester_principal_id=requester.principal_id,
                limit=limit,
            )
        except Exception as exc:
            return _error("RUNTIME_UNAVAILABLE", str(exc))
        if not result.decision.allow:
            self._record_admin_audit(
                agent_id=agent_id,
                requester=requester,
                action="read_memory_audit",
                relation_to_agent=result.decision.relation_to_agent,
                details={"allowed": False, "reason": result.decision.reason, "limit": limit},
            )
            return _error(
                "ACCESS_DENIED",
                f"Principal '{requester.principal_id}' cannot read memory audit for agent '{agent_id}'.",
                {"reason": result.decision.reason},
            )
        payload = _ok(
            {
                "items": result.rows,
                "requester": {
                    "principal_id": requester.principal_id,
                    "relation": result.decision.relation_to_agent,
                    "reason": result.decision.reason,
                    "scope_kind": result.decision.scope_kind,
                },
            }
        )
        self._record_admin_audit(
            agent_id=agent_id,
            requester=requester,
            action="read_memory_audit",
            relation_to_agent=result.decision.relation_to_agent,
            details={
                "allowed": True,
                "reason": result.decision.reason,
                "limit": limit,
                "result_count": len(result.rows),
            },
        )
        return payload

    def get_access_audit(
        self,
        agent_id: str,
        *,
        user_id: str = "ppx-client-user",
        limit: int = 50,
        category: str = "all",
    ) -> dict[str, Any]:
        """Return visible admin-audit rows for one requester and agent."""
        requester = self._ensure_requester_principal(user_id)
        if self._ensure_agent_access_state(agent_id) is None:
            return _error("AGENT_NOT_FOUND", f"Agent '{agent_id}' was not found.")
        try:
            normalized_category = _normalize_access_audit_category(category)
        except ValueError as exc:
            return _error("INVALID_REQUEST", str(exc))
        decision = self._access_policy.decide_agent_management(
            requester_principal_id=requester.principal_id,
            agent_id=agent_id,
            access_kind="access_audit_read",
        )
        if not decision.allow:
            self._record_admin_audit(
                agent_id=agent_id,
                requester=requester,
                action="read_admin_audit",
                relation_to_agent=decision.relation_to_agent,
                details={
                    "allowed": False,
                    "reason": decision.reason,
                    "limit": limit,
                    "category": normalized_category,
                },
            )
            return _error(
                "ACCESS_DENIED",
                f"Principal '{requester.principal_id}' cannot read access audit for agent '{agent_id}'.",
                {"reason": decision.reason},
            )
        rows = self._agent_access_store.list_audit(
            agent_id=agent_id,
            limit=limit,
            actions=_actions_for_access_audit_category(normalized_category),
        )
        payload = _ok(
            {
                "items": [
                    {
                        "audit_id": row.audit_id,
                        "agent_id": row.agent_id,
                        "actor_principal_id": row.actor_principal_id,
                        "actor_relation": row.actor_relation,
                        "action": row.action,
                        "target_principal_id": row.target_principal_id,
                        "details": dict(row.details),
                        "created_at_ms": row.created_at_ms,
                    }
                    for row in rows
                ],
                "requester": {
                    "principal_id": requester.principal_id,
                    "relation": decision.relation_to_agent,
                    "reason": decision.reason,
                    "scope_kind": decision.scope_kind,
                },
                "category": normalized_category,
            }
        )
        self._record_admin_audit(
            agent_id=agent_id,
            requester=requester,
            action="read_admin_audit",
            relation_to_agent=decision.relation_to_agent,
            details={
                "allowed": True,
                "reason": decision.reason,
                "limit": limit,
                "category": normalized_category,
                "result_count": len(rows),
            },
        )
        return payload

    def _consume_run_stderr(self, handle: RunHandle) -> None:
        """Continuously collect worker stderr for debug visibility."""

        assert handle.process.stderr is not None
        for raw_line in handle.process.stderr:
            line = raw_line.strip()
            if not line:
                continue
            handle.append_stderr_line(line)
            _debug(
                "client_api.worker.stderr",
                {
                    "run_id": handle.run_id,
                    "line_preview": line[:400] + ("..." if len(line) > 400 else ""),
                },
            )

    def _consume_run_process(self, handle: RunHandle) -> None:
        """Translate worker NDJSON lines into replayable SSE events."""

        assert handle.process.stdout is not None
        final_text = ""

        def _publish_run_failure(error_message: str, *, code: str = "RUN_FAILED") -> None:
            handle.failed = True
            _debug(
                "client_api.message.failed",
                {
                    "run_id": handle.run_id,
                    "message": error_message,
                },
            )
            handle.publish(
                "message.failed",
                {
                    "run_id": handle.run_id,
                    "agent_id": handle.agent_id,
                    "session_id": handle.session_id,
                    "message_id": handle.assistant_message_id,
                    "status": "failed",
                    "error": _error_part_payload(code=code, text=error_message),
                },
            )
            handle.publish(
                "error",
                {
                    "run_id": handle.run_id,
                    "code": code,
                    "message": error_message,
                },
            )

        for line in handle.process.stdout:
            line = line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except Exception:
                _debug(
                    "client_api.worker.invalid_json",
                    {
                        "run_id": handle.run_id,
                        "line_preview": line[:320],
                    },
                )
                continue
            event_type = str(payload.get("type") or "")
            _debug(
                "client_api.worker.payload",
                {
                    "run_id": handle.run_id,
                    "event_type": event_type or "unknown",
                    "keys": sorted(payload.keys()),
                },
            )
            if event_type == "event":
                event = payload.get("event")
                if isinstance(event, dict):
                    content = event.get("content") if isinstance(event.get("content"), dict) else {}
                    raw_parts = content.get("parts") if isinstance(content, dict) and isinstance(content.get("parts"), list) else []
                    raw_long_running_ids = event.get("long_running_tool_ids") or []
                    long_running_ids = set(str(item) for item in raw_long_running_ids if item is not None)
                    for raw_part in raw_parts:
                        if not isinstance(raw_part, dict):
                            continue
                        function_call = raw_part.get("function_call")
                        if isinstance(function_call, dict):
                            step_id = str(function_call.get("id") or "step")
                            _debug(
                                "client_api.step.updated",
                                {
                                    "run_id": handle.run_id,
                                    "step_id": step_id,
                                    "title": str(function_call.get("name") or "tool"),
                                    "status": "running",
                                    "long_running": step_id in long_running_ids,
                                },
                            )
                            handle.publish(
                                "step.updated",
                                {
                                    "run_id": handle.run_id,
                                    "agent_id": handle.agent_id,
                                    "session_id": handle.session_id,
                                    "message_id": handle.assistant_message_id,
                                    "step": _step_ref_payload(
                                        step_id=step_id,
                                        title=str(function_call.get("name") or "tool"),
                                        status="running",
                                        detail=(
                                            "Background task is running.\n\n" + _preview_value(function_call.get("args"), "No tool arguments")
                                            if step_id in long_running_ids
                                            else _preview_value(function_call.get("args"), "No tool arguments")
                                        ),
                                    ),
                                },
                            )
                        function_response = raw_part.get("function_response")
                        if isinstance(function_response, dict):
                            _debug(
                                "client_api.step.updated",
                                {
                                    "run_id": handle.run_id,
                                    "step_id": str(function_response.get("id") or "step"),
                                    "title": str(function_response.get("name") or "tool"),
                                    "status": "completed",
                                },
                            )
                            handle.publish(
                                "step.updated",
                                {
                                    "run_id": handle.run_id,
                                    "agent_id": handle.agent_id,
                                    "session_id": handle.session_id,
                                    "message_id": handle.assistant_message_id,
                                    "step": _step_ref_payload(
                                        step_id=str(function_response.get("id") or "step"),
                                        title=str(function_response.get("name") or "tool"),
                                        status="completed",
                                        detail=_preview_value(function_response.get("response"), "Tool returned without a payload"),
                                    ),
                                },
                            )
            elif event_type == "delta":
                final_text = str(payload.get("text") or final_text)
                is_first_delta = handle.mark_first_delta()
                _debug(
                    "client_api.message.delta",
                    {
                        "run_id": handle.run_id,
                        "text_length": len(final_text),
                        "elapsed_ms": handle.elapsed_ms(),
                        "first_delta": is_first_delta,
                    },
                )
                handle.publish(
                    "message.delta",
                    {
                        "run_id": handle.run_id,
                        "agent_id": handle.agent_id,
                        "session_id": handle.session_id,
                        "message_id": handle.assistant_message_id,
                        "status": "streaming",
                        "part": {
                            "type": "markdown",
                            "text": final_text,
                        },
                    },
                )
            elif event_type == "final":
                final_text = str(payload.get("text") or final_text)
                if not final_text.strip():
                    _publish_run_failure(
                        "Worker finished without returning a final reply.",
                        code="RUN_EMPTY_FINAL",
                    )
                    continue
                _debug(
                    "client_api.message.completed",
                    {
                        "run_id": handle.run_id,
                        "text_length": len(final_text),
                        "elapsed_ms": handle.elapsed_ms(),
                    },
                )
                handle.publish(
                    "message.completed",
                    {
                        "run_id": handle.run_id,
                        "agent_id": handle.agent_id,
                        "session_id": handle.session_id,
                        "message_id": handle.assistant_message_id,
                        "status": "completed",
                        "message": _message_payload(
                            message_id=handle.assistant_message_id,
                            session_id=handle.session_id,
                            role="assistant",
                            parts=[{"type": "markdown", "text": final_text}],
                            status="completed",
                        ),
                    },
                )
            elif event_type == "error":
                error_message = str(payload.get("message") or "Unknown worker error")
                _publish_run_failure(error_message)
        exit_code = handle.process.wait()
        stderr_text = handle.stderr_text()
        _debug(
            "client_api.worker.exit",
            {
                "run_id": handle.run_id,
                "exit_code": exit_code,
                "failed": handle.failed,
                "elapsed_ms": handle.elapsed_ms(),
                "stderr_preview": stderr_text[:400] + ("..." if len(stderr_text) > 400 else ""),
            },
        )
        if exit_code != 0 and not handle.failed:
            _publish_run_failure(
                stderr_text or "worker exited unexpectedly",
                code="WORKER_EXIT_ERROR",
            )
        _debug(
            "client_api.run.finished",
            {
                "run_id": handle.run_id,
                "agent_id": handle.agent_id,
                "session_id": handle.session_id,
                "status": "failed" if handle.failed else "completed",
                "elapsed_ms": handle.elapsed_ms(),
            },
        )
        handle.publish(
            "run.finished",
            {
                "run_id": handle.run_id,
                "agent_id": handle.agent_id,
                "session_id": handle.session_id,
                "message_id": handle.assistant_message_id,
                "status": "failed" if handle.failed else "completed",
            },
        )
        handle.finish()

    def cancel_run(self, run_id: str) -> dict[str, Any]:
        """Cancel one active run."""

        handle = self._runs.get(run_id)
        if handle is None:
            return _error("RUN_NOT_FOUND", f"Run '{run_id}' was not found.")
        cancelled = handle.cancel()
        if not cancelled:
            return _error("RUN_ALREADY_FINISHED", f"Run '{run_id}' has already finished.")
        _debug("client_api.cancel_run", {"run_id": run_id})
        return _ok({"run": {"id": run_id, "status": "cancelled"}})

    def stream_run_events(self, run_id: str, *, last_event_id: str | None = None) -> queue.Queue[RunEnvelope | None] | None:
        """Return one subscriber queue for SSE streaming."""

        handle = self._runs.get(run_id)
        if handle is None:
            return None
        return handle.subscribe(last_event_id=last_event_id)


class _ClientApiHandler(BaseHTTPRequestHandler):
    """HTTP request handler bound to one coordinator instance."""

    server_version = "OpenPpxClientApi/0.1"

    @property
    def coordinator(self) -> ClientApiCoordinator:
        return self.server.coordinator  # type: ignore[attr-defined]

    def _send_json(self, status: int, payload: dict[str, Any]) -> None:
        body = _json_bytes(payload)
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_json_body(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0") or 0)
        if length <= 0:
            return {}
        raw = self.rfile.read(length)
        if not raw:
            return {}
        parsed = json.loads(raw.decode("utf-8"))
        if not isinstance(parsed, dict):
            raise ValueError("JSON request body must be an object.")
        return parsed

    def _read_json_body_or_error(self) -> dict[str, Any] | None:
        """Read one JSON object body or send a stable client error response."""

        try:
            return self._read_json_body()
        except (UnicodeDecodeError, ValueError):
            self._send_json(
                400,
                _error("INVALID_REQUEST", "Request body must contain a valid JSON object."),
            )
            return None

    def _parse(self) -> tuple[str, list[str], dict[str, str]]:
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path or "/"
        segments = [urllib.parse.unquote(segment) for segment in path.split("/") if segment]
        query = {key: values[-1] for key, values in urllib.parse.parse_qs(parsed.query).items() if values}
        return path, segments, query

    def do_GET(self) -> None:  # noqa: N802
        path, segments, query = self._parse()
        if path == "/api/v1/health":
            self._send_json(200, self.coordinator.health())
            return
        if path == "/api/v1/agents":
            self._send_json(200, self.coordinator.list_agents())
            return
        if path == "/api/v1/runtime/status":
            self._send_json(200, self.coordinator.runtime_status())
            return
        if segments == ["api", "v1", "gm-science", "capabilities"]:
            self._send_json(200, self.coordinator.list_gm_science_capabilities())
            return
        if segments == ["api", "v1", "gm-science", "settings"]:
            self._send_json(200, self.coordinator.get_gm_science_settings())
            return
        if segments == ["api", "v1", "gm-science", "storage"]:
            self._send_json(200, self.coordinator.get_gm_science_storage())
            return
        if segments == ["api", "v1", "gm-science", "usage"]:
            payload = self.coordinator.get_gm_science_usage(str(query.get("window") or "7d"))
            self._send_json(200 if payload.get("ok") else 400, payload)
            return
        if segments == ["api", "v1", "gm-science", "projects"]:
            self._send_json(200, self.coordinator.list_gm_science_projects())
            return
        if len(segments) == 5 and segments[:4] == ["api", "v1", "gm-science", "projects"]:
            payload = self.coordinator.get_gm_science_project(segments[4])
            self._send_json(200 if payload.get("ok") else 404, payload)
            return
        if (
            len(segments) == 6
            and segments[:4] == ["api", "v1", "gm-science", "projects"]
            and segments[5] == "memory"
        ):
            payload = self.coordinator.get_gm_science_memory(
                segments[4],
                user_id=str(query.get("user_id") or "ppx-client-user"),
            )
            self._send_json(200 if payload.get("ok") else 404, payload)
            return
        if (
            len(segments) == 6
            and segments[:4] == ["api", "v1", "gm-science", "projects"]
            and segments[5] == "artifacts"
        ):
            payload = self.coordinator.list_gm_science_artifacts(segments[4])
            self._send_json(200 if payload.get("ok") else 404, payload)
            return
        if (
            len(segments) == 6
            and segments[:4] == ["api", "v1", "gm-science", "projects"]
            and segments[5] == "resources"
        ):
            payload = self.coordinator.list_gm_science_resources(segments[4], query.get("q", ""))
            status = 200
            if not payload.get("ok"):
                code = payload.get("error", {}).get("code")
                status = 404 if code == "PROJECT_NOT_FOUND" else 503 if code == "RESOURCE_CATALOG_UNAVAILABLE" else 400
            self._send_json(status, payload)
            return
        if (
            len(segments) == 6
            and segments[:4] == ["api", "v1", "gm-science", "projects"]
            and segments[5] == "resource-detail"
        ):
            payload = self.coordinator.get_gm_science_resource_detail(
                segments[4],
                query.get("resource_id", ""),
            )
            status = 200
            if not payload.get("ok"):
                code = payload.get("error", {}).get("code")
                status = 404 if code in {"PROJECT_NOT_FOUND", "RESOURCE_NOT_FOUND"} else 503 if code == "RESOURCE_CATALOG_UNAVAILABLE" else 400
            self._send_json(status, payload)
            return
        if (
            len(segments) == 6
            and segments[:4] == ["api", "v1", "gm-science", "projects"]
            and segments[5] == "datasets"
        ):
            payload = self.coordinator.list_gm_science_datasets(segments[4])
            self._send_json(200 if payload.get("ok") else 404, payload)
            return
        if (
            len(segments) == 7
            and segments[:4] == ["api", "v1", "gm-science", "projects"]
            and segments[5] == "datasets"
        ):
            payload = self.coordinator.get_gm_science_dataset(segments[4], segments[6])
            self._send_json(200 if payload.get("ok") else 404, payload)
            return
        if (
            len(segments) == 6
            and segments[:4] == ["api", "v1", "gm-science", "projects"]
            and segments[5] == "analyses"
        ):
            payload = self.coordinator.list_gm_science_analyses(segments[4])
            status = 200 if payload.get("ok") else 404
            if not payload.get("ok") and payload.get("error", {}).get("code") == "EXECUTION_UNAVAILABLE":
                status = 503
            self._send_json(status, payload)
            return
        if (
            len(segments) == 7
            and segments[:4] == ["api", "v1", "gm-science", "projects"]
            and segments[5] == "analyses"
        ):
            payload = self.coordinator.get_gm_science_analysis(segments[4], segments[6])
            status = 200 if payload.get("ok") else 404
            if not payload.get("ok") and payload.get("error", {}).get("code") == "EXECUTION_UNAVAILABLE":
                status = 503
            self._send_json(status, payload)
            return
        if (
            len(segments) == 6
            and segments[:4] == ["api", "v1", "gm-science", "projects"]
            and segments[5] == "runs"
        ):
            payload = self.coordinator.list_gm_science_runs(segments[4])
            self._send_json(200 if payload.get("ok") else 404, payload)
            return
        if (
            len(segments) == 7
            and segments[:4] == ["api", "v1", "gm-science", "projects"]
            and segments[5] == "runs"
        ):
            payload = self.coordinator.get_gm_science_run(segments[4], segments[6])
            self._send_json(200 if payload.get("ok") else 404, payload)
            return
        if (
            len(segments) == 6
            and segments[:4] == ["api", "v1", "gm-science", "projects"]
            and segments[5] == "capabilities"
        ):
            payload = self.coordinator.list_gm_science_capabilities(segments[4])
            self._send_json(200 if payload.get("ok") else 404, payload)
            return
        if (
            len(segments) == 6
            and segments[:4] == ["api", "v1", "gm-science", "sessions"]
            and segments[5] == "policy"
        ):
            payload = self.coordinator.get_gm_science_session_policy(segments[4])
            self._send_json(200 if payload.get("ok") else 404, payload)
            return
        if len(segments) == 5 and segments[:3] == ["api", "v1", "agents"] and segments[4] == "sessions":
            user_id = str(query.get("user_id") or "ppx-client-user")
            payload = self.coordinator.list_sessions(segments[3], user_id=user_id)
            self._send_json(200 if payload.get("ok") else 404, payload)
            return
        if len(segments) == 5 and segments[:3] == ["api", "v1", "agents"] and segments[4] == "access":
            user_id = str(query.get("user_id") or "ppx-client-user")
            payload = self.coordinator.get_agent_access(segments[3], user_id=user_id)
            self._send_json(200 if payload.get("ok") else 404, payload)
            return
        if len(segments) == 6 and segments[:3] == ["api", "v1", "agents"] and segments[4] == "access" and segments[5] == "audit":
            user_id = str(query.get("user_id") or "ppx-client-user")
            raw_limit = str(query.get("limit") or "50").strip()
            category = str(query.get("category") or "all")
            try:
                limit = int(raw_limit)
            except ValueError:
                self._send_json(400, _error("INVALID_REQUEST", "Query parameter 'limit' must be an integer."))
                return
            payload = self.coordinator.get_access_audit(
                segments[3],
                user_id=user_id,
                limit=limit,
                category=category,
            )
            status = 200 if payload.get("ok") else 403
            if not payload.get("ok") and payload.get("error", {}).get("code") == "AGENT_NOT_FOUND":
                status = 404
            if not payload.get("ok") and payload.get("error", {}).get("code") == "INVALID_REQUEST":
                status = 400
            self._send_json(status, payload)
            return
        if len(segments) == 5 and segments[:3] == ["api", "v1", "sessions"] and segments[4] == "messages":
            user_id = str(query.get("user_id") or "ppx-client-user")
            payload = self.coordinator.get_session_messages(segments[3], user_id=user_id)
            self._send_json(200 if payload.get("ok") else 404, payload)
            return
        if len(segments) == 6 and segments[:3] == ["api", "v1", "agents"] and segments[4] == "memory" and segments[5] == "search":
            query_text = str(query.get("q") or "").strip()
            user_id = str(query.get("user_id") or "ppx-client-user")
            if not query_text:
                self._send_json(400, _error("INVALID_REQUEST", "Query parameter 'q' is required."))
                return
            payload = self.coordinator.search_memory(segments[3], query_text, user_id=user_id)
            self._send_json(200 if payload.get("ok") else 404, payload)
            return
        if len(segments) == 6 and segments[:3] == ["api", "v1", "agents"] and segments[4] == "memory" and segments[5] == "audit":
            user_id = str(query.get("user_id") or "ppx-client-user")
            raw_limit = str(query.get("limit") or "50").strip()
            try:
                limit = int(raw_limit)
            except ValueError:
                self._send_json(400, _error("INVALID_REQUEST", "Query parameter 'limit' must be an integer."))
                return
            payload = self.coordinator.get_memory_audit(segments[3], user_id=user_id, limit=limit)
            self._send_json(200 if payload.get("ok") else 404, payload)
            return
        if len(segments) == 5 and segments[:3] == ["api", "v1", "runs"] and segments[4] == "events":
            run_id = segments[3]
            subscriber = self.coordinator.stream_run_events(run_id, last_event_id=self.headers.get("Last-Event-ID"))
            if subscriber is None:
                self._send_json(404, _error("RUN_NOT_FOUND", f"Run '{run_id}' was not found."))
                return
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "close")
            self.end_headers()
            try:
                while True:
                    item = subscriber.get()
                    if item is None:
                        break
                    self.wfile.write(f"id: {item.event_id}\n".encode("utf-8"))
                    self.wfile.write(f"event: {item.event}\n".encode("utf-8"))
                    self.wfile.write(f"data: {json.dumps(item.payload, ensure_ascii=False)}\n\n".encode("utf-8"))
                    self.wfile.flush()
            finally:
                self.close_connection = True
            return
        self._send_json(404, _error("NOT_FOUND", f"Unknown path: {path}"))

    def do_PATCH(self) -> None:  # noqa: N802
        path, segments, _query = self._parse()
        body = self._read_json_body_or_error()
        if body is None:
            return
        if segments == ["api", "v1", "gm-science", "settings"]:
            payload = self.coordinator.update_gm_science_settings(body)
            status = 200 if payload.get("ok") else 400
            if not payload.get("ok") and payload.get("error", {}).get("code") == "PROJECT_NOT_FOUND":
                status = 404
            self._send_json(status, payload)
            return
        if (
            len(segments) == 8
            and segments[:4] == ["api", "v1", "gm-science", "projects"]
            and segments[5] == "memory"
            and segments[6] == "notes"
        ):
            payload = self.coordinator.update_gm_science_memory_note(
                segments[4],
                segments[7],
                body,
            )
            status = 200 if payload.get("ok") else 400
            if not payload.get("ok") and payload.get("error", {}).get("code") in {
                "PROJECT_NOT_FOUND",
                "MEMORY_NOTE_NOT_FOUND",
            }:
                status = 404
            self._send_json(status, payload)
            return
        if (
            len(segments) == 6
            and segments[:4] == ["api", "v1", "gm-science", "projects"]
            and segments[5] == "capabilities"
        ):
            payload = self.coordinator.update_gm_science_project_capabilities(segments[4], body)
            status = 200 if payload.get("ok") else 400
            if not payload.get("ok"):
                code = payload.get("error", {}).get("code")
                if code == "PROJECT_NOT_FOUND":
                    status = 404
                elif code == "PERMISSION_DENIED":
                    status = 403
            self._send_json(status, payload)
            return
        if (
            len(segments) == 6
            and segments[:4] == ["api", "v1", "gm-science", "sessions"]
            and segments[5] == "policy"
        ):
            payload = self.coordinator.update_gm_science_session_policy(segments[4], body)
            status = 200 if payload.get("ok") else 400
            if not payload.get("ok") and payload.get("error", {}).get("code") in {
                "SESSION_NOT_IN_PROJECT",
                "PROJECT_NOT_FOUND",
            }:
                status = 404
            self._send_json(status, payload)
            return
        self._send_json(404, _error("NOT_FOUND", f"Unknown path: {path}"))

    def do_POST(self) -> None:  # noqa: N802
        path, segments, _query = self._parse()
        body = self._read_json_body_or_error()
        if body is None:
            return
        if (
            len(segments) == 5
            and segments[:4] == ["api", "v1", "gm-science", "capabilities"]
            and segments[4] in {"skills", "connectors", "specialists"}
        ):
            payload = self.coordinator.create_gm_science_capability(segments[4], body)
            status = 200 if payload.get("ok") else 400
            if not payload.get("ok"):
                code = payload.get("error", {}).get("code")
                if code == "PERMISSION_DENIED":
                    status = 403
                elif code == "CAPABILITY_CONFLICT":
                    status = 409
            self._send_json(status, payload)
            return
        if segments == ["api", "v1", "gm-science", "projects"]:
            payload = self.coordinator.create_gm_science_project(body)
            status = 200 if payload.get("ok") else 400
            if not payload.get("ok") and payload.get("error", {}).get("code") == "PERMISSION_DENIED":
                status = 403
            self._send_json(status, payload)
            return
        if segments == ["api", "v1", "gm-science", "settings", "compute", "check"]:
            payload = self.coordinator.check_gm_science_compute_target(body)
            status = 200 if payload.get("ok") else 400
            if not payload.get("ok") and payload.get("error", {}).get("code") == "COMPUTE_TARGET_NOT_FOUND":
                status = 404
            self._send_json(status, payload)
            return
        if (
            len(segments) == 7
            and segments[:4] == ["api", "v1", "gm-science", "projects"]
            and segments[5:] == ["memory", "notes"]
        ):
            payload = self.coordinator.create_gm_science_memory_note(segments[4], body)
            status = 200 if payload.get("ok") else 400
            if not payload.get("ok") and payload.get("error", {}).get("code") == "PROJECT_NOT_FOUND":
                status = 404
            self._send_json(status, payload)
            return
        if (
            len(segments) == 9
            and segments[:4] == ["api", "v1", "gm-science", "projects"]
            and segments[5] == "memory"
            and segments[6] == "candidates"
            and segments[8] == "review"
        ):
            payload = self.coordinator.review_gm_science_memory_candidate(
                segments[4],
                segments[7],
                body,
            )
            status = 200 if payload.get("ok") else 400
            if not payload.get("ok") and payload.get("error", {}).get("code") == "PROJECT_NOT_FOUND":
                status = 404
            self._send_json(status, payload)
            return
        if (
            len(segments) == 6
            and segments[:4] == ["api", "v1", "gm-science", "projects"]
            and segments[5] == "artifacts"
        ):
            payload = self.coordinator.create_gm_science_artifact(segments[4], body)
            status = 200 if payload.get("ok") else 400
            if not payload.get("ok") and payload.get("error", {}).get("code") == "PROJECT_NOT_FOUND":
                status = 404
            self._send_json(status, payload)
            return
        if (
            len(segments) == 7
            and segments[:4] == ["api", "v1", "gm-science", "projects"]
            and segments[5] == "datasets"
            and segments[6] == "import"
        ):
            payload = self.coordinator.import_gm_science_dataset(segments[4], body)
            self._send_json(200 if payload.get("ok") else 400, payload)
            return
        if (
            len(segments) == 6
            and segments[:4] == ["api", "v1", "gm-science", "projects"]
            and segments[5] == "analyses"
        ):
            payload = self.coordinator.create_gm_science_analysis(segments[4], body)
            self._send_json(200 if payload.get("ok") else 400, payload)
            return
        if (
            len(segments) == 8
            and segments[:4] == ["api", "v1", "gm-science", "projects"]
            and segments[5] == "analyses"
            and segments[7] == "run"
        ):
            payload = self.coordinator.run_gm_science_analysis(
                segments[4],
                segments[6],
                user_id=str(body.get("user_id") or "ppx-client-user"),
            )
            status = 200 if payload.get("ok") else 400
            if not payload.get("ok") and payload.get("error", {}).get("code") == "EXECUTION_UNAVAILABLE":
                status = 503
            self._send_json(status, payload)
            return
        if (
            len(segments) == 6
            and segments[:4] == ["api", "v1", "gm-science", "projects"]
            and segments[5] == "runs"
        ):
            payload = self.coordinator.create_gm_science_python_run(segments[4], body)
            status = 200 if payload.get("ok") else 400
            if not payload.get("ok") and payload.get("error", {}).get("code") == "EXECUTION_UNAVAILABLE":
                status = 503
            self._send_json(status, payload)
            return
        if (
            len(segments) == 8
            and segments[:4] == ["api", "v1", "gm-science", "projects"]
            and segments[5] == "runs"
            and segments[7] in {"cancel", "retry"}
        ):
            if segments[7] == "cancel":
                payload = self.coordinator.cancel_gm_science_run(segments[4], segments[6])
            else:
                payload = self.coordinator.retry_gm_science_run(
                    segments[4],
                    segments[6],
                    user_id=str(body.get("user_id") or "ppx-client-user"),
                )
            status = 200 if payload.get("ok") else 400
            if not payload.get("ok") and payload.get("error", {}).get("code") == "RUN_NOT_FOUND":
                status = 404
            if not payload.get("ok") and payload.get("error", {}).get("code") == "EXECUTION_UNAVAILABLE":
                status = 503
            self._send_json(status, payload)
            return
        if (
            len(segments) == 8
            and segments[:4] == ["api", "v1", "gm-science", "projects"]
            and segments[5] == "sessions"
            and segments[7] == "runs"
        ):
            text = str(body.get("text") or "").strip()
            user_id = str(body.get("user_id") or "ppx-client-user")
            agent_id = str(body.get("agent_id") or _GM_SCIENCE_DEFAULT_AGENT_ID)
            if not text:
                self._send_json(400, _error("INVALID_REQUEST", "Field 'text' is required."))
                return
            payload = self.coordinator.create_gm_science_project_run(
                segments[4],
                segments[6],
                text,
                user_id=user_id,
                agent_id=agent_id,
                resource_refs=body.get("resource_refs", body.get("resourceRefs", [])),
            )
            self._send_json(_project_run_http_status(payload), payload)
            return
        if len(segments) == 6 and segments[:3] == ["api", "v1", "agents"] and segments[4] == "access" and segments[5] == "owner":
            user_id = str(body.get("user_id") or "ppx-client-user")
            owner_principal_id = str(body.get("owner_principal_id") or "").strip()
            if not owner_principal_id:
                self._send_json(400, _error("INVALID_REQUEST", "Field 'owner_principal_id' is required."))
                return
            payload = self.coordinator.set_agent_owner(segments[3], owner_principal_id, user_id=user_id)
            self._send_json(200 if payload.get("ok") else 403, payload)
            return
        if len(segments) == 6 and segments[:3] == ["api", "v1", "agents"] and segments[4] == "access" and segments[5] == "memberships":
            user_id = str(body.get("user_id") or "ppx-client-user")
            principal_id = str(body.get("principal_id") or "").strip()
            relation = str(body.get("relation") or "participant").strip()
            if not principal_id:
                self._send_json(400, _error("INVALID_REQUEST", "Field 'principal_id' is required."))
                return
            payload = self.coordinator.upsert_agent_membership(
                segments[3],
                principal_id,
                relation=relation,
                user_id=user_id,
            )
            self._send_json(200 if payload.get("ok") else 403, payload)
            return
        if len(segments) == 7 and segments[:3] == ["api", "v1", "agents"] and segments[4] == "access" and segments[5] == "memberships" and segments[6] == "batch":
            user_id = str(body.get("user_id") or "ppx-client-user")
            operation = str(body.get("operation") or "").strip().lower()
            dry_run = bool(body.get("dry_run"))
            raw_principal_ids = body.get("principal_ids")
            if not isinstance(raw_principal_ids, list):
                self._send_json(400, _error("INVALID_REQUEST", "Field 'principal_ids' must be a JSON array."))
                return
            principal_ids = [str(item or "") for item in raw_principal_ids]
            if operation == "add":
                payload = self.coordinator.batch_add_participants(
                    segments[3],
                    principal_ids,
                    user_id=user_id,
                    dry_run=dry_run,
                )
            elif operation == "remove":
                payload = self.coordinator.batch_remove_participants(
                    segments[3],
                    principal_ids,
                    user_id=user_id,
                    dry_run=dry_run,
                )
            elif operation == "sync":
                payload = self.coordinator.sync_participants(
                    segments[3],
                    principal_ids,
                    user_id=user_id,
                    dry_run=dry_run,
                )
            else:
                self._send_json(400, _error("INVALID_REQUEST", "Field 'operation' must be add, remove, or sync."))
                return
            status = 200 if payload.get("ok") else 403
            if not payload.get("ok") and payload.get("error", {}).get("code") == "AGENT_NOT_FOUND":
                status = 404
            if not payload.get("ok") and payload.get("error", {}).get("code") == "INVALID_REQUEST":
                status = 400
            self._send_json(status, payload)
            return
        if len(segments) == 5 and segments[:3] == ["api", "v1", "agents"] and segments[4] == "sessions":
            user_id = str(body.get("user_id") or "ppx-client-user")
            project_id = str(body.get("project_id") or body.get("projectId") or "")
            payload = self.coordinator.create_session(segments[3], user_id=user_id, project_id=project_id)
            status = 200 if payload.get("ok") else 404
            if not payload.get("ok") and payload.get("error", {}).get("code") == "INVALID_REQUEST":
                status = 400
            self._send_json(status, payload)
            return
        if len(segments) == 7 and segments[:3] == ["api", "v1", "agents"] and segments[4] == "sessions" and segments[6] == "runs":
            text = str(body.get("text") or "").strip()
            user_id = str(body.get("user_id") or "ppx-client-user")
            if not text:
                self._send_json(400, _error("INVALID_REQUEST", "Field 'text' is required."))
                return
            payload = self.coordinator.create_run(segments[3], segments[5], text, user_id=user_id)
            self._send_json(200 if payload.get("ok") else 404, payload)
            return
        if len(segments) == 5 and segments[:3] == ["api", "v1", "runs"] and segments[4] == "cancel":
            payload = self.coordinator.cancel_run(segments[3])
            self._send_json(200 if payload.get("ok") else 404, payload)
            return
        self._send_json(404, _error("NOT_FOUND", f"Unknown path: {path}"))

    def do_DELETE(self) -> None:  # noqa: N802
        path, segments, query = self._parse()
        if (
            len(segments) == 8
            and segments[:4] == ["api", "v1", "gm-science", "projects"]
            and segments[5] == "memory"
            and segments[6] == "notes"
        ):
            payload = self.coordinator.delete_gm_science_memory_note(
                segments[4],
                segments[7],
                user_id=str(query.get("user_id") or "ppx-client-user"),
            )
            status = 200 if payload.get("ok") else 400
            if not payload.get("ok") and payload.get("error", {}).get("code") in {
                "PROJECT_NOT_FOUND",
                "MEMORY_NOTE_NOT_FOUND",
            }:
                status = 404
            self._send_json(status, payload)
            return
        if (
            len(segments) == 6
            and segments[:4] == ["api", "v1", "gm-science", "projects"]
            and segments[5] == "memory"
        ):
            payload = self.coordinator.clear_gm_science_memory(
                segments[4],
                user_id=str(query.get("user_id") or "ppx-client-user"),
                scope=str(query.get("scope") or ""),
            )
            status = 200 if payload.get("ok") else 400
            if not payload.get("ok") and payload.get("error", {}).get("code") == "PROJECT_NOT_FOUND":
                status = 404
            self._send_json(status, payload)
            return
        if len(segments) == 7 and segments[:3] == ["api", "v1", "agents"] and segments[4] == "access" and segments[5] == "memberships":
            user_id = str(query.get("user_id") or "ppx-client-user")
            payload = self.coordinator.delete_agent_membership(
                segments[3],
                segments[6],
                user_id=user_id,
            )
            self._send_json(200 if payload.get("ok") else 403, payload)
            return
        self._send_json(404, _error("NOT_FOUND", f"Unknown path: {path}"))

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A003
        """Silence default stdlib access logs for cleaner CLI output."""


class ClientApiHttpServer(ThreadingHTTPServer):
    """Threading HTTP server bound to one `ClientApiCoordinator`."""

    def __init__(self, server_address: tuple[str, int], coordinator: ClientApiCoordinator) -> None:
        super().__init__(server_address, _ClientApiHandler)
        self.coordinator = coordinator


def serve_client_api(*, host: str = "127.0.0.1", port: int = 8876) -> None:
    """Start the local client API HTTP server."""

    coordinator = ClientApiCoordinator()
    server = ClientApiHttpServer((host, port), coordinator)
    print(f"openppx client-api listening on http://{host}:{port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
