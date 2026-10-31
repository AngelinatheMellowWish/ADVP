"""Pipeline run creation, inspection, and lifecycle endpoints."""

from __future__ import annotations

import json
import time
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, NoReturn

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query, Response
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy.orm import Session

from advp import audit, pipeline_events
from advp import exports as export_service
from advp import reports as report_service
from advp import trace as trace_service
from advp.api.deps import DbSession
from advp.api.schemas import (
    PipelineRunCreate,
    PipelineRunDetail,
    PipelineRunSummary,
    ReportRegenerate,
)
from advp.db import get_session
from advp.llm import providers as provider_service
from advp.models import ChartSelection, Dataset, PipelineRun
from advp.pipelines import (
    TERMINAL_RUN_STATUSES,
    PipelineStateError,
    cancel_run,
    create_run,
    get_run,
    list_dataset_runs,
    list_steps,
    pause_run,
    pipeline_detail,
    pipeline_summary,
    rerun_from_step,
    resume_run,
    retry_step,
    run_pipeline,
)

router = APIRouter(tags=["pipelines"])


def _dataset_or_404(session: Session, dataset_id: str) -> Dataset:
    dataset = session.get(Dataset, dataset_id)
    if dataset is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "dataset_not_found", "message": f"dataset was not found: {dataset_id}"},
        )
    return dataset


def _run_or_404(session: Session, run_id: str) -> PipelineRun:
    run = get_run(session, run_id)
    if run is None:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "pipeline_run_not_found",
                "message": f"pipeline run was not found: {run_id}",
            },
        )
    return run


def _raise_state(exc: PipelineStateError) -> NoReturn:
    raise HTTPException(
        status_code=exc.status_code,
        detail={"code": exc.code, "message": str(exc)},
    )


def _report_step_or_404(session: Session, run: PipelineRun) -> Any:
    step = next((item for item in list_steps(session, run.id) if item.key == "report"), None)
    if step is None or step.status != "succeeded":
        raise HTTPException(
            status_code=404,
            detail={"code": "report_not_ready", "message": "the pipeline report is not ready"},
        )
    return step


def _regenerate_report(
    session: Session,
    run: PipelineRun,
    *,
    language: str = "zh",
    template: str = "standard",
    conclusion: str | None = None,
    include_chart: bool = True,
) -> dict[str, Any]:
    steps = list_steps(session, run.id)
    working_id = str(run.options.get("working_dataset_id") or run.dataset_id)
    dataset = session.get(Dataset, working_id)
    if dataset is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "dataset_not_found", "message": "working dataset was not found"},
        )
    prior = {item.key: item.output_json for item in steps if item.status == "succeeded"}
    selection_id = (prior.get("selection") or {}).get("selection_id")
    selection = session.get(ChartSelection, str(selection_id)) if selection_id is not None else None
    chart_image = None
    chart_error = None
    if include_chart and selection is not None:
        target = report_service.report_directory(run) / f"report_{run.id}_chart.png"
        try:
            chart_image = export_service.capture_selection_png(session, selection, target)
        except Exception as exc:
            chart_error = str(exc)
    bundle = report_service.write_report_bundle(
        dataset,
        run,
        prior,
        selection,
        steps,
        language=language,
        template=template,
        conclusion=conclusion,
        chart_image=chart_image,
        chart_note=chart_error,
    )
    step = next((item for item in steps if item.key == "report"), None)
    if step is not None:
        step.status = "succeeded"
        step.error = None
        step.finished_at = datetime.now(UTC)
        step.output_json = {
            **(step.output_json or {}),
            "path": bundle["md_path"],
            "html_path": bundle["html_path"],
            "manifest_path": bundle["manifest_path"],
            "chart_path": bundle["chart_path"],
            "chart_error": chart_error,
            "selection_id": selection.id if selection is not None else None,
            "bytes": bundle["bytes"],
            "html_bytes": bundle["html_bytes"],
            "language": language,
            "template": template,
        }
        session.commit()
    bundle["chart_error"] = chart_error
    return bundle


@router.post(
    "/datasets/{dataset_id}/pipeline-runs",
    response_model=PipelineRunDetail,
    status_code=201,
)
def create_pipeline_run(
    dataset_id: str,
    payload: PipelineRunCreate,
    background_tasks: BackgroundTasks,
    session: DbSession,
) -> dict[str, Any]:
    dataset = _dataset_or_404(session, dataset_id)
    if payload.provider_id and provider_service.get_provider(session, payload.provider_id) is None:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "provider_not_found",
                "message": f"provider was not found: {payload.provider_id}",
            },
        )
    options = payload.model_dump(exclude={"auto_start"}, exclude_none=True)
    run = create_run(session, dataset, options=options)
    if payload.auto_start:
        background_tasks.add_task(run_pipeline, run.id)
    return pipeline_detail(session, run)


@router.get("/datasets/{dataset_id}/pipeline-runs", response_model=list[PipelineRunSummary])
def list_pipeline_runs(
    dataset_id: str,
    session: DbSession,
    limit: int = Query(default=20, ge=1, le=100),
) -> list[dict[str, Any]]:
    _dataset_or_404(session, dataset_id)
    return [pipeline_summary(run) for run in list_dataset_runs(session, dataset_id, limit=limit)]


@router.get("/pipeline-runs/{run_id}", response_model=PipelineRunDetail)
def get_pipeline_run(run_id: str, session: DbSession) -> dict[str, Any]:
    return pipeline_detail(session, _run_or_404(session, run_id))


EVENT_POLL_SECONDS = 0.5
EVENT_HEARTBEAT_POLLS = 30


@router.get("/pipeline-runs/{run_id}/events")
def stream_pipeline_events(
    run_id: str,
    session: DbSession,
    since: int = Query(default=0, ge=0),
) -> StreamingResponse:
    """Stream persisted run events; `since` replays events after that sequence."""
    _run_or_404(session, run_id)
    return StreamingResponse(
        _event_stream(run_id, since),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def _event_stream(run_id: str, since: int) -> Iterator[str]:
    cursor = since
    idle = 0
    while True:
        session = get_session()
        try:
            rows = pipeline_events.list_events(session, run_id, since=cursor)
            run = session.get(PipelineRun, run_id)
            terminal = run is None or run.status in TERMINAL_RUN_STATUSES
        finally:
            session.close()
        if rows:
            for row in rows:
                cursor = row.seq
                payload = json.dumps(
                    pipeline_events.event_dict(row),
                    ensure_ascii=False,
                    default=str,
                )
                yield f"id: {row.seq}\nevent: {row.type}\ndata: {payload}\n\n"
            idle = 0
            continue
        if terminal:
            return
        idle += 1
        if idle % EVENT_HEARTBEAT_POLLS == 0:
            yield ": heartbeat\n\n"
        time.sleep(EVENT_POLL_SECONDS)


@router.get("/pipeline-runs/{run_id}/trace")
def get_pipeline_trace(run_id: str, session: DbSession) -> dict[str, Any]:
    run = _run_or_404(session, run_id)
    return trace_service.build_trace(session, run)


@router.get("/pipeline-runs/{run_id}/trace/export")
def export_pipeline_trace(
    run_id: str,
    session: DbSession,
    format: str = Query(default="json", pattern="^(json|markdown)$"),
) -> Response:
    run = _run_or_404(session, run_id)
    trace = trace_service.build_trace(session, run)
    if format == "markdown":
        return Response(
            content=trace_service.trace_markdown(trace),
            media_type="text/markdown; charset=utf-8",
            headers={
                "Content-Disposition": f'attachment; filename="trace_{run.id}.md"',
            },
        )
    return Response(
        content=json.dumps(trace, ensure_ascii=False, indent=2),
        media_type="application/json",
        headers={
            "Content-Disposition": f'attachment; filename="trace_{run.id}.json"',
        },
    )


@router.get("/pipeline-runs/{run_id}/compare/{other_id}")
def compare_pipeline_runs(
    run_id: str,
    other_id: str,
    session: DbSession,
) -> dict[str, Any]:
    run = _run_or_404(session, run_id)
    other = _run_or_404(session, other_id)
    return trace_service.compare_runs(session, run, other)


def _report_export_name(
    session: Session,
    run: PipelineRun,
    step: Any,
    extension: str,
) -> str:
    working_id = str(run.options.get("working_dataset_id") or run.dataset_id)
    dataset = session.get(Dataset, working_id)
    if dataset is None:
        return f"report_{run.id}.{extension}"
    selection_id = (step.output_json or {}).get("selection_id")
    selection = session.get(ChartSelection, str(selection_id)) if selection_id is not None else None
    return report_service.export_filename(dataset, selection, extension)


@router.get("/pipeline-runs/{run_id}/report/manifest")
def get_report_manifest(run_id: str, session: DbSession) -> dict[str, Any]:
    run = _run_or_404(session, run_id)
    step = _report_step_or_404(session, run)
    path = Path(str((step.output_json or {}).get("manifest_path") or ""))
    if not path.is_file():
        bundle = _regenerate_report(session, run, language="zh", include_chart=False)
        path = Path(str(bundle["manifest_path"]))
    manifest: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return manifest


@router.get("/pipeline-runs/{run_id}/report")
def get_pipeline_report(
    run_id: str,
    session: DbSession,
    format: str = Query(default="md", pattern="^(md|html|pdf)$"),
) -> Response:
    run = _run_or_404(session, run_id)
    step = _report_step_or_404(session, run)
    output = step.output_json or {}
    if format == "md":
        path = Path(str(output.get("path") or ""))
        if not path.is_file():
            bundle = _regenerate_report(session, run, language="zh", include_chart=False)
            path = Path(str(bundle["md_path"]))
        return Response(
            content=path.read_text(encoding="utf-8"),
            media_type="text/markdown; charset=utf-8",
            headers={
                "Content-Disposition": (
                    f'attachment; filename="{_report_export_name(session, run, step, "md")}"'
                )
            },
        )
    if format == "html":
        path = Path(str(output.get("html_path") or ""))
        if not path.is_file():
            bundle = _regenerate_report(session, run, language="zh", include_chart=False)
            path = Path(str(bundle["html_path"]))
        return Response(
            content=path.read_text(encoding="utf-8"),
            media_type="text/html; charset=utf-8",
            headers={
                "Content-Disposition": (
                    f'attachment; filename="{_report_export_name(session, run, step, "html")}"'
                )
            },
        )
    html_path = Path(str(output.get("html_path") or ""))
    if not html_path.is_file():
        bundle = _regenerate_report(session, run, language="zh", include_chart=False)
        html_path = Path(str(bundle["html_path"]))
    try:
        pdf_path = export_service.build_report_pdf(html_path)
    except export_service.ExportError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail={"code": exc.code, "message": str(exc)},
        ) from exc
    return FileResponse(
        pdf_path,
        media_type="application/pdf",
        filename=_report_export_name(session, run, step, "pdf"),
    )


@router.post("/pipeline-runs/{run_id}/report")
def regenerate_pipeline_report(
    run_id: str,
    payload: ReportRegenerate,
    session: DbSession,
) -> dict[str, Any]:
    run = _run_or_404(session, run_id)
    bundle = _regenerate_report(
        session,
        run,
        language=payload.language,
        template=payload.template,
        conclusion=payload.conclusion,
        include_chart=payload.include_chart,
    )
    audit.record_event(
        session,
        "report_regenerated",
        project_id=run.project_id,
        target_type="pipeline_run",
        target_id=run.id,
        detail={
            "language": payload.language,
            "template": payload.template,
            "include_chart": payload.include_chart,
        },
    )
    return {
        "run": pipeline_detail(session, run),
        "report": {
            "markdown": f"/api/pipeline-runs/{run.id}/report?format=md",
            "html": f"/api/pipeline-runs/{run.id}/report?format=html",
            "pdf": f"/api/pipeline-runs/{run.id}/report?format=pdf",
            **bundle,
        },
    }


@router.post("/pipeline-runs/{run_id}/pause", response_model=PipelineRunDetail)
def pause_pipeline_run(run_id: str, session: DbSession) -> dict[str, Any]:
    run = _run_or_404(session, run_id)
    try:
        pause_run(session, run)
    except PipelineStateError as exc:
        _raise_state(exc)
    return pipeline_detail(session, run)


@router.post("/pipeline-runs/{run_id}/resume", response_model=PipelineRunDetail)
def resume_pipeline_run(
    run_id: str,
    background_tasks: BackgroundTasks,
    session: DbSession,
) -> dict[str, Any]:
    run = _run_or_404(session, run_id)
    try:
        resume_run(session, run)
    except PipelineStateError as exc:
        _raise_state(exc)
    background_tasks.add_task(run_pipeline, run.id)
    return pipeline_detail(session, run)


@router.post("/pipeline-runs/{run_id}/cancel", response_model=PipelineRunDetail)
def cancel_pipeline_run(run_id: str, session: DbSession) -> dict[str, Any]:
    run = _run_or_404(session, run_id)
    try:
        cancel_run(session, run)
    except PipelineStateError as exc:
        _raise_state(exc)
    return pipeline_detail(session, run)


@router.post("/pipeline-runs/{run_id}/steps/{step_id}/retry", response_model=PipelineRunDetail)
def retry_pipeline_step(
    run_id: str,
    step_id: str,
    background_tasks: BackgroundTasks,
    session: DbSession,
) -> dict[str, Any]:
    run = _run_or_404(session, run_id)
    step = next((item for item in list_steps(session, run.id) if item.id == step_id), None)
    if step is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "pipeline_step_not_found", "message": f"step was not found: {step_id}"},
        )
    try:
        retry_step(session, run, step)
    except PipelineStateError as exc:
        _raise_state(exc)
    background_tasks.add_task(run_pipeline, run.id)
    return pipeline_detail(session, run)


@router.post(
    "/pipeline-runs/{run_id}/steps/{step_id}/rerun",
    response_model=PipelineRunDetail,
    status_code=201,
)
def rerun_pipeline_step(
    run_id: str,
    step_id: str,
    background_tasks: BackgroundTasks,
    session: DbSession,
) -> dict[str, Any]:
    run = _run_or_404(session, run_id)
    step = next((item for item in list_steps(session, run.id) if item.id == step_id), None)
    if step is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "pipeline_step_not_found", "message": f"step was not found: {step_id}"},
        )
    try:
        child = rerun_from_step(session, run, step)
    except PipelineStateError as exc:
        _raise_state(exc)
    audit.record_event(
        session,
        "pipeline_rerun",
        project_id=run.project_id,
        target_type="pipeline_run",
        target_id=child.id,
        detail={"source_run_id": run.id, "from_step": step.key},
    )
    background_tasks.add_task(run_pipeline, child.id)
    return pipeline_detail(session, child)
