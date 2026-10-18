"""Model Context Protocol server for jsoncrm."""

import argparse
import json
import subprocess
import sys
from pathlib import Path

from jsoncrm.schema import JSON_DB_ENCODING
from jsoncrm.tool import build_parser

EXCLUDED_COMMANDS = frozenset({"serve", "mcp"})


def _canonical_command_parsers():
    parser = build_parser()
    subparsers = next(
        action for action in parser._actions
        if isinstance(action, argparse._SubParsersAction)
    )
    commands = {}
    seen = set()
    for name, command_parser in subparsers.choices.items():
        if id(command_parser) in seen:
            continue
        seen.add(id(command_parser))
        commands[name] = command_parser
    return commands


COMMAND_PARSERS = _canonical_command_parsers()


def _build_cli_args(command, values):
    positionals = []
    options = []
    for action in COMMAND_PARSERS[command]._actions:
        if action.dest in ("help", "json"):
            continue
        value = values.get(action.dest)
        if action.option_strings:
            flag = next(
                (option for option in action.option_strings if option.startswith("--")),
                action.option_strings[0],
            )
            if action.nargs == 0:
                if value != action.default:
                    options.append(flag)
                continue
            if value is None:
                continue
            options.append(flag)
            if isinstance(value, dict):
                options.append(json.dumps(value, ensure_ascii=False))
            elif isinstance(value, (list, tuple)):
                options.extend(str(item) for item in value)
            else:
                options.append(str(value))
        else:
            if value is None:
                continue
            if isinstance(value, (list, tuple)):
                positionals.extend(str(item) for item in value)
            else:
                positionals.append(str(value))
    return [command, *positionals, *options, "--json"]


def _run_command(command, config_path=None, **values):
    argv = [sys.executable, "-m", "jsoncrm"]
    if config_path:
        argv.extend(["--config", config_path])
    argv.extend(_build_cli_args(command, values))
    result = subprocess.run(
        argv,
        capture_output=True,
        text=True,
        encoding=JSON_DB_ENCODING,
        check=False,
    )
    stdout = result.stdout.strip()
    stderr = result.stderr.strip()
    if result.returncode:
        message = "\n".join(part for part in (stdout, stderr) if part)
        raise RuntimeError(message or f"jsoncrm {command} exited with status {result.returncode}")
    try:
        data = json.loads(stdout)
    except json.JSONDecodeError:
        return {"output": stdout}
    return data if isinstance(data, dict) else {"result": data}


def create_server(config_path=None):
    try:
        from mcp.server.fastmcp import FastMCP
    except ImportError as exc:
        raise SystemExit("MCP support requires: pip install 'jsoncrm[mcp]'") from exc

    if config_path:
        config_path = str(Path(config_path).resolve())

    server = FastMCP(
        "jsoncrm",
        instructions="Inspect and modify the configured git-tracked JSON CRM.",
    )

    @server.tool()
    def search(query: str, person: bool = False, company: bool = False, competitor: bool = False):
        """Search the CRM pipeline by name, company, LinkedIn URL, or email."""
        return _run_command(
            "search", config_path, query=query, person=person, company=company, competitor=competitor,
        )

    @server.tool()
    def find(
        database_file: str,
        item_file: str | None = None,
        item_json: dict | str | None = None,
        output_file: str | None = None,
    ):
        """Find exact field matches in a CRM JSON file."""
        return _run_command(
            "find", config_path, database_file=database_file, item_file=item_file,
            item_json=item_json, output_file=output_file,
        )

    @server.tool()
    def add(
        database_file: str,
        item_file: str | None = None,
        item_json: dict | str | None = None,
        output_file: str | None = None,
    ):
        """Add one record to a CRM JSON file."""
        return _run_command(
            "add", config_path, database_file=database_file, item_file=item_file,
            item_json=item_json, output_file=output_file,
        )

    @server.tool()
    def update(
        database_file: str,
        item_file: str | None = None,
        item_json: dict | str | None = None,
        output_file: str | None = None,
    ):
        """Update one record identified by id or linkedin_url."""
        return _run_command(
            "update", config_path, database_file=database_file, item_file=item_file,
            item_json=item_json, output_file=output_file,
        )

    @server.tool()
    def delete(
        database_file: str,
        item_file: str | None = None,
        item_json: dict | str | None = None,
        output_file: str | None = None,
    ):
        """Delete one record identified by id or linkedin_url."""
        return _run_command(
            "delete", config_path, database_file=database_file, item_file=item_file,
            item_json=item_json, output_file=output_file,
        )

    @server.tool()
    def apply_update(pending_file: str = "default"):
        """Apply updates from a pending update file."""
        return _run_command("apply_update", config_path, pending_file=pending_file)

    @server.tool()
    def intake(file: str, output: str | None = None):
        """Pick the next unscored record from an intake file."""
        return _run_command("intake", config_path, file=file, output=output)

    @server.tool(name="parse-from-linkedin-mcp")
    def parse_from_linkedin_mcp(files: list[str]):
        """Convert LinkedIn MCP output files to CRM flat lists in place."""
        return _run_command("parse-from-linkedin-mcp", config_path, files=files)

    @server.tool()
    def shuffle(file: str, seed: int | None = None, dry_run: bool = False):
        """Shuffle records in a JSON array file."""
        return _run_command("shuffle", config_path, file=file, seed=seed, dry_run=dry_run)

    @server.tool()
    def top(
        num: int = 1,
        min_score: str | None = None,
        include_contacted: bool = False,
        include_disqualified: bool = False,
        output: str | None = None,
        file: str | None = None,
    ):
        """Return top-scored actionable leads."""
        return _run_command(
            "top", config_path, num=num, min_score=min_score,
            include_contacted=include_contacted, include_disqualified=include_disqualified,
            output=output, file=file,
        )

    @server.tool()
    def merge(file: str, dry_run: bool = False, leads_file: str | None = None):
        """Merge scored records from a source file into leads."""
        return _run_command("merge", config_path, file=file, dry_run=dry_run, leads_file=leads_file)

    @server.tool()
    def deduplicate(
        file: str,
        dry_run: bool = False,
        leads_file: str | None = None,
        prospects_file: str | None = None,
        customers_file: str | None = None,
    ):
        """Remove records whose LinkedIn URLs already exist in the pipeline."""
        return _run_command(
            "deduplicate", config_path, file=file, dry_run=dry_run, leads_file=leads_file,
            prospects_file=prospects_file, customers_file=customers_file,
        )

    @server.tool(name="filter-competitors")
    def filter_competitors(file: str, dry_run: bool = False):
        """Remove records matching the configured competitor watchlist."""
        return _run_command("filter-competitors", config_path, file=file, dry_run=dry_run)

    @server.tool()
    def promote(
        identity_value: str,
        identity_field: str | None = None,
        lead: bool = False,
        prospect: bool = False,
        from_file: str | None = None,
        to_file: str | None = None,
    ):
        """Move a lead or prospect to the next configured pipeline stage."""
        return _run_command(
            "promote", config_path, identity_value=identity_value, identity_field=identity_field,
            lead=lead, prospect=prospect, from_file=from_file, to_file=to_file,
        )

    @server.tool()
    def stats(
        leads_file: str | None = None,
        prospects_file: str | None = None,
        customers_file: str | None = None,
    ):
        """Show pipeline statistics."""
        return _run_command(
            "stats", config_path, leads_file=leads_file,
            prospects_file=prospects_file, customers_file=customers_file,
        )

    @server.tool()
    def validate(
        leads_file: str | None = None,
        prospects_file: str | None = None,
        customers_file: str | None = None,
    ):
        """Validate pipeline JSON files for structural integrity."""
        return _run_command(
            "validate", config_path, leads_file=leads_file,
            prospects_file=prospects_file, customers_file=customers_file,
        )

    @server.tool()
    def recent(
        num: int = 10,
        stage: str | None = None,
        leads_file: str | None = None,
        prospects_file: str | None = None,
        customers_file: str | None = None,
    ):
        """Show the most recently added pipeline records."""
        return _run_command(
            "recent", config_path, num=num, stage=stage, leads_file=leads_file,
            prospects_file=prospects_file, customers_file=customers_file,
        )

    @server.tool()
    def demote(
        identity_value: str,
        identity_field: str | None = None,
        customer: bool = False,
        prospect: bool = False,
        from_file: str | None = None,
        to_file: str | None = None,
    ):
        """Move a prospect or customer back one pipeline stage."""
        return _run_command(
            "demote", config_path, identity_value=identity_value, identity_field=identity_field,
            customer=customer, prospect=prospect, from_file=from_file, to_file=to_file,
        )

    @server.tool(name="list")
    def list_records(
        stage: str,
        score: str | None = None,
        company: str | None = None,
        query: str | None = None,
        limit: int | None = None,
        file: str | None = None,
    ):
        """List and filter records in a pipeline stage."""
        return _run_command(
            "list", config_path, stage=stage, score=score, company=company,
            query=query, limit=limit, file=file,
        )

    @server.tool()
    def dump_emails(out: str | None = None):
        """Dump all unique pipeline email addresses, comma separated."""
        return _run_command("dump_emails", config_path, out=out)

    return server


def run_mcp(config_path=None):
    create_server(config_path=config_path).run(transport="stdio")
