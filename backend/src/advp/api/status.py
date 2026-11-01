"""System status for the project home page."""

from __future__ import annotations

import os
import shutil
import socket
from typing import Any

from fastapi import APIRouter
from sqlalchemy import select

from advp import render3d
from advp.api.deps import DbSession
from advp.api.tasks import task_state
from advp.config import get_settings
from advp.db import check_database
from advp.models import Provider

router = APIRouter(prefix="/system", tags=["status"])


def _memory_percent() -> float:
    try:
        import psutil  # type: ignore[import-untyped]

        return float(psutil.virtual_memory().percent)
    except Exception:
        return 0.0


def _cpu_percent() -> float:
    try:
        import psutil

        return float(psutil.cpu_percent(interval=0.05))
    except Exception:
        return 0.0


def _network_online() -> bool:
    try:
        with socket.create_connection(("1.1.1.1", 53), timeout=0.25):
            return True
    except OSError:
        return False


def _gpu_state() -> str:
    try:
        probe = render3d.probe_renderer()
    except render3d.Render3DError:
        return "software"
    return "available" if probe.get("ok") else "software"


@router.get("/status")
def system_status(session: DbSession) -> dict[str, Any]:
    """Return service, provider, GPU, disk, database, and resource status."""
    settings = get_settings()
    provider = session.scalars(
        select(Provider).order_by(Provider.is_default.desc(), Provider.priority).limit(1)
    ).first()
    usage = shutil.disk_usage(
        settings.workspace_dir if settings.workspace_dir.exists() else settings.database_path.parent
    )
    tasks = task_state(session)
    return {
        "service": "ok",
        "provider": {
            "status": "configured" if provider is not None else "missing",
            "name": provider.name if provider is not None else None,
            "has_key": bool(provider.has_key) if provider is not None else False,
        },
        "gpu": _gpu_state(),
        "disk_free_gb": round(usage.free / (1024**3), 2),
        "disk_total_gb": round(usage.total / (1024**3), 2),
        "database": "ok" if check_database() else "error",
        "cpu_percent": _cpu_percent(),
        "cpu_count": os.cpu_count() or 0,
        "memory_percent": _memory_percent(),
        "network_online": _network_online(),
        "active_tasks": tasks["counts"],
        "recent_tasks": {
            key: tasks[key]
            for key in ("imports", "pipelines", "exports", "render_jobs", "live_streams")
        },
    }
