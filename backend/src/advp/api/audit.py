"""Audit event read endpoints."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy.orm import Session

from advp import audit as audit_service
from advp.api.deps import DbSession
from advp.models import Project

router = APIRouter(tags=["audit"])


def _project_or_404(session: Session, project_id: str) -> Project:
    project = session.get(Project, project_id)
    if project is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "project_not_found", "message": f"project was not found: {project_id}"},
        )
    return project


@router.get("/projects/{project_id}/audit")
def project_audit(
    project_id: str,
    session: DbSession,
    limit: int = Query(default=100, ge=1, le=500),
) -> list[dict[str, Any]]:
    _project_or_404(session, project_id)
    return [
        audit_service.event_dict(row)
        for row in audit_service.list_events(session, project_id=project_id, limit=limit)
    ]


@router.get("/audit/events")
def all_audit_events(
    session: DbSession,
    project_id: str | None = None,
    limit: int = Query(default=100, ge=1, le=500),
) -> list[dict[str, Any]]:
    return [
        audit_service.event_dict(row)
        for row in audit_service.list_events(session, project_id=project_id, limit=limit)
    ]
