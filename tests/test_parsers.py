"""Unit tests for jsoncrm.parsers."""

import json
import sys
from pathlib import Path
from types import SimpleNamespace


from jsoncrm.parsers import cmd_parse_from_linkedin_mcp


# --- cmd_parse_from_linkedin_mcp ---

def test_parse_likers_format(tmp_path, capsys):
    path = tmp_path / "likers.json"
    path.write_text(
        json.dumps(
            {
                "url": "https://linkedin.com/post/123",
                "likers": [
                    {
                        "name": "Liker One\nView Liker One's profile\n· 2nd\nFounder at Startup",
                        "url": "https://www.linkedin.com/in/liker-one/",
                    }
                ],
            },
            indent=2,
        )
    )
    cmd_parse_from_linkedin_mcp(SimpleNamespace(files=[str(path)]))
    parsed = json.loads(path.read_text())
    assert len(parsed) == 1
    assert parsed[0]["name"] == "Liker One"
    assert parsed[0]["position"] == "Founder"
    assert parsed[0]["company"] == "Startup"
    assert parsed[0]["linkedin_url"] == "https://www.linkedin.com/in/liker-one/"
    assert parsed[0]["source"] == "linkedin_mcp"
    assert parsed[0]["connected"] is False
    captured = capsys.readouterr()
    assert "Successfully converted 1 records" in captured.out


def test_parse_inbox_format(tmp_path, capsys):
    path = tmp_path / "inbox.json"
    path.write_text(
        json.dumps(
            {
                "conversations": [
                    {
                        "name": "Inbox Person",
                        "username": "inbox-person",
                        "thread_url": "/messaging/thread/123/",
                    }
                ]
            },
            indent=2,
        )
    )
    cmd_parse_from_linkedin_mcp(SimpleNamespace(files=[str(path)]))
    parsed = json.loads(path.read_text())
    assert len(parsed) == 1
    assert parsed[0]["name"] == "Inbox Person"
    assert parsed[0]["linkedin_url"] == "https://www.linkedin.com/in/inbox-person/"
    assert parsed[0]["position"] == ""
    assert parsed[0]["company"] is None


def test_parse_references_format(tmp_path, capsys):
    path = tmp_path / "refs.json"
    path.write_text(
        json.dumps(
            {
                "references": {
                    "search_results": [
                        {
                            "kind": "person",
                            "text": "Ref Person\n· 1st degree connection\nResearcher @ University",
                            "url": "/in/ref-person/",
                        },
                        {
                            "kind": "company",
                            "text": "Some Company",
                            "url": "/company/some-co/",
                        },
                    ]
                }
            },
            indent=2,
        )
    )
    cmd_parse_from_linkedin_mcp(SimpleNamespace(files=[str(path)]))
    parsed = json.loads(path.read_text())
    assert len(parsed) == 1
    assert parsed[0]["name"] == "Ref Person"
    assert parsed[0]["position"] == "Researcher"
    assert parsed[0]["company"] == "University"
    assert parsed[0]["linkedin_url"] == "https://www.linkedin.com/in/ref-person/"
    assert parsed[0]["connected"] is True


def test_parse_references_at_separator(tmp_path, capsys):
    path = tmp_path / "refs.json"
    path.write_text(
        json.dumps(
            {
                "references": {
                    "results": [
                        {
                            "kind": "person",
                            "text": "Jane Doe\nCEO at BigCorp",
                            "url": "https://www.linkedin.com/in/jane/",
                        }
                    ]
                }
            },
            indent=2,
        )
    )
    cmd_parse_from_linkedin_mcp(SimpleNamespace(files=[str(path)]))
    parsed = json.loads(path.read_text())
    assert parsed[0]["name"] == "Jane Doe"
    assert parsed[0]["position"] == "CEO"
    assert parsed[0]["company"] == "BigCorp"


def test_parse_invalid_format_warns(tmp_path, capsys):
    path = tmp_path / "bad.json"
    path.write_text(json.dumps(["this", "is", "a", "list"]))
    cmd_parse_from_linkedin_mcp(SimpleNamespace(files=[str(path)]))
    captured = capsys.readouterr()
    assert "must be a recognized MCP output format (dict)" in captured.out


def test_parse_no_people_warns(tmp_path, capsys):
    path = tmp_path / "empty.json"
    path.write_text(json.dumps({"references": {"main": [{"kind": "company", "url": "x"}]}}))
    cmd_parse_from_linkedin_mcp(SimpleNamespace(files=[str(path)]))
    captured = capsys.readouterr()
    assert "No people records found" in captured.out


def test_parse_missing_file_warns(tmp_path, capsys):
    path = tmp_path / "missing.json"
    cmd_parse_from_linkedin_mcp(SimpleNamespace(files=[str(path)]))
    captured = capsys.readouterr()
    assert "not found" in captured.out


def test_parse_likers_emits_full_schema(tmp_path, capsys):
    """Regression: parser must emit all CRM schema fields, not a subset.

    Bug: parser previously wrote 12 fields, missing last_contact,
    next_follow_up, and github_issue.
    """
    path = tmp_path / "likers.json"
    path.write_text(json.dumps({
        "url": "https://linkedin.com/post/123",
        "likers": [{"name": "Liker One\n· 2nd\nFounder at Startup", "url": "https://www.linkedin.com/in/liker-one/"}],
    }, indent=2))
    cmd_parse_from_linkedin_mcp(SimpleNamespace(files=[str(path)]))
    parsed = json.loads(path.read_text())
    required = {"name","position","company","linkedin_url","connected",
                "email","contacted_at","last_contact","next_follow_up",
                "source","added","score","github_issue","notes"}
    assert set(parsed[0].keys()) == required, (
        f"missing: {required - set(parsed[0].keys())}, "
        f"extra: {set(parsed[0].keys()) - required}")
    assert parsed[0]["last_contact"] is None
    assert parsed[0]["next_follow_up"] is None
    assert parsed[0]["github_issue"] is None
