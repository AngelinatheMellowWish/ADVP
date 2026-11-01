"""Persisted background dataset import jobs."""

from __future__ import annotations

import logging
import threading
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from sqlalchemy import case, select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.orm import Session

from advp.config import get_settings
from advp.db import get_session
from advp.ingest.files import MAX_SAMPLE_ROWS, ImportOptions
from advp.models import ImportJob, Project
from advp.services import projects as project_service

logger = logging.getLogger("advp.import")

_active_lock = threading.Lock()
_active_jobs: set[str] = set()
_running_threads: dict[str, threading.Thread] = {}


class ImportJobError(Exception):
    """Invalid import job request."""

    def __init__(self, code: str, message: str, status_code: int = 422) -> None:
        super().__init__(message)
        self.code = code
        self.status_code = status_code


def create_import_job(
    session: Session,
    project_id: str,
    payload: dict[str, Any],
) -> ImportJob:
    """Create a pending import job for an existing project."""
    project = session.get(Project, project_id)
    if project is None:
        raise ImportJobError("project_not_found", f"project was not found: {project_id}", 404)
    path = str(payload.get("path") or "").strip()
    if not path:
        raise ImportJobError("invalid_import_payload", "path is required", 422)
    row = ImportJob(
        id=uuid.uuid4().hex,
        project_id=project_id,
        status="pending",
        stage="pending",
        progress=0.0,
        payload={**payload, "path": path},
        cancel_requested=False,
    )
    session.add(row)
    session.commit()
    session.refresh(row)
    return row


def start_import_job(job_id: str) -> str:
    """Claim a pending job and run it, or queue it when slots are full.

    Returns ``started``, ``queued``, or ``failed``. Queued jobs stay pending and
    are started when an active import finishes.
    """
    with _active_lock:
        if job_id in _active_jobs or len(_active_jobs) >= _capacity():
            return "queued"
        _active_jobs.add(job_id)
    session = get_session()
    try:
        claimed = _claim_pending(session, job_id)
    finally:
        session.close()
    if not claimed:
        _release_slot(job_id)
        return "queued"
    thread = threading.Thread(
        target=run_import_job,
        args=(job_id,),
        kwargs={"claimed": True},
        name=f"import-job-{job_id}",
        daemon=True,
    )
    with _active_lock:
        _running_threads[job_id] = thread
    try:
        thread.start()
    except Exception as exc:
        _mark_runner_start_failed(job_id, exc)
        _release_slot(job_id)
        return "failed"
    return "started"


def run_import_job(job_id: str, claimed: bool = False) -> None:
    """Execute one import job in the background."""
    session = get_session()
    try:
        execute_import_job(session, job_id, claimed=claimed)
    finally:
        session.close()
        _finish_slot(job_id)


def shutdown_import_jobs(timeout: float = 5.0) -> None:
    """Join active import threads so shutdown does not abandon in-flight work."""
    with _active_lock:
        threads = list(_running_threads.values())
    deadline = time.monotonic() + timeout
    for thread in threads:
        thread.join(timeout=max(0.0, deadline - time.monotonic()))


def _capacity() -> int:
    return max(1, min(get_settings().import_concurrency, 8))


def _release_slot(job_id: str) -> None:
    with _active_lock:
        _active_jobs.discard(job_id)
        _running_threads.pop(job_id, None)


def _finish_slot(job_id: str) -> None:
    _release_slot(job_id)
    _resume_queued()


def _resume_queued() -> None:
    session = get_session()
    try:
        pending = list(
            session.scalars(
                select(ImportJob.id)
                .where(ImportJob.status == "pending")
                .order_by(ImportJob.created_at)
            )
        )
    finally:
        session.close()
    for job_id in pending:
        if start_import_job(job_id) != "started":
            return


def execute_import_job(
    session: Session,
    job_id: str,
    *,
    claimed: bool = False,
) -> ImportJob | None:
    """Execute one import job, claiming it first when called directly."""
    if not claimed and not _claim_pending(session, job_id):
        session.expire_all()
        return session.get(ImportJob, job_id)
    session.expire_all()
    row = session.get(ImportJob, job_id)
    if row is None:
        return None
    if row.status != "running":
        return row
    if row.cancel_requested:
        return _mark_cancelled(session, row)
    logger.info("import_started", extra={"job_id": row.id, "project_id": row.project_id})

    try:
        project = session.get(Project, row.project_id)
        if project is None:
            raise ImportJobError(
                "project_not_found", f"project was not found: {row.project_id}", 404
            )

        session.refresh(row)
        if row.cancel_requested:
            return _mark_cancelled(session, row)

        payload = dict(row.payload or {})
        _set_stage(session, row, "importing", 0.25, "importing data")
        session.refresh(row)
        if row.cancel_requested:
            return _mark_cancelled(session, row)

        dataset = project_service.import_dataset(
            session,
            project,
            path=str(payload.get("path") or ""),
            name=str(payload["name"]) if payload.get("name") else None,
            options=_import_options(payload.get("options")),
        )
        session.refresh(row)
        if row.cancel_requested and dataset is None:
            return _mark_cancelled(session, row)
        if dataset is None:
            raise RuntimeError("importer returned no dataset")

        _set_stage(session, row, "profiling", 0.55, "profiling data")
        _set_stage(session, row, "writing", 0.85, "writing dataset")
        result = cast(
            CursorResult[Any],
            session.execute(
                update(ImportJob)
                .where(ImportJob.id == row.id, ImportJob.status == "running")
                .values(
                    status="succeeded",
                    stage="completed",
                    progress=1.0,
                    message=case(
                        (
                            ImportJob.cancel_requested.is_(True),
                            "import completed before cancellation; dataset was committed",
                        ),
                        else_="import completed",
                    ),
                    result_dataset_id=dataset.id,
                    error=None,
                    cancel_requested=False,
                    updated_at=datetime.now(UTC),
                )
                .execution_options(synchronize_session=False)
            ),
        )
        session.commit()
        session.expire_all()
        row = session.get(ImportJob, job_id)
        if row is None:
            return None
        if result.rowcount != 1:
            return row
        logger.info(
            "import_succeeded",
            extra={"job_id": row.id, "dataset_id": row.result_dataset_id},
        )
        return row
    except Exception as exc:
        session.rollback()
        row = session.get(ImportJob, job_id)
        if row is None:
            return None
        failed_payload = dict(row.payload or {})
        row.status = "failed"
        row.stage = "failed"
        row.message = "import failed"
        row.error = _error_text(exc, str(failed_payload.get("path") or "") or None)
        row.updated_at = datetime.now(UTC)
        session.commit()
        session.refresh(row)
        logger.error(
            "import_failed",
            extra={"job_id": row.id, "error": row.error},
        )
        return row


def cancel_import_job(session: Session, job_id: str) -> ImportJob:
    """Cancel pending jobs immediately and flag running jobs cooperatively."""
    now = datetime.now(UTC)
    pending = cast(
        CursorResult[Any],
        session.execute(
            update(ImportJob)
            .where(ImportJob.id == job_id, ImportJob.status == "pending")
            .values(
                status="cancelled",
                stage="cancelled",
                message="import cancelled",
                cancel_requested=True,
                updated_at=now,
            )
        ),
    )
    if pending.rowcount == 1:
        session.commit()
        session.expire_all()
        row = session.get(ImportJob, job_id)
        if row is None:
            raise ImportJobError("import_job_not_found", f"import job was not found: {job_id}", 404)
        logger.info("import_cancelled", extra={"job_id": row.id})
        return row

    running = cast(
        CursorResult[Any],
        session.execute(
            update(ImportJob)
            .where(ImportJob.id == job_id, ImportJob.status == "running")
            .values(cancel_requested=True, updated_at=now)
        ),
    )
    session.commit()
    session.expire_all()
    row = session.get(ImportJob, job_id)
    if row is None:
        raise ImportJobError("import_job_not_found", f"import job was not found: {job_id}", 404)
    if running.rowcount != 1:
        raise ImportJobError("import_job_not_active", f"job {job_id} is {row.status}", 409)
    return row


def retry_import_job(session: Session, job_id: str) -> ImportJob:
    """Atomically reset and claim a failed, cancelled, or pending job."""
    now = datetime.now(UTC)
    result = cast(
        CursorResult[Any],
        session.execute(
            update(ImportJob)
            .where(
                ImportJob.id == job_id,
                ImportJob.status.in_(("failed", "cancelled", "pending")),
            )
            .values(
                status="pending",
                stage="pending",
                progress=0.0,
                message=None,
                result_dataset_id=None,
                error=None,
                cancel_requested=False,
                updated_at=now,
            )
        ),
    )
    session.commit()
    if result.rowcount != 1:
        session.expire_all()
        row = session.get(ImportJob, job_id)
        if row is None:
            raise ImportJobError("import_job_not_found", f"import job was not found: {job_id}", 404)
        raise ImportJobError("import_job_not_retryable", f"job {job_id} is {row.status}", 409)
    if start_import_job(job_id) != "started":
        session.expire_all()
        row = session.get(ImportJob, job_id)
        if row is None:
            raise ImportJobError("import_job_not_found", f"import job was not found: {job_id}", 404)
        if (row.error or "").startswith("runner_start_failed"):
            raise ImportJobError(
                "import_runner_failed",
                f"import runner failed to start for job {job_id}",
                500,
            )
        if row.status == "pending":
            return row
        raise ImportJobError("import_job_not_retryable", f"job {job_id} is {row.status}", 409)
    session.expire_all()
    row = session.get(ImportJob, job_id)
    if row is None:
        raise ImportJobError("import_job_not_found", f"import job was not found: {job_id}", 404)
    return row


def recover_import_jobs(session: Session) -> list[ImportJob]:
    """Mark interrupted running jobs as failed; leave pending jobs retryable."""
    rows = list(session.scalars(select(ImportJob).where(ImportJob.status == "running")))
    for row in rows:
        row.status = "failed"
        row.stage = "failed"
        row.message = "import interrupted"
        row.error = "interrupted: the service restarted before the import finished"
        row.updated_at = datetime.now(UTC)
    if rows:
        session.commit()
    return rows


def resume_pending_import_jobs(session: Session) -> list[str]:
    """Start pending jobs left behind by a previous process, up to the limit."""
    pending = list(
        session.scalars(
            select(ImportJob.id).where(ImportJob.status == "pending").order_by(ImportJob.created_at)
        )
    )
    started: list[str] = []
    for job_id in pending:
        if start_import_job(job_id) != "started":
            break
        started.append(job_id)
    return started


def list_import_jobs(session: Session, project_id: str, limit: int = 50) -> list[ImportJob]:
    """Return recent import jobs for a project."""
    bounded = max(1, min(limit, 200))
    statement = (
        select(ImportJob)
        .where(ImportJob.project_id == project_id)
        .order_by(ImportJob.created_at.desc())
        .limit(bounded)
    )
    return list(session.scalars(statement))


def job_dict(row: ImportJob) -> dict[str, Any]:
    """Serialize an import job for API responses."""
    return {
        "id": row.id,
        "project_id": row.project_id,
        "status": row.status,
        "stage": row.stage,
        "progress": row.progress,
        "message": row.message,
        "payload": row.payload,
        "result_dataset_id": row.result_dataset_id,
        "error": row.error,
        "cancel_requested": row.cancel_requested,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


def _claim_pending(session: Session, job_id: str) -> bool:
    result = cast(
        CursorResult[Any],
        session.execute(
            update(ImportJob)
            .where(ImportJob.id == job_id, ImportJob.status == "pending")
            .values(
                status="running",
                stage="validating",
                progress=0.05,
                message="validating source",
                error=None,
                updated_at=datetime.now(UTC),
            )
        ),
    )
    session.commit()
    return result.rowcount == 1


def _set_stage(session: Session, row: ImportJob, stage: str, progress: float, message: str) -> None:
    row.status = "running"
    row.stage = stage
    row.progress = progress
    row.message = message
    row.updated_at = datetime.now(UTC)
    session.commit()


def _mark_runner_start_failed(job_id: str, exc: Exception) -> None:
    session = get_session()
    try:
        row = session.get(ImportJob, job_id)
        if row is None:
            return
        payload = dict(row.payload or {})
        path = str(payload.get("path") or "") or None
        error = f"runner_start_failed: {_error_text(exc, path)}"
        result = cast(
            CursorResult[Any],
            session.execute(
                update(ImportJob)
                .where(ImportJob.id == job_id, ImportJob.status == "running")
                .values(
                    status="failed",
                    stage="failed",
                    message="import runner failed",
                    error=error,
                    updated_at=datetime.now(UTC),
                )
                .execution_options(synchronize_session=False)
            ),
        )
        session.commit()
        if result.rowcount == 1:
            logger.error(
                "import_runner_start_failed",
                extra={"job_id": job_id, "error": error},
            )
    finally:
        session.close()


def _mark_cancelled(session: Session, row: ImportJob) -> ImportJob:
    row.status = "cancelled"
    row.stage = "cancelled"
    row.message = "import cancelled"
    row.updated_at = datetime.now(UTC)
    session.commit()
    session.refresh(row)
    logger.info("import_cancelled", extra={"job_id": row.id})
    return row


def _import_options(raw: Any) -> ImportOptions:
    data = raw if isinstance(raw, dict) else {}
    return ImportOptions(
        encoding=data.get("encoding"),
        delimiter=data.get("delimiter"),
        has_header=data.get("has_header"),
        sheet=data.get("sheet"),
        variable=data.get("variable"),
        shape=data.get("shape"),
        dtype=data.get("dtype"),
        byte_order=data.get("byte_order"),
        raw_offset=int(data.get("raw_offset") or 0),
        sample_rows=int(data.get("sample_rows") or MAX_SAMPLE_ROWS),
        preview_rows=int(data.get("preview_rows") or 20),
    )


def _error_text(exc: Exception, path: str | None = None) -> str:
    from advp.logging_config import redact_text

    text = str(exc)
    marker = "Traceback (most recent call last):"
    index = text.find(marker)
    if index >= 0:
        text = text[:index]
    if path:
        raw = path.replace("\\", "/")
        candidates = {path, raw}
        parent = Path(path).parent
        if str(parent) not in {"", "."}:
            candidates.update({str(parent), parent.as_posix()})
        for candidate in sorted(candidates, key=len, reverse=True):
            if candidate not in {"", ".", "/"}:
                text = text.replace(candidate, "<path>")
    text = redact_text(text).strip()
    if not text:
        text = exc.__class__.__name__
    return text[:2000]
