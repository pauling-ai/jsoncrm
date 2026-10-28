---
name: jsoncrm
description: Operate a JSONCRM pipeline — a CRM stored as JSON files in git (leads.json, prospects.json, customers.json) driven by the jsoncrm CLI. Use when the user mentions their CRM, pipeline, leads, prospects, customers, scoring or promoting contacts, or when a .crm.json file exists in the working directory.
---

# JSONCRM agent skill

The database is plain JSON arrays in the current directory; git is the audit log.
The `jsoncrm` CLI validates and writes everything atomically. Read `.crm.json`
first — it defines the stages, valid transitions, the identity field (often
`linkedin_url`), the score scale, and the blocklist.

## Rules

1. **Never hand-edit the JSON files while a CLI command exists** — the CLI
   enforces identity, scores, and transitions. If you must edit by hand, run
   `jsoncrm validate` afterwards.
2. **Preview, then write.** Every write command takes `--dry-run` (returns the
   prospective record, writes nothing) and `--apply` (explicit write). Running
   with neither writes immediately; for anything nontrivial, show the human the
   dry run first.
3. **Commit after writes.** `git diff` is the product — offer to commit so the
   change lands in the audit log.
4. **Append `--json` to any command** for machine-readable output.
5. **`--config path/to/.crm.json` goes before the command** if the config is
   not in the working directory.

## Reading the pipeline

```bash
jsoncrm stats                          # counts per stage
jsoncrm search "Alice"                 # name/company/URL/email fragment
jsoncrm search "Acme" --company        # companies only
jsoncrm search "Acme" --competitor     # also search the watchlist
jsoncrm list leads --score "⭐⭐⭐⭐" -n 20
jsoncrm list prospects --company Acme
jsoncrm top -n 5 --min ⭐⭐⭐            # best unscored→acted leads first
jsoncrm recent -n 10 --stage leads
jsoncrm dump_emails --out emails.txt   # all pipeline emails, comma-separated
```

## Writing records

`--database_file` picks the stage file; the record must carry the identity
field (check `identity.primary` in `.crm.json`):

```bash
jsoncrm add --database_file leads.json --item_json '{"name":"...","linkedin_url":"...","score":"⭐⭐⭐"}' --dry-run
jsoncrm update --database_file leads.json --item_json '{"linkedin_url":"...","company":"NewCo"}' --dry-run
jsoncrm delete --database_file leads.json --item_json '{"linkedin_url":"..."}' --dry-run
jsoncrm find --database_file leads.json --item_json '{"company":"Acme"}'
```

Scores must be exactly the values in `.crm.json` `scores.order` (plus the
disqualified marker, default `❌`) — anything else is rejected. Drop the
`--dry-run` (or use `--apply`) to write.

## Stage moves

Only transitions declared in `.crm.json` exist. Pass the primary identity value:

```bash
jsoncrm promote "https://linkedin.com/in/alice" --lead       # leads → prospects
jsoncrm promote "https://linkedin.com/in/alice" --prospect   # prospects → customers
jsoncrm demote  "https://linkedin.com/in/alice" --prospect   # prospects → leads
jsoncrm demote  "https://linkedin.com/in/alice" --customer   # customers → prospects
```

All four accept `--dry-run` / `--apply` and `--identity-field` to override the
identity field.

## Hygiene

```bash
jsoncrm validate                       # structural check of all pipeline files
jsoncrm deduplicate intake.json        # drop records already in the pipeline
jsoncrm filter-competitors intake.json # drop blocklist matches
jsoncrm merge scored.json              # merge scored records into leads
jsoncrm backup                         # ZIP snapshot outside git
```

`deduplicate`, `filter-competitors`, and `merge` also take `--dry-run`.

## Intake workflow

```bash
jsoncrm parse-from-linkedin-mcp likes.json   # normalize MCP output to flat records
# ...score the records (your judgment / external data)...
jsoncrm merge likes.json                     # into leads
# or one at a time:
jsoncrm intake intake.json                   # picks the next unscored record
jsoncrm apply_update                         # applies the pending update file
```

## MCP server

If the MCP server is configured (`jsoncrm mcp`), every command above is also
an MCP tool with the same names and arguments — `item_json` accepts a native
object, and `dry_run`/`apply` are booleans. Prefer MCP tools when present;
fall back to the CLI otherwise.

## Web UI

`jsoncrm serve` starts a local spreadsheet UI at http://127.0.0.1:7341 bound
to the same files. Humans use it; you don't need it.
