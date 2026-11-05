# JSONCRM agent instructions (for AGENTS.md)

Paste this block into the `AGENTS.md` of your CRM repo for Codex, Cursor, or
any AGENTS.md-compatible agent.

---

## This repo is a JSONCRM pipeline

The JSON files are the CRM database; git is the audit log. Operate it through
the `jsoncrm` CLI — it validates identity, scores, and transitions, and writes
atomically. Read `.crm.json` for stages, transitions, the identity field
(usually `linkedin_url`), and the valid score values.

- Any command supports `--json` for machine-readable output.
- Every write command (`add`, `update`, `delete`, `promote`, `demote`, `merge`,
  `deduplicate`, `filter-competitors`) takes `--dry-run` to preview and
  `--apply` to write explicitly. Prefer showing a dry run before writing.
- After writing, offer to commit — the git diff is the audit trail.
- If something can't be done with the CLI, edit the JSON by hand only as a
  last resort and run `jsoncrm validate` afterwards.

Quick reference:

```
jsoncrm stats / search <q> / list <stage> / top -n 5 --min ⭐⭐⭐ / recent
jsoncrm add|update|delete --database_file <file> --item_json '{...}' [--dry-run|--apply]
jsoncrm promote <identity> --lead|--prospect    # or: demote <identity> --prospect|--customer
jsoncrm validate / deduplicate <file> / filter-competitors <file> / merge <file> / backup
```

Scores must match `.crm.json` exactly. Stage moves only work along configured
transitions. The `jsoncrm mcp` MCP server exposes the same commands as tools
if configured — prefer those when available.
