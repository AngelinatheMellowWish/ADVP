"""Quality issue suggestions and ignored-issue tracking."""

from __future__ import annotations

from typing import Any, NoReturn

from fastapi import APIRouter, HTTPException
from sqlalchemy.orm import Session

from advp import audit
from advp.api.deps import DbSession
from advp.api.schemas import (
    DatasetDetail,
    QualityApplyRequest,
    QualityApplyResponse,
    QualityIgnoreRequest,
)
from advp.cleaning import CleanError, apply_recipe
from advp.ingest.files import frame_to_rows
from advp.models import Dataset, utcnow
from advp.services import projects as project_service

router = APIRouter(tags=["quality"])

NUMERIC_TYPES = {"number", "integer"}
ACTIONABLE_ISSUES = {"missing_values", "numeric_outliers", "type_conflict"}


class QualityError(Exception):
    """A quality issue has no applicable cleaning suggestion."""

    def __init__(self, code: str, message: str, status_code: int = 422) -> None:
        super().__init__(message)
        self.code = code
        self.status_code = status_code


def _raise_quality(exc: QualityError) -> NoReturn:
    raise HTTPException(
        status_code=exc.status_code,
        detail={"code": exc.code, "message": str(exc)},
    )


def _dataset_or_404(session: Session, dataset_id: str) -> Dataset:
    dataset = project_service.get_dataset(session, dataset_id)
    if dataset is None:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "dataset_not_found",
                "message": f"dataset was not found: {dataset_id}",
            },
        )
    return dataset


def _issue_column(dataset: Dataset, code: str) -> str | None:
    for issue in (dataset.profile_json or {}).get("issues", []):
        if issue.get("code") == code and issue.get("column"):
            return str(issue["column"])
    return None


def _column_info(dataset: Dataset, column: str) -> dict[str, Any]:
    for item in (dataset.schema_json or {}).get("columns", []):
        if isinstance(item, dict) and item.get("name") == column:
            return item
    raise QualityError("unknown_column", f"column not found: {column}")


def steps_for_issue(dataset: Dataset, code: str, column: str | None) -> list[dict[str, Any]]:
    """Map one quality issue to a cleaning recipe without applying it."""
    if code == "duplicate_rows":
        return [{"operation": "deduplicate"}]
    if code not in ACTIONABLE_ISSUES:
        raise QualityError("no_cleaning_step", f"no cleaning step for issue: {code}")
    name = column or _issue_column(dataset, code)
    if not name:
        raise QualityError("no_cleaning_step", f"issue {code} has no target column")
    info = _column_info(dataset, name)
    semantic = str(info.get("semantic_type") or "")
    if code == "missing_values":
        strategy = "median" if semantic in NUMERIC_TYPES else "mode"
        return [{"operation": "fill_missing", "column": name, "strategy": strategy}]
    if code == "numeric_outliers":
        return [{"operation": "clip_outliers", "column": name, "method": "iqr"}]
    return [{"operation": "cast_type", "column": name, "target": "float"}]


@router.post(
    "/datasets/{dataset_id}/quality/apply",
    response_model=QualityApplyResponse,
)
def apply_quality_suggestion(
    dataset_id: str,
    payload: QualityApplyRequest,
    session: DbSession,
) -> dict[str, Any]:
    """Preview the cleaning recipe suggested by one quality issue."""
    dataset = _dataset_or_404(session, dataset_id)
    try:
        steps = steps_for_issue(dataset, payload.code, payload.column)
        outcome = apply_recipe(dataset, steps)
    except QualityError as exc:
        _raise_quality(exc)
    except CleanError as exc:
        raise HTTPException(
            status_code=422,
            detail={"code": exc.code, "message": str(exc)},
        ) from exc
    affected = sum(int(entry.get("affected_rows") or 0) for entry in outcome.log)
    return {
        "code": payload.code,
        "steps": steps,
        "columns": sorted({str(step["column"]) for step in steps if step.get("column")}),
        "affected_rows": affected,
        "before_rows": outcome.before_rows,
        "after_rows": outcome.after_rows,
        "truncated": outcome.truncated,
        "preview": frame_to_rows(outcome.frame, limit=20),
        "log": outcome.log,
    }


@router.post(
    "/datasets/{dataset_id}/quality/ignore",
    response_model=DatasetDetail,
)
def ignore_quality_issue(
    dataset_id: str,
    payload: QualityIgnoreRequest,
    session: DbSession,
) -> dict[str, Any]:
    """Persist an issue code so P03 can hide it for this dataset."""
    dataset = _dataset_or_404(session, dataset_id)
    options = dict(dataset.options or {})
    ignored = list(options.get("ignored_issues") or [])
    if payload.code not in ignored:
        ignored.append(payload.code)
    dataset.options = {**options, "ignored_issues": ignored}
    audit.record_event(
        session,
        "quality_issue_ignored",
        project_id=dataset.project_id,
        target_type="dataset",
        target_id=dataset.id,
        detail={"code": payload.code},
    )
    dataset.updated_at = utcnow()
    session.commit()
    session.refresh(dataset)
    return project_service.dataset_detail(dataset)
