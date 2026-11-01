"""Persisted, ordered pipeline run events used by the SSE progress stream."""

from __future__ import annotations

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from advp.models import PipelineEvent


def append(
    session: Session,
    run_id: str,
    event_type: str,
    payload: dict[str, Any] | None = None,
) -> PipelineEvent:
    """Add the next event for a run; the caller commits with its own changes."""
    current = session.scalar(
        select(func.max(PipelineEvent.seq)).where(PipelineEvent.run_id == run_id)
    )
    row = PipelineEvent(
        run_id=run_id,
        seq=int(current or 0) + 1,
        type=event_type,
        payload_json=payload or {},
    )
    session.add(row)
    session.flush()
    return row


def list_events(
    session: Session,
    run_id: str,
    since: int = 0,
    limit: int = 1000,
) -> list[PipelineEvent]:
    """Return events after a sequence cursor in ascending order."""
    statement = (
        select(PipelineEvent)
        .where(PipelineEvent.run_id == run_id, PipelineEvent.seq > since)
        .order_by(PipelineEvent.seq)
        .limit(max(1, min(limit, 2000)))
    )
    return list(session.scalars(statement))


def event_dict(row: PipelineEvent) -> dict[str, Any]:
    """Serialize one event for SSE and API responses."""
    return {
        "id": row.id,
        "run_id": row.run_id,
        "seq": row.seq,
        "type": row.type,
        "payload": row.payload_json,
        "created_at": row.created_at,
    }
