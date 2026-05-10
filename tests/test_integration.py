#!/usr/bin/env python3
"""End-to-end tests for jsoncrm against the real CRM database (search)
and isolated test files (update, intake)."""

import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest


import jsoncrm.schema as _jsoncrm_schema
import jsoncrm.tool as _jsoncrm_tool
import jsoncrm.utils as _jsoncrm_utils

CRM_DIR = Path(__file__).parent / "fixtures"
TOOL = [sys.executable, "-m", "jsoncrm", "--config", str(CRM_DIR / ".crm.json")]
TEST_FILE = CRM_DIR / "test_leads.json"
TEST_INTAKE = CRM_DIR / "test_intake.json"
TEST_LINKEDIN_MCP_INTAKE = CRM_DIR / "test_mcp_intake.json"
TEST_SHUFFLE = CRM_DIR / "test_shuffle.json"
TEST_TOP = CRM_DIR / "test_top.json"
TEST_MERGE_SRC = CRM_DIR / "test_merge_src.json"
TEST_MERGE_DST = CRM_DIR / "test_merge_dst.json"
TEST_DEDUPE_SRC = CRM_DIR / "test_dedupe_src.json"
TEST_DEDUPE_LEADS = CRM_DIR / "test_dedupe_leads.json"
TEST_DEDUPE_PROSPECTS = CRM_DIR / "test_dedupe_prospects.json"
TEST_DEDUPE_CUSTOMERS = CRM_DIR / "test_dedupe_customers.json"
TEST_FILTER_COMPETITORS_SRC = CRM_DIR / "test_filter_competitors_src.json"
TEST_PROMOTE_SRC = CRM_DIR / "test_promote_src.json"
TEST_PROMOTE_DST = CRM_DIR / "test_promote_dst.json"
TEST_STATS_LEADS = CRM_DIR / "test_stats_leads.json"
TEST_STATS_PROSPECTS = CRM_DIR / "test_stats_prospects.json"
TEST_STATS_CUSTOMERS = CRM_DIR / "test_stats_customers.json"
TEST_FIND_QUERY = CRM_DIR / "test_find_query.json"
TEST_FIND_OUTPUT = CRM_DIR / "test_find_output.json"
TEST_DELETE_ITEM = CRM_DIR / "test_delete_item.json"
TEST_DELETE_OUTPUT = CRM_DIR / "test_delete_output.json"
TEST_VALIDATE_LEADS = CRM_DIR / "test_validate_leads.json"
TEST_VALIDATE_PROSPECTS = CRM_DIR / "test_validate_prospects.json"
TEST_VALIDATE_CUSTOMERS = CRM_DIR / "test_validate_customers.json"
TEST_RECENT_LEADS = CRM_DIR / "test_recent_leads.json"
TEST_RECENT_PROSPECTS = CRM_DIR / "test_recent_prospects.json"
TEST_RECENT_CUSTOMERS = CRM_DIR / "test_recent_customers.json"
TEST_DEMOTE_SRC = CRM_DIR / "test_demote_src.json"
TEST_DEMOTE_DST = CRM_DIR / "test_demote_dst.json"
TEST_LIST = CRM_DIR / "test_list.json"
PENDING_FILE = CRM_DIR / ".pending_update.json"

TEST_RECORDS = [
    {
        "name": "Alice Testerson",
        "position": "Head of Computational Chemistry",
        "company": "TestPharma Inc",
        "linkedin_url": "https://www.linkedin.com/in/alice-testerson/",
        "connected": False,
        "email": "alice@testpharma.com",
        "contacted_at": None,
        "source": "manual",
        "added": "2026-01-01",
        "score": "⭐⭐⭐⭐",
        "notes": "original notes",
    },
    {
        "name": "Bob Labguy",
        "id": "bob-1",
        "position": "Senior Scientist",
        "company": "MockBio Labs",
        "linkedin_url": "https://www.linkedin.com/in/bob-labguy/",
        "connected": True,
        "email": None,
        "contacted_at": None,
        "source": "post_likers",
        "added": "2026-02-15",
        "score": None,
        "notes": "",
    },
]

ALICE_URL = TEST_RECORDS[0]["linkedin_url"]
BOB_URL = TEST_RECORDS[1]["linkedin_url"]


def run(*args):
    result = subprocess.run([*TOOL, *args], capture_output=True, text=True)
    return result.stdout + result.stderr, result.returncode


def read_test_record(url):
    data = json.loads(TEST_FILE.read_text())
    for r in data:
        if r.get("linkedin_url", "").rstrip("/") == url.rstrip("/"):
            return r
    return None


@pytest.fixture(autouse=True)
def reset_test_files():
    TEST_FILE.write_text(json.dumps(TEST_RECORDS, indent=2, ensure_ascii=False) + "\n")
    yield
    TEST_FILE.unlink(missing_ok=True)
    TEST_INTAKE.unlink(missing_ok=True)
    TEST_LINKEDIN_MCP_INTAKE.unlink(missing_ok=True)
    TEST_SHUFFLE.unlink(missing_ok=True)
    TEST_TOP.unlink(missing_ok=True)
    TEST_MERGE_SRC.unlink(missing_ok=True)
    TEST_MERGE_DST.unlink(missing_ok=True)
    TEST_DEDUPE_SRC.unlink(missing_ok=True)
    TEST_DEDUPE_LEADS.unlink(missing_ok=True)
    TEST_DEDUPE_PROSPECTS.unlink(missing_ok=True)
    TEST_DEDUPE_CUSTOMERS.unlink(missing_ok=True)
    TEST_FILTER_COMPETITORS_SRC.unlink(missing_ok=True)
    TEST_PROMOTE_SRC.unlink(missing_ok=True)
    TEST_PROMOTE_DST.unlink(missing_ok=True)
    TEST_STATS_LEADS.unlink(missing_ok=True)
    TEST_STATS_PROSPECTS.unlink(missing_ok=True)
    TEST_STATS_CUSTOMERS.unlink(missing_ok=True)
    TEST_FIND_QUERY.unlink(missing_ok=True)
    TEST_FIND_OUTPUT.unlink(missing_ok=True)
    TEST_DELETE_ITEM.unlink(missing_ok=True)
    TEST_DELETE_OUTPUT.unlink(missing_ok=True)
    TEST_VALIDATE_LEADS.unlink(missing_ok=True)
    TEST_VALIDATE_PROSPECTS.unlink(missing_ok=True)
    TEST_VALIDATE_CUSTOMERS.unlink(missing_ok=True)
    TEST_RECENT_LEADS.unlink(missing_ok=True)
    TEST_RECENT_PROSPECTS.unlink(missing_ok=True)
    TEST_RECENT_CUSTOMERS.unlink(missing_ok=True)
    TEST_DEMOTE_SRC.unlink(missing_ok=True)
    TEST_DEMOTE_DST.unlink(missing_ok=True)
    TEST_LIST.unlink(missing_ok=True)
    PENDING_FILE.unlink(missing_ok=True)


# --- search (default: all fields) ---

def test_search_default_finds_by_company():
    out, _ = run("search", "Pfizer")
    assert "result(s)" in out
    assert "Pfizer" in out


def test_search_default_finds_by_name():
    out, _ = run("search", "Martin Bonde")
    assert "Martin Bonde" in out


def test_search_default_no_results_for_garbage():
    out, _ = run("search", "zzzznotaname999")
    assert "No results" in out


# --- find ---

def test_find_by_item_json():
    out, rc = run("find", "--database_file", str(TEST_FILE), "--item_json", '{"company":"TestPharma Inc"}')
    assert rc == 0
    assert "Alice Testerson" in out
    assert "Bob Labguy" not in out


def test_find_by_item_file_to_output_file():
    TEST_FIND_QUERY.write_text(json.dumps({"connected": True}, indent=2, ensure_ascii=False) + "\n")
    out, rc = run(
        "find",
        "--database_file", str(TEST_FILE),
        "--item_file", str(TEST_FIND_QUERY),
        "--output_file", str(TEST_FIND_OUTPUT),
    )
    assert rc == 0
    assert out == ""
    results = json.loads(TEST_FIND_OUTPUT.read_text())
    assert len(results) == 1
    assert results[0]["name"] == "Bob Labguy"


def test_find_no_matches_returns_empty_list():
    out, rc = run("find", "--database_file", str(TEST_FILE), "--item_json", '{"company":"NoSuchCo"}')
    assert rc == 0
    assert json.loads(out) == []


def test_find_multiple_field_match():
    out, rc = run(
        "find",
        "--database_file", str(TEST_FILE),
        "--item_json", '{"company":"TestPharma Inc","connected":false}',
    )
    assert rc == 0
    results = json.loads(out)
    assert len(results) == 1
    assert results[0]["name"] == "Alice Testerson"


def test_find_requires_single_item_source():
    TEST_FIND_QUERY.write_text(json.dumps({"company": "TestPharma Inc"}, indent=2, ensure_ascii=False) + "\n")
    out, rc = run(
        "find",
        "--database_file", str(TEST_FILE),
        "--item_file", str(TEST_FIND_QUERY),
        "--item_json", '{"company":"TestPharma Inc"}',
    )
    assert rc != 0
    assert "use only one of --item_file or --item_json" in out


def test_find_requires_item_input():
    out, rc = run("find", "--database_file", str(TEST_FILE))
    assert rc != 0
    assert "provide one of --item_file or --item_json" in out


def test_find_rejects_non_object_matcher():
    out, rc = run("find", "--database_file", str(TEST_FILE), "--item_json", '["not","an","object"]')
    assert rc != 0
    assert "find item must be a JSON object" in out


# --- add ---

def test_add_by_item_json():
    out, rc = run(
        "add",
        "--database_file", str(TEST_FILE),
        "--item_json", '{"name":"Cara Add","linkedin_url":"https://www.linkedin.com/in/cara-add/","company":"AddCo"}',
    )
    assert rc == 0
    assert "Cara Add" in out
    data = json.loads(TEST_FILE.read_text())
    assert any(r.get("name") == "Cara Add" for r in data)


def test_add_requires_identity():
    out, rc = run(
        "add",
        "--database_file", str(TEST_FILE),
        "--item_json", '{"name":"No Id Person"}',
    )
    assert rc != 0
    assert "requires at least one of 'id' or 'linkedin_url'" in out


def test_add_by_item_file_to_output_file():
    item = {
        "id": "dana-1",
        "name": "Dana File",
        "linkedin_url": "https://www.linkedin.com/in/dana-file/",
        "company": "FileCo",
    }
    TEST_FIND_QUERY.write_text(json.dumps(item, indent=2, ensure_ascii=False) + "\n")
    out, rc = run(
        "add",
        "--database_file", str(TEST_FILE),
        "--item_file", str(TEST_FIND_QUERY),
        "--output_file", str(TEST_FIND_OUTPUT),
    )
    assert rc == 0
    assert out == ""
    written = json.loads(TEST_FIND_OUTPUT.read_text())
    assert written["name"] == "Dana File"
    data = json.loads(TEST_FILE.read_text())
    assert any(r.get("id") == "dana-1" for r in data)


def test_add_requires_single_item_source():
    TEST_FIND_QUERY.write_text(
        json.dumps({"name": "Extra", "linkedin_url": "https://www.linkedin.com/in/extra/"}, indent=2, ensure_ascii=False) + "\n"
    )
    out, rc = run(
        "add",
        "--database_file", str(TEST_FILE),
        "--item_file", str(TEST_FIND_QUERY),
        "--item_json", '{"name":"Extra","linkedin_url":"https://www.linkedin.com/in/extra/"}',
    )
    assert rc != 0
    assert "use only one of --item_file or --item_json" in out


def test_add_requires_item_input():
    out, rc = run("add", "--database_file", str(TEST_FILE))
    assert rc != 0
    assert "provide one of --item_file or --item_json" in out


def test_add_rejects_non_object_item():
    out, rc = run("add", "--database_file", str(TEST_FILE), "--item_json", '["not","an","object"]')
    assert rc != 0
    assert "add item must be a JSON object" in out


# --- delete ---

def test_delete_by_linkedin_url():
    out, rc = run(
        "delete",
        "--database_file", str(TEST_FILE),
        "--item_json", '{"linkedin_url":"https://www.linkedin.com/in/alice-testerson/"}',
    )
    assert rc == 0
    assert "Alice Testerson" in out
    assert read_test_record(ALICE_URL) is None


def test_delete_by_id():
    out, rc = run(
        "delete",
        "--database_file", str(TEST_FILE),
        "--item_json", '{"id":"bob-1"}',
    )
    assert rc == 0
    assert "Bob Labguy" in out
    assert read_test_record(BOB_URL) is None


def test_delete_by_item_file_to_output_file():
    TEST_DELETE_ITEM.write_text(
        json.dumps({"linkedin_url": "https://www.linkedin.com/in/alice-testerson/"}, indent=2, ensure_ascii=False) + "\n"
    )
    out, rc = run(
        "delete",
        "--database_file", str(TEST_FILE),
        "--item_file", str(TEST_DELETE_ITEM),
        "--output_file", str(TEST_DELETE_OUTPUT),
    )
    assert rc == 0
    assert out == ""
    deleted = json.loads(TEST_DELETE_OUTPUT.read_text())
    assert deleted["name"] == "Alice Testerson"
    assert read_test_record(ALICE_URL) is None


def test_delete_requires_identity():
    out, rc = run(
        "delete",
        "--database_file", str(TEST_FILE),
        "--item_json", '{"name":"No Id Person"}',
    )
    assert rc != 0
    assert "requires at least one of 'id' or 'linkedin_url'" in out


def test_delete_not_found():
    out, rc = run(
        "delete",
        "--database_file", str(TEST_FILE),
        "--item_json", '{"linkedin_url":"https://www.linkedin.com/in/not-found/"}',
    )
    assert rc != 0
    assert "no record found" in out


# --- update ---

def test_update_by_linkedin_url():
    out, rc = run(
        "update",
        "--database_file", str(TEST_FILE),
        "--item_json", '{"linkedin_url":"https://www.linkedin.com/in/alice-testerson/","notes":"updated by update"}',
    )
    assert rc == 0
    assert "updated by update" in out
    assert read_test_record(ALICE_URL)["notes"] == "updated by update"


def test_update_by_id():
    out, rc = run(
        "update",
        "--database_file", str(TEST_FILE),
        "--item_json", '{"id":"bob-1","score":"⭐⭐⭐","notes":"updated by id"}',
    )
    assert rc == 0
    bob = read_test_record(BOB_URL)
    assert bob["score"] == "⭐⭐⭐"
    assert bob["notes"] == "updated by id"


def test_update_by_item_file_to_output_file():
    TEST_FIND_QUERY.write_text(
        json.dumps({"linkedin_url": ALICE_URL, "company": "UpdatedCo"}, indent=2, ensure_ascii=False) + "\n"
    )
    out, rc = run(
        "update",
        "--database_file", str(TEST_FILE),
        "--item_file", str(TEST_FIND_QUERY),
        "--output_file", str(TEST_FIND_OUTPUT),
    )
    assert rc == 0
    assert out == ""
    updated = json.loads(TEST_FIND_OUTPUT.read_text())
    assert updated["company"] == "UpdatedCo"
    assert read_test_record(ALICE_URL)["company"] == "UpdatedCo"


def test_update_requires_identity():
    out, rc = run(
        "update",
        "--database_file", str(TEST_FILE),
        "--item_json", '{"notes":"missing identity"}',
    )
    assert rc != 0
    assert "requires at least one of 'id' or 'linkedin_url'" in out


def test_update_requires_single_item_source():
    TEST_FIND_QUERY.write_text(
        json.dumps({"linkedin_url": ALICE_URL, "notes": "dup source"}, indent=2, ensure_ascii=False) + "\n"
    )
    out, rc = run(
        "update",
        "--database_file", str(TEST_FILE),
        "--item_file", str(TEST_FIND_QUERY),
        "--item_json", '{"linkedin_url":"https://www.linkedin.com/in/alice-testerson/","notes":"dup source"}',
    )
    assert rc != 0
    assert "use only one of --item_file or --item_json" in out


def test_update_requires_item_input():
    out, rc = run("update", "--database_file", str(TEST_FILE))
    assert rc != 0
    assert "provide one of --item_file or --item_json" in out


def test_update_rejects_non_object_item():
    out, rc = run("update", "--database_file", str(TEST_FILE), "--item_json", '["not","an","object"]')
    assert rc != 0
    assert "update item must be a JSON object" in out


def test_update_not_found():
    out, rc = run(
        "update",
        "--database_file", str(TEST_FILE),
        "--item_json", '{"linkedin_url":"https://www.linkedin.com/in/not-found/","notes":"x"}',
    )
    assert rc != 0
    assert "no record found" in out


# --- search --person ---

def test_search_person_finds_by_name():
    out, _ = run("search", "--person", "Martin Bonde")
    assert "Martin Bonde" in out


def test_search_person_does_not_match_company():
    out, _ = run("search", "--person", "Pfizer")
    assert "No results" in out


# --- search --company ---

def test_search_company_finds_by_company():
    out, _ = run("search", "--company", "Pfizer")
    assert "result(s)" in out
    assert "Pfizer" in out


def test_search_company_does_not_match_name():
    out, _ = run("search", "--company", "Martin Bonde")
    assert "No results" in out


# --- search --competitor ---

def test_search_competitor_flags_competitor_company():
    out, _ = run("search", "--competitor", "Schrödinger")
    assert "COMPETITOR MATCH" in out
    assert "Schrödinger" in out


def test_search_competitor_flags_competitor_person():
    out, _ = run("search", "--competitor", "David van der Spoel")
    assert "COMPETITOR MATCH" in out
    assert "David van der Spoel" in out


def test_search_without_competitor_flag_hides_warning():
    out, _ = run("search", "Schrödinger")
    assert "COMPETITOR" not in out
    assert "result(s)" in out


# --- apply_update ---

def test_apply_update():
    pending = CRM_DIR / ".pending_update.json"
    pending.write_text(json.dumps({
        "linkedin_url": ALICE_URL,
        "target_file": str(TEST_FILE),
        "fields": {"notes": "applied by pytest"}
    }))
    out, rc = run("apply_update")
    assert rc == 0
    assert "Saved" in out
    assert read_test_record(ALICE_URL)["notes"] == "applied by pytest"
    assert not pending.exists()


def test_apply_update_custom_file():
    custom = CRM_DIR / ".custom_pending.json"
    try:
        custom.write_text(json.dumps({
            "linkedin_url": BOB_URL,
            "target_file": str(TEST_FILE),
            "fields": {"score": "⭐⭐"}
        }))
        out, rc = run("apply_update", str(custom))
        assert rc == 0
        assert read_test_record(BOB_URL)["score"] == "⭐⭐"
        assert not custom.exists()
    finally:
        custom.unlink(missing_ok=True)


# --- parse-from-linkedin-mcp ---

def write_linkedin_mcp_intake(data):
    TEST_LINKEDIN_MCP_INTAKE.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")

def test_parse_linkedin_mcp_likers_format():
    write_linkedin_mcp_intake({
        "url": "https://linkedin.com/post/123",
        "likers": [
            {
                "name": "Liker One\nView Liker One's profile\n· 2nd\nFounder at Startup",
                "url": "https://www.linkedin.com/in/liker-one/"
            }
        ]
    })
    out, rc = run("parse-from-linkedin-mcp", str(TEST_LINKEDIN_MCP_INTAKE))
    assert rc == 0
    assert "Successfully converted 1 records" in out
    
    parsed = json.loads(TEST_LINKEDIN_MCP_INTAKE.read_text())
    assert len(parsed) == 1
    assert parsed[0]["name"] == "Liker One"
    assert parsed[0]["company"] == "Startup"
    assert parsed[0]["position"] == "Founder"
    assert parsed[0]["linkedin_url"] == "https://www.linkedin.com/in/liker-one/"
    assert parsed[0]["source"] == "linkedin_mcp"

def test_parse_linkedin_mcp_inbox_format():
    write_linkedin_mcp_intake({
        "conversations": [
            {
                "name": "Inbox Person",
                "username": "inbox-person",
                "thread_url": "/messaging/thread/123/"
            }
        ]
    })
    out, rc = run("parse-from-linkedin-mcp", str(TEST_LINKEDIN_MCP_INTAKE))
    assert rc == 0
    assert "Successfully converted 1 records" in out
    
    parsed = json.loads(TEST_LINKEDIN_MCP_INTAKE.read_text())
    assert len(parsed) == 1
    assert parsed[0]["name"] == "Inbox Person"
    assert parsed[0]["linkedin_url"] == "https://www.linkedin.com/in/inbox-person/"

def test_parse_linkedin_mcp_references_format():
    write_linkedin_mcp_intake({
        "references": {
            "search_results": [
                {
                    "kind": "person",
                    "text": "Ref Person\n· 1st degree connection\nResearcher @ University",
                    "url": "/in/ref-person/"
                },
                {
                    "kind": "company",
                    "text": "Some Company",
                    "url": "/company/some-co/"
                }
            ]
        }
    })
    out, rc = run("parse-from-linkedin-mcp", str(TEST_LINKEDIN_MCP_INTAKE))
    assert rc == 0
    assert "Successfully converted 1 records" in out
    
    parsed = json.loads(TEST_LINKEDIN_MCP_INTAKE.read_text())
    assert len(parsed) == 1
    assert parsed[0]["name"] == "Ref Person"
    assert parsed[0]["company"] == "University"
    assert parsed[0]["position"] == "Researcher"
    assert parsed[0]["linkedin_url"] == "https://www.linkedin.com/in/ref-person/"
    assert parsed[0]["connected"] is True

def test_parse_linkedin_mcp_invalid_format():
    write_linkedin_mcp_intake(["this", "is", "a", "list", "not", "a", "dict"])
    out, rc = run("parse-from-linkedin-mcp", str(TEST_LINKEDIN_MCP_INTAKE))
    assert rc == 0  # It gracefully continues on error but prints it
    assert "must be a recognized MCP output format (dict)" in out

def test_parse_linkedin_mcp_no_people():
    write_linkedin_mcp_intake({"references": {"main": [{"kind": "company", "url": "x"}]}})
    out, rc = run("parse-from-linkedin-mcp", str(TEST_LINKEDIN_MCP_INTAKE))
    assert rc == 0  # It gracefully continues on error but prints it
    assert "No people records found" in out

def test_parse_linkedin_mcp_multiple_files():
    TEST_FILE_1 = CRM_DIR / "test_mcp_1.json"
    TEST_FILE_2 = CRM_DIR / "test_mcp_2.json"
    
    TEST_FILE_1.write_text(json.dumps({
        "likers": [{"name": "Person 1\nTitle", "url": "url1"}]
    }))
    TEST_FILE_2.write_text(json.dumps({
        "likers": [{"name": "Person 2\nTitle", "url": "url2"}]
    }))
    
    try:
        out, rc = run("parse-from-linkedin-mcp", str(TEST_FILE_1), str(TEST_FILE_2))
        assert rc == 0
        assert "Successfully converted 1 records in test_mcp_1.json" in out
        assert "Successfully converted 1 records in test_mcp_2.json" in out
        
        d1 = json.loads(TEST_FILE_1.read_text())
        assert d1[0]["name"] == "Person 1"
        d2 = json.loads(TEST_FILE_2.read_text())
        assert d2[0]["name"] == "Person 2"
    finally:
        TEST_FILE_1.unlink(missing_ok=True)
        TEST_FILE_2.unlink(missing_ok=True)


# --- shuffle ---

def test_shuffle_reorders_json_array_with_seed():
    records = [{"name": f"Person {idx}"} for idx in range(6)]
    TEST_SHUFFLE.write_text(json.dumps(records, indent=2, ensure_ascii=False) + "\n")

    out, rc = run("shuffle", str(TEST_SHUFFLE), "--seed", "7")

    assert rc == 0
    assert "Shuffled 6 records" in out
    shuffled = json.loads(TEST_SHUFFLE.read_text())
    assert sorted(record["name"] for record in shuffled) == sorted(record["name"] for record in records)
    assert shuffled != records


def test_shuffle_dry_run_leaves_file_unchanged():
    records = [{"name": f"Person {idx}"} for idx in range(5)]
    TEST_SHUFFLE.write_text(json.dumps(records, indent=2, ensure_ascii=False) + "\n")

    out, rc = run("shuffle", str(TEST_SHUFFLE), "--seed", "2", "--dry-run")

    assert rc == 0
    assert "(dry run" in out
    assert json.loads(TEST_SHUFFLE.read_text()) == records


def test_shuffle_rejects_non_array_file():
    TEST_SHUFFLE.write_text(json.dumps({"not": "a list"}, indent=2) + "\n")

    out, rc = run("shuffle", str(TEST_SHUFFLE))

    assert rc != 0
    assert "file must be a JSON array" in out


# --- intake ---

INTAKE_RECORDS = [
    {
        "name": "Carol Unscored",
        "linkedin_url": "https://www.linkedin.com/in/carol-unscored/",
        "linkedin_username": "carol-unscored",
        "position": "CSO",
        "company": "IntakeCo",
        "score": None,
    },
    {
        "name": "Dave Scored",
        "linkedin_url": "https://www.linkedin.com/in/dave-scored/",
        "linkedin_username": "dave-scored",
        "score": "⭐⭐⭐",
    },
    {
        "name": "Eve Also Unscored",
        "linkedin_url": "https://www.linkedin.com/in/eve-unscored/",
        "linkedin_username": "eve-unscored",
        "score": None,
    },
]


def write_intake(records=None):
    TEST_INTAKE.write_text(json.dumps(records or INTAKE_RECORDS, indent=2, ensure_ascii=False) + "\n")


def test_intake_picks_first_unscored():
    write_intake()
    out, rc = run("intake", str(TEST_INTAKE))
    assert rc == 0
    assert "Carol Unscored" in out
    assert "IntakeCo" in out
    assert "2 unscored" in out


def test_intake_writes_pending_stub():
    write_intake()
    run("intake", str(TEST_INTAKE))
    assert PENDING_FILE.exists()
    pending = json.loads(PENDING_FILE.read_text())
    assert pending["linkedin_url"] == "https://www.linkedin.com/in/carol-unscored/"
    assert pending["target_file"] == str(TEST_INTAKE)
    assert pending["fields"] == {}


def test_intake_writes_custom_output_file():
    write_intake()
    custom = CRM_DIR / ".custom_intake_pending.json"
    try:
        out, rc = run("intake", str(TEST_INTAKE), "--output", str(custom))
        assert rc == 0
        assert custom.exists()
        pending = json.loads(custom.read_text())
        assert pending["linkedin_url"] == "https://www.linkedin.com/in/carol-unscored/"
        assert pending["target_file"] == str(TEST_INTAKE)
        assert "apply_update" in out
    finally:
        custom.unlink(missing_ok=True)


def test_intake_all_scored():
    write_intake([{"name": "Done", "linkedin_url": "x", "score": "⭐"}])
    out, rc = run("intake", str(TEST_INTAKE))
    assert rc != 0
    assert "All records scored" in out


def test_intake_missing_file():
    out, rc = run("intake", "crm/does_not_exist.json")
    assert rc != 0
    assert "not found" in out.lower()


def test_intake_then_apply_update():
    """Full workflow: intake → fill pending → apply_update."""
    write_intake()
    run("intake", str(TEST_INTAKE))
    # Fill in the pending stub
    pending = json.loads(PENDING_FILE.read_text())
    pending["fields"] = {"score": "⭐⭐⭐⭐", "notes": "intake workflow test"}
    PENDING_FILE.write_text(json.dumps(pending, indent=2, ensure_ascii=False) + "\n")
    # Also need the record in a file that find_record can glob
    # intake file is test_intake.json which is *.json so it gets picked up
    out, rc = run("apply_update")
    assert rc == 0
    assert "Saved" in out
    # Verify the record was updated in the intake file
    data = json.loads(TEST_INTAKE.read_text())
    carol = next(r for r in data if "carol" in r["linkedin_url"])
    assert carol["score"] == "⭐⭐⭐⭐"
    assert carol["notes"] == "intake workflow test"


# --- top ---

TOP_RECORDS = [
    {
        "name": "Fiona Five Stars",
        "position": "CSO",
        "company": "TopBio",
        "linkedin_url": "https://www.linkedin.com/in/fiona-five/",
        "connected": False,
        "email": None,
        "contacted_at": None,
        "source": "manual",
        "added": "2026-01-01",
        "score": "⭐⭐⭐⭐⭐",
        "notes": "top lead",
    },
    {
        "name": "George Three Stars",
        "position": "Scientist",
        "company": "MidPharma",
        "linkedin_url": "https://www.linkedin.com/in/george-three/",
        "connected": False,
        "email": None,
        "contacted_at": None,
        "source": "manual",
        "added": "2026-01-02",
        "score": "⭐⭐⭐",
        "notes": "",
    },
    {
        "name": "Helen Contacted",
        "position": "VP Research",
        "company": "DoneBio",
        "linkedin_url": "https://www.linkedin.com/in/helen-contacted/",
        "connected": True,
        "email": "helen@donebio.com",
        "contacted_at": "2026-03-01",
        "source": "manual",
        "added": "2026-01-03",
        "score": "⭐⭐⭐⭐⭐",
        "notes": "already contacted",
    },
    {
        "name": "Ivan Disqualified",
        "position": "Engineer",
        "company": "CompetitorCo",
        "linkedin_url": "https://www.linkedin.com/in/ivan-dq/",
        "connected": False,
        "email": None,
        "contacted_at": None,
        "source": "manual",
        "added": "2026-01-04",
        "score": "❌",
        "notes": "competitor",
    },
    {
        "name": "Jane Unscored",
        "position": "Analyst",
        "company": "NewCo",
        "linkedin_url": "https://www.linkedin.com/in/jane-unscored/",
        "connected": False,
        "email": None,
        "contacted_at": None,
        "source": "manual",
        "added": "2026-01-05",
        "score": None,
        "notes": "",
    },
]


def write_top(records=None):
    TEST_TOP.write_text(json.dumps(records or TOP_RECORDS, indent=2, ensure_ascii=False) + "\n")


def test_top_returns_highest_scored():
    write_top()
    out, rc = run("top", "--file", str(TEST_TOP))
    assert rc == 0
    assert "Fiona Five Stars" in out
    assert "George Three Stars" not in out


def test_top_n():
    write_top()
    out, rc = run("top", "-n", "2", "--file", str(TEST_TOP))
    assert rc == 0
    assert "Fiona Five Stars" in out
    assert "George Three Stars" in out


def test_top_excludes_contacted():
    write_top()
    out, rc = run("top", "-n", "10", "--file", str(TEST_TOP))
    assert rc == 0
    assert "Helen Contacted" not in out


def test_top_include_contacted():
    write_top()
    out, rc = run("top", "-n", "10", "--include-contacted", "--file", str(TEST_TOP))
    assert rc == 0
    assert "Helen Contacted" in out


def test_top_excludes_disqualified():
    write_top()
    out, rc = run("top", "-n", "10", "--file", str(TEST_TOP))
    assert rc == 0
    assert "Ivan Disqualified" not in out


def test_top_include_disqualified():
    write_top()
    out, rc = run("top", "-n", "10", "--include-disqualified", "--file", str(TEST_TOP))
    assert rc == 0
    assert "Ivan Disqualified" in out


def test_top_excludes_unscored():
    write_top()
    out, rc = run("top", "-n", "10", "--file", str(TEST_TOP))
    assert rc == 0
    assert "Jane Unscored" not in out


def test_top_min_score():
    write_top()
    out, rc = run("top", "-n", "10", "--min", "⭐⭐⭐⭐", "--file", str(TEST_TOP))
    assert rc == 0
    assert "Fiona Five Stars" in out
    assert "George Three Stars" not in out


def test_top_does_not_write_pending_stub_by_default():
    write_top()
    run("top", "--file", str(TEST_TOP))
    assert not PENDING_FILE.exists()


def test_top_writes_requested_output_for_single():
    write_top()
    PENDING_FILE.unlink(missing_ok=True)
    out, rc = run("top", "--file", str(TEST_TOP), "--output", str(PENDING_FILE))
    assert rc == 0
    assert PENDING_FILE.exists()
    pending = json.loads(PENDING_FILE.read_text())
    assert pending["linkedin_url"] == "https://www.linkedin.com/in/fiona-five/"
    assert pending["target_file"] == str(TEST_TOP)
    assert "Wrote" in out


def test_top_output_requires_single_result():
    write_top()
    PENDING_FILE.unlink(missing_ok=True)
    out, rc = run("top", "-n", "2", "--file", str(TEST_TOP), "--output", str(PENDING_FILE))
    assert rc != 0
    assert "requires exactly one result" in out
    assert not PENDING_FILE.exists()


def test_top_empty():
    write_top([{"name": "X", "linkedin_url": "x", "score": None}])
    out, rc = run("top", "--file", str(TEST_TOP))
    assert rc != 0
    assert "No leads match" in out


# --- merge ---

def write_merge(src_records, dst_records=None):
    TEST_MERGE_SRC.write_text(json.dumps(src_records, indent=2, ensure_ascii=False) + "\n")
    TEST_MERGE_DST.write_text(json.dumps(dst_records or [], indent=2, ensure_ascii=False) + "\n")


def test_merge_adds_scored_records():
    write_merge(
        src_records=[
            {"name": "New Lead", "linkedin_url": "https://www.linkedin.com/in/new-lead/",
             "company": "NewCo", "score": "⭐⭐⭐"},
        ],
    )
    out, rc = run("merge", str(TEST_MERGE_SRC), "--leads-file", str(TEST_MERGE_DST))
    assert rc == 0
    assert "Add:      1" in out
    dst = json.loads(TEST_MERGE_DST.read_text())
    assert len(dst) == 1
    assert dst[0]["name"] == "New Lead"


def test_merge_skips_duplicates():
    existing = {"name": "Existing", "linkedin_url": "https://www.linkedin.com/in/existing/",
                "company": "OldCo", "score": "⭐⭐"}
    write_merge(
        src_records=[
            {"name": "Existing", "linkedin_url": "https://www.linkedin.com/in/existing/",
             "company": "OldCo", "score": "⭐⭐⭐"},
        ],
        dst_records=[existing],
    )
    out, rc = run("merge", str(TEST_MERGE_SRC), "--leads-file", str(TEST_MERGE_DST))
    assert rc == 0
    assert "Skip:     1" in out
    dst = json.loads(TEST_MERGE_DST.read_text())
    assert len(dst) == 1
    assert dst[0]["score"] == "⭐⭐"  # original unchanged
    src = json.loads(TEST_MERGE_SRC.read_text())
    assert src == []


def test_merge_drops_scored_duplicates_but_keeps_unscored():
    existing = {"name": "Existing", "linkedin_url": "https://www.linkedin.com/in/existing/",
                "company": "OldCo", "score": "⭐⭐"}
    write_merge(
        src_records=[
            {"name": "Existing", "linkedin_url": "https://www.linkedin.com/in/existing/",
             "company": "OldCo", "score": "⭐⭐⭐"},
            {"name": "Unscored", "linkedin_url": "https://www.linkedin.com/in/unscored/",
             "company": "NewCo", "score": None},
        ],
        dst_records=[existing],
    )
    out, rc = run("merge", str(TEST_MERGE_SRC), "--leads-file", str(TEST_MERGE_DST))
    assert rc == 0
    assert "Skip:     1" in out
    dst = json.loads(TEST_MERGE_DST.read_text())
    assert len(dst) == 1
    assert dst[0]["score"] == "⭐⭐"
    src = json.loads(TEST_MERGE_SRC.read_text())
    assert len(src) == 1
    assert src[0]["name"] == "Unscored"


def test_merge_leaves_unscored_in_source():
    write_merge(
        src_records=[
            {"name": "Scored", "linkedin_url": "https://www.linkedin.com/in/scored/",
             "company": "A", "score": "⭐⭐⭐"},
            {"name": "Unscored", "linkedin_url": "https://www.linkedin.com/in/unscored/",
             "company": "B", "score": None},
        ],
    )
    out, rc = run("merge", str(TEST_MERGE_SRC), "--leads-file", str(TEST_MERGE_DST))
    assert rc == 0
    assert "Unscored: 1 (left in source file)" in out
    src = json.loads(TEST_MERGE_SRC.read_text())
    assert len(src) == 1
    assert src[0]["name"] == "Unscored"


def test_merge_dry_run():
    write_merge(
        src_records=[
            {"name": "DryRun", "linkedin_url": "https://www.linkedin.com/in/dryrun/",
             "company": "X", "score": "⭐"},
        ],
    )
    out, rc = run("merge", str(TEST_MERGE_SRC), "--leads-file", str(TEST_MERGE_DST), "--dry-run")
    assert rc == 0
    assert "dry run" in out.lower()
    # dst should still be empty
    dst = json.loads(TEST_MERGE_DST.read_text())
    assert len(dst) == 0
    # source should still have the record
    src = json.loads(TEST_MERGE_SRC.read_text())
    assert len(src) == 1


def test_merge_missing_file():
    out, rc = run("merge", "crm/does_not_exist.json", "--leads-file", str(TEST_MERGE_DST))
    assert rc != 0
    assert "not found" in out.lower()


def write_deduplicate(src_records, leads=None, prospects=None, customers=None):
    TEST_DEDUPE_SRC.write_text(json.dumps(src_records, indent=2, ensure_ascii=False) + "\n")
    TEST_DEDUPE_LEADS.write_text(json.dumps(leads or [], indent=2, ensure_ascii=False) + "\n")
    TEST_DEDUPE_PROSPECTS.write_text(json.dumps(prospects or [], indent=2, ensure_ascii=False) + "\n")
    TEST_DEDUPE_CUSTOMERS.write_text(json.dumps(customers or [], indent=2, ensure_ascii=False) + "\n")


def test_deduplicate_removes_records_already_in_pipeline():
    write_deduplicate(
        src_records=[
            {"name": "Keep Me", "linkedin_url": "https://www.linkedin.com/in/keep-me/", "company": "FreshCo"},
            {"name": "Lead Dup", "linkedin_url": "https://www.linkedin.com/in/lead-dup/", "company": "LeadCo"},
            {"name": "Prospect Dup", "linkedin_url": "https://www.linkedin.com/in/prospect-dup/", "company": "ProspectCo"},
            {"name": "Customer Dup", "linkedin_url": "https://www.linkedin.com/in/customer-dup/", "company": "CustomerCo"},
        ],
        leads=[
            {"name": "Existing Lead", "linkedin_url": "https://www.linkedin.com/in/lead-dup/", "company": "LeadCo"}
        ],
        prospects=[
            {"name": "Existing Prospect", "linkedin_url": "https://www.linkedin.com/in/prospect-dup/", "company": "ProspectCo"}
        ],
        customers=[
            {"name": "Existing Customer", "linkedin_url": "https://www.linkedin.com/in/customer-dup/", "company": "CustomerCo"}
        ],
    )

    out, rc = run(
        "deduplicate",
        str(TEST_DEDUPE_SRC),
        "--leads-file", str(TEST_DEDUPE_LEADS),
        "--prospects-file", str(TEST_DEDUPE_PROSPECTS),
        "--customers-file", str(TEST_DEDUPE_CUSTOMERS),
    )

    assert rc == 0
    assert "Drop:     3" in out
    remaining = json.loads(TEST_DEDUPE_SRC.read_text())
    assert len(remaining) == 1
    assert remaining[0]["name"] == "Keep Me"


def test_deduplicate_dry_run_leaves_source_unchanged():
    write_deduplicate(
        src_records=[
            {"name": "Lead Dup", "linkedin_url": "https://www.linkedin.com/in/lead-dup/", "company": "LeadCo"},
            {"name": "Keep Me", "linkedin_url": "https://www.linkedin.com/in/keep-me/", "company": "FreshCo"},
        ],
        leads=[
            {"name": "Existing Lead", "linkedin_url": "https://www.linkedin.com/in/lead-dup/", "company": "LeadCo"}
        ],
    )

    out, rc = run(
        "deduplicate",
        str(TEST_DEDUPE_SRC),
        "--leads-file", str(TEST_DEDUPE_LEADS),
        "--prospects-file", str(TEST_DEDUPE_PROSPECTS),
        "--customers-file", str(TEST_DEDUPE_CUSTOMERS),
        "--dry-run",
    )

    assert rc == 0
    assert "dry run" in out.lower()
    remaining = json.loads(TEST_DEDUPE_SRC.read_text())
    assert len(remaining) == 2


def test_deduplicate_missing_file():
    out, rc = run("deduplicate", "crm/does_not_exist.json")
    assert rc != 0
    assert "not found" in out.lower()


def write_filter_competitors(src_records):
    TEST_FILTER_COMPETITORS_SRC.write_text(json.dumps(src_records, indent=2, ensure_ascii=False) + "\n")


def test_filter_competitors_removes_person_and_company_matches():
    write_filter_competitors(
        [
            {
                "name": "Keep Me",
                "linkedin_url": "https://www.linkedin.com/in/keep-me/",
                "company": "FreshCo",
            },
            {
                "name": "David van der Spoel",
                "linkedin_url": "https://www.linkedin.com/in/david-van-der-spoel-4053372/",
                "company": "Uppsala University",
            },
            {
                "name": "Schrodinger Employee",
                "linkedin_url": "https://www.linkedin.com/in/schrodinger-employee/",
                "company": "Schrodinger",
            },
        ]
    )

    out, rc = run("filter-competitors", str(TEST_FILTER_COMPETITORS_SRC))

    assert rc == 0
    assert "Drop:     2" in out
    remaining = json.loads(TEST_FILTER_COMPETITORS_SRC.read_text())
    assert len(remaining) == 1
    assert remaining[0]["name"] == "Keep Me"


def test_filter_competitors_includes_skipped_watchlist_buckets(monkeypatch, tmp_path):
    competitors_file = tmp_path / "competitors.json"
    competitors_file.write_text(
        json.dumps(
            {
                "companies": [],
                "people": [],
                "skipped_companies": [
                    {"name": "NoisyCo", "url": "https://www.linkedin.com/company/noisyco/"}
                ],
                "skipped_people": [
                    {"name": "Noisy Person", "url": "https://www.linkedin.com/in/noisy-person/"}
                ],
            },
            indent=2,
        )
        + "\n"
    )
    source_file = tmp_path / "source.json"
    source_file.write_text(
        json.dumps(
            [
                {
                    "name": "Noisy Person",
                    "linkedin_url": "https://www.linkedin.com/in/noisy-person/",
                    "company": "OtherCo",
                },
                {
                    "name": "NoisyCo Employee",
                    "linkedin_url": "https://www.linkedin.com/in/noisyco-employee/",
                    "company": "NoisyCo",
                },
                {
                    "name": "Keep Me",
                    "linkedin_url": "https://www.linkedin.com/in/keep-me/",
                    "company": "FreshCo",
                },
            ],
            indent=2,
        )
        + "\n"
    )
    monkeypatch.setattr(_jsoncrm_tool, "COMPETITORS_FILE", competitors_file)

    _jsoncrm_tool.cmd_filter_competitors(SimpleNamespace(file=str(source_file), dry_run=False))

    remaining = json.loads(source_file.read_text())
    assert [record["name"] for record in remaining] == ["Keep Me"]


def test_search_competitors_includes_skipped_people(monkeypatch, tmp_path):
    competitors_file = tmp_path / "competitors.json"
    competitors_file.write_text(
        json.dumps(
            {
                "companies": [],
                "people": [],
                "skipped_people": [
                    {"name": "Noisy Person", "url": "https://www.linkedin.com/in/noisy-person/"}
                ],
            },
            indent=2,
        )
        + "\n"
    )
    monkeypatch.setattr(_jsoncrm_schema, "COMPETITORS_FILE", competitors_file)

    assert _jsoncrm_utils.search_competitors("Noisy Person") == [
        ("person", {"name": "Noisy Person", "url": "https://www.linkedin.com/in/noisy-person/"})
    ]


def test_filter_competitors_dry_run_leaves_source_unchanged():
    write_filter_competitors(
        [
            {
                "name": "Schrodinger Employee",
                "linkedin_url": "https://www.linkedin.com/in/schrodinger-employee/",
                "company": "Schrodinger",
            },
            {
                "name": "Keep Me",
                "linkedin_url": "https://www.linkedin.com/in/keep-me/",
                "company": "FreshCo",
            },
        ]
    )

    out, rc = run("filter-competitors", str(TEST_FILTER_COMPETITORS_SRC), "--dry-run")

    assert rc == 0
    assert "dry run" in out.lower()
    remaining = json.loads(TEST_FILTER_COMPETITORS_SRC.read_text())
    assert len(remaining) == 2


def test_filter_competitors_missing_file():
    out, rc = run("filter-competitors", "crm/does_not_exist.json")
    assert rc != 0
    assert "not found" in out.lower()


# --- promote ---

PROMOTE_LEADS = [
    {
        "name": "Kay Lead",
        "position": "CSO",
        "company": "LeadCo",
        "linkedin_url": "https://www.linkedin.com/in/kay-lead/",
        "score": "⭐⭐⭐⭐⭐",
    },
    {
        "name": "Leo Other",
        "position": "Scientist",
        "company": "OtherCo",
        "linkedin_url": "https://www.linkedin.com/in/leo-other/",
        "score": "⭐⭐⭐",
    },
]

KAY_URL = PROMOTE_LEADS[0]["linkedin_url"]


def write_promote(src_records=None, dst_records=None):
    TEST_PROMOTE_SRC.write_text(
        json.dumps(src_records if src_records is not None else PROMOTE_LEADS,
                   indent=2, ensure_ascii=False) + "\n")
    TEST_PROMOTE_DST.write_text(
        json.dumps(dst_records or [], indent=2, ensure_ascii=False) + "\n")


def test_promote_lead_to_prospect():
    write_promote()
    out, rc = run("promote", KAY_URL, "--lead",
                  "--from-file", str(TEST_PROMOTE_SRC),
                  "--to-file", str(TEST_PROMOTE_DST))
    assert rc == 0
    assert "Promoted" in out
    assert "Kay Lead" in out
    # Record should be in dst
    dst = json.loads(TEST_PROMOTE_DST.read_text())
    assert len(dst) == 1
    assert dst[0]["name"] == "Kay Lead"
    # Record should be removed from src
    src = json.loads(TEST_PROMOTE_SRC.read_text())
    assert len(src) == 1
    assert src[0]["name"] == "Leo Other"


def test_promote_prospect_to_customer():
    write_promote()
    out, rc = run("promote", KAY_URL, "--prospect",
                  "--from-file", str(TEST_PROMOTE_SRC),
                  "--to-file", str(TEST_PROMOTE_DST))
    assert rc == 0
    assert "Promoted" in out
    dst = json.loads(TEST_PROMOTE_DST.read_text())
    assert len(dst) == 1
    assert dst[0]["name"] == "Kay Lead"


def test_promote_not_found():
    write_promote()
    out, rc = run("promote", "https://www.linkedin.com/in/nobody/", "--lead",
                  "--from-file", str(TEST_PROMOTE_SRC),
                  "--to-file", str(TEST_PROMOTE_DST))
    assert rc != 0
    assert "no record found" in out.lower()


def test_promote_requires_stage_flag():
    """--lead or --prospect is required."""
    out, rc = run("promote", KAY_URL)
    assert rc != 0


# --- stats ---

STATS_LEADS = [
    {"name": "A", "linkedin_url": "a", "score": "⭐⭐⭐⭐⭐", "contacted_at": None},
    {"name": "B", "linkedin_url": "b", "score": "⭐⭐⭐⭐⭐", "contacted_at": "2026-03-01"},
    {"name": "C", "linkedin_url": "c", "score": "⭐⭐⭐", "contacted_at": None},
    {"name": "D", "linkedin_url": "d", "score": "❌", "contacted_at": None},
    {"name": "E", "linkedin_url": "e", "score": None, "contacted_at": None},
]

STATS_PROSPECTS = [
    {"name": "F", "linkedin_url": "f"},
    {"name": "G", "linkedin_url": "g"},
]

STATS_CUSTOMERS = [
    {"name": "H", "linkedin_url": "h"},
]


def write_stats():
    TEST_STATS_LEADS.write_text(json.dumps(STATS_LEADS, indent=2) + "\n")
    TEST_STATS_PROSPECTS.write_text(json.dumps(STATS_PROSPECTS, indent=2) + "\n")
    TEST_STATS_CUSTOMERS.write_text(json.dumps(STATS_CUSTOMERS, indent=2) + "\n")


def run_stats():
    return run("stats",
               "--leads-file", str(TEST_STATS_LEADS),
               "--prospects-file", str(TEST_STATS_PROSPECTS),
               "--customers-file", str(TEST_STATS_CUSTOMERS))


def test_stats_lead_counts():
    write_stats()
    out, rc = run_stats()
    assert rc == 0
    assert "Leads: 5" in out
    assert "Scored:       4" in out
    assert "Unscored:     1" in out
    assert "Contacted:    1" in out
    assert "Disqualified: 1" in out


def test_stats_score_breakdown():
    write_stats()
    out, _ = run_stats()
    assert "⭐⭐⭐⭐⭐  2" in out
    assert "⭐⭐⭐  1" in out


def test_stats_prospects_and_customers():
    write_stats()
    out, _ = run_stats()
    assert "Prospects: 2" in out
    assert "Customers: 1" in out


def test_stats_empty_pipeline():
    TEST_STATS_LEADS.write_text("[]\n")
    TEST_STATS_PROSPECTS.write_text("[]\n")
    TEST_STATS_CUSTOMERS.write_text("[]\n")
    out, rc = run_stats()
    assert rc == 0
    assert "Leads: 0" in out
    assert "Prospects: 0" in out
    assert "Customers: 0" in out


def run_validate():
    result = subprocess.run(
        [*TOOL, "validate", "--leads-file", str(TEST_VALIDATE_LEADS),
         "--prospects-file", str(TEST_VALIDATE_PROSPECTS),
         "--customers-file", str(TEST_VALIDATE_CUSTOMERS)],
        capture_output=True, text=True,
    )
    return result.stdout + result.stderr, result.returncode


def test_validate_all_valid():
    TEST_VALIDATE_LEADS.write_text(json.dumps([{"name": "Alice", "linkedin_url": "https://linkedin.com/in/alice"}]))
    TEST_VALIDATE_PROSPECTS.write_text("[]\n")
    TEST_VALIDATE_CUSTOMERS.write_text("[]\n")
    out, rc = run_validate()
    assert rc == 0
    assert "All pipeline files are valid" in out


def test_validate_invalid_json():
    TEST_VALIDATE_LEADS.write_text("not json")
    TEST_VALIDATE_PROSPECTS.write_text("[]\n")
    TEST_VALIDATE_CUSTOMERS.write_text("[]\n")
    out, rc = run_validate()
    assert rc == 1
    assert "invalid JSON" in out


def test_validate_duplicate_identity():
    TEST_VALIDATE_LEADS.write_text(json.dumps([
        {"name": "Alice", "linkedin_url": "https://linkedin.com/in/alice"},
        {"name": "Alice2", "linkedin_url": "https://linkedin.com/in/alice"},
    ]))
    TEST_VALIDATE_PROSPECTS.write_text("[]\n")
    TEST_VALIDATE_CUSTOMERS.write_text("[]\n")
    out, rc = run_validate()
    assert rc == 1
    assert "duplicate" in out



def run_recent(*extra):
    result = subprocess.run(
        [*TOOL, "recent", "--leads-file", str(TEST_RECENT_LEADS),
         "--prospects-file", str(TEST_RECENT_PROSPECTS),
         "--customers-file", str(TEST_RECENT_CUSTOMERS), *extra],
        capture_output=True, text=True,
    )
    return result.stdout + result.stderr, result.returncode


def test_recent_basic():
    TEST_RECENT_LEADS.write_text(json.dumps([
        {"name": "Alice", "company": "Acme", "added": "2026-01-03", "linkedin_url": "https://linkedin.com/in/alice"},
        {"name": "Bob", "company": "Bio", "added": "2026-01-01", "linkedin_url": "https://linkedin.com/in/bob"},
    ]))
    TEST_RECENT_PROSPECTS.write_text("[]\n")
    TEST_RECENT_CUSTOMERS.write_text("[]\n")
    out, rc = run_recent("-n", "2")
    assert rc == 0
    assert "Alice" in out
    assert "Bob" in out


def test_recent_json_mode():
    TEST_RECENT_LEADS.write_text(json.dumps([
        {"name": "Alice", "company": "Acme", "added": "2026-01-03", "linkedin_url": "https://linkedin.com/in/alice"},
    ]))
    TEST_RECENT_PROSPECTS.write_text("[]\n")
    TEST_RECENT_CUSTOMERS.write_text("[]\n")
    out, rc = run_recent("--json", "-n", "1")
    assert rc == 0
    data = json.loads(out)
    assert len(data) == 1
    assert data[0]["name"] == "Alice"



def test_demote_prospect_to_lead():
    TEST_DEMOTE_SRC.write_text(json.dumps([
        {"name": "Alice", "linkedin_url": "https://linkedin.com/in/alice"},
    ]))
    TEST_DEMOTE_DST.write_text("[]\n")
    result = subprocess.run(
        [*TOOL, "demote", "https://linkedin.com/in/alice", "--prospect",
         "--from-file", str(TEST_DEMOTE_SRC), "--to-file", str(TEST_DEMOTE_DST)],
        capture_output=True, text=True,
    )
    out, rc = result.stdout + result.stderr, result.returncode
    assert rc == 0
    assert "Demoted" in out
    assert len(json.loads(TEST_DEMOTE_SRC.read_text())) == 0
    assert len(json.loads(TEST_DEMOTE_DST.read_text())) == 1


def test_demote_missing_record():
    TEST_DEMOTE_SRC.write_text("[]\n")
    TEST_DEMOTE_DST.write_text("[]\n")
    result = subprocess.run(
        [*TOOL, "demote", "https://linkedin.com/in/alice", "--prospect",
         "--from-file", str(TEST_DEMOTE_SRC), "--to-file", str(TEST_DEMOTE_DST)],
        capture_output=True, text=True,
    )
    assert result.returncode == 1
    assert "no record found" in result.stdout + result.stderr



def run_list(*extra):
    result = subprocess.run(
        [*TOOL, "list", "leads", "--file", str(TEST_LIST), *extra],
        capture_output=True, text=True,
    )
    return result.stdout + result.stderr, result.returncode


def test_list_basic():
    TEST_LIST.write_text(json.dumps([
        {"name": "Alice", "company": "Acme", "score": "⭐⭐⭐⭐", "linkedin_url": "https://linkedin.com/in/alice"},
        {"name": "Bob", "company": "Bio", "score": None, "linkedin_url": "https://linkedin.com/in/bob"},
    ]))
    out, rc = run_list()
    assert rc == 0
    assert "Alice" in out
    assert "Bob" in out


def test_list_filter_score():
    TEST_LIST.write_text(json.dumps([
        {"name": "Alice", "company": "Acme", "score": "⭐⭐⭐⭐", "linkedin_url": "https://linkedin.com/in/alice"},
        {"name": "Bob", "company": "Bio", "score": None, "linkedin_url": "https://linkedin.com/in/bob"},
    ]))
    out, rc = run_list("--score", "⭐⭐⭐⭐")
    assert rc == 0
    assert "Alice" in out
    assert "Bob" not in out


def test_list_json_mode():
    TEST_LIST.write_text(json.dumps([
        {"name": "Alice", "company": "Acme", "score": "⭐⭐⭐⭐", "linkedin_url": "https://linkedin.com/in/alice"},
    ]))
    out, rc = run_list("--json")
    assert rc == 0
    data = json.loads(out)
    assert len(data) == 1
    assert data[0]["name"] == "Alice"


def test_stats_json_mode():
    TEST_STATS_LEADS.write_text("[]\n")
    TEST_STATS_PROSPECTS.write_text("[]\n")
    TEST_STATS_CUSTOMERS.write_text("[]\n")
    result = subprocess.run(
        [*TOOL, "stats", "--leads-file", str(TEST_STATS_LEADS),
         "--prospects-file", str(TEST_STATS_PROSPECTS),
         "--customers-file", str(TEST_STATS_CUSTOMERS), "--json"],
        capture_output=True, text=True,
    )
    out, rc = result.stdout + result.stderr, result.returncode
    assert rc == 0
    data = json.loads(out)
    assert data["leads"]["total"] == 0


def test_search_json_mode():
    TEST_FILE.write_text(json.dumps(TEST_RECORDS, indent=2, ensure_ascii=False) + "\n")
    result = subprocess.run(
        [*TOOL, "search", "Alice", "--json"],
        capture_output=True, text=True,
    )
    out, rc = result.stdout + result.stderr, result.returncode
    assert rc == 0
    data = json.loads(out)
    assert len(data["results"]) >= 1
    assert any(r["name"] == "Alice Testerson" for r in data["results"])
