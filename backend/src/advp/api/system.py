"""Local service lifecycle and graceful shutdown endpoints."""

from __future__ import annotations

import logging
import platform
import sys
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel

from advp import __version__, audit, lifecycle
from advp.api.deps import DbSession
from advp.read_only import is_read_only

router = APIRouter(prefix="/system", tags=["system"])
ROOT = Path(__file__).resolve().parents[4]


class ActiveTasksResponse(BaseModel):
    pipelines: int
    exports: int
    imports: int
    render_jobs: int
    live_streams: int
    total: int


class LifecycleResponse(BaseModel):
    shutdown_enabled: bool
    mode: str
    active_tasks: ActiveTasksResponse


class ShutdownRequest(BaseModel):
    force: bool = False


class ShutdownResponse(BaseModel):
    status: str
    active_tasks: ActiveTasksResponse


class AboutResponse(BaseModel):
    version: str
    python: str
    platform: str
    license: str
    repository: dict[str, str | None]


def _bundled_text(names: tuple[str, ...], fallback: str) -> str:
    roots = [ROOT, *ROOT.parents[:2], Path.cwd(), Path(sys.executable).resolve().parent]
    for root in roots:
        parts: list[str] = []
        for name in names:
            path = root / name
            if path.is_file():
                parts.append(path.read_text(encoding="utf-8"))
        if parts:
            return "\n\n".join(parts)
    return fallback


@router.get("/about", response_model=AboutResponse)
def about() -> dict[str, Any]:
    """Return sanitized version and runtime information for the About panel."""
    return {
        "version": __version__,
        "python": platform.python_version(),
        "platform": platform.platform(),
        "license": "Apache-2.0",
        "repository": {"label": "ADVP", "url": None},
    }


@router.get("/license", response_class=PlainTextResponse)
def license_text() -> str:
    """Return the bundled license and NOTICE text."""
    return _bundled_text(
        ("LICENSE", "NOTICE"),
        "Apache-2.0\n\nADVP is distributed under the Apache License 2.0.",
    )


@router.get("/third-party", response_class=PlainTextResponse)
def third_party_text() -> str:
    """Return the bundled third-party notices."""
    return _bundled_text(
        ("THIRD_PARTY_NOTICES.md",),
        "Third-party notices are bundled with the ADVP release package.",
    )


@router.get("/lifecycle", response_model=LifecycleResponse)
def lifecycle_state(session: DbSession) -> dict[str, object]:
    """Report whether the service can be closed and how much work is active."""
    state = lifecycle.shutdown_state()
    tasks = lifecycle.active_task_counts(session)
    return {
        **state,
        "active_tasks": tasks.as_dict(),
    }


@router.post("/shutdown", response_model=ShutdownResponse, status_code=202)
def shutdown(
    payload: ShutdownRequest,
    session: DbSession,
) -> dict[str, object]:
    """Schedule a graceful local-service shutdown after the response is sent."""
    state = lifecycle.shutdown_state()
    if not state["shutdown_enabled"]:
        raise HTTPException(
            status_code=403,
            detail={
                "code": "shutdown_unavailable",
                "message": "local service shutdown is disabled in this run mode",
                "hint": "start ADVP with the launcher or packaged application",
            },
        )
    if not lifecycle.can_schedule_shutdown():
        raise HTTPException(
            status_code=503,
            detail={
                "code": "shutdown_not_wired",
                "message": "the launcher did not install a shutdown callback",
                "hint": "restart with the packaged launcher",
            },
        )

    tasks = lifecycle.active_task_counts(session)
    if tasks.total and not payload.force:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "active_tasks",
                "message": f"{tasks.total} active task(s) would be interrupted",
                "hint": "cancel the tasks or resend with force=true after confirming",
                "active_tasks": tasks.as_dict(),
            },
        )

    if is_read_only():
        logging.getLogger("advp").info(
            "service_shutdown",
            extra={
                "mode": state["mode"],
                "force": payload.force,
                "active_tasks": tasks.as_dict(),
                "read_only": True,
            },
        )
    else:
        audit.record_event(
            session,
            "service_shutdown",
            target_type="service",
            detail={
                "mode": state["mode"],
                "force": payload.force,
                "active_tasks": tasks.as_dict(),
            },
        )
    if not lifecycle.schedule_shutdown():
        raise HTTPException(
            status_code=503,
            detail={
                "code": "shutdown_not_wired",
                "message": "the launcher did not install a shutdown callback",
                "hint": "restart with the packaged launcher",
            },
        )
    return {
        "status": "shutting_down",
        "active_tasks": tasks.as_dict(),
    }
