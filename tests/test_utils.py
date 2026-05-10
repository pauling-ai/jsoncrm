"""Unit tests for jsoncrm.utils helpers."""

import json
import sys
from pathlib import Path

import pytest


import jsoncrm.schema as schema
from jsoncrm.utils import (
    apply_updates,
    build_known_urls,
    coerce,
    find_record,
    iter_competitor_entries,
    load_json,
    match,
    normalize_company_name,
    normalize_url,
    record_identity_value,
    search_competitors,
)


# --- normalize_url ---

def test_normalize_url_strips_trailing_slash():
    assert normalize_url("https://linkedin.com/in/alice/") == "https://linkedin.com/in/alice"


def test_normalize_url_lowercases():
    assert normalize_url("HTTPS://LINKEDIN.COM/in/Alice") == "https://linkedin.com/in/alice"


def test_normalize_url_none_returns_empty():
    assert normalize_url(None) == ""


def test_normalize_url_no_trailing_slash():
    assert normalize_url("https://linkedin.com/in/bob") == "https://linkedin.com/in/bob"


# --- normalize_company_name ---

def test_normalize_company_name_lowercases():
    assert normalize_company_name("Acme Corp") == "acme corp"


def test_normalize_company_name_strips_special_chars():
    assert normalize_company_name("Schrödinger, Inc.") == "schrodinger inc"


def test_normalize_company_name_collapses_whitespace():
    assert normalize_company_name("  Big   Tech  ") == "big tech"


def test_normalize_company_name_none_returns_empty():
    assert normalize_company_name(None) == ""


# --- coerce ---

def test_coerce_true():
    assert coerce("true") is True
    assert coerce("True") is True
    assert coerce("TRUE") is True


def test_coerce_false():
    assert coerce("false") is False
    assert coerce("False") is False


def test_coerce_null():
    assert coerce("null") is None
    assert coerce("none") is None
    assert coerce("None") is None


def test_coerce_int():
    assert coerce("42") == 42
    assert coerce("0") == 0
    assert coerce("-3") == -3


def test_coerce_passthrough():
    assert coerce("hello") == "hello"
    assert coerce(123) == 123
    assert coerce(None) is None


# --- load_json ---

def test_load_json_existing_file(tmp_path):
    path = tmp_path / "data.json"
    path.write_text(json.dumps([{"name": "Alice"}], indent=2))
    assert load_json(path) == [{"name": "Alice"}]


def test_load_json_missing_file_returns_empty_list(tmp_path):
    path = tmp_path / "missing.json"
    assert load_json(path) == []


# --- record_identity_value ---

def test_record_identity_value_prefers_id():
    assert record_identity_value({"id": "123", "linkedin_url": "https://x.com/in/a"}) == ("id", "123")


def test_record_identity_value_fallback_to_url():
    assert record_identity_value({"linkedin_url": "https://x.com/in/a"}) == ("linkedin_url", "https://x.com/in/a")


def test_record_identity_value_no_identity():
    assert record_identity_value({"name": "Alice"}) == (None, None)


# --- match ---

def test_match_default_searches_name_company_url_email():
    record = {"name": "Alice", "company": "Acme", "linkedin_url": "https://x.com/in/a", "email": "a@ac.me"}
    assert match(record, "alice") is True
    assert match(record, "acme") is True
    assert match(record, "x.com/in/a") is True
    assert match(record, "a@ac.me") is True
    assert match(record, "zzz") is False


def test_match_person_mode():
    record = {"name": "Alice", "company": "Acme", "linkedin_url": "https://x.com/in/a", "email": "a@ac.me"}
    assert match(record, "alice", person=True) is True
    assert match(record, "acme", person=True) is False
    assert match(record, "a@ac.me", person=True) is True


def test_match_company_mode():
    record = {"name": "Alice", "company": "Acme", "linkedin_url": "https://x.com/in/a", "email": "a@ac.me"}
    assert match(record, "acme", company=True) is True
    assert match(record, "alice", company=True) is False


def test_match_case_insensitive():
    record = {"name": "Alice", "company": "Acme"}
    assert match(record, "ALICE") is True
    assert match(record, "ACME") is True


# --- iter_competitor_entries ---

def test_iter_competitor_entries_yields_dicts():
    data = {
        "companies": [{"name": "A"}, {"name": "B"}],
        "people": [{"name": "C"}],
    }
    results = list(iter_competitor_entries(data, ("companies", "people")))
    assert len(results) == 3
    assert results[0]["name"] == "A"


def test_iter_competitor_entries_skips_non_dicts():
    data = {"companies": [{"name": "A"}, "not-a-dict"]}
    results = list(iter_competitor_entries(data, ("companies",)))
    assert len(results) == 1


def test_iter_competitor_entries_missing_key():
    data = {}
    assert list(iter_competitor_entries(data, ("companies",))) == []


# --- search_competitors ---

def test_search_competitors_company_match(monkeypatch, tmp_path):
    competitors_file = tmp_path / "competitors.json"
    competitors_file.write_text(
        json.dumps(
            {"companies": [{"name": "Acme", "url": "https://linkedin.com/company/acme"}]},
            indent=2,
        )
        + "\n"
    )
    monkeypatch.setattr(schema, "COMPETITORS_FILE", competitors_file)
    hits = search_competitors("acme")
    assert len(hits) == 1
    assert hits[0][0] == "company"


def test_search_competitors_person_match(monkeypatch, tmp_path):
    competitors_file = tmp_path / "competitors.json"
    competitors_file.write_text(
        json.dumps(
            {"people": [{"name": "Alice", "url": "https://linkedin.com/in/alice"}]},
            indent=2,
        )
        + "\n"
    )
    monkeypatch.setattr(schema, "COMPETITORS_FILE", competitors_file)
    hits = search_competitors("alice")
    assert len(hits) == 1
    assert hits[0][0] == "person"


def test_search_competitors_missing_file_returns_empty(monkeypatch, tmp_path):
    competitors_file = tmp_path / "competitors.json"
    monkeypatch.setattr(schema, "COMPETITORS_FILE", competitors_file)
    assert search_competitors("anything") == []


def test_search_competitors_person_filter(monkeypatch, tmp_path):
    competitors_file = tmp_path / "competitors.json"
    competitors_file.write_text(
        json.dumps(
            {
                "companies": [{"name": "Acme", "url": "https://linkedin.com/company/acme"}],
                "people": [{"name": "Alice", "url": "https://linkedin.com/in/alice"}],
            },
            indent=2,
        )
        + "\n"
    )
    monkeypatch.setattr(schema, "COMPETITORS_FILE", competitors_file)
    hits = search_competitors("acme", person=True)
    assert len(hits) == 0
    hits = search_competitors("alice", person=True)
    assert len(hits) == 1


def test_search_competitors_company_filter(monkeypatch, tmp_path):
    competitors_file = tmp_path / "competitors.json"
    competitors_file.write_text(
        json.dumps(
            {
                "companies": [{"name": "Acme", "url": "https://linkedin.com/company/acme"}],
                "people": [{"name": "Alice", "url": "https://linkedin.com/in/alice"}],
            },
            indent=2,
        )
        + "\n"
    )
    monkeypatch.setattr(schema, "COMPETITORS_FILE", competitors_file)
    hits = search_competitors("alice", company=True)
    assert len(hits) == 0
    hits = search_competitors("acme", company=True)
    assert len(hits) == 1


# --- build_known_urls ---

def test_build_known_urls_from_explicit_files(tmp_path):
    leads = tmp_path / "leads.json"
    leads.write_text(json.dumps([{"linkedin_url": "https://linkedin.com/in/a"}]))
    prospects = tmp_path / "prospects.json"
    prospects.write_text(json.dumps([{"linkedin_url": "https://linkedin.com/in/b"}]))
    customers = tmp_path / "customers.json"
    customers.write_text(json.dumps([{"linkedin_url": "https://linkedin.com/in/c"}]))

    urls = build_known_urls(leads_file=str(leads), prospects_file=str(prospects), customers_file=str(customers))
    assert urls == {"https://linkedin.com/in/a", "https://linkedin.com/in/b", "https://linkedin.com/in/c"}


def test_build_known_urls_ignores_missing_files(tmp_path, monkeypatch):
    # When files don't exist, load_json returns [] so known_urls is empty
    empty = tmp_path / "empty.json"
    monkeypatch.setattr(schema, "LEADS_FILE", empty)
    monkeypatch.setattr(schema, "PROSPECTS_FILE", empty)
    monkeypatch.setattr(schema, "CUSTOMERS_FILE", empty)
    assert build_known_urls() == set()


# --- find_record ---

def test_find_record_by_url(tmp_path, monkeypatch):
    db = tmp_path / "db.json"
    db.write_text(
        json.dumps([{"name": "Alice", "linkedin_url": "https://linkedin.com/in/alice"}])
    )
    matches = find_record("https://linkedin.com/in/alice", target_file=str(db))
    assert len(matches) == 1
    assert matches[0][3]["name"] == "Alice"


def test_find_record_not_found(tmp_path, monkeypatch):
    db = tmp_path / "db.json"
    db.write_text(json.dumps([{"name": "Alice", "linkedin_url": "https://linkedin.com/in/alice"}]))
    assert find_record("https://linkedin.com/in/bob", target_file=str(db)) == []


def test_find_record_target_file(tmp_path):
    db = tmp_path / "db.json"
    db.write_text(
        json.dumps([{"name": "Alice", "linkedin_url": "https://linkedin.com/in/alice"}])
    )
    matches = find_record("https://linkedin.com/in/alice", target_file=str(db))
    assert len(matches) == 1


# --- apply_updates ---

def test_apply_updates_single_match(tmp_path, capsys):
    db = tmp_path / "db.json"
    db.write_text(
        json.dumps([{"name": "Alice", "linkedin_url": "https://linkedin.com/in/alice", "company": "Old"}])
    )
    apply_updates("https://linkedin.com/in/alice", {"company": "New"}, target_file=str(db))
    data = json.loads(db.read_text())
    assert data[0]["company"] == "New"
    captured = capsys.readouterr()
    assert "Saved: Alice" in captured.out


def test_apply_updates_no_match_exits(tmp_path):
    db = tmp_path / "db.json"
    db.write_text(json.dumps([{"name": "Alice", "linkedin_url": "https://linkedin.com/in/alice"}]))
    with pytest.raises(SystemExit) as exc:
        apply_updates("https://linkedin.com/in/bob", {"company": "New"}, target_file=str(db))
    assert exc.value.code == 1


def test_apply_updates_multiple_matches_exits(tmp_path, monkeypatch):
    db1 = tmp_path / "a.json"
    db1.write_text(json.dumps([{"name": "Alice", "linkedin_url": "https://linkedin.com/in/alice"}]))
    db2 = tmp_path / "b.json"
    db2.write_text(json.dumps([{"name": "Alice", "linkedin_url": "https://linkedin.com/in/alice"}]))
    monkeypatch.chdir(tmp_path)
    with pytest.raises(SystemExit) as exc:
        apply_updates("https://linkedin.com/in/alice", {"company": "New"})
    assert exc.value.code == 1


