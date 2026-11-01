"""Deterministic cleaning recipes, change logs, and derived datasets."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

import polars as pl
from sqlalchemy import select
from sqlalchemy.orm import Session

from advp.config import get_settings
from advp.ingest.files import frame_to_rows, read_preview, sha256_source
from advp.ingest.profiling import profile_frame, schema_from_profile
from advp.models import CleaningRun, Dataset

CLEANING_MAX_ROWS = 100_000
MAX_CLEAN_STEPS = 20
ALLOWED_OPERATIONS = {
    "drop_missing",
    "fill_missing",
    "clip_outliers",
    "deduplicate",
    "cast_type",
    "rename_columns",
    "drop_columns",
}
HIGH_RISK_OPERATIONS = {"drop_columns"}


class CleanError(Exception):
    """Invalid recipe or cleaning execution failure."""

    def __init__(self, code: str, message: str, status_code: int = 422) -> None:
        super().__init__(message)
        self.code = code
        self.status_code = status_code


@dataclass(slots=True)
class CleanOutcome:
    frame: pl.DataFrame
    log: list[dict[str, Any]]
    truncated: bool
    before_rows: int
    after_rows: int


def apply_recipe(
    dataset: Dataset,
    steps: list[dict[str, Any]],
    *,
    confirm_high_risk: bool = False,
    max_rows: int = CLEANING_MAX_ROWS,
) -> CleanOutcome:
    """Apply a cleaning recipe to a bounded preview window."""
    if dataset.kind != "table":
        raise CleanError("unsupported_kind", "cleaning is only available for tabular datasets")
    if not steps:
        raise CleanError("empty_recipe", "at least one cleaning step is required")
    if len(steps) > MAX_CLEAN_STEPS:
        raise CleanError("recipe_too_long", f"at most {MAX_CLEAN_STEPS} steps are allowed")
    settings = get_settings()
    rows = read_preview(
        dataset.source_path,
        dataset.options,
        limit=min(max_rows, CLEANING_MAX_ROWS),
        offset=0,
        max_file_bytes=settings.max_file_bytes,
        schema=dataset.schema_json,
        max_limit=CLEANING_MAX_ROWS,
    )
    if not rows:
        raise CleanError("empty_dataset", "the dataset has no rows to clean")
    frame = pl.DataFrame(rows)
    before_rows = frame.height
    log: list[dict[str, Any]] = []
    for index, step in enumerate(steps):
        frame = _apply_step(frame, step, index, log, confirm_high_risk)
    truncated = dataset.row_count > before_rows
    return CleanOutcome(
        frame=frame,
        log=log,
        truncated=truncated,
        before_rows=before_rows,
        after_rows=frame.height,
    )


def clean_dataset(
    session: Session,
    dataset: Dataset,
    steps: list[dict[str, Any]],
    *,
    confirm_high_risk: bool = False,
    parent_run_id: str | None = None,
) -> CleaningRun:
    """Apply and persist a cleaning recipe as a derived Parquet dataset."""
    outcome = apply_recipe(
        dataset,
        steps,
        confirm_high_risk=confirm_high_risk,
    )
    derived_id = uuid.uuid4().hex
    run_id = uuid.uuid4().hex
    settings = get_settings()
    derived_dir = settings.workspace_dir / "derived" / dataset.project_id
    derived_dir.mkdir(parents=True, exist_ok=True)
    path = derived_dir / f"clean_{derived_id}.parquet"
    outcome.frame.write_parquet(path)

    profile = profile_frame(
        outcome.frame,
        sampled=outcome.truncated,
        sample_rows=outcome.frame.height,
        row_count=outcome.frame.height,
        row_count_estimated=False,
    )
    schema = schema_from_profile(profile)
    derived = Dataset(
        id=derived_id,
        project_id=dataset.project_id,
        name=f"{dataset.name} · 清洗",
        version=1,
        kind="table",
        format="parquet",
        source_path=str(path),
        source_sha256=sha256_source(path),
        source_size=path.stat().st_size,
        source_mtime=path.stat().st_mtime,
        row_count=outcome.frame.height,
        row_count_estimated=False,
        column_count=outcome.frame.width,
        sampled=outcome.truncated,
        options={
            "derived_from": dataset.id,
            "cleaning_run_id": run_id,
            "recipe_version": 1,
            "truncated": outcome.truncated,
        },
        schema_json=schema,
        profile_json=profile,
        preview_json=frame_to_rows(outcome.frame.head(20)),
    )
    run = CleaningRun(
        id=run_id,
        dataset_id=dataset.id,
        project_id=dataset.project_id,
        derived_dataset_id=derived_id,
        parent_run_id=parent_run_id,
        recipe_json={"version": 1, "steps": steps, "confirm_high_risk": confirm_high_risk},
        log_json=outcome.log,
        before_rows=outcome.before_rows,
        after_rows=outcome.after_rows,
        truncated=outcome.truncated,
    )
    session.add_all([derived, run])
    session.commit()
    session.refresh(run)
    return run


def list_cleanings(session: Session, dataset_id: str, *, limit: int = 20) -> list[CleaningRun]:
    """Return recent cleaning runs for a source dataset."""
    statement = (
        select(CleaningRun)
        .where(CleaningRun.dataset_id == dataset_id)
        .order_by(CleaningRun.created_at.desc())
        .limit(limit)
    )
    return list(session.scalars(statement).all())


def get_cleaning(session: Session, run_id: str) -> CleaningRun | None:
    """Return one cleaning run."""
    return session.get(CleaningRun, run_id)


def undo_cleaning(session: Session, run: CleaningRun) -> CleaningRun | None:
    """Undo the last step by applying the remaining recipe.

    Returns None when the recipe becomes empty; callers should fall back to the
    original dataset.
    """
    source = session.get(Dataset, run.dataset_id)
    if source is None:
        raise CleanError("dataset_not_found", "source dataset no longer exists", 404)
    steps = list((run.recipe_json or {}).get("steps") or [])
    if len(steps) <= 1:
        return None
    return clean_dataset(
        session,
        source,
        steps[:-1],
        confirm_high_risk=bool((run.recipe_json or {}).get("confirm_high_risk")),
        parent_run_id=run.id,
    )


def rollback_cleaning(session: Session, run: CleaningRun) -> Dataset:
    """Return the original dataset; no derived data is modified."""
    source = session.get(Dataset, run.dataset_id)
    if source is None:
        raise CleanError("dataset_not_found", "source dataset no longer exists", 404)
    return source


def cleaning_summary(run: CleaningRun) -> dict[str, Any]:
    """Compact list representation."""
    return {
        "id": run.id,
        "dataset_id": run.dataset_id,
        "derived_dataset_id": run.derived_dataset_id,
        "parent_run_id": run.parent_run_id,
        "before_rows": run.before_rows,
        "after_rows": run.after_rows,
        "truncated": run.truncated,
        "created_at": run.created_at,
    }


def _apply_step(
    frame: pl.DataFrame,
    step: dict[str, Any],
    index: int,
    log: list[dict[str, Any]],
    confirm_high_risk: bool,
) -> pl.DataFrame:
    operation = str(step.get("operation") or "")
    if operation not in ALLOWED_OPERATIONS:
        raise CleanError("invalid_operation", f"unsupported cleaning operation: {operation!r}")
    if operation in HIGH_RISK_OPERATIONS and not confirm_high_risk:
        raise CleanError(
            "confirmation_required",
            f"operation {operation!r} requires confirm_high_risk=true",
        )
    before_rows = frame.height
    initial_null_counts = frame.null_count().row(0)
    step_before_nulls = 0
    if operation == "drop_missing":
        columns = _step_columns(step, frame)
        frame = frame.drop_nulls(subset=columns)
        affected = before_rows - frame.height
        entry = _entry(
            operation,
            index,
            affected,
            columns=columns,
            before_rows=before_rows,
            after_rows=frame.height,
        )
    elif operation == "fill_missing":
        column = _step_column(step, frame)
        strategy = str(step.get("strategy") or "mean")
        value = step.get("value")
        step_before_nulls = int(frame[column].null_count())
        expression = _fill_expression(frame, column, strategy, value)
        frame = frame.with_columns(expression)
        affected = step_before_nulls - int(frame[column].null_count())
        entry = _entry(
            operation,
            index,
            max(0, affected),
            columns=[column],
            strategy=strategy,
            before_nulls=step_before_nulls,
            after_nulls=int(frame[column].null_count()),
        )
    elif operation == "clip_outliers":
        column = _step_column(step, frame)
        method = str(step.get("method") or "iqr")
        factor = float(step.get("factor", 1.5))
        frame, affected, bounds = _clip(frame, column, method, factor)
        entry = _entry(
            operation,
            index,
            affected,
            columns=[column],
            method=method,
            bounds=bounds,
        )
    elif operation == "deduplicate":
        subset = _step_columns(step, frame, required=False)
        frame = frame.unique(subset=subset or None, keep="first", maintain_order=True)
        affected = before_rows - frame.height
        entry = _entry(
            operation,
            index,
            affected,
            columns=subset,
            before_rows=before_rows,
            after_rows=frame.height,
        )
    elif operation == "cast_type":
        column = _step_column(step, frame)
        target = str(step.get("target") or "")
        step_before_nulls = int(frame[column].null_count())
        frame = _cast(frame, column, target)
        entry = _entry(
            operation,
            index,
            max(0, int(frame[column].null_count()) - step_before_nulls),
            columns=[column],
            target=target,
        )
    elif operation == "rename_columns":
        mapping = step.get("mapping")
        if not isinstance(mapping, dict) or not mapping:
            raise CleanError("invalid_recipe", "rename_columns requires a non-empty mapping")
        unknown = [name for name in mapping if name not in frame.columns]
        if unknown:
            raise CleanError("unknown_column", f"columns not found: {unknown}")
        frame = frame.rename({str(left): str(right) for left, right in mapping.items()})
        entry = _entry(operation, index, 0, mapping=mapping)
    else:
        columns = _step_columns(step, frame)
        if len(columns) >= len(frame.columns):
            raise CleanError("invalid_recipe", "cannot drop every column")
        frame = frame.drop(columns)
        entry = _entry(operation, index, 0, columns=columns)

    entry["before_nulls_total"] = int(sum(initial_null_counts))
    entry["after_nulls_total"] = int(sum(frame.null_count().row(0)))
    log.append(entry)
    return frame


def _entry(operation: str, index: int, affected_rows: int, **extra: Any) -> dict[str, Any]:
    return {
        "step": index,
        "operation": operation,
        "affected_rows": affected_rows,
        **extra,
    }


def _step_columns(
    step: dict[str, Any],
    frame: pl.DataFrame,
    *,
    required: bool = True,
) -> list[str]:
    raw = step.get("columns") or []
    if not isinstance(raw, list) or not all(isinstance(item, str) for item in raw):
        raise CleanError("invalid_recipe", "columns must be a list of strings")
    if required and not raw:
        raise CleanError("invalid_recipe", "columns must not be empty")
    unknown = [name for name in raw if name not in frame.columns]
    if unknown:
        raise CleanError("unknown_column", f"columns not found: {unknown}")
    return list(raw)


def _step_column(step: dict[str, Any], frame: pl.DataFrame) -> str:
    column = step.get("column")
    if not isinstance(column, str) or column not in frame.columns:
        raise CleanError("unknown_column", f"column not found: {column!r}")
    return column


def _fill_expression(
    frame: pl.DataFrame,
    column: str,
    strategy: str,
    value: Any,
) -> pl.Expr:
    if strategy in {"forward", "backward"}:
        return pl.col(column).fill_null(strategy="forward" if strategy == "forward" else "backward")
    if strategy == "constant":
        return pl.col(column).fill_null(value)
    if strategy in {"mean", "median"}:
        series = frame[column].drop_nulls()
        if series.len() == 0:
            return pl.col(column)
        fill_value = series.mean() if strategy == "mean" else series.median()
        return pl.col(column).fill_null(fill_value)
    if strategy == "mode":
        counts = frame[column].drop_nulls().value_counts()
        if counts.height == 0:
            return pl.col(column)
        return pl.col(column).fill_null(counts.sort("count", descending=True)[column][0])
    raise CleanError("invalid_recipe", f"unsupported fill strategy: {strategy!r}")


def _clip(
    frame: pl.DataFrame,
    column: str,
    method: str,
    factor: float,
) -> tuple[pl.DataFrame, int, dict[str, float]]:
    series = frame[column].drop_nulls()
    if series.len() == 0:
        return frame, 0, {}
    if method == "iqr":
        q1 = _to_float(series.quantile(0.25), 0.0)
        q3 = _to_float(series.quantile(0.75), 0.0)
        spread = q3 - q1
        lower = q1 - factor * spread
        upper = q3 + factor * spread
    elif method == "zscore":
        mean = _to_float(series.mean(), 0.0)
        std = _to_float(series.std(), 0.0)
        lower = mean - factor * std
        upper = mean + factor * std
    elif method in {"quantile", "winsorize"}:
        lower = _to_float(series.quantile(0.05), 0.0)
        upper = _to_float(series.quantile(0.95), 0.0)
    else:
        raise CleanError("invalid_recipe", f"unsupported outlier method: {method!r}")
    mask = (pl.col(column) < lower) | (pl.col(column) > upper)
    affected = int(frame.select(mask.sum())[0, 0] or 0)
    frame = frame.with_columns(pl.col(column).clip(lower, upper))
    return frame, affected, {"lower": round(lower, 6), "upper": round(upper, 6)}


def _cast(frame: pl.DataFrame, column: str, target: str) -> pl.DataFrame:
    if target in {"int", "integer"}:
        expression = pl.col(column).cast(pl.Int64, strict=False)
    elif target in {"float", "number"}:
        expression = pl.col(column).cast(pl.Float64, strict=False)
    elif target in {"string", "text"}:
        expression = pl.col(column).cast(pl.Utf8, strict=False)
    elif target == "boolean":
        expression = pl.col(column).cast(pl.Boolean, strict=False)
    elif target == "date":
        expression = pl.col(column).cast(pl.Utf8, strict=False).str.to_date(strict=False)
    elif target == "datetime":
        expression = pl.col(column).cast(pl.Utf8, strict=False).str.to_datetime(strict=False)
    else:
        raise CleanError("invalid_recipe", f"unsupported cast target: {target!r}")
    try:
        return frame.with_columns(expression)
    except Exception as exc:
        raise CleanError("cast_failed", f"cannot cast {column!r} to {target}: {exc}") from exc


def _to_float(value: Any, default: float) -> float:
    try:
        converted = float(value)
    except (TypeError, ValueError):
        return default
    return converted
