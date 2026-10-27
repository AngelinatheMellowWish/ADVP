"""Persisted background export jobs for reports and chart packages."""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from advp import exports as export_service
from advp import reports as report_service
from advp.db import get_session
from advp.models import ChartSelection, Dataset, ExportJob, PipelineRun

logger = logging.getLogger("advp.export")

KINDS = {"report", "selection"}
FORMATS = {"html", "pdf"}


class ExportJobError(Exception):
    """Invalid export job or unavailable output."""

    def __init__(self, code: str, message: str, status_code: int = 422) -> None:
        super().__init__(message)
        self.code = code
        self.status_code = status_code


def create_job(
    session: Session,
    *,
    kind: str,
    target_id: str,
    format: str,
    options: dict[str, Any] | None = None,
) -> ExportJob:
    """Create a pending export job after validating the target."""
    if kind not in KINDS:
        raise ExportJobError("invalid_export_kind", f"unsupported export kind: {kind}", 422)
    if format not in FORMATS:
        raise ExportJobError("invalid_export_format", f"unsupported format: {format}", 422)
    project_id: str | None = None
    if kind == "report":
        run = session.get(PipelineRun, target_id)
        if run is None:
            raise ExportJobError("pipeline_run_not_found", "pipeline run was not found", 404)
        project_id = run.project_id
    else:
        selection = session.get(ChartSelection, target_id)
        if selection is None:
            raise ExportJobError("chart_selection_not_found", "selection was not found", 404)
        project_id = selection.project_id
    row = ExportJob(
        id=uuid.uuid4().hex,
        kind=kind,
        project_id=project_id,
        target_id=target_id,
        format=format,
        options_json=options or {},
        status="pending",
    )
    session.add(row)
    session.commit()
    session.refresh(row)
    return row


def run_job(job_id: str) -> None:
    """Execute a job in the background with its own session."""
    session = get_session()
    try:
        execute_job(session, job_id)
    finally:
        session.close()


def execute_job(session: Session, job_id: str) -> ExportJob:
    """Execute one pending/failed job and persist its outcome."""
    row = session.get(ExportJob, job_id)
    if row is None:
        raise ExportJobError("export_job_not_found", "export job was not found", 404)
    if row.status not in {"pending", "failed"}:
        return row
    row.status = "running"
    row.attempts += 1
    row.started_at = datetime.now(UTC)
    row.finished_at = None
    row.error = None
    session.commit()
    logger.info(
        "export_started",
        extra={"job_id": row.id, "kind": row.kind, "format": row.format, "attempt": row.attempts},
    )
    try:
        output = _execute(session, row)
    except Exception as exc:
        row.status = "failed"
        row.error = _redact(str(exc))
        row.finished_at = datetime.now(UTC)
        session.commit()
        logger.error(
            "export_failed",
            extra={"job_id": row.id, "kind": row.kind, "format": row.format, "error": row.error},
        )
        return row
    row.status = "succeeded"
    row.output_path = str(output)
    row.finished_at = datetime.now(UTC)
    session.commit()
    session.refresh(row)
    logger.info(
        "export_succeeded",
        extra={"job_id": row.id, "kind": row.kind, "format": row.format},
    )
    return row


def retry_job(session: Session, row: ExportJob) -> ExportJob:
    """Reset a failed job to pending so it can be scheduled again."""
    if row.status != "failed":
        raise ExportJobError("export_job_not_failed", f"job {row.id} is not failed", 409)
    row.status = "pending"
    row.error = None
    row.finished_at = None
    session.commit()
    session.refresh(row)
    return row


def job_dict(row: ExportJob) -> dict[str, Any]:
    """Serialize a job for API responses."""
    return {
        "id": row.id,
        "kind": row.kind,
        "project_id": row.project_id,
        "target_id": row.target_id,
        "format": row.format,
        "status": row.status,
        "attempts": row.attempts,
        "error": row.error,
        "output_path": row.output_path,
        "created_at": row.created_at,
        "started_at": row.started_at,
        "finished_at": row.finished_at,
        "download_url": f"/api/export-jobs/{row.id}/download"
        if row.status == "succeeded"
        else None,
    }


def _execute(session: Session, row: ExportJob) -> Path:
    if row.kind == "selection":
        selection = session.get(ChartSelection, row.target_id)
        if selection is None:
            raise ExportJobError("chart_selection_not_found", "selection was not found", 404)
        if row.format == "html":
            return export_service.build_single_file_html(session, selection)
        return export_service.build_pdf(session, selection)
    run = session.get(PipelineRun, row.target_id)
    if run is None:
        raise ExportJobError("pipeline_run_not_found", "pipeline run was not found", 404)
    html_path = _ensure_report_html(session, run)
    if row.format == "html":
        return html_path
    return export_service.build_report_pdf(html_path)


def _ensure_report_html(session: Session, run: PipelineRun) -> Path:
    steps = list_steps(session, run)
    report_step = next((step for step in steps if step.key == "report"), None)
    html_value = (report_step.output_json or {}).get("html_path") if report_step else None
    if isinstance(html_value, str) and Path(html_value).is_file():
        return Path(html_value)
    working_id = str(run.options.get("working_dataset_id") or run.dataset_id)
    dataset = session.get(Dataset, working_id)
    if dataset is None:
        raise ExportJobError("dataset_not_found", "working dataset was not found", 404)
    prior = {step.key: step.output_json for step in steps if step.status == "succeeded"}
    selection_id = (prior.get("selection") or {}).get("selection_id")
    selection = session.get(ChartSelection, str(selection_id)) if selection_id is not None else None
    bundle = report_service.write_report_bundle(
        dataset,
        run,
        prior,
        selection,
        steps,
        language=str(run.options.get("report_language") or "zh"),
        template=str(run.options.get("report_template") or "standard"),
        conclusion=str(run.options.get("report_conclusion") or "") or None,
        chart_image=None,
    )
    if report_step is not None:
        report_step.output_json = {
            **(report_step.output_json or {}),
            "path": bundle["md_path"],
            "html_path": bundle["html_path"],
            "bytes": bundle["bytes"],
            "html_bytes": bundle["html_bytes"],
        }
        session.commit()
    return Path(str(bundle["html_path"]))


def list_steps(session: Session, run: PipelineRun) -> list[Any]:
    """Local import helper to avoid a module-level pipelines cycle."""
    from advp.pipelines import list_steps as pipeline_steps

    return pipeline_steps(session, run.id)


def _redact(value: str) -> str:
    lowered = value.lower()
    for key in ("api_key", "apikey", "token", "secret", "password", "authorization"):
        if key in lowered:
            return "export failed; see application logs"
    return value
