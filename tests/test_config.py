"""Unit tests for jsoncrm.config."""

import json
import sys
from pathlib import Path


from jsoncrm.config import Config


def test_default_config_has_marketing_stages():
    cfg = Config.from_file(path="/dev/null/nonexistent.json")
    stages = cfg.pipeline_stages
    assert [s["name"] for s in stages] == ["leads", "prospects", "customers"]
    assert stages[0]["file"] == "leads.json"


def test_default_config_has_marketing_scores():
    cfg = Config.from_file()
    assert cfg.score_order == {
        "⭐": 1,
        "⭐⭐": 2,
        "⭐⭐⭐": 3,
        "⭐⭐⭐⭐": 4,
        "⭐⭐⭐⭐⭐": 5,
    }
    assert cfg.disqualified_score == "❌"


def test_default_config_identity():
    cfg = Config.from_file()
    assert cfg.identity_primary == "linkedin_url"
    assert cfg.identity_fallback == ["id"]


def test_default_config_blocklist():
    cfg = Config.from_file()
    assert cfg.blocklist_file == "competitors.json"
    assert cfg.blocklist_match_fields == ["company", "name"]


def test_custom_config_override(tmp_path):
    config_path = tmp_path / "custom.json"
    config_path.write_text(
        json.dumps(
            {
                "pipeline": {
                    "stages": [
                        {"name": "candidates", "file": "candidates.json"},
                        {"name": "hired", "file": "hired.json"},
                    ]
                },
                "scores": {"order": ["A", "B", "C"], "disqualified": "X"},
            }
        )
    )
    cfg = Config.from_file(path=str(config_path))
    assert [s["name"] for s in cfg.pipeline_stages] == ["candidates", "hired"]
    assert cfg.score_order == {"A": 1, "B": 2, "C": 3}
    assert cfg.disqualified_score == "X"


def test_custom_config_merges_missing_keys(tmp_path):
    """Keys not overridden should keep their default values."""
    config_path = tmp_path / "partial.json"
    config_path.write_text(
        json.dumps(
            {
                "scores": {"order": ["🧊", "🔥"]},
            }
        )
    )
    cfg = Config.from_file(path=str(config_path))
    # Pipeline should still be default
    assert [s["name"] for s in cfg.pipeline_stages] == ["leads", "prospects", "customers"]
    # Scores overridden
    assert cfg.score_order == {"🧊": 1, "🔥": 2}
    # Disqualified kept default
    assert cfg.disqualified_score == "❌"


def test_apply_config_rebinds_schema(tmp_path):
    """Loading a custom config and applying it should rebind schema constants."""
    import jsoncrm.schema as schema

    config_path = tmp_path / "investor.json"
    config_path.write_text(
        json.dumps(
            {
                "pipeline": {
                    "stages": [
                        {"name": "investors", "file": "investors.json"},
                        {"name": "committed", "file": "committed.json"},
                    ]
                },
                "scores": {"order": ["🧊", "🔥"]},
                "blocklist": {"file": "blocked.json"},
            }
        )
    )
    cfg = Config.from_file(path=str(config_path))
    schema.apply_config(cfg)

    assert [name for name, _ in schema.PIPELINE_FILES] == ["investors", "committed"]
    assert schema.COMPETITORS_FILE.name == "blocked.json"
    assert schema.SCORE_ORDER == {"🧊": 1, "🔥": 2}

    # Restore defaults so other tests aren't affected
    schema.apply_config(Config.from_file())
