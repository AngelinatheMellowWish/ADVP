"""Persisted chart-selection detail endpoint."""

from __future__ import annotations

from typing import Any, NoReturn

from fastapi import APIRouter, HTTPException
from sqlalchemy.orm import Session

from advp.api.deps import DbSession
from advp.api.schemas import (
    ChartCorrectionRequest,
    ChartFigureResponse,
    ChartSelectionResult,
)
from advp.charts import render as render_service
from advp.charts import selection as selection_service
from advp.charts.selector import ChartSelectionError
from advp.models import ChartSelection

router = APIRouter(prefix="/chart-selections", tags=["chart-selections"])


def _row_or_404(session: Session, selection_id: str) -> ChartSelection:
    row = selection_service.get_selection(session, selection_id)
    if row is None:
        _not_found(selection_id)
    return row


@router.get("/{selection_id}", response_model=ChartSelectionResult)
def get_chart_selection(selection_id: str, session: DbSession) -> dict[str, Any]:
    return selection_service.selection_result(_row_or_404(session, selection_id))


@router.post("/{selection_id}/correct", response_model=ChartSelectionResult)
def correct_chart_selection(
    selection_id: str,
    payload: ChartCorrectionRequest,
    session: DbSession,
) -> dict[str, Any]:
    row = _row_or_404(session, selection_id)
    try:
        corrected = selection_service.correct_chart_selection(
            session,
            row,
            payload.instruction,
            provider_id=payload.provider_id,
        )
    except ChartSelectionError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail={"code": exc.code, "message": str(exc), "hint": exc.hint},
        ) from exc
    return selection_service.selection_result(corrected)


@router.get("/{selection_id}/figure", response_model=ChartFigureResponse)
def get_chart_figure(selection_id: str, session: DbSession) -> dict[str, Any]:
    row = _row_or_404(session, selection_id)
    try:
        return render_service.render_selection(session, row)
    except render_service.RenderError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail={"code": exc.code, "message": str(exc)},
        ) from exc


def _not_found(selection_id: str) -> NoReturn:
    raise HTTPException(
        status_code=404,
        detail={
            "code": "chart_selection_not_found",
            "message": f"chart selection was not found: {selection_id}",
        },
    )
