from __future__ import annotations

from openppx.gm_science.literature.config import parse_literature_config


def test_parse_literature_config_normalizes_sources_and_numeric_bounds() -> None:
    config = parse_literature_config(
        {
            "science": {
                "literature": {
                    "defaultSources": ["pubmed", "unknown", "arxiv", "pubmed", "openalex"],
                    "maxResultsPerSource": 100,
                    "requestTimeoutSeconds": 0,
                    "cacheTtlSeconds": -1,
                    "arxiv": {"enabled": True, "apiBase": "https://arxiv.test/query", "minIntervalSeconds": -2},
                    "pubmed": {
                        "enabled": True,
                        "apiBase": "https://pubmed.test",
                        "tool": "gm-science-test",
                        "email": "researcher@example.test",
                        "apiKey": "pubmed-secret",
                        "minIntervalSeconds": 0.1,
                    },
                    "openalex": {
                        "enabled": True,
                        "apiBase": "https://openalex.test",
                        "apiKey": "openalex-secret",
                    },
                }
            }
        }
    )

    assert config.default_sources == ("pubmed", "arxiv", "openalex")
    assert config.max_results_per_source == 25
    assert config.request_timeout_seconds == 1.0
    assert config.cache_ttl_seconds == 0
    assert config.sources["arxiv"].min_interval_seconds == 0.0
    assert config.sources["pubmed"].tool == "gm-science-test"


def test_source_statuses_explain_missing_configuration_without_leaking_secrets() -> None:
    config = parse_literature_config(
        {
            "science": {
                "literature": {
                    "pubmed": {"enabled": True, "email": "", "apiKey": "pubmed-secret"},
                    "openalex": {"enabled": True, "apiKey": ""},
                }
            }
        }
    )

    statuses = config.public_source_statuses()

    assert statuses["arxiv"]["status"] == "ok"
    assert statuses["pubmed"]["status"] == "needs_configuration"
    assert statuses["pubmed"]["configuration_message"] == "Set science.literature.pubmed.email."
    assert statuses["openalex"]["status"] == "needs_configuration"
    assert statuses["openalex"]["configuration_message"] == "Set science.literature.openalex.apiKey."
    rendered = repr(statuses)
    assert "pubmed-secret" not in rendered
    assert "api_key" not in rendered.lower()
    assert "email" not in statuses["pubmed"]


def test_disabled_source_reports_disabled_before_configuration_requirements() -> None:
    config = parse_literature_config(
        {
            "science": {
                "literature": {
                    "pubmed": {"enabled": False, "email": ""},
                    "openalex": {"enabled": False, "apiKey": ""},
                }
            }
        }
    )

    statuses = config.public_source_statuses()

    assert statuses["pubmed"]["status"] == "disabled"
    assert statuses["openalex"]["status"] == "disabled"
