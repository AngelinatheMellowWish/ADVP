"""Background import job endpoints."""

from __future__ import annotations

from typing import Any, NoReturn

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy.orm import Session

from advp import import_jobs
from advp.api.deps import DbSession
from advp.api.schemas import ImportJobCreate, ImportJobDetail
from advp.models import ImportJob
from advp.services import projects as project_service

router = APIRouter(tags=["imports"])


def _job_or_404(session: Session, job_id: str) -> ImportJob:
    row = session.get(ImportJob, job_id)
    if row is None:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "import_job_not_found",
                "message": f"import job was not found: {job_id}",
            },
        )
    return row


def _raise_job(exc: import_jobs.ImportJobError, *, job_id: str | None = None) -> NoReturn:
    detail: dict[str, Any] = {"code": exc.code, "message": str(exc)}
    if job_id is not None:
        detail["job_id"] = job_id
    raise HTTPException(status_code=exc.status_code, detail=detail)


@router.post(
    "/projects/{project_id}/import-jobs",
    response_model=ImportJobDetail,
    status_code=201,
)
def create_import_job(
    project_id: str,
    payload: ImportJobCreate,
    session: DbSession,
) -> dict[str, Any]:
    try:
        row = import_jobs.create_import_job(session, project_id, payload.model_dump())
    except import_jobs.ImportJobError as exc:
        _raise_job(exc)
    started = import_jobs.start_import_job(row.id)
    session.expire_all()
    refreshed = session.get(ImportJob, row.id)
    if refreshed is None:
        raise HTTPException(
            status_code=500,
            detail={
                "code": "import_runner_failed",
                "message": f"import runner failed to start for job {row.id}",
                "job_id": row.id,
            },
        )
    if started == "failed":
        raise HTTPException(
            status_code=500,
            detail={
                "code": "import_runner_failed",
                "message": f"import runner failed to start for job {refreshed.id}",
                "job_id": refreshed.id,
            },
        )
    return import_jobs.job_dict(refreshed)


@router.get("/import-jobs", response_model=list[ImportJobDetail])
def list_import_jobs(
    session: DbSession,
    project_id: str = Query(...),
    limit: int = Query(default=50, ge=1, le=200),
) -> list[dict[str, Any]]:
    if project_service.get_project(session, project_id) is None:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "project_not_found",
                "message": f"project was not found: {project_id}",
            },
        )
    return [
        import_jobs.job_dict(row)
        for row in import_jobs.list_import_jobs(session, project_id, limit)
    ]


@router.get("/import-jobs/{job_id}", response_model=ImportJobDetail)
def get_import_job(job_id: str, session: DbSession) -> dict[str, Any]:
    return import_jobs.job_dict(_job_or_404(session, job_id))


@router.post("/import-jobs/{job_id}/cancel", response_model=ImportJobDetail)
def cancel_import_job(job_id: str, session: DbSession) -> dict[str, Any]:
    _job_or_404(session, job_id)
    try:
        row = import_jobs.cancel_import_job(session, job_id)
    except import_jobs.ImportJobError as exc:
        _raise_job(exc)
    return import_jobs.job_dict(row)


@router.post("/import-jobs/{job_id}/retry", response_model=ImportJobDetail)
def retry_import_job(job_id: str, session: DbSession) -> dict[str, Any]:
    _job_or_404(session, job_id)
    try:
        row = import_jobs.retry_import_job(session, job_id)
    except import_jobs.ImportJobError as exc:
        _raise_job(exc, job_id=job_id)
    return import_jobs.job_dict(row)
