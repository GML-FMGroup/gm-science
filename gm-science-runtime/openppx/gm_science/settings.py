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
        "providers": provider_items,
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


def _runtime_memory_enabled(runtime_config: Mapping[str, Any]) -> bool:
    """Read the normalized global Memory switch from runtime configuration."""

    raw = _mapping(runtime_config.get("env")).get("OPENPPX_MEMORY_ENABLED", True)
    if isinstance(raw, bool):
        return raw
    return str(raw or "").strip().lower() not in {"", "0", "false", "no", "off"}


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
