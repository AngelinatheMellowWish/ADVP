"""Safe cleanup endpoints for rebuildable and orphaned artifacts."""

from __future__ import annotations

from typing import Any, NoReturn

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from advp import cleanup
from advp.api.deps import DbSession

router = APIRouter(prefix="/system/cleanup", tags=["cleanup"])


class CleanupPreviewRequest(BaseModel):
    """Categories to scan, plus whether referenced uploads are in scope."""

    categories: list[str] = Field(default_factory=lambda: list(cleanup.CATEGORIES))
    allow_referenced_uploads: bool = False


class CleanupExecuteRequest(CleanupPreviewRequest):
    """A confirmed cleanup request."""

    confirm: bool = False


def _raise_cleanup(exc: cleanup.CleanupError) -> NoReturn:
    detail: dict[str, Any] = {"code": exc.code, "message": str(exc)}
    if exc.hint:
        detail["hint"] = exc.hint
    raise HTTPException(status_code=exc.status_code, detail=detail) from exc


@router.post("/preview")
def preview_cleanup(
    payload: CleanupPreviewRequest,
    session: DbSession,
) -> dict[str, Any]:
    """Report deletable and protected bytes without changing the disk."""
    try:
        return cleanup.preview(
            session,
            payload.categories,
            allow_referenced_uploads=payload.allow_referenced_uploads,
        )
    except cleanup.CleanupError as exc:
        _raise_cleanup(exc)


@router.post("")
def run_cleanup(
    payload: CleanupExecuteRequest,
    session: DbSession,
) -> dict[str, Any]:
    """Delete the selected non-protected artifacts and write an audit event."""
    try:
        return cleanup.execute(
            session,
            payload.categories,
            confirm=payload.confirm,
            allow_referenced_uploads=payload.allow_referenced_uploads,
        )
    except cleanup.CleanupError as exc:
        _raise_cleanup(exc)
