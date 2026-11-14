"""Audit event read, search, and redacted export endpoints."""

from __future__ import annotations

import csv
import io
import json
from datetime import UTC, datetime
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Query, Response
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from advp import audit as audit_service
from advp.api.deps import DbSession
from advp.logging_config import redact
from advp.models import AuditEvent, Project

router = APIRouter(tags=["audit"])


def _project_or_404(session: Session, project_id: str) -> Project:
    project = session.get(Project, project_id)
    if project is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "project_not_found", "message": f"project was not found: {project_id}"},
        )
    return project


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def _parse_time(value: str | None, name: str) -> datetime | None:
    if value is None or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "invalid_audit_filter",
                "message": f"{name} must be an ISO 8601 datetime",
                "hint": "use a value such as 2026-11-01T00:00:00Z",
            },
        ) from None
    return _aware(parsed)


def _filtered_events(
    session: Session,
    *,
    project_id: str | None = None,
    event: str | None = None,
    target: str | None = None,
    target_type: str | None = None,
    target_id: str | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
    q: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[dict[str, Any]]:
    """Return redacted audit rows matching every supplied filter."""
    rows = list(session.scalars(select(AuditEvent).order_by(AuditEvent.created_at.desc())).all())
    needle = q.strip().casefold() if q and q.strip() else None
    target_needle = target.strip().casefold() if target and target.strip() else None
    matched: list[AuditEvent] = []
    for row in rows:
        if project_id is not None and row.project_id != project_id:
            continue
        if event is not None and row.event != event:
            continue
        if target_type is not None and row.target_type != target_type:
            continue
        if target_id is not None and row.target_id != target_id:
            continue
        created = _aware(row.created_at)
        if since is not None and created < since:
            continue
        if until is not None and created > until:
            continue
        if target_needle is not None:
            candidate = f"{row.target_type or ''} {row.target_id or ''}".casefold()
            if target_needle not in candidate:
                continue
        if needle is not None:
            haystack = " ".join(
                [
                    row.event,
                    row.target_type or "",
                    row.target_id or "",
                    json.dumps(row.detail_json, ensure_ascii=False, default=str),
                ]
            ).casefold()
            if needle not in haystack:
                continue
        matched.append(row)
    selected = matched[offset : offset + limit]
    return [redact(audit_service.event_dict(row)) for row in selected]


@router.get("/projects/{project_id}/audit")
def project_audit(
    project_id: str,
    session: DbSession,
    event: str | None = None,
    target: str | None = None,
    target_type: str | None = None,
    target_id: str | None = None,
    since: str | None = None,
    until: str | None = None,
    q: str | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> list[dict[str, Any]]:
    _project_or_404(session, project_id)
    return _filtered_events(
        session,
        project_id=project_id,
        event=event,
        target=target,
        target_type=target_type,
        target_id=target_id,
        since=_parse_time(since, "since"),
        until=_parse_time(until, "until"),
        q=q,
        limit=limit,
        offset=offset,
    )


@router.get("/audit/events")
def all_audit_events(
    session: DbSession,
    project_id: str | None = None,
    event: str | None = None,
    target: str | None = None,
    target_type: str | None = None,
    target_id: str | None = None,
    since: str | None = None,
    until: str | None = None,
    q: str | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> list[dict[str, Any]]:
    return _filtered_events(
        session,
        project_id=project_id,
        event=event,
        target=target,
        target_type=target_type,
        target_id=target_id,
        since=_parse_time(since, "since"),
        until=_parse_time(until, "until"),
        q=q,
        limit=limit,
        offset=offset,
    )


@router.get("/audit/export")
def export_audit_events(
    session: DbSession,
    project_id: str | None = None,
    event: str | None = None,
    target: str | None = None,
    target_type: str | None = None,
    target_id: str | None = None,
    since: str | None = None,
    until: str | None = None,
    q: str | None = None,
    limit: int = Query(default=500, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    export_format: Literal["json", "csv"] = Query(default="json", alias="format"),
) -> Response:
    rows = _filtered_events(
        session,
        project_id=project_id,
        event=event,
        target=target,
        target_type=target_type,
        target_id=target_id,
        since=_parse_time(since, "since"),
        until=_parse_time(until, "until"),
        q=q,
        limit=limit,
        offset=offset,
    )
    if export_format == "csv":
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(
            [
                "id",
                "project_id",
                "event",
                "target_type",
                "target_id",
                "detail",
                "created_at",
            ]
        )
        for row in rows:
            created = row.get("created_at")
            writer.writerow(
                [
                    row["id"],
                    row.get("project_id") or "",
                    row["event"],
                    row.get("target_type") or "",
                    row.get("target_id") or "",
                    json.dumps(row.get("detail") or {}, ensure_ascii=False, default=str),
                    _aware(created).isoformat() if isinstance(created, datetime) else "",
                ]
            )
        return Response(
            content=buffer.getvalue(),
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": 'attachment; filename="advp-audit.csv"'},
        )
    return JSONResponse(
        content=jsonable_encoder(rows),
        headers={"Content-Disposition": 'attachment; filename="advp-audit.json"'},
    )
