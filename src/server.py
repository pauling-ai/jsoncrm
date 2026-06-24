"""FastAPI web server for jsoncrm — spreadsheet UI + optional GitHub PR writes."""

from __future__ import annotations

import base64
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import jsoncrm.schema as schema
from jsoncrm.config import Config
from jsoncrm.schema import PIPELINE_FILES, COMPETITORS_FILE, PENDING_FILE, SCORE_ORDER, JSON_DB_ENCODING
from jsoncrm.utils import (
    atomic_write_json,
    build_known_urls,
    load_json,
    normalize_company_name,
    normalize_url,
    record_identity_value,
)

# ---------------------------------------------------------------------------
# Config (injected at startup)
# ---------------------------------------------------------------------------

SERVER_CONFIG: dict[str, Any] = {
    "crm_dir": Path("."),
    "github_token": None,
    "repo": None,
    "base_branch": "main",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _stage_path(stage: str) -> Path:
    for name, path in schema.PIPELINE_FILES:
        if name == stage:
            return path
    raise HTTPException(status_code=404, detail=f"Unknown stage '{stage}'")


def _infer_schema(rows: list[dict]) -> dict[str, str]:
    keys: dict[str, set[str]] = {}
    for row in rows[:50]:
        for k, v in row.items():
            keys.setdefault(k, set())
            keys[k].add(type(v).__name__)
    return {k: list(v)[0] if len(v) == 1 else "mixed" for k, v in keys.items()}


def _gh_headers() -> dict[str, str]:
    token = SERVER_CONFIG["github_token"]
    if not token:
        raise HTTPException(status_code=400, detail="GitHub token not configured")
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class AddRecordRequest(BaseModel):
    record: dict[str, Any]


class UpdateRecordRequest(BaseModel):
    updates: dict[str, Any]


class DeleteRecordRequest(BaseModel):
    identity: dict[str, Any]


class PromoteRequest(BaseModel):
    linkedin_url: str


class PRRequest(BaseModel):
    title: str = ""
    body: str = ""


# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------


def create_app(
    *,
    config_path: str | None = None,
    github_token: str | None = None,
    repo: str | None = None,
    base_branch: str = "main",
) -> FastAPI:
    app = FastAPI(title="jsoncrm")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Load config and rebind schema
    cfg = Config.from_file(config_path)
    if config_path:
        schema.CRM_DIR = Path(config_path).resolve().parent
    schema.apply_config(cfg)
    SERVER_CONFIG["crm_dir"] = schema.CRM_DIR
    SERVER_CONFIG["github_token"] = github_token
    SERVER_CONFIG["repo"] = repo
    SERVER_CONFIG["base_branch"] = base_branch

    # -------------------------------------------------------------------
    # Routes
    # -------------------------------------------------------------------

    # Resolve static files directory
    static_dir = Path(__file__).parent / "web"
    if not static_dir.exists():
        try:
            import importlib.resources
            static_dir = importlib.resources.files("jsoncrm") / "web"
        except Exception:
            static_dir = None

    if static_dir and Path(str(static_dir)).exists():
        app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    @app.get("/")
    def ui():
        if static_dir and Path(str(static_dir)).exists():
            return FileResponse(str(Path(str(static_dir)) / "index.html"))
        raise HTTPException(status_code=500, detail="UI files not found")

    @app.get("/api/config")
    def get_config() -> dict:
        cfg_obj = Config.from_file(config_path)
        stages = [{"name": s["name"], "file": str(schema.CRM_DIR / s["file"])} for s in cfg_obj.pipeline_stages]
        return {
            "crm_dir": str(schema.CRM_DIR),
            "stages": stages,
            "scores": {
                "order": list(cfg_obj.score_order.keys()),
                "disqualified": cfg_obj.disqualified_score,
            },
            "identity": {
                "primary": cfg_obj.identity_primary,
                "fallback": cfg_obj.identity_fallback,
            },
            "github_configured": bool(github_token and repo),
        }

    @app.get("/api/data/{stage}")
    def get_data(
        stage: str,
        limit: int = 100,
        offset: int = 0,
        q: str = "",
        sort_key: str = "",
        sort_dir: str = "asc",
    ) -> dict:
        path = _stage_path(stage)
        rows = load_json(path)
        total = len(rows)

        # Filter
        if q:
            from jsoncrm.utils import match
            rows = [r for r in rows if match(r, q)]

        # Sort
        if sort_key:
            def _sort_key(r):
                v = r.get(sort_key)
                if v is None:
                    return (1, "")  # nulls last
                return (0, v)
            rows = sorted(rows, key=_sort_key, reverse=(sort_dir == "desc"))

        total_filtered = len(rows)
        rows = rows[offset : offset + limit]

        return {
            "stage": stage,
            "file": str(path),
            "rows": rows,
            "total": total,
            "total_filtered": total_filtered,
            "offset": offset,
            "limit": limit,
        }

    @app.get("/api/schema/{stage}")
    def get_schema(stage: str) -> dict:
        path = _stage_path(stage)
        rows = load_json(path)
        return {"stage": stage, "columns": _infer_schema(rows)}

    @app.post("/api/data/{stage}")
    def add_record(stage: str, req: AddRecordRequest) -> dict:
        path = _stage_path(stage)
        rows = load_json(path)
        if rows and not isinstance(rows, list):
            raise HTTPException(status_code=500, detail="File must be a JSON array")
        record = req.record

        # Duplicate guard on linkedin_url
        url = normalize_url(record.get("linkedin_url"))
        if url and url in build_known_urls():
            raise HTTPException(status_code=409, detail=f"Record with URL '{url}' already exists in pipeline")

        rows.append(record)
        atomic_write_json(path, rows)
        return {"ok": True, "stage": stage, "index": len(rows) - 1, "record": record}

    @app.patch("/api/data/{stage}")
    def update_record(stage: str, req: UpdateRecordRequest) -> dict:
        path = _stage_path(stage)
        rows = load_json(path)
        if not isinstance(rows, list):
            raise HTTPException(status_code=500, detail="File must be a JSON array")

        updates = req.updates
        identity_field, identity_value = record_identity_value(updates)
        if not identity_field:
            raise HTTPException(status_code=400, detail="Updates must contain an identity field (id or linkedin_url)")

        matched = False
        for r in rows:
            if r.get(identity_field) == identity_value:
                # Warn about unknown fields
                unknown = [k for k in updates if k not in r and k != identity_field]
                r.update(updates)
                matched = True
                break

        if not matched:
            raise HTTPException(status_code=404, detail=f"No record found for {identity_field} '{identity_value}'")

        atomic_write_json(path, rows)
        return {"ok": True, "stage": stage, "unknown_fields": unknown if matched else []}

    @app.delete("/api/data/{stage}")
    def delete_record(stage: str, req: DeleteRecordRequest) -> dict:
        path = _stage_path(stage)
        rows = load_json(path)
        if not isinstance(rows, list):
            raise HTTPException(status_code=500, detail="File must be a JSON array")

        identity_field, identity_value = record_identity_value(req.identity)
        if not identity_field:
            raise HTTPException(status_code=400, detail="Identity must contain id or linkedin_url")

        new_rows = [r for r in rows if r.get(identity_field) != identity_value]
        if len(new_rows) == len(rows):
            raise HTTPException(status_code=404, detail=f"No record found for {identity_field} '{identity_value}'")

        atomic_write_json(path, new_rows)
        return {"ok": True, "stage": stage, "deleted": 1, "remaining": len(new_rows)}

    @app.get("/api/competitors")
    def get_competitors() -> dict:
        if not schema.COMPETITORS_FILE.exists():
            return {"companies": [], "people": []}
        data = load_json(schema.COMPETITORS_FILE)
        if not isinstance(data, dict):
            return {"companies": [], "people": []}
        companies = [
            {"name": c.get("name"), "url": c.get("url")}
            for c in data.get("companies", []) + data.get("skipped_companies", [])
            if isinstance(c, dict)
        ]
        people = [
            {"name": p.get("name"), "url": p.get("url"), "company": p.get("company")}
            for p in data.get("people", []) + data.get("skipped_people", [])
            if isinstance(p, dict)
        ]
        return {"companies": companies, "people": people}

    @app.post("/api/promote")
    def promote_record(req: PromoteRequest) -> dict:
        from jsoncrm.tool import PROMOTE_MAP

        norm = normalize_url(req.linkedin_url)
        for stage_key, (src_name, dst_name) in PROMOTE_MAP.items():
            src_path = schema.CRM_DIR / src_name
            dst_path = schema.CRM_DIR / dst_name
            src_rows = load_json(src_path)
            dst_rows = load_json(dst_path)

            record = None
            remaining = []
            for r in src_rows:
                if normalize_url(r.get("linkedin_url", "")) == norm:
                    record = r
                else:
                    remaining.append(r)

            if record is not None:
                dst_rows.append(record)
                atomic_write_json(src_path, remaining)
                atomic_write_json(dst_path, dst_rows)
                return {
                    "ok": True,
                    "action": "promoted",
                    "from": src_name,
                    "to": dst_name,
                    "record": record,
                }

        raise HTTPException(status_code=404, detail=f"No record found for '{req.linkedin_url}'")

    @app.post("/api/demote")
    def demote_record(req: PromoteRequest) -> dict:
        from jsoncrm.tool import PROMOTE_MAP

        # Reverse the promote map
        reverse = {}
        for src_name, dst_name in PROMOTE_MAP.values():
            reverse[dst_name] = (dst_name, src_name)

        norm = normalize_url(req.linkedin_url)
        for src_name, dst_name in reverse.values():
            src_path = schema.CRM_DIR / src_name
            dst_path = schema.CRM_DIR / dst_name
            src_rows = load_json(src_path)
            dst_rows = load_json(dst_path)

            record = None
            remaining = []
            for r in src_rows:
                if normalize_url(r.get("linkedin_url", "")) == norm:
                    record = r
                else:
                    remaining.append(r)

            if record is not None:
                dst_rows.append(record)
                atomic_write_json(src_path, remaining)
                atomic_write_json(dst_path, dst_rows)
                return {
                    "ok": True,
                    "action": "demoted",
                    "from": src_name,
                    "to": dst_name,
                    "record": record,
                }

        raise HTTPException(status_code=404, detail=f"No record found for '{req.linkedin_url}'")

    @app.post("/api/pr")
    def create_pr(req: PRRequest) -> dict:
        token = SERVER_CONFIG["github_token"]
        repo = SERVER_CONFIG["repo"]
        base_branch = SERVER_CONFIG["base_branch"]
        if not token or not repo:
            raise HTTPException(status_code=400, detail="GitHub not configured")

        branch = f"jsoncrm-edit-{int(time.time())}"
        files_changed = []

        # Get base branch SHA
        ref_url = f"https://api.github.com/repos/{repo}/git/ref/heads/{base_branch}"
        r = httpx.get(ref_url, headers=_gh_headers())
        if r.status_code != 200:
            raise HTTPException(status_code=500, detail=f"Could not get base branch: {r.text}")
        base_sha = r.json()["object"]["sha"]

        # Create new branch
        r = httpx.post(
            f"https://api.github.com/repos/{repo}/git/refs",
            headers=_gh_headers(),
            json={"ref": f"refs/heads/{branch}", "sha": base_sha},
        )
        if r.status_code not in (200, 201):
            raise HTTPException(status_code=500, detail=f"Could not create branch: {r.text}")

        # Push each pipeline file
        for stage_name, path in schema.PIPELINE_FILES:
            if not path.exists():
                continue
            filename = path.name
            content = json.dumps(load_json(path), indent=2, ensure_ascii=False) + "\n"
            encoded = base64.b64encode(content.encode(JSON_DB_ENCODING)).decode()

            # Get file SHA on base branch
            file_url = f"https://api.github.com/repos/{repo}/contents/{filename}"
            r = httpx.get(file_url, headers=_gh_headers(), params={"ref": base_branch})
            file_sha = r.json().get("sha") if r.status_code == 200 else None

            payload = {
                "message": req.title or f"jsoncrm: update {filename} [{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M')} UTC]",
                "content": encoded,
                "branch": branch,
            }
            if file_sha:
                payload["sha"] = file_sha

            r = httpx.put(file_url, headers=_gh_headers(), json=payload)
            if r.status_code in (200, 201):
                files_changed.append(filename)

        # Open PR
        r = httpx.post(
            f"https://api.github.com/repos/{repo}/pulls",
            headers=_gh_headers(),
            json={
                "title": req.title or "Update CRM via jsoncrm",
                "body": req.body or f"Automated PR from jsoncrm serve.\n\n**Files changed:** {', '.join(files_changed)}",
                "head": branch,
                "base": base_branch,
            },
        )
        if r.status_code not in (200, 201):
            raise HTTPException(status_code=500, detail=f"Could not open PR: {r.text}")

        return {"pr_url": r.json()["html_url"], "branch": branch}

    return app


def run_server(
    port: int = 7341,
    config_path: str | None = None,
    github_token: str | None = None,
    repo: str | None = None,
    base_branch: str = "main",
) -> None:
    import uvicorn

    app = create_app(
        config_path=config_path,
        github_token=github_token,
        repo=repo,
        base_branch=base_branch,
    )
    print(f"\n  jsoncrm serve running at http://127.0.0.1:{port}")
    print(f"  CRM dir : {schema.CRM_DIR.resolve()}")
    print(f"  Repo    : {repo or '(not set — PR disabled)'}")
    print(f"  Branch  : {base_branch}\n")
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")
