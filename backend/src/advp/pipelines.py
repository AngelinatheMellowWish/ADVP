"""Persisted pipeline runs, steps, execution, and lifecycle controls."""

from __future__ import annotations

import logging
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from advp import analysis as analysis_service
from advp import cleaning as cleaning_service
from advp import exports as export_service
from advp import reports as report_service
from advp.charts import render as render_service
from advp.charts import selection as selection_service
from advp.charts.registry import ChartIntent
from advp.charts.scoring import score_candidates
from advp.charts.selector import (
    ArrayContext,
    TableContext,
    build_array_context,
    build_table_context,
    select_array_candidates,
    select_table_candidates,
)
from advp.db import get_session
from advp.models import Dataset, PipelineRun, PipelineStep

logger = logging.getLogger("advp.pipeline")

RUN_STATUSES = {"pending", "running", "paused", "succeeded", "failed", "cancelled"}
TERMINAL_RUN_STATUSES = {"succeeded", "failed", "cancelled"}

STEP_DEFINITIONS: tuple[tuple[str, str], ...] = (
    ("profile", "数据画像"),
    ("clean", "数据清洗"),
    ("candidates", "规则候选"),
    ("analyze", "分析摘要"),
    ("selection", "AI 选型"),
    ("render", "图表渲染"),
    ("report", "Markdown 报告"),
)
PLACEHOLDER_STEPS: set[str] = set()


class PipelineStateError(Exception):
    """Invalid lifecycle transition or missing pipeline resource."""

    def __init__(self, code: str, message: str, status_code: int = 409) -> None:
        super().__init__(message)
        self.code = code
        self.status_code = status_code


StepHandler = Callable[
    [Session, Dataset, PipelineRun, PipelineStep, dict[str, dict[str, Any]]],
    dict[str, Any],
]


def create_run(
    session: Session,
    dataset: Dataset,
    *,
    options: dict[str, Any] | None = None,
) -> PipelineRun:
    """Create a pending run and its ordered steps."""
    run = PipelineRun(
        id=uuid.uuid4().hex,
        dataset_id=dataset.id,
        project_id=dataset.project_id,
        status="pending",
        options=options or {},
    )
    session.add(run)
    session.flush()
    for position, (key, name) in enumerate(STEP_DEFINITIONS):
        session.add(
            PipelineStep(
                id=uuid.uuid4().hex,
                run_id=run.id,
                key=key,
                name=name,
                position=position,
                status="pending",
                placeholder=key in PLACEHOLDER_STEPS,
            )
        )
    session.commit()
    session.refresh(run)
    return run


def get_run(session: Session, run_id: str) -> PipelineRun | None:
    """Return one run or None."""
    return session.get(PipelineRun, run_id)


def list_dataset_runs(session: Session, dataset_id: str, *, limit: int = 20) -> list[PipelineRun]:
    """Return recent runs for a dataset, newest first."""
    statement = (
        select(PipelineRun)
        .where(PipelineRun.dataset_id == dataset_id)
        .order_by(PipelineRun.created_at.desc())
        .limit(limit)
    )
    return list(session.scalars(statement).all())


def list_steps(session: Session, run_id: str) -> list[PipelineStep]:
    """Return ordered steps for a run."""
    statement = (
        select(PipelineStep).where(PipelineStep.run_id == run_id).order_by(PipelineStep.position)
    )
    return list(session.scalars(statement).all())


def pause_run(session: Session, run: PipelineRun) -> PipelineRun:
    """Request a cooperative pause or pause a pending run immediately."""
    if run.status in TERMINAL_RUN_STATUSES:
        raise PipelineStateError("run_terminal", f"run {run.id} is already {run.status}")
    run.pause_requested = True
    if run.status == "pending":
        run.status = "paused"
    session.commit()
    session.refresh(run)
    return run


def resume_run(session: Session, run: PipelineRun) -> PipelineRun:
    """Resume a paused run; the caller schedules execution."""
    if run.status != "paused":
        raise PipelineStateError("run_not_paused", f"run {run.id} is not paused")
    run.pause_requested = False
    run.status = "running"
    run.error = None
    run.finished_at = None
    session.commit()
    session.refresh(run)
    return run


def cancel_run(session: Session, run: PipelineRun) -> PipelineRun:
    """Request cancellation or cancel a non-running run immediately."""
    if run.status in TERMINAL_RUN_STATUSES:
        raise PipelineStateError("run_terminal", f"run {run.id} is already {run.status}")
    run.cancel_requested = True
    if run.status in {"pending", "paused"}:
        _mark_cancelled(session, run)
    session.commit()
    session.refresh(run)
    return run


def rerun_from_step(
    session: Session,
    run: PipelineRun,
    step: PipelineStep,
) -> PipelineRun:
    """Create a child run that reuses upstream outputs from ``run``."""
    if step.run_id != run.id:
        raise PipelineStateError("step_not_found", "step does not belong to this run", 404)
    if run.status in {"pending", "running", "paused"}:
        raise PipelineStateError(
            "run_active",
            f"run {run.id} is {run.status}; finish, fail, or cancel it before rerunning",
        )
    steps = list_steps(session, run.id)
    upstream = [item for item in steps if item.position < step.position]
    if any(item.status not in {"succeeded", "skipped"} for item in upstream):
        raise PipelineStateError(
            "upstream_not_succeeded",
            "all upstream steps must have succeeded before rerunning from this step",
        )
    child = PipelineRun(
        id=uuid.uuid4().hex,
        dataset_id=run.dataset_id,
        project_id=run.project_id,
        parent_run_id=run.id,
        status="pending",
        options={
            **run.options,
            "working_dataset_id": run.options.get("working_dataset_id", run.dataset_id),
            "rerun_from_step": step.key,
            "rerun_source_run_id": run.id,
        },
    )
    session.add(child)
    session.flush()
    for item in steps:
        copied = item.position < step.position
        session.add(
            PipelineStep(
                id=uuid.uuid4().hex,
                run_id=child.id,
                key=item.key,
                name=item.name,
                position=item.position,
                status=item.status if copied else "pending",
                attempts=item.attempts if copied else 0,
                placeholder=item.placeholder,
                output_json=item.output_json if copied else {},
                error=item.error if copied else None,
                started_at=item.started_at if copied else None,
                finished_at=item.finished_at if copied else None,
            )
        )
    session.commit()
    session.refresh(child)
    return child


def retry_step(session: Session, run: PipelineRun, step: PipelineStep) -> PipelineRun:
    """Reset a failed step and all downstream steps to pending."""
    if step.run_id != run.id:
        raise PipelineStateError("step_not_found", "step does not belong to this run", 404)
    if step.status != "failed":
        raise PipelineStateError("step_not_failed", f"step {step.key} is not failed")
    steps = list_steps(session, run.id)
    for item in steps:
        if item.position >= step.position:
            item.status = "pending"
            item.output_json = {}
            item.error = None
            item.started_at = None
            item.finished_at = None
            item.attempts = 0
    run.status = "running"
    run.current_step = None
    run.error = None
    run.finished_at = None
    run.pause_requested = False
    run.cancel_requested = False
    session.commit()
    session.refresh(run)
    return run


def execute_run(session: Session, run_id: str) -> PipelineRun:
    """Execute pending steps until completion, pause, cancel, or failure."""
    run = session.get(PipelineRun, run_id)
    if run is None:
        raise PipelineStateError("run_not_found", f"pipeline run was not found: {run_id}", 404)
    logger.info(
        "run_started",
        extra={"run_id": run.id, "dataset_id": run.dataset_id, "project_id": run.project_id},
    )

    while True:
        session.refresh(run)
        if run.status in TERMINAL_RUN_STATUSES:
            return run
        if run.cancel_requested:
            _mark_cancelled(session, run)
            session.commit()
            return run
        if run.pause_requested:
            run.status = "paused"
            session.commit()
            return run

        steps = list_steps(session, run.id)
        step = next((item for item in steps if item.status == "pending"), None)
        if step is None:
            run.status = "succeeded"
            run.current_step = None
            run.finished_at = datetime.now(UTC)
            session.commit()
            logger.info(
                "run_succeeded",
                extra={
                    "run_id": run.id,
                    "duration_ms": _duration_ms(run.started_at, run.finished_at),
                },
            )
            return run

        working_dataset_id = str(run.options.get("working_dataset_id") or run.dataset_id)
        dataset = session.get(Dataset, working_dataset_id)
        if dataset is None:
            run.status = "failed"
            run.error = f"working dataset {working_dataset_id} no longer exists"
            run.finished_at = datetime.now(UTC)
            session.commit()
            return run

        run.status = "running"
        run.started_at = run.started_at or datetime.now(UTC)
        run.current_step = step.key
        step.status = "running"
        step.attempts += 1
        step.started_at = datetime.now(UTC)
        step.error = None
        session.commit()
        logger.info(
            "step_started",
            extra={"run_id": run.id, "step": step.key, "attempt": step.attempts},
        )

        prior = {
            item.key: item.output_json
            for item in steps
            if item.position < step.position and item.status == "succeeded"
        }
        handler = STEP_HANDLERS.get(step.key)
        try:
            if handler is None:
                raise PipelineStateError("unknown_step", f"no handler for step {step.key}")
            output = handler(session, dataset, run, step, prior)
        except Exception as exc:
            step.status = "failed"
            step.error = str(exc)
            step.finished_at = datetime.now(UTC)
            run.status = "failed"
            run.error = str(exc)
            run.finished_at = datetime.now(UTC)
            session.commit()
            logger.error(
                "step_failed",
                extra={
                    "run_id": run.id,
                    "step": step.key,
                    "attempt": step.attempts,
                    "error": str(exc),
                },
            )
            return run

        step.status = "succeeded"
        step.output_json = output
        step.finished_at = datetime.now(UTC)
        session.commit()
        logger.info(
            "step_succeeded",
            extra={
                "run_id": run.id,
                "step": step.key,
                "attempt": step.attempts,
                "duration_ms": _duration_ms(step.started_at, step.finished_at),
            },
        )

        session.refresh(run)
        if run.cancel_requested:
            _mark_cancelled(session, run)
            session.commit()
            return run
        if run.pause_requested:
            run.status = "paused"
            session.commit()
            return run


def run_pipeline(run_id: str) -> None:
    """Background entry point using its own database session."""
    session = get_session()
    try:
        execute_run(session, run_id)
    finally:
        session.close()


def pipeline_summary(run: PipelineRun) -> dict[str, Any]:
    """Compact list representation."""
    return {
        "id": run.id,
        "dataset_id": run.dataset_id,
        "status": run.status,
        "current_step": run.current_step,
        "error": run.error,
        "created_at": run.created_at,
        "finished_at": run.finished_at,
    }


def pipeline_detail(session: Session, run: PipelineRun) -> dict[str, Any]:
    """Full run detail with ordered steps."""
    return {
        "id": run.id,
        "dataset_id": run.dataset_id,
        "project_id": run.project_id,
        "parent_run_id": run.parent_run_id,
        "status": run.status,
        "current_step": run.current_step,
        "pause_requested": run.pause_requested,
        "cancel_requested": run.cancel_requested,
        "options": run.options,
        "error": run.error,
        "created_at": run.created_at,
        "started_at": run.started_at,
        "finished_at": run.finished_at,
        "steps": [
            {
                "id": step.id,
                "key": step.key,
                "name": step.name,
                "position": step.position,
                "status": step.status,
                "attempts": step.attempts,
                "placeholder": step.placeholder,
                "output": step.output_json,
                "error": step.error,
                "started_at": step.started_at,
                "finished_at": step.finished_at,
            }
            for step in list_steps(session, run.id)
        ],
    }


def _mark_cancelled(session: Session, run: PipelineRun) -> None:
    run.status = "cancelled"
    run.finished_at = datetime.now(UTC)
    for step in list_steps(session, run.id):
        if step.status == "pending":
            step.status = "skipped"
            step.finished_at = datetime.now(UTC)


def _profile_step(
    session: Session,
    dataset: Dataset,
    run: PipelineRun,
    step: PipelineStep,
    prior: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    profile = dataset.profile_json or {}
    if not profile:
        raise PipelineStateError("missing_profile", "dataset has no profile", 422)
    summary = profile.get("summary") or {}
    return {
        "quality_score": profile.get("quality_score"),
        "row_count": dataset.row_count,
        "column_count": dataset.column_count,
        "sampled": dataset.sampled,
        "missing_cells": summary.get("missing_cells"),
        "issue_counts": summary.get("issue_counts") or {},
    }


def _clean_step(
    session: Session,
    dataset: Dataset,
    run: PipelineRun,
    step: PipelineStep,
    prior: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    steps = run.options.get("clean_steps") or []
    if not steps:
        return {
            "skipped": True,
            "reason": "no clean_steps supplied",
            "working_dataset_id": run.dataset_id,
        }
    try:
        cleaning_run = cleaning_service.clean_dataset(
            session,
            dataset,
            list(steps),
            confirm_high_risk=bool(run.options.get("confirm_high_risk")),
        )
    except cleaning_service.CleanError as exc:
        raise PipelineStateError(exc.code, str(exc), exc.status_code) from exc
    run.options = {
        **run.options,
        "working_dataset_id": cleaning_run.derived_dataset_id,
    }
    session.commit()
    return {
        "skipped": False,
        "derived_dataset_id": cleaning_run.derived_dataset_id,
        "cleaning_run_id": cleaning_run.id,
        "before_rows": cleaning_run.before_rows,
        "after_rows": cleaning_run.after_rows,
        "truncated": cleaning_run.truncated,
        "working_dataset_id": cleaning_run.derived_dataset_id,
    }


def _candidates_step(
    session: Session,
    dataset: Dataset,
    run: PipelineRun,
    step: PipelineStep,
    prior: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    intent = _intent(run)
    context: TableContext | ArrayContext
    if dataset.kind == "table":
        table_context = build_table_context(
            dataset.schema_json,
            row_count=dataset.row_count,
            sampled=dataset.sampled,
            is_stream=str(dataset.options.get("source_kind") or "") in {"websocket", "kafka"},
        )
        candidates = select_table_candidates(table_context, intent).candidates
        context = table_context
    elif dataset.kind == "array":
        schema = dataset.schema_json
        array_context = build_array_context(
            variable=str(schema.get("variable", dataset.name)),
            shape=schema.get("shape", []),
            dims=schema.get("dims", []),
            dtype=str(schema.get("dtype", "")),
            units=schema.get("units"),
            sampled=dataset.sampled,
            format=dataset.format,
        )
        candidates = select_array_candidates(array_context, intent).candidates
        context = array_context
    else:
        raise PipelineStateError("unsupported_kind", f"dataset kind {dataset.kind!r}")
    scored = score_candidates(candidates, context, intent)
    return {
        "candidate_count": len(scored),
        "top": [
            {
                "chart_id": item.candidate.spec.id,
                "score": item.total,
                "dimensions": item.dimensions,
            }
            for item in scored[:5]
        ],
    }


def _analyze_step(
    session: Session,
    dataset: Dataset,
    run: PipelineRun,
    step: PipelineStep,
    prior: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    analysis = analysis_service.compute_and_store(session, dataset)
    return {
        "summary": analysis.get("summary"),
        "sample_size": analysis.get("sample_size"),
        "sampled": analysis.get("sampled"),
        "analysis": analysis,
    }


def _selection_step(
    session: Session,
    dataset: Dataset,
    run: PipelineRun,
    step: PipelineStep,
    prior: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    provider_id = run.options.get("provider_id")
    row = selection_service.create_chart_selection(
        session,
        dataset,
        intent=_intent(run),
        provider_id=provider_id,
        max_reselects=int(run.options.get("max_reselects", 2)),
        run_id=run.id,
    )
    result = row.result_json
    return {
        "selection_id": row.id,
        "chart_id": result["selected"]["chart_id"],
        "score": result["selected"]["score"],
        "degraded": result["degraded"],
        "needs_confirmation": result["needs_confirmation"],
        "provider_name": result["provider_name"],
        "usage": result["usage"],
    }


def _render_step(
    session: Session,
    dataset: Dataset,
    run: PipelineRun,
    step: PipelineStep,
    prior: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    selection = prior.get("selection") or {}
    selection_id = selection.get("selection_id")
    if not selection_id:
        raise PipelineStateError("missing_selection", "render requires a selection result")
    row = selection_service.get_selection(session, str(selection_id))
    if row is None:
        raise PipelineStateError("missing_selection", "the selection record no longer exists")
    rendered = render_service.render_selection(session, row)
    return {
        "placeholder": False,
        "selection_id": rendered["selection_id"],
        "chart_id": rendered["chart_id"],
        "renderer": rendered["renderer"],
        "figure": rendered["figure"],
        "row_count": rendered["row_count"],
        "sampled": rendered["sampled"],
    }


def _report_step(
    session: Session,
    dataset: Dataset,
    run: PipelineRun,
    step: PipelineStep,
    prior: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    selection_id = prior.get("selection", {}).get("selection_id")
    selection = (
        selection_service.get_selection(session, str(selection_id)) if selection_id else None
    )
    language = str(run.options.get("report_language") or "zh")
    template = str(run.options.get("report_template") or "standard")
    conclusion = run.options.get("report_conclusion")
    include_chart = bool(run.options.get("report_include_chart", False))
    chart_image = None
    chart_error = None
    if include_chart and selection is not None:
        target = report_service.report_directory(run) / f"report_{run.id}_chart.png"
        try:
            chart_image = export_service.capture_selection_png(session, selection, target)
        except Exception as exc:  # chart capture is optional; keep the report usable
            chart_error = str(exc)
    bundle = report_service.write_report_bundle(
        dataset,
        run,
        prior,
        selection,
        list_steps(session, run.id),
        language=language,
        template=template,
        conclusion=str(conclusion) if conclusion else None,
        chart_image=chart_image,
        chart_note=chart_error,
    )
    return {
        "placeholder": False,
        "path": bundle["md_path"],
        "html_path": bundle["html_path"],
        "manifest_path": bundle["manifest_path"],
        "chart_path": bundle["chart_path"],
        "chart_error": chart_error,
        "selection_id": selection_id,
        "bytes": bundle["bytes"],
        "html_bytes": bundle["html_bytes"],
        "language": language,
        "template": template,
        "summary": "Markdown/HTML report with profile, analysis, selection, lineage, and cost.",
    }


def _duration_ms(start: datetime | None, end: datetime | None) -> int:
    if start is None or end is None:
        return 0
    start_aware = start if start.tzinfo else start.replace(tzinfo=UTC)
    end_aware = end if end.tzinfo else end.replace(tzinfo=UTC)
    return max(0, int((end_aware - start_aware).total_seconds() * 1000))


def _intent(run: PipelineRun) -> ChartIntent | None:
    value = run.options.get("intent")
    return ChartIntent(value) if value else None


STEP_HANDLERS: dict[str, StepHandler] = {
    "profile": _profile_step,
    "clean": _clean_step,
    "candidates": _candidates_step,
    "analyze": _analyze_step,
    "selection": _selection_step,
    "render": _render_step,
    "report": _report_step,
}
