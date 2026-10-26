"""Cleaning recipe preview/apply, history, undo, and rollback endpoints."""

from __future__ import annotations

from typing import Any, NoReturn

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy.orm import Session

from advp.api.deps import DbSession
from advp.api.schemas import (
    CleaningRunSummary,
    CleanRequest,
    CleanResponse,
    CleanUndoResponse,
)
from advp.cleaning import (
    CleanError,
    apply_recipe,
    clean_dataset,
    cleaning_summary,
    get_cleaning,
    list_cleanings,
    rollback_cleaning,
    undo_cleaning,
)
from advp.ingest.files import frame_to_rows
from advp.models import Dataset

router = APIRouter(tags=["cleaning"])


def _dataset_or_404(session: Session, dataset_id: str) -> Dataset:
    dataset = session.get(Dataset, dataset_id)
    if dataset is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "dataset_not_found", "message": f"dataset was not found: {dataset_id}"},
        )
    return dataset


def _raise_clean(exc: CleanError) -> NoReturn:
    raise HTTPException(
        status_code=exc.status_code,
        detail={"code": exc.code, "message": str(exc)},
    )


@router.post("/datasets/{dataset_id}/clean", response_model=CleanResponse)
def clean(
    dataset_id: str,
    payload: CleanRequest,
    session: DbSession,
) -> dict[str, Any]:
    dataset = _dataset_or_404(session, dataset_id)
    steps = [step.model_dump(exclude_none=True) for step in payload.steps]
    try:
        if payload.dry_run:
            outcome = apply_recipe(
                dataset,
                steps,
                confirm_high_risk=payload.confirm_high_risk,
            )
            return {
                "source_dataset_id": dataset.id,
                "derived_dataset_id": None,
                "cleaning_run_id": None,
                "dry_run": True,
                "before_rows": outcome.before_rows,
                "after_rows": outcome.after_rows,
                "truncated": outcome.truncated,
                "log": outcome.log,
                "preview": frame_to_rows(outcome.frame.head(20)),
            }
        run = clean_dataset(
            session,
            dataset,
            steps,
            confirm_high_risk=payload.confirm_high_risk,
        )
        derived = session.get(Dataset, run.derived_dataset_id) if run.derived_dataset_id else None
        return {
            "source_dataset_id": dataset.id,
            "derived_dataset_id": run.derived_dataset_id,
            "cleaning_run_id": run.id,
            "dry_run": False,
            "before_rows": run.before_rows,
            "after_rows": run.after_rows,
            "truncated": run.truncated,
            "log": run.log_json,
            "preview": derived.preview_json if derived is not None else [],
        }
    except CleanError as exc:
        _raise_clean(exc)


@router.get("/datasets/{dataset_id}/cleanings", response_model=list[CleaningRunSummary])
def list_dataset_cleanings(
    dataset_id: str,
    session: DbSession,
    limit: int = Query(default=20, ge=1, le=100),
) -> list[dict[str, Any]]:
    _dataset_or_404(session, dataset_id)
    return [cleaning_summary(run) for run in list_cleanings(session, dataset_id, limit=limit)]


@router.post("/cleanings/{run_id}/undo", response_model=CleanUndoResponse)
def undo(run_id: str, session: DbSession) -> dict[str, Any]:
    run = get_cleaning(session, run_id)
    if run is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "cleaning_not_found", "message": f"cleaning was not found: {run_id}"},
        )
    try:
        new_run = undo_cleaning(session, run)
    except CleanError as exc:
        _raise_clean(exc)
    if new_run is None:
        return {
            "dataset_id": run.dataset_id,
            "cleaning_run_id": None,
            "message": "rolled back to the original dataset",
        }
    return {
        "dataset_id": str(new_run.derived_dataset_id),
        "cleaning_run_id": new_run.id,
        "message": "undid the last cleaning step",
    }


@router.post("/cleanings/{run_id}/rollback", response_model=CleanUndoResponse)
def rollback(run_id: str, session: DbSession) -> dict[str, Any]:
    run = get_cleaning(session, run_id)
    if run is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "cleaning_not_found", "message": f"cleaning was not found: {run_id}"},
        )
    try:
        source = rollback_cleaning(session, run)
    except CleanError as exc:
        _raise_clean(exc)
    return {
        "dataset_id": source.id,
        "cleaning_run_id": None,
        "message": "rolled back to the original dataset",
    }
