"""Unit tests for jsoncrm.tool command handlers."""

import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest


import jsoncrm.schema as schema
import jsoncrm.tool as tool
from jsoncrm.utils import load_json

TEST_DB = Path(__file__).parent / "test_tool_db.json"


def reset_db():
    TEST_DB.write_text("[]\n")


def cleanup_db():
    TEST_DB.unlink(missing_ok=True)


def make_args(**kwargs):
    return SimpleNamespace(**kwargs)


# --- cmd_find ---

def test_cmd_find_by_item_json(tmp_path, capsys):
    db = tmp_path / "db.json"
    db.write_text(json.dumps([{"name": "Alice", "company": "Acme"}, {"name": "Bob", "company": "Acme"}]))
    tool.cmd_find(
        make_args(
            database_file=str(db),
            item_file=None,
            item_json='{"company": "Acme"}',
            output_file=None,
        )
    )
    captured = capsys.readouterr()
    assert "Alice" in captured.out
    assert "Bob" in captured.out


def test_cmd_find_no_matches(tmp_path, capsys):
    db = tmp_path / "db.json"
    db.write_text(json.dumps([{"name": "Alice", "company": "Acme"}]))
    tool.cmd_find(
        make_args(
            database_file=str(db),
            item_file=None,
            item_json='{"company": "ZZZ"}',
            output_file=None,
        )
    )
    captured = capsys.readouterr()
    assert captured.out.strip() == "[]"


def test_cmd_find_missing_database_exits(tmp_path):
    with pytest.raises(SystemExit) as exc:
        tool.cmd_find(
            make_args(
                database_file=str(tmp_path / "missing.json"),
                item_file=None,
                item_json='{"name": "Alice"}',
                output_file=None,
            )
        )
    assert exc.value.code == 1


# --- cmd_add ---

def test_cmd_add_by_item_json(tmp_path, capsys):
    db = tmp_path / "db.json"
    db.write_text("[]\n")
    tool.cmd_add(
        make_args(
            database_file=str(db),
            item_file=None,
            item_json='{"name":"Alice","linkedin_url":"https://linkedin.com/in/alice"}',
            output_file=None,
        )
    )
    data = json.loads(db.read_text())
    assert len(data) == 1
    assert data[0]["name"] == "Alice"


def test_cmd_add_requires_identity(tmp_path):
    db = tmp_path / "db.json"
    db.write_text("[]\n")
    with pytest.raises(SystemExit) as exc:
        tool.cmd_add(
            make_args(
                database_file=str(db),
                item_file=None,
                item_json='{"name":"Alice"}',
                output_file=None,
            )
        )
    assert exc.value.code == 1


# --- cmd_delete ---

def test_cmd_delete_by_linkedin_url(tmp_path, capsys):
    db = tmp_path / "db.json"
    db.write_text(
        json.dumps(
            [
                {"name": "Alice", "linkedin_url": "https://linkedin.com/in/alice"},
                {"name": "Bob", "linkedin_url": "https://linkedin.com/in/bob"},
            ]
        )
    )
    tool.cmd_delete(
        make_args(
            database_file=str(db),
            item_file=None,
            item_json='{"linkedin_url":"https://linkedin.com/in/alice"}',
            output_file=None,
        )
    )
    data = json.loads(db.read_text())
    assert len(data) == 1
    assert data[0]["name"] == "Bob"


def test_cmd_delete_by_id(tmp_path, capsys):
    db = tmp_path / "db.json"
    db.write_text(json.dumps([{"name": "Alice", "id": "123"}, {"name": "Bob", "id": "456"}]))
    tool.cmd_delete(
        make_args(
            database_file=str(db),
            item_file=None,
            item_json='{"id":"123"}',
            output_file=None,
        )
    )
    data = json.loads(db.read_text())
    assert len(data) == 1
    assert data[0]["name"] == "Bob"


def test_cmd_delete_not_found_exits(tmp_path):
    db = tmp_path / "db.json"
    db.write_text(json.dumps([{"name": "Alice", "linkedin_url": "https://linkedin.com/in/alice"}]))
    with pytest.raises(SystemExit) as exc:
        tool.cmd_delete(
            make_args(
                database_file=str(db),
                item_file=None,
                item_json='{"linkedin_url":"https://linkedin.com/in/bob"}',
                output_file=None,
            )
        )
    assert exc.value.code == 1


# --- cmd_update ---

def test_cmd_update_by_linkedin_url(tmp_path, capsys):
    db = tmp_path / "db.json"
    db.write_text(
        json.dumps([{"name": "Alice", "linkedin_url": "https://linkedin.com/in/alice", "company": "Old"}])
    )
    tool.cmd_update(
        make_args(
            database_file=str(db),
            item_file=None,
            item_json='{"linkedin_url":"https://linkedin.com/in/alice","company":"New"}',
            output_file=None,
        )
    )
    data = json.loads(db.read_text())
    assert data[0]["company"] == "New"


def test_cmd_update_not_found_exits(tmp_path):
    db = tmp_path / "db.json"
    db.write_text(json.dumps([{"name": "Alice", "linkedin_url": "https://linkedin.com/in/alice"}]))
    with pytest.raises(SystemExit) as exc:
        tool.cmd_update(
            make_args(
                database_file=str(db),
                item_file=None,
                item_json='{"linkedin_url":"https://linkedin.com/in/bob","company":"New"}',
                output_file=None,
            )
        )
    assert exc.value.code == 1


# --- cmd_shuffle ---

def test_cmd_shuffle_with_seed_is_deterministic(tmp_path, capsys):
    db = tmp_path / "db.json"
    db.write_text(json.dumps([{"name": "A"}, {"name": "B"}, {"name": "C"}]))
    tool.cmd_shuffle(make_args(file=str(db), seed=42, dry_run=False))
    first = json.loads(db.read_text())
    db.write_text(json.dumps([{"name": "A"}, {"name": "B"}, {"name": "C"}]))
    tool.cmd_shuffle(make_args(file=str(db), seed=42, dry_run=False))
    second = json.loads(db.read_text())
    assert first == second


def test_cmd_shuffle_dry_run_does_not_write(tmp_path, capsys):
    db = tmp_path / "db.json"
    original = [{"name": "A"}, {"name": "B"}, {"name": "C"}]
    db.write_text(json.dumps(original))
    tool.cmd_shuffle(make_args(file=str(db), seed=None, dry_run=True))
    assert json.loads(db.read_text()) == original


# --- cmd_intake ---

def test_cmd_intake_shows_first_unscored(tmp_path, capsys):
    db = tmp_path / "db.json"
    pending = tmp_path / "pending.json"
    db.write_text(
        json.dumps(
            [
                {"name": "Alice", "linkedin_url": "https://linkedin.com/in/alice", "score": "⭐⭐⭐"},
                {"name": "Bob", "linkedin_url": "https://linkedin.com/in/bob", "score": None},
            ]
        )
    )
    tool.cmd_intake(make_args(file=str(db), output=str(pending)))
    captured = capsys.readouterr()
    assert "Bob" in captured.out
    assert "Alice" not in captured.out
    assert pending.exists()


def test_cmd_intake_all_scored_exits(tmp_path):
    db = tmp_path / "db.json"
    db.write_text(json.dumps([{"name": "Alice", "score": "⭐⭐⭐"}]))
    with pytest.raises(SystemExit) as exc:
        tool.cmd_intake(make_args(file=str(db), output=None))
    assert exc.value.code == 1


def test_cmd_intake_missing_file_exits(tmp_path):
    with pytest.raises(SystemExit) as exc:
        tool.cmd_intake(make_args(file=str(tmp_path / "missing.json"), output=None))
    assert exc.value.code == 1


# --- cmd_top ---

def test_cmd_top_returns_highest_scored(tmp_path, capsys):
    db = tmp_path / "db.json"
    db.write_text(
        json.dumps(
            [
                {"name": "Low", "score": "⭐⭐", "next_follow_up": "2020-01-01"},
                {"name": "High", "score": "⭐⭐⭐⭐⭐", "next_follow_up": "2020-01-01"},
                {"name": "Mid", "score": "⭐⭐⭐", "next_follow_up": "2020-01-01"},
            ]
        )
    )
    tool.cmd_top(make_args(file=str(db), num=1, min_score=None, include_contacted=False, include_disqualified=False, output=None))
    captured = capsys.readouterr()
    assert "High" in captured.out
    assert "Low" not in captured.out


def test_cmd_top_excludes_unscored(tmp_path, capsys):
    db = tmp_path / "db.json"
    db.write_text(json.dumps([{"name": "Unscored", "score": None}, {"name": "Scored", "score": "⭐", "next_follow_up": "2020-01-01"}]))
    tool.cmd_top(make_args(file=str(db), num=10, min_score=None, include_contacted=False, include_disqualified=False, output=None))
    captured = capsys.readouterr()
    assert "Scored" in captured.out
    assert "Unscored" not in captured.out


def test_cmd_top_empty_exits(tmp_path):
    db = tmp_path / "db.json"
    db.write_text("[]\n")
    with pytest.raises(SystemExit) as exc:
        tool.cmd_top(make_args(file=str(db), num=1, min_score=None, include_contacted=False, include_disqualified=False, output=None))
    assert exc.value.code == 1


def test_cmd_top_excludes_null_next_follow_up(tmp_path, capsys):
    db = tmp_path / "db.json"
    db.write_text(
        json.dumps(
            [
                {"name": "NullFollowUp", "score": "⭐⭐⭐⭐⭐", "next_follow_up": None},
                {"name": "Actionable", "score": "⭐⭐⭐⭐⭐", "next_follow_up": "2020-01-01"},
            ]
        )
    )
    tool.cmd_top(make_args(file=str(db), num=10, min_score=None, include_contacted=False, include_disqualified=False, output=None))
    captured = capsys.readouterr()
    assert "Actionable" in captured.out
    assert "NullFollowUp" not in captured.out


def test_cmd_top_excludes_future_next_follow_up(tmp_path, capsys):
    db = tmp_path / "db.json"
    db.write_text(
        json.dumps(
            [
                {"name": "Future", "score": "⭐⭐⭐⭐⭐", "next_follow_up": "2099-12-31"},
                {"name": "Ready", "score": "⭐⭐⭐⭐", "next_follow_up": "2020-01-01"},
            ]
        )
    )
    tool.cmd_top(make_args(file=str(db), num=10, min_score=None, include_contacted=False, include_disqualified=False, output=None))
    captured = capsys.readouterr()
    assert "Ready" in captured.out
    assert "Future" not in captured.out


def test_cmd_top_includes_past_next_follow_up(tmp_path, capsys):
    db = tmp_path / "db.json"
    db.write_text(
        json.dumps(
            [
                {"name": "PastDue", "score": "⭐⭐⭐⭐⭐", "next_follow_up": "2020-01-01"},
                {"name": "NeverSet", "score": "⭐⭐⭐⭐", "next_follow_up": "2024-06-01"},
            ]
        )
    )
    tool.cmd_top(make_args(file=str(db), num=10, min_score=None, include_contacted=False, include_disqualified=False, output=None))
    captured = capsys.readouterr()
    assert "PastDue" in captured.out
    assert "NeverSet" in captured.out


def test_cmd_top_include_contacted_bypasses_filter(tmp_path, capsys):
    db = tmp_path / "db.json"
    db.write_text(
        json.dumps(
            [
                {"name": "NullFollowUp", "score": "⭐⭐⭐⭐⭐", "next_follow_up": None},
                {"name": "Future", "score": "⭐⭐⭐⭐", "next_follow_up": "2099-12-31"},
                {"name": "Past", "score": "⭐⭐⭐", "next_follow_up": "2020-01-01"},
            ]
        )
    )
    tool.cmd_top(make_args(file=str(db), num=10, min_score=None, include_contacted=True, include_disqualified=False, output=None))
    captured = capsys.readouterr()
    assert "NullFollowUp" in captured.out
    assert "Future" in captured.out
    assert "Past" in captured.out


# --- cmd_merge ---

def test_cmd_merge_adds_scored_records(tmp_path, capsys):
    src = tmp_path / "src.json"
    src.write_text(json.dumps([{"name": "New", "linkedin_url": "https://linkedin.com/in/new", "score": "⭐⭐⭐"}]))
    dst = tmp_path / "dst.json"
    dst.write_text("[]\n")
    tool.cmd_merge(make_args(file=str(src), leads_file=str(dst), dry_run=False))
    data = json.loads(dst.read_text())
    assert len(data) == 1
    assert data[0]["name"] == "New"


def test_cmd_merge_skips_duplicates(tmp_path, capsys):
    src = tmp_path / "src.json"
    src.write_text(
        json.dumps([{"name": "Existing", "linkedin_url": "https://linkedin.com/in/existing", "score": "⭐⭐⭐"}])
    )
    dst = tmp_path / "dst.json"
    dst.write_text(
        json.dumps([{"name": "Existing", "linkedin_url": "https://linkedin.com/in/existing", "score": "⭐⭐"}])
    )
    tool.cmd_merge(make_args(file=str(src), leads_file=str(dst), dry_run=False))
    data = json.loads(dst.read_text())
    assert len(data) == 1
    assert data[0]["score"] == "⭐⭐"


def test_cmd_merge_leaves_unscored_in_source(tmp_path, capsys):
    src = tmp_path / "src.json"
    src.write_text(
        json.dumps(
            [
                {"name": "Scored", "linkedin_url": "https://linkedin.com/in/scored", "score": "⭐"},
                {"name": "Unscored", "linkedin_url": "https://linkedin.com/in/unscored", "score": None},
            ]
        )
    )
    dst = tmp_path / "dst.json"
    dst.write_text("[]\n")
    tool.cmd_merge(make_args(file=str(src), leads_file=str(dst), dry_run=False))
    src_data = json.loads(src.read_text())
    assert len(src_data) == 1
    assert src_data[0]["name"] == "Unscored"


def test_cmd_merge_dry_run_does_not_write(tmp_path, capsys):
    src = tmp_path / "src.json"
    src.write_text(json.dumps([{"name": "New", "linkedin_url": "https://linkedin.com/in/new", "score": "⭐"}]))
    dst = tmp_path / "dst.json"
    dst.write_text("[]\n")
    tool.cmd_merge(make_args(file=str(src), leads_file=str(dst), dry_run=True))
    assert json.loads(dst.read_text()) == []


# --- cmd_deduplicate ---

def test_cmd_deduplicate_removes_known_urls(tmp_path, capsys):
    src = tmp_path / "src.json"
    src.write_text(
        json.dumps(
            [
                {"name": "Dup", "linkedin_url": "https://linkedin.com/in/dup"},
                {"name": "New", "linkedin_url": "https://linkedin.com/in/new"},
            ]
        )
    )
    leads = tmp_path / "leads.json"
    leads.write_text(json.dumps([{"name": "Dup", "linkedin_url": "https://linkedin.com/in/dup"}]))
    tool.cmd_deduplicate(
        make_args(
            file=str(src),
            leads_file=str(leads),
            prospects_file=None,
            customers_file=None,
            dry_run=False,
        )
    )
    data = json.loads(src.read_text())
    assert len(data) == 1
    assert data[0]["name"] == "New"


def test_cmd_deduplicate_dry_run(tmp_path, capsys):
    src = tmp_path / "src.json"
    original = [{"name": "Dup", "linkedin_url": "https://linkedin.com/in/dup"}]
    src.write_text(json.dumps(original))
    leads = tmp_path / "leads.json"
    leads.write_text(json.dumps([{"name": "Dup", "linkedin_url": "https://linkedin.com/in/dup"}]))
    tool.cmd_deduplicate(
        make_args(
            file=str(src),
            leads_file=str(leads),
            prospects_file=None,
            customers_file=None,
            dry_run=True,
        )
    )
    assert json.loads(src.read_text()) == original


# --- cmd_promote ---

def test_cmd_promote_lead_to_prospect(tmp_path, capsys):
    leads = tmp_path / "leads.json"
    leads.write_text(json.dumps([{"name": "Alice", "linkedin_url": "https://linkedin.com/in/alice"}]))
    prospects = tmp_path / "prospects.json"
    prospects.write_text("[]\n")
    tool.cmd_promote(
        make_args(
            linkedin_url="https://linkedin.com/in/alice",
            lead=True,
            prospect=False,
            from_file=str(leads),
            to_file=str(prospects),
        )
    )
    assert json.loads(leads.read_text()) == []
    dst = json.loads(prospects.read_text())
    assert len(dst) == 1
    assert dst[0]["name"] == "Alice"


def test_cmd_promote_prospect_to_customer(tmp_path, capsys):
    prospects = tmp_path / "prospects.json"
    prospects.write_text(json.dumps([{"name": "Alice", "linkedin_url": "https://linkedin.com/in/alice"}]))
    customers = tmp_path / "customers.json"
    customers.write_text("[]\n")
    tool.cmd_promote(
        make_args(
            linkedin_url="https://linkedin.com/in/alice",
            lead=False,
            prospect=True,
            from_file=str(prospects),
            to_file=str(customers),
        )
    )
    assert json.loads(prospects.read_text()) == []
    dst = json.loads(customers.read_text())
    assert len(dst) == 1


def test_cmd_promote_not_found_exits(tmp_path):
    leads = tmp_path / "leads.json"
    leads.write_text("[]\n")
    prospects = tmp_path / "prospects.json"
    prospects.write_text("[]\n")
    with pytest.raises(SystemExit) as exc:
        tool.cmd_promote(
            make_args(
                linkedin_url="https://linkedin.com/in/alice",
                lead=True,
                prospect=False,
                from_file=str(leads),
                to_file=str(prospects),
            )
        )
    assert exc.value.code == 1


# --- cmd_stats ---

def test_cmd_stats_leads(tmp_path, capsys):
    leads = tmp_path / "leads.json"
    leads.write_text(
        json.dumps(
            [
                {"name": "A", "score": "⭐⭐⭐", "contacted_at": "2024-01-01"},
                {"name": "B", "score": None},
                {"name": "C", "score": "❌"},
            ]
        )
    )
    prospects = tmp_path / "prospects.json"
    prospects.write_text("[]\n")
    customers = tmp_path / "customers.json"
    customers.write_text("[]\n")
    tool.cmd_stats(
        make_args(
            leads_file=str(leads),
            prospects_file=str(prospects),
            customers_file=str(customers),
        )
    )
    captured = capsys.readouterr()
    assert "Leads: 3" in captured.out
    assert "Scored:" in captured.out
    assert "Unscored:" in captured.out
    assert "Contacted:" in captured.out
    assert "Disqualified:" in captured.out


def test_cmd_stats_prospects(tmp_path, capsys):
    leads = tmp_path / "leads.json"
    leads.write_text("[]\n")
    prospects = tmp_path / "prospects.json"
    prospects.write_text(
        json.dumps([{"name": "A", "status": "active"}, {"name": "B", "status": "closed"}])
    )
    customers = tmp_path / "customers.json"
    customers.write_text("[]\n")
    tool.cmd_stats(
        make_args(
            leads_file=str(leads),
            prospects_file=str(prospects),
            customers_file=str(customers),
        )
    )
    captured = capsys.readouterr()
    assert "Prospects: 2 (1 active, 1 closed)" in captured.out


def test_cmd_stats_customers(tmp_path, capsys):
    leads = tmp_path / "leads.json"
    leads.write_text("[]\n")
    prospects = tmp_path / "prospects.json"
    prospects.write_text("[]\n")
    customers = tmp_path / "customers.json"
    customers.write_text(
        json.dumps(
            [
                {"name": "A", "company": "Acme", "paid": True},
                {"name": "B", "company": "Acme", "paid": False},
            ]
        )
    )
    tool.cmd_stats(
        make_args(
            leads_file=str(leads),
            prospects_file=str(prospects),
            customers_file=str(customers),
        )
    )
    captured = capsys.readouterr()
    assert "Customers: 2 contacts (1 companies)" in captured.out
    assert "Paid:" in captured.out


def test_cmd_stats_empty_pipeline(tmp_path, capsys):
    leads = tmp_path / "leads.json"
    leads.write_text("[]\n")
    prospects = tmp_path / "prospects.json"
    prospects.write_text("[]\n")
    customers = tmp_path / "customers.json"
    customers.write_text("[]\n")
    tool.cmd_stats(
        make_args(
            leads_file=str(leads),
            prospects_file=str(prospects),
            customers_file=str(customers),
        )
    )
    captured = capsys.readouterr()
    assert "Leads: 0" in captured.out
    assert "Prospects: 0" in captured.out
    assert "Customers: 0" in captured.out


# --- cmd_validate ---

def test_cmd_validate_all_valid(tmp_path, capsys):
    leads = tmp_path / "leads.json"
    leads.write_text(json.dumps([{"name": "Alice", "linkedin_url": "https://linkedin.com/in/alice"}]))
    prospects = tmp_path / "prospects.json"
    prospects.write_text(json.dumps([{"name": "Bob", "linkedin_url": "https://linkedin.com/in/bob"}]))
    customers = tmp_path / "customers.json"
    customers.write_text("[]\n")
    tool.cmd_validate(
        make_args(config=None, leads_file=str(leads), prospects_file=str(prospects), customers_file=str(customers))
    )
    captured = capsys.readouterr()
    assert "All pipeline files are valid" in captured.out


def test_cmd_validate_invalid_json(tmp_path, capsys):
    leads = tmp_path / "leads.json"
    leads.write_text("not json")
    prospects = tmp_path / "prospects.json"
    prospects.write_text("[]\n")
    customers = tmp_path / "customers.json"
    customers.write_text("[]\n")
    with pytest.raises(SystemExit) as exc:
        tool.cmd_validate(
            make_args(config=None, leads_file=str(leads), prospects_file=str(prospects), customers_file=str(customers))
        )
    assert exc.value.code == 1


def test_cmd_validate_missing_identity(tmp_path, capsys):
    leads = tmp_path / "leads.json"
    leads.write_text(json.dumps([{"name": "Alice"}]))
    prospects = tmp_path / "prospects.json"
    prospects.write_text("[]\n")
    customers = tmp_path / "customers.json"
    customers.write_text("[]\n")
    with pytest.raises(SystemExit) as exc:
        tool.cmd_validate(
            make_args(config=None, leads_file=str(leads), prospects_file=str(prospects), customers_file=str(customers))
        )
    assert exc.value.code == 1


def test_cmd_validate_duplicate_identity(tmp_path, capsys):
    leads = tmp_path / "leads.json"
    leads.write_text(json.dumps([
        {"name": "Alice", "linkedin_url": "https://linkedin.com/in/alice"},
        {"name": "Alice2", "linkedin_url": "https://linkedin.com/in/alice"},
    ]))
    prospects = tmp_path / "prospects.json"
    prospects.write_text("[]\n")
    customers = tmp_path / "customers.json"
    customers.write_text("[]\n")
    with pytest.raises(SystemExit) as exc:
        tool.cmd_validate(
            make_args(config=None, leads_file=str(leads), prospects_file=str(prospects), customers_file=str(customers))
        )
    assert exc.value.code == 1


# --- cmd_recent ---

@pytest.fixture
def patched_pipeline(tmp_path):
    """Temporarily point PIPELINE_FILES at tmp_path for recent/list tests."""
    orig_dir = schema.CRM_DIR
    orig_pipeline = tool.PIPELINE_FILES
    orig_leads = tool.LEADS_FILE
    orig_prospects = tool.PROSPECTS_FILE
    orig_customers = tool.CUSTOMERS_FILE
    schema.CRM_DIR = tmp_path
    pipeline = [
        ("leads", tmp_path / "leads.json"),
        ("prospects", tmp_path / "prospects.json"),
        ("customers", tmp_path / "customers.json"),
    ]
    tool.PIPELINE_FILES = pipeline
    tool.LEADS_FILE = tmp_path / "leads.json"
    tool.PROSPECTS_FILE = tmp_path / "prospects.json"
    tool.CUSTOMERS_FILE = tmp_path / "customers.json"
    yield tmp_path
    schema.CRM_DIR = orig_dir
    tool.PIPELINE_FILES = orig_pipeline
    tool.LEADS_FILE = orig_leads
    tool.PROSPECTS_FILE = orig_prospects
    tool.CUSTOMERS_FILE = orig_customers


def test_cmd_recent_basic(patched_pipeline, capsys):
    leads = patched_pipeline / "leads.json"
    leads.write_text(json.dumps([
        {"name": "Alice", "company": "Acme", "added": "2026-01-03", "linkedin_url": "https://linkedin.com/in/alice"},
        {"name": "Bob", "company": "Acme", "added": "2026-01-01", "linkedin_url": "https://linkedin.com/in/bob"},
    ]))
    tool.cmd_recent(make_args(num=2, stage=None, leads_file=None, prospects_file=None, customers_file=None))
    captured = capsys.readouterr()
    assert "Alice" in captured.out
    assert "Bob" in captured.out


def test_cmd_recent_stage_filter(patched_pipeline, capsys):
    leads = patched_pipeline / "leads.json"
    leads.write_text(json.dumps([
        {"name": "Alice", "company": "Acme", "added": "2026-01-03", "linkedin_url": "https://linkedin.com/in/alice"},
    ]))
    prospects = patched_pipeline / "prospects.json"
    prospects.write_text(json.dumps([
        {"name": "Bob", "company": "Acme", "added": "2026-01-01", "linkedin_url": "https://linkedin.com/in/bob"},
    ]))
    tool.cmd_recent(make_args(num=10, stage="prospects", leads_file=None, prospects_file=None, customers_file=None))
    captured = capsys.readouterr()
    assert "Bob" in captured.out
    assert "Alice" not in captured.out


# --- cmd_demote ---

def test_cmd_demote_prospect_to_lead(tmp_path, capsys):
    prospects = tmp_path / "prospects.json"
    prospects.write_text(json.dumps([
        {"name": "Alice", "linkedin_url": "https://linkedin.com/in/alice"},
    ]))
    leads = tmp_path / "leads.json"
    leads.write_text("[]\n")
    tool.cmd_demote(
        make_args(
            linkedin_url="https://linkedin.com/in/alice",
            prospect=True,
            customer=False,
            from_file=str(prospects),
            to_file=str(leads),
        )
    )
    captured = capsys.readouterr()
    assert "Demoted" in captured.out
    assert len(json.loads(prospects.read_text())) == 0
    assert len(json.loads(leads.read_text())) == 1


def test_cmd_demote_customer_to_prospect(tmp_path, capsys):
    customers = tmp_path / "customers.json"
    customers.write_text(json.dumps([
        {"name": "Alice", "linkedin_url": "https://linkedin.com/in/alice"},
    ]))
    prospects = tmp_path / "prospects.json"
    prospects.write_text("[]\n")
    tool.cmd_demote(
        make_args(
            linkedin_url="https://linkedin.com/in/alice",
            prospect=False,
            customer=True,
            from_file=str(customers),
            to_file=str(prospects),
        )
    )
    captured = capsys.readouterr()
    assert "Demoted" in captured.out
    assert len(json.loads(customers.read_text())) == 0
    assert len(json.loads(prospects.read_text())) == 1


def test_cmd_demote_missing_record(tmp_path):
    prospects = tmp_path / "prospects.json"
    prospects.write_text("[]\n")
    leads = tmp_path / "leads.json"
    leads.write_text("[]\n")
    with pytest.raises(SystemExit) as exc:
        tool.cmd_demote(
            make_args(
                linkedin_url="https://linkedin.com/in/alice",
                prospect=True,
                customer=False,
                from_file=str(prospects),
                to_file=str(leads),
            )
        )
    assert exc.value.code == 1


# --- cmd_list ---

def test_cmd_list_basic(patched_pipeline, capsys):
    leads = patched_pipeline / "leads.json"
    leads.write_text(json.dumps([
        {"name": "Alice", "company": "Acme", "score": "⭐⭐⭐⭐", "linkedin_url": "https://linkedin.com/in/alice"},
        {"name": "Bob", "company": "Bio", "score": None, "linkedin_url": "https://linkedin.com/in/bob"},
    ]))
    tool.cmd_list(make_args(stage="leads", score=None, company=None, query=None, limit=None, file=None))
    captured = capsys.readouterr()
    assert "Alice" in captured.out
    assert "Bob" in captured.out


def test_cmd_list_with_filters(patched_pipeline, capsys):
    leads = patched_pipeline / "leads.json"
    leads.write_text(json.dumps([
        {"name": "Alice", "company": "Acme", "score": "⭐⭐⭐⭐", "linkedin_url": "https://linkedin.com/in/alice"},
        {"name": "Bob", "company": "Bio", "score": None, "linkedin_url": "https://linkedin.com/in/bob"},
    ]))
    tool.cmd_list(make_args(stage="leads", score="⭐⭐⭐⭐", company=None, query=None, limit=None, file=None))
    captured = capsys.readouterr()
    assert "Alice" in captured.out
    assert "Bob" not in captured.out


def test_cmd_list_limit(patched_pipeline, capsys):
    leads = patched_pipeline / "leads.json"
    leads.write_text(json.dumps([
        {"name": "Alice", "company": "Acme", "score": None, "linkedin_url": "https://linkedin.com/in/alice"},
        {"name": "Bob", "company": "Bio", "score": None, "linkedin_url": "https://linkedin.com/in/bob"},
    ]))
    tool.cmd_list(make_args(stage="leads", score=None, company=None, query=None, limit=1, file=None))
    captured = capsys.readouterr()
    # Should show 1 of 2 records
    assert "1 of 2" in captured.out


def test_cmd_list_unknown_stage():
    with pytest.raises(SystemExit) as exc:
        tool.cmd_list(make_args(stage="unknown", score=None, company=None, query=None, limit=None, file=None))
    assert exc.value.code == 1


# --- --json output flag ---

def test_json_mode_search(patched_pipeline, capsys):
    leads = patched_pipeline / "leads.json"
    leads.write_text(json.dumps([
        {"name": "Alice", "company": "Acme", "linkedin_url": "https://linkedin.com/in/alice"},
    ]))
    tool._set_json_mode(True)
    try:
        tool.cmd_search(make_args(query="Alice", person=False, company=False, competitor=False))
    finally:
        tool._set_json_mode(False)
    captured = capsys.readouterr()
    data = json.loads(captured.out)
    assert "results" in data
    assert len(data["results"]) == 1


def test_json_mode_stats(tmp_path, capsys):
    leads = tmp_path / "leads.json"
    leads.write_text("[]\n")
    prospects = tmp_path / "prospects.json"
    prospects.write_text("[]\n")
    customers = tmp_path / "customers.json"
    customers.write_text("[]\n")
    tool._set_json_mode(True)
    try:
        tool.cmd_stats(
            make_args(
                leads_file=str(leads),
                prospects_file=str(prospects),
                customers_file=str(customers),
            )
        )
    finally:
        tool._set_json_mode(False)
    captured = capsys.readouterr()
    data = json.loads(captured.out)
    assert "leads" in data
    assert data["leads"]["total"] == 0
