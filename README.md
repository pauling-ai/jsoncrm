# JSONCRM

A CRM system built on top of JSON. That's right. You may be wondering why? And the answer is: why not? If this doesn't immediately tickle your hypothalamus here is the longer intro ↓↓↓

CRMs are valuable because they combine two things most companies fail to systematize: a structured database of customer relationships and a process engine that makes sure people actually do what they said they would do. Contacts, companies, deals, and activities form a living timeline of every interaction, while workflows make sure nothing quietly dies in a corner. The real power of a CRM is not the UI that guides people through a process, or the data contained in its database. It is the enforcement of consistent behavior at scale. In other words, it is the system that politely refuses to let you forget your leads.

Historically, tools like Salesforce and HubSpot wrapped this idea in large, heavy applications. But of course spreadsheets have always been here, and proved you could get surprisingly far with something much simpler. Rows become records, tabs become pipeline stages, and humans drag deals around and call it a process. It works, until it very much does not. No enforcement, no structure, no automation. Just optimism and increasingly questionable data. One lesson is: the CRM is not the interface. It is the combination of state and process. The interface is just the surface.

JSONCRM takes this one step further by making the state itself the interface. Instead of hiding data inside an application, everything lives as structured JSON files. Contacts, deals, pipelines. You can open them, edit them, diff them, and roll them back. Git handles history and collaboration. Code handles the process, enforcing stage transitions, next actions, and updates. No mystery, no black box. Just files as the source of truth and tools making sure things happen the way they should.

Now, if you are a human reading this, then you may think: well, we already have databases. And it's true! We have databases and they are great. But as databases become more complex and rich they become harder to manipulate, and then you need UIs and so on and we are back to the same place. As a human you may be very good using CRM user interfaces. But guess who's not that good? That's right, AI agents.

The real shift is that JSONCRM is native to AI agents. JSON is exactly the kind of structure language models can read and write without friction. Instead of forcing an agent to click through a UI, you give it the actual state of the business. It can reason over deals, update records, draft follow ups, and trigger actions through tools. Humans and agents now operate on the same substrate: inspectable files, auditable changes, and explicit workflows. The result is a CRM that is not just simpler or more flexible, but fundamentally different. A git backed, agent native system where customer data, process, and automation are all transparent, programmable, and shared between humans and AI.

On top of that, extensions become trivial instead of a multi month integration project. Because everything is just files and tools, you can plug in new capabilities as simple services that read and write JSON. An MCP server can watch for new leads and enrich them with data from external sources. Another tool can sync activity with email, trigger campaigns, or update product usage signals. Want to score deals, enrich contacts, or run outbound sequences? Add a tool that reads the files, writes updates, and you are done. No SDK hell, no brittle UI automation, no fighting someone else's data model. Just composable building blocks operating on shared state. The result is a system where adding new capabilities can be done with a tiny script, not negotiating with a platform.

This project is hosted [here](https://www.jsoncrm.dev)

---

## Installation

```bash
pip install jsoncrm
# or with web server support
pip install jsoncrm[web]
```

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

### CRUD
- `jsoncrm add --database_file leads.json --item_json '{...}'`
- `jsoncrm update --database_file leads.json --item_json '{...}'`
- `jsoncrm delete --database_file leads.json --item_json '{...}'`
- `jsoncrm find --database_file leads.json --item_json '{"company":"Acme"}'`

### Pipeline
- `jsoncrm promote <url> --lead` — Move lead → prospect
- `jsoncrm promote <url> --prospect` — Move prospect → customer
- `jsoncrm demote <url> --prospect` — Move prospect → lead
- `jsoncrm demote <url> --customer` — Move customer → prospect

### Data Quality
- `jsoncrm validate` — Validate all pipeline files for structural integrity
- `jsoncrm deduplicate intake.json` — Remove records already in pipeline
- `jsoncrm filter-competitors intake.json` — Remove competitor matches
- `jsoncrm merge scored.json` — Merge scored records into leads

### LinkedIn MCP
- `jsoncrm parse-from-linkedin-mcp likes.json` — Convert MCP output to CRM flat list
- `jsoncrm intake intake.json` — Pick next unscored record
- `jsoncrm apply_update` — Apply pending update file

### Web Server
- `jsoncrm serve` — Start the web UI on http://127.0.0.1:7341
- `jsoncrm serve --port 8080 --github-token $TOKEN --repo owner/repo`

All commands support `--config path/to/.crm.json` for custom configs.

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
- Use the CLI as tools (MCP server compatible)
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

# Install in editable mode
pip install -e .
pip install -e ".[web]"
```

## License

This project is licensed under the GNU Affero General Public License v3.0 only.

Commercial licensing is available for organizations that want to use this software
without the obligations of the AGPL. Contact: info@pauling.ai

## Copyright

Copyright (C) 2026 Pauling.AI
