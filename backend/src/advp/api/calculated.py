"""Safe calculated-field expressions and derived datasets."""

from __future__ import annotations

import ast
import operator
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, NoReturn, cast

import polars as pl
from fastapi import APIRouter, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from advp.api.deps import DbSession
from advp.api.schemas import CalculatedFieldPreviewRequest, CalculatedFieldRequest
from advp.config import get_settings
from advp.ingest.files import ImportOptions, frame_to_rows, read_preview
from advp.ingest.profiling import profile_frame, schema_from_profile
from advp.models import ChartSelection, Dataset, utcnow
from advp.services import projects as project_service

router = APIRouter(prefix="/datasets", tags=["calculated-fields"])

CALCULATED_MAX_ROWS = 100_000
NUMERIC_FUNCTIONS = frozenset(
    {
        "abs",
        "round",
        "floor",
        "ceil",
        "sqrt",
        "exp",
        "log",
        "log10",
        "clip",
        "min",
        "max",
        "pow",
    }
)
WHITELISTED_FUNCTIONS = frozenset(
    {"lower", "upper", "concat", "year", "month", "day"} | NUMERIC_FUNCTIONS
)
DATE_FUNCTIONS = frozenset({"year", "month", "day"})
BINARY_OPERATORS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Mod: operator.mod,
}
COMPARISON_OPERATORS = {
    ast.Eq: "eq",
    ast.NotEq: "ne",
    ast.Lt: "lt",
    ast.LtE: "le",
    ast.Gt: "gt",
    ast.GtE: "ge",
}


class CalculatedFieldError(Exception):
    """Stable calculated-field validation or execution error."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        status_code: int = 422,
        hint: str | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.status_code = status_code
        self.hint = hint


def _raise(exc: CalculatedFieldError) -> NoReturn:
    detail: dict[str, str] = {"code": exc.code, "message": str(exc)}
    if exc.hint:
        detail["hint"] = exc.hint
    raise HTTPException(status_code=exc.status_code, detail=detail)


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


def _columns(dataset: Dataset) -> dict[str, dict[str, Any]]:
    columns: dict[str, dict[str, Any]] = {}
    for column in (dataset.schema_json or {}).get("columns", []):
        if isinstance(column, dict) and column.get("name"):
            columns[str(column["name"])] = column
    return columns


def _column_map(dataset: Dataset) -> dict[str, dict[str, Any]]:
    if dataset.kind != "table":
        raise CalculatedFieldError(
            "unsupported_kind",
            "calculated fields are only available for tabular datasets",
        )
    return _columns(dataset)


def _check_output_column(output_column: str, columns: dict[str, dict[str, Any]]) -> None:
    if not output_column:
        raise CalculatedFieldError(
            "calculated_expression_invalid",
            "an output column name is required",
        )
    if output_column in columns:
        raise CalculatedFieldError(
            "calculated_output_exists",
            f"output column already exists: {output_column}",
            hint="choose a new output column name",
        )


def _parse(expression: str, columns: dict[str, dict[str, Any]]) -> pl.Expr:
    try:
        tree = ast.parse(expression, mode="eval")
    except SyntaxError as exc:
        raise CalculatedFieldError(
            "calculated_expression_invalid",
            "expression could not be parsed",
            hint=f"line {exc.lineno}: {exc.msg}" if exc.lineno else exc.msg,
        ) from exc
    return _build(tree.body, columns)


def _build(node: ast.AST, columns: dict[str, dict[str, Any]]) -> pl.Expr:
    if isinstance(node, ast.Constant):
        if isinstance(node.value, (bool, int, float, str)):
            return pl.lit(node.value)
        raise _invalid("only numeric, string, and boolean literals are supported")
    if isinstance(node, ast.Name):
        if node.id not in columns:
            raise CalculatedFieldError(
                "calculated_unknown_column",
                f"unknown column: {node.id}",
                hint="use a column from the dataset schema",
            )
        return pl.col(node.id)
    if isinstance(node, ast.BinOp):
        handler = BINARY_OPERATORS.get(type(node.op))
        if handler is None:
            raise _invalid("unsupported arithmetic operator")
        return cast(
            pl.Expr,
            handler(_build(node.left, columns), _build(node.right, columns)),
        )
    if isinstance(node, ast.UnaryOp):
        operand = _build(node.operand, columns)
        if isinstance(node.op, ast.USub):
            return -operand
        if isinstance(node.op, ast.UAdd):
            return operand
        if isinstance(node.op, ast.Not):
            return ~operand
        raise _invalid("unsupported unary operator")
    if isinstance(node, ast.Compare):
        return _compare(node, columns)
    if isinstance(node, ast.BoolOp):
        values = [_build(value, columns) for value in node.values]
        if not values:
            raise _invalid("empty boolean expression")
        result = values[0]
        for value in values[1:]:
            if isinstance(node.op, ast.And):
                result = result & value
            elif isinstance(node.op, ast.Or):
                result = result | value
            else:
                raise _invalid("unsupported boolean operator")
        return result
    if isinstance(node, ast.Call):
        return _call(node, columns)
    raise _invalid(f"unsupported syntax: {type(node).__name__}")


def _compare(node: ast.Compare, columns: dict[str, dict[str, Any]]) -> pl.Expr:
    if len(node.ops) != len(node.comparators):
        raise _invalid("invalid comparison")
    left = _build(node.left, columns)
    result: pl.Expr | None = None
    for op, comparator in zip(node.ops, node.comparators, strict=True):
        method = COMPARISON_OPERATORS.get(type(op))
        if method is None:
            raise _invalid("unsupported comparison operator")
        right = _build(comparator, columns)
        comparison = getattr(left, method)(right)
        result = comparison if result is None else result & comparison
        left = right
    if result is None:
        raise _invalid("empty comparison")
    return result


def _call(node: ast.Call, columns: dict[str, dict[str, Any]]) -> pl.Expr:
    if not isinstance(node.func, ast.Name) or node.func.id not in WHITELISTED_FUNCTIONS:
        raise _invalid("only whitelisted functions are supported")
    if node.keywords:
        raise _invalid("keyword arguments are not supported")
    name = node.func.id
    arguments = [_build(argument, columns) for argument in node.args]
    if name in {"lower", "upper"}:
        if len(arguments) != 1:
            raise _invalid(f"{name} expects one argument")
        if name == "lower":
            return arguments[0].str.to_lowercase()
        return arguments[0].str.to_uppercase()
    if name == "concat":
        if not arguments:
            raise _invalid("concat expects at least one argument")
        return pl.concat_str(
            [argument.cast(pl.Utf8) for argument in arguments],
            separator="",
        )
    if name in DATE_FUNCTIONS:
        if len(arguments) != 1:
            raise _invalid(f"{name} expects one argument")
        date_expr = arguments[0].cast(pl.Utf8).str.slice(0, 10).str.to_date(strict=False)
        if name == "year":
            return date_expr.dt.year()
        if name == "month":
            return date_expr.dt.month()
        return date_expr.dt.day()
    if name == "abs":
        if len(arguments) != 1:
            raise _invalid("abs expects one argument")
        return arguments[0].abs()
    if name == "round":
        if len(arguments) not in {1, 2}:
            raise _invalid("round expects one or two arguments")
        if len(arguments) == 1:
            return arguments[0].round(0)
        precision = node.args[1]
        if not isinstance(precision, ast.Constant) or not isinstance(precision.value, int):
            raise _invalid("round expects an integer precision")
        return arguments[0].round(precision.value)
    if name in {"floor", "ceil", "sqrt", "exp", "log", "log10"}:
        if len(arguments) != 1:
            raise _invalid(f"{name} expects one argument")
        value = arguments[0]
        if name == "floor":
            return value.floor()
        if name == "ceil":
            return value.ceil()
        if name == "exp":
            return value.exp()
        if name == "sqrt":
            return pl.when(value >= 0).then(value.sqrt()).otherwise(None)
        if name == "log":
            return pl.when(value > 0).then(value.log()).otherwise(None)
        return pl.when(value > 0).then(value.log(base=10)).otherwise(None)
    if name == "clip":
        if len(arguments) != 3:
            raise _invalid("clip expects three arguments")
        return arguments[0].clip(arguments[1], arguments[2])
    if name in {"min", "max"}:
        if len(arguments) != 2:
            raise _invalid(f"{name} expects two arguments")
        if name == "min":
            return pl.min_horizontal(arguments[0], arguments[1])
        return pl.max_horizontal(arguments[0], arguments[1])
    if name == "pow":
        if len(arguments) != 2:
            raise _invalid("pow expects two arguments")
        return arguments[0].pow(arguments[1])
    raise _invalid(f"unsupported function: {name}")


def _invalid(message: str) -> CalculatedFieldError:
    return CalculatedFieldError("calculated_expression_invalid", message)


def _load_frame(dataset: Dataset) -> tuple[pl.DataFrame, bool]:
    settings = get_settings()
    rows = read_preview(
        dataset.source_path,
        dataset.options,
        limit=CALCULATED_MAX_ROWS,
        offset=0,
        max_file_bytes=settings.max_file_bytes,
        schema=dataset.schema_json,
        max_limit=CALCULATED_MAX_ROWS,
    )
    if not rows:
        raise CalculatedFieldError(
            "calculated_expression_invalid",
            "the dataset has no rows to evaluate",
        )
    return pl.DataFrame(rows), dataset.row_count > len(rows)


def _evaluate(
    frame: pl.DataFrame,
    expression: str,
    output_column: str,
    columns: dict[str, dict[str, Any]],
) -> pl.DataFrame:
    parsed = _parse(expression, columns)
    try:
        return frame.with_columns(parsed.alias(output_column))
    except Exception as exc:  # Polars raises several type-specific exceptions.
        raise CalculatedFieldError(
            "calculated_type_mismatch",
            f"expression cannot be evaluated for {output_column}: {exc}",
            hint="check column types and function arguments",
        ) from exc


def _output_type(frame: pl.DataFrame, output_column: str) -> str:
    profile = profile_frame(
        frame,
        sampled=False,
        sample_rows=frame.height,
        row_count=frame.height,
        row_count_estimated=False,
    )
    schema = schema_from_profile(profile)
    for column in schema.get("columns", []):
        if column.get("name") == output_column:
            return str(column.get("semantic_type") or "unknown")
    return "unknown"


def _preview(
    dataset: Dataset,
    expression: str,
    output_column: str,
) -> tuple[pl.DataFrame, bool, str]:
    columns = _column_map(dataset)
    _check_output_column(output_column, columns)
    frame, truncated = _load_frame(dataset)
    result = _evaluate(frame, expression, output_column, columns)
    return result, truncated, _output_type(result, output_column)


def _lineage(dataset: Dataset, entry: dict[str, Any]) -> list[dict[str, Any]]:
    existing = (dataset.options or {}).get("lineage")
    lineage = (
        [dict(item) for item in existing if isinstance(item, dict)]
        if isinstance(existing, list)
        else []
    )
    lineage.append(entry)
    return lineage


def _derived_payload(
    source: Dataset,
    dataset: Dataset,
    *,
    expression: str,
    output_column: str,
    output_type: str,
    lineage: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "dataset": project_service.dataset_detail(dataset),
        "source_dataset_id": source.id,
        "parent_dataset_id": source.id,
        "expression": expression,
        "output_column": output_column,
        "output_type": output_type,
        "columns": (dataset.schema_json or {}).get("columns", []),
        "preview": dataset.preview_json,
        "lineage": lineage,
    }


@router.post("/{dataset_id}/calculated-fields/preview")
def preview_calculated_field(
    dataset_id: str,
    payload: CalculatedFieldPreviewRequest,
    session: DbSession,
) -> dict[str, Any]:
    dataset = _dataset_or_404(session, dataset_id)
    output_column = (payload.output_column or "calculated").strip()
    try:
        frame, truncated, output_type = _preview(
            dataset,
            payload.expression,
            output_column,
        )
    except CalculatedFieldError as exc:
        _raise(exc)
    rows = frame_to_rows(frame.head(20))
    return {
        "source_dataset_id": dataset.id,
        "expression": payload.expression,
        "output_column": output_column,
        "output_type": output_type,
        "columns": (dataset.schema_json or {}).get("columns", []),
        "preview": rows,
        "rows": rows,
        "row_count": frame.height,
        "sampled": truncated,
    }


@router.post("/{dataset_id}/calculated-fields", status_code=201)
def create_calculated_field(
    dataset_id: str,
    payload: CalculatedFieldRequest,
    session: DbSession,
) -> dict[str, Any]:
    source = _dataset_or_404(session, dataset_id)
    output_column = (payload.output_column or payload.name).strip()
    try:
        columns = _column_map(source)
        _check_output_column(output_column, columns)
        frame, truncated = _load_frame(source)
        result = _evaluate(frame, payload.expression, output_column, columns)
        output_type = _output_type(result, output_column)
    except CalculatedFieldError as exc:
        _raise(exc)

    settings = get_settings()
    derived_dir = settings.workspace_dir / "derived" / source.project_id
    derived_dir.mkdir(parents=True, exist_ok=True)
    path = derived_dir / f"calculated_{uuid.uuid4().hex}.parquet"
    result.write_parquet(path)

    project = project_service.get_project(session, source.project_id)
    if project is None:
        path.unlink(missing_ok=True)
        raise HTTPException(
            status_code=404,
            detail={
                "code": "project_not_found",
                "message": f"project was not found: {source.project_id}",
            },
        )

    created_at = datetime.now(UTC).isoformat()
    entry = {
        "operation": "calculated_field",
        "source_dataset_id": source.id,
        "expression": payload.expression,
        "output_column": output_column,
        "created_at": created_at,
    }
    lineage = _lineage(source, entry)

    try:
        derived = project_service.import_dataset(
            session,
            project,
            path=str(path),
            name=(payload.name or f"{source.name} · {output_column}").strip(),
            options=ImportOptions(
                sample_rows=settings.profile_sample_rows,
                preview_rows=settings.preview_rows,
            ),
        )
    except Exception:
        path.unlink(missing_ok=True)
        raise

    derived.options = {
        **derived.options,
        "source_kind": "calculated_field",
        "source_dataset_id": source.id,
        "parent_dataset_id": source.id,
        "expression": payload.expression,
        "output_column": output_column,
        "calculated_field": entry,
        "lineage": lineage,
        "truncated": truncated,
    }
    if truncated:
        derived.sampled = True
        derived.profile_json = {**derived.profile_json, "sampled": True}
    derived.updated_at = utcnow()
    session.commit()
    session.refresh(derived)
    return _derived_payload(
        source,
        derived,
        expression=payload.expression,
        output_column=output_column,
        output_type=output_type,
        lineage=lineage,
    )


@router.delete("/{dataset_id}/calculated-fields/{calculated_id}")
def remove_calculated_field(
    dataset_id: str,
    calculated_id: str,
    session: DbSession,
) -> dict[str, Any]:
    source = _dataset_or_404(session, dataset_id)
    calculated = session.get(Dataset, calculated_id)
    options = (calculated.options or {}) if calculated is not None else {}
    if (
        calculated is None
        or options.get("source_kind") != "calculated_field"
        or options.get("source_dataset_id") != source.id
    ):
        raise HTTPException(
            status_code=404,
            detail={
                "code": "calculated_field_not_found",
                "message": f"calculated field was not found: {calculated_id}",
            },
        )

    dependent_chart = session.scalars(
        select(ChartSelection).where(ChartSelection.dataset_id == calculated.id).limit(1)
    ).first()
    downstream = _downstream_dataset(session, source.project_id, calculated.id)
    if dependent_chart is not None or downstream is not None:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "calculated_dependency_conflict",
                "message": "calculated field is used by dependent charts or datasets",
                "hint": "remove dependent charts or derived datasets first",
            },
        )

    derived_root = (get_settings().workspace_dir / "derived").resolve()
    path = Path(calculated.source_path).resolve()
    if derived_root in path.parents:
        path.unlink(missing_ok=True)
    session.delete(calculated)
    session.commit()
    session.refresh(source)
    return {
        "removed_id": calculated_id,
        "source_dataset_id": source.id,
        "dataset": project_service.dataset_detail(source),
    }


def _downstream_dataset(session: Session, project_id: str, dataset_id: str) -> Dataset | None:
    statement = select(Dataset).where(
        Dataset.project_id == project_id,
        Dataset.id != dataset_id,
    )
    for candidate in session.scalars(statement):
        options = candidate.options or {}
        if options.get("source_dataset_id") == dataset_id:
            return candidate
        if options.get("parent_dataset_id") == dataset_id:
            return candidate
    return None
