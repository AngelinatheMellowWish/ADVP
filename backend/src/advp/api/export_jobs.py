"""Background export job endpoints."""

from __future__ import annotations

from pathlib import Path
from typing import Any, NoReturn

from fastapi import APIRouter, BackgroundTasks, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from advp import export_jobs
from advp.api.deps import DbSession
from advp.api.schemas import ExportJobCreate, TargetExportCreate
from advp.config import get_settings
from advp.models import ExportJob

router = APIRouter(tags=["exports"])


def _job_or_404(session: Session, job_id: str) -> ExportJob:
    row = session.get(ExportJob, job_id)
    if row is None:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "export_job_not_found",
                "message": f"export job was not found: {job_id}",
            },
        )
    return row


def _raise_job(exc: export_jobs.ExportJobError) -> NoReturn:
    raise HTTPException(
        status_code=exc.status_code,
        detail={"code": exc.code, "message": str(exc)},
    )


@router.post("/exports", status_code=201)
def create_export(
    payload: ExportJobCreate,
    background_tasks: BackgroundTasks,
    session: DbSession,
) -> dict[str, Any]:
    try:
        row = export_jobs.create_job(
            session,
            kind=payload.kind,
            target_id=payload.target_id,
            format=payload.format,
            options=payload.options,
        )
    except export_jobs.ExportJobError as exc:
        _raise_job(exc)
    background_tasks.add_task(export_jobs.run_job, row.id)
    return export_jobs.job_dict(row)


@router.post("/pipeline-runs/{run_id}/exports", status_code=201)
def create_report_export(
    run_id: str,
    payload: TargetExportCreate,
    background_tasks: BackgroundTasks,
    session: DbSession,
) -> dict[str, Any]:
    try:
        row = export_jobs.create_job(
            session,
            kind="report",
            target_id=run_id,
            format=payload.format,
            options=payload.options,
        )
    except export_jobs.ExportJobError as exc:
        _raise_job(exc)
    background_tasks.add_task(export_jobs.run_job, row.id)
    return export_jobs.job_dict(row)


@router.post("/chart-selections/{selection_id}/exports", status_code=201)
def create_selection_export(
    selection_id: str,
    payload: TargetExportCreate,
    background_tasks: BackgroundTasks,
    session: DbSession,
) -> dict[str, Any]:
    try:
        row = export_jobs.create_job(
            session,
            kind="selection",
            target_id=selection_id,
            format=payload.format,
            options=payload.options,
        )
    except export_jobs.ExportJobError as exc:
        _raise_job(exc)
    background_tasks.add_task(export_jobs.run_job, row.id)
    return export_jobs.job_dict(row)


@router.get("/export-jobs/{job_id}")
def get_export_job(job_id: str, session: DbSession) -> dict[str, Any]:
    return export_jobs.job_dict(_job_or_404(session, job_id))


@router.post("/export-jobs/{job_id}/retry")
def retry_export_job(
    job_id: str,
    background_tasks: BackgroundTasks,
    session: DbSession,
) -> dict[str, Any]:
    row = _job_or_404(session, job_id)
    try:
        export_jobs.retry_job(session, row)
    except export_jobs.ExportJobError as exc:
        _raise_job(exc)
    background_tasks.add_task(export_jobs.run_job, row.id)
    return export_jobs.job_dict(row)


@router.get("/export-jobs/{job_id}/download")
def download_export_job(job_id: str, session: DbSession) -> FileResponse:
    row = _job_or_404(session, job_id)
    if row.status != "succeeded" or not row.output_path:
        raise HTTPException(
            status_code=409,
            detail={"code": "export_not_ready", "message": f"job {job_id} is {row.status}"},
        )
    path = Path(row.output_path).resolve()
    workspace = get_settings().workspace_dir.resolve()
    if workspace not in path.parents or not path.is_file():
        raise HTTPException(
            status_code=404,
            detail={"code": "export_not_found", "message": "export output is missing"},
        )
    media = "application/pdf" if path.suffix.lower() == ".pdf" else "text/html"
    return FileResponse(path, media_type=media, filename=path.name)
