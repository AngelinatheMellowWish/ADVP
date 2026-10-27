"""Local service lifecycle and graceful shutdown endpoints."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from advp import audit, lifecycle
from advp.api.deps import DbSession

router = APIRouter(prefix="/system", tags=["system"])


class ActiveTasksResponse(BaseModel):
    pipelines: int
    exports: int
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
