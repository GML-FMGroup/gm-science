from __future__ import annotations

import json
from pathlib import Path

from openppx.gm_science.specialists.config import (
    load_specialist_config,
    parse_specialist_config,
)


def test_specialist_config_uses_science_defaults() -> None:
    config = parse_specialist_config({})

    assert config.enabled is True
    assert config.model == ""
    assert config.max_skill_chars == 60_000
    assert config.custom == ()
    assert config.project_defaults.enabled_skills == ("literature-review",)
    assert config.project_defaults.enabled_connectors == ("arxiv", "pubmed", "openalex")
    assert config.project_defaults.enabled_specialists == ("paper_reader", "research_reviewer")
    assert config.paper_reader.enabled is True
    assert config.paper_reader.auto_dispatch is True
    assert config.paper_reader.max_papers == 6
    assert config.paper_reader.max_source_chars == 30_000
    assert config.reviewer.enabled is True
    assert config.reviewer.auto_dispatch is True
    assert config.reviewer.review_gate == "annotate"
    assert config.reviewer.max_findings == 20
    assert config.reviewer.max_source_chars == 60_000


def test_specialist_config_normalizes_lists_and_bounds() -> None:
    config = parse_specialist_config(
        {
            "science": {
                "projectDefaults": {
                    "enabledSkills": [" literature-review ", "literature-review", "custom-skill", ""],
                    "enabledConnectors": ["PUBMED", "pubmed", "custom-source"],
                    "enabledSpecialists": [
                        "research_reviewer",
                        "unknown",
                        "paper_reader",
                        "research_reviewer",
                    ],
                },
                "specialists": {
                    "enabled": False,
                    "model": " openai-codex/gpt-5.5 ",
                    "paperReader": {
                        "enabled": False,
                        "autoDispatch": False,
                        "maxPapers": 100,
                        "maxSourceChars": 10,
                    },
                    "reviewer": {
                        "enabled": False,
                        "autoDispatch": False,
                        "reviewGate": "invalid",
                        "maxFindings": 0,
                        "maxSourceChars": 999_999,
                    },
                },
            }
        }
    )

    assert config.enabled is False
    assert config.model == "openai-codex/gpt-5.5"
    assert config.project_defaults.enabled_skills == ("literature-review", "custom-skill")
    assert config.project_defaults.enabled_connectors == ("pubmed", "custom-source")
    assert config.project_defaults.enabled_specialists == (
        "research_reviewer",
        "unknown",
        "paper_reader",
    )
    assert config.paper_reader.enabled is False
    assert config.paper_reader.auto_dispatch is False
    assert config.paper_reader.max_papers == 20
    assert config.paper_reader.max_source_chars == 1_000
    assert config.reviewer.enabled is False
    assert config.reviewer.auto_dispatch is False
    assert config.reviewer.review_gate == "annotate"
    assert config.reviewer.max_findings == 1
    assert config.reviewer.max_source_chars == 200_000


def test_specialist_config_parses_custom_definitions_and_keeps_diagnostics() -> None:
    config = parse_specialist_config(
        {
            "science": {
                "specialists": {
                    "maxSkillChars": 400,
                    "custom": {
                        "literature_scout": {
                            "title": "Literature Scout",
                            "description": "Find and compare relevant papers.",
                            "autoDispatch": True,
                            "model": "openai-codex/gpt-5.5",
                            "instructions": "Prefer primary sources.",
                            "skills": ["Literature-Review", "literature-review"],
                            "connectors": ["MCP:Lab", "mcp:lab", "PubMed"],
                        },
                        "Bad ID": {},
                        "": "not-an-object",
                    },
                }
            }
        }
    )

    assert config.max_skill_chars == 1_000
    assert [item.name for item in config.custom] == [
        "invalid_specialist_1",
        "Bad ID",
        "literature_scout",
    ]
    invalid, bad_id, scout = config.custom
    assert "Agent ID" in invalid.configuration_error
    assert "must be an object" in invalid.configuration_error
    assert "Agent ID" in bad_id.configuration_error
    assert "description is required" in bad_id.configuration_error
    assert scout.title == "Literature Scout"
    assert scout.auto_dispatch is True
    assert scout.model == "openai-codex/gpt-5.5"
    assert scout.instructions == "Prefer primary sources."
    assert scout.skills == ("Literature-Review",)
    assert scout.connectors == ("MCP:Lab", "PubMed")
    assert scout.configuration_error == ""


def test_specialist_public_status_does_not_expose_internal_configuration() -> None:
    config = parse_specialist_config(
        {
            "science": {
                "specialists": {
                    "custom": {
                        "literature_scout": {
                            "description": "Find papers.",
                            "instructions": "This must remain private to the runtime prompt.",
                        }
                    }
                }
            }
        }
    )

    assert config.public_statuses() == {
        "paper_reader": {"enabled": True, "auto_dispatch": True},
        "research_reviewer": {
            "enabled": True,
            "auto_dispatch": True,
            "review_gate": "annotate",
        },
        "literature_scout": {"enabled": True, "auto_dispatch": False},
    }
    assert "instructions" not in json.dumps(config.public_statuses())


def test_load_specialist_config_reads_agent_config(tmp_path: Path) -> None:
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "science": {
                    "specialists": {
                        "model": "openai-codex/custom-model",
                        "reviewer": {"reviewGate": "off"},
                    }
                }
            }
        ),
        encoding="utf-8",
    )

    config = load_specialist_config(config_path)

    assert config.model == "openai-codex/custom-model"
    assert config.reviewer.review_gate == "off"
