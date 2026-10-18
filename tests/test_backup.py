"""Tests for atomic CRM ZIP backups."""

import json
from datetime import datetime, timezone
from pathlib import Path
from zipfile import ZipFile

import pytest

from jsoncrm.backup import MANIFEST_NAME, create_backup

NOW = datetime(2026, 10, 17, 12, 0, tzinfo=timezone.utc)


def _write(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_backup_archives_files_and_recovers_by_extraction(tmp_path):
    repo = tmp_path / "repo"
    crm = repo / "crm"
    (repo / ".git").mkdir(parents=True)
    (crm / "nested").mkdir(parents=True)
    _write(crm / ".crm.json", '{"name":"test-crm"}\n')
    _write(crm / "leads.json", '[{"name":"Alice","score":"⭐⭐⭐⭐"}]\n')
    _write(crm / "nested" / "customers.json", '[]\n')
    _write(crm / "competitors.json", '{"companies":[]}\n')
    output = tmp_path / "external" / "backup.zip"

    result = create_backup(
        crm,
        [
            crm / ".crm.json",
            crm / "leads.json",
            crm / "prospects.json",
            crm / "nested" / "customers.json",
            crm / "competitors.json",
            crm / "leads.json",
        ],
        output=output,
        now=NOW,
    )

    assert result == {
        "backup": str(output.resolve()),
        "files": [".crm.json", "leads.json", "nested/customers.json", "competitors.json"],
        "missing": ["prospects.json"],
    }
    with ZipFile(output) as archive:
        assert set(archive.namelist()) == {
            ".crm.json",
            "leads.json",
            "nested/customers.json",
            "competitors.json",
            MANIFEST_NAME,
        }
        assert archive.read("leads.json") == (crm / "leads.json").read_bytes()
        manifest = json.loads(archive.read(MANIFEST_NAME))
        assert manifest == {
            "created_at": "2026-10-17T12:00:00Z",
            "files": result["files"],
            "missing": ["prospects.json"],
        }
        recovered = tmp_path / "recovered"
        archive.extractall(recovered)

    assert (recovered / "leads.json").read_bytes() == (crm / "leads.json").read_bytes()
    assert (recovered / "nested" / "customers.json").read_bytes() == (crm / "nested" / "customers.json").read_bytes()
    assert not list(output.parent.glob(".*.tmp-*"))


def test_backup_default_output_uses_home_and_timestamp(monkeypatch, tmp_path):
    home = tmp_path / "home"
    crm = tmp_path / "my crm"
    _write(crm / "leads.json", "[]\n")
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))

    result = create_backup(crm, [crm / "leads.json"], now=NOW)

    output = home / ".jsoncrm" / "backups" / "my-crm-20261017T120000000000Z.zip"
    assert result["backup"] == str(output.resolve())
    assert output.exists()


def test_backup_fails_when_nothing_exists(tmp_path):
    crm = tmp_path / "crm"
    crm.mkdir()
    output = tmp_path / "backup.zip"

    with pytest.raises(ValueError, match="no CRM files found"):
        create_backup(crm, [crm / "missing.json"], output=output, now=NOW)

    assert not output.exists()


def test_backup_refuses_to_overwrite(tmp_path):
    crm = tmp_path / "crm"
    _write(crm / "leads.json", "[]\n")
    output = tmp_path / "backup.zip"
    _write(output, "existing backup")

    with pytest.raises(ValueError, match="backup already exists"):
        create_backup(crm, [crm / "leads.json"], output=output, now=NOW)

    assert output.read_text(encoding="utf-8") == "existing backup"


def test_backup_rejects_source_outside_crm(tmp_path):
    crm = tmp_path / "crm"
    crm.mkdir()
    outside = tmp_path / "outside.json"
    _write(outside, "[]\n")

    with pytest.raises(ValueError, match="CRM source is outside"):
        create_backup(crm, [outside], output=tmp_path / "backup.zip", now=NOW)


def test_backup_rejects_non_file_source(tmp_path):
    crm = tmp_path / "crm"
    (crm / "leads.json").mkdir(parents=True)

    with pytest.raises(ValueError, match="not a file"):
        create_backup(crm, [crm / "leads.json"], output=tmp_path / "backup.zip", now=NOW)


def test_cmd_backup_omits_optional_missing_files(monkeypatch, tmp_path, capsys):
    from types import SimpleNamespace

    import jsoncrm.tool as tool

    crm = tmp_path / "crm"
    leads = crm / "leads.json"
    prospects = crm / "prospects.json"
    customers = crm / "customers.json"
    competitors = crm / "competitors.json"
    for path in (leads, prospects, customers):
        _write(path, "[]\n")
    _write(competitors, '{"companies":[]}\n')
    monkeypatch.setattr(tool, "CRM_DIR", crm)
    monkeypatch.setattr(tool, "PIPELINE_FILES", [
        ("leads", leads), ("prospects", prospects), ("customers", customers),
    ])
    monkeypatch.setattr(tool, "COMPETITORS_FILE", competitors)
    monkeypatch.setattr(tool, "PENDING_FILE", crm / ".pending_update.json")
    tool._set_json_mode(True)
    try:
        tool.cmd_backup(SimpleNamespace(
            config=None,
            output=str(tmp_path / "backup.zip"),
        ))
    finally:
        tool._set_json_mode(False)

    result = json.loads(capsys.readouterr().out)
    assert result["missing"] == []
    assert result["files"] == ["leads.json", "prospects.json", "customers.json", "competitors.json"]


def test_backup_rejects_destination_inside_git_repository(tmp_path):
    repo = tmp_path / "repo"
    crm = repo / "crm"
    (repo / ".git").mkdir(parents=True)
    _write(crm / "leads.json", "[]\n")
    output = repo / "backups" / "backup.zip"

    with pytest.raises(ValueError, match="outside the Git repository"):
        create_backup(crm, [crm / "leads.json"], output=output, now=NOW)

    assert not output.exists()
