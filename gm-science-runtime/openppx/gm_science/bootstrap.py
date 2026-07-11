"""Bootstrap helpers for the local gm-science workspace."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..core.config import (
    apply_agent_privilege_level_defaults,
    default_config,
    default_runtime_config,
    load_config,
    save_config,
    save_runtime_config,
)
from ..core.provider_registry import find_provider_spec
from .paths import get_gm_science_data_dir

GM_SCIENCE_DEFAULT_AGENT_NAME = "science-research"
GM_SCIENCE_DEFAULT_PROVIDER = "openai_codex"
GM_SCIENCE_DEFAULT_PRIVILEGE_LEVEL = "medium"
_LEGACY_OPENAI_CODEX_DEFAULT_MODEL = "openai-codex/gpt-5.1-codex"


@dataclass(frozen=True)
class GmScienceBootstrapResult:
    """Resolved paths after gm-science workspace initialization."""

    agent_name: str
    data_dir: Path
    config_path: Path
    runtime_config_path: Path
    global_config_path: Path
    workspace_path: Path


def ensure_gm_science_initialized(root_dir: Path | str | None = None) -> GmScienceBootstrapResult:
    """Create the default gm-science data layout if it does not already exist."""

    data_dir = _resolve_data_dir(root_dir)
    agent_name = GM_SCIENCE_DEFAULT_AGENT_NAME
    agent_home = data_dir / agent_name
    config_path = agent_home / "config.json"
    runtime_config_path = agent_home / "runtime.json"
    global_config_path = data_dir / "global_config.json"
    workspace_path = data_dir / "workspaces" / agent_name

    data_dir.mkdir(parents=True, exist_ok=True)
    workspace_path.mkdir(parents=True, exist_ok=True)

    if not config_path.exists():
        config = _build_default_agent_config(agent_name=agent_name, workspace_path=workspace_path)
        save_config(config, config_path=config_path)
    else:
        config = load_config(config_path=config_path)
        if _migrate_legacy_openai_codex_default(config):
            save_config(config, config_path=config_path)
        configured_workspace = str(config.get("agent", {}).get("workspace", "")).strip()
        if configured_workspace:
            workspace_path = Path(configured_workspace).expanduser().resolve(strict=False)
            workspace_path.mkdir(parents=True, exist_ok=True)

    if not runtime_config_path.exists():
        save_runtime_config(default_runtime_config(), runtime_config_path=runtime_config_path)

    _init_agent_support_files(agent_home)
    _ensure_global_agent_enabled(global_config_path=global_config_path, agent_name=agent_name)

    return GmScienceBootstrapResult(
        agent_name=agent_name,
        data_dir=data_dir,
        config_path=config_path,
        runtime_config_path=runtime_config_path,
        global_config_path=global_config_path,
        workspace_path=workspace_path,
    )


def _resolve_data_dir(root_dir: Path | str | None) -> Path:
    """Resolve the gm-science data directory from an explicit path or environment defaults."""

    raw = Path(root_dir).expanduser() if root_dir is not None else get_gm_science_data_dir()
    return raw.resolve(strict=False)


def _build_default_agent_config(*, agent_name: str, workspace_path: Path) -> dict[str, Any]:
    """Build the first-run config for the default science research agent."""

    config = default_config()
    agent = config.setdefault("agent", {})
    agent["name"] = agent_name
    agent["workspace"] = str(workspace_path)
    apply_agent_privilege_level_defaults(config, privilege_level=GM_SCIENCE_DEFAULT_PRIVILEGE_LEVEL)
    _prefer_provider(config, GM_SCIENCE_DEFAULT_PROVIDER)
    return config


def _prefer_provider(config: dict[str, Any], provider_name: str) -> None:
    """Enable one provider and disable all other known providers in the config."""

    providers = config.get("providers")
    if not isinstance(providers, dict):
        return

    selected = provider_name if find_provider_spec(provider_name) else "openai"
    for name, provider_config in providers.items():
        if isinstance(provider_config, dict):
            provider_config["enabled"] = name == selected


def _migrate_legacy_openai_codex_default(config: dict[str, Any]) -> bool:
    """Upgrade the obsolete generated Codex model without changing custom models."""

    providers = config.get("providers")
    if not isinstance(providers, dict):
        return False
    codex_config = providers.get(GM_SCIENCE_DEFAULT_PROVIDER)
    if not isinstance(codex_config, dict):
        return False
    if codex_config.get("model") != _LEGACY_OPENAI_CODEX_DEFAULT_MODEL:
        return False

    provider = find_provider_spec(GM_SCIENCE_DEFAULT_PROVIDER)
    if provider is None:
        return False
    codex_config["model"] = provider.default_model
    return True


def _init_agent_support_files(agent_home: Path) -> None:
    """Create lightweight agent support directories expected by openppx tooling."""

    agent_home.mkdir(parents=True, exist_ok=True)
    (agent_home / "skills").mkdir(parents=True, exist_ok=True)
    (agent_home / "memory").mkdir(parents=True, exist_ok=True)
    readme = agent_home / "AGENTS.md"
    if not readme.exists():
        readme.write_text(
            "# gm-science default agent\n\n"
            "This is the local science-research agent home for gm-science.\n",
            encoding="utf-8",
        )


def _ensure_global_agent_enabled(*, global_config_path: Path, agent_name: str) -> None:
    """Ensure the default agent is present and enabled in global_config.json."""

    entries = _load_global_agent_entries(global_config_path)
    for entry in entries:
        if entry["name"] != agent_name:
            continue
        entry["enabled"] = True
        _save_global_agent_entries(global_config_path=global_config_path, entries=entries)
        return

    entries.append({"name": agent_name, "enabled": True})
    _save_global_agent_entries(global_config_path=global_config_path, entries=entries)


def _load_global_agent_entries(global_config_path: Path) -> list[dict[str, Any]]:
    """Load normalized global agent entries from one global config file."""

    if not global_config_path.exists():
        return []
    try:
        raw = json.loads(global_config_path.read_text(encoding="utf-8"))
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

    normalized: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in entries:
        name = ""
        enabled = True
        if isinstance(item, str):
            name = item.strip()
        elif isinstance(item, dict):
            name = str(item.get("name") or item.get("id") or "").strip()
            enabled = item.get("enabled") is not False
        if not name or name in seen:
            continue
        seen.add(name)
        normalized.append({"name": name, "enabled": enabled})
    return normalized


def _save_global_agent_entries(*, global_config_path: Path, entries: list[dict[str, Any]]) -> None:
    """Persist normalized global agent entries."""

    global_config_path.parent.mkdir(parents=True, exist_ok=True)
    global_config_path.write_text(
        json.dumps({"agents": entries}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
