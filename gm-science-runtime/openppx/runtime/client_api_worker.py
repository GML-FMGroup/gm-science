"""Per-agent worker helpers for the local client API service."""

from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from google.adk.agents.run_config import RunConfig

from openppx.gm_science.catalog import GM_SCIENCE_ENABLED_SKILLS_ENV
from openppx.gm_science.memory import GM_SCIENCE_PROJECT_ID_ENV
from openppx.gm_science.paths import get_gm_science_data_dir
from openppx.gm_science.resources import ResolvedResourceContext, ResourceCatalogService, ResourceContextService
from openppx.gm_science.session_policy import default_session_policy, normalize_session_policy, write_session_policy_env
from openppx.gm_science.specialists.config import load_specialist_config
from openppx.gm_science.store import GmScienceStore
from openppx.runtime.run_config import build_run_config


_MAX_SESSION_REFS = 8
_MAX_SESSION_CONTEXT_CHARS = 24_000
_MAX_SESSION_EVENTS = 12
_MAX_SKILL_REFS = 8
_MAX_SKILL_CONTEXT_CHARS = 40_000


@dataclass(frozen=True, slots=True)
class ReviewGateResult:
    """Outcome of one optional annotate-only report review."""

    status: str
    verdict: str = ""
    target_artifact_id: str = ""
    critique_artifact_id: str = ""
    message: str = ""


@dataclass(frozen=True, slots=True)
class ResolvedReferenceContext:
    """One bounded non-resource reference resolved for an ADK user Content."""

    text: str
    metadata_key: str
    metadata_value: dict[str, Any]

    def render_text(self) -> str:
        """Return the bounded context text supplied to the model."""

        return self.text

    def metadata(self) -> dict[str, Any]:
        """Return metadata used to reconstruct the visible reference chip."""

        return {self.metadata_key: self.metadata_value}


def _build_interactive_run_config(project_id: str) -> RunConfig:
    """Build the ADK-native streaming profile used by interactive client runs."""

    return build_run_config(
        profile="full",
        streaming=True,
        custom_metadata={
            "transport": "client_api",
            "project_id": project_id,
        },
    )


def _build_project_memory_service(
    *,
    project_id: str,
    session_id: str,
    data_dir: Path,
) -> Any | None:
    """Build the gm-science scoped ADK MemoryService for Project runs only."""

    normalized_project_id = str(project_id or "").strip()
    if not normalized_project_id:
        return None
    from openppx.gm_science.memory import ProjectScopedMemoryService
    from openppx.runtime.sqlite_memory_service import SQLiteMemoryService

    return ProjectScopedMemoryService(
        backend=SQLiteMemoryService(db_path=data_dir / "database" / "memory.db"),
        project_id=normalized_project_id,
        session_id=str(session_id or "").strip(),
    )


def _emit(payload: dict[str, Any]) -> None:
    """Write one NDJSON payload to stdout."""

    sys.stdout.write(json.dumps(payload, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Per-agent worker for openppx client API.")
    parser.add_argument("action", choices=["list_sessions", "get_session", "create_session", "run"])
    parser.add_argument("--config-path", required=True)
    parser.add_argument("--session-id", default="")
    parser.add_argument("--message", default="")
    parser.add_argument("--user-id", default="ppx-client-user")
    parser.add_argument("--project-id", default="")
    parser.add_argument("--enabled-skills-json", default=None)
    parser.add_argument("--enabled-mcp-servers-json", default=None)
    parser.add_argument("--resource-refs-json", default=None)
    parser.add_argument("--session-refs-json", default=None)
    parser.add_argument("--skill-refs-json", default=None)
    parser.add_argument("--session-policy-json", default=None)
    return parser.parse_args()


def _configure_session_policy_env(raw_policy: str | None) -> dict[str, Any]:
    """Validate and expose the Session policy before root Agent import."""

    if raw_policy is None:
        policy = default_session_policy()
    else:
        try:
            parsed = json.loads(raw_policy)
        except ValueError as exc:
            raise ValueError("--session-policy-json must contain valid JSON.") from exc
        if not isinstance(parsed, dict):
            raise ValueError("--session-policy-json must contain a JSON object.")
        policy = normalize_session_policy(parsed)
    write_session_policy_env(policy)
    return policy


def _restrict_mcp_servers_env(enabled_servers_json: str) -> None:
    """Restrict configured MCP servers to the explicit Project allowlist."""

    try:
        raw_enabled = json.loads(enabled_servers_json)
    except (TypeError, ValueError):
        raw_enabled = []
    enabled = {str(name) for name in raw_enabled} if isinstance(raw_enabled, list) else set()
    try:
        raw_servers = json.loads(os.getenv("OPENPPX_MCP_SERVERS_JSON", "{}"))
    except (TypeError, ValueError):
        raw_servers = {}
    if not isinstance(raw_servers, dict):
        raw_servers = {}
    filtered = {name: config for name, config in raw_servers.items() if str(name) in enabled}
    os.environ["OPENPPX_MCP_SERVERS_JSON"] = json.dumps(
        filtered,
        ensure_ascii=False,
        separators=(",", ":"),
    )


def _restrict_project_skills_env(enabled_skills_json: str) -> None:
    """Expose the explicit Project Skill selection to the ADK root Agent."""

    try:
        raw_enabled = json.loads(enabled_skills_json)
    except (TypeError, ValueError):
        raw_enabled = []
    enabled = []
    seen: set[str] = set()
    if isinstance(raw_enabled, list):
        for value in raw_enabled:
            name = str(value).strip()
            if not name or name.casefold() in seen:
                continue
            seen.add(name.casefold())
            enabled.append(name)
    os.environ[GM_SCIENCE_ENABLED_SKILLS_ENV] = json.dumps(
        enabled,
        ensure_ascii=False,
        separators=(",", ":"),
    )


async def run_report_review_gate(
    *,
    project_id: str,
    session_id: str,
    user_id: str,
    app_name: str,
    before_artifact_ids: set[str],
    reviewer_tool: Any,
) -> ReviewGateResult:
    """Review at most the latest unreviewed report created by the current run."""

    config = load_specialist_config()
    if (
        not config.enabled
        or not config.reviewer.enabled
        or config.reviewer.review_gate != "annotate"
    ):
        return ReviewGateResult(status="skipped")
    store = GmScienceStore()
    project = store.get_project(project_id)
    if project is None or "research_reviewer" not in project.enabled_specialists:
        return ReviewGateResult(status="skipped")

    artifacts = store.list_artifacts(project.id)
    reviewed_targets = {
        str(artifact.metadata.get("target_artifact_id") or "")
        for artifact in artifacts
        if artifact.type == "critique_report"
    }
    candidates = [
        artifact
        for artifact in artifacts
        if artifact.type == "report"
        and artifact.id not in before_artifact_ids
        and artifact.id not in reviewed_targets
        and artifact.session_id == session_id
    ]
    if not candidates:
        return ReviewGateResult(status="skipped")
    target = max(candidates, key=lambda artifact: (artifact.created_at, artifact.id))
    if reviewer_tool is None:
        return ReviewGateResult(
            status="failed",
            target_artifact_id=target.id,
            message="research_reviewer tool is unavailable",
        )

    invocation_context = SimpleNamespace(
        user_id=user_id,
        app_name=app_name,
        credential_service=None,
    )
    try:
        result = await reviewer_tool.run_async(
            args={
                "project_id": project.id,
                "session_id": session_id,
                "target_artifact_id": target.id,
                "review_focus": (
                    "Check evidence support, citation integrity, reasoning, and reproducibility."
                ),
                "trigger": "gate",
            },
            tool_context=SimpleNamespace(_invocation_context=invocation_context),
        )
    except Exception as exc:
        return ReviewGateResult(
            status="failed",
            target_artifact_id=target.id,
            message=str(exc),
        )
    output = result.get("output") if isinstance(result, dict) else None
    artifact = result.get("artifact") if isinstance(result, dict) else None
    verdict = str(output.get("verdict") or "") if isinstance(output, dict) else ""
    critique_id = str(artifact.get("id") or "") if isinstance(artifact, dict) else ""
    return ReviewGateResult(
        status="completed",
        verdict=verdict,
        target_artifact_id=target.id,
        critique_artifact_id=critique_id,
    )


def append_review_gate_note(text: str, gate: ReviewGateResult) -> str:
    """Append a non-blocking reviewer annotation to the main result."""

    if gate.status == "completed":
        note = f"Reviewer gate: {gate.verdict or 'completed'}."
        if gate.critique_artifact_id:
            note += f" Critique artifact: {gate.critique_artifact_id}."
        return f"{text.rstrip()}\n\n{note}".strip()
    if gate.status == "failed":
        return f"{text.rstrip()}\n\nReviewer gate: review could not be completed.".strip()
    return text


def _find_reviewer_tool(root_agent: Any) -> Any | None:
    """Return the configured research-reviewer AgentTool from the root agent."""

    return next(
        (tool for tool in getattr(root_agent, "tools", []) if getattr(tool, "name", "") == "research_reviewer"),
        None,
    )


def _reviewer_tool_for_policy(root_agent: Any, reviewer_model: str) -> Any | None:
    """Build the Reviewer with the Session-selected authoritative model route."""

    if reviewer_model in {"default", "subagent"}:
        existing = _find_reviewer_tool(root_agent)
        if existing is not None:
            return existing
    from openppx.gm_science.specialists.agents import build_specialist_tools

    model = None
    if reviewer_model == "main":
        from openppx.core.provider import build_adk_model_from_env

        model = build_adk_model_from_env()
    return _find_reviewer_tool(SimpleNamespace(tools=build_specialist_tools(model=model)))


def _event_preview_text(event: object) -> str:
    """Build a lightweight preview string from one ADK event object."""

    content = getattr(event, "content", None)
    parts = getattr(content, "parts", None) or []
    texts: list[str] = []
    for part in parts:
        if bool(getattr(part, "thought", False)):
            continue
        if _part_reference_metadata(part) is not None:
            continue
        text = getattr(part, "text", None)
        if isinstance(text, str) and text.strip():
            normalized_text = _strip_request_time_prefix(text)
            if normalized_text.strip():
                texts.append(normalized_text.strip())
    return " ".join(texts).strip()


def _part_resource_metadata(part: object) -> dict[str, Any] | None:
    """Return gm-science resource metadata from one ADK Part object."""

    raw_metadata = getattr(part, "part_metadata", None)
    if not isinstance(raw_metadata, dict):
        return None
    resource = raw_metadata.get("gm_science_resource")
    return resource if isinstance(resource, dict) and resource.get("id") else None


def _part_reference_metadata(part: object) -> dict[str, Any] | None:
    """Return any gm-science structured reference metadata from an ADK Part."""

    raw_metadata = getattr(part, "part_metadata", None)
    if not isinstance(raw_metadata, dict):
        return None
    for key in ("gm_science_resource", "gm_science_session_ref", "gm_science_skill_ref"):
        value = raw_metadata.get(key)
        if isinstance(value, dict) and value.get("id"):
            return value
    return None


def _build_adk_user_content(
    prompt: str,
    contexts: list[ResolvedResourceContext | ResolvedReferenceContext],
) -> Any:
    """Build one ADK-native user Content with structured reference Parts."""

    from google.genai import types

    parts = [types.Part.from_text(text=prompt)]
    parts.extend(
        types.Part(text=context.render_text(), part_metadata=context.metadata())
        for context in contexts
    )
    return types.UserContent(parts=parts)


def _resolve_resource_contexts(
    *,
    project_id: str,
    resource_refs_json: str | None,
    config_path: Path,
) -> list[ResolvedResourceContext]:
    """Revalidate compact resource references and read bounded local context."""

    if resource_refs_json is None:
        return []
    try:
        raw_refs = json.loads(resource_refs_json)
    except (TypeError, ValueError) as exc:
        raise ValueError("--resource-refs-json must contain valid JSON.") from exc
    if raw_refs and not project_id:
        raise ValueError("Project resource references require --project-id.")
    catalog = ResourceCatalogService(store=GmScienceStore(), config_path=config_path)
    return ResourceContextService(catalog=catalog).resolve_contexts(project_id, raw_refs)


def _parse_compact_reference_ids(
    raw_json: str | None,
    *,
    argument_name: str,
    limit: int,
) -> list[str]:
    """Parse a bounded JSON list containing stable IDs or compact ID objects."""

    if raw_json is None:
        return []
    try:
        raw_items = json.loads(raw_json)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{argument_name} must contain valid JSON.") from exc
    if not isinstance(raw_items, list):
        raise ValueError(f"{argument_name} must contain a JSON list.")
    if len(raw_items) > limit:
        raise ValueError(f"{argument_name} supports at most {limit} references.")
    resolved: list[str] = []
    for raw_item in raw_items:
        value = raw_item.get("id") if isinstance(raw_item, dict) else raw_item
        reference_id = str(value or "").strip()
        if not reference_id:
            raise ValueError(f"{argument_name} contains an empty reference ID.")
        if reference_id not in resolved:
            resolved.append(reference_id)
    return resolved


def _bounded_text(text: str, remaining: int) -> tuple[str, bool]:
    """Return text constrained to a shared character budget."""

    if remaining <= 0:
        return "", bool(text)
    if len(text) <= remaining:
        return text, False
    return text[:remaining].rstrip(), True


async def _resolve_session_contexts(
    *,
    project_id: str,
    current_session_id: str,
    session_refs_json: str | None,
    session_service: Any,
    app_name: str,
    user_id: str,
) -> list[ResolvedReferenceContext]:
    """Resolve Project Session references into a bounded visible transcript."""

    reference_ids = _parse_compact_reference_ids(
        session_refs_json,
        argument_name="--session-refs-json",
        limit=_MAX_SESSION_REFS,
    )
    if reference_ids and not project_id:
        raise ValueError("Project Session references require --project-id.")
    store = GmScienceStore()
    contexts: list[ResolvedReferenceContext] = []
    remaining = _MAX_SESSION_CONTEXT_CHARS
    for reference_id in reference_ids:
        if reference_id == current_session_id:
            raise ValueError("The current Session cannot reference itself.")
        association = store.get_project_session(reference_id)
        if association is None or association.project_id != project_id:
            raise ValueError(f"Session '{reference_id}' does not belong to Project '{project_id}'.")
        session = await session_service.get_session(
            app_name=app_name,
            user_id=user_id,
            session_id=reference_id,
        )
        if session is None:
            raise ValueError(f"Session '{reference_id}' is unavailable.")
        transcript: list[str] = []
        visible_events = list(getattr(session, "events", []) or [])[-_MAX_SESSION_EVENTS:]
        for event in visible_events:
            text = _event_preview_text(event)
            if not text:
                continue
            author = str(getattr(event, "author", "") or "").strip().lower()
            role = "User" if author == "user" else "Assistant"
            transcript.append(f"{role}: {text}")
        title = association.display_title or _session_title(list(getattr(session, "events", []) or [])) or "Session"
        body = f"Referenced Session: {title}\n" + ("\n".join(transcript) or "No visible messages.")
        bounded, truncated = _bounded_text(body, remaining)
        if not bounded:
            break
        remaining -= len(bounded)
        contexts.append(
            ResolvedReferenceContext(
                text=bounded,
                metadata_key="gm_science_session_ref",
                metadata_value={
                    "id": reference_id,
                    "display_name": title,
                    "truncated": truncated,
                },
            )
        )
    return contexts


def _resolve_skill_contexts(
    *,
    project_id: str,
    skill_refs_json: str | None,
) -> list[ResolvedReferenceContext]:
    """Resolve attached Skill references into bounded Skill instructions."""

    reference_ids = _parse_compact_reference_ids(
        skill_refs_json,
        argument_name="--skill-refs-json",
        limit=_MAX_SKILL_REFS,
    )
    if reference_ids and not project_id:
        raise ValueError("Project Skill references require --project-id.")
    from openppx.tooling.skills_adapter import get_registry

    store = GmScienceStore()
    project = store.get_project(project_id) if project_id else None
    enabled = set(project.enabled_skills if project is not None else [])
    registry = get_registry()
    available = {skill.name: skill for skill in registry.list_skills()}
    contexts: list[ResolvedReferenceContext] = []
    remaining = _MAX_SKILL_CONTEXT_CHARS
    for reference_id in reference_ids:
        if reference_id not in enabled or reference_id not in available:
            raise ValueError(f"Skill '{reference_id}' is not attached to Project '{project_id}'.")
        content = registry.read_skill(reference_id)
        bounded, truncated = _bounded_text(
            f"Referenced Skill: {reference_id}\n{content}",
            remaining,
        )
        if not bounded:
            break
        remaining -= len(bounded)
        contexts.append(
            ResolvedReferenceContext(
                text=bounded,
                metadata_key="gm_science_skill_ref",
                metadata_value={
                    "id": reference_id,
                    "display_name": reference_id,
                    "truncated": truncated,
                },
            )
        )
    return contexts


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


def _compact_session_title(text: str, *, limit: int = 64) -> str:
    """Return a single-line session title derived from user-visible text."""
    normalized = " ".join(str(text or "").split())
    if len(normalized) <= limit:
        return normalized
    return normalized[: max(0, limit - 3)].rstrip() + "..."


def _session_title(events: list[object]) -> str:
    """Return the first user message as the client-facing session title."""
    for event in events:
        if str(getattr(event, "author", "") or "").strip().lower() != "user":
            continue
        title = _compact_session_title(_visible_user_request(_event_preview_text(event)))
        if title:
            return title
    return ""


def _visible_user_request(text: str) -> str:
    """Remove gm-science machine context from a client-facing session title."""

    if "<gm_science_context>" not in text:
        return text
    marker = "\nUser request:\n"
    if marker not in text:
        return text
    return text.rsplit(marker, 1)[1].strip()


async def _run() -> int:
    args = _parse_args()
    config_path = Path(args.config_path).expanduser().resolve()
    if not config_path.exists():
        _emit({"type": "error", "message": f"config path not found: {config_path}"})
        return 1

    from openppx.core.config import bootstrap_env_from_config

    bootstrap_env_from_config(config_path)
    if args.enabled_skills_json is not None:
        _restrict_project_skills_env(args.enabled_skills_json)
    if args.enabled_mcp_servers_json is not None:
        _restrict_mcp_servers_env(args.enabled_mcp_servers_json)
    session_policy = _configure_session_policy_env(args.session_policy_json)
    os.environ[GM_SCIENCE_PROJECT_ID_ENV] = str(args.project_id or "")

    from openppx.app.agent import root_agent
    from openppx.runtime.adk_utils import run_text_async
    from openppx.runtime.message_time import inject_request_time
    from openppx.runtime.runner_factory import create_runner
    from openppx.runtime.session_service import create_session_service

    session_service = create_session_service()
    app_name = root_agent.name

    if args.action == "create_session":
        session = await session_service.create_session(
            app_name=app_name,
            user_id=args.user_id,
            session_id=args.session_id or None,
        )
        _emit(
            {
                "type": "session_created",
                "session": {
                    "id": session.id,
                    "app_name": session.app_name,
                    "user_id": session.user_id,
                    "last_update_time": session.last_update_time,
                },
            }
        )
        return 0

    if args.action == "list_sessions":
        response = await session_service.list_sessions(app_name=app_name, user_id=args.user_id)
        sessions: list[dict[str, Any]] = []
        for session in response.sessions:
            detail = await session_service.get_session(
                app_name=app_name,
                user_id=args.user_id,
                session_id=session.id,
            )
            events = list(detail.events if detail else [])
            sessions.append(
                {
                    "id": session.id,
                    "app_name": session.app_name,
                    "user_id": session.user_id,
                    "last_update_time": detail.last_update_time if detail else session.last_update_time,
                    "event_count": len(events),
                    "title": _session_title(events),
                    "last_preview": _event_preview_text(events[-1]) if events else "",
                }
            )
        _emit(
            {
                "type": "session_list",
                "sessions": sessions,
            }
        )
        return 0

    if args.action == "get_session":
        if not args.session_id:
            _emit({"type": "error", "message": "--session-id is required for get_session"})
            return 1
        session = await session_service.get_session(
            app_name=app_name,
            user_id=args.user_id,
            session_id=args.session_id,
        )
        if session is None:
            _emit({"type": "session_detail", "session": None})
            return 0
        _emit(
            {
                "type": "session_detail",
                "session": {
                    "id": session.id,
                    "app_name": session.app_name,
                    "user_id": session.user_id,
                    "last_update_time": session.last_update_time,
                    "events": [event.model_dump(mode="json") for event in session.events],
                },
            }
        )
        return 0

    if not args.session_id:
        _emit({"type": "error", "message": "--session-id is required for run"})
        return 1
    if not args.message:
        _emit({"type": "error", "message": "--message is required for run"})
        return 1

    prompt = inject_request_time(args.message, received_at=dt.datetime.now().astimezone())
    try:
        resource_contexts = _resolve_resource_contexts(
            project_id=args.project_id,
            resource_refs_json=args.resource_refs_json,
            config_path=config_path,
        )
        session_contexts = await _resolve_session_contexts(
            project_id=args.project_id,
            current_session_id=args.session_id,
            session_refs_json=args.session_refs_json,
            session_service=session_service,
            app_name=app_name,
            user_id=args.user_id,
        )
        skill_contexts = _resolve_skill_contexts(
            project_id=args.project_id,
            skill_refs_json=args.skill_refs_json,
        )
    except ValueError as exc:
        _emit({"type": "error", "message": str(exc)})
        return 1
    request = _build_adk_user_content(
        prompt,
        [*resource_contexts, *session_contexts, *skill_contexts],
    )
    memory_service = _build_project_memory_service(
        project_id=args.project_id,
        session_id=args.session_id,
        data_dir=get_gm_science_data_dir(),
    )
    runner_options: dict[str, Any] = {}
    if memory_service is not None:
        runner_options["memory_service"] = memory_service
    runner, _service = create_runner(
        agent=root_agent,
        app_name=app_name,
        session_service=session_service,
        **runner_options,
    )
    before_artifact_ids: set[str] = set()
    if args.project_id:
        before_artifact_ids = {
            artifact.id for artifact in GmScienceStore().list_artifacts(args.project_id)
        }

    def _emit_raw_event(event: Any) -> None:
        payload = event.model_dump(mode="json")
        _emit({"type": "event", "event": payload})

    def _emit_text_update(merged: str, _delta: str) -> None:
        _emit({"type": "delta", "text": merged})

    final_text = await run_text_async(
        runner,
        on_event=_emit_raw_event,
        on_text_update=_emit_text_update,
        user_id=args.user_id,
        session_id=args.session_id,
        new_message=request,
        run_config=_build_interactive_run_config(args.project_id),
    )

    if args.project_id and session_policy["auto_review_enabled"]:
        reviewer_tool = _reviewer_tool_for_policy(
            root_agent,
            session_policy["reviewer_model"],
        )
        gate = await run_report_review_gate(
            project_id=args.project_id,
            session_id=args.session_id,
            user_id=args.user_id,
            app_name=app_name,
            before_artifact_ids=before_artifact_ids,
            reviewer_tool=reviewer_tool,
        )
        final_text = append_review_gate_note(final_text, gate)

    _emit({"type": "final", "text": final_text})
    return 0


def main() -> int:
    """Run the worker entrypoint."""

    try:
        return asyncio.run(_run())
    except Exception as exc:  # pragma: no cover - defensive worker fallback
        _emit({"type": "error", "message": str(exc)})
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
