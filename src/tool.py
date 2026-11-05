#!/usr/bin/env python3
"""Unified CRM tool — command implementations and CLI entry point."""

import argparse
import copy
import json
import os
import random
import sys
from datetime import date
from pathlib import Path

# Re-export everything from sub-modules so callers can import from jsoncrm.tool.
from jsoncrm.parsers import cmd_parse_from_linkedin_mcp  # noqa: F401
from jsoncrm.context import CRMContext
from jsoncrm.schema import COMPETITOR_COMPANY_KEYS, COMPETITOR_PERSON_KEYS, JSON_DB_ENCODING, score_value
from jsoncrm.invariants import (
    RecordError,
    ensure_unique,
    ensure_valid_record,
    identity_matches,
    record_errors,
    require_identity,
    sort_records,
)
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
    print_record,
    search_competitors,
)

# ---------------------------------------------------------------------------
# Global JSON-output mode (toggled by --json)
# ---------------------------------------------------------------------------
_JSON_MODE = False


def _set_json_mode(enabled):
    global _JSON_MODE
    _JSON_MODE = enabled


def _jout(data):
    """Print *data* as JSON and return True when JSON mode is active."""
    if _JSON_MODE:
        print(json.dumps(data, indent=2, ensure_ascii=False))
        return True
    return False


def _context(args):
    context = getattr(args, "crm_context", None)
    if context is None:
        context = CRMContext.from_file(getattr(args, "config", None))
        args.crm_context = context
    return context


def _write_json(args, path, data):
    _context(args).write_json(path, data)


def load_all(args):
    records = []
    for stage, path in _context(args).pipeline_files:
        if path.exists():
            data = json.loads(path.read_text(encoding=JSON_DB_ENCODING))
            for r in data:
                records.append((stage, r))
    return records


def load_item(args):
    if getattr(args, "item_file", None) and getattr(args, "item_json", None):
        print("Error: use only one of --item_file or --item_json")
        sys.exit(1)
    if getattr(args, "item_file", None):
        return json.loads(Path(args.item_file).read_text(encoding=JSON_DB_ENCODING))
    if getattr(args, "item_json", None):
        return json.loads(args.item_json)
    print("Error: provide one of --item_file or --item_json")
    sys.exit(1)


def _load_item_dict(args, command_name):
    """Load item from args and validate it is a JSON object."""
    item = load_item(args)
    if not isinstance(item, dict):
        print(f"Error: {command_name} item must be a JSON object")
        sys.exit(1)
    return item


def _identity_fields(args):
    return _context(args).identity_fields


def _other_pipeline_records(args, database_path):
    return _context(args).other_records(database_path)


def _exit_record_error(command, error):
    message = str(error)
    prefix = f"{command} " if message.startswith("requires") else ""
    print(f"Error: {prefix}{message}")
    sys.exit(1)


def _load_records(database_path):
    """Load records from database_path and validate it is a JSON array."""
    records = load_json(database_path)
    if records and not isinstance(records, list):
        print("Error: database file must be a JSON array")
        sys.exit(1)
    return records


def add_record(records, item, *, stage, fields, existing_records=None):
    require_identity(item, fields)
    ensure_valid_record(item, stage)
    ensure_unique(item, [*records, *(existing_records or [])], fields)
    added = copy.deepcopy(item)
    updated = sort_records([*records, added], stage, fields)
    return updated, added


def update_record(records, updates, *, stage, fields, existing_records=None):
    field, value = require_identity(updates, fields)
    matches = [index for index, record in enumerate(records) if identity_matches(record, field, value)]
    if not matches:
        from jsoncrm.invariants import RecordNotFoundError
        raise RecordNotFoundError(f"no record found for {field} '{value}'")
    if len(matches) > 1:
        from jsoncrm.invariants import RecordValidationError
        raise RecordValidationError(f"multiple records found for {field} '{value}'")

    index = matches[0]
    original = records[index]
    updated = copy.deepcopy(original)
    unknown = [key for key in updates if key not in updated and key != field]
    updated.update(copy.deepcopy(updates))
    require_identity(updated, fields)
    ensure_valid_record(updated, stage)
    remaining = [record for i, record in enumerate(records) if i != index]
    identity_changed = any(
        key in updates and original.get(key) != updated.get(key)
        for key in fields
    )
    if identity_changed:
        ensure_unique(updated, [*remaining, *(existing_records or [])], fields)
    if stage and stage.get("sort"):
        return sort_records([*remaining, updated], stage, fields), updated, unknown
    updated_records = list(records)
    updated_records[index] = updated
    return updated_records, updated, unknown


def delete_record(records, identity, *, fields):
    from jsoncrm.invariants import RecordNotFoundError, RecordValidationError

    field, value = require_identity(identity, fields)
    matches = [index for index, record in enumerate(records) if identity_matches(record, field, value)]
    if not matches:
        raise RecordNotFoundError(f"no record found for {field} '{value}'")
    if len(matches) > 1:
        raise RecordValidationError(f"multiple records found for {field} '{value}'")
    index = matches[0]
    return [record for i, record in enumerate(records) if i != index], records[index]


def _render_template(value, context):
    from jsoncrm.invariants import RecordValidationError

    if not isinstance(value, str):
        return copy.deepcopy(value)
    try:
        return value.format_map(context)
    except (KeyError, ValueError) as exc:
        raise RecordValidationError(f"invalid transition value template {value!r}: {exc}") from exc


def apply_transition_map(record, mapping, *, today=None):
    from jsoncrm.invariants import RecordValidationError

    mapped = copy.deepcopy(record)
    if not mapping:
        return mapped
    unknown = set(mapping) - {"drop", "rename", "set"}
    if unknown:
        raise RecordValidationError(f"unknown transition map operation(s): {', '.join(sorted(unknown))}")

    for field in mapping.get("drop", []):
        mapped.pop(field, None)
    for source, destination in mapping.get("rename", {}).items():
        if source not in mapped:
            raise RecordValidationError(f"cannot rename missing field '{source}'")
        mapped[destination] = mapped.pop(source)

    context = {**record, **mapped, "today": (today or date.today()).isoformat()}
    for field, value in mapping.get("set", {}).items():
        mapped[field] = _render_template(value, context)
    return mapped


def move_record(
    source_records,
    destination_records,
    *,
    identity_field,
    identity_value,
    source_stage,
    destination_stage,
    fields,
    transition_map=None,
    existing_records=None,
    today=None,
):
    from jsoncrm.invariants import RecordNotFoundError, RecordValidationError

    matches = [
        index for index, record in enumerate(source_records)
        if identity_matches(record, identity_field, identity_value)
    ]
    if not matches:
        raise RecordNotFoundError(f"no record found for {identity_field} '{identity_value}'")
    if len(matches) > 1:
        raise RecordValidationError(f"multiple records found for {identity_field} '{identity_value}'")

    index = matches[0]
    moved = apply_transition_map(source_records[index], transition_map, today=today)
    require_identity(moved, fields)
    ensure_valid_record(moved, destination_stage)
    ensure_unique(moved, [*destination_records, *(existing_records or [])], fields)
    remaining = [record for i, record in enumerate(source_records) if i != index]
    return (
        sort_records(remaining, source_stage, fields),
        sort_records([*destination_records, moved], destination_stage, fields),
        moved,
    )


def _within(value, days, today):
    from jsoncrm.invariants import RecordValidationError, _parse_iso_date

    parsed = _parse_iso_date(value)
    if parsed is None or isinstance(days, bool):
        return False
    try:
        days = int(days)
    except (TypeError, ValueError):
        return False
    if days < 0:
        raise RecordValidationError("within window must be a non-negative number of days")
    return today <= parsed <= date.fromordinal(today.toordinal() + days)


def record_matches(record, matcher, *, today=None):
    from jsoncrm.invariants import RecordValidationError

    operators = {
        "lt": lambda a, b: a < b,
        "lte": lambda a, b: a <= b,
        "gt": lambda a, b: a > b,
        "gte": lambda a, b: a >= b,
        "ne": lambda a, b: a != b,
    }
    for expression, expected in matcher.items():
        field, separator, operator = expression.rpartition("__")
        if not separator:
            field, operator = expression, "eq"
        if operator == "within":
            if not _within(record.get(field), expected, today or date.today()):
                return False
            continue
        if operator not in {"eq", *operators}:
            raise RecordValidationError(f"unknown query operator '{operator}'")
        actual = record.get(field)
        if operator == "eq":
            if actual != expected:
                return False
            continue
        if actual is None and operator != "ne":
            return False
        try:
            if not operators[operator](actual, expected):
                return False
        except TypeError:
            return False
    return True


def query_records(records, matcher, *, projection=None, today=None):
    results = [record for record in records if record_matches(record, matcher, today=today)]
    if projection is None:
        return results
    return [{field: record.get(field) for field in projection} for record in results]


def cmd_search(args):
    comp_hits = []
    if args.competitor:
        comp_hits = search_competitors(args.query, person=args.person, company=args.company, context=_context(args))

    records = load_all(args)
    hits = [(stage, r) for stage, r in records
            if match(r, args.query, person=args.person, company=args.company)]

    if _jout({
        "query": args.query,
        "competitor_matches": [{"kind": k, **e} for k, e in comp_hits],
        "results": [{"stage": s, **r} for s, r in hits],
    }):
        return

    if comp_hits:
        print(f"⚠️  COMPETITOR MATCH for '{args.query}':\n")
        for kind, entry in comp_hits:
            name = entry.get("name", "—")
            role = entry.get("role", "")
            url = entry.get("url", "")
            if kind == "company":
                print(f"  [COMPETITOR]  {name}  —  {role}")
            else:
                print(f"  [COMPETITOR]  {name}  ({entry.get('company', '')})")
            if url:
                print(f"           {url}")
            print()

    if not hits:
        print(f"No results for '{args.query}'")
        sys.exit(0)

    print(f"{len(hits)} result(s) for '{args.query}':\n")
    for stage, r in hits:
        print_record(stage, r)


def cmd_find(args):
    database_path = Path(args.database_file)
    if not database_path.exists():
        print(f"Error: {database_path} not found")
        sys.exit(1)

    matcher = _load_item_dict(args, "find")
    records = _load_records(database_path)
    projection = getattr(args, "fields", None)
    if projection:
        projection = [field.strip() for item in projection for field in item.split(",") if field.strip()]
    try:
        results = query_records(records, matcher, projection=projection)
    except RecordError as exc:
        _exit_record_error("find", exc)
    output = json.dumps(results, indent=2, ensure_ascii=False)
    if args.output_file:
        Path(args.output_file).write_text(output + "\n", encoding=JSON_DB_ENCODING)
    else:
        print(output)


def _output_record_result(args, record, dry_run):
    result = {"dry_run": True, "record": record} if dry_run else record
    output = json.dumps(result, indent=2, ensure_ascii=False)
    if args.output_file and not dry_run:
        Path(args.output_file).write_text(output + "\n", encoding=JSON_DB_ENCODING)
    else:
        print(output)


def _valid_scores(args):
    """Return (set of valid score values, human-readable description) from config."""
    cfg = _context(args).config
    valid = set(cfg.score_order) | {cfg.disqualified_score}
    description = ", ".join(repr(s) for s in cfg.score_order_descending + [cfg.disqualified_score])
    return valid, description


def cmd_add(args):
    database_path = Path(args.database_file)
    item = _load_item_dict(args, "add")

    valid_scores, valid_description = _valid_scores(args)
    score = item.get("score")
    if score is not None and score not in valid_scores:
        print(f"Error: invalid score {score!r} — must be one of {valid_description}, or null")
        sys.exit(1)

    records = _load_records(database_path)
    try:
        records, added = add_record(
            records,
            item,
            stage=_context(args).stage_for_path(database_path),
            fields=_identity_fields(args),
            existing_records=_other_pipeline_records(args, database_path),
        )
    except RecordError as exc:
        _exit_record_error("add", exc)

    dry_run = getattr(args, "dry_run", False)
    if not dry_run:
        _write_json(args, database_path, records)
    _output_record_result(args, added, dry_run)


def cmd_delete(args):
    database_path = Path(args.database_file)
    if not database_path.exists():
        print(f"Error: {database_path} not found")
        sys.exit(1)

    item = _load_item_dict(args, "delete")
    records = _load_records(database_path)
    try:
        kept, deleted = delete_record(records, item, fields=_identity_fields(args))
    except RecordError as exc:
        _exit_record_error("delete", exc)

    dry_run = getattr(args, "dry_run", False)
    if not dry_run:
        _write_json(args, database_path, kept)
    _output_record_result(args, deleted, dry_run)


def cmd_update(args):
    database_path = Path(args.database_file)
    if not database_path.exists():
        print(f"Error: {database_path} not found")
        sys.exit(1)

    item = _load_item_dict(args, "update")
    records = _load_records(database_path)
    try:
        records, updated, unknown = update_record(
            records,
            item,
            stage=_context(args).stage_for_path(database_path),
            fields=_identity_fields(args),
            existing_records=_other_pipeline_records(args, database_path),
        )
    except RecordError as exc:
        _exit_record_error("update", exc)

    if unknown:
        print(f"Warning: updating unknown field(s): {', '.join(unknown)}")
    dry_run = getattr(args, "dry_run", False)
    if not dry_run:
        _write_json(args, database_path, records)
    _output_record_result(args, updated, dry_run)


def cmd_apply_update(args):
    pending_path = Path(args.pending_file) if args.pending_file != "default" else _context(args).pending_file
    if not pending_path.exists():
        print(f"Error: no pending update file at {pending_path}")
        sys.exit(1)
    payload = json.loads(pending_path.read_text(encoding=JSON_DB_ENCODING))
    target_url = payload.get("linkedin_url")
    if not target_url:
        print("Error: pending file missing 'linkedin_url'")
        sys.exit(1)
    updates = {k: coerce(v) for k, v in payload.get("fields", {}).items()}
    if not updates:
        print("Error: pending file has no 'fields'")
        sys.exit(1)
    target_file = payload.get("target_file")
    apply_updates(target_url, updates, target_file=target_file, context=_context(args))
    pending_path.unlink()


def cmd_shuffle(args):
    path = Path(args.file)
    if not path.exists():
        print(f"Error: {path} not found")
        sys.exit(1)
    stage = _context(args).stage_for_path(path)
    if stage and stage.get("sort"):
        print(f"Error: cannot shuffle sorted stage '{stage['name']}'")
        sys.exit(1)

    data = load_json(path)
    if not isinstance(data, list):
        print("Error: file must be a JSON array")
        sys.exit(1)

    rng = random.Random(args.seed) if args.seed is not None else random
    rng.shuffle(data)

    if args.dry_run:
        print(json.dumps(data, indent=2, ensure_ascii=False))
        print("\n(dry run — no files modified)")
        return

    _write_json(args, path, data)
    print(f"Shuffled {len(data)} records in {path.name}.")


def cmd_intake(args):
    path = Path(args.file)
    if not path.exists():
        print(f"Error: {path} not found")
        sys.exit(1)

    data = json.loads(path.read_text(encoding=JSON_DB_ENCODING))
    if not isinstance(data, list):
        print("Error: file must be a JSON array")
        sys.exit(1)

    unscored = [r for r in data if not r.get("score")]
    if not unscored:
        print("All records scored.")
        sys.exit(1)

    r = unscored[0]
    output_path = Path(args.output) if args.output else _context(args).pending_file
    pending = {
        "linkedin_url": r.get("linkedin_url"),
        "target_file": str(path),
        "fields": {},
    }
    _write_json(args, output_path, pending)

    if _jout({"record": r, "remaining": len(unscored), "pending_file": str(output_path)}):
        return

    print(f"Name:      {r.get('name')}")
    print(f"URL:       {r.get('linkedin_url')}")
    print(f"Username:  {r.get('linkedin_username')}")
    if r.get("position"):
        print(f"Position:  {r.get('position')}")
    if r.get("company"):
        print(f"Company:   {r.get('company')}")
    print(f"Remaining: {len(unscored)} unscored")
    print(f"\nWrote {output_path} — fill in fields, then run: jsoncrm apply_update {output_path}")


def cmd_top(args):
    path = Path(args.file) if args.file else _context(args).leads_file
    if not path.exists():
        print(f"Error: {path} not found")
        sys.exit(1)

    records = json.loads(path.read_text(encoding=JSON_DB_ENCODING))
    today = date.today().isoformat()
    results = []
    for r in records:
        score = r.get("score")
        if score is None:
            continue
        if score == "❌" and not args.include_disqualified:
            continue
        if not args.include_contacted:
            next_up = r.get("next_follow_up")
            contacted = bool(r.get("contacted_at"))
            # A lead is due now when it has never been contacted (fresh, no
            # next_follow_up scheduled) OR its scheduled follow-up is today/past.
            # It is deferred only by a future next_follow_up (cooldown), or by a
            # null next_follow_up once it has been contacted ("don't contact").
            if next_up is None:
                if contacted:
                    continue
            elif next_up > today:
                continue
        if args.min_score and _context(args).score_value(score) < _context(args).score_value(args.min_score):
            continue
        results.append(r)

    results.sort(key=lambda r: _context(args).score_value(r.get("score")), reverse=True)
    results = results[:args.num]

    if not results:
        print("No leads match the filters.")
        sys.exit(1)

    if _jout(results):
        if args.output:
            if len(results) != 1:
                print("Error: --output requires exactly one result. Use -n 1 or tighten filters.",
                      file=sys.stderr)
                sys.exit(1)
            output_path = Path(args.output)
            r = results[0]
            pending = {
                "linkedin_url": r.get("linkedin_url"),
                "target_file": str(path),
                "fields": {},
            }
            _write_json(args, output_path, pending)
        return

    print(json.dumps(results, indent=2, ensure_ascii=False))
    print(f"\n({len(results)} lead(s) shown)", file=sys.stderr)

    if args.output:
        if len(results) != 1:
            print("Error: --output requires exactly one result. Use -n 1 or tighten filters.",
                  file=sys.stderr)
            sys.exit(1)
        output_path = Path(args.output)
        r = results[0]
        pending = {
            "linkedin_url": r.get("linkedin_url"),
            "target_file": str(path),
            "fields": {},
        }
        _write_json(args, output_path, pending)
        print(
            f"Wrote {output_path} — fill in fields, then run: jsoncrm apply_update {output_path}",
            file=sys.stderr,
        )


def cmd_merge(args):
    source_path = Path(args.file)
    leads_path = Path(args.leads_file) if args.leads_file else _context(args).leads_file

    if not source_path.exists():
        print(f"Error: {source_path} not found")
        sys.exit(1)

    source_records = load_json(source_path)
    if not isinstance(source_records, list):
        print("Error: source file must be a JSON array")
        sys.exit(1)

    valid_scores, valid_description = _valid_scores(args)
    scored = [r for r in source_records if r.get("score")]
    unscored = [r for r in source_records if not r.get("score")]
    invalid = [r for r in scored if r.get("score") not in valid_scores]
    scored = [r for r in scored if r.get("score") in valid_scores]

    if args.leads_file:
        known_urls = build_known_urls(leads_file=leads_path, context=_context(args))
    else:
        known_urls = build_known_urls(context=_context(args))

    existing_leads = load_json(leads_path)

    added, skipped = [], []
    for record in scored:
        url = normalize_url(record.get("linkedin_url"))
        if url and url in known_urls:
            skipped.append(record)
        else:
            added.append(record)
            if url:
                known_urls.add(url)

    # Invalid-score records are never merged or dropped — they stay in the
    # source file alongside unscored ones so a human (or the next run) can
    # fix the score and retry.
    remaining = unscored + invalid

    if _jout({
        "source_total": len(source_records),
        "scored": len(scored),
        "unscored": len(unscored),
        "invalid": invalid,
        "added": added,
        "skipped": skipped,
        "dry_run": args.dry_run,
    }):
        if not args.dry_run:
            if added:
                merged = existing_leads + added
                _write_json(args, leads_path, merged)
            if remaining != source_records:
                _write_json(args, source_path, remaining)
        if invalid:
            sys.exit(1)
        return

    print(f"Source:   {len(source_records)} records")
    print(f"Scored:   {len(scored)}  |  Unscored: {len(unscored)} (left in source file)")
    if invalid:
        print(f"Invalid:  {len(invalid)} (score not in {valid_description}; left in source file)")
    print(f"Add:      {len(added)}")
    print(f"Skip:     {len(skipped)} (already in pipeline)")

    if skipped:
        print("\nSkipped:")
        for r in skipped:
            print(f"  {r.get('name')}  —  {r.get('company')}  ({r.get('linkedin_url')})")

    if added:
        print("\nTo add:")
        for r in added:
            print(f"  {r.get('name')}  —  {r.get('company')}  ({r.get('linkedin_url')})")

    if invalid:
        print("\nInvalid score (not merged, left in source file):")
        for r in invalid:
            print(f"  {r.get('name')}  —  {r.get('linkedin_url')}  (score: {r.get('score')!r})")

    if args.dry_run:
        print("\n(dry run — no files modified)")
        if invalid:
            sys.exit(1)
        return

    if not added and not scored:
        print("\nNothing to do.")
        if remaining != source_records:
            _write_json(args, source_path, remaining)
        if invalid:
            sys.exit(1)
        return

    if added:
        merged = existing_leads + added
        _write_json(args, leads_path, merged)
        print(f"\nWrote {len(merged)} records to {leads_path}")

    if remaining != source_records:
        _write_json(args, source_path, remaining)
        print(f"Updated {source_path.name}: {len(remaining)} unscored/invalid record(s) remaining")
    else:
        print(f"No changes to {source_path.name}")

    if invalid:
        sys.exit(1)


def cmd_deduplicate(args):
    source_path = Path(args.file)
    if not source_path.exists():
        print(f"Error: {source_path} not found")
        sys.exit(1)

    source_records = load_json(source_path)
    if not isinstance(source_records, list):
        print("Error: source file must be a JSON array")
        sys.exit(1)

    known_urls = build_known_urls(
        leads_file=args.leads_file,
        prospects_file=args.prospects_file,
        customers_file=args.customers_file,
        context=_context(args),
    )

    kept = []
    removed = []
    for record in source_records:
        url = normalize_url(record.get("linkedin_url"))
        if url and url in known_urls:
            removed.append(record)
        else:
            kept.append(record)

    if _jout({
        "source_total": len(source_records),
        "kept": kept,
        "removed": removed,
        "dry_run": args.dry_run,
    }):
        if not args.dry_run and kept != source_records:
            _write_json(args, source_path, kept)
        return

    print(f"Source:   {len(source_records)} records")
    print(f"Keep:     {len(kept)}")
    print(f"Drop:     {len(removed)} (already in pipeline)")

    if removed:
        print("\nDropped:")
        for record in removed:
            print(f"  {record.get('name')}  —  {record.get('company')}  ({record.get('linkedin_url')})")

    if args.dry_run:
        print("\n(dry run — no files modified)")
        return

    if kept != source_records:
        _write_json(args, source_path, kept)
        print(f"Updated {source_path.name}: {len(kept)} records remaining")
    else:
        print(f"No changes to {source_path.name}")


def cmd_filter_competitors(args):
    source_path = Path(args.file)
    if not source_path.exists():
        print(f"Error: {source_path} not found")
        sys.exit(1)

    source_records = load_json(source_path)
    if not isinstance(source_records, list):
        print("Error: source file must be a JSON array")
        sys.exit(1)
    if not _context(args).competitors_file.exists():
        print(f"Error: {_context(args).competitors_file} not found")
        sys.exit(1)

    competitors = load_json(_context(args).competitors_file)
    if not isinstance(competitors, dict):
        print("Error: competitors file must be a JSON object")
        sys.exit(1)

    competitor_people = {
        normalize_url(entry.get("url"))
        for entry in iter_competitor_entries(competitors, COMPETITOR_PERSON_KEYS)
        if normalize_url(entry.get("url"))
    }
    competitor_companies = {
        normalize_company_name(entry.get("name"))
        for entry in iter_competitor_entries(competitors, COMPETITOR_COMPANY_KEYS)
        if normalize_company_name(entry.get("name"))
    }

    kept = []
    removed = []
    for record in source_records:
        url = normalize_url(record.get("linkedin_url"))
        company = normalize_company_name(record.get("company"))
        if (url and url in competitor_people) or (company and company in competitor_companies):
            removed.append(record)
        else:
            kept.append(record)

    if _jout({
        "source_total": len(source_records),
        "kept": kept,
        "removed": removed,
        "dry_run": args.dry_run,
    }):
        if not args.dry_run and kept != source_records:
            _write_json(args, source_path, kept)
        return

    print(f"Source:   {len(source_records)} records")
    print(f"Keep:     {len(kept)}")
    print(f"Drop:     {len(removed)} (competitor match)")

    if removed:
        print("\nDropped:")
        for record in removed:
            print(f"  {record.get('name')}  —  {record.get('company')}  ({record.get('linkedin_url')})")

    if args.dry_run:
        print("\n(dry run — no files modified)")
        return

    if kept != source_records:
        _write_json(args, source_path, kept)
        print(f"Updated {source_path.name}: {len(kept)} records remaining")
    else:
        print(f"No changes to {source_path.name}")


def _move_between(args, src_path, dst_path, action, *, enforce_transition=False):
    if not src_path.exists():
        print(f"Error: {src_path} not found")
        sys.exit(1)

    cfg = _context(args).config
    fields = _context(args).identity_fields
    source_stage = _context(args).stage_for_path(src_path)
    destination_stage = _context(args).stage_for_path(dst_path)
    source_name = source_stage["name"] if source_stage else None
    destination_name = destination_stage["name"] if destination_stage else None
    if enforce_transition:
        destinations = cfg.pipeline_transitions.get(source_name, [])
        if destination_name not in destinations:
            print(f"Error: transition '{source_name}->{destination_name}' is not configured")
            sys.exit(1)

    excluded = {src_path.resolve(), dst_path.resolve()}
    existing_records = []
    for _stage, path in _context(args).pipeline_files:
        if path.resolve() not in excluded and path.exists():
            data = load_json(path)
            if isinstance(data, list):
                existing_records.extend(data)

    identity_value = getattr(args, "identity_value", None) or getattr(args, "linkedin_url", None)
    identity_field = getattr(args, "identity_field", None) or cfg.identity_primary
    try:
        remaining, destination, record = move_record(
            _load_records(src_path),
            _load_records(dst_path),
            identity_field=identity_field,
            identity_value=identity_value,
            source_stage=source_stage,
            destination_stage=destination_stage,
            fields=fields,
            transition_map=cfg.transition_map(source_name, destination_name),
            existing_records=existing_records,
        )
    except RecordError as exc:
        _exit_record_error(action, exc)

    dry_run = getattr(args, "dry_run", False)
    if not dry_run:
        _write_json(args, dst_path, destination)
        _write_json(args, src_path, remaining)

    name = record.get("name", identity_value)
    completed_action = "moved" if action == "move" else f"{action}d"
    if dry_run:
        if _jout({
            "action": action, "dry_run": True, "record": record,
            "from": src_path.name, "to": dst_path.name,
        }):
            return
        print(f"Dry run: would {action} {name}  {src_path.name} → {dst_path.name}")
        return
    if _jout({"action": completed_action, "record": record, "from": src_path.name, "to": dst_path.name}):
        return
    print(f"{completed_action.capitalize()}: {name}  {src_path.name} → {dst_path.name}")


def cmd_move(args):
    context = _context(args)
    if not context.stage_for_name(args.from_stage) or not context.stage_for_name(args.to_stage):
        print("Error: both --from and --to must name configured stages")
        sys.exit(1)
    _move_between(
        args,
        context.stage_path(args.from_stage),
        context.stage_path(args.to_stage),
        "move",
        enforce_transition=True,
    )


def cmd_promote(args):
    context = _context(args)
    stage = "lead" if args.lead else "prospect"
    src_name, dst_name = context.promote_map()[stage]
    src_path = Path(args.from_file) if args.from_file else context.root / src_name
    dst_path = Path(args.to_file) if args.to_file else context.root / dst_name
    _move_between(args, src_path, dst_path, "promote")


def cmd_stats(args):
    # Use explicit overrides if provided, otherwise fall back to config-driven pipeline
    if args.leads_file or args.prospects_file or args.customers_file:
        pipeline = [
            ("leads", Path(args.leads_file) if args.leads_file else _context(args).leads_file),
            ("prospects", Path(args.prospects_file) if args.prospects_file else _context(args).prospects_file),
            ("customers", Path(args.customers_file) if args.customers_file else _context(args).customers_file),
        ]
    else:
        pipeline = [(name, path) for name, path in _context(args).pipeline_files]

    report = {}
    for stage, path in pipeline:
        records = load_json(path)
        total = len(records)
        report[stage] = {"total": total}

        if stage == "leads" and total > 0:
            scored = [r for r in records if r.get("score") is not None]
            unscored = [r for r in records if r.get("score") is None]
            contacted = [r for r in records if r.get("contacted_at")]
            disqualified = [r for r in records if r.get("score") == "❌"]

            by_score = {}
            for r in scored:
                s = r.get("score")
                if s != "❌":
                    by_score[s] = by_score.get(s, 0) + 1

            report[stage]["scored"] = len(scored)
            report[stage]["unscored"] = len(unscored)
            report[stage]["contacted"] = len(contacted)
            report[stage]["disqualified"] = len(disqualified)
            report[stage]["by_score"] = by_score
        elif stage == "prospects" and total > 0:
            closed = [r for r in records if r.get("status") == "closed"]
            active = total - len(closed)
            contacted = [r for r in records if r.get("contacted_at")]
            report[stage]["active"] = active
            report[stage]["closed"] = len(closed)
            report[stage]["contacted"] = len(contacted)
        elif stage == "customers" and total > 0:
            companies = len(set(r.get("company") for r in records if r.get("company")))
            paid = sum(1 for r in records if r.get("paid"))
            unpaid = total - paid
            paid_companies = len(set(r.get("company") for r in records if r.get("paid") and r.get("company")))
            unpaid_companies = len(set(r.get("company") for r in records if not r.get("paid") and r.get("company")))
            report[stage]["companies"] = companies
            report[stage]["paid"] = paid
            report[stage]["unpaid"] = unpaid
            report[stage]["paid_companies"] = paid_companies
            report[stage]["unpaid_companies"] = unpaid_companies

    if _jout(report):
        return

    for stage, path in pipeline:
        total = report[stage]["total"]
        if stage == "leads" and total > 0:
            print(f"Leads: {total}")
            print(f"  Scored:       {report[stage]['scored']}")
            print(f"  Unscored:     {report[stage]['unscored']}")
            print(f"  Contacted:    {report[stage]['contacted']}")
            print(f"  Disqualified: {report[stage]['disqualified']}")
            for stars in ["⭐⭐⭐⭐⭐", "⭐⭐⭐⭐", "⭐⭐⭐", "⭐⭐", "⭐"]:
                count = report[stage]["by_score"].get(stars, 0)
                if count:
                    print(f"  {stars}  {count}")
        elif stage == "prospects" and total > 0:
            print(f"Prospects: {total} ({report[stage]['active']} active, {report[stage]['closed']} closed, {report[stage]['contacted']} contacted)")
        elif stage == "customers" and total > 0:
            print(f"Customers: {total} contacts ({report[stage]['companies']} companies)")
            print(f"  Paid:     {report[stage]['paid']} contacts ({report[stage]['paid_companies']} companies)")
            print(f"  Unpaid:   {report[stage]['unpaid']} contacts ({report[stage]['unpaid_companies']} companies)")
        else:
            print(f"{stage.capitalize()}: {total}")


def cmd_validate(args):
    """Validate structure, configured identities, fields, and sorted order."""
    cfg = _context(args).config

    if args.leads_file or args.prospects_file or args.customers_file:
        pipeline = [
            ("leads", Path(args.leads_file) if args.leads_file else _context(args).leads_file),
            ("prospects", Path(args.prospects_file) if args.prospects_file else _context(args).prospects_file),
            ("customers", Path(args.customers_file) if args.customers_file else _context(args).customers_file),
        ]
    else:
        pipeline = [(name, path) for name, path in _context(args).pipeline_files]
    errors = []
    warnings_list = []
    summary = {}
    fields = _context(args).identity_fields
    valid_scores = set(cfg.score_order) | {cfg.disqualified_score}
    seen_identities = {}

    def add_error(stage, path, message, index=None):
        nonlocal errors
        entry = {"stage": stage, "file": str(path), "error": message}
        if index is not None:
            entry["record"] = index
        errors.append(entry)
        return f"record {index} {message}" if index is not None else message

    for stage, path in pipeline:
        stage_errors = []
        stage_warnings = []
        stage_config = _context(args).stage_for_path(path) or _context(args).stage_for_name(stage)

        if not path.exists():
            stage_errors.append(add_error(stage, path, "file not found"))
            summary[stage] = {"valid": False, "records": 0, "errors": 1, "warnings": 0}
            continue

        try:
            data = json.loads(path.read_text(encoding=JSON_DB_ENCODING))
        except json.JSONDecodeError as e:
            stage_errors.append(add_error(stage, path, f"invalid JSON: {e}"))
            summary[stage] = {"valid": False, "records": 0, "errors": 1, "warnings": 0}
            continue

        if not isinstance(data, list):
            stage_errors.append(add_error(stage, path, "file must be a JSON array"))
            summary[stage] = {"valid": False, "records": 0, "errors": 1, "warnings": 0}
            continue

        for idx, record in enumerate(data):
            if not isinstance(record, dict):
                stage_errors.append(add_error(stage, path, "not an object", idx))
                continue

            present = [(field, record.get(field)) for field in fields if record.get(field) not in (None, "")]
            if not present:
                stage_errors.append(add_error(stage, path, f"missing identity ({' or '.join(fields)})", idx))
            for field, value in present:
                normalized = normalize_url(value) if field.endswith("_url") else str(value)
                key = (field, normalized)
                if key in seen_identities:
                    first_stage, first_index = seen_identities[key]
                    message = f"duplicate {field} '{value}' (first at {first_stage} record {first_index})"
                    stage_errors.append(add_error(stage, path, message, idx))
                else:
                    seen_identities[key] = (stage, idx)

            for message in record_errors(record, stage_config):
                stage_errors.append(add_error(stage, path, message, idx))

            score = record.get("score")
            if score is not None and score not in valid_scores:
                message = f"unknown score '{score}'"
                stage_warnings.append(f"record {idx} has {message}")
                warnings_list.append({"stage": stage, "file": str(path), "record": idx, "warning": message})

        if stage_config and stage_config.get("sort") and all(isinstance(record, dict) for record in data):
            try:
                if sort_records(data, stage_config, fields) != data:
                    sort = stage_config["sort"]
                    stage_errors.append(add_error(stage, path, f"records are not sorted by '{sort['key']}'"))
            except RecordError as exc:
                stage_errors.append(add_error(stage, path, str(exc)))

        summary[stage] = {
            "valid": len(stage_errors) == 0,
            "records": len(data),
            "errors": len(stage_errors),
            "warnings": len(stage_warnings),
        }

    total_errors = len(errors)
    total_warnings = len(warnings_list)

    if _jout({
        "valid": total_errors == 0,
        "total_errors": total_errors,
        "total_warnings": total_warnings,
        "summary": summary,
        "errors": errors,
        "warnings": warnings_list,
    }):
        if total_errors:
            sys.exit(1)
        return

    if total_errors == 0 and total_warnings == 0:
        print("✅ All pipeline files are valid.")
        return

    for stage, info in summary.items():
        status = "✅" if info["valid"] else "❌"
        print(f"{status} {stage}: {info['records']} records, {info['errors']} errors, {info['warnings']} warnings")

    if errors:
        print("\nErrors:")
        for e in errors:
            loc = f"{e['stage']} record {e.get('record', 'N/A')}"
            print(f"  [{loc}] {e['error']}")

    if warnings_list:
        print("\nWarnings:")
        for w in warnings_list:
            loc = f"{w['stage']} record {w.get('record', 'N/A')}"
            print(f"  [{loc}] {w['warning']}")

    if total_errors:
        sys.exit(1)


def cmd_recent(args):
    """Show the most recently added records across the pipeline."""
    if args.leads_file or args.prospects_file or args.customers_file:
        pipeline = [
            ("leads", Path(args.leads_file) if args.leads_file else _context(args).leads_file),
            ("prospects", Path(args.prospects_file) if args.prospects_file else _context(args).prospects_file),
            ("customers", Path(args.customers_file) if args.customers_file else _context(args).customers_file),
        ]
    else:
        pipeline = [(name, path) for name, path in _context(args).pipeline_files]

    all_records = []
    for stage, path in pipeline:
        if not path.exists():
            continue
        stage_config = _context(args).stage_for_path(path) or _context(args).stage_for_name(stage) or {}
        recent_key = _context(args).config.stage_recent_key(stage_config)
        for r in load_json(path):
            if isinstance(r, dict):
                entry = {"stage": stage, "file": str(path), **r}
                all_records.append((r.get(recent_key) or "", entry))

    if args.stage:
        all_records = [item for item in all_records if item[1]["stage"] == args.stage]

    all_records.sort(key=lambda item: item[0], reverse=True)
    results = all_records[:args.num]

    if _jout([record for _recent_date, record in results]):
        return

    if not results:
        print("No records found.")
        return

    for recent_date, r in results:
        print(f"[{r['stage'].upper()}] {recent_date or '—'}  {r.get('name')}  —  {r.get('company')}  ({r.get('linkedin_url')})")


def cmd_demote(args):
    """Move a record back one pipeline stage (reverse of promote)."""
    context = _context(args)
    promote_map = context.promote_map()
    stage = "customer" if args.customer else "prospect"
    if stage == "customer":
        src_name, dst_name = promote_map["prospect"][1], promote_map["prospect"][0]
    else:
        src_name, dst_name = promote_map["lead"][1], promote_map["lead"][0]
    src_path = Path(args.from_file) if args.from_file else context.root / src_name
    dst_path = Path(args.to_file) if args.to_file else context.root / dst_name
    _move_between(args, src_path, dst_path, "demote")


def cmd_list(args):
    """List records in a pipeline stage."""
    stage = args.stage
    path = None
    if args.file:
        path = Path(args.file)
    else:
        for name, p in _context(args).pipeline_files:
            if name == stage:
                path = p
                break

    if path is None:
        print(f"Error: unknown stage '{stage}'")
        sys.exit(1)

    if not path.exists():
        print(f"Error: {path} not found")
        sys.exit(1)

    records = load_json(path)
    if not isinstance(records, list):
        print("Error: file must be a JSON array")
        sys.exit(1)

    if args.score:
        records = [r for r in records if r.get("score") == args.score]
    if args.company:
        records = [r for r in records if args.company.lower() in (r.get("company") or "").lower()]
    if args.query:
        records = [r for r in records if match(r, args.query)]

    total = len(records)
    if args.limit:
        records = records[:args.limit]

    if _jout(records):
        return

    if not records:
        print(f"No records in '{stage}'.")
        return

    print(f"{len(records)} of {total} record(s) in '{stage}':\n")
    for r in records:
        score = r.get("score") or "—"
        print(f"  {r.get('name')}  —  {r.get('company')}  [{score}]")
        if r.get("linkedin_url"):
            print(f"           {r['linkedin_url']}")


def cmd_dump_emails(args):
    """Dump all email addresses in the pipeline, comma separated."""
    seen = set()
    emails = []
    for _stage, r in load_all(args):
        email = (r.get("email") or "").strip()
        if email and email not in seen:
            seen.add(email)
            emails.append(email)

    if args.out:
        Path(args.out).write_text(", ".join(emails) + "\n", encoding=JSON_DB_ENCODING)

    if _jout({"count": len(emails), "emails": emails}):
        return

    if args.out:
        print(f"Wrote {len(emails)} email(s) to {args.out}")
    elif emails:
        print(", ".join(emails))
    else:
        print("No emails found in pipeline.")


def cmd_backup(args):
    from jsoncrm.backup import create_backup

    context = _context(args)
    config_path = context.config_path
    source_files = [*(path for _, path in context.pipeline_files), context.competitors_file]
    if config_path.exists():
        source_files.insert(0, config_path)
    if context.pending_file.exists():
        source_files.append(context.pending_file)
    try:
        result = create_backup(context.root, source_files, output=args.output)
    except (OSError, ValueError) as exc:
        print(f"Error: {exc}")
        sys.exit(1)

    if _jout(result):
        return
    print(f"Created backup: {result['backup']}")
    print(f"Archived {len(result['files'])} file(s).")
    if result["missing"]:
        print(f"Missing: {', '.join(result['missing'])}")


def build_parser():
    parser = argparse.ArgumentParser(description="Unified CRM tool.")
    parser.add_argument("--config", default=None, help="Path to .crm.json config file")
    subparsers = parser.add_subparsers(dest="command")

    # Shared parent parser so --json can appear after subcommands
    parent = argparse.ArgumentParser(add_help=False)
    parent.add_argument("--json", action="store_true",
                        help="Output machine-readable JSON instead of human-readable text")

    # search
    p_search = subparsers.add_parser("search", parents=[parent], help="Search CRM pipeline for a lead.")
    p_search.add_argument("query", help="Name, company, LinkedIn URL, or email fragment to search for")
    mode = p_search.add_mutually_exclusive_group()
    mode.add_argument("--person", action="store_true", help="Search person fields only (name, LinkedIn URL, email)")
    mode.add_argument("--company", action="store_true", help="Search company field only")
    p_search.add_argument("--competitor", action="store_true",
                          help="Also search the competitor watchlist")

    # find
    p_find = subparsers.add_parser("find", parents=[parent], help="Find records in a specific CRM JSON file.")
    p_find.add_argument("--database_file", required=True, help="JSON file to search")
    p_find.add_argument("--item_file", default=None, help="Path to JSON object containing match fields")
    p_find.add_argument("--item_json", default=None, help="JSON object containing match fields or field__operator expressions")
    p_find.add_argument("--fields", nargs="+", default=None, help="Project only these fields (space or comma separated)")
    p_find.add_argument("--output_file", default=None, help="Optional file for matched results")

    # add
    p_add = subparsers.add_parser("add", parents=[parent], help="Add one record to a specific CRM JSON file.")
    p_add.add_argument("--database_file", required=True, help="JSON file to update")
    p_add.add_argument("--item_file", default=None, help="Path to JSON object to add")
    p_add.add_argument("--item_json", default=None, help="JSON object to add")
    p_add.add_argument("--output_file", default=None, help="Optional file for written record")
    write_mode = p_add.add_mutually_exclusive_group()
    write_mode.add_argument("--dry-run", action="store_true", help="Preview without writing files")
    write_mode.add_argument("--apply", action="store_true", help="Apply the change (default behavior)")

    # update
    p_update = subparsers.add_parser("update", parents=[parent], help="Update one record in a specific CRM JSON file.")
    p_update.add_argument("--database_file", required=True, help="JSON file to update")
    p_update.add_argument("--item_file", default=None, help="Path to JSON object containing identity and fields")
    p_update.add_argument("--item_json", default=None, help="JSON object containing identity and fields")
    p_update.add_argument("--output_file", default=None, help="Optional file for updated record")
    write_mode = p_update.add_mutually_exclusive_group()
    write_mode.add_argument("--dry-run", action="store_true", help="Preview without writing files")
    write_mode.add_argument("--apply", action="store_true", help="Apply the change (default behavior)")

    # delete
    p_delete = subparsers.add_parser("delete", parents=[parent], help="Delete one record from a specific CRM JSON file.")
    p_delete.add_argument("--database_file", required=True, help="JSON file to update")
    p_delete.add_argument("--item_file", default=None, help="Path to JSON object containing id or linkedin_url")
    p_delete.add_argument("--item_json", default=None, help="JSON object containing id or linkedin_url")
    p_delete.add_argument("--output_file", default=None, help="Optional file for deleted record")
    write_mode = p_delete.add_mutually_exclusive_group()
    write_mode.add_argument("--dry-run", action="store_true", help="Preview without writing files")
    write_mode.add_argument("--apply", action="store_true", help="Apply the change (default behavior)")

    # apply_update
    p_apply_update = subparsers.add_parser("apply_update", parents=[parent], help="Apply updates from a pending file.")
    p_apply_update.add_argument("pending_file", nargs="?", const="default", default="default",
                                help="Pending update file (default: crm/.pending_update.json)")

    # intake
    p_intake = subparsers.add_parser("intake", parents=[parent], help="Pick next unscored record from an intake file.")
    p_intake.add_argument("file", help="Path to intake JSON file")
    p_intake.add_argument("--output", default=None,
                          help="Optional pending file to write")

    # parse-from-linkedin-mcp
    p_intake_mcp = subparsers.add_parser("parse-from-linkedin-mcp", parents=[parent], help="Convert MCP get_post_likers output to CRM flat list in-place.")
    p_intake_mcp.add_argument("files", nargs='+', help="Path to one or more MCP JSON files")

    # shuffle
    p_shuffle = subparsers.add_parser("shuffle", parents=[parent], help="Shuffle records in a JSON array file in-place.")
    p_shuffle.add_argument("file", help="Path to JSON array file")
    p_shuffle.add_argument("--seed", type=int, default=None,
                           help="Optional random seed for reproducible shuffles")
    p_shuffle.add_argument("--dry-run", action="store_true",
                           help="Print shuffled output without writing")

    # top
    p_top = subparsers.add_parser("top", parents=[parent], help="Return top scored leads from leads.json.")
    p_top.add_argument("-n", "--num", type=int, default=1,
                       help="Number of leads to return (default: 1)")
    p_top.add_argument("--min", dest="min_score", default=None,
                       metavar="STARS", help="Minimum score, e.g. ⭐⭐⭐")
    p_top.add_argument("--include-contacted", action="store_true",
                       help="Include leads regardless of next_follow_up (bypass re-engagement filter)")
    p_top.add_argument("--include-disqualified", action="store_true",
                       help="Include disqualified (❌) leads")
    p_top.add_argument("--output", default=None,
                       help="Optional pending file to write. Requires exactly one result.")
    p_top.add_argument("--file", default=None,
                       help="Override leads file (default: crm/leads.json)")

    # merge
    p_merge = subparsers.add_parser("merge", parents=[parent],
                                    help="Merge scored records from a source file into leads.json.")
    p_merge.add_argument("file", help="Path to source JSON file")
    p_merge.add_argument("--dry-run", action="store_true",
                         help="Print what would happen without writing")
    p_merge.add_argument("--leads-file", default=None,
                         help="Override leads file (default: crm/leads.json)")

    # deduplicate
    p_deduplicate = subparsers.add_parser(
        "deduplicate",
        parents=[parent],
        help="Remove records from a source file if their LinkedIn URL already exists in the CRM pipeline.",
    )
    p_deduplicate.add_argument("file", help="Path to source JSON file")
    p_deduplicate.add_argument("--dry-run", action="store_true",
                               help="Print what would happen without writing")
    p_deduplicate.add_argument("--leads-file", default=None, help="Override leads file")
    p_deduplicate.add_argument("--prospects-file", default=None, help="Override prospects file")
    p_deduplicate.add_argument("--customers-file", default=None, help="Override customers file")

    # filter-competitors
    p_filter_competitors = subparsers.add_parser(
        "filter-competitors",
        parents=[parent],
        aliases=["filter-blocklist"],
        help="Remove records from a source file if they match crm/competitors.json.",
    )
    p_filter_competitors.add_argument("file", help="Path to source JSON file")
    p_filter_competitors.add_argument("--dry-run", action="store_true",
                                      help="Print what would happen without writing")

    # move
    p_move = subparsers.add_parser("move", parents=[parent], help="Move a record between configured pipeline stages.")
    p_move.add_argument("identity_value", help="Configured identity value of the record to move")
    p_move.add_argument("--from", dest="from_stage", required=True, help="Source stage name")
    p_move.add_argument("--to", dest="to_stage", required=True, help="Destination stage name")
    p_move.add_argument("--identity-field", default=None, help="Override the configured primary identity field")
    write_mode = p_move.add_mutually_exclusive_group()
    write_mode.add_argument("--dry-run", action="store_true", help="Preview without writing files")
    write_mode.add_argument("--apply", action="store_true", help="Apply the change (default behavior)")

    # promote
    p_promote = subparsers.add_parser("promote", parents=[parent],
                                      help="Move a record to the next pipeline stage.")
    p_promote.add_argument("identity_value",
                           help="Configured primary identity value of the record to promote")
    p_promote.add_argument("--identity-field", default=None,
                           help="Override the configured primary identity field")
    stage = p_promote.add_mutually_exclusive_group(required=True)
    stage.add_argument("--lead", action="store_true",
                       help="Promote from leads to prospects")
    stage.add_argument("--prospect", action="store_true",
                       help="Promote from prospects to customers")
    p_promote.add_argument("--from-file", default=None,
                           help="Override source file (for testing)")
    p_promote.add_argument("--to-file", default=None,
                           help="Override destination file (for testing)")
    write_mode = p_promote.add_mutually_exclusive_group()
    write_mode.add_argument("--dry-run", action="store_true", help="Preview without writing files")
    write_mode.add_argument("--apply", action="store_true", help="Apply the change (default behavior)")

    # stats
    p_stats = subparsers.add_parser("stats", parents=[parent], help="Show pipeline statistics.")
    p_stats.add_argument("--leads-file", default=None, help="Override leads file")
    p_stats.add_argument("--prospects-file", default=None, help="Override prospects file")
    p_stats.add_argument("--customers-file", default=None, help="Override customers file")

    # validate
    p_validate = subparsers.add_parser("validate", parents=[parent], help="Validate identities, field rules, and sorted stage invariants.")
    p_validate.add_argument("--leads-file", default=None, help="Override leads file")
    p_validate.add_argument("--prospects-file", default=None, help="Override prospects file")
    p_validate.add_argument("--customers-file", default=None, help="Override customers file")

    # recent
    p_recent = subparsers.add_parser("recent", parents=[parent], help="Show records by each stage's configured recent_key date.")
    p_recent.add_argument("-n", "--num", type=int, default=10, help="Number of records to show (default: 10)")
    p_recent.add_argument("--stage", default=None, help="Limit to a specific stage (e.g. leads)")
    p_recent.add_argument("--leads-file", default=None, help="Override leads file")
    p_recent.add_argument("--prospects-file", default=None, help="Override prospects file")
    p_recent.add_argument("--customers-file", default=None, help="Override customers file")

    # demote
    p_demote = subparsers.add_parser("demote", parents=[parent], help="Move a record back one pipeline stage.")
    p_demote.add_argument("identity_value",
                          help="Configured primary identity value of the record to demote")
    p_demote.add_argument("--identity-field", default=None,
                          help="Override the configured primary identity field")
    stage = p_demote.add_mutually_exclusive_group(required=True)
    stage.add_argument("--customer", action="store_true", help="Demote from customers to prospects")
    stage.add_argument("--prospect", action="store_true", help="Demote from prospects to leads")
    p_demote.add_argument("--from-file", default=None, help="Override source file (for testing)")
    p_demote.add_argument("--to-file", default=None, help="Override destination file (for testing)")
    write_mode = p_demote.add_mutually_exclusive_group()
    write_mode.add_argument("--dry-run", action="store_true", help="Preview without writing files")
    write_mode.add_argument("--apply", action="store_true", help="Apply the change (default behavior)")

    # list / ls
    p_list = subparsers.add_parser("list", parents=[parent], aliases=["ls"], help="List records in a pipeline stage.")
    p_list.add_argument("stage", help="Pipeline stage to list (e.g. leads, prospects, customers)")
    p_list.add_argument("--score", default=None, help="Filter by score")
    p_list.add_argument("--company", default=None, help="Filter by company substring")
    p_list.add_argument("--query", default=None, help="Filter by general search query")
    p_list.add_argument("-n", "--limit", type=int, default=None, help="Limit number of results")
    p_list.add_argument("--file", default=None, help="Override the JSON file for the given stage")

    # dump_emails
    p_dump_emails = subparsers.add_parser("dump_emails", parents=[parent],
                                          help="Dump all email addresses in the pipeline, comma separated.")
    p_dump_emails.add_argument("--out", default=None,
                               help="Write the comma-separated emails to this file instead of stdout")

    # backup
    p_backup = subparsers.add_parser("backup", parents=[parent], help="Back up configured CRM files outside Git.")
    p_backup.add_argument("--output", default=None,
                          help="New ZIP path (default: ~/.jsoncrm/backups/<crm>-<timestamp>.zip)")

    # serve
    p_serve = subparsers.add_parser("serve", parents=[parent], help="Start the web UI server.")
    p_serve.add_argument("--port", type=int, default=7341, help="Port (default: 7341)")
    p_serve.add_argument("--github-token", default=os.environ.get("GITHUB_TOKEN", ""), help="GitHub PAT")
    p_serve.add_argument("--repo", default=os.environ.get("GITHUB_REPO", ""), help="owner/repo")
    p_serve.add_argument("--branch", default="main", help="Base branch for PRs")

    # mcp
    subparsers.add_parser("mcp", parents=[parent], help="Start the MCP stdio server.")

    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        sys.exit(1)

    args.crm_context = CRMContext.from_file(args.config)
    _set_json_mode(args.json)

    if args.command == "search":
        cmd_search(args)
    elif args.command == "find":
        cmd_find(args)
    elif args.command == "add":
        cmd_add(args)
    elif args.command == "update":
        cmd_update(args)
    elif args.command == "delete":
        cmd_delete(args)
    elif args.command == "apply_update":
        cmd_apply_update(args)
    elif args.command == "intake":
        cmd_intake(args)
    elif args.command == "parse-from-linkedin-mcp":
        cmd_parse_from_linkedin_mcp(args)
    elif args.command == "shuffle":
        cmd_shuffle(args)
    elif args.command == "top":
        cmd_top(args)
    elif args.command == "merge":
        cmd_merge(args)
    elif args.command == "deduplicate":
        cmd_deduplicate(args)
    elif args.command in ("filter-competitors", "filter-blocklist"):
        cmd_filter_competitors(args)
    elif args.command == "move":
        cmd_move(args)
    elif args.command == "promote":
        cmd_promote(args)
    elif args.command == "stats":
        cmd_stats(args)
    elif args.command == "validate":
        cmd_validate(args)
    elif args.command == "recent":
        cmd_recent(args)
    elif args.command == "demote":
        cmd_demote(args)
    elif args.command in ("list", "ls"):
        cmd_list(args)
    elif args.command == "dump_emails":
        cmd_dump_emails(args)
    elif args.command == "backup":
        cmd_backup(args)
    elif args.command == "mcp":
        from jsoncrm.mcp import run_mcp
        run_mcp(config_path=args.config)
    elif args.command == "serve":
        from jsoncrm.server import run_server
        run_server(
            port=args.port,
            config_path=args.config,
            github_token=args.github_token or None,
            repo=args.repo or None,
            base_branch=args.branch,
        )


if __name__ == "__main__":
    main()
