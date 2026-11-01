"""Project budget and cost aggregation endpoints."""

from __future__ import annotations

import csv
import io
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Response
from sqlalchemy.orm import Session

from advp import audit
from advp.api.deps import DbSession
from advp.api.schemas import BudgetStatusResponse, BudgetUpdate, CostSummaryResponse
from advp.costs import check_budget, cost_rows, cost_summary, update_budgets
from advp.models import Project

router = APIRouter(prefix="/projects", tags=["costs"])


def _project_or_404(session: Session, project_id: str) -> Project:
    project = session.get(Project, project_id)
    if project is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "project_not_found", "message": f"project was not found: {project_id}"},
        )
    return project


@router.get("/{project_id}/budgets", response_model=BudgetStatusResponse)
def get_budgets(project_id: str, session: DbSession) -> dict[str, Any]:
    _project_or_404(session, project_id)
    return check_budget(session, project_id).to_dict()


@router.patch("/{project_id}/budgets", response_model=BudgetStatusResponse)
def patch_budgets(
    project_id: str,
    payload: BudgetUpdate,
    session: DbSession,
) -> dict[str, Any]:
    project = _project_or_404(session, project_id)
    result = update_budgets(
        session,
        project,
        project_limit=payload.project_limit,
        monthly_limit=payload.monthly_limit,
        warning_ratio=payload.warning_ratio,
        currency=payload.currency,
    )
    audit.record_event(
        session,
        "budget_updated",
        project_id=project_id,
        target_type="project",
        target_id=project_id,
        detail=payload.model_dump(),
    )
    return result


@router.get("/{project_id}/costs", response_model=CostSummaryResponse)
def get_costs(
    project_id: str,
    session: DbSession,
    period: str = Query(default="month", pattern="^(month|all)$"),
) -> dict[str, Any]:
    _project_or_404(session, project_id)
    return cost_summary(session, project_id, period=period)


@router.get("/{project_id}/costs.csv")
def get_costs_csv(
    project_id: str,
    session: DbSession,
    period: str = Query(default="month", pattern="^(month|all)$"),
) -> Response:
    _project_or_404(session, project_id)
    rows = cost_rows(session, project_id, period=period)
    buffer = io.StringIO()
    fields = [
        "created_at",
        "run_id",
        "provider",
        "model",
        "operation",
        "tag",
        "input_tokens",
        "output_tokens",
        "cached_tokens",
        "latency_ms",
        "estimated_cost",
        "currency",
        "attempts",
    ]
    writer = csv.DictWriter(buffer, fieldnames=fields)
    writer.writeheader()
    writer.writerows(rows)
    return Response(
        content=buffer.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="advp-costs-{project_id}.csv"'},
    )
