"""Validated per-Session policy for the gm-science ADK runtime."""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from typing import Any

GM_SCIENCE_SESSION_POLICY_ENV = "GM_SCIENCE_SESSION_POLICY_JSON"

_DEFAULT_POLICY: dict[str, Any] = {
    "delegation_enabled": False,
    "auto_review_enabled": False,
    "memory_enabled": False,
    "specialist_id": "",
    "reviewer_model": "default",
    "compute_target": "local",
}
_MUTABLE_FIELDS = frozenset(_DEFAULT_POLICY)


def default_session_policy() -> dict[str, Any]:
    """Return a fresh product-default Session policy."""

    return dict(_DEFAULT_POLICY)


def normalize_session_policy(value: Mapping[str, Any] | None) -> dict[str, Any]:
    """Return one complete Session policy or raise on invalid values."""

    raw = value or {}
    unknown = sorted(set(raw).difference(_MUTABLE_FIELDS))
    if unknown:
        raise ValueError(f"Unknown Session policy fields: {', '.join(unknown)}.")
    policy = default_session_policy()
    policy.update(raw)
    for field in ("delegation_enabled", "auto_review_enabled", "memory_enabled"):
        if not isinstance(policy[field], bool):
            raise ValueError(f"Session policy field '{field}' must be a boolean.")
    specialist_id = str(policy["specialist_id"] or "").strip()
    reviewer_model = str(policy["reviewer_model"] or "").strip().lower()
    compute_target = str(policy["compute_target"] or "").strip().lower()
    if reviewer_model != "default":
        raise ValueError("Session reviewer_model currently supports only 'default'.")
    if compute_target != "local":
        raise ValueError("Session compute_target currently supports only 'local'.")
    policy["specialist_id"] = specialist_id
    policy["reviewer_model"] = reviewer_model
    policy["compute_target"] = compute_target
    return policy


def update_session_policy(
    current: Mapping[str, Any] | None,
    patch: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Apply a partial validated update to one complete Session policy."""

    if not isinstance(patch, Mapping):
        raise ValueError("Session policy update must be a JSON object.")
    unknown = sorted(set(patch).difference(_MUTABLE_FIELDS))
    if unknown:
        raise ValueError(f"Unknown Session policy fields: {', '.join(unknown)}.")
    merged = normalize_session_policy(current)
    merged.update(patch)
    return normalize_session_policy(merged)


def session_policy_from_env() -> dict[str, Any]:
    """Load the worker Session policy from its bounded JSON environment value."""

    raw = os.getenv(GM_SCIENCE_SESSION_POLICY_ENV, "").strip()
    if not raw:
        return default_session_policy()
    try:
        parsed = json.loads(raw)
    except ValueError:
        return default_session_policy()
    if not isinstance(parsed, dict):
        return default_session_policy()
    try:
        return normalize_session_policy(parsed)
    except ValueError:
        return default_session_policy()


def write_session_policy_env(policy: Mapping[str, Any]) -> None:
    """Expose one validated Session policy before importing the ADK root Agent."""

    os.environ[GM_SCIENCE_SESSION_POLICY_ENV] = json.dumps(
        normalize_session_policy(policy),
        ensure_ascii=False,
        separators=(",", ":"),
    )
