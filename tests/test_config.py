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


def test_scores_null_falls_back_to_default(tmp_path):
    """An explicit `"scores": null` means 'no override', same as omitting the key."""
    config_path = tmp_path / "null_scores.json"
    config_path.write_text(json.dumps({"scores": None}))
    cfg = Config.from_file(path=str(config_path))
    assert cfg.score_order == {
        "⭐": 1,
        "⭐⭐": 2,
        "⭐⭐⭐": 3,
        "⭐⭐⭐⭐": 4,
        "⭐⭐⭐⭐⭐": 5,
    }
    assert cfg.disqualified_score == "❌"


def test_scores_empty_order_falls_back_to_default(tmp_path):
    """An explicit empty `order` list means 'no override', same as omitting the key —
    not a config with zero valid scores."""
    config_path = tmp_path / "empty_order.json"
    config_path.write_text(json.dumps({"scores": {"order": []}}))
    cfg = Config.from_file(path=str(config_path))
    assert cfg.score_order == {
        "⭐": 1,
        "⭐⭐": 2,
        "⭐⭐⭐": 3,
        "⭐⭐⭐⭐": 4,
        "⭐⭐⭐⭐⭐": 5,
    }
    assert cfg.score_order_descending == ["⭐⭐⭐⭐⭐", "⭐⭐⭐⭐", "⭐⭐⭐", "⭐⭐", "⭐"]


def test_scores_empty_disqualified_falls_back_to_default(tmp_path):
    config_path = tmp_path / "empty_disqualified.json"
    config_path.write_text(json.dumps({"scores": {"disqualified": ""}}))
    cfg = Config.from_file(path=str(config_path))
    assert cfg.disqualified_score == "❌"


def test_context_resolves_custom_config_paths(tmp_path):
    from jsoncrm.context import CRMContext

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
    context = CRMContext.from_file(str(config_path))

    assert [name for name, _ in context.pipeline_files] == ["investors", "committed"]
    assert context.competitors_file.name == "blocked.json"
    assert context.score_order == {"🧊": 1, "🔥": 2}
    assert all(path.parent == tmp_path for _name, path in context.pipeline_files)
