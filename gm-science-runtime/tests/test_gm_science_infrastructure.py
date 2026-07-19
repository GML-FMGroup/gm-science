"""Contracts for gm-science permission, network, and Compute governance."""

from __future__ import annotations

import json

import pytest

from openppx.core.config import config_to_env, default_config
from openppx.gm_science.infrastructure import (
    RegistryPermissionError,
    apply_infrastructure_update,
    check_compute_target,
    filter_mcp_servers_by_network,
    network_policy_from_env,
    package_environment,
    parse_network_policy,
    public_infrastructure_settings,
    require_registry_permissions,
)


def test_default_infrastructure_matches_trusted_local_product_contract() -> None:
    payload = public_infrastructure_settings(default_config(), environ={})

    assert payload["permissions"]["items"]
    assert all(item["granted"] is True for item in payload["permissions"]["items"])
    assert payload["network"]["enabled"] is True
    assert payload["network"]["enforce_allowlist"] is True
    local = next(item for item in payload["compute"]["targets"] if item["id"] == "local")
    assert local["type"] == "local"
    assert local["executable"] is True
    assert local["status"] == "ready"


def test_registry_permissions_are_durable_and_deny_revoked_mutations() -> None:
    config = default_config()
    apply_infrastructure_update(
        config,
        {"permission_grants": {"attach_skill": False, "detach_connector": False}},
        now="2026-07-19T01:02:03+00:00",
    )

    with pytest.raises(RegistryPermissionError, match="Attach skill"):
        require_registry_permissions(config, ["attach_skill"])
    require_registry_permissions(config, ["detach_skill"])

    payload = public_infrastructure_settings(config, environ={})
    by_id = {item["id"]: item for item in payload["permissions"]["items"]}
    assert by_id["attach_skill"] == {
        "id": "attach_skill",
        "name": "Attach skill",
        "description": "Attach a Skill to a Project.",
        "category": "registry_writes",
        "granted": False,
        "scope": "global",
        "source": "user",
        "updated_at": "2026-07-19T01:02:03+00:00",
    }


@pytest.mark.parametrize(
    ("url", "allowed"),
    [
        ("https://api.openalex.org/works", True),
        ("https://sub.example.org/data", True),
        ("https://example.net/data", False),
        ("http://localhost:8000/v1", False),
    ],
)
def test_network_policy_enforces_categories_wildcards_and_private_hosts(url: str, allowed: bool) -> None:
    config = default_config()
    apply_infrastructure_update(
        config,
        {
            "network": {
                "custom_domains": ["*.example.org"],
                "allow_private_networks": False,
            }
        },
    )

    decision = parse_network_policy(config).evaluate_url(url, purpose="test")
    assert decision.allowed is allowed


def test_disabled_network_category_blocks_native_literature_endpoint() -> None:
    config = default_config()
    apply_infrastructure_update(
        config,
        {"network": {"category_enabled": {"research_data": False}}},
    )

    decision = parse_network_policy(config).evaluate_url(
        "https://api.openalex.org/works",
        purpose="openalex",
    )

    assert decision.allowed is False
    assert "network policy" in decision.reason.lower()


def test_remote_mcp_servers_are_filtered_by_network_policy_without_affecting_stdio() -> None:
    config = default_config()
    policy = parse_network_policy(config)
    servers = {
        "local": {"command": "python", "args": ["server.py"]},
        "allowed": {"url": "https://api.openalex.org/mcp"},
        "blocked": {"url": "https://blocked.example.net/mcp"},
    }

    filtered, blocked = filter_mcp_servers_by_network(servers, policy=policy)

    assert set(filtered) == {"local", "allowed"}
    assert blocked == {"blocked": "Domain 'blocked.example.net' is not enabled by Network policy."}


def test_compute_targets_are_validated_and_redacted_in_public_projection() -> None:
    config = default_config()
    apply_infrastructure_update(
        config,
        {
            "compute_target": {
                "operation": "upsert",
                "target": {
                    "id": "lab_ssh",
                    "type": "ssh",
                    "name": "Lab cluster",
                    "enabled": True,
                    "host": "cluster.example.org",
                    "port": 22,
                    "username": "researcher",
                    "identity_file": "/Users/example/.ssh/id_ed25519",
                },
            }
        },
    )
    apply_infrastructure_update(
        config,
        {
            "compute_target": {
                "operation": "upsert",
                "target": {
                    "id": "nim_endpoint",
                    "type": "model_endpoint",
                    "name": "NIM endpoint",
                    "enabled": True,
                    "url": "https://user:password@nim.example.org/v1?token=secret",
                    "health_path": "/health",
                    "api_key": {"operation": "replace", "value": "endpoint-secret"},
                },
            }
        },
    )

    payload = public_infrastructure_settings(config, environ={})
    targets = {item["id"]: item for item in payload["compute"]["targets"]}
    assert targets["lab_ssh"]["metadata"] == {
        "host": "cluster.example.org",
        "port": 22,
        "username": "researcher",
        "identity_configured": True,
    }
    assert targets["nim_endpoint"]["metadata"] == {
        "url": "https://nim.example.org/v1",
        "health_path": "/health",
        "api_key_configured": True,
    }
    serialized = json.dumps(payload)
    assert "id_ed25519" not in serialized
    assert "endpoint-secret" not in serialized
    assert "password" not in serialized
    assert "token=secret" not in serialized


def test_package_environment_projects_configured_mirrors_and_ca_bundle() -> None:
    config = default_config()
    apply_infrastructure_update(
        config,
        {
            "network": {
                "conda_channel_mirror": "https://packages.example.org/conda",
                "python_package_index": "https://packages.example.org/pypi/simple",
                "ca_bundle_path": "/opt/example/ca-bundle.pem",
                "custom_domains": ["packages.example.org"],
            }
        },
    )

    assert package_environment(config) == {
        "CONDA_CHANNEL_ALIAS": "https://packages.example.org/conda",
        "PIP_INDEX_URL": "https://packages.example.org/pypi/simple",
        "PIP_CERT": "/opt/example/ca-bundle.pem",
        "REQUESTS_CA_BUNDLE": "/opt/example/ca-bundle.pem",
        "SSL_CERT_FILE": "/opt/example/ca-bundle.pem",
    }
    assert parse_network_policy(config).evaluate_url(
        "https://packages.example.org/pypi/simple",
        purpose="package mirror",
    ).allowed is True


def test_package_mirror_urls_never_expose_or_forward_embedded_credentials() -> None:
    config = default_config()
    apply_infrastructure_update(
        config,
        {
            "network": {
                "conda_channel_mirror": "https://user:password@packages.example.org/conda?token=secret#fragment",
                "python_package_index": "https://token@packages.example.org/pypi/simple?key=secret",
            }
        },
    )

    payload = public_infrastructure_settings(config, environ={})

    assert payload["network"]["package_mirrors"] == {
        "conda_channel_mirror": "https://packages.example.org/conda",
        "python_package_index": "https://packages.example.org/pypi/simple",
        "ca_bundle_path": "",
    }
    assert package_environment(config) == {
        "CONDA_CHANNEL_ALIAS": "https://packages.example.org/conda",
        "PIP_INDEX_URL": "https://packages.example.org/pypi/simple",
    }
    serialized = json.dumps(payload)
    assert "password" not in serialized
    assert "token=secret" not in serialized
    assert "key=secret" not in serialized


def test_malformed_worker_network_policy_fails_closed(monkeypatch) -> None:
    monkeypatch.setenv("GM_SCIENCE_NETWORK_POLICY_JSON", "{not-json")

    decision = network_policy_from_env().evaluate_url("https://api.openalex.org/works")

    assert decision.allowed is False
    assert "disabled" in decision.reason.lower()


def test_config_to_env_projects_bounded_network_policy() -> None:
    config = default_config()
    apply_infrastructure_update(
        config,
        {"network": {"category_enabled": {"research_data": False}, "custom_domains": ["data.example.org"]}},
    )

    policy = json.loads(config_to_env(config)["GM_SCIENCE_NETWORK_POLICY_JSON"])

    assert policy["enabled"] is True
    assert policy["enforce_allowlist"] is True
    assert "data.example.org" in policy["allowed_domains"]
    assert "api.openalex.org" not in policy["allowed_domains"]


def test_explicit_empty_environment_does_not_inherit_compute_credentials(monkeypatch) -> None:
    monkeypatch.setenv("MODAL_TOKEN_ID", "ambient-id")
    monkeypatch.setenv("MODAL_TOKEN_SECRET", "ambient-secret")

    payload = public_infrastructure_settings(default_config(), environ={})
    modal = next(item for item in payload["compute"]["targets"] if item["id"] == "modal")
    health = check_compute_target(default_config(), "modal", environ={})

    assert modal["configured"] is False
    assert health["status"] == "needs_configuration"


def test_local_compute_health_is_real_and_remote_execution_is_not_implied() -> None:
    config = default_config()

    local = check_compute_target(config, "local", environ={})
    modal = check_compute_target(config, "modal", environ={})

    assert local["reachable"] is True
    assert local["executable"] is True
    assert modal["reachable"] is False
    assert modal["executable"] is False
    assert modal["status"] == "needs_configuration"


@pytest.mark.parametrize(
    "update",
    [
        {"permission_grants": {"unknown_permission": False}},
        {"network": {"custom_domains": ["https://example.org/path"]}},
        {"network": {"unknown": True}},
        {"compute_target": {"operation": "remove", "id": "local"}},
        {
            "compute_target": {
                "operation": "upsert",
                "target": {"id": "bad", "type": "ssh", "name": "Bad", "host": ""},
            }
        },
    ],
)
def test_infrastructure_update_rejects_unknown_or_unsafe_values(update: dict[str, object]) -> None:
    with pytest.raises(ValueError):
        apply_infrastructure_update(default_config(), update)
