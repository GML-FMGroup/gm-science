"""Tests for the gm-science public settings contract."""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from openppx.core.config import default_config, load_runtime_config, save_config
from openppx.gm_science.settings import GmScienceSettingsService


def _config_path(tmp_path: Path) -> Path:
    path = tmp_path / "science-research" / "config.json"
    config = default_config()
    providers = config["providers"]
    for provider in providers.values():
        provider["enabled"] = False
    providers["openai_codex"]["enabled"] = True
    providers["openai_codex"]["model"] = "openai-codex/gpt-5.5"
    config["science"]["literature"]["pubmed"]["email"] = "researcher@example.org"
    save_config(config, config_path=path)
    return path


def test_public_settings_are_product_owned_and_redact_secrets(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = _config_path(tmp_path)
    monkeypatch.setattr(
        "openppx.gm_science.settings._openai_codex_oauth_configured",
        lambda: True,
    )

    payload = GmScienceSettingsService(config_path=path).get_settings()

    assert payload["model"] == {
        "provider": "openai_codex",
        "model": "openai-codex/gpt-5.5",
    }
    assert payload["memory"] == {"enabled": True}
    assert [item["id"] for item in payload["providers"]] == [
        "openai_codex",
        "openai",
        "google",
        "anthropic",
        "custom",
        "vllm",
    ]
    codex = payload["providers"][0]
    assert codex["auth_type"] == "oauth"
    assert codex["credential_configured"] is True
    assert codex["credential_source"] == "oauth_cache"
    assert payload["literature"]["pubmed"] == {
        "email": "researcher@example.org",
        "api_key_configured": False,
        "status": "ready",
        "status_detail": "",
    }
    assert payload["literature"]["openalex"]["status"] == "needs_configuration"
    serialized = json.dumps(payload)
    assert '"apiKey":' not in serialized
    assert '"api_key":' not in serialized
    assert '"access"' not in serialized
    assert '"account_id"' not in serialized


def test_settings_update_switches_provider_and_writes_secrets_without_returning_them(tmp_path: Path) -> None:
    path = _config_path(tmp_path)
    service = GmScienceSettingsService(config_path=path)

    payload = service.update_settings(
        {
            "model": {"provider": "openai", "model": "openai/gpt-5.5"},
            "provider_api_key": {"operation": "replace", "value": "sk-provider-secret"},
            "pubmed_email": "owner@example.org",
            "pubmed_api_key": {"operation": "replace", "value": "pubmed-secret"},
            "openalex_api_key": {"operation": "replace", "value": "openalex-secret"},
        }
    )

    raw = json.loads(path.read_text(encoding="utf-8"))
    assert raw["providers"]["openai"]["enabled"] is True
    assert raw["providers"]["openai_codex"]["enabled"] is False
    assert raw["providers"]["openai"]["model"] == "openai/gpt-5.5"
    assert raw["providers"]["openai"]["apiKey"] == "sk-provider-secret"
    assert raw["science"]["literature"]["pubmed"]["email"] == "owner@example.org"
    assert raw["science"]["literature"]["pubmed"]["apiKey"] == "pubmed-secret"
    assert raw["science"]["literature"]["openalex"]["apiKey"] == "openalex-secret"
    assert payload["model"] == {"provider": "openai", "model": "openai/gpt-5.5"}
    assert payload["literature"]["pubmed"]["api_key_configured"] is True
    assert payload["literature"]["openalex"]["api_key_configured"] is True
    assert "sk-provider-secret" not in json.dumps(payload)
    assert "pubmed-secret" not in json.dumps(payload)
    assert "openalex-secret" not in json.dumps(payload)


def test_omitted_secrets_are_preserved_and_remove_is_explicit(tmp_path: Path) -> None:
    path = _config_path(tmp_path)
    service = GmScienceSettingsService(config_path=path)
    service.update_settings(
        {
            "model": {"provider": "openai", "model": "openai/gpt-5.5"},
            "provider_api_key": {"operation": "replace", "value": "keep-provider"},
            "pubmed_api_key": {"operation": "replace", "value": "keep-pubmed"},
        }
    )

    service.update_settings({"pubmed_email": "updated@example.org"})
    preserved = json.loads(path.read_text(encoding="utf-8"))
    assert preserved["providers"]["openai"]["apiKey"] == "keep-provider"
    assert preserved["science"]["literature"]["pubmed"]["apiKey"] == "keep-pubmed"

    service.update_settings(
        {
            "provider_api_key": {"operation": "remove"},
            "pubmed_api_key": {"operation": "remove"},
        }
    )
    removed = json.loads(path.read_text(encoding="utf-8"))
    assert removed["providers"]["openai"]["apiKey"] == ""
    assert removed["science"]["literature"]["pubmed"]["apiKey"] == ""


def test_custom_credentials_are_write_only_and_cannot_be_removed_while_referenced(
    tmp_path: Path,
) -> None:
    path = _config_path(tmp_path)
    service = GmScienceSettingsService(config_path=path)

    payload = service.update_settings(
        {
            "custom_credential": {
                "operation": "upsert",
                "id": "lab-token",
                "name": "Lab token",
                "value": "top-secret",
            }
        }
    )

    assert payload["credentials"]["custom"] == [
        {"id": "lab-token", "name": "Lab token", "configured": True}
    ]
    assert "top-secret" not in json.dumps(payload)
    raw = json.loads(path.read_text(encoding="utf-8"))
    raw["tools"]["mcpServers"]["lab"] = {
        "managedBy": "gm-science",
        "command": "lab-mcp",
        "credentialBindings": {"env": {"LAB_TOKEN": "lab-token"}},
    }
    save_config(raw, config_path=path)

    with pytest.raises(ValueError, match="still used by Connector 'mcp:lab'"):
        service.update_settings(
            {"custom_credential": {"operation": "remove", "id": "lab-token"}}
        )

    raw["tools"]["mcpServers"] = {}
    save_config(raw, config_path=path)
    removed = service.update_settings(
        {"custom_credential": {"operation": "remove", "id": "lab-token"}}
    )
    assert removed["credentials"]["custom"] == []


@pytest.mark.parametrize(
    ("update", "message"),
    [
        ({"model": {"provider": "deepseek", "model": "deepseek-v4"}}, "Unsupported gm-science provider"),
        ({"model": {"provider": "openai", "model": ""}}, "Model is required"),
        ({"provider_api_key": {"operation": "replace", "value": ""}}, "non-empty value"),
        ({"provider_api_key": {"operation": "unknown"}}, "replace or remove"),
        ({"pubmed_email": "not-an-email"}, "valid email"),
    ],
)
def test_settings_update_rejects_invalid_mutations(tmp_path: Path, update: dict[str, object], message: str) -> None:
    path = _config_path(tmp_path)

    with pytest.raises(ValueError, match=message):
        GmScienceSettingsService(config_path=path).update_settings(update)


def test_settings_updates_are_serialized_without_losing_independent_fields(tmp_path: Path) -> None:
    path = _config_path(tmp_path)
    service = GmScienceSettingsService(config_path=path)

    with ThreadPoolExecutor(max_workers=2) as executor:
        updates = [
            executor.submit(service.update_settings, {"pubmed_email": "parallel@example.org"}),
            executor.submit(
                service.update_settings,
                {"openalex_api_key": {"operation": "replace", "value": "parallel-openalex"}},
            ),
        ]
        for update in updates:
            update.result()

    raw = json.loads(path.read_text(encoding="utf-8"))
    assert raw["science"]["literature"]["pubmed"]["email"] == "parallel@example.org"
    assert raw["science"]["literature"]["openalex"]["apiKey"] == "parallel-openalex"


def test_global_memory_switch_is_persisted_in_runtime_config(tmp_path: Path) -> None:
    path = _config_path(tmp_path)
    service = GmScienceSettingsService(config_path=path)

    payload = service.update_settings({"memory_enabled": False})

    runtime = load_runtime_config(runtime_config_path=path.with_name("runtime.json"))
    assert runtime["env"]["OPENPPX_MEMORY_ENABLED"] is False
    assert payload["memory"] == {"enabled": False}
    assert service.get_settings()["memory"] == {"enabled": False}


def test_global_memory_switch_requires_boolean(tmp_path: Path) -> None:
    path = _config_path(tmp_path)

    with pytest.raises(ValueError, match="must be a boolean"):
        GmScienceSettingsService(config_path=path).update_settings({"memory_enabled": "false"})


def test_settings_service_exposes_and_updates_infrastructure_without_secret_leakage(tmp_path: Path) -> None:
    path = _config_path(tmp_path)
    service = GmScienceSettingsService(config_path=path)

    payload = service.update_settings(
        {
            "permission_grants": {"attach_connector": False},
            "network": {"custom_domains": ["data.example.org"]},
            "compute_target": {
                "operation": "upsert",
                "target": {
                    "id": "lab_endpoint",
                    "type": "model_endpoint",
                    "name": "Lab endpoint",
                    "enabled": True,
                    "url": "https://data.example.org/v1",
                    "api_key": {"operation": "replace", "value": "secret-value"},
                },
            },
        }
    )

    assert next(
        item for item in payload["permissions"]["items"] if item["id"] == "attach_connector"
    )["granted"] is False
    assert payload["network"]["custom_domains"] == ["data.example.org"]
    target = next(item for item in payload["compute"]["targets"] if item["id"] == "lab_endpoint")
    assert target["metadata"]["api_key_configured"] is True
    assert "secret-value" not in json.dumps(payload)


def test_settings_service_checks_registry_permissions_and_compute_health(tmp_path: Path) -> None:
    path = _config_path(tmp_path)
    service = GmScienceSettingsService(config_path=path)
    service.update_settings({"permission_grants": {"attach_skill": False}})

    with pytest.raises(PermissionError, match="Attach skill"):
        service.require_permissions(["attach_skill"])

    health = service.check_compute_target("local")
    assert health["target_id"] == "local"
    assert health["reachable"] is True
