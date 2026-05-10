"""Configuration loader for jsoncrm.

Supports `.crm.json` in the working directory or an explicit ``--config`` path.
Falls back to built-in marketing-CRM defaults when no config is found.
"""

import json
from pathlib import Path

DEFAULT_MARKETING_CONFIG = {
    "name": "marketing-crm",
    "pipeline": {
        "stages": [
            {"name": "leads", "file": "leads.json"},
            {"name": "prospects", "file": "prospects.json"},
            {"name": "customers", "file": "customers.json"},
        ],
        "transitions": {
            "leads": ["prospects"],
            "prospects": ["customers"],
        },
    },
    "identity": {
        "primary": "linkedin_url",
        "fallback": ["id"],
    },
    "scores": {
        "order": ["⭐", "⭐⭐", "⭐⭐⭐", "⭐⭐⭐⭐", "⭐⭐⭐⭐⭐"],
        "disqualified": "❌",
    },
    "blocklist": {
        "file": "competitors.json",
        "match_fields": ["company", "name"],
    },
}


def _deep_merge(base, override):
    """Recursively merge *override* into *base*."""
    result = {}
    for key, value in base.items():
        if key in override:
            if isinstance(value, dict) and isinstance(override[key], dict):
                result[key] = _deep_merge(value, override[key])
            else:
                result[key] = override[key]
        else:
            result[key] = value
    # Add keys that exist only in override
    for key, value in override.items():
        if key not in base:
            result[key] = value
    return result


class Config:
    """Domain-agnostic CRM configuration."""

    def __init__(self, data):
        self._data = data

    @classmethod
    def from_file(cls, path=None):
        """Load config from *path* or fall back to ``.crm.json`` in cwd."""
        if path is not None:
            config_path = Path(path)
        else:
            config_path = Path(".crm.json")

        if config_path.exists():
            with open(config_path, encoding="utf-8") as f:
                override = json.load(f)
            return cls(_deep_merge(DEFAULT_MARKETING_CONFIG, override))
        return cls(_deep_merge(DEFAULT_MARKETING_CONFIG, {}))

    # --- pipeline ---

    @property
    def pipeline_stages(self):
        return self._data["pipeline"]["stages"]

    @property
    def pipeline_transitions(self):
        return self._data["pipeline"].get("transitions", {})

    # --- identity ---

    @property
    def identity_primary(self):
        return self._data["identity"]["primary"]

    @property
    def identity_fallback(self):
        return self._data["identity"].get("fallback", [])

    # --- scores ---

    @property
    def score_order(self):
        order = self._data["scores"]["order"]
        return {s: i + 1 for i, s in enumerate(order)}

    @property
    def score_order_descending(self):
        order = self._data["scores"]["order"]
        return list(reversed(order))

    @property
    def disqualified_score(self):
        return self._data["scores"].get("disqualified")

    # --- blocklist ---

    @property
    def blocklist_file(self):
        return self._data["blocklist"]["file"]

    @property
    def blocklist_match_fields(self):
        return self._data["blocklist"].get("match_fields", ["company", "name"])
