"""Atomic, out-of-Git snapshots of configured CRM state."""

import json
import os
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

MANIFEST_NAME = "backup-manifest.json"


def _git_root(crm_dir):
    for candidate in (crm_dir, *crm_dir.parents):
        if (candidate / ".git").exists():
            return candidate
    return None


def _default_output(crm_dir, now):
    name = re.sub(r"[^A-Za-z0-9_.-]+", "-", crm_dir.name).strip("-.") or "crm"
    timestamp = now.strftime("%Y%m%dT%H%M%S%fZ")
    return Path.home() / ".jsoncrm" / "backups" / f"{name}-{timestamp}.zip"


def create_backup(crm_dir, source_files, output=None, now=None):
    crm_dir = Path(crm_dir).expanduser().resolve()
    now = now or datetime.now(timezone.utc)
    created_at = now.isoformat(timespec="seconds").replace("+00:00", "Z")
    output = Path(output).expanduser() if output else _default_output(crm_dir, now)
    output = output.resolve()

    git_root = _git_root(crm_dir)
    if git_root is not None:
        try:
            output.relative_to(git_root)
        except ValueError:
            pass
        else:
            raise ValueError(f"backup destination must be outside the Git repository: {git_root}")

    entries = []
    missing = []
    seen = set()
    for source in source_files:
        path = Path(source).expanduser()
        if not path.is_absolute():
            path = crm_dir / path
        path = path.resolve()
        try:
            relative = path.relative_to(crm_dir)
        except ValueError as exc:
            raise ValueError(f"CRM source is outside {crm_dir}: {path}") from exc
        archive_name = relative.as_posix()
        if archive_name in seen:
            continue
        seen.add(archive_name)
        if not path.exists():
            missing.append(archive_name)
            continue
        if not path.is_file():
            raise ValueError(f"CRM source is not a file: {path}")
        entries.append((path, archive_name))

    if not entries:
        raise ValueError(f"no CRM files found to back up in {crm_dir}")
    if output.exists():
        raise ValueError(f"backup already exists: {output}")

    archived_files = [archive_name for _, archive_name in entries]
    manifest = {
        "created_at": created_at,
        "files": archived_files,
        "missing": missing,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(f".{output.name}.tmp-{uuid.uuid4().hex}")
    try:
        with ZipFile(temporary, "x", compression=ZIP_DEFLATED) as archive:
            for path, archive_name in entries:
                archive.write(path, archive_name)
            archive.writestr(
                MANIFEST_NAME,
                json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
            )
        os.replace(temporary, output)
    finally:
        temporary.unlink(missing_ok=True)

    return {"backup": str(output), "files": archived_files, "missing": missing}
