"""Smoke tests for jsoncrm package — isolated, no real data needed."""

import json
import sys
from pathlib import Path
from types import SimpleNamespace


import jsoncrm.tool as crm

TEST_DB = Path(__file__).parent / "test_db.json"


def reset_db():
    TEST_DB.write_text("[]\n")


def cleanup_db():
    TEST_DB.unlink(missing_ok=True)


def test_add_and_find():
    reset_db()
    try:
        # add
        crm.cmd_add(
            SimpleNamespace(
                database_file=str(TEST_DB),
                item_file=None,
                item_json='{"name":"Alice","linkedin_url":"https://linkedin.com/in/alice","company":"Acme"}',
                output_file=None,
            )
        )
        # find
        out = crm.load_json(TEST_DB)
        assert len(out) == 1
        assert out[0]["name"] == "Alice"
    finally:
        cleanup_db()


def test_update_and_delete():
    reset_db()
    try:
        crm.cmd_add(
            SimpleNamespace(
                database_file=str(TEST_DB),
                item_file=None,
                item_json='{"name":"Bob","linkedin_url":"https://linkedin.com/in/bob","company":"OldCo"}',
                output_file=None,
            )
        )
        crm.cmd_update(
            SimpleNamespace(
                database_file=str(TEST_DB),
                item_file=None,
                item_json='{"linkedin_url":"https://linkedin.com/in/bob","company":"NewCo"}',
                output_file=None,
            )
        )
        data = crm.load_json(TEST_DB)
        assert data[0]["company"] == "NewCo"

        crm.cmd_delete(
            SimpleNamespace(
                database_file=str(TEST_DB),
                item_file=None,
                item_json='{"linkedin_url":"https://linkedin.com/in/bob"}',
                output_file=None,
            )
        )
        data = crm.load_json(TEST_DB)
        assert len(data) == 0
    finally:
        cleanup_db()


def test_normalize_url():
    assert crm.normalize_url("https://LinkedIn.com/in/Alice/") == "https://linkedin.com/in/alice"
    assert crm.normalize_url(None) == ""


def test_score_value():
    assert crm.score_value("⭐⭐⭐⭐⭐") == 5
    assert crm.score_value("⭐") == 1
    assert crm.score_value("") == 0
    assert crm.score_value(None) == 0
