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

from jsoncrm.context import CRMContext
from jsoncrm.schema import JSON_DB_ENCODING
from jsoncrm.invariants import (
    DuplicateRecordError,
    RecordError,
    RecordNotFoundError,
    identity_matches,
)
from jsoncrm.tool import add_record, delete_record, move_record, update_record
from jsoncrm.utils import load_json

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _infer_schema(rows: list[dict]) -> dict[str, str]:
    keys: dict[str, set[str]] = {}
    for row in rows[:50]:
        for k, v in row.items():
            keys.setdefault(k, set())
            keys[k].add(type(v).__name__)
    return {k: list(v)[0] if len(v) == 1 else "mixed" for k, v in keys.items()}


def _gh_headers(token) -> dict[str, str]:
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


class MoveRequest(BaseModel):
    identity: dict[str, Any]
    from_stage: str
    to_stage: str
    allow_reverse: bool = False


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

    context = CRMContext.from_file(config_path)
    app.state.crm_context = context
    cfg = context.config
    fields = context.identity_fields

    def stage_path(stage):
        try:
            return context.stage_path(stage)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=f"Unknown stage '{stage}'") from exc

    def other_records(*excluded):
        return context.other_records(*excluded)

    def raise_record_error(exc):
        if isinstance(exc, RecordNotFoundError):
            status = 404
        elif isinstance(exc, DuplicateRecordError):
            status = 409
        else:
            status = 400
        raise HTTPException(status_code=status, detail=str(exc)) from exc

    def configured_move(identity_field, identity_value, source_name, destination_name, action):
        source_stage = context.stage_for_name(source_name)
        destination_stage = context.stage_for_name(destination_name)
        if not source_stage or not destination_stage:
            raise HTTPException(status_code=404, detail="Unknown source or destination stage")
        source_path = stage_path(source_name)
        destination_path = stage_path(destination_name)
        try:
            source_rows, destination_rows, record = move_record(
                load_json(source_path),
                load_json(destination_path),
                identity_field=identity_field,
                identity_value=identity_value,
                source_stage=source_stage,
                destination_stage=destination_stage,
                fields=fields,
                transition_map=cfg.transition_map(source_name, destination_name),
                existing_records=other_records(source_path, destination_path),
            )
        except RecordError as exc:
            raise_record_error(exc)
        context.write_json(destination_path, destination_rows)
        context.write_json(source_path, source_rows)
        return {
            "ok": True,
            "action": action,
            "from": source_name,
            "to": destination_name,
            "record": record,
        }

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
        cfg_obj = context.config
        stages = [{"name": s["name"], "file": str(context.root / s["file"])} for s in cfg_obj.pipeline_stages]
        return {
            "crm_dir": str(context.root),
            "stages": stages,
            "transitions": cfg_obj.pipeline_transitions,
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
        path = stage_path(stage)
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
        path = stage_path(stage)
        rows = load_json(path)
        return {"stage": stage, "columns": _infer_schema(rows)}

    @app.post("/api/data/{stage}")
    def add_record_route(stage: str, req: AddRecordRequest) -> dict:
        path = stage_path(stage)
        rows = load_json(path)
        if not isinstance(rows, list):
            raise HTTPException(status_code=500, detail="File must be a JSON array")
        try:
            rows, record = add_record(
                rows,
                req.record,
                stage=context.stage_for_name(stage),
                fields=fields,
                existing_records=other_records(path),
            )
        except RecordError as exc:
            raise_record_error(exc)
        context.write_json(path, rows)
        return {"ok": True, "stage": stage, "index": rows.index(record), "record": record}

    @app.patch("/api/data/{stage}")
    def update_record_route(stage: str, req: UpdateRecordRequest) -> dict:
        path = stage_path(stage)
        rows = load_json(path)
        if not isinstance(rows, list):
            raise HTTPException(status_code=500, detail="File must be a JSON array")
        try:
            rows, _record, unknown = update_record(
                rows,
                req.updates,
                stage=context.stage_for_name(stage),
                fields=fields,
                existing_records=other_records(path),
            )
        except RecordError as exc:
            raise_record_error(exc)
        context.write_json(path, rows)
        return {"ok": True, "stage": stage, "unknown_fields": unknown}

    @app.delete("/api/data/{stage}")
    def delete_record_route(stage: str, req: DeleteRecordRequest) -> dict:
        path = stage_path(stage)
        rows = load_json(path)
        if not isinstance(rows, list):
            raise HTTPException(status_code=500, detail="File must be a JSON array")
        try:
            new_rows, _record = delete_record(rows, req.identity, fields=fields)
        except RecordError as exc:
            raise_record_error(exc)
        context.write_json(path, new_rows)
        return {"ok": True, "stage": stage, "deleted": 1, "remaining": len(new_rows)}

    @app.get("/api/competitors")
    def get_competitors() -> dict:
        if not context.competitors_file.exists():
            return {"companies": [], "people": []}
        data = load_json(context.competitors_file)
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

    @app.post("/api/move")
    def move_record_route(req: MoveRequest) -> dict:
        identity_field = next(
            (field for field in fields if req.identity.get(field) not in (None, "")),
            None,
        )
        if not identity_field:
            raise HTTPException(status_code=400, detail=f"Identity must contain one of {fields}")
        forward = req.to_stage in cfg.pipeline_transitions.get(req.from_stage, [])
        reverse = req.from_stage in cfg.pipeline_transitions.get(req.to_stage, [])
        if not forward and not (req.allow_reverse and reverse):
            raise HTTPException(
                status_code=400,
                detail=f"Transition '{req.from_stage}->{req.to_stage}' is not configured",
            )
        return configured_move(
            identity_field,
            req.identity[identity_field],
            req.from_stage,
            req.to_stage,
            "moved",
        )

    @app.post("/api/promote")
    def promote_record(req: PromoteRequest) -> dict:
        for source_name, destinations in cfg.pipeline_transitions.items():
            if not destinations:
                continue
            rows = load_json(stage_path(source_name))
            if any(identity_matches(row, "linkedin_url", req.linkedin_url) for row in rows):
                return configured_move(
                    "linkedin_url", req.linkedin_url, source_name, destinations[0], "promoted",
                )
        raise HTTPException(status_code=404, detail=f"No record found for '{req.linkedin_url}'")

    @app.post("/api/demote")
    def demote_record(req: PromoteRequest) -> dict:
        reverse = [
            (destination, source_name)
            for source_name, destinations in cfg.pipeline_transitions.items()
            for destination in destinations
        ]
        for source_name, destination_name in reverse:
            rows = load_json(stage_path(source_name))
            if any(identity_matches(row, "linkedin_url", req.linkedin_url) for row in rows):
                return configured_move(
                    "linkedin_url", req.linkedin_url, source_name, destination_name, "demoted",
                )
        raise HTTPException(status_code=404, detail=f"No record found for '{req.linkedin_url}'")

    @app.post("/api/pr")
    def create_pr(req: PRRequest) -> dict:
        token = github_token
        if not token or not repo:
            raise HTTPException(status_code=400, detail="GitHub not configured")

        branch = f"jsoncrm-edit-{int(time.time())}"
        files_changed = []

        # Get base branch SHA
        ref_url = f"https://api.github.com/repos/{repo}/git/ref/heads/{base_branch}"
        r = httpx.get(ref_url, headers=_gh_headers(token))
        if r.status_code != 200:
            raise HTTPException(status_code=500, detail=f"Could not get base branch: {r.text}")
        base_sha = r.json()["object"]["sha"]

        # Create new branch
        r = httpx.post(
            f"https://api.github.com/repos/{repo}/git/refs",
            headers=_gh_headers(token),
            json={"ref": f"refs/heads/{branch}", "sha": base_sha},
        )
        if r.status_code not in (200, 201):
            raise HTTPException(status_code=500, detail=f"Could not create branch: {r.text}")

        # Push each pipeline file
        for stage_name, path in context.pipeline_files:
            if not path.exists():
                continue
            filename = path.name
            content = json.dumps(load_json(path), indent=2, ensure_ascii=False) + "\n"
            encoded = base64.b64encode(content.encode(JSON_DB_ENCODING)).decode()

            # Get file SHA on base branch
            file_url = f"https://api.github.com/repos/{repo}/contents/{filename}"
            r = httpx.get(file_url, headers=_gh_headers(token), params={"ref": base_branch})
            file_sha = r.json().get("sha") if r.status_code == 200 else None

            payload = {
                "message": req.title or f"jsoncrm: update {filename} [{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M')} UTC]",
                "content": encoded,
                "branch": branch,
            }
            if file_sha:
                payload["sha"] = file_sha

            r = httpx.put(file_url, headers=_gh_headers(token), json=payload)
            if r.status_code in (200, 201):
                files_changed.append(filename)

        # Open PR
        r = httpx.post(
            f"https://api.github.com/repos/{repo}/pulls",
            headers=_gh_headers(token),
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
    print(f"  CRM dir : {app.state.crm_context.root}")
    print(f"  Repo    : {repo or '(not set — PR disabled)'}")
    print(f"  Branch  : {base_branch}\n")
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")
