# Contributing to JSONCRM

Thanks for your interest in contributing! JSONCRM is a git-tracked, JSON-file CRM built for AI agents, and there's plenty to help with: bug reports, new CLI/MCP features, web UI improvements, docs, and comparison-page corrections.

## Development setup

```bash
# Clone and install in editable mode with all extras
pip install -e ".[dev,web,mcp]"

# Or with uv
uv sync --extra dev --extra web --extra mcp

# Run the Python tests
pytest tests/
# or
uv run --extra dev --extra web pytest tests/

# JavaScript tests (optional)
npm install
npm test
```

## Submitting changes

1. Open an issue first for anything non-trivial, so we can agree on the approach.
2. Fork, branch, and keep PRs small and focused.
3. Add or update tests for anything that changes behavior — the integration suite (`tests/test_integration.py`) is the pattern to follow.
4. Make sure `pytest tests/` passes before submitting.

## License and copyright

JSONCRM is licensed under **AGPL-3.0-only**, with commercial licensing available from Pauling.AI. To keep both licensing paths viable, the project needs clear rights over contributions. By submitting a pull request, you agree to:

- **Inbound licensing:** Your contribution is licensed to the project under AGPL-3.0-only.
- **Sublicense grant:** You grant Pauling.AI a perpetual, worldwide, non-exclusive, royalty-free, irrevocable right to use, reproduce, modify, and sublicense your contribution, including as part of its commercial licensing program. You retain copyright of your contribution.
- **Origin certification:** Your contribution is your original work (or you have the right to submit it), and it contains no code from incompatible licenses. Add a `Signed-off-by:` line to your commits (`git commit -s`) to certify this.

If any of this is a problem for you or your employer, open an issue before submitting and we'll figure it out.

## Questions

- Bug reports and feature requests: [GitHub Issues](https://github.com/pauling-ai/jsoncrm/issues)
- Copyright (C) 2026 Pauling.AI
