"""Local service lifecycle state and active-task accounting."""

from __future__ import annotations

import threading
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from advp.live import MANAGER as LIVE_MANAGER
from advp.models import ExportJob, ImportJob, PipelineRun, RenderJob

ACTIVE_PIPELINE_STATUSES = ("pending", "running", "paused")
ACTIVE_JOB_STATUSES = ("pending", "running")


@dataclass(slots=True)
class ActiveTasks:
    """Counts of work that would be interrupted by a shutdown."""

    pipelines: int = 0
    exports: int = 0
    imports: int = 0
    render_jobs: int = 0
    live_streams: int = 0

    @property
    def total(self) -> int:
        return self.pipelines + self.exports + self.imports + self.render_jobs + self.live_streams

    def as_dict(self) -> dict[str, int]:
        return {
            "pipelines": self.pipelines,
            "exports": self.exports,
            "imports": self.imports,
            "render_jobs": self.render_jobs,
            "live_streams": self.live_streams,
            "total": self.total,
        }


@dataclass(slots=True)
class ShutdownController:
    """Process-wide shutdown availability and callback."""

    enabled: bool = False
    mode: str = "development"
    callback: Callable[[], None] | None = None


_CONTROLLER = ShutdownController()


def configure_shutdown(
    *,
    enabled: bool,
    mode: str,
    callback: Callable[[], None] | None,
) -> None:
    """Configure lifecycle behavior for this process."""
    _CONTROLLER.enabled = enabled
    _CONTROLLER.mode = mode
    _CONTROLLER.callback = callback


def reset_shutdown() -> None:
    """Return to the safe development default."""
    configure_shutdown(enabled=False, mode="development", callback=None)


def shutdown_state() -> dict[str, Any]:
    """Return whether shutdown is enabled and the current run mode."""
    return {
        "shutdown_enabled": _CONTROLLER.enabled,
        "mode": _CONTROLLER.mode,
    }


def can_schedule_shutdown() -> bool:
    """Return True when a graceful shutdown callback is installed."""
    return _CONTROLLER.enabled and _CONTROLLER.callback is not None


def schedule_shutdown(delay: float = 0.2) -> bool:
    """Schedule the installed callback after the HTTP response can be flushed."""
    callback = _CONTROLLER.callback
    if not _CONTROLLER.enabled or callback is None:
        return False
    timer = threading.Timer(delay, callback)
    timer.daemon = True
    timer.start()
    return True


def active_task_counts(session: Session) -> ActiveTasks:
    """Count tasks that a shutdown would interrupt."""
    return ActiveTasks(
        pipelines=_count_statuses(session, PipelineRun, ACTIVE_PIPELINE_STATUSES),
        exports=_count_statuses(session, ExportJob, ACTIVE_JOB_STATUSES),
        imports=_count_statuses(session, ImportJob, ACTIVE_JOB_STATUSES),
        render_jobs=_count_statuses(session, RenderJob, ACTIVE_JOB_STATUSES),
        live_streams=LIVE_MANAGER.active_count(),
    )


def _count_statuses(
    session: Session,
    model: type[PipelineRun] | type[ExportJob] | type[ImportJob] | type[RenderJob],
    statuses: tuple[str, ...],
) -> int:
    statement = select(func.count()).select_from(model).where(model.status.in_(statuses))
    return int(session.scalar(statement) or 0)


__all__ = [
    "ActiveTasks",
    "ShutdownController",
    "active_task_counts",
    "can_schedule_shutdown",
    "configure_shutdown",
    "reset_shutdown",
    "schedule_shutdown",
    "shutdown_state",
]
