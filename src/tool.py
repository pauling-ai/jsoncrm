#!/usr/bin/env python3
"""Unified CRM tool — command implementations and CLI entry point."""

import argparse
import json
import random
import sys
from pathlib import Path

# Re-export everything from sub-modules so callers can import from jsoncrm.tool.
from jsoncrm.parsers import cmd_parse_from_linkedin_mcp  # noqa: F401
import jsoncrm.schema as schema
from jsoncrm.schema import (
    COMPETITORS_FILE,
    COMPETITOR_COMPANY_KEYS,
    COMPETITOR_PERSON_KEYS,
    CRM_DIR,
    CUSTOMERS_FILE,
    LEADS_FILE,
    PENDING_FILE,
    PIPELINE_FILES,
    PROSPECTS_FILE,
    SCORE_ORDER,
    score_value,
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
    record_identity_value,
    search_competitors,
)


def load_all():
    records = []
    for stage, path in PIPELINE_FILES:
        if path.exists():
            data = json.loads(path.read_text())
            for r in data:
                records.append((stage, r))
    return records


def load_item(args):
    if getattr(args, "item_file", None) and getattr(args, "item_json", None):
        print("Error: use only one of --item_file or --item_json")
        sys.exit(1)
    if getattr(args, "item_file", None):
        return json.loads(Path(args.item_file).read_text())
    if getattr(args, "item_json", None):
        return json.loads(args.item_json)
    print("Error: provide one of --item_file or --item_json")
    sys.exit(1)


def cmd_search(args):
    if args.competitor:
        comp_hits = search_competitors(args.query, person=args.person, company=args.company)
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

    records = load_all()
    hits = [(stage, r) for stage, r in records
            if match(r, args.query, person=args.person, company=args.company)]

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

    matcher = load_item(args)
    if not isinstance(matcher, dict):
        print("Error: find matcher must be a JSON object")
        sys.exit(1)

    records = load_json(database_path)
    if not isinstance(records, list):
        print("Error: database file must be a JSON array")
        sys.exit(1)

    def matches(record):
        for key, value in matcher.items():
            if record.get(key) != value:
                return False
        return True

    results = [record for record in records if matches(record)]
    output = json.dumps(results, indent=2, ensure_ascii=False)
    if args.output_file:
        Path(args.output_file).write_text(output + "\n")
    else:
        print(output)


def cmd_add(args):
    database_path = Path(args.database_file)
    item = load_item(args)
    if not isinstance(item, dict):
        print("Error: add item must be a JSON object")
        sys.exit(1)
    identity_field, identity_value = record_identity_value(item)
    if not identity_field:
        print("Error: add requires at least one of 'id' or 'linkedin_url'")
        sys.exit(1)

    records = load_json(database_path)
    if records and not isinstance(records, list):
        print("Error: database file must be a JSON array")
        sys.exit(1)

    records.append(item)
    database_path.write_text(json.dumps(records, indent=2, ensure_ascii=False) + "\n")

    output = json.dumps(item, indent=2, ensure_ascii=False)
    if args.output_file:
        Path(args.output_file).write_text(output + "\n")
    else:
        print(output)


def cmd_delete(args):
    database_path = Path(args.database_file)
    if not database_path.exists():
        print(f"Error: {database_path} not found")
        sys.exit(1)

    item = load_item(args)
    if not isinstance(item, dict):
        print("Error: delete item must be a JSON object")
        sys.exit(1)

    identity_field, identity_value = record_identity_value(item)
    if not identity_field:
        print("Error: delete requires at least one of 'id' or 'linkedin_url'")
        sys.exit(1)

    records = load_json(database_path)
    if not isinstance(records, list):
        print("Error: database file must be a JSON array")
        sys.exit(1)

    kept = []
    deleted = None
    for record in records:
        if deleted is None and record.get(identity_field) == identity_value:
            deleted = record
        else:
            kept.append(record)

    if deleted is None:
        print(f"Error: no record found for {identity_field} '{identity_value}'")
        sys.exit(1)

    database_path.write_text(json.dumps(kept, indent=2, ensure_ascii=False) + "\n")

    output = json.dumps(deleted, indent=2, ensure_ascii=False)
    if args.output_file:
        Path(args.output_file).write_text(output + "\n")
    else:
        print(output)


def cmd_update(args):
    database_path = Path(args.database_file)
    if not database_path.exists():
        print(f"Error: {database_path} not found")
        sys.exit(1)

    item = load_item(args)
    if not isinstance(item, dict):
        print("Error: update item must be a JSON object")
        sys.exit(1)

    identity_field, identity_value = record_identity_value(item)
    if not identity_field:
        print("Error: update requires at least one of 'id' or 'linkedin_url'")
        sys.exit(1)

    records = load_json(database_path)
    if not isinstance(records, list):
        print("Error: database file must be a JSON array")
        sys.exit(1)

    updated = None
    for record in records:
        if record.get(identity_field) == identity_value:
            record.update(item)
            updated = record
            break

    if updated is None:
        print(f"Error: no record found for {identity_field} '{identity_value}'")
        sys.exit(1)

    database_path.write_text(json.dumps(records, indent=2, ensure_ascii=False) + "\n")

    output = json.dumps(updated, indent=2, ensure_ascii=False)
    if args.output_file:
        Path(args.output_file).write_text(output + "\n")
    else:
        print(output)


def cmd_apply_update(args):
    pending_path = Path(args.pending_file) if args.pending_file != "default" else PENDING_FILE
    if not pending_path.exists():
        print(f"Error: no pending update file at {pending_path}")
        sys.exit(1)
    payload = json.loads(pending_path.read_text())
    target_url = payload.get("linkedin_url")
    if not target_url:
        print("Error: pending file missing 'linkedin_url'")
        sys.exit(1)
    updates = {k: coerce(v) for k, v in payload.get("fields", {}).items()}
    if not updates:
        print("Error: pending file has no 'fields'")
        sys.exit(1)
    target_file = payload.get("target_file")
    apply_updates(target_url, updates, target_file=target_file)
    pending_path.unlink()


def cmd_shuffle(args):
    path = Path(args.file)
    if not path.exists():
        print(f"Error: {path} not found")
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

    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
    print(f"Shuffled {len(data)} records in {path.name}.")


def cmd_intake(args):
    path = Path(args.file)
    if not path.exists():
        print(f"Error: {path} not found")
        sys.exit(1)

    data = json.loads(path.read_text())
    if not isinstance(data, list):
        print("Error: file must be a JSON array")
        sys.exit(1)

    unscored = [r for r in data if not r.get("score")]
    if not unscored:
        print("All records scored.")
        sys.exit(1)

    r = unscored[0]
    print(f"Name:      {r.get('name')}")
    print(f"URL:       {r.get('linkedin_url')}")
    print(f"Username:  {r.get('linkedin_username')}")
    if r.get("position"):
        print(f"Position:  {r.get('position')}")
    if r.get("company"):
        print(f"Company:   {r.get('company')}")
    print(f"Remaining: {len(unscored)} unscored")

    output_path = Path(args.output) if args.output else PENDING_FILE
    pending = {
        "linkedin_url": r.get("linkedin_url"),
        "target_file": str(path),
        "fields": {},
    }
    output_path.write_text(json.dumps(pending, indent=2, ensure_ascii=False) + "\n")
    print(f"\nWrote {output_path} — fill in fields, then run: jsoncrm apply_update {output_path}")


def cmd_top(args):
    path = Path(args.file) if args.file else LEADS_FILE
    if not path.exists():
        print(f"Error: {path} not found")
        sys.exit(1)

    records = json.loads(path.read_text())
    results = []
    for r in records:
        score = r.get("score")
        if not args.include_contacted and r.get("contacted_at"):
            continue
        if score is None:
            continue
        if score == "❌" and not args.include_disqualified:
            continue
        if args.min_score and score_value(score) < score_value(args.min_score):
            continue
        results.append(r)

    results.sort(key=lambda r: score_value(r.get("score")), reverse=True)
    results = results[:args.num]

    if not results:
        print("No leads match the filters.")
        sys.exit(1)

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
        output_path.write_text(json.dumps(pending, indent=2, ensure_ascii=False) + "\n")
        print(
            f"Wrote {output_path} — fill in fields, then run: jsoncrm apply_update {output_path}",
            file=sys.stderr,
        )


def cmd_merge(args):
    source_path = Path(args.file)
    leads_path = Path(args.leads_file) if args.leads_file else LEADS_FILE

    if not source_path.exists():
        print(f"Error: {source_path} not found")
        sys.exit(1)

    source_records = load_json(source_path)
    if not isinstance(source_records, list):
        print("Error: source file must be a JSON array")
        sys.exit(1)

    scored = [r for r in source_records if r.get("score")]
    unscored = [r for r in source_records if not r.get("score")]

    if args.leads_file:
        known_urls = build_known_urls(leads_file=leads_path)
    else:
        known_urls = build_known_urls()

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

    print(f"Source:   {len(source_records)} records")
    print(f"Scored:   {len(scored)}  |  Unscored: {len(unscored)} (left in source file)")
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

    if args.dry_run:
        print("\n(dry run — no files modified)")
        return

    if not added and not scored:
        print("\nNothing to do.")
        return

    if added:
        merged = existing_leads + added
        leads_path.write_text(json.dumps(merged, indent=2, ensure_ascii=False) + "\n")
        print(f"\nWrote {len(merged)} records to {leads_path}")

    source_path.write_text(json.dumps(unscored, indent=2, ensure_ascii=False) + "\n")
    print(f"Updated {source_path.name}: {len(unscored)} unscored records remaining")


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
    )

    kept = []
    removed = []
    for record in source_records:
        url = normalize_url(record.get("linkedin_url"))
        if url and url in known_urls:
            removed.append(record)
        else:
            kept.append(record)

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

    source_path.write_text(json.dumps(kept, indent=2, ensure_ascii=False) + "\n")
    print(f"Updated {source_path.name}: {len(kept)} records remaining")


def cmd_filter_competitors(args):
    source_path = Path(args.file)
    if not source_path.exists():
        print(f"Error: {source_path} not found")
        sys.exit(1)

    source_records = load_json(source_path)
    if not isinstance(source_records, list):
        print("Error: source file must be a JSON array")
        sys.exit(1)
    if not COMPETITORS_FILE.exists():
        print(f"Error: {COMPETITORS_FILE} not found")
        sys.exit(1)

    competitors = load_json(COMPETITORS_FILE)
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

    source_path.write_text(json.dumps(kept, indent=2, ensure_ascii=False) + "\n")
    print(f"Updated {source_path.name}: {len(kept)} records remaining")


PROMOTE_MAP = {
    "lead": ("leads.json", "prospects.json"),
    "prospect": ("prospects.json", "customers.json"),
}


def _build_promote_map(config):
    """Build PROMOTE_MAP from config transitions."""
    transitions = config.pipeline_transitions
    result = {}
    stage_files = {s["name"]: CRM_DIR / s["file"] for s in config.pipeline_stages}
    for from_stage, to_stages in transitions.items():
        if to_stages:
            key = from_stage[:-1] if from_stage.endswith("s") else from_stage
            to_stage = to_stages[0]
            result[key] = (
                stage_files.get(from_stage, CRM_DIR / f"{from_stage}.json").name,
                stage_files.get(to_stage, CRM_DIR / f"{to_stage}.json").name,
            )
    return result


def cmd_promote(args):
    if args.lead:
        stage = "lead"
    else:
        stage = "prospect"

    src_name, dst_name = PROMOTE_MAP[stage]
    src_path = Path(args.from_file) if args.from_file else CRM_DIR / src_name
    dst_path = Path(args.to_file) if args.to_file else CRM_DIR / dst_name

    if not src_path.exists():
        print(f"Error: {src_path} not found")
        sys.exit(1)

    src_data = load_json(src_path)
    dst_data = load_json(dst_path)

    norm = normalize_url(args.linkedin_url)
    record = None
    remaining = []
    for r in src_data:
        if normalize_url(r.get("linkedin_url", "")) == norm:
            record = r
        else:
            remaining.append(r)

    if record is None:
        print(f"Error: no record found for '{args.linkedin_url}' in {src_path.name}")
        sys.exit(1)

    dst_data.append(record)
    src_path.write_text(json.dumps(remaining, indent=2, ensure_ascii=False) + "\n")
    dst_path.write_text(json.dumps(dst_data, indent=2, ensure_ascii=False) + "\n")

    name = record.get("name", args.linkedin_url)
    print(f"Promoted: {name}  {src_path.name} → {dst_path.name}")


def cmd_stats(args):
    # Use explicit overrides if provided, otherwise fall back to config-driven pipeline
    if args.leads_file or args.prospects_file or args.customers_file:
        pipeline = [
            ("leads", Path(args.leads_file) if args.leads_file else LEADS_FILE),
            ("prospects", Path(args.prospects_file) if args.prospects_file else PROSPECTS_FILE),
            ("customers", Path(args.customers_file) if args.customers_file else CUSTOMERS_FILE),
        ]
    else:
        pipeline = [(name, path) for name, path in PIPELINE_FILES]

    for stage, path in pipeline:
        records = load_json(path)
        total = len(records)

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

            print(f"Leads: {total}")
            print(f"  Scored:       {len(scored)}")
            print(f"  Unscored:     {len(unscored)}")
            print(f"  Contacted:    {len(contacted)}")
            print(f"  Disqualified: {len(disqualified)}")
            for stars in ["⭐⭐⭐⭐⭐", "⭐⭐⭐⭐", "⭐⭐⭐", "⭐⭐", "⭐"]:
                count = by_score.get(stars, 0)
                if count:
                    print(f"  {stars}  {count}")
        elif stage == "prospects" and total > 0:
            closed = [r for r in records if r.get("status") == "closed"]
            active = total - len(closed)
            print(f"Prospects: {total} ({active} active, {len(closed)} closed)")
        elif stage == "customers" and total > 0:
            companies = len(set(r.get("company") for r in records if r.get("company")))
            paid_companies = len(set(r.get("company") for r in records if r.get("paid") and r.get("company")))
            unpaid_companies = len(set(r.get("company") for r in records if not r.get("paid") and r.get("company")))
            print(f"Customers: {total} contacts ({companies} companies)")
            print(f"  Paid:     {sum(1 for r in records if r.get('paid'))} contacts ({paid_companies} companies)")
            print(f"  Unpaid:   {sum(1 for r in records if not r.get('paid'))} contacts ({unpaid_companies} companies)")
        else:
            print(f"{stage.capitalize()}: {total}")


def main():
    parser = argparse.ArgumentParser(description="Unified CRM tool.")
    parser.add_argument("--config", default=None, help="Path to .crm.json config file")
    subparsers = parser.add_subparsers(dest="command")

    # search
    p_search = subparsers.add_parser("search", help="Search CRM pipeline for a lead.")
    p_search.add_argument("query", help="Name, company, LinkedIn URL, or email fragment to search for")
    mode = p_search.add_mutually_exclusive_group()
    mode.add_argument("--person", action="store_true", help="Search person fields only (name, LinkedIn URL, email)")
    mode.add_argument("--company", action="store_true", help="Search company field only")
    p_search.add_argument("--competitor", action="store_true",
                          help="Also search the competitor watchlist")

    # find
    p_find = subparsers.add_parser("find", help="Find records in a specific CRM JSON file.")
    p_find.add_argument("--database_file", required=True, help="JSON file to search")
    p_find.add_argument("--item_file", default=None, help="Path to JSON object containing match fields")
    p_find.add_argument("--item_json", default=None, help="JSON object containing match fields")
    p_find.add_argument("--output_file", default=None, help="Optional file for matched results")

    # add
    p_add = subparsers.add_parser("add", help="Add one record to a specific CRM JSON file.")
    p_add.add_argument("--database_file", required=True, help="JSON file to update")
    p_add.add_argument("--item_file", default=None, help="Path to JSON object to add")
    p_add.add_argument("--item_json", default=None, help="JSON object to add")
    p_add.add_argument("--output_file", default=None, help="Optional file for written record")

    # update
    p_update = subparsers.add_parser("update", help="Update one record in a specific CRM JSON file.")
    p_update.add_argument("--database_file", required=True, help="JSON file to update")
    p_update.add_argument("--item_file", default=None, help="Path to JSON object containing identity and fields")
    p_update.add_argument("--item_json", default=None, help="JSON object containing identity and fields")
    p_update.add_argument("--output_file", default=None, help="Optional file for updated record")

    # delete
    p_delete = subparsers.add_parser("delete", help="Delete one record from a specific CRM JSON file.")
    p_delete.add_argument("--database_file", required=True, help="JSON file to update")
    p_delete.add_argument("--item_file", default=None, help="Path to JSON object containing id or linkedin_url")
    p_delete.add_argument("--item_json", default=None, help="JSON object containing id or linkedin_url")
    p_delete.add_argument("--output_file", default=None, help="Optional file for deleted record")

    # apply_update
    p_apply_update = subparsers.add_parser("apply_update", help="Apply updates from a pending file.")
    p_apply_update.add_argument("pending_file", nargs="?", const="default", default="default",
                                help="Pending update file (default: crm/.pending_update.json)")

    # intake
    p_intake = subparsers.add_parser("intake", help="Pick next unscored record from an intake file.")
    p_intake.add_argument("file", help="Path to intake JSON file")
    p_intake.add_argument("--output", default=None,
                          help="Optional pending file to write")

    # parse-from-linkedin-mcp
    p_intake_mcp = subparsers.add_parser("parse-from-linkedin-mcp", help="Convert MCP get_post_likers output to CRM flat list in-place.")
    p_intake_mcp.add_argument("files", nargs='+', help="Path to one or more MCP JSON files")

    # shuffle
    p_shuffle = subparsers.add_parser("shuffle", help="Shuffle records in a JSON array file in-place.")
    p_shuffle.add_argument("file", help="Path to JSON array file")
    p_shuffle.add_argument("--seed", type=int, default=None,
                           help="Optional random seed for reproducible shuffles")
    p_shuffle.add_argument("--dry-run", action="store_true",
                           help="Print shuffled output without writing")

    # top
    p_top = subparsers.add_parser("top", help="Return top scored leads from leads.json.")
    p_top.add_argument("-n", "--num", type=int, default=1,
                       help="Number of leads to return (default: 1)")
    p_top.add_argument("--min", dest="min_score", default=None,
                       metavar="STARS", help="Minimum score, e.g. ⭐⭐⭐")
    p_top.add_argument("--include-contacted", action="store_true",
                       help="Include leads that have already been contacted")
    p_top.add_argument("--include-disqualified", action="store_true",
                       help="Include disqualified (❌) leads")
    p_top.add_argument("--output", default=None,
                       help="Optional pending file to write. Requires exactly one result.")
    p_top.add_argument("--file", default=None,
                       help="Override leads file (default: crm/leads.json)")

    # merge
    p_merge = subparsers.add_parser("merge",
                                    help="Merge scored records from a source file into leads.json.")
    p_merge.add_argument("file", help="Path to source JSON file")
    p_merge.add_argument("--dry-run", action="store_true",
                         help="Print what would happen without writing")
    p_merge.add_argument("--leads-file", default=None,
                         help="Override leads file (default: crm/leads.json)")

    # deduplicate
    p_deduplicate = subparsers.add_parser(
        "deduplicate",
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
        help="Remove records from a source file if they match crm/competitors.json.",
    )
    p_filter_competitors.add_argument("file", help="Path to source JSON file")
    p_filter_competitors.add_argument("--dry-run", action="store_true",
                                      help="Print what would happen without writing")

    # promote
    p_promote = subparsers.add_parser("promote",
                                      help="Move a record to the next pipeline stage.")
    p_promote.add_argument("linkedin_url", help="LinkedIn URL of the record to promote")
    stage = p_promote.add_mutually_exclusive_group(required=True)
    stage.add_argument("--lead", action="store_true",
                       help="Promote from leads to prospects")
    stage.add_argument("--prospect", action="store_true",
                       help="Promote from prospects to customers")
    p_promote.add_argument("--from-file", default=None,
                           help="Override source file (for testing)")
    p_promote.add_argument("--to-file", default=None,
                           help="Override destination file (for testing)")

    # stats
    p_stats = subparsers.add_parser("stats", help="Show pipeline statistics.")
    p_stats.add_argument("--leads-file", default=None, help="Override leads file")
    p_stats.add_argument("--prospects-file", default=None, help="Override prospects file")
    p_stats.add_argument("--customers-file", default=None, help="Override customers file")

    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        sys.exit(1)

    # Load config and rebind module-level constants
    from jsoncrm.config import Config
    config = Config.from_file(args.config)
    # If a config file was explicitly provided, resolve relative paths from its directory
    if args.config:
        schema.CRM_DIR = Path(args.config).resolve().parent
    schema.apply_config(config)

    # Rebind tool.py's imported names so they reflect the config
    global PIPELINE_FILES, COMPETITORS_FILE, LEADS_FILE, PROSPECTS_FILE
    global CUSTOMERS_FILE, PENDING_FILE, SCORE_ORDER, PROMOTE_MAP
    PIPELINE_FILES = schema.PIPELINE_FILES
    COMPETITORS_FILE = schema.COMPETITORS_FILE
    LEADS_FILE = schema.LEADS_FILE
    PROSPECTS_FILE = schema.PROSPECTS_FILE
    CUSTOMERS_FILE = schema.CUSTOMERS_FILE
    PENDING_FILE = schema.PENDING_FILE
    SCORE_ORDER = schema.SCORE_ORDER
    PROMOTE_MAP = _build_promote_map(config)

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
    elif args.command == "filter-competitors":
        cmd_filter_competitors(args)
    elif args.command == "promote":
        cmd_promote(args)
    elif args.command == "stats":
        cmd_stats(args)


if __name__ == "__main__":
    main()
