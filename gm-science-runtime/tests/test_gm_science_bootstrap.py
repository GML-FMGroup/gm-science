from __future__ import annotations

import json
from pathlib import Path

from openppx.gm_science.bootstrap import (
    GM_SCIENCE_DEFAULT_AGENT_NAME,
    ensure_gm_science_initialized,
)
from openppx.core.provider_registry import find_provider_spec


EXPECTED_CODEX_MODEL = "openai-codex/gpt-5.5"


def test_openai_codex_provider_defaults_to_supported_chatgpt_model() -> None:
    provider = find_provider_spec("openai_codex")

    assert provider is not None
    assert provider.default_model == EXPECTED_CODEX_MODEL


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
    assert config["providers"]["openai_codex"]["model"] == EXPECTED_CODEX_MODEL
    assert config["providers"]["google"]["enabled"] is False
    literature = config["science"]["literature"]
    assert literature["defaultSources"] == ["arxiv", "pubmed", "openalex"]
    assert literature["arxiv"]["apiBase"] == "https://export.arxiv.org/api/query"
    assert literature["pubmed"]["tool"] == "gm-science"
    assert literature["pubmed"]["email"] == ""
    assert literature["openalex"]["apiKey"] == ""
    project_defaults = config["science"]["projectDefaults"]
    assert project_defaults["enabledSkills"] == ["literature-review"]
    assert project_defaults["enabledConnectors"] == ["arxiv", "pubmed", "openalex"]
    assert project_defaults["enabledSpecialists"] == ["paper_reader", "research_reviewer"]
    specialists = config["science"]["specialists"]
    assert specialists["enabled"] is True
    assert specialists["model"] == ""
    assert specialists["paperReader"]["maxPapers"] == 6
    assert specialists["reviewer"]["reviewGate"] == "annotate"

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


def test_bootstrap_persists_missing_science_defaults_into_existing_config(tmp_path: Path) -> None:
    first = ensure_gm_science_initialized(root_dir=tmp_path)
    config = json.loads(first.config_path.read_text(encoding="utf-8"))
    config.pop("science")
    first.config_path.write_text(json.dumps(config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    ensure_gm_science_initialized(root_dir=tmp_path)

    saved = json.loads(first.config_path.read_text(encoding="utf-8"))
    assert saved["science"]["literature"]["defaultSources"] == ["arxiv", "pubmed", "openalex"]
    assert saved["science"]["literature"]["pubmed"]["email"] == ""
    assert saved["science"]["literature"]["openalex"]["apiKey"] == ""
    assert saved["science"]["projectDefaults"]["enabledSpecialists"] == [
        "paper_reader",
        "research_reviewer",
    ]
    assert saved["science"]["specialists"]["reviewer"]["reviewGate"] == "annotate"
