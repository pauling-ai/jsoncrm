"""Integration and parity tests for the MCP server."""

import argparse
import asyncio
import copy
import json
import subprocess
import sys
from pathlib import Path

import pytest

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from jsoncrm.mcp import EXCLUDED_COMMANDS
from jsoncrm.tool import build_parser

ALICE_URL = "https://www.linkedin.com/in/alice/"
BOB_URL = "https://www.linkedin.com/in/bob/"
ALICE = {
    "name": "Alice",
    "company": "Acme",
    "linkedin_url": ALICE_URL,
    "email": "alice@example.com",
    "score": "⭐⭐⭐⭐",
    "contacted_at": None,
    "next_follow_up": None,
    "added": "2026-01-01",
}
BOB = {
    "name": "Bob",
    "company": "BetaCo",
    "linkedin_url": BOB_URL,
    "email": "bob@example.com",
    "score": "⭐⭐⭐",
    "added": "2026-02-01",
}
BASE_FILES = {
    "leads.json": [ALICE],
    "prospects.json": [],
    "customers.json": [],
    "competitors.json": {"companies": [{"name": "Acme"}], "people": []},
}

CASES = [
    {
        "name": "search",
        "cli_args": ["Alice"],
        "mcp_args": {"query": "Alice"},
    },
    {
        "name": "find",
        "cli_args": ["--database_file", "$CRM/leads.json", "--item_json", '{"company":"Acme"}'],
        "mcp_args": {"database_file": "$CRM/leads.json", "item_json": '{"company":"Acme"}'},
    },
    {
        "name": "add",
        "cli_args": [
            "--database_file", "$CRM/prospects.json", "--item_json",
            '{"name":"Bob","company":"BetaCo","linkedin_url":"https://www.linkedin.com/in/bob/"}',
        ],
        "mcp_args": {
            "database_file": "$CRM/prospects.json",
            "item_json": '{"name":"Bob","company":"BetaCo","linkedin_url":"https://www.linkedin.com/in/bob/"}',
        },
    },
    {
        "name": "update",
        "cli_args": [
            "--database_file", "$CRM/leads.json", "--item_json",
            '{"linkedin_url":"https://www.linkedin.com/in/alice/","company":"UpdatedCo"}',
        ],
        "mcp_args": {
            "database_file": "$CRM/leads.json",
            "item_json": '{"linkedin_url":"https://www.linkedin.com/in/alice/","company":"UpdatedCo"}',
        },
    },
    {
        "name": "delete",
        "cli_args": [
            "--database_file", "$CRM/leads.json", "--item_json",
            '{"linkedin_url":"https://www.linkedin.com/in/alice/"}',
        ],
        "mcp_args": {
            "database_file": "$CRM/leads.json",
            "item_json": '{"linkedin_url":"https://www.linkedin.com/in/alice/"}',
        },
    },
    {
        "name": "apply_update",
        "files": {
            "pending.json": {
                "linkedin_url": ALICE_URL,
                "target_file": "$CRM/leads.json",
                "fields": {"notes": "Updated through MCP"},
            },
        },
        "cli_args": ["$CRM/pending.json"],
        "mcp_args": {"pending_file": "$CRM/pending.json"},
    },
    {
        "name": "intake",
        "files": {
            "intake.json": [{"name": "Unscored", "linkedin_url": "https://example.com/unscored"}],
        },
        "cli_args": ["$CRM/intake.json", "--output", "$CRM/pending.json"],
        "mcp_args": {"file": "$CRM/intake.json", "output": "$CRM/pending.json"},
    },
    {
        "name": "parse-from-linkedin-mcp",
        "files": {
            "linkedin.json": {
                "url": "https://linkedin.com/post/123",
                "likers": [{
                    "name": "Liker One\nView Liker One's profile\n· 2nd\nFounder at Startup",
                    "url": "https://www.linkedin.com/in/liker-one/",
                }],
            },
        },
        "cli_args": ["$CRM/linkedin.json"],
        "mcp_args": {"files": ["$CRM/linkedin.json"]},
    },
    {
        "name": "shuffle",
        "files": {"shuffle.json": [{"id": str(number)} for number in range(6)]},
        "cli_args": ["$CRM/shuffle.json", "--seed", "7"],
        "mcp_args": {"file": "$CRM/shuffle.json", "seed": 7},
    },
    {
        "name": "top",
        "cli_args": ["--file", "$CRM/leads.json"],
        "mcp_args": {"file": "$CRM/leads.json"},
    },
    {
        "name": "merge",
        "files": {"source.json": [BOB]},
        "cli_args": ["$CRM/source.json", "--leads-file", "$CRM/leads.json"],
        "mcp_args": {"file": "$CRM/source.json", "leads_file": "$CRM/leads.json"},
    },
    {
        "name": "deduplicate",
        "files": {"source.json": [ALICE, BOB]},
        "cli_args": [
            "$CRM/source.json",
            "--leads-file", "$CRM/leads.json",
            "--prospects-file", "$CRM/prospects.json",
            "--customers-file", "$CRM/customers.json",
        ],
        "mcp_args": {
            "file": "$CRM/source.json",
            "leads_file": "$CRM/leads.json",
            "prospects_file": "$CRM/prospects.json",
            "customers_file": "$CRM/customers.json",
        },
    },
    {
        "name": "filter-competitors",
        "files": {
            "source.json": [
                {"name": "Acme Rep", "company": "Acme", "linkedin_url": "https://example.com/acme"},
                {"name": "Fresh Lead", "company": "FreshCo", "linkedin_url": "https://example.com/fresh"},
            ],
        },
        "cli_args": ["$CRM/source.json"],
        "mcp_args": {"file": "$CRM/source.json"},
    },
    {
        "name": "promote",
        "cli_args": [
            ALICE_URL, "--lead",
            "--from-file", "$CRM/leads.json", "--to-file", "$CRM/prospects.json",
        ],
        "mcp_args": {
            "identity_value": ALICE_URL, "lead": True,
            "from_file": "$CRM/leads.json", "to_file": "$CRM/prospects.json",
        },
    },
    {
        "name": "stats",
        "cli_args": [],
        "mcp_args": {},
    },
    {
        "name": "validate",
        "cli_args": [],
        "mcp_args": {},
    },
    {
        "name": "recent",
        "files": {"prospects.json": [BOB]},
        "cli_args": ["--num", "1"],
        "mcp_args": {"num": 1},
    },
    {
        "name": "demote",
        "files": {"leads.json": [], "prospects.json": [ALICE]},
        "cli_args": [
            ALICE_URL, "--prospect",
            "--from-file", "$CRM/prospects.json", "--to-file", "$CRM/leads.json",
        ],
        "mcp_args": {
            "identity_value": ALICE_URL, "prospect": True,
            "from_file": "$CRM/prospects.json", "to_file": "$CRM/leads.json",
        },
    },
    {
        "name": "list",
        "cli_args": ["leads", "--company", "Acme"],
        "mcp_args": {"stage": "leads", "company": "Acme"},
    },
    {
        "name": "dump_emails",
        "cli_args": ["--out", "$CRM/emails.txt"],
        "mcp_args": {"out": "$CRM/emails.txt"},
    },
    {
        "name": "delete-not-found",
        "command": "delete",
        "cli_args": [
            "--database_file", "$CRM/leads.json", "--item_json",
            '{"linkedin_url":"https://www.linkedin.com/in/missing/"}',
        ],
        "mcp_args": {
            "database_file": "$CRM/leads.json",
            "item_json": '{"linkedin_url":"https://www.linkedin.com/in/missing/"}',
        },
    },
]


def _resolve(value, root):
    if isinstance(value, str):
        return value.replace("$CRM", str(root))
    if isinstance(value, list):
        return [_resolve(item, root) for item in value]
    if isinstance(value, dict):
        return {key: _resolve(item, root) for key, item in value.items()}
    return value


def _normalize(value, root):
    if isinstance(value, str):
        return value.replace(str(root), "$CRM")
    if isinstance(value, list):
        return [_normalize(item, root) for item in value]
    if isinstance(value, dict):
        return {key: _normalize(item, root) for key, item in value.items()}
    return value


def _write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _setup_crm(root, case):
    root.mkdir(parents=True)
    _write_json(root / ".crm.json", {"name": "mcp-parity-test"})
    files = copy.deepcopy(BASE_FILES)
    files.update(copy.deepcopy(case.get("files", {})))
    for name, data in files.items():
        _write_json(root / name, _resolve(data, root))


def _normalized_tree(root):
    tree = {}
    for path in sorted(root.rglob("*")):
        if path.is_file():
            relative = str(path.relative_to(root))
            tree[relative] = path.read_text(encoding="utf-8").replace(str(root), "$CRM")
    return tree


def _server_params(config_path, cwd):
    return StdioServerParameters(
        command=sys.executable,
        args=["-m", "jsoncrm", "--config", str(config_path), "mcp"],
        cwd=cwd,
    )


async def _list_tools(config_path, cwd):
    async with stdio_client(_server_params(config_path, cwd)) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            return (await session.list_tools()).tools


async def _call_tool(config_path, cwd, command, arguments):
    async with stdio_client(_server_params(config_path, cwd)) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            return await session.call_tool(command, arguments)


def _cli_command_parsers():
    parser = build_parser()
    subparsers = next(
        action for action in parser._actions
        if isinstance(action, argparse._SubParsersAction)
    )
    commands = {}
    seen = set()
    for name, command_parser in subparsers.choices.items():
        if id(command_parser) not in seen:
            commands[name] = command_parser
            seen.add(id(command_parser))
    return commands


def _cli_actions(command_parser):
    return {
        action.dest: action
        for action in command_parser._actions
        if action.dest not in ("help", "json")
    }


def _schema_types(prop):
    if "type" in prop:
        return {prop["type"]}
    return {
        option["type"]
        for option in prop.get("anyOf", [])
        if option.get("type") != "null"
    }


def _expected_schema_type(action):
    if action.nargs in ("+", "*"):
        return "array"
    if action.nargs == 0:
        return "boolean"
    if action.type is int:
        return "integer"
    return "string"


def _decoded_content(result):
    assert result.content
    return json.loads(result.content[0].text)


def _direct_cli(root, command, args):
    return subprocess.run(
        [
            sys.executable, "-m", "jsoncrm", "--config", str(root / ".crm.json"),
            command, *_resolve(args, root), "--json",
        ],
        cwd=root,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )


def test_mcp_registers_every_non_server_cli_command(tmp_path):
    config_path = tmp_path / ".crm.json"
    _write_json(config_path, {})
    tools = asyncio.run(_list_tools(config_path, tmp_path))
    cli_commands = set(_cli_command_parsers()) - EXCLUDED_COMMANDS
    assert {tool.name for tool in tools} == cli_commands


def test_mcp_schemas_match_cli_arguments(tmp_path):
    config_path = tmp_path / ".crm.json"
    _write_json(config_path, {})
    tools = {tool.name: tool for tool in asyncio.run(_list_tools(config_path, tmp_path))}

    for command, parser in _cli_command_parsers().items():
        if command in EXCLUDED_COMMANDS:
            continue
        expected_actions = _cli_actions(parser)
        schema = tools[command].inputSchema
        properties = schema["properties"]
        assert set(properties) == set(expected_actions), command
        assert set(schema.get("required", [])) == {
            dest for dest, action in expected_actions.items() if action.required
        }, command
        for dest, action in expected_actions.items():
            prop = properties[dest]
            expected_types = {_expected_schema_type(action)}
            if dest == "item_json":
                expected_types.add("object")
            assert _schema_types(prop) == expected_types, f"{command}.{dest}"
            assert prop.get("default") == action.default, f"{command}.{dest} default"


@pytest.mark.parametrize("case", CASES, ids=[case["name"] for case in CASES])
def test_mcp_command_matches_direct_cli(case, tmp_path):
    command = case.get("command", case["name"])
    mcp_root = tmp_path / "mcp"
    cli_root = tmp_path / "cli"
    _setup_crm(mcp_root, case)
    _setup_crm(cli_root, case)

    direct = _direct_cli(cli_root, command, case["cli_args"])
    result = asyncio.run(_call_tool(
        mcp_root / ".crm.json",
        mcp_root,
        command,
        _resolve(case["mcp_args"], mcp_root),
    ))

    assert result.isError == (direct.returncode != 0), case["name"]
    if result.isError:
        expected_error = (direct.stdout + direct.stderr).strip().replace(str(cli_root), "$CRM")
        actual_error = result.content[0].text.replace(str(mcp_root), "$CRM")
        assert expected_error in actual_error
    else:
        actual = _normalize(_decoded_content(result), mcp_root)
        try:
            expected = json.loads(direct.stdout.strip())
            if not isinstance(expected, dict):
                expected = {"result": expected}
        except json.JSONDecodeError:
            expected = {"output": direct.stdout.strip()}
        assert actual == _normalize(expected, cli_root)

    assert _normalized_tree(mcp_root) == _normalized_tree(cli_root)


def test_mcp_uses_custom_config_paths(tmp_path):
    root = tmp_path / "custom"
    root.mkdir()
    config = {
        "pipeline": {
            "stages": [
                {"name": "leads", "file": "custom-leads.json"},
                {"name": "prospects", "file": "custom-prospects.json"},
                {"name": "customers", "file": "custom-customers.json"},
            ],
            "transitions": {"leads": ["prospects"], "prospects": ["customers"]},
        },
    }
    _write_json(root / ".crm.json", config)
    _write_json(root / "custom-leads.json", [{**ALICE, "name": "Custom Config Alice"}])
    _write_json(root / "custom-prospects.json", [])
    _write_json(root / "custom-customers.json", [])

    result = asyncio.run(_call_tool(root / ".crm.json", root, "stats", {}))
    assert not result.isError
    assert _decoded_content(result)["leads"]["total"] == 1

    result = asyncio.run(_call_tool(root / ".crm.json", root, "search", {"query": "Custom Config"}))
    assert not result.isError
    assert _decoded_content(result)["results"][0]["name"] == "Custom Config Alice"
