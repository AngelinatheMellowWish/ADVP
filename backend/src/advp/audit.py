"""Redacted audit events for sensitive configuration changes."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from advp.logging_config import redact
from advp.models import AuditEvent


def record_event(
    session: Session,
    event: str,
    *,
    project_id: str | None = None,
    target_type: str | None = None,
    target_id: str | None = None,
    detail: dict[str, Any] | None = None,
) -> AuditEvent:
    """Persist one redacted audit event."""
    row = AuditEvent(
        id=uuid.uuid4().hex,
        project_id=project_id,
        event=event,
        target_type=target_type,
        target_id=target_id,
        detail_json=redact(detail or {}),
    )
    session.add(row)
    session.commit()
    session.refresh(row)
    return row


def list_events(
    session: Session,
    *,
    project_id: str | None = None,
    limit: int = 100,
) -> list[AuditEvent]:
    """Return recent audit events, optionally scoped to a project."""
    statement = select(AuditEvent).order_by(AuditEvent.created_at.desc()).limit(limit)
    if project_id is not None:
        statement = statement.where(AuditEvent.project_id == project_id)
    return list(session.scalars(statement).all())


def event_dict(row: AuditEvent) -> dict[str, Any]:
    """Serialize an audit event."""
    return {
        "id": row.id,
        "project_id": row.project_id,
        "event": row.event,
        "target_type": row.target_type,
        "target_id": row.target_id,
        "detail": row.detail_json,
        "created_at": row.created_at,
    }
