"""Schema, constants, and configuration defaults for jsoncrm."""

from pathlib import Path

# Default to current working directory. Callers (or a shim) can override
# CRM_DIR before importing other names if they need a different base path.
CRM_DIR = Path(".")
LEADS_FILE = CRM_DIR / "leads.json"
PROSPECTS_FILE = CRM_DIR / "prospects.json"
CUSTOMERS_FILE = CRM_DIR / "customers.json"
PIPELINE_FILES = [
    ("leads", LEADS_FILE),
    ("prospects", PROSPECTS_FILE),
    ("customers", CUSTOMERS_FILE),
]
COMPETITORS_FILE = CRM_DIR / "competitors.json"
ACTIVE_COMPETITOR_COMPANY_KEYS = ("companies",)
ACTIVE_COMPETITOR_PERSON_KEYS = ("people",)
SKIPPED_COMPETITOR_COMPANY_KEYS = ("skipped_companies",)
SKIPPED_COMPETITOR_PERSON_KEYS = ("skipped_people",)
COMPETITOR_COMPANY_KEYS = ACTIVE_COMPETITOR_COMPANY_KEYS + SKIPPED_COMPETITOR_COMPANY_KEYS
COMPETITOR_PERSON_KEYS = ACTIVE_COMPETITOR_PERSON_KEYS + SKIPPED_COMPETITOR_PERSON_KEYS

PENDING_FILE = CRM_DIR / ".pending_update.json"

SCORE_ORDER = {
    "⭐⭐⭐⭐⭐": 5,
    "⭐⭐⭐⭐": 4,
    "⭐⭐⭐": 3,
    "⭐⭐": 2,
    "⭐": 1,
}


def score_value(s):
    return SCORE_ORDER.get(s or "", 0)


def apply_config(config):
    """Rebind module-level constants from a loaded Config object.

    This is called by the CLI entry point after loading ``.crm.json``
    so that the rest of the codebase uses config-driven paths and scores.
    """
    global LEADS_FILE, PROSPECTS_FILE, CUSTOMERS_FILE, PIPELINE_FILES
    global COMPETITORS_FILE, PENDING_FILE, SCORE_ORDER

    stages = config.pipeline_stages
    stage_files = {}
    for stage in stages:
        stage_files[stage["name"]] = CRM_DIR / stage["file"]

    # Rebuild PIPELINE_FILES from config
    PIPELINE_FILES = [(s["name"], stage_files[s["name"]]) for s in stages]

    # Individual stage files (backward-compat aliases)
    LEADS_FILE = stage_files.get("leads", CRM_DIR / "leads.json")
    PROSPECTS_FILE = stage_files.get("prospects", CRM_DIR / "prospects.json")
    CUSTOMERS_FILE = stage_files.get("customers", CRM_DIR / "customers.json")

    # Blocklist / competitors
    COMPETITORS_FILE = CRM_DIR / config.blocklist_file

    # Scores
    SCORE_ORDER = config.score_order

    # Pending file stays in CRM_DIR (domain-agnostic)
    PENDING_FILE = CRM_DIR / ".pending_update.json"
