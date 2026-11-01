"""Unsigned update check, download, and install endpoints."""

from __future__ import annotations

from pathlib import Path
from typing import Any, NoReturn
from urllib.parse import urlsplit

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from advp import __version__, updates
from advp.api.deps import DbSession
from advp.config import get_settings

router = APIRouter(prefix="/updates", tags=["updates"])


class DownloadRequest(BaseModel):
    url: str = Field(min_length=1, max_length=2000)
    filename: str | None = Field(default=None, max_length=200)


class InstallRequest(BaseModel):
    path: str = Field(min_length=1, max_length=2000)
    sha256: str = Field(min_length=64, max_length=64)


def _raise_update(exc: updates.UpdateError) -> NoReturn:
    raise HTTPException(
        status_code=exc.status_code,
        detail={"code": exc.code, "message": str(exc)},
    )


@router.get("/status")
def get_status() -> dict[str, Any]:
    return updates.read_update_status()


@router.post("/check")
def check(session: DbSession) -> dict[str, Any]:
    del session
    try:
        result = updates.check_for_update(__version__)
    except updates.UpdateError as exc:
        _raise_update(exc)
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail={"code": "update_check_failed", "message": str(exc)},
        ) from exc
    updates.write_update_status(result)
    return result


@router.post("/download")
def download(payload: DownloadRequest) -> dict[str, Any]:
    name = Path(payload.filename or urlsplit(payload.url).path).name or "advp-update.exe"
    destination = get_settings().resolved_eu2_dir / "updates" / name
    try:
        result = updates.download_update(payload.url, destination)
    except updates.UpdateError as exc:
        _raise_update(exc)
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail={"code": "update_download_failed", "message": str(exc)},
        ) from exc
    return result


@router.post("/install")
def install(payload: InstallRequest) -> dict[str, Any]:
    try:
        result = updates.install_update(
            Path(payload.path),
            expected_sha256=payload.sha256,
        )
    except updates.UpdateError as exc:
        _raise_update(exc)
    return result
