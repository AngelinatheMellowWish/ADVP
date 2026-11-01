"""Native file picker and copy-to-workspace upload endpoints."""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import subprocess
import sys
import uuid
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, UploadFile
from pydantic import BaseModel

from advp.api.deps import DbSession
from advp.config import get_settings
from advp.models import Project

router = APIRouter(tags=["files"])
logger = logging.getLogger("advp.files")

FILE_DIALOG_SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "file_dialog.py"
PICK_TIMEOUT_SECONDS = 60.0
CHUNK_BYTES = 1024 * 1024
_UNSAFE_FILENAME = re.compile(r"[^A-Za-z0-9._ -]+")


class PickFileResponse(BaseModel):
    path: str | None


class UploadResponse(BaseModel):
    path: str
    sha256: str
    size: int
    copied: bool


def pick_path(timeout: float = PICK_TIMEOUT_SECONDS) -> str | None:
    """Run the native picker helper and return the selected path, if any."""
    try:
        completed = subprocess.run(
            [sys.executable, str(FILE_DIALOG_SCRIPT)],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if completed.returncode != 0:
        return None
    try:
        payload = json.loads(completed.stdout.strip() or "{}")
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None
    selected = payload.get("path")
    if not isinstance(selected, str):
        return None
    selected = selected.strip()
    return selected or None


@router.post("/system/pick-file", response_model=PickFileResponse)
def pick_file() -> dict[str, Any]:
    """Open a native file dialog on the machine running the service."""
    return {"path": pick_path()}


@router.post(
    "/projects/{project_id}/uploads",
    response_model=UploadResponse,
    status_code=201,
)
def upload_file(project_id: str, file: UploadFile, session: DbSession) -> dict[str, Any]:
    """Copy an uploaded file into the project's workspace and hash it."""
    if session.get(Project, project_id) is None:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "project_not_found",
                "message": f"project was not found: {project_id}",
            },
        )
    settings = get_settings()
    project_dir = settings.resolved_imports_dir / project_id
    project_dir.mkdir(parents=True, exist_ok=True)
    temp_path = project_dir / f".upload-{uuid.uuid4().hex}.tmp"
    digest = hashlib.sha256()
    size = 0
    target_path: Path | None = None
    try:
        with temp_path.open("wb") as handle:
            while chunk := file.file.read(CHUNK_BYTES):
                size += len(chunk)
                if size > settings.max_file_bytes:
                    raise HTTPException(
                        status_code=413,
                        detail={
                            "code": "file_too_large",
                            "message": f"upload exceeds the {settings.max_file_bytes} byte limit",
                        },
                    )
                digest.update(chunk)
                handle.write(chunk)
        if size == 0:
            raise HTTPException(
                status_code=422,
                detail={"code": "empty_upload", "message": "uploaded file is empty"},
            )
        sha256 = digest.hexdigest()
        target_dir = project_dir / sha256
        target_dir.mkdir(parents=True, exist_ok=True)
        target_path = target_dir / _safe_filename(file.filename)
        os.replace(temp_path, target_path)
    finally:
        temp_path.unlink(missing_ok=True)
    assert target_path is not None
    logger.info("upload_copied", extra={"project_id": project_id, "size": size})
    return {
        "path": str(target_path),
        "sha256": sha256,
        "size": size,
        "copied": True,
    }


def _safe_filename(name: str | None) -> str:
    """Reduce an uploaded name to a single plain filename."""
    base = Path(name or "").name.strip()
    base = _UNSAFE_FILENAME.sub("_", base).strip(" .")
    if not base or base in {".", ".."}:
        base = "upload"
    return base[:120]
