from __future__ import annotations

import json
from pathlib import Path

from openppx.gm_science.bootstrap import (
    GM_SCIENCE_DEFAULT_AGENT_NAME,
    ensure_gm_science_initialized,
)


def test_bootstrap_creates_default_science_agent_with_openai_codex_provider(tmp_path: Path) -> None:
    result = ensure_gm_science_initialized(root_dir=tmp_path)

    assert result.agent_name == GM_SCIENCE_DEFAULT_AGENT_NAME
    assert result.data_dir == tmp_path
    assert result.config_path == tmp_path / GM_SCIENCE_DEFAULT_AGENT_NAME / "config.json"
    assert result.runtime_config_path == tmp_path / GM_SCIENCE_DEFAULT_AGENT_NAME / "runtime.json"
    assert result.global_config_path == tmp_path / "global_config.json"
    assert result.workspace_path == tmp_path / "workspaces" / GM_SCIENCE_DEFAULT_AGENT_NAME
    assert result.workspace_path.is_dir()

    global_config = json.loads(result.global_config_path.read_text(encoding="utf-8"))
    assert global_config == {"agents": [{"name": GM_SCIENCE_DEFAULT_AGENT_NAME, "enabled": True}]}

    config = json.loads(result.config_path.read_text(encoding="utf-8"))
    assert config["agent"]["name"] == GM_SCIENCE_DEFAULT_AGENT_NAME
    assert config["agent"]["privilegeLevel"] == "medium"
    assert config["agent"]["workspace"] == str(result.workspace_path)
    assert config["providers"]["openai_codex"]["enabled"] is True
    assert config["providers"]["google"]["enabled"] is False

    runtime_config = json.loads(result.runtime_config_path.read_text(encoding="utf-8"))
    assert isinstance(runtime_config["env"], dict)


def test_bootstrap_is_idempotent_and_does_not_overwrite_existing_agent_config(tmp_path: Path) -> None:
    first = ensure_gm_science_initialized(root_dir=tmp_path)
    config = json.loads(first.config_path.read_text(encoding="utf-8"))
    config["providers"]["openai_codex"]["model"] = "openai-codex/custom-research-model"
    first.config_path.write_text(json.dumps(config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    second = ensure_gm_science_initialized(root_dir=tmp_path)

    saved = json.loads(second.config_path.read_text(encoding="utf-8"))
    assert saved["providers"]["openai_codex"]["model"] == "openai-codex/custom-research-model"
    assert second == first
