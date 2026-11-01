"""Deterministic chart candidate selection for tables and numeric arrays."""

from __future__ import annotations

import math
from dataclasses import dataclass, replace
from typing import Any

import numpy as np

from advp.charts.registry import (
    CHARTS,
    GROUP_PREFERENCE,
    REGISTRY_VERSION,
    SEMANTIC_GROUPS,
    ChartIntent,
    ChartSpec,
    get_chart,
)

OPTIONAL_ROLE_GROUPS: dict[str, str] = {
    "series": "categorical",
    "facet": "categorical",
    "x": "categorical",
    "y": "numeric",
    "y2": "numeric",
    "error_y": "numeric",
    "size": "numeric",
    "value": "numeric",
    "label": "categorical",
    "weight": "numeric",
    "level1": "categorical",
    "level2": "categorical",
    "level3": "categorical",
    "region": "categorical",
    "track": "categorical",
    "time": "temporal",
}


class ChartSelectionError(Exception):
    """Stable API error for invalid chart-selection input."""

    def __init__(
        self,
        code: str,
        message: str,
        hint: str | None = None,
        status_code: int = 422,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.hint = hint
        self.status_code = status_code


@dataclass(frozen=True, slots=True)
class TableColumn:
    """A chart-relevant column profile."""

    name: str
    semantic_type: str
    cardinality: int
    nullable: bool = False


@dataclass(frozen=True, slots=True)
class TableContext:
    """Normalized table context for rule filtering."""

    row_count: int
    sampled: bool
    columns: tuple[TableColumn, ...]
    is_stream: bool = False


@dataclass(frozen=True, slots=True)
class ArrayContext:
    """Normalized scientific-array context for rule filtering."""

    variable: str
    shape: tuple[int, ...]
    dims: tuple[str, ...]
    dtype: str
    units: str | None = None
    sampled: bool = False
    format: str | None = None


@dataclass(frozen=True, slots=True)
class Candidate:
    """A chart that passed every rule check."""

    spec: ChartSpec
    suggested_fields: dict[str, str]
    why: str
    rule_rank: int
    array_mapping: dict[str, Any] | None = None
    exact_matches: int = 0


@dataclass(frozen=True, slots=True)
class Excluded:
    """A chart rejected by a specific rule."""

    spec: ChartSpec
    reason_code: str
    message: str


@dataclass(frozen=True, slots=True)
class SelectionResult:
    """Candidates plus explainable exclusions."""

    candidates: tuple[Candidate, ...]
    excluded: tuple[Excluded, ...]


def build_table_context(
    schema_definition: dict[str, Any],
    *,
    row_count: int,
    sampled: bool = False,
    is_stream: bool = False,
) -> TableContext:
    """Validate and normalize a tabular schema payload."""
    raw_columns = schema_definition.get("columns") if isinstance(schema_definition, dict) else None
    if not isinstance(raw_columns, list) or not raw_columns:
        raise ChartSelectionError(
            "invalid_schema",
            "schema_definition.columns must be a non-empty list",
            "provide the Tabular Schema version 1 columns from profiling",
        )
    columns: list[TableColumn] = []
    for raw in raw_columns:
        if not isinstance(raw, dict):
            raise ChartSelectionError("invalid_schema", "each schema column must be an object")
        name = raw.get("name")
        semantic_type = raw.get("semantic_type")
        if not isinstance(name, str) or not name:
            raise ChartSelectionError("invalid_schema", "each schema column needs a name")
        if not isinstance(semantic_type, str) or not semantic_type:
            raise ChartSelectionError(
                "invalid_schema",
                f"column {name!r} needs a semantic_type",
            )
        try:
            cardinality = max(0, int(raw.get("cardinality", 0)))
        except (TypeError, ValueError) as exc:
            raise ChartSelectionError(
                "invalid_schema",
                f"column {name!r} has a non-numeric cardinality",
            ) from exc
        columns.append(
            TableColumn(
                name=name,
                semantic_type=semantic_type,
                cardinality=cardinality,
                nullable=bool(raw.get("nullable", False)),
            )
        )
    if row_count < 0:
        raise ChartSelectionError("invalid_schema", "row_count must be non-negative")
    return TableContext(
        row_count=int(row_count),
        sampled=bool(sampled),
        columns=tuple(columns),
        is_stream=bool(is_stream),
    )


def build_array_context(
    *,
    variable: str,
    shape: tuple[int, ...] | list[int],
    dims: tuple[str, ...] | list[str],
    dtype: str,
    units: str | None = None,
    sampled: bool = False,
    format: str | None = None,
) -> ArrayContext:
    """Validate and normalize a scientific-array schema payload."""
    if not variable:
        raise ChartSelectionError("invalid_schema", "array variable must be non-empty")
    if not dtype:
        raise ChartSelectionError("invalid_schema", "array dtype must be non-empty")
    try:
        normalized_shape = tuple(int(size) for size in shape)
    except (TypeError, ValueError) as exc:
        raise ChartSelectionError("invalid_schema", "array shape must contain integers") from exc
    if not normalized_shape:
        raise ChartSelectionError("invalid_schema", "array shape must not be empty")
    dims_tuple = tuple(str(dim) for dim in dims)
    if len(dims_tuple) != len(normalized_shape):
        dims_tuple = tuple(f"dim_{index}" for index in range(len(normalized_shape)))
    return ArrayContext(
        variable=variable,
        shape=normalized_shape,
        dims=dims_tuple,
        dtype=str(dtype),
        units=units,
        sampled=bool(sampled),
        format=format,
    )


def select_table_candidates(
    context: TableContext,
    intent: ChartIntent | None = None,
) -> SelectionResult:
    """Return ranked table candidates and rejected charts."""
    evaluated: list[Candidate] = []
    excluded: list[Excluded] = []
    for spec in CHARTS:
        if "table" not in spec.data_kinds:
            continue
        if spec.id == "live_timeseries" and not context.is_stream:
            continue
        outcome = _evaluate_table(spec, context, intent)
        if isinstance(outcome, Candidate):
            evaluated.append(outcome)
        else:
            excluded.append(outcome)

    evaluated.sort(
        key=lambda candidate: (
            -candidate.exact_matches,
            -candidate.spec.perceptual_score,
            candidate.spec.id,
        )
    )
    ranked = tuple(
        replace(candidate, rule_rank=index) for index, candidate in enumerate(evaluated, start=1)
    )
    return SelectionResult(candidates=ranked, excluded=tuple(excluded))


def select_array_candidates(
    context: ArrayContext,
    intent: ChartIntent | None = None,
) -> SelectionResult:
    """Return numeric-array heatmap and image-slice candidates or explicit errors."""
    if any(size <= 0 for size in context.shape):
        raise ChartSelectionError(
            "empty_array",
            f"array {context.variable!r} has no elements",
            "choose another variable or check the source dimensions",
        )
    try:
        dtype = np.dtype(context.dtype)
    except TypeError as exc:
        raise ChartSelectionError(
            "invalid_schema",
            f"array dtype {context.dtype!r} is not recognized",
        ) from exc
    if not np.issubdtype(dtype, np.number) or np.issubdtype(dtype, np.complexfloating):
        raise ChartSelectionError(
            "non_numeric_array",
            f"array {context.variable!r} is not numeric ({context.dtype})",
            "string, object, and complex arrays are not chartable in this slice",
        )

    ndim = len(context.shape)
    total_elements = math.prod(context.shape)
    imaging_like = context.format in {"dicom", "nifti", "raw"} or ndim >= 3
    specs = [
        spec
        for spec in (get_chart("image_slice"), get_chart("array_heatmap"))
        if spec is not None
        and "array" in spec.data_kinds
        and (spec.id != "image_slice" or imaging_like)
        and spec.array_dims is not None
        and spec.array_dims[0] <= ndim <= spec.array_dims[1]
    ]
    if not specs:
        raise ChartSelectionError(
            "array_dim_unsupported",
            f"array {context.variable!r} has {ndim} dimensions",
            "numeric arrays with 1 to 4 dimensions are supported",
        )

    candidates: list[Candidate] = []
    excluded: list[Excluded] = []
    for spec in specs:
        if total_elements > spec.max_rows:
            excluded.append(
                Excluded(
                    spec=spec,
                    reason_code="row_limit_exceeded",
                    message=(
                        f"array {context.variable!r} has {total_elements} elements, "
                        f"above maxRows {spec.max_rows}"
                    ),
                )
            )
            continue
        if intent is not None and intent not in spec.intents:
            excluded.append(
                Excluded(
                    spec=spec,
                    reason_code="intent_mismatch",
                    message=f"intent {intent.value!r} is not supported by {spec.id}",
                )
            )
            continue
        if spec.id == "image_slice":
            display_shape = list(context.shape[-2:])
            slice_axis = context.dims[0] if ndim >= 3 else None
            mapping = {
                "value": context.variable,
                "axis": 0,
                "index": 0,
                "slice_axis": slice_axis,
                "slice_index": 0 if ndim >= 3 else None,
                "display_shape": display_shape,
            }
            why = (
                f"value={context.variable} ({context.dtype})，{ndim}D 影像（"
                f"{', '.join(context.dims)}）；切片显示 {display_shape[0]}×{display_shape[1]}"
            )
            if slice_axis is not None:
                why += f"，默认切片 {slice_axis}=0"
        else:
            display_shape = [1, context.shape[0]] if ndim == 1 else list(context.shape[-2:])
            slice_axis = context.dims[0] if ndim == 3 else None
            mapping = {
                "value": context.variable,
                "slice_axis": slice_axis,
                "slice_index": 0 if ndim == 3 else None,
                "display_shape": display_shape,
            }
            why = (
                f"value={context.variable} ({context.dtype})，{ndim}D 数组（"
                f"{', '.join(context.dims)}）；显示 {display_shape[0]}×{display_shape[1]}"
            )
            if slice_axis is not None:
                why += f"，默认切片 {slice_axis}=0"
        if context.units:
            why += f"，单位 {context.units}"
        if context.sampled:
            why += "；画像基于采样"
        candidates.append(
            Candidate(
                spec=spec,
                suggested_fields={},
                why=why + "。",
                rule_rank=0,
                array_mapping=mapping,
            )
        )

    candidates.sort(
        key=lambda candidate: (
            0 if candidate.spec.id == "image_slice" and imaging_like else 1,
            candidate.spec.id,
        )
    )
    ranked = tuple(
        replace(candidate, rule_rank=index) for index, candidate in enumerate(candidates, start=1)
    )
    return SelectionResult(candidates=ranked, excluded=tuple(excluded))


def _evaluate_table(
    spec: ChartSpec,
    context: TableContext,
    intent: ChartIntent | None,
) -> Candidate | Excluded:
    if intent is not None and intent not in spec.intents:
        return _excluded(spec, "intent_mismatch", f"intent {intent.value!r} is not supported")
    if context.row_count < spec.min_rows:
        return _excluded(
            spec,
            "insufficient_rows",
            f"row_count {context.row_count} is below the minimum {spec.min_rows}",
        )
    if context.row_count > spec.max_rows:
        return _excluded(
            spec,
            "row_limit_exceeded",
            f"row_count {context.row_count} exceeds maxRows {spec.max_rows}",
        )
    numeric_count = sum(1 for column in context.columns if _is_numeric(column))
    if numeric_count < spec.min_numeric_fields:
        return _excluded(
            spec,
            "insufficient_numeric_fields",
            f"requires at least {spec.min_numeric_fields} numeric fields, found {numeric_count}",
        )

    used: set[str] = set()
    suggested: dict[str, str] = {}
    assignments: dict[str, TableColumn] = {}
    for role, group in spec.required_types.items():
        column = _pick_column(context, role, group, used)
        if column is None:
            return _excluded(
                spec,
                "missing_field",
                f"requires a {group} field for role {role!r}",
            )
        limit = spec.max_cardinality.get(role)
        if limit is not None and column.cardinality > limit:
            return _excluded(
                spec,
                "cardinality_too_high",
                f"{role} column {column.name!r} cardinality {column.cardinality} exceeds {limit}",
            )
        used.add(column.name)
        assignments[role] = column
        suggested[role] = column.name

    for role in spec.optional:
        group = OPTIONAL_ROLE_GROUPS.get(role, "any")
        column = _pick_column(context, role, group, used)
        if column is None:
            continue
        limit = spec.max_cardinality.get(role)
        if limit is not None and column.cardinality > limit:
            continue
        used.add(column.name)
        assignments[role] = column
        suggested[role] = column.name

    why_parts = [
        f"{role}={column.name} ({column.semantic_type})" for role, column in assignments.items()
    ]
    if spec.min_numeric_fields:
        why_parts.append(f"{numeric_count} 个数值字段可用")
    if context.sampled:
        why_parts.append("画像基于采样")
    exact_matches = sum(
        1
        for role, group in spec.required_types.items()
        if (column := assignments.get(role)) is not None
        and (preference := GROUP_PREFERENCE.get(group, ()))
        and column.semantic_type == preference[0]
    )
    return Candidate(
        spec=spec,
        suggested_fields=suggested,
        why="; ".join(why_parts) + "。",
        rule_rank=0,
        exact_matches=exact_matches,
    )


def _pick_column(
    context: TableContext,
    role: str,
    group: str,
    used: set[str],
) -> TableColumn | None:
    candidates = [
        column for column in context.columns if column.name not in used and _matches(column, group)
    ]
    if not candidates:
        return None
    candidates.sort(key=lambda column: _column_sort_key(column, group))
    return candidates[0]


def _column_sort_key(column: TableColumn, group: str) -> tuple[object, ...]:
    preference = GROUP_PREFERENCE.get(group, ())
    rank = preference.index(column.semantic_type) if column.semantic_type in preference else 99
    if group == "numeric":
        return (rank, -column.cardinality, column.name)
    if group == "categorical":
        return (rank, column.cardinality, column.name)
    return (rank, column.name)


def _matches(column: TableColumn, group: str) -> bool:
    groups = SEMANTIC_GROUPS.get(column.semantic_type, frozenset())
    if group == "any":
        return bool(groups) and "array" not in groups
    return group in groups


def _is_numeric(column: TableColumn) -> bool:
    return "numeric" in SEMANTIC_GROUPS.get(column.semantic_type, frozenset())


def _excluded(spec: ChartSpec, reason_code: str, message: str) -> Excluded:
    return Excluded(spec=spec, reason_code=reason_code, message=message)


def to_response(
    result: SelectionResult,
    *,
    kind: str,
    intent: ChartIntent | None = None,
    dataset_id: str | None = None,
    row_count: int | None = None,
) -> dict[str, Any]:
    """Serialize a selection result for the REST API."""
    return {
        "kind": kind,
        "dataset_id": dataset_id,
        "intent": intent.value if intent is not None else None,
        "registry_version": REGISTRY_VERSION,
        "row_count": row_count,
        "candidates": [
            {
                "id": candidate.spec.id,
                "name": {"zh": candidate.spec.name_zh, "en": candidate.spec.name_en},
                "family": candidate.spec.family,
                "backend": candidate.spec.backend,
                "rule_rank": candidate.rule_rank,
                "suggested_fields": candidate.suggested_fields,
                "array_mapping": candidate.array_mapping,
                "why": candidate.why,
                "supports": list(candidate.spec.supports),
                "accessibility_notes": candidate.spec.accessibility_notes,
                "notes": candidate.spec.notes,
            }
            for candidate in result.candidates
        ],
        "excluded": [
            {
                "id": item.spec.id,
                "reason_code": item.reason_code,
                "message": item.message,
            }
            for item in result.excluded
        ],
    }
