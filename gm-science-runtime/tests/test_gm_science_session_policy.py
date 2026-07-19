from __future__ import annotations

import json
import os

import pytest

from openppx.gm_science.session_policy import (
    GM_SCIENCE_SESSION_POLICY_ENV,
    default_session_policy,
    normalize_session_policy,
    session_policy_from_env,
    update_session_policy,
    write_session_policy_env,
)


def test_session_policy_defaults_match_product_menu() -> None:
    assert default_session_policy() == {
        "delegation_enabled": False,
        "auto_review_enabled": False,
        "memory_enabled": False,
        "specialist_id": "",
        "reviewer_model": "default",
        "compute_target": "local",
    }


def test_session_policy_partial_update_preserves_other_fields() -> None:
    updated = update_session_policy(
        default_session_policy(),
        {"delegation_enabled": True, "specialist_id": "paper_reader"},
    )

    assert updated["delegation_enabled"] is True
    assert updated["specialist_id"] == "paper_reader"
    assert updated["memory_enabled"] is False


@pytest.mark.parametrize("reviewer_model", ["default", "main", "subagent"])
def test_session_policy_accepts_supported_reviewer_routes(reviewer_model: str) -> None:
    assert normalize_session_policy({"reviewer_model": reviewer_model})["reviewer_model"] == reviewer_model


@pytest.mark.parametrize(
    ("value", "message"),
    [
        ({"delegation_enabled": "yes"}, "must be a boolean"),
        ({"reviewer_model": "other"}, "must be default, main, or subagent"),
        ({"compute_target": "ssh"}, "only 'local'"),
        ({"unknown": True}, "Unknown Session policy fields"),
    ],
)
def test_session_policy_rejects_unsupported_values(value: dict[str, object], message: str) -> None:
    with pytest.raises(ValueError, match=message):
        normalize_session_policy(value)


def test_session_policy_environment_round_trip(monkeypatch) -> None:
    policy = update_session_policy(default_session_policy(), {"memory_enabled": True})

    write_session_policy_env(policy)

    assert session_policy_from_env() == policy
    assert json.loads(os.environ[GM_SCIENCE_SESSION_POLICY_ENV]) == policy


def test_invalid_session_policy_environment_falls_back(monkeypatch) -> None:
    monkeypatch.setenv(GM_SCIENCE_SESSION_POLICY_ENV, "not-json")

    assert session_policy_from_env() == default_session_policy()
