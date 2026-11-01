"""Persistent local notification center."""

from __future__ import annotations

import contextlib
import json
import os
import threading
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel, Field

from advp.config import get_settings

router = APIRouter(prefix="/notifications", tags=["notifications"])

_LOCK = threading.RLock()
MAX_ITEMS = 1000
MAX_AGE_DAYS = 30


class NotificationCreate(BaseModel):
    kind: str = Field(min_length=1, max_length=40)
    title: str = Field(min_length=1, max_length=200)
    message: str = Field(default="", max_length=2000)


def _path() -> Path:
    return get_settings().resolved_eu2_dir / "notifications.json"


def _load() -> list[dict[str, Any]]:
    with _LOCK:
        try:
            data = json.loads(_path().read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            return []
        if not isinstance(data, list):
            return []
        return [item for item in data if isinstance(item, dict)]


def _save(items: list[dict[str, Any]]) -> None:
    path = _path()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f"{path.name}.{uuid.uuid4().hex}.tmp")
    with _LOCK:
        try:
            temporary.write_text(
                json.dumps(items, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            os.replace(temporary, path)
        finally:
            with contextlib.suppress(OSError):
                temporary.unlink()


def _prune(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    cutoff = (datetime.now(UTC) - timedelta(days=MAX_AGE_DAYS)).isoformat()
    items = [item for item in items if str(item.get("created_at") or "") >= cutoff]
    return items[:MAX_ITEMS]


@router.get("")
def list_notifications() -> dict[str, Any]:
    items = _load()
    return {
        "items": items,
        "unread": sum(1 for item in items if not item.get("read")),
    }


@router.post("", status_code=201)
def create_notification(payload: NotificationCreate) -> dict[str, Any]:
    item = {
        "id": uuid.uuid4().hex,
        "kind": payload.kind,
        "title": payload.title,
        "message": payload.message,
        "read": False,
        "created_at": datetime.now(UTC).isoformat(),
    }
    items = _prune([item, *_load()])
    _save(items)
    return item


@router.post("/{notification_id}/read")
def mark_read(notification_id: str) -> dict[str, Any]:
    items = _load()
    for item in items:
        if item.get("id") == notification_id:
            item["read"] = True
            _save(items)
            return item
    raise HTTPException(
        status_code=404,
        detail={
            "code": "notification_not_found",
            "message": f"notification was not found: {notification_id}",
        },
    )


@router.delete("", status_code=204)
def clear_notifications() -> Response:
    _save([])
    return Response(status_code=204)
