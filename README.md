# JSONCRM

[![PyPI](https://img.shields.io/pypi/v/jsoncrm)](https://pypi.org/project/jsoncrm/)
[![Python Versions](https://img.shields.io/pypi/pyversions/jsoncrm)](https://pypi.org/project/jsoncrm/)
[![License: AGPL-3.0](https://img.shields.io/pypi/l/jsoncrm)](https://www.gnu.org/licenses/agpl-3.0)

A CRM system built on top of JSON. That's right.

Your pipeline — leads, prospects, customers — lives as plain JSON files in a git repo. The files are the database, git is the audit log, and AI agents are first-class users: they read and write the same state you do, through a CLI, a first-party MCP server, or plain file I/O.

- **No accounts, no cloud, no lock-in** — the data is yours, in files you can read, diff, and roll back
- **Agent-native** — JSON is what LLMs read and write without friction; every write supports a dry run
- **Zero infra** — `pip install` and a git repo; no database, no containers
- **Humans welcome too** — a local spreadsheet-style web UI, plus a GitHub PR workflow for review

Why build a CRM this way? The long version — what a CRM actually is, the spreadsheet lesson, and why agents change the answer — lives in [the philosophy](https://www.jsoncrm.dev/philosophy).

This project is hosted [here](https://www.jsoncrm.dev)

---

## Installation

```bash
# No install — run it straight from PyPI with uv
uvx jsoncrm stats

# Or install the core CLI (zero dependencies)
pip install jsoncrm
# with web server support
pip install "jsoncrm[web]"
# with MCP server support
pip install "jsoncrm[mcp]"
```

The core CLI has no dependencies, so a `uvx` cold start is near-instant. To run the web UI or MCP server without installing anything, use the extras form: `uvx --from "jsoncrm[web,mcp]" jsoncrm serve`.

For JavaScript tests (optional):
```bash
npm install
```

## Quick Start

```bash
# Initialize a CRM directory
cd my-crm

# Create a .crm.json config (or use defaults)
# Edit leads.json, prospects.json, customers.json

# View stats
jsoncrm stats

# Search for a lead
jsoncrm search "Alice"

# Start the web UI
jsoncrm serve
# open http://127.0.0.1:7341
```

## Data Model

JSONCRM stores everything as plain JSON arrays of objects. Each record is a flat object with arbitrary fields. The pipeline is defined by `.crm.json`:

```json
{
  "pipeline": {
    "stages": [
      {"name": "leads", "file": "leads.json"},
      {"name": "prospects", "file": "prospects.json"},
      {"name": "customers", "file": "customers.json"}
    ],
    "transitions": {
      "leads": ["prospects"],
      "prospects": ["customers"]
    }
  },
  "identity": {
    "primary": "linkedin_url",
    "fallback": ["id"]
  },
  "scores": {
    "order": ["⭐", "⭐⭐", "⭐⭐⭐", "⭐⭐⭐⭐", "⭐⭐⭐⭐⭐"],
    "disqualified": "❌"
  },
  "blocklist": {
    "file": "competitors.json",
    "match_fields": ["company", "name"]
  }
}
```

A typical lead looks like:

```json
{
  "name": "Alice Testerson",
  "position": "Head of Computational Chemistry",
  "company": "TestPharma Inc",
  "linkedin_url": "https://www.linkedin.com/in/alice-testerson/",
  "email": "alice@testpharma.com",
  "score": "⭐⭐⭐⭐",
  "connected": false,
  "contacted_at": null,
  "source": "manual",
  "added": "2026-01-01",
  "notes": "Met at conference"
}
```

## CLI Commands

### Search & Inspect
- `jsoncrm search <query>` — Search across all pipeline stages
- `jsoncrm search <query> --company` — Search companies only
- `jsoncrm search <query> --competitor` — Also search competitor watchlist
- `jsoncrm stats` — Pipeline statistics
- `jsoncrm list leads` — List records in a stage (with `--score`, `--company`, `--query`, `--limit`)
- `jsoncrm recent` — Most recently added records
- `jsoncrm top -n 5 --min ⭐⭐⭐` — Top scored leads
- `jsoncrm dump_emails --out emails.txt` — Dump all pipeline emails, comma separated

### CRUD
- `jsoncrm add --database_file leads.json --item_json '{...}'`
- `jsoncrm update --database_file leads.json --item_json '{...}'`
- `jsoncrm delete --database_file leads.json --item_json '{...}'`
- `jsoncrm find --database_file leads.json --item_json '{"company":"Acme"}'`

### Pipeline
- `jsoncrm promote <identity> --lead` — Move lead → prospect
- `jsoncrm promote <identity> --prospect` — Move prospect → next configured stage
  (uses `identity.primary`; override with `--identity-field`)
- `jsoncrm demote <identity> --prospect` — Move prospect → lead
- `jsoncrm demote <identity> --customer` — Move customer → prospect
  (uses `identity.primary`; override with `--identity-field`)

### Write Previews

`add`, `update`, `delete`, `promote`, and `demote` write immediately by default. Use `--dry-run` to run the same validation and inspect the prospective record without writing CRM or output files. Use `--apply` when you want to make the write explicit; the two flags are mutually exclusive.

```bash
jsoncrm update --database_file leads.json --item_json '{"linkedin_url":"https://example.com/alice","company":"NewCo"}' --dry-run
jsoncrm update --database_file leads.json --item_json '{"linkedin_url":"https://example.com/alice","company":"NewCo"}' --apply
```

Dry-run JSON output includes `dry_run: true` and the prospective `record`; stage moves also include `from` and `to`. The same boolean arguments are available as `dry_run` and `apply` through MCP.

### Data Quality
- `jsoncrm validate` — Validate all pipeline files for structural integrity
- `jsoncrm deduplicate intake.json` — Remove records already in pipeline
- `jsoncrm filter-competitors intake.json` — Remove competitor matches
- `jsoncrm merge scored.json` — Merge scored records into leads

### Backup
- `jsoncrm backup` — Snapshot configured CRM files to a ZIP outside Git
- `jsoncrm backup --output /path/to/backup.zip` — Write to an exact new ZIP path

### LinkedIn MCP
- `jsoncrm parse-from-linkedin-mcp likes.json` — Convert MCP output to CRM flat list
- `jsoncrm intake intake.json` — Pick next unscored record
- `jsoncrm apply_update` — Apply pending update file

### MCP Server
- `jsoncrm mcp` — Start the stdio MCP server with CLI-parity tools

### Web Server
- `jsoncrm serve` — Start the web UI on http://127.0.0.1:7341
- `jsoncrm serve --port 8080 --github-token $TOKEN --repo owner/repo`

All commands support `--config path/to/.crm.json` for custom configs. Place this global option before the command, for example `jsoncrm --config /path/to/.crm.json stats`.

## MCP Server

Install the MCP extra and start the server from a CRM directory:

```bash
pip install "jsoncrm[mcp]"
jsoncrm mcp
```

Every canonical CLI command except the long-running `serve` and `mcp` commands is exposed as an MCP tool; aliases such as `ls` are not duplicated. The tools use the same CLI implementation, and integration tests enforce command coverage, argument schemas, defaults, results, errors, and file effects.

For Claude Desktop, add this to `claude_desktop_config.json` with an absolute config path:

```json
{
  "mcpServers": {
    "jsoncrm": {
      "command": "jsoncrm",
      "args": ["--config", "/absolute/path/to/.crm.json", "mcp"]
    }
  }
}
```

For Claude Code:

```bash
claude mcp add --transport stdio jsoncrm -- jsoncrm --config /absolute/path/to/.crm.json mcp
```

The `item_json` arguments accept either the CLI's JSON-encoded string or a native MCP object. JSON list results are returned under `result`; output from legacy text-only commands is returned under `output`.

## Agent Skill

Give your agent expert jsoncrm workflow knowledge (dry-run discipline, identity rules, intake flow) — no MCP required, works alongside it.

**Claude Code plugin** (one command, managed and updatable):

```
/plugin install jsoncrm --marketplace pauling-ai/jsoncrm
```

**Or install the skill directly** into your CRM repo:

```bash
# Claude Code (project-level skill)
mkdir -p .claude/skills/jsoncrm
curl -fsSL https://raw.githubusercontent.com/pauling-ai/jsoncrm/main/skills/jsoncrm/SKILL.md \
  -o .claude/skills/jsoncrm/SKILL.md

# Codex / Cursor / any AGENTS.md-compatible agent
curl -fsSL https://raw.githubusercontent.com/pauling-ai/jsoncrm/main/skills/AGENTS-snippet.md >> AGENTS.md
```

For Claude Code user-level install (all projects), target `~/.claude/skills/jsoncrm/SKILL.md` instead.

## Web UI

`jsoncrm serve` launches a local spreadsheet-like UI:

- **Pipeline tabs** — Switch between leads, prospects, customers
- **Inline editing** — Double-click any cell, Tab/Enter to navigate
- **Search** — Debounced server-side search across all fields
- **Sort** — Click column headers for server-side sort
- **Pagination** — 100 rows per page (fast even with 2,000+ records)
- **Score visualization** — Stars rendered in gold, disqualified in red
- **Competitor warnings** — Red badge when company matches blocklist
- **Promote/demote buttons** — Move records between stages
- **Dark mode** — Respects `prefers-color-scheme`

### GitHub PR Integration

Configure with `--github-token` and `--repo`:

```bash
jsoncrm serve --github-token $GITHUB_TOKEN --repo pauling-ai/pauling-marketing
```

The "Open PR" button in the UI creates a branch, commits all pipeline files, and opens a pull request on GitHub. Changes are reviewed and merged through your normal git workflow.

## Agentic vs Human Usage

### Humans
- Use the web UI (`jsoncrm serve`) for browsing and editing
- Use the CLI for one-off operations (`jsoncrm search`, `jsoncrm promote`)
- Submit changes via GitHub PRs for review

### AI Agents
- Read and write JSON files directly
- Use the CLI or first-party MCP server (`jsoncrm mcp`) as tools
- No UI automation needed — just structured file I/O
- Every change is auditable in git

Example agent workflow:
```
1. Agent reads leads.json
2. Agent scores new leads using external data
3. Agent writes updates via `jsoncrm update` or direct file edit
4. Human reviews via git diff or GitHub PR
5. Agent promotes qualified leads via `jsoncrm promote`
```

## Version Control

Because everything is JSON, git becomes the CRM's audit log:

```bash
git diff leads.json          # See what changed
git log -p leads.json        # Full history
git revert HEAD -- leads.json # Roll back
```

The server writes to disk immediately, so local edits are always in sync with the filesystem. For upstream changes, use the GitHub PR flow or push directly.

## Backups

Git history does not protect against damage to `.git` itself. Create an independent ZIP snapshot with:

```bash
jsoncrm backup
# Default: ~/.jsoncrm/backups/<crm-name>-<UTC-timestamp>.zip

jsoncrm backup --output /path/to/recovery/backup.zip
```

Backups include the active config file, configured pipeline files, blocklist, and pending update file when present. Missing configured files are listed in the result and in `backup-manifest.json` inside the archive. Writes are atomic, existing backups are never overwritten, and destinations inside the CRM's Git repository are rejected.

To recover manually, extract the ZIP into a new directory and inspect or copy back the JSON files:

```bash
unzip /path/to/backup.zip -d /path/to/recovered-crm
```

## Configuration

`.crm.json` in the working directory drives all behavior:

| Key | Purpose |
|-----|---------|
| `pipeline.stages` | Stage names and file mappings |
| `pipeline.transitions` | Valid promote paths |
| `identity.primary` | Main ID field (e.g. `linkedin_url`) |
| `identity.fallback` | Fallback ID fields |
| `scores.order` | Valid score values |
| `scores.disqualified` | Disqualified marker |
| `blocklist.file` | Competitor watchlist file |
| `blocklist.match_fields` | Fields to match against blocklist |

Marketing and investor CRMs can coexist with different `.crm.json` configs.

## Development

```bash
# Python tests
pytest tests/

# JavaScript tests
npm test

# Install in editable mode with all development capabilities
pip install -e ".[dev,web,mcp]"
```

### Releasing

1. Bump the version in **both** `pyproject.toml` and `src/__init__.py` (keep them in sync).
2. Run `./publish.sh` — it builds fresh `dist/` artifacts and uploads them to PyPI.

The publish token lives in the macOS Keychain, never in the repo. One-time setup on a new machine:

```bash
security add-generic-password -s pypi -a jsoncrm -w
```

## License

This project is licensed under the GNU Affero General Public License v3.0 only.

Commercial licensing is available for organizations that want to use this software
without the obligations of the AGPL. Contact: info@pauling.ai

## Copyright

Copyright (C) 2026 Pauling.AI
