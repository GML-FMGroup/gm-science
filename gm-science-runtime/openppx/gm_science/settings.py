"""Config-backed public settings service for gm-science."""

from __future__ import annotations

import os
import re
import threading
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Literal

from ..core.config import (
    config_to_env,
    load_config,
    load_runtime_config,
    save_config,
    save_runtime_config,
)
from ..core.provider import normalize_model_name
from ..core.provider_registry import ProviderSpec, find_provider_spec
from .infrastructure import (
    apply_infrastructure_update,
    check_compute_target,
    public_infrastructure_settings,
    require_registry_permissions,
)
from .literature.config import parse_literature_config

GM_SCIENCE_PROVIDER_IDS: tuple[str, ...] = (
    "openai_codex",
    "openai",
    "google",
    "anthropic",
    "custom",
    "vllm",
)

_OPTIONAL_API_KEY_PROVIDERS = frozenset({"custom", "vllm"})
_SECRET_OPERATIONS = frozenset({"replace", "remove"})
_MAX_MODEL_CHARS = 300
_MAX_SECRET_CHARS = 32768
_MAX_EMAIL_CHARS = 320
_EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_CREDENTIAL_ID_PATTERN = re.compile(r"^[a-z][a-z0-9_-]{0,63}$")
_MAX_CREDENTIAL_NAME_CHARS = 120


class GmScienceSettingsService:
    """Read and update the safe gm-science settings projection.

    Stored credentials are never included in public responses. Callers update a
    secret only by sending an explicit ``replace`` or ``remove`` mutation.
    """

    def __init__(self, *, config_path: Path, lock: Any | None = None) -> None:
        self.config_path = config_path
        self._lock = lock or threading.RLock()

    def get_settings(self) -> dict[str, Any]:
        """Return model, provider, and literature settings without secrets."""

        with self._lock:
            return _public_settings(
                load_config(config_path=self.config_path),
                load_runtime_config(runtime_config_path=self._runtime_config_path),
            )

    @property
    def _runtime_config_path(self) -> Path:
        """Return the runtime settings file paired with this Agent config."""

        return self.config_path.with_name("runtime.json")

    def update_settings(self, update: Mapping[str, Any]) -> dict[str, Any]:
        """Validate and persist one partial settings update."""

        if not isinstance(update, Mapping):
            raise ValueError("Settings update must be a JSON object.")
        allowed_fields = {
            "compute_target",
            "custom_credential",
            "general",
            "model",
            "memory_enabled",
            "network",
            "permission_grants",
            "provider_api_key",
            "pubmed_email",
            "pubmed_api_key",
            "openalex_api_key",
        }
        unknown_fields = sorted(set(update).difference(allowed_fields))
        if unknown_fields:
            raise ValueError(f"Unsupported settings fields: {', '.join(unknown_fields)}")

        with self._lock:
            config = load_config(config_path=self.config_path)
            runtime_config = load_runtime_config(runtime_config_path=self._runtime_config_path)
            active_provider = _active_provider(config)
            if "model" in update:
                active_provider = _apply_model_update(config, update["model"])

            providers = _mapping(config.get("providers"))
            provider_config = _mutable_mapping(providers.get(active_provider))
            _apply_secret_mutation(
                provider_config,
                "apiKey",
                update.get("provider_api_key"),
                field_name="provider_api_key",
            )

            literature = _literature_config(config)
            pubmed = _mutable_mapping(literature.get("pubmed"))
            openalex = _mutable_mapping(literature.get("openalex"))
            if "pubmed_email" in update:
                pubmed["email"] = _validate_email(update.get("pubmed_email"))
            _apply_secret_mutation(
                pubmed,
                "apiKey",
                update.get("pubmed_api_key"),
                field_name="pubmed_api_key",
            )
            _apply_secret_mutation(
                openalex,
                "apiKey",
                update.get("openalex_api_key"),
                field_name="openalex_api_key",
            )

            if "memory_enabled" in update:
                memory_enabled = update["memory_enabled"]
                if not isinstance(memory_enabled, bool):
                    raise ValueError("Field 'memory_enabled' must be a boolean.")
                runtime_env = _mutable_mapping(runtime_config.get("env"))
                runtime_env["OPENPPX_MEMORY_ENABLED"] = memory_enabled

            if "general" in update:
                _apply_general_update(config, runtime_config, update["general"])

            if "custom_credential" in update:
                _apply_custom_credential_update(config, update["custom_credential"])

            infrastructure_update = {
                key: update[key]
                for key in ("permission_grants", "network", "compute_target")
                if key in update
            }
            if infrastructure_update:
                apply_infrastructure_update(config, infrastructure_update)

            save_config(config, config_path=self.config_path)
            save_runtime_config(
                runtime_config,
                runtime_config_path=self._runtime_config_path,
            )
            return _public_settings(config, runtime_config)

    def require_permissions(self, permission_ids: list[str] | tuple[str, ...]) -> None:
        """Require durable registry permissions against the latest saved config."""

        with self._lock:
            require_registry_permissions(
                load_config(config_path=self.config_path),
                permission_ids,
            )

    def check_compute_target(self, target_id: str) -> dict[str, Any]:
        """Run one bounded Compute Target health check without changing config."""

        with self._lock:
            config = load_config(config_path=self.config_path)
        return check_compute_target(config, target_id)


def _public_settings(
    config: Mapping[str, Any],
    runtime_config: Mapping[str, Any],
) -> dict[str, Any]:
    """Build the renderer-safe settings payload from normalized config."""

    runtime_env = config_to_env(dict(config))
    active_provider = runtime_env.get("OPENPPX_PROVIDER", "")
    active_model = runtime_env.get("OPENPPX_MODEL", "")
    providers = _mapping(config.get("providers"))
    provider_items = [
        _provider_payload(
            spec=_provider_spec(provider_id),
            config=_mapping(providers.get(provider_id)),
            active=provider_id == active_provider,
        )
        for provider_id in GM_SCIENCE_PROVIDER_IDS
    ]

    literature_config = parse_literature_config(config)
    science = _mapping(config.get("science"))
    general = _mapping(science.get("general"))
    specialists = _mapping(science.get("specialists"))
    pubmed = literature_config.sources["pubmed"]
    openalex = literature_config.sources["openalex"]
    pubmed_status, pubmed_detail = pubmed.status()
    openalex_status, openalex_detail = openalex.status()
    return {
        "model": {
            "provider": active_provider,
            "model": active_model,
        },
        "memory": {
            "enabled": _runtime_memory_enabled(runtime_config),
        },
        "general": {
            "reasoning_effort": _reasoning_effort(general.get("reasoningEffort")),
            "reasoning_effort_supported": active_provider in {"openai_codex", "openai", "custom", "vllm"},
            "subagent_model": str(specialists.get("model") or "").strip(),
            "license_use_intent": _license_use_intent(general.get("licenseUseIntent")),
        },
        "providers": provider_items,
        "credentials": {
            "custom": _public_custom_credentials(config),
        },
        "literature": {
            "arxiv": {
                "status": "ready" if literature_config.sources["arxiv"].enabled else "disabled",
                "status_detail": "",
            },
            "pubmed": {
                "email": pubmed.email,
                "api_key_configured": bool(pubmed.api_key),
                "status": _public_status(pubmed_status),
                "status_detail": pubmed_detail,
            },
            "openalex": {
                "api_key_configured": bool(openalex.api_key),
                "status": _public_status(openalex_status),
                "status_detail": openalex_detail,
            },
        },
        **public_infrastructure_settings(config),
    }


def _public_custom_credentials(config: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Return stable custom credential metadata without secret values."""

    credentials = _mapping(_mapping(_mapping(config.get("science")).get("credentials")).get("custom"))
    items: list[dict[str, Any]] = []
    for raw_id in sorted(credentials, key=lambda value: str(value).casefold()):
        credential_id = str(raw_id)
        raw = _mapping(credentials[raw_id])
        items.append(
            {
                "id": credential_id,
                "name": str(raw.get("name") or credential_id),
                "configured": bool(str(raw.get("value") or "")),
            }
        )
    return items


def _apply_custom_credential_update(config: dict[str, Any], raw: Any) -> None:
    """Create, replace, rename, or remove one write-only local credential."""

    if not isinstance(raw, Mapping):
        raise ValueError("Field 'custom_credential' must be a JSON object.")
    operation = str(raw.get("operation") or "").strip().lower()
    if operation not in {"upsert", "remove"}:
        raise ValueError("Field 'custom_credential.operation' must be upsert or remove.")
    credential_id = str(raw.get("id") or "").strip()
    if not _CREDENTIAL_ID_PATTERN.fullmatch(credential_id):
        raise ValueError("Custom credential ID has an invalid format.")

    science = _mutable_mapping(config.get("science"))
    credentials = science.setdefault("credentials", {})
    if not isinstance(credentials, dict):
        raise ValueError("gm-science credentials configuration must be an object.")
    custom = credentials.setdefault("custom", {})
    if not isinstance(custom, dict):
        raise ValueError("gm-science custom credentials configuration must be an object.")
    if operation == "remove":
        if credential_id not in custom:
            raise ValueError(f"Custom credential '{credential_id}' was not found.")
        usages = _custom_credential_usages(config, credential_id)
        if usages:
            raise ValueError(
                f"Custom credential '{credential_id}' is still used by {', '.join(usages)}."
            )
        del custom[credential_id]
        return

    name = str(raw.get("name") or "").strip()
    if (
        not name
        or len(name) > _MAX_CREDENTIAL_NAME_CHARS
        or "\n" in name
        or "\r" in name
        or not all(char.isprintable() for char in name)
    ):
        raise ValueError(
            f"Custom credential name must be printable text of at most {_MAX_CREDENTIAL_NAME_CHARS} characters."
        )
    existing = _mapping(custom.get(credential_id))
    value = str(raw.get("value") or "")
    if not value:
        value = str(existing.get("value") or "")
    if not value:
        raise ValueError("A new custom credential requires a non-empty secret value.")
    if len(value) > _MAX_SECRET_CHARS or "\x00" in value:
        raise ValueError("Custom credential contains an invalid secret value.")
    custom[credential_id] = {
        "name": name,
        "value": value,
        "managedBy": "gm-science",
    }


def _custom_credential_usages(config: Mapping[str, Any], credential_id: str) -> list[str]:
    """Return managed Connectors that still reference one custom credential."""

    servers = _mapping(_mapping(config.get("tools")).get("mcpServers"))
    usages: list[str] = []
    for raw_server_id, raw_server in servers.items():
        bindings = _mapping(_mapping(raw_server).get("credentialBindings"))
        referenced = {
            str(value)
            for group in ("headers", "env")
            for value in _mapping(bindings.get(group)).values()
        }
        if credential_id in referenced:
            usages.append(f"Connector 'mcp:{raw_server_id}'")
    return usages


def _runtime_memory_enabled(runtime_config: Mapping[str, Any]) -> bool:
    """Read the normalized global Memory switch from runtime configuration."""

    raw = _mapping(runtime_config.get("env")).get("OPENPPX_MEMORY_ENABLED", True)
    if isinstance(raw, bool):
        return raw
    return str(raw or "").strip().lower() not in {"", "0", "false", "no", "off"}


def _apply_general_update(
    config: dict[str, Any],
    runtime_config: dict[str, Any],
    raw: Any,
) -> None:
    """Persist model-policy controls and their runtime projection."""

    if not isinstance(raw, Mapping):
        raise ValueError("Field 'general' must be a JSON object.")
    unknown = sorted(set(raw).difference({"reasoning_effort", "subagent_model", "license_use_intent"}))
    if unknown:
        raise ValueError(f"Unsupported general settings fields: {', '.join(unknown)}")
    science = _mutable_mapping(config.get("science"))
    general = _mutable_mapping(science.get("general"))
    specialists = _mutable_mapping(science.get("specialists"))
    if "reasoning_effort" in raw:
        effort = _reasoning_effort(raw.get("reasoning_effort"), strict=True)
        general["reasoningEffort"] = effort
        _mutable_mapping(runtime_config.get("env"))["OPENPPX_REASONING_EFFORT"] = effort
    if "subagent_model" in raw:
        model = str(raw.get("subagent_model") or "").strip()
        if len(model) > _MAX_MODEL_CHARS or any(ord(char) < 32 for char in model):
            raise ValueError(f"Subagent model must be at most {_MAX_MODEL_CHARS} printable characters.")
        specialists["model"] = model
    if "license_use_intent" in raw:
        general["licenseUseIntent"] = _license_use_intent(raw.get("license_use_intent"), strict=True)


def _reasoning_effort(value: Any, *, strict: bool = False) -> str:
    normalized = str(value or "medium").strip().lower()
    if normalized in {"low", "medium", "high"}:
        return normalized
    if strict:
        raise ValueError("Reasoning effort must be low, medium, or high.")
    return "medium"


def _license_use_intent(value: Any, *, strict: bool = False) -> str:
    normalized = str(value or "commercial").strip().lower()
    if normalized in {"commercial", "non_commercial"}:
        return normalized
    if strict:
        raise ValueError("License use intent must be commercial or non_commercial.")
    return "commercial"


def _provider_payload(*, spec: ProviderSpec, config: Mapping[str, Any], active: bool) -> dict[str, Any]:
    """Return one safe product-provider option."""

    auth_type: Literal["oauth", "api_key", "optional_api_key"]
    configured = False
    source = "none"
    if spec.is_oauth:
        auth_type = "oauth"
        configured = _oauth_configured(spec.name)
        source = "oauth_cache" if configured else "none"
    else:
        auth_type = "optional_api_key" if spec.name in _OPTIONAL_API_KEY_PROVIDERS else "api_key"
        config_key = str(config.get("apiKey") or "").strip()
        env_key = str(os.getenv(spec.api_key_env or "", "")).strip() if spec.api_key_env else ""
        configured = bool(config_key or env_key)
        source = "local_config" if config_key else "environment" if env_key else "none"
    return {
        "id": spec.name,
        "name": spec.display_name,
        "default_model": spec.default_model,
        "auth_type": auth_type,
        "credential_required": auth_type != "optional_api_key",
        "credential_configured": configured,
        "credential_source": source,
        "active": active,
    }


def _apply_model_update(config: dict[str, Any], raw: Any) -> str:
    """Select one product provider and validate its model."""

    if not isinstance(raw, Mapping):
        raise ValueError("Field 'model' must be a JSON object.")
    provider = str(raw.get("provider") or "").strip()
    if provider not in GM_SCIENCE_PROVIDER_IDS:
        raise ValueError(f"Unsupported gm-science provider: {provider or '<empty>'}")
    model = str(raw.get("model") or "").strip()
    if not model:
        raise ValueError("Model is required.")
    if len(model) > _MAX_MODEL_CHARS or any(ord(char) < 32 for char in model):
        raise ValueError(f"Model must be at most {_MAX_MODEL_CHARS} printable characters.")

    providers = _mutable_mapping(config.get("providers"))
    for provider_id, provider_value in providers.items():
        if isinstance(provider_value, dict):
            provider_value["enabled"] = provider_id == provider
    provider_config = _mutable_mapping(providers.get(provider))
    provider_config["model"] = normalize_model_name(provider, model)
    return provider


def _apply_secret_mutation(
    target: dict[str, Any],
    key: str,
    raw: Any,
    *,
    field_name: str,
) -> None:
    """Apply an explicit write-only secret mutation, preserving omitted values."""

    if raw is None:
        return
    if not isinstance(raw, Mapping):
        raise ValueError(f"Field '{field_name}' must be a JSON object.")
    operation = str(raw.get("operation") or "").strip().lower()
    if operation not in _SECRET_OPERATIONS:
        raise ValueError(f"Field '{field_name}.operation' must be replace or remove.")
    if operation == "remove":
        target[key] = ""
        return
    value = str(raw.get("value") or "").strip()
    if not value:
        raise ValueError(f"Field '{field_name}' replace operation requires a non-empty value.")
    if len(value) > _MAX_SECRET_CHARS or any(ord(char) < 32 for char in value):
        raise ValueError(f"Field '{field_name}' contains an invalid credential value.")
    target[key] = value


def _validate_email(raw: Any) -> str:
    """Validate the optional PubMed policy contact email."""

    email = str(raw or "").strip()
    if not email:
        return ""
    if len(email) > _MAX_EMAIL_CHARS or not _EMAIL_PATTERN.fullmatch(email):
        raise ValueError("PubMed contact must be a valid email address.")
    return email


def _active_provider(config: Mapping[str, Any]) -> str:
    """Resolve the active provider from the same config mapping used at runtime."""

    return config_to_env(dict(config)).get("OPENPPX_PROVIDER", "")


def _provider_spec(provider_id: str) -> ProviderSpec:
    spec = find_provider_spec(provider_id)
    if spec is None:  # pragma: no cover - protected by the static product catalog
        raise RuntimeError(f"Missing provider registry entry: {provider_id}")
    return spec


def _oauth_configured(provider_id: str) -> bool:
    if provider_id == "openai_codex":
        return _openai_codex_oauth_configured()
    return False


def _public_status(status: str) -> str:
    """Translate connector config status into the public settings vocabulary."""

    if status == "ok":
        return "ready"
    return status


def _openai_codex_oauth_configured() -> bool:
    """Check the local Codex OAuth cache without returning token metadata."""

    try:
        from oauth_cli_kit import get_token

        token = get_token()
    except Exception:
        return False
    return bool(token and getattr(token, "access", "") and getattr(token, "account_id", ""))


def _literature_config(config: dict[str, Any]) -> dict[str, Any]:
    science = _mutable_mapping(config.get("science"))
    return _mutable_mapping(science.get("literature"))


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _mutable_mapping(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("gm-science configuration has an invalid object structure.")
    return value
