"""Cost aggregation and project/monthly budget decisions."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from advp.models import LlmUsage, PipelineStep, Project

DEFAULT_BUDGETS: dict[str, Any] = {
    "project_limit": None,
    "monthly_limit": None,
    "warning_ratio": 0.8,
    "currency": "USD",
}


@dataclass(frozen=True, slots=True)
class BudgetDecision:
    project_limit: float | None
    monthly_limit: float | None
    project_spend: float
    monthly_spend: float
    warning_ratio: float
    currency: str
    warning: bool
    exceeded: bool
    reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "project_limit": self.project_limit,
            "monthly_limit": self.monthly_limit,
            "project_spend": round(self.project_spend, 8),
            "monthly_spend": round(self.monthly_spend, 8),
            "warning_ratio": self.warning_ratio,
            "currency": self.currency,
            "warning": self.warning,
            "exceeded": self.exceeded,
            "reason": self.reason,
        }


def get_budgets(project: Project) -> dict[str, Any]:
    """Return merged budget settings from project settings."""
    stored = (project.settings or {}).get("budgets")
    budgets = dict(DEFAULT_BUDGETS)
    if isinstance(stored, dict):
        budgets.update(stored)
    return budgets


def update_budgets(
    session: Session,
    project: Project,
    *,
    project_limit: float | None,
    monthly_limit: float | None,
    warning_ratio: float,
    currency: str,
) -> dict[str, Any]:
    """Persist budget settings and return the current status."""
    budgets = {
        "project_limit": project_limit,
        "monthly_limit": monthly_limit,
        "warning_ratio": warning_ratio,
        "currency": currency,
    }
    project.settings = {**(project.settings or {}), "budgets": budgets}
    session.commit()
    session.refresh(project)
    return check_budget(session, project.id).to_dict()


def check_budget(session: Session, project_id: str) -> BudgetDecision:
    """Compute project and current-month spend against configured limits."""
    project = session.get(Project, project_id)
    if project is None:
        return BudgetDecision(
            project_limit=None,
            monthly_limit=None,
            project_spend=0.0,
            monthly_spend=0.0,
            warning_ratio=0.8,
            currency="USD",
            warning=False,
            exceeded=False,
        )
    budgets = get_budgets(project)
    rows = list(session.scalars(select(LlmUsage).where(LlmUsage.project_id == project_id)).all())
    project_spend = sum(float(row.estimated_cost) for row in rows)
    month_start = datetime.now(UTC).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    monthly_spend = sum(
        float(row.estimated_cost) for row in rows if _aware(row.created_at) >= month_start
    )
    project_limit = _optional_float(budgets.get("project_limit"))
    monthly_limit = _optional_float(budgets.get("monthly_limit"))
    warning_ratio = _ratio(budgets.get("warning_ratio"))
    exceeded = bool(
        (project_limit is not None and project_spend >= project_limit)
        or (monthly_limit is not None and monthly_spend >= monthly_limit)
    )
    warning = bool(
        not exceeded
        and (
            (project_limit is not None and project_spend >= project_limit * warning_ratio)
            or (monthly_limit is not None and monthly_spend >= monthly_limit * warning_ratio)
        )
    )
    reason = None
    if exceeded:
        project_exceeded = project_limit is not None and project_spend >= project_limit
        reason = "project budget exceeded" if project_exceeded else "monthly budget exceeded"
    return BudgetDecision(
        project_limit=project_limit,
        monthly_limit=monthly_limit,
        project_spend=project_spend,
        monthly_spend=monthly_spend,
        warning_ratio=warning_ratio,
        currency=str(budgets.get("currency") or "USD"),
        warning=warning,
        exceeded=exceeded,
        reason=reason,
    )


def cost_summary(
    session: Session,
    project_id: str,
    *,
    period: str = "month",
) -> dict[str, Any]:
    """Aggregate usage and include the current budget status."""
    rows = list(
        session.scalars(
            select(LlmUsage).where(LlmUsage.project_id == project_id).order_by(LlmUsage.created_at)
        ).all()
    )
    month_start = datetime.now(UTC).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    if period == "month":
        rows = [row for row in rows if _aware(row.created_at) >= month_start]
    by_provider: dict[str, dict[str, Any]] = {}
    by_model: dict[str, dict[str, Any]] = {}
    by_day: dict[str, dict[str, Any]] = {}
    by_tag: dict[str, dict[str, Any]] = {}
    by_operation: dict[str, dict[str, Any]] = {}
    by_run: dict[str, dict[str, Any]] = {}
    by_chart: dict[str, dict[str, Any]] = {}
    chart_cache: dict[str, str] = {}
    total_cost = 0.0
    retry_cost = 0.0
    input_tokens = 0
    output_tokens = 0
    cached_tokens = 0
    for row in rows:
        total_cost += float(row.estimated_cost)
        if (row.tag or "initial") != "initial" or row.attempts > 1:
            retry_cost += float(row.estimated_cost)
        input_tokens += int(row.input_tokens)
        output_tokens += int(row.output_tokens)
        cached_tokens += int(row.cached_tokens)
        _accumulate(by_provider, row.provider_name, row)
        _accumulate(by_model, f"{row.provider_name}/{row.model}", row)
        _accumulate(by_tag, row.tag or "initial", row)
        _accumulate(by_operation, row.operation, row)
        run_key = row.run_id or "unassigned"
        _accumulate(by_run, run_key, row)
        if row.run_id:
            if row.run_id not in chart_cache:
                chart_cache[row.run_id] = _run_chart_id(session, row.run_id) or "unknown"
            _accumulate(by_chart, chart_cache[row.run_id], row)
        day = _aware(row.created_at).date().isoformat()
        _accumulate(by_day, day, row)
    project = session.get(Project, project_id)
    return {
        "project_id": project_id,
        "period": period,
        "total_cost": round(total_cost, 8),
        "retry_cost": round(retry_cost, 8),
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cached_tokens": cached_tokens,
        "currency": get_budgets(project).get("currency", "USD") if project else "USD",
        "by_provider": _items(by_provider),
        "by_model": _items(by_model),
        "by_day": _items(by_day),
        "by_tag": _items(by_tag),
        "by_operation": _items(by_operation),
        "by_run": _items(by_run),
        "by_chart": _items(by_chart),
        "budget": check_budget(session, project_id).to_dict(),
    }


def cost_rows(
    session: Session,
    project_id: str,
    *,
    period: str = "month",
) -> list[dict[str, Any]]:
    """Return per-request usage rows for CSV export."""
    rows = list(
        session.scalars(
            select(LlmUsage).where(LlmUsage.project_id == project_id).order_by(LlmUsage.created_at)
        ).all()
    )
    if period == "month":
        month_start = datetime.now(UTC).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        rows = [row for row in rows if _aware(row.created_at) >= month_start]
    return [
        {
            "created_at": _aware(row.created_at).isoformat(),
            "run_id": row.run_id or "",
            "provider": row.provider_name,
            "model": row.model,
            "operation": row.operation,
            "tag": row.tag or "initial",
            "input_tokens": row.input_tokens,
            "output_tokens": row.output_tokens,
            "cached_tokens": row.cached_tokens,
            "latency_ms": row.latency_ms,
            "estimated_cost": row.estimated_cost,
            "currency": row.currency,
            "attempts": row.attempts,
        }
        for row in rows
    ]


def _run_chart_id(session: Session, run_id: str) -> str | None:
    step = session.scalars(
        select(PipelineStep).where(
            PipelineStep.run_id == run_id,
            PipelineStep.key == "selection",
        )
    ).first()
    if step is None:
        return None
    chart_id = (step.output_json or {}).get("chart_id")
    return str(chart_id) if chart_id else None


def _accumulate(target: dict[str, dict[str, Any]], key: str, row: LlmUsage) -> None:
    item = target.setdefault(key, {"name": key, "cost": 0.0, "requests": 0})
    item["cost"] = round(float(item["cost"]) + float(row.estimated_cost), 8)
    item["requests"] = int(item["requests"]) + 1


def _items(values: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(values.values(), key=lambda item: float(item["cost"]), reverse=True)


def _optional_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return max(0.0, float(value))
    except (TypeError, ValueError):
        return None


def _ratio(value: Any) -> float:
    try:
        return min(1.0, max(0.0, float(value)))
    except (TypeError, ValueError):
        return 0.8


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)
