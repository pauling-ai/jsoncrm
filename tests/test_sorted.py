"""End-to-end coverage for sorted, schema-constrained ledger stages."""

import json
import random
import subprocess
import sys
from datetime import date, timedelta
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from jsoncrm.config import Config
from jsoncrm.invariants import sort_records
from jsoncrm.tool import add_record, update_record


def iso(days):
    return (date.today() + timedelta(days=days)).isoformat()


@pytest.fixture
def ledger_crm(tmp_path):
    config = {
        "name": "bids",
        "identity": {"primary": "sol_id", "fallback": ["active_key"]},
        "pipeline": {
            "stages": [
                {
                    "name": "active",
                    "file": "active.json",
                    "recent_key": "deadline",
                    "sort": {
                        "key": "deadline",
                        "type": "iso-date",
                        "nulls": "last",
                        "tiebreak": "active_key",
                    },
                    "fields": {
                        "sol_id": {"required": True, "type": "string"},
                        "active_key": {"required": True, "type": "string"},
                        "agency": {"required": True, "type": "string"},
                        "classification": {
                            "required": True,
                            "enum": ["PRIME", "SUB", "EVALUATE", "ESCALATE"],
                        },
                        "status": {"forbidden": True},
                    },
                },
                {
                    "name": "passive",
                    "file": "passive.json",
                    "sort": {"key": "check_at", "type": "iso-date", "tiebreak": "sol_id"},
                },
                {
                    "name": "submitted",
                    "file": "submitted.json",
                    "sort": {"key": "submitted_at", "type": "iso-date", "tiebreak": "sol_id"},
                    "fields": {
                        "id": {"required": True, "type": "string"},
                        "submitted_at": {"required": True, "type": "iso-date"},
                        "kind": {"required": True, "enum": ["submitted"]},
                    },
                },
                {"name": "declined", "file": "declined.json"},
            ],
            "transitions": {
                "active": ["passive", "submitted", "declined"],
                "passive": ["active", "declined"],
            },
            "maps": {
                "active->passive": {"rename": {"deadline": "check_at"}},
                "active->submitted": {
                    "drop": ["deadline"],
                    "set": {
                        "id": "{today}-{sol_id}",
                        "submitted_at": "{today}",
                        "kind": "submitted",
                    },
                },
            },
        },
    }
    active = [
        {
            "sol_id": "SOL-1",
            "active_key": "a",
            "agency": "Agency A",
            "classification": "PRIME",
            "deadline": iso(1),
        },
        {
            "sol_id": "SOL-2",
            "active_key": "b",
            "agency": "Agency B",
            "company": "Agency B",
            "classification": "SUB",
            "deadline": iso(3),
            "notes": "long notes " * 100,
        },
        {
            "sol_id": "SOL-3",
            "active_key": "c",
            "agency": "Agency C",
            "classification": "EVALUATE",
            "deadline": None,
        },
    ]
    passive = [{
        "sol_id": "PASSIVE-1",
        "active_key": "taken",
        "check_at": iso(2),
    }]
    for name, rows in (
        ("active", active),
        ("passive", passive),
        ("submitted", []),
        ("declined", []),
    ):
        (tmp_path / f"{name}.json").write_text(json.dumps(rows, indent=2) + "\n")
    (tmp_path / ".crm.json").write_text(json.dumps(config, indent=2) + "\n")
    return tmp_path


def run_cli(crm, *args):
    return subprocess.run(
        [sys.executable, "-m", "jsoncrm", "--config", str(crm / ".crm.json"), *args],
        capture_output=True,
        text=True,
        check=False,
    )


def read_stage(crm, stage):
    return json.loads((crm / f"{stage}.json").read_text())


def test_validate_accepts_sorted_ledger(ledger_crm):
    result = run_cli(ledger_crm, "validate", "--json")
    assert result.returncode == 0, result.stdout + result.stderr
    assert json.loads(result.stdout)["valid"] is True


def test_add_sorts_nulls_and_ties_and_rejects_configured_duplicates(ledger_crm):
    new_records = [
        {
            "sol_id": "SOL-0",
            "active_key": "z",
            "agency": "Agency Z",
            "classification": "PRIME",
            "deadline": iso(1),
        },
        {
            "sol_id": "SOL-4",
            "active_key": "aa",
            "agency": "Agency A",
            "classification": "PRIME",
            "deadline": iso(1),
        },
        {
            "sol_id": "SOL-5",
            "active_key": "last",
            "agency": "Agency L",
            "classification": "SUB",
            "deadline": None,
        },
    ]
    for record in new_records:
        result = run_cli(ledger_crm, "add", "--database_file", str(ledger_crm / "active.json"), "--item_json", json.dumps(record))
        assert result.returncode == 0, result.stdout + result.stderr

    rows = read_stage(ledger_crm, "active")
    assert [row["active_key"] for row in rows[:3]] == ["a", "aa", "z"]
    assert [row["deadline"] for row in rows[-2:]] == [None, None]

    duplicate = dict(new_records[0], sol_id="NEW-ID")
    result = run_cli(ledger_crm, "add", "--database_file", str(ledger_crm / "active.json"), "--item_json", json.dumps(duplicate))
    assert result.returncode == 1
    assert "active_key 'z' already exists" in result.stdout + result.stderr

    cross_stage = dict(new_records[0], sol_id="NEW-ID", active_key="taken")
    result = run_cli(ledger_crm, "add", "--database_file", str(ledger_crm / "active.json"), "--item_json", json.dumps(cross_stage))
    assert result.returncode == 1
    assert "already exists" in result.stdout + result.stderr


def test_update_resorts_and_enforces_fields_without_partial_writes(ledger_crm):
    result = run_cli(
        ledger_crm,
        "update",
        "--database_file", str(ledger_crm / "active.json"),
        "--item_json", json.dumps({"sol_id": "SOL-2", "deadline": iso(0)}),
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert read_stage(ledger_crm, "active")[0]["sol_id"] == "SOL-2"

    before = (ledger_crm / "active.json").read_text()
    result = run_cli(
        ledger_crm,
        "update",
        "--database_file", str(ledger_crm / "active.json"),
        "--item_json", json.dumps({"sol_id": "SOL-2", "classification": "INVALID"}),
    )
    assert result.returncode == 1
    assert "must be one of" in result.stdout + result.stderr
    assert (ledger_crm / "active.json").read_text() == before

    result = run_cli(
        ledger_crm,
        "update",
        "--database_file", str(ledger_crm / "active.json"),
        "--item_json", json.dumps({"sol_id": "SOL-2", "deadline": "not-a-date"}),
    )
    assert result.returncode == 1
    assert "iso-date" in result.stdout + result.stderr
    assert (ledger_crm / "active.json").read_text() == before


def test_move_applies_maps_and_sorts_destination(ledger_crm):
    result = run_cli(
        ledger_crm,
        "move", "SOL-1", "--from", "active", "--to", "passive",
    )
    assert result.returncode == 0, result.stdout + result.stderr
    passive = read_stage(ledger_crm, "passive")
    moved = next(row for row in passive if row["sol_id"] == "SOL-1")
    assert moved["check_at"] == iso(1)
    assert "deadline" not in moved
    assert [row["check_at"] for row in passive] == [iso(1), iso(2)]

    result = run_cli(
        ledger_crm,
        "move", "SOL-2", "--from", "active", "--to", "submitted",
    )
    assert result.returncode == 0, result.stdout + result.stderr
    submitted = read_stage(ledger_crm, "submitted")[0]
    assert submitted["id"] == f"{date.today().isoformat()}-SOL-2"
    assert submitted["submitted_at"] == date.today().isoformat()
    assert submitted["kind"] == "submitted"
    assert "deadline" not in submitted

    result = run_cli(ledger_crm, "move", "PASSIVE-1", "--from", "passive", "--to", "submitted")
    assert result.returncode == 1
    assert "not configured" in result.stdout + result.stderr


def test_find_comparisons_windows_and_projection(ledger_crm):
    result = run_cli(
        ledger_crm,
        "find",
        "--database_file", str(ledger_crm / "active.json"),
        "--item_json", json.dumps({"deadline__lte": iso(2)}),
        "--fields", "sol_id", "agency",
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert json.loads(result.stdout) == [{"sol_id": "SOL-1", "agency": "Agency A"}]

    result = run_cli(
        ledger_crm,
        "find",
        "--database_file", str(ledger_crm / "active.json"),
        "--item_json", json.dumps({"deadline__within": 2, "classification": "PRIME"}),
        "--fields", "sol_id",
    )
    assert json.loads(result.stdout) == [{"sol_id": "SOL-1"}]
    assert "notes" not in result.stdout


def test_recent_uses_stage_date_field(ledger_crm):
    result = run_cli(ledger_crm, "recent", "--stage", "active", "--num", "1", "--json")
    assert result.returncode == 0
    assert json.loads(result.stdout)[0]["sol_id"] == "SOL-2"


def test_validate_reports_sortedness_schema_and_forbidden_fields(ledger_crm):
    rows = read_stage(ledger_crm, "active")
    rows[0], rows[1] = rows[1], rows[0]
    rows[0]["classification"] = "INVALID"
    rows[0]["status"] = "unexpected"
    (ledger_crm / "active.json").write_text(json.dumps(rows) + "\n")

    result = run_cli(ledger_crm, "validate", "--json")
    assert result.returncode == 1
    report = json.loads(result.stdout)
    messages = [error["error"] for error in report["errors"]]
    assert any("not sorted" in message for message in messages)
    assert any("must be one of" in message for message in messages)
    assert any("forbidden" in message for message in messages)


def test_shuffle_rejects_sorted_stage_but_allows_unsorted_stage(ledger_crm):
    result = run_cli(ledger_crm, "shuffle", str(ledger_crm / "active.json"), "--seed", "1")
    assert result.returncode == 1
    assert "cannot shuffle sorted stage" in result.stdout + result.stderr

    result = run_cli(ledger_crm, "shuffle", str(ledger_crm / "declined.json"), "--seed", "1")
    assert result.returncode == 0


def test_random_mutation_sequences_preserve_sorted_invariant(ledger_crm):
    cfg = Config.from_file(str(ledger_crm / ".crm.json"))
    stage = cfg.pipeline_stages[0]
    fields = [cfg.identity_primary, *cfg.identity_fallback]
    rng = random.Random(7341)
    rows = []

    for index in range(75):
        rows, _record = add_record(
            rows,
            {
                "sol_id": f"RANDOM-{index}",
                "active_key": f"key-{index:03}",
                "agency": "Random",
                "classification": "PRIME",
                "deadline": iso(rng.randint(-10, 30)) if index % 7 else None,
            },
            stage=stage,
            fields=fields,
        )
        assert sort_records(rows, stage, fields) == rows

    for index in range(0, 75, 3):
        rows, _record, _unknown = update_record(
            rows,
            {"sol_id": f"RANDOM-{index}", "deadline": iso(rng.randint(-10, 30))},
            stage=stage,
            fields=fields,
        )
        assert sort_records(rows, stage, fields) == rows

    first = json.dumps(rows, ensure_ascii=False, indent=2) + "\n"
    second = json.dumps(sort_records(rows, stage, fields), ensure_ascii=False, indent=2) + "\n"
    assert first == second


def test_context_writer_owns_sorted_file_invariant(ledger_crm):
    from jsoncrm.context import CRMContext

    context = CRMContext.from_file(str(ledger_crm / ".crm.json"))
    active = read_stage(ledger_crm, "active")
    context.write_json(ledger_crm / "active.json", list(reversed(active)))
    assert read_stage(ledger_crm, "active") == active

    declined = [{"sol_id": "B"}, {"sol_id": "A"}]
    context.write_json(ledger_crm / "declined.json", declined)
    assert read_stage(ledger_crm, "declined") == declined


@pytest.mark.asyncio
async def test_web_mutations_share_sorted_ledger_behavior(ledger_crm):
    from jsoncrm.server import create_app

    app = create_app(config_path=str(ledger_crm / ".crm.json"))
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        record = {
            "sol_id": "WEB-1",
            "active_key": "0-web",
            "agency": "Web Agency",
            "classification": "PRIME",
            "deadline": iso(-1),
        }
        response = await client.post("/api/data/active", json={"record": record})
        assert response.status_code == 200, response.text
        assert read_stage(ledger_crm, "active")[0]["sol_id"] == "WEB-1"

        response = await client.patch(
            "/api/data/active",
            json={"updates": {"sol_id": "WEB-1", "deadline": iso(10)}},
        )
        assert response.status_code == 200, response.text
        rows = read_stage(ledger_crm, "active")
        assert [row["deadline"] for row in rows[:-2]] == sorted(row["deadline"] for row in rows[:-2])
        assert rows[-2]["sol_id"] == "WEB-1"

        response = await client.post(
            "/api/move",
            json={"identity": {"sol_id": "WEB-1"}, "from_stage": "active", "to_stage": "passive"},
        )
        assert response.status_code == 200, response.text
        assert response.json()["record"]["check_at"] == iso(10)


def test_dry_runs_leave_sorted_files_byte_identical(ledger_crm):
    paths = [ledger_crm / f"{stage}.json" for stage in ("active", "passive", "submitted")]
    before = {path: path.read_bytes() for path in paths}
    record = {
        "sol_id": "DRY-1",
        "active_key": "dry",
        "agency": "Dry Agency",
        "classification": "PRIME",
        "deadline": iso(0),
    }
    commands = [
        ("add", "--database_file", str(ledger_crm / "active.json"), "--item_json", json.dumps(record), "--dry-run"),
        ("update", "--database_file", str(ledger_crm / "active.json"), "--item_json", json.dumps({"sol_id": "SOL-2", "deadline": iso(0)}), "--dry-run"),
        ("move", "SOL-1", "--from", "active", "--to", "passive", "--dry-run", "--json"),
    ]
    for command in commands:
        result = run_cli(ledger_crm, *command)
        assert result.returncode == 0, result.stdout + result.stderr
        assert json.loads(result.stdout)["dry_run"] is True
        assert {path: path.read_bytes() for path in paths} == before


def test_merge_and_pending_update_preserve_sorted_stage(ledger_crm):
    active_path = ledger_crm / "active.json"
    rows = read_stage(ledger_crm, "active")
    rows[0]["linkedin_url"] = "https://example.com/sol-1"
    active_path.write_text(json.dumps(rows, indent=2) + "\n")
    merged = {
        "sol_id": "MERGE-1",
        "active_key": "merge",
        "agency": "Merge Agency",
        "classification": "PRIME",
        "deadline": iso(0),
        "linkedin_url": "https://example.com/merge",
        "score": "⭐⭐⭐",
    }
    source = ledger_crm / "merge.json"
    source.write_text(json.dumps([merged]) + "\n")
    result = run_cli(ledger_crm, "merge", str(source), "--leads-file", str(active_path))
    assert result.returncode == 0, result.stdout + result.stderr
    assert read_stage(ledger_crm, "active")[0]["sol_id"] == "MERGE-1"

    pending = ledger_crm / "pending.json"
    pending.write_text(json.dumps({
        "linkedin_url": "https://example.com/sol-1",
        "target_file": str(active_path),
        "fields": {"deadline": iso(-1)},
    }) + "\n")
    result = run_cli(ledger_crm, "apply_update", str(pending))
    assert result.returncode == 0, result.stdout + result.stderr
    assert read_stage(ledger_crm, "active")[0]["sol_id"] == "SOL-1"
    assert not pending.exists()


def test_delete_and_filter_preserve_remaining_sorted_order(ledger_crm):
    result = run_cli(
        ledger_crm,
        "delete",
        "--database_file", str(ledger_crm / "active.json"),
        "--item_json", '{"sol_id":"SOL-1"}',
    )
    assert result.returncode == 0
    assert [row["sol_id"] for row in read_stage(ledger_crm, "active")] == ["SOL-2", "SOL-3"]

    (ledger_crm / "competitors.json").write_text(json.dumps({
        "companies": [{"name": "Agency B"}],
        "people": [],
    }) + "\n")
    result = run_cli(ledger_crm, "filter-competitors", str(ledger_crm / "active.json"))
    assert result.returncode == 0, result.stdout + result.stderr
    assert [row["sol_id"] for row in read_stage(ledger_crm, "active")] == ["SOL-3"]


def test_find_all_comparison_operators_and_output_file(ledger_crm):
    expectations = [
        ({"deadline__lt": iso(3)}, ["SOL-1"]),
        ({"deadline__gte": iso(3)}, ["SOL-2"]),
        ({"deadline__gt": iso(1)}, ["SOL-2"]),
        ({"classification__ne": "PRIME"}, ["SOL-2", "SOL-3"]),
    ]
    for matcher, expected in expectations:
        result = run_cli(
            ledger_crm,
            "find",
            "--database_file", str(ledger_crm / "active.json"),
            "--item_json", json.dumps(matcher),
            "--fields", "sol_id",
        )
        assert result.returncode == 0, result.stdout + result.stderr
        assert [row["sol_id"] for row in json.loads(result.stdout)] == expected

    output = ledger_crm / "query-output.json"
    result = run_cli(
        ledger_crm,
        "find",
        "--database_file", str(ledger_crm / "active.json"),
        "--item_json", json.dumps({"deadline__within": 1}),
        "--fields", "sol_id,deadline",
        "--output_file", str(output),
    )
    assert result.returncode == 0
    assert result.stdout == ""
    assert json.loads(output.read_text()) == [{"sol_id": "SOL-1", "deadline": iso(1)}]

    result = run_cli(
        ledger_crm,
        "find",
        "--database_file", str(ledger_crm / "active.json"),
        "--item_json", '{"deadline__unknown":1}',
    )
    assert result.returncode == 1
    assert "unknown query operator" in result.stdout + result.stderr


def test_add_enforces_required_and_forbidden_fields(ledger_crm):
    before = (ledger_crm / "active.json").read_bytes()
    base = {
        "sol_id": "INVALID-1",
        "active_key": "invalid",
        "classification": "PRIME",
        "deadline": iso(1),
    }
    result = run_cli(
        ledger_crm,
        "add",
        "--database_file", str(ledger_crm / "active.json"),
        "--item_json", json.dumps(base),
    )
    assert result.returncode == 1
    assert "missing required field 'agency'" in result.stdout + result.stderr

    result = run_cli(
        ledger_crm,
        "add",
        "--database_file", str(ledger_crm / "active.json"),
        "--item_json", json.dumps({**base, "agency": "Agency", "status": "unexpected"}),
    )
    assert result.returncode == 1
    assert "forbidden" in result.stdout + result.stderr
    assert (ledger_crm / "active.json").read_bytes() == before


def test_validate_detects_cross_stage_duplicate_identities(ledger_crm):
    rows = read_stage(ledger_crm, "active")
    rows.append({
        "sol_id": "UNIQUE",
        "active_key": "taken",
        "agency": "Duplicate",
        "classification": "PRIME",
        "deadline": None,
    })
    (ledger_crm / "active.json").write_text(json.dumps(rows) + "\n")
    result = run_cli(ledger_crm, "validate", "--json")
    assert result.returncode == 1
    report = json.loads(result.stdout)
    assert any("duplicate active_key 'taken'" in error["error"] for error in report["errors"])


def test_numeric_descending_nulls_first_and_unsorted_stage(tmp_path):
    config = {
        "identity": {"primary": "id", "fallback": []},
        "pipeline": {
            "stages": [
                {
                    "name": "items",
                    "file": "items.json",
                    "sort": {
                        "key": "rank",
                        "type": "number",
                        "direction": "desc",
                        "nulls": "first",
                        "tiebreak": "id",
                    },
                },
                {"name": "notes", "file": "notes.json"},
            ],
            "transitions": {},
        },
    }
    (tmp_path / ".crm.json").write_text(json.dumps(config) + "\n")
    initial = [{"id": "null", "rank": None}, {"id": "ten", "rank": 10}, {"id": "two", "rank": 2}]
    (tmp_path / "items.json").write_text(json.dumps(initial) + "\n")
    (tmp_path / "notes.json").write_text("[]\n")

    result = run_cli(tmp_path, "add", "--database_file", str(tmp_path / "items.json"), "--item_json", '{"id":"five","rank":5}')
    assert result.returncode == 0, result.stdout + result.stderr
    assert [row["id"] for row in json.loads((tmp_path / "items.json").read_text())] == ["null", "ten", "five", "two"]

    result = run_cli(tmp_path, "validate", "--json")
    assert result.returncode == 0, result.stdout + result.stderr

    for identity in ("first", "second"):
        result = run_cli(tmp_path, "add", "--database_file", str(tmp_path / "notes.json"), "--item_json", json.dumps({"id": identity}))
        assert result.returncode == 0
    assert [row["id"] for row in json.loads((tmp_path / "notes.json").read_text())] == ["first", "second"]


def test_repeat_context_writes_are_byte_stable(ledger_crm):
    from jsoncrm.context import CRMContext

    context = CRMContext.from_file(str(ledger_crm / ".crm.json"))
    path = ledger_crm / "active.json"
    rows = list(reversed(read_stage(ledger_crm, "active")))
    context.write_json(path, rows)
    first = path.read_bytes()
    context.write_json(path, rows)
    assert path.read_bytes() == first


def test_two_crm_contexts_do_not_share_configuration(tmp_path):
    from jsoncrm.context import CRMContext

    sorted_root = tmp_path / "sorted"
    plain_root = tmp_path / "plain"
    sorted_root.mkdir()
    plain_root.mkdir()
    sorted_config = {
        "pipeline": {
            "stages": [{"name": "leads", "file": "leads.json", "sort": {"key": "added", "type": "iso-date"}}],
            "transitions": {},
        }
    }
    (sorted_root / ".crm.json").write_text(json.dumps(sorted_config) + "\n")
    (plain_root / ".crm.json").write_text("{}\n")
    sorted_context = CRMContext.from_file(str(sorted_root / ".crm.json"))
    plain_context = CRMContext.from_file(str(plain_root / ".crm.json"))
    rows = [
        {"linkedin_url": "https://example.com/new", "added": "2026-11-02"},
        {"linkedin_url": "https://example.com/old", "added": "2026-11-01"},
    ]

    sorted_context.write_json(sorted_root / "leads.json", rows)
    plain_context.write_json(plain_root / "leads.json", rows)

    assert [row["added"] for row in json.loads((sorted_root / "leads.json").read_text())] == ["2026-11-01", "2026-11-02"]
    assert [row["added"] for row in json.loads((plain_root / "leads.json").read_text())] == ["2026-11-02", "2026-11-01"]
    assert sorted_context.stage_for_name("leads") is not plain_context.stage_for_name("leads")


def test_legacy_unsorted_cli_writes_keep_insertion_order(tmp_path):
    (tmp_path / ".crm.json").write_text("{}\n")
    leads = [
        {"name": "Newer", "linkedin_url": "https://example.com/newer", "added": "2026-11-02"},
        {"name": "Older", "linkedin_url": "https://example.com/older", "added": "2026-11-01"},
    ]
    (tmp_path / "leads.json").write_text(json.dumps(leads) + "\n")
    (tmp_path / "prospects.json").write_text(json.dumps([
        {"name": "Existing", "linkedin_url": "https://example.com/existing"}
    ]) + "\n")
    (tmp_path / "customers.json").write_text("[]\n")

    added = {"name": "Earliest", "linkedin_url": "https://example.com/earliest", "added": "2020-01-01"}
    result = run_cli(tmp_path, "add", "--database_file", str(tmp_path / "leads.json"), "--item_json", json.dumps(added))
    assert result.returncode == 0, result.stdout + result.stderr
    assert [row["name"] for row in json.loads((tmp_path / "leads.json").read_text())] == ["Newer", "Older", "Earliest"]

    result = run_cli(
        tmp_path,
        "update",
        "--database_file", str(tmp_path / "leads.json"),
        "--item_json", '{"linkedin_url":"https://example.com/older","added":"2019-01-01"}',
    )
    assert result.returncode == 0
    assert [row["name"] for row in json.loads((tmp_path / "leads.json").read_text())] == ["Newer", "Older", "Earliest"]

    result = run_cli(tmp_path, "promote", "https://example.com/newer", "--lead")
    assert result.returncode == 0, result.stdout + result.stderr
    assert [row["name"] for row in json.loads((tmp_path / "prospects.json").read_text())] == ["Existing", "Newer"]


@pytest.mark.asyncio
async def test_web_rejects_duplicate_and_invalid_sorted_records(ledger_crm):
    from jsoncrm.server import create_app

    app = create_app(config_path=str(ledger_crm / ".crm.json"))
    transport = ASGITransport(app=app)
    before = (ledger_crm / "active.json").read_bytes()
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        duplicate = {
            "sol_id": "SOL-1",
            "active_key": "different",
            "agency": "Duplicate",
            "classification": "PRIME",
            "deadline": iso(1),
        }
        response = await client.post("/api/data/active", json={"record": duplicate})
        assert response.status_code == 409

        response = await client.post("/api/data/active", json={"record": {**duplicate, "sol_id": "NEW", "classification": "BAD"}})
        assert response.status_code == 400
        assert (ledger_crm / "active.json").read_bytes() == before
