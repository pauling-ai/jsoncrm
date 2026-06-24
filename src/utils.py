"""Utility functions for jsoncrm."""

import json
import os
import re
import sys
import unicodedata
from pathlib import Path

from jsoncrm.schema import (
    COMPETITOR_COMPANY_KEYS,
    COMPETITOR_PERSON_KEYS,
    JSON_DB_ENCODING,
)


def load_json(path):
    if path.exists():
        return json.loads(path.read_text(encoding=JSON_DB_ENCODING))
    return []


def atomic_write_json(path, data):
    """Write *data* to *path* atomically via a temp file + os.replace()."""
    import uuid
    path = Path(path)
    tmp = path.with_suffix(path.suffix + f".tmp-{uuid.uuid4().hex}")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding=JSON_DB_ENCODING)
    os.replace(tmp, path)


def build_known_urls(*, leads_file=None, prospects_file=None, customers_file=None):
    known_urls = set()
    if leads_file is None and prospects_file is None and customers_file is None:
        from jsoncrm.schema import PIPELINE_FILES
        pipeline_files = PIPELINE_FILES
    else:
        from jsoncrm.schema import LEADS_FILE, PROSPECTS_FILE, CUSTOMERS_FILE
        pipeline_files = [
            ("leads", Path(leads_file) if leads_file else LEADS_FILE),
            ("prospects", Path(prospects_file) if prospects_file else PROSPECTS_FILE),
            ("customers", Path(customers_file) if customers_file else CUSTOMERS_FILE),
        ]
    for _, path in pipeline_files:
        for record in load_json(path):
            url = normalize_url(record.get("linkedin_url"))
            if url:
                known_urls.add(url)
    return known_urls


def normalize_company_name(name):
    folded = unicodedata.normalize("NFKD", name or "").encode("ascii", "ignore").decode("ascii")
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", folded.lower())).strip()


def record_identity_value(item):
    if item.get("id"):
        return "id", item.get("id")
    if item.get("linkedin_url"):
        return "linkedin_url", item.get("linkedin_url")
    return None, None


def match(record, query, person=False, company=False):
    q = query.lower()
    if person:
        return (
            q in (record.get("name") or "").lower()
            or q in (record.get("linkedin_url") or "").lower()
            or q in (record.get("email") or "").lower()
        )
    if company:
        return q in (record.get("company") or "").lower()
    return (
        q in (record.get("name") or "").lower()
        or q in (record.get("company") or "").lower()
        or q in (record.get("linkedin_url") or "").lower()
        or q in (record.get("email") or "").lower()
    )


def print_record(stage, record):
    print(f"  [{stage.upper()}]  {record.get('name')}  —  {record.get('position')}  @  {record.get('company')}")
    print(f"           {record.get('linkedin_url')}")
    score = record.get("score") or "—"
    connected = "connected" if record.get("connected") else "not connected"
    print(f"           score: {score}  |  {connected}  |  added: {record.get('added')}")
    if record.get("notes"):
        print(f"           notes: {record['notes']}")
    print()


def iter_competitor_entries(data, keys):
    for key in keys:
        for entry in data.get(key, []):
            if isinstance(entry, dict):
                yield entry


def search_competitors(query, person=False, company=False):
    from jsoncrm.schema import COMPETITORS_FILE
    if not COMPETITORS_FILE.exists():
        return []
    data = json.loads(COMPETITORS_FILE.read_text(encoding=JSON_DB_ENCODING))
    q = query.lower()
    q_norm = normalize_company_name(query)
    hits = []
    if not person:
        for c in iter_competitor_entries(data, COMPETITOR_COMPANY_KEYS):
            if q_norm in normalize_company_name(c.get("name")) or q in (c.get("url") or "").lower():
                hits.append(("company", c))
    if not company:
        for p in iter_competitor_entries(data, COMPETITOR_PERSON_KEYS):
            if q in (p.get("name") or "").lower() or q in (p.get("url") or "").lower():
                hits.append(("person", p))
    return hits


def normalize_url(url):
    return (url or "").rstrip("/").lower()


def find_record(target_url, target_file=None):
    norm = normalize_url(target_url)
    matches = []
    if target_file:
        paths = [Path(target_file)]
    else:
        # Search configured pipeline files instead of globbing all *.json
        from jsoncrm.schema import PIPELINE_FILES
        paths = [path for _, path in PIPELINE_FILES]
    for path in paths:
        try:
            data = json.loads(path.read_text(encoding=JSON_DB_ENCODING))
        except Exception:
            continue
        if not isinstance(data, list):
            continue
        for i, record in enumerate(data):
            if normalize_url(record.get("linkedin_url", "")) == norm:
                matches.append((path, data, i, record))
    return matches


def apply_updates(target_url, updates, target_file=None):
    matches = find_record(target_url, target_file=target_file)
    if not matches:
        print(f"Error: no record found for URL '{target_url}'")
        sys.exit(1)
    if len(matches) > 1:
        files = ", ".join(str(m[0].name) for m in matches)
        print(f"Error: found in multiple files ({files}) — use --file to target one")
        sys.exit(1)

    for path, data, idx, record in matches:
        record.update(updates)
        atomic_write_json(path, data)
        name = record.get("name", target_url)
        changed = ", ".join(f"{k}={v!r}" for k, v in updates.items())
        print(f"Saved: {name}  [{path.name}]  —  {changed}")


def coerce(value):
    if isinstance(value, str):
        if value.lower() == "true":
            return True
        if value.lower() == "false":
            return False
        if value.lower() in ("null", "none"):
            return None
        try:
            return int(value)
        except ValueError:
            pass
    return value
