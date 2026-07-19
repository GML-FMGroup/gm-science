"""Permission, network, and Compute governance for gm-science."""

from __future__ import annotations

import datetime as dt
import ipaddress
import os
import re
import socket
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import httpx


PERMISSION_DEFINITIONS: tuple[dict[str, str], ...] = (
    {
        "id": "create_agent",
        "name": "Create agent",
        "description": "Create a persistent specialist Agent definition.",
    },
    {
        "id": "update_agent",
        "name": "Update agent",
        "description": "Update or attach a persistent specialist Agent definition.",
    },
    {
        "id": "publish_skill",
        "name": "Publish skill",
        "description": "Publish a Skill into the local registry.",
    },
    {
        "id": "edit_skill",
        "name": "Edit skill",
        "description": "Modify a Skill already stored in the local registry.",
    },
    {
        "id": "attach_skill",
        "name": "Attach skill",
        "description": "Attach a Skill to a Project.",
    },
    {
        "id": "detach_skill",
        "name": "Detach skill",
        "description": "Detach a Skill from a Project.",
    },
    {
        "id": "attach_connector",
        "name": "Attach connector",
        "description": "Attach a Connector to a Project.",
    },
    {
        "id": "detach_connector",
        "name": "Detach connector",
        "description": "Detach a Connector from a Project.",
    },
)

NETWORK_CATEGORY_DEFINITIONS: tuple[dict[str, Any], ...] = (
    {
        "id": "package_management",
        "name": "Package management",
        "description": "Python, Conda, npm, CRAN, Bioconductor, and source repositories.",
        "domains": (
            "pypi.org",
            "files.pythonhosted.org",
            "repo.anaconda.com",
            "conda.anaconda.org",
            "cran.r-project.org",
            "bioconductor.org",
            "github.com",
            "raw.githubusercontent.com",
        ),
    },
    {
        "id": "research_data",
        "name": "Research data",
        "description": "Native literature and public scientific data services.",
        "domains": (
            "export.arxiv.org",
            "arxiv.org",
            "eutils.ncbi.nlm.nih.gov",
            "api.ncbi.nlm.nih.gov",
            "api.openalex.org",
        ),
    },
    {
        "id": "model_providers",
        "name": "Model providers",
        "description": "Configured language and scientific model APIs.",
        "domains": (
            "chatgpt.com",
            "api.openai.com",
            "generativelanguage.googleapis.com",
            "api.anthropic.com",
        ),
    },
    {
        "id": "cloud_compute",
        "name": "Cloud compute",
        "description": "Optional remote compute and model endpoint services.",
        "domains": ("modal.com", "api.modal.com", "integrate.api.nvidia.com"),
    },
)

_PERMISSION_IDS = frozenset(item["id"] for item in PERMISSION_DEFINITIONS)
_NETWORK_CATEGORY_IDS = frozenset(item["id"] for item in NETWORK_CATEGORY_DEFINITIONS)
_NETWORK_UPDATE_FIELDS = frozenset(
    {
        "enabled",
        "enforce_allowlist",
        "allow_private_networks",
        "conda_channel_mirror",
        "python_package_index",
        "ca_bundle_path",
        "category_enabled",
        "custom_domains",
    }
)
_TARGET_ID_PATTERN = re.compile(r"^[a-z][a-z0-9_-]{1,63}$")
_HOST_PATTERN = re.compile(r"^[A-Za-z0-9*_.-]+$")
_MAX_TEXT = 4096
_BUILTIN_TARGET_IDS = frozenset({"local", "modal", "nvidia_bionemo_nim"})


class RegistryPermissionError(PermissionError):
    """Raised when a durable registry mutation has been revoked."""


@dataclass(frozen=True, slots=True)
class NetworkDecision:
    """Result of evaluating one outbound destination against product policy."""

    allowed: bool
    reason: str = ""
    hostname: str = ""


@dataclass(frozen=True, slots=True)
class NetworkPolicy:
    """Validated gm-science outbound network policy."""

    enabled: bool
    enforce_allowlist: bool
    allow_private_networks: bool
    allowed_domains: tuple[str, ...]

    def evaluate_url(self, url: str, *, purpose: str = "network request") -> NetworkDecision:
        """Return whether an HTTP(S) URL may be used by a product tool."""

        try:
            parsed = urlsplit(str(url or "").strip())
        except ValueError:
            return NetworkDecision(False, f"{purpose} has an invalid URL.")
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            return NetworkDecision(False, f"{purpose} requires an HTTP(S) URL with a domain.")
        return self.evaluate_hostname(parsed.hostname, purpose=purpose)

    def evaluate_hostname(self, hostname: str, *, purpose: str = "network request") -> NetworkDecision:
        """Return whether one normalized host may be contacted."""

        normalized = str(hostname or "").strip().lower().rstrip(".")
        if not self.enabled:
            return NetworkDecision(False, "Network access is disabled by gm-science policy.", normalized)
        if not normalized:
            return NetworkDecision(False, f"{purpose} requires a domain.")
        if not self.allow_private_networks and _is_private_hostname(normalized):
            return NetworkDecision(
                False,
                f"Domain '{normalized}' is blocked by private-network policy.",
                normalized,
            )
        if self.enforce_allowlist and not any(_domain_matches(normalized, item) for item in self.allowed_domains):
            return NetworkDecision(
                False,
                f"Domain '{normalized}' is not enabled by Network policy.",
                normalized,
            )
        return NetworkDecision(True, hostname=normalized)


def public_infrastructure_settings(
    config: Mapping[str, Any],
    *,
    environ: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Return renderer-safe permission, network, and Compute settings."""

    effective_environ = os.environ if environ is None else environ
    return {
        "permissions": {"items": _public_permissions(config)},
        "network": _public_network(config),
        "compute": {"targets": _public_compute_targets(config, environ=effective_environ)},
    }


def apply_infrastructure_update(
    config: dict[str, Any],
    update: Mapping[str, Any],
    *,
    now: str | None = None,
) -> None:
    """Validate and apply one infrastructure update to an in-memory config."""

    if not isinstance(update, Mapping):
        raise ValueError("Infrastructure update must be a JSON object.")
    unknown = sorted(set(update).difference({"permission_grants", "network", "compute_target"}))
    if unknown:
        raise ValueError(f"Unsupported infrastructure fields: {', '.join(unknown)}")
    if "permission_grants" in update:
        _apply_permission_update(config, update["permission_grants"], now=now or _iso_now())
    if "network" in update:
        _apply_network_update(config, update["network"])
    if "compute_target" in update:
        _apply_compute_target_update(config, update["compute_target"])


def require_registry_permissions(config: Mapping[str, Any], required: list[str] | tuple[str, ...]) -> None:
    """Raise when any requested durable registry permission is revoked."""

    permissions = _permission_config(config)
    definitions = {item["id"]: item for item in PERMISSION_DEFINITIONS}
    for permission_id in dict.fromkeys(required):
        if permission_id not in definitions:
            raise ValueError(f"Unknown registry permission '{permission_id}'.")
        record = _mapping(permissions.get(permission_id))
        if record.get("granted", True) is False:
            definition = definitions[permission_id]
            raise RegistryPermissionError(
                f"{definition['name']} permission is revoked in gm-science Permissions."
            )


def parse_network_policy(config: Mapping[str, Any]) -> NetworkPolicy:
    """Build a validated network policy from one normalized config mapping."""

    network = _network_config(config)
    category_enabled = _mapping(network.get("categoryEnabled"))
    domains: list[str] = []
    for definition in NETWORK_CATEGORY_DEFINITIONS:
        if category_enabled.get(definition["id"], True) is False:
            continue
        domains.extend(str(item) for item in definition["domains"])
    if category_enabled.get("configured_connectors", True) is not False:
        domains.extend(_configured_remote_mcp_domains(config))
    domains.extend(_configured_package_mirror_domains(config))
    domains.extend(_normalize_domains(network.get("customDomains"), strict=False))
    return NetworkPolicy(
        enabled=_bool(network.get("enabled"), True),
        enforce_allowlist=_bool(network.get("enforceAllowlist"), True),
        allow_private_networks=_bool(network.get("allowPrivateNetworks"), False),
        allowed_domains=tuple(dict.fromkeys(domains)),
    )


def network_policy_from_env() -> NetworkPolicy:
    """Load the worker network policy from its bounded environment payload."""

    raw = os.getenv("GM_SCIENCE_NETWORK_POLICY_JSON", "").strip()
    if raw:
        try:
            import json

            parsed = json.loads(raw)
        except (TypeError, ValueError):
            parsed = None
        if isinstance(parsed, dict):
            return NetworkPolicy(
                enabled=_bool(parsed.get("enabled"), True),
                enforce_allowlist=_bool(parsed.get("enforce_allowlist"), True),
                allow_private_networks=_bool(parsed.get("allow_private_networks"), False),
                allowed_domains=tuple(_normalize_domains(parsed.get("allowed_domains"), strict=False)),
            )
        return NetworkPolicy(
            enabled=False,
            enforce_allowlist=True,
            allow_private_networks=False,
            allowed_domains=(),
        )
    # Direct connector unit use has no product worker context. Managed
    # gm-science workers always receive the explicit bounded payload.
    return NetworkPolicy(
        enabled=True,
        enforce_allowlist=False,
        allow_private_networks=False,
        allowed_domains=(),
    )


def network_policy_env_payload(config: Mapping[str, Any]) -> dict[str, Any]:
    """Return the minimal worker environment representation of Network policy."""

    policy = parse_network_policy(config)
    return {
        "enabled": policy.enabled,
        "enforce_allowlist": policy.enforce_allowlist,
        "allow_private_networks": policy.allow_private_networks,
        "allowed_domains": list(policy.allowed_domains),
    }


def filter_mcp_servers_by_network(
    servers: Mapping[str, Any],
    *,
    policy: NetworkPolicy | None = None,
) -> tuple[dict[str, Any], dict[str, str]]:
    """Remove remote MCP servers denied by policy while retaining stdio servers."""

    active_policy = policy or network_policy_from_env()
    allowed: dict[str, Any] = {}
    blocked: dict[str, str] = {}
    for raw_name, value in servers.items():
        name = str(raw_name)
        item = _mapping(value)
        url = str(item.get("url") or "").strip()
        if not url:
            allowed[name] = value
            continue
        decision = active_policy.evaluate_url(url, purpose=f"MCP server '{name}'")
        if decision.allowed:
            allowed[name] = value
        else:
            blocked[name] = decision.reason
    return allowed, blocked


def package_environment(config: Mapping[str, Any]) -> dict[str, str]:
    """Return package and TLS environment variables configured for local runs."""

    network = _network_config(config)
    conda = _public_url(str(network.get("condaChannelMirror") or "").strip())
    pip = _public_url(str(network.get("pythonPackageIndex") or "").strip())
    ca_bundle = str(network.get("caBundlePath") or "").strip()
    values: dict[str, str] = {}
    if conda:
        values["CONDA_CHANNEL_ALIAS"] = conda
    if pip:
        values["PIP_INDEX_URL"] = pip
    if ca_bundle:
        values.update(
            {
                "PIP_CERT": ca_bundle,
                "REQUESTS_CA_BUNDLE": ca_bundle,
                "SSL_CERT_FILE": ca_bundle,
            }
        )
    return values


def check_compute_target(
    config: Mapping[str, Any],
    target_id: str,
    *,
    environ: Mapping[str, str] | None = None,
    timeout_seconds: float = 2.0,
) -> dict[str, Any]:
    """Run a bounded, non-mutating connectivity check for one Compute Target."""

    normalized_id = str(target_id or "").strip()
    env = os.environ if environ is None else environ
    if normalized_id == "local":
        execution = _mapping(_science(config).get("execution"))
        enabled = _bool(execution.get("enabled"), True)
        return _health_payload(
            target_id="local",
            status="ready" if enabled else "disabled",
            reachable=enabled,
            executable=enabled,
            detail="Local Python execution is available." if enabled else "Local execution is disabled.",
        )
    if normalized_id == "modal":
        configured = bool(str(env.get("MODAL_TOKEN_ID") or "").strip() and str(env.get("MODAL_TOKEN_SECRET") or "").strip())
        return _health_payload(
            target_id="modal",
            status="unavailable" if configured else "needs_configuration",
            reachable=False,
            executable=False,
            detail=(
                "Modal credentials are present; remote execution adapter is not implemented."
                if configured
                else "Modal credentials are not configured."
            ),
        )
    if normalized_id == "nvidia_bionemo_nim":
        configured = bool(str(env.get("NVIDIA_API_KEY") or "").strip())
        return _health_payload(
            target_id=normalized_id,
            status="unavailable" if configured else "needs_configuration",
            reachable=False,
            executable=False,
            detail=(
                "NVIDIA credentials are present; NIM execution adapter is not implemented."
                if configured
                else "NVIDIA API credentials are not configured."
            ),
        )

    target = _mapping(_compute_targets(config).get(normalized_id))
    if not target:
        raise ValueError(f"Compute Target '{normalized_id}' was not found.")
    if not _bool(target.get("enabled"), True):
        return _health_payload(
            target_id=normalized_id,
            status="disabled",
            reachable=False,
            executable=False,
            detail="Compute Target is disabled.",
        )
    target_type = str(target.get("type") or "")
    if target_type == "ssh":
        host = str(target.get("host") or "")
        port = int(target.get("port") or 22)
        decision = parse_network_policy(config).evaluate_hostname(host, purpose="SSH health check")
        if not decision.allowed:
            return _health_payload(normalized_id, "blocked", False, False, decision.reason)
        try:
            connection = socket.create_connection((host, port), timeout=max(0.1, timeout_seconds))
            connection.close()
        except OSError as exc:
            return _health_payload(normalized_id, "unreachable", False, False, _safe_error(exc))
        return _health_payload(
            normalized_id,
            "reachable",
            True,
            False,
            "SSH port is reachable; remote execution adapter is not implemented.",
        )
    if target_type == "model_endpoint":
        base_url = str(target.get("url") or "")
        health_path = str(target.get("healthPath") or "").strip() or "/health"
        health_url = base_url.rstrip("/") + "/" + health_path.lstrip("/")
        decision = parse_network_policy(config).evaluate_url(health_url, purpose="Model endpoint health check")
        if not decision.allowed:
            return _health_payload(normalized_id, "blocked", False, False, decision.reason)
        headers: dict[str, str] = {}
        api_key = str(target.get("apiKey") or "").strip()
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        try:
            response = httpx.get(health_url, headers=headers, timeout=max(0.1, timeout_seconds))
        except httpx.HTTPError as exc:
            return _health_payload(normalized_id, "unreachable", False, False, _safe_error(exc))
        reachable = response.status_code < 500
        return _health_payload(
            normalized_id,
            "reachable" if reachable else "unreachable",
            reachable,
            False,
            f"Endpoint returned HTTP {response.status_code}; execution adapter is not implemented.",
        )
    raise ValueError(f"Compute Target '{normalized_id}' has unsupported type '{target_type}'.")


def _public_permissions(config: Mapping[str, Any]) -> list[dict[str, Any]]:
    stored = _permission_config(config)
    items: list[dict[str, Any]] = []
    for definition in PERMISSION_DEFINITIONS:
        record = _mapping(stored.get(definition["id"]))
        items.append(
            {
                **definition,
                "category": "registry_writes",
                "granted": record.get("granted", True) is not False,
                "scope": "global",
                "source": str(record.get("source") or "default"),
                "updated_at": str(record.get("updatedAt") or ""),
            }
        )
    return items


def _public_network(config: Mapping[str, Any]) -> dict[str, Any]:
    network = _network_config(config)
    category_enabled = _mapping(network.get("categoryEnabled"))
    categories = [
        {
            "id": definition["id"],
            "name": definition["name"],
            "description": definition["description"],
            "enabled": category_enabled.get(definition["id"], True) is not False,
            "domains": list(definition["domains"]),
        }
        for definition in NETWORK_CATEGORY_DEFINITIONS
    ]
    connector_domains = _configured_remote_mcp_domains(config)
    categories.append(
        {
            "id": "configured_connectors",
            "name": "Configured Connectors",
            "description": "Remote MCP domains already configured in gm-science.",
            "enabled": category_enabled.get("configured_connectors", True) is not False,
            "domains": connector_domains,
        }
    )
    return {
        "enabled": _bool(network.get("enabled"), True),
        "enforce_allowlist": _bool(network.get("enforceAllowlist"), True),
        "allow_private_networks": _bool(network.get("allowPrivateNetworks"), False),
        "package_mirrors": {
            "conda_channel_mirror": _public_url(str(network.get("condaChannelMirror") or "")),
            "python_package_index": _public_url(str(network.get("pythonPackageIndex") or "")),
            "ca_bundle_path": str(network.get("caBundlePath") or ""),
        },
        "categories": categories,
        "custom_domains": _normalize_domains(network.get("customDomains"), strict=False),
        "enforcement_boundary": (
            "Applied to gm-science native HTTP tools, remote MCP registration, explicit Compute health checks, "
            "and package configuration for managed local runs. It is not process-level sandbox isolation."
        ),
    }


def _public_compute_targets(config: Mapping[str, Any], *, environ: Mapping[str, str]) -> list[dict[str, Any]]:
    execution = _mapping(_science(config).get("execution"))
    local_enabled = _bool(execution.get("enabled"), True)
    targets: list[dict[str, Any]] = [
        {
            "id": "local",
            "type": "local",
            "name": "This computer",
            "enabled": local_enabled,
            "configured": True,
            "executable": local_enabled,
            "status": "ready" if local_enabled else "disabled",
            "status_detail": "Managed local Python TaskRun." if local_enabled else "Disabled in execution settings.",
            "metadata": {},
        },
        _public_managed_target(
            target_id="modal",
            target_type="cloud_provider",
            name="Modal",
            configured=bool(str(environ.get("MODAL_TOKEN_ID") or "").strip() and str(environ.get("MODAL_TOKEN_SECRET") or "").strip()),
            detail="Serverless GPU provider; execution adapter is not implemented.",
        ),
        _public_managed_target(
            target_id="nvidia_bionemo_nim",
            target_type="model_endpoint",
            name="NVIDIA BioNeMo NIM",
            configured=bool(str(environ.get("NVIDIA_API_KEY") or "").strip()),
            detail="Scientific model endpoint; execution adapter is not implemented.",
        ),
    ]
    for target_id, raw in sorted(_compute_targets(config).items(), key=lambda item: str(item[0]).casefold()):
        target = _mapping(raw)
        target_type = str(target.get("type") or "")
        enabled = _bool(target.get("enabled"), True)
        configured = _target_configured(target)
        if not enabled:
            status = "disabled"
            detail = "Disabled in Compute settings."
        elif not configured:
            status = "needs_configuration"
            detail = "Required Compute Target fields are missing."
        else:
            status = "unavailable"
            detail = "Configured; remote execution adapter is not implemented."
        metadata: dict[str, Any]
        if target_type == "ssh":
            metadata = {
                "host": str(target.get("host") or ""),
                "port": int(target.get("port") or 22),
                "username": str(target.get("username") or ""),
                "identity_configured": bool(str(target.get("identityFile") or "").strip()),
            }
        else:
            metadata = {
                "url": _public_url(str(target.get("url") or "")),
                "health_path": str(target.get("healthPath") or "/health"),
                "api_key_configured": bool(str(target.get("apiKey") or "").strip()),
            }
        targets.append(
            {
                "id": str(target_id),
                "type": target_type,
                "name": str(target.get("name") or target_id),
                "enabled": enabled,
                "configured": configured,
                "executable": False,
                "status": status,
                "status_detail": detail,
                "metadata": metadata,
            }
        )
    return targets


def _public_managed_target(
    *,
    target_id: str,
    target_type: str,
    name: str,
    configured: bool,
    detail: str,
) -> dict[str, Any]:
    return {
        "id": target_id,
        "type": target_type,
        "name": name,
        "enabled": True,
        "configured": configured,
        "executable": False,
        "status": "unavailable" if configured else "needs_configuration",
        "status_detail": detail,
        "metadata": {},
    }


def _apply_permission_update(config: dict[str, Any], raw: Any, *, now: str) -> None:
    if not isinstance(raw, Mapping):
        raise ValueError("Field 'permission_grants' must be a JSON object.")
    unknown = sorted(set(raw).difference(_PERMISSION_IDS))
    if unknown:
        raise ValueError(f"Unknown registry permissions: {', '.join(unknown)}")
    permissions = _mutable_mapping(_infrastructure(config).get("permissions"), "science.infrastructure.permissions")
    for permission_id, granted in raw.items():
        if not isinstance(granted, bool):
            raise ValueError(f"Permission '{permission_id}' must be a boolean.")
        permissions[str(permission_id)] = {
            "granted": granted,
            "source": "user",
            "updatedAt": now,
        }


def _apply_network_update(config: dict[str, Any], raw: Any) -> None:
    if not isinstance(raw, Mapping):
        raise ValueError("Field 'network' must be a JSON object.")
    unknown = sorted(set(raw).difference(_NETWORK_UPDATE_FIELDS))
    if unknown:
        raise ValueError(f"Unsupported network fields: {', '.join(unknown)}")
    network = _mutable_mapping(_science(config).get("network"), "science.network")
    scalar_fields = {
        "enabled": "enabled",
        "enforce_allowlist": "enforceAllowlist",
        "allow_private_networks": "allowPrivateNetworks",
    }
    for public_name, stored_name in scalar_fields.items():
        if public_name not in raw:
            continue
        value = raw[public_name]
        if not isinstance(value, bool):
            raise ValueError(f"Network field '{public_name}' must be a boolean.")
        network[stored_name] = value
    url_fields = {
        "conda_channel_mirror": "condaChannelMirror",
        "python_package_index": "pythonPackageIndex",
    }
    for public_name, stored_name in url_fields.items():
        if public_name not in raw:
            continue
        value = _bounded_text(raw[public_name], public_name)
        network[stored_name] = _sanitize_stored_url(value) if value else ""
    if "ca_bundle_path" in raw:
        network["caBundlePath"] = _bounded_text(raw["ca_bundle_path"], "ca_bundle_path")
    if "category_enabled" in raw:
        categories = raw["category_enabled"]
        if not isinstance(categories, Mapping):
            raise ValueError("Network field 'category_enabled' must be a JSON object.")
        allowed_ids = _NETWORK_CATEGORY_IDS | {"configured_connectors"}
        unknown_categories = sorted(set(categories).difference(allowed_ids))
        if unknown_categories:
            raise ValueError(f"Unknown Network categories: {', '.join(unknown_categories)}")
        category_config = _mutable_mapping(network.get("categoryEnabled"), "science.network.categoryEnabled")
        for category_id, enabled in categories.items():
            if not isinstance(enabled, bool):
                raise ValueError(f"Network category '{category_id}' must be a boolean.")
            category_config[str(category_id)] = enabled
    if "custom_domains" in raw:
        network["customDomains"] = _normalize_domains(raw["custom_domains"], strict=True)


def _apply_compute_target_update(config: dict[str, Any], raw: Any) -> None:
    if not isinstance(raw, Mapping):
        raise ValueError("Field 'compute_target' must be a JSON object.")
    operation = str(raw.get("operation") or "").strip().lower()
    targets = _compute_targets_mutable(config)
    if operation == "remove":
        target_id = str(raw.get("id") or "").strip()
        if target_id in _BUILTIN_TARGET_IDS:
            raise ValueError(f"Built-in Compute Target '{target_id}' cannot be removed.")
        if target_id not in targets:
            raise ValueError(f"Compute Target '{target_id}' was not found.")
        del targets[target_id]
        return
    if operation != "upsert":
        raise ValueError("Compute Target operation must be upsert or remove.")
    target_raw = raw.get("target")
    if not isinstance(target_raw, Mapping):
        raise ValueError("Compute Target upsert requires a target object.")
    target_id = str(target_raw.get("id") or "").strip().lower()
    if not _TARGET_ID_PATTERN.fullmatch(target_id) or target_id in _BUILTIN_TARGET_IDS:
        raise ValueError("Compute Target id must be a non-reserved lowercase identifier.")
    target_type = str(target_raw.get("type") or "").strip().lower()
    if target_type not in {"ssh", "model_endpoint"}:
        raise ValueError("Compute Target type must be ssh or model_endpoint.")
    name = _bounded_text(target_raw.get("name"), "compute target name")
    if not name:
        raise ValueError("Compute Target name is required.")
    enabled = target_raw.get("enabled", True)
    if not isinstance(enabled, bool):
        raise ValueError("Compute Target enabled must be a boolean.")
    existing = _mapping(targets.get(target_id))
    if target_type == "ssh":
        host = _normalize_hostname(target_raw.get("host"))
        if not host:
            raise ValueError("SSH Compute Target host is required.")
        port = _bounded_port(target_raw.get("port", 22))
        username = _bounded_text(target_raw.get("username"), "SSH username")
        identity_file = (
            _bounded_text(target_raw.get("identity_file"), "SSH identity file")
            if "identity_file" in target_raw
            else str(existing.get("identityFile") or "")
        )
        targets[target_id] = {
            "type": target_type,
            "name": name,
            "enabled": enabled,
            "host": host,
            "port": port,
            "username": username,
            "identityFile": identity_file,
        }
        return
    url = _bounded_text(target_raw.get("url"), "model endpoint URL")
    if not url:
        raise ValueError("Model endpoint URL is required.")
    sanitized_url = _sanitize_stored_url(url)
    health_path = _bounded_text(target_raw.get("health_path", "/health"), "health path") or "/health"
    if not health_path.startswith("/") or "?" in health_path or "#" in health_path:
        raise ValueError("Model endpoint health path must start with '/' and contain no query or fragment.")
    api_key = str(existing.get("apiKey") or "")
    if "api_key" in target_raw:
        api_key = _apply_secret_value(api_key, target_raw["api_key"], field_name="compute target api_key")
    targets[target_id] = {
        "type": target_type,
        "name": name,
        "enabled": enabled,
        "url": sanitized_url,
        "healthPath": health_path,
        "apiKey": api_key,
    }


def _apply_secret_value(current: str, raw: Any, *, field_name: str) -> str:
    if not isinstance(raw, Mapping):
        raise ValueError(f"{field_name} must be a JSON object.")
    operation = str(raw.get("operation") or "").strip().lower()
    if operation == "remove":
        return ""
    if operation != "replace":
        raise ValueError(f"{field_name} operation must be replace or remove.")
    value = _bounded_text(raw.get("value"), field_name)
    if not value:
        raise ValueError(f"{field_name} replace operation requires a non-empty value.")
    return value


def _permission_config(config: Mapping[str, Any]) -> Mapping[str, Any]:
    return _mapping(_infrastructure(config).get("permissions"))


def _network_config(config: Mapping[str, Any]) -> Mapping[str, Any]:
    return _mapping(_science(config).get("network"))


def _compute_targets(config: Mapping[str, Any]) -> Mapping[str, Any]:
    return _mapping(_mapping(_science(config).get("compute")).get("targets"))


def _science(config: Mapping[str, Any]) -> Mapping[str, Any]:
    return _mapping(config.get("science"))


def _infrastructure(config: Mapping[str, Any]) -> Mapping[str, Any]:
    return _mapping(_science(config).get("infrastructure"))


def _compute_targets_mutable(config: dict[str, Any]) -> dict[str, Any]:
    compute = _mutable_mapping(_science_mutable(config).get("compute"), "science.compute")
    return _mutable_mapping(compute.get("targets"), "science.compute.targets")


def _science_mutable(config: dict[str, Any]) -> dict[str, Any]:
    return _mutable_mapping(config.get("science"), "science")


def _configured_remote_mcp_domains(config: Mapping[str, Any]) -> list[str]:
    tools = _mapping(config.get("tools"))
    servers = _mapping(tools.get("mcpServers"))
    domains: list[str] = []
    for raw in servers.values():
        url = str(_mapping(raw).get("url") or "").strip()
        if not url:
            continue
        try:
            hostname = (urlsplit(url).hostname or "").lower()
        except ValueError:
            continue
        if hostname:
            domains.append(hostname)
    return list(dict.fromkeys(domains))


def _configured_package_mirror_domains(config: Mapping[str, Any]) -> list[str]:
    """Return validated hostnames for configured package mirror URLs."""

    network = _network_config(config)
    domains: list[str] = []
    for key in ("condaChannelMirror", "pythonPackageIndex"):
        url = str(network.get(key) or "").strip()
        if not url:
            continue
        try:
            hostname = (urlsplit(url).hostname or "").lower()
        except ValueError:
            continue
        if hostname:
            domains.append(hostname)
    return list(dict.fromkeys(domains))


def _normalize_domains(raw: Any, *, strict: bool) -> list[str]:
    if raw is None:
        return []
    if not isinstance(raw, (list, tuple)):
        if strict:
            raise ValueError("Network custom_domains must be an array.")
        return []
    domains: list[str] = []
    for value in raw:
        domain = str(value or "").strip().lower().rstrip(".")
        if not domain:
            continue
        valid = (
            len(domain) <= 253
            and "://" not in domain
            and "/" not in domain
            and "?" not in domain
            and "#" not in domain
            and bool(_HOST_PATTERN.fullmatch(domain))
            and domain not in {"*", "*."}
        )
        if not valid:
            if strict:
                raise ValueError(f"Invalid Network domain pattern: {domain}")
            continue
        domains.append(domain)
    return list(dict.fromkeys(domains))


def _domain_matches(hostname: str, pattern: str) -> bool:
    if pattern.startswith("*."):
        suffix = pattern[2:]
        return hostname.endswith("." + suffix) and hostname != suffix
    return hostname == pattern or hostname.endswith("." + pattern)


def _is_private_hostname(hostname: str) -> bool:
    if hostname == "localhost" or hostname.endswith(".localhost"):
        return True
    try:
        address = ipaddress.ip_address(hostname)
    except ValueError:
        return False
    return bool(
        address.is_private
        or address.is_loopback
        or address.is_link_local
        or address.is_reserved
        or address.is_unspecified
    )


def _sanitize_stored_url(url: str) -> str:
    _validate_public_http_url(url, "model endpoint URL")
    parsed = urlsplit(url)
    hostname = parsed.hostname or ""
    if ":" in hostname:
        hostname = f"[{hostname}]"
    port = f":{parsed.port}" if parsed.port is not None else ""
    return urlunsplit((parsed.scheme, hostname + port, parsed.path.rstrip("/"), "", ""))


def _public_url(url: str) -> str:
    if not url:
        return ""
    try:
        return _sanitize_stored_url(url)
    except ValueError:
        return ""


def _validate_public_http_url(url: str, field_name: str) -> None:
    try:
        parsed = urlsplit(url)
    except ValueError as exc:
        raise ValueError(f"{field_name} must be a valid HTTP(S) URL.") from exc
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError(f"{field_name} must be a valid HTTP(S) URL.")


def _normalize_hostname(raw: Any) -> str:
    host = str(raw or "").strip().lower().rstrip(".")
    if not host or len(host) > 253 or not _HOST_PATTERN.fullmatch(host) or "*" in host:
        return ""
    return host


def _target_configured(target: Mapping[str, Any]) -> bool:
    target_type = str(target.get("type") or "")
    if target_type == "ssh":
        return bool(str(target.get("host") or "").strip())
    if target_type == "model_endpoint":
        return bool(str(target.get("url") or "").strip())
    return False


def _health_payload(
    target_id: str,
    status: str,
    reachable: bool,
    executable: bool,
    detail: str,
) -> dict[str, Any]:
    return {
        "target_id": target_id,
        "status": status,
        "reachable": reachable,
        "executable": executable,
        "detail": detail,
        "checked_at": _iso_now(),
    }


def _safe_error(exc: Exception) -> str:
    name = type(exc).__name__
    return f"Connectivity check failed ({name})."


def _bounded_text(raw: Any, field_name: str) -> str:
    value = str(raw or "").strip()
    if len(value) > _MAX_TEXT or any(ord(char) < 32 for char in value):
        raise ValueError(f"{field_name} must be at most {_MAX_TEXT} printable characters.")
    return value


def _bounded_port(raw: Any) -> int:
    try:
        port = int(raw)
    except (TypeError, ValueError) as exc:
        raise ValueError("SSH port must be an integer.") from exc
    if port < 1 or port > 65535:
        raise ValueError("SSH port must be between 1 and 65535.")
    return port


def _mutable_mapping(value: Any, field_name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"gm-science configuration field '{field_name}' must be an object.")
    return value


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _bool(value: Any, default: bool) -> bool:
    return value if isinstance(value, bool) else default


def _iso_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()
