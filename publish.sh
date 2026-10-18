#!/usr/bin/env bash
# Publish jsoncrm to PyPI.
# Auth comes from macOS Keychain; no secrets live in this repo.
#   one-time setup: security add-generic-password -s pypi -a jsoncrm -w
set -euo pipefail

if ! security find-generic-password -s pypi -a jsoncrm >/dev/null 2>&1; then
  echo "error: keychain item not found (service: 'pypi', account: 'jsoncrm')" >&2
  echo "create it with: security add-generic-password -s pypi -a jsoncrm -w" >&2
  exit 1
fi

# Fresh artifacts only — never upload a stale dist/.
rm -rf dist
uv build

uv publish --token "$(security find-generic-password -s pypi -a jsoncrm -w)"
