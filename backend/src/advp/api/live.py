"""Live WebSocket/Kafka session endpoints and server-sent events."""

from __future__ import annotations

import asyncio
import json
import uuid
from collections.abc import AsyncIterator
from typing import Any, NoReturn

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from advp import live as live_service
from advp.api.deps import DbSession
from advp.api.schemas import (
    LiveSessionCreate,
    LiveSessionResponse,
    LiveSnapshotImportRequest,
)
from advp.services import projects as project_service

router = APIRouter(prefix="/streams/live", tags=["live"])


def _raise_live(exc: live_service.LiveError) -> NoReturn:
    raise HTTPException(
        status_code=exc.status_code,
        detail={"code": exc.code, "message": str(exc)},
    )


@router.post("", response_model=LiveSessionResponse)
def create_live_session(payload: LiveSessionCreate) -> dict[str, Any]:
    try:
        config = _session_config(payload)
        session = live_service.MANAGER.create(
            kind=payload.kind,
            config=config,
            max_messages=payload.max_messages,
            sample_interval_ms=payload.sample_interval_ms,
        )
        return session.snapshot()
    except live_service.LiveError as exc:
        _raise_live(exc)


@router.get("/{session_id}", response_model=LiveSessionResponse)
def get_live_session(session_id: str) -> dict[str, Any]:
    try:
        return live_service.MANAGER.snapshot(session_id)
    except live_service.LiveError as exc:
        _raise_live(exc)


@router.get("/{session_id}/events")
async def live_events(session_id: str, since: int = 0) -> StreamingResponse:
    try:
        live_service.MANAGER.snapshot(session_id)
    except live_service.LiveError as exc:
        _raise_live(exc)

    async def generator() -> AsyncIterator[str]:
        cursor = max(0, since)
        while True:
            try:
                snapshot = live_service.MANAGER.snapshot(session_id, since=cursor)
            except live_service.LiveError as exc:
                payload = {"status": "error", "error": str(exc), "session_id": session_id}
                yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
                break
            yield f"data: {json.dumps(snapshot, ensure_ascii=False)}\n\n"
            cursor = int(snapshot["to_sequence"])
            if snapshot["status"] == "stopped":
                break
            await asyncio.sleep(1.0)

    return StreamingResponse(
        generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/{session_id}/pause", response_model=LiveSessionResponse)
def pause_live_session(session_id: str) -> dict[str, Any]:
    try:
        return live_service.MANAGER.pause(session_id)
    except live_service.LiveError as exc:
        _raise_live(exc)


@router.post("/{session_id}/resume", response_model=LiveSessionResponse)
def resume_live_session(session_id: str) -> dict[str, Any]:
    try:
        return live_service.MANAGER.resume(session_id)
    except live_service.LiveError as exc:
        _raise_live(exc)


@router.post("/{session_id}/stop", response_model=LiveSessionResponse)
def stop_live_session(session_id: str) -> dict[str, Any]:
    try:
        return live_service.MANAGER.stop(session_id)
    except live_service.LiveError as exc:
        _raise_live(exc)


@router.post("/{session_id}/snapshot")
def save_live_snapshot(
    session_id: str,
    payload: LiveSnapshotImportRequest,
    session: DbSession,
) -> dict[str, Any]:
    try:
        snapshot = live_service.MANAGER.snapshot(session_id)
    except live_service.LiveError as exc:
        _raise_live(exc)
    project = project_service.get_project(session, payload.project_id)
    if project is None:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "project_not_found",
                "message": f"project was not found: {payload.project_id}",
            },
        )
    records = [
        {key: value for key, value in record.items() if not key.startswith("_")}
        for record in snapshot["records"]
    ]
    if not records:
        raise HTTPException(
            status_code=409,
            detail={"code": "empty_stream", "message": "live session has no records to save"},
        )
    try:
        dataset = project_service.import_stream_snapshot(
            session,
            project,
            records,
            source_kind=str(snapshot["kind"]),
            label=session_id,
            name=payload.name,
            options=None,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=422,
            detail={"code": "snapshot_import_failed", "message": str(exc)},
        ) from exc
    return project_service.dataset_detail(dataset)


def _session_config(payload: LiveSessionCreate) -> dict[str, Any]:
    if payload.kind == "websocket":
        url = (payload.url or "").strip()
        if not url.startswith(("ws://", "wss://")):
            raise live_service.LiveError(
                "invalid_source",
                "WebSocket URL must start with ws:// or wss://",
            )
        return {
            "url": url,
            "headers": payload.headers,
            "auth": payload.auth.model_dump(exclude_none=True) if payload.auth else None,
            "open_timeout": payload.timeout,
        }
    if not payload.bootstrap or not payload.topic:
        raise live_service.LiveError(
            "invalid_source",
            "Kafka bootstrap and topic are required",
        )
    if payload.auto_offset_reset not in {"earliest", "latest"}:
        raise live_service.LiveError(
            "invalid_source",
            "auto_offset_reset must be earliest or latest",
        )
    config: dict[str, Any] = {
        "bootstrap.servers": payload.bootstrap,
        "group.id": payload.group or f"advp-live-{uuid.uuid4().hex}",
        "auto.offset.reset": payload.auto_offset_reset,
        "enable.auto.commit": False,
        "session.timeout.ms": 10000,
        "max.poll.interval.ms": 300000,
    }
    if payload.security_protocol:
        config["security.protocol"] = payload.security_protocol
    if payload.sasl_mechanism:
        config["sasl.mechanism"] = payload.sasl_mechanism
    if payload.sasl_username:
        config["sasl.username"] = payload.sasl_username
    if payload.sasl_password is not None:
        config["sasl.password"] = payload.sasl_password.get_secret_value()
    if payload.ssl_ca_location:
        config["ssl.ca.location"] = payload.ssl_ca_location
    return {"consumer_config": config, "topic": payload.topic}
