"""Aggregated active task state for the global task bar."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from sqlalchemy import select
from sqlalchemy.orm import Session

from advp import lifecycle
from advp.api.deps import DbSession
from advp.models import ExportJob, ImportJob, PipelineRun, RenderJob

router = APIRouter(prefix="/system", tags=["tasks"])


def _items(
    session: Session,
    model: Any,
    kind: str,
    limit: int = 10,
) -> list[dict[str, Any]]:
    rows: list[Any] = list(
        session.scalars(
            select(model)
            .where(model.status.in_(("pending", "running", "paused")))
            .order_by(model.created_at.desc())
            .limit(limit)
        ).all()
    )
    return [
        {
            "id": row.id,
            "kind": kind,
            "status": row.status,
            "created_at": row.created_at,
        }
        for row in rows
    ]


def task_state(session: Session) -> dict[str, Any]:
    """Return counts and recent active items for every background task type."""
    counts = lifecycle.active_task_counts(session).as_dict()
    return {
        "counts": counts,
        "imports": _items(session, ImportJob, "import"),
        "pipelines": _items(session, PipelineRun, "pipeline"),
        "exports": _items(session, ExportJob, "export"),
        "render_jobs": _items(session, RenderJob, "render"),
        "live_streams": [],
    }


@router.get("/tasks")
def list_tasks(session: DbSession) -> dict[str, Any]:
    """Return aggregated background task state."""
    return task_state(session)
