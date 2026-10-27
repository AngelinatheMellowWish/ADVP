"""Chart-selection prompt, output contract, and semantic validation."""

from __future__ import annotations

import json
import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from advp.charts.registry import SEMANTIC_GROUPS, ChartIntent, ChartSpec
from advp.charts.selector import ArrayContext, Candidate, TableContext

PROMPT_VERSION = "chart-selection-v1"
ALLOWED_AGGREGATIONS = {"none", "sum", "mean", "median", "count", "min", "max"}


class SelectionValidationError(Exception):
    """The model returned a syntactically valid but semantically invalid selection."""

    code = "invalid_selection"
    status_code = 422

    def __init__(self, message: str) -> None:
        super().__init__(message)


HEX_COLOR = re.compile(r"^#[0-9a-fA-F]{6}$")


class ChartAnnotation(BaseModel):
    """One optional annotation on a chart."""

    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=1, max_length=500)
    x: float | None = None
    y: float | None = None
    showarrow: bool = True


class ChartReferenceLine(BaseModel):
    """One optional reference line or threshold."""

    model_config = ConfigDict(extra="forbid")

    axis: Literal["x", "y"] = "y"
    value: float
    label: str | None = Field(default=None, max_length=100)


class ChartStyle(BaseModel):
    """Optional presentation-only hints."""

    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(default=None, max_length=200)
    x_title: str | None = Field(default=None, max_length=200)
    y_title: str | None = Field(default=None, max_length=200)
    color: str | None = None
    colorscale: str | None = Field(default=None, max_length=50)
    colorscale_min: float | None = None
    colorscale_max: float | None = None
    show_legend: bool | None = None
    legend_position: Literal["top", "bottom", "left", "right"] | None = None
    log_x: bool | None = None
    log_y: bool | None = None
    barmode: Literal["group", "stack", "overlay"] | None = None
    dual_y: bool | None = None
    colorblind_palette: bool | None = None
    reference_lines: list[ChartReferenceLine] = Field(default_factory=list, max_length=5)
    source_note: str | None = Field(default=None, max_length=300)
    annotations: list[ChartAnnotation] = Field(default_factory=list, max_length=10)


class SelectionOption(BaseModel):
    """One selected or alternative chart."""

    chart_id: str
    fields: dict[str, str] = Field(default_factory=dict)
    aggregation: str | None = None
    reason: str = Field(min_length=1)
    confidence: float = Field(ge=0.0, le=1.0)
    style: ChartStyle | None = None


class SelectionOutput(BaseModel):
    """Structured output expected from the model."""

    selected: SelectionOption
    alternatives: list[SelectionOption] = Field(default_factory=list, max_length=2)
    notes: str | None = None


def build_selection_messages(
    *,
    context_payload: dict[str, Any],
    candidates: list[dict[str, Any]],
    intent: ChartIntent | None,
    feedback: str | None = None,
) -> list[dict[str, str]]:
    """Build system/user messages for a chart-selection request."""
    system = (
        "You are ADVP's scientific chart selector. Choose only from the supplied "
        "candidate chart IDs. Do not invent chart IDs, columns, or fields. "
        "Every field value must exist in the supplied schema and every required role "
        "must be filled. Use aggregation only from none/sum/mean/median/count/min/max. "
        "The reason must cite concrete data features (column names and semantic types). "
        "Return only one JSON object matching the requested schema. confidence is 0..1. "
        "Optional style may set title, x_title, y_title, #RRGGBB color, "
        "colorscale, colorscale_min/max, legend_position, annotations, "
        "show_legend, log_x, log_y, barmode, dual_y, colorblind_palette, "
        "reference_lines, or source_note. "
        "Provide at most two alternatives. Prefer perceptually accurate charts for the "
        "user's intent; avoid pie/radar/3D when precise comparison is required."
    )
    request = {
        "intent": intent.value if intent is not None else None,
        "context": context_payload,
        "candidates": candidates,
        "prompt_version": PROMPT_VERSION,
    }
    if feedback:
        request["feedback"] = feedback
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": json.dumps(request, ensure_ascii=False)},
    ]


def build_correction_messages(
    *,
    context_payload: dict[str, Any],
    candidates: list[dict[str, Any]],
    intent: ChartIntent | None,
    previous: dict[str, Any],
    instruction: str,
) -> list[dict[str, str]]:
    """Build a prompt that applies a natural-language correction."""
    system = (
        "You are ADVP's scientific chart selector applying a user correction. "
        "The corrected selection must stay inside the supplied candidate chart IDs. "
        "Do not invent chart IDs, columns, or fields. Every field value must exist "
        "in the supplied schema and every required role must be filled. "
        "Aggregation is limited to none/sum/mean/median/count/min/max. "
        "Explain how the instruction changed the chart in the reason. "
        "Optional style may set title, x_title, y_title, #RRGGBB color, "
        "colorscale, colorscale_min/max, legend_position, annotations, "
        "show_legend, log_x, log_y, barmode, dual_y, colorblind_palette, "
        "reference_lines, or source_note. "
        "Return only one JSON object matching the requested schema."
    )
    request = {
        "mode": "correction",
        "intent": intent.value if intent is not None else None,
        "context": context_payload,
        "candidates": candidates,
        "previous": previous,
        "instruction": instruction,
        "prompt_version": PROMPT_VERSION,
    }
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": json.dumps(request, ensure_ascii=False)},
    ]


def candidate_payload(candidate: Candidate) -> dict[str, Any]:
    """Serialize one rule candidate for the prompt."""
    spec = candidate.spec.to_dict()
    spec["suggestedFields"] = candidate.suggested_fields
    spec["ruleRank"] = candidate.rule_rank
    spec["why"] = candidate.why
    return spec


def build_dataset_context(
    *,
    schema_definition: dict[str, Any],
    profile: dict[str, Any],
    row_count: int,
    sampled: bool,
    kind: str,
) -> dict[str, Any]:
    """Build a minimal, privacy-aware dataset context for the model."""
    if kind == "array":
        array = profile.get("array") or {}
        return {
            "kind": "array",
            "variable": schema_definition.get("variable"),
            "shape": schema_definition.get("shape"),
            "dims": schema_definition.get("dims"),
            "dtype": schema_definition.get("dtype"),
            "units": schema_definition.get("units"),
            "row_count": row_count,
            "sampled": sampled,
            "stats": _safe_stats(array.get("stats") or {}),
            "analysis": profile.get("analysis"),
        }

    columns = []
    for column in profile.get("columns") or schema_definition.get("columns") or []:
        columns.append(
            {
                "name": column.get("name"),
                "physical_type": column.get("dtype") or column.get("physical_type"),
                "semantic_type": column.get("semantic_type"),
                "cardinality": column.get("cardinality"),
                "null_rate": column.get("null_rate"),
                "unit": column.get("unit"),
                "sensitive": bool(column.get("sensitive", False)),
                "samples": list(column.get("samples") or [])[:3],
                "stats": _safe_stats(column.get("stats") or {}),
                "value_range": column.get("value_range"),
            }
        )
    summary = profile.get("summary") or {}
    return {
        "kind": "table",
        "row_count": row_count,
        "sampled": sampled,
        "columns": columns,
        "quality": {
            "missing_cells": summary.get("missing_cells"),
            "issue_counts": summary.get("issue_counts") or {},
            "sensitive_columns": summary.get("sensitive_columns") or [],
        },
        "analysis": profile.get("analysis"),
    }


def validate_selection(
    output: SelectionOutput,
    candidates: list[Candidate] | tuple[Candidate, ...],
    context: TableContext | ArrayContext,
) -> SelectionOutput:
    """Reject unknown chart IDs, fabricated fields, and missing required roles."""
    by_id = {candidate.spec.id: candidate for candidate in candidates}
    seen: set[str] = set()
    for option in [output.selected, *output.alternatives]:
        spec = by_id.get(option.chart_id)
        if spec is None:
            raise SelectionValidationError(
                f"chart id {option.chart_id!r} is not registered in the candidate set"
            )
        if option.chart_id in seen:
            raise SelectionValidationError(f"chart id {option.chart_id!r} appears more than once")
        seen.add(option.chart_id)
        allowed_roles = set(spec.spec.required_types) | set(spec.spec.optional) | {"value"}
        unknown_roles = set(option.fields) - allowed_roles
        if unknown_roles:
            raise SelectionValidationError(
                f"chart {option.chart_id!r} has unknown field roles: {sorted(unknown_roles)}"
            )
        missing_roles = set(spec.spec.required_types) - set(option.fields)
        if missing_roles:
            raise SelectionValidationError(
                f"chart {option.chart_id!r} is missing required fields: {sorted(missing_roles)}"
            )
        _validate_field_values(option, context)
        _validate_role_semantics(option, spec.spec, context)
        if option.aggregation is not None:
            normalized = option.aggregation.strip().lower()
            if normalized not in ALLOWED_AGGREGATIONS:
                raise SelectionValidationError(f"aggregation {option.aggregation!r} is not allowed")
            option.aggregation = normalized
        if (
            option.style is not None
            and option.style.color is not None
            and not HEX_COLOR.fullmatch(option.style.color)
        ):
            raise SelectionValidationError(
                f"style color {option.style.color!r} must be a #RRGGBB value"
            )
        if (
            option.style is not None
            and option.style.colorscale_min is not None
            and option.style.colorscale_max is not None
            and option.style.colorscale_min >= option.style.colorscale_max
        ):
            raise SelectionValidationError("style colorscale_min must be less than colorscale_max")
    return output


def _validate_field_values(
    option: SelectionOption,
    context: TableContext | ArrayContext,
) -> None:
    if isinstance(context, TableContext):
        available = {column.name for column in context.columns}
        unknown = {value for value in option.fields.values() if value not in available}
        if unknown:
            raise SelectionValidationError(
                f"fields {sorted(unknown)} do not exist in the dataset schema"
            )
        return
    allowed_values = {context.variable}
    unknown = {value for value in option.fields.values() if value not in allowed_values}
    if unknown:
        raise SelectionValidationError(
            f"array fields {sorted(unknown)} do not match variable {context.variable!r}"
        )


def _validate_role_semantics(
    option: SelectionOption,
    spec: ChartSpec,
    context: TableContext | ArrayContext,
) -> None:
    """Reject duplicate graph endpoints and non-numeric measure roles."""
    if not isinstance(context, TableContext):
        return
    if spec.id in {"network_graph", "sankey_flow"}:
        source = option.fields.get("source")
        target = option.fields.get("target")
        if source and target and source == target:
            raise SelectionValidationError(
                f"chart {spec.id!r} requires distinct source and target fields"
            )
    if spec.id == "sunburst_hierarchy":
        levels = [
            option.fields[role]
            for role in ("level1", "level2", "level3")
            if option.fields.get(role)
        ]
        if len(levels) != len(set(levels)):
            raise SelectionValidationError("sunburst hierarchy levels must use distinct fields")
    columns = {column.name: column for column in context.columns}
    for role in ("weight", "value", "y", "y2", "error_y", "size"):
        field = option.fields.get(role)
        if field is None:
            continue
        column = columns.get(field)
        if column is None:
            continue
        groups = SEMANTIC_GROUPS.get(column.semantic_type, frozenset())
        if "numeric" not in groups:
            raise SelectionValidationError(f"role {role!r} requires a numeric field, got {field!r}")


def _safe_stats(stats: dict[str, Any]) -> dict[str, Any]:
    allowed = {
        "min",
        "max",
        "mean",
        "median",
        "std",
        "outlier_count",
        "finite_count",
        "missing_count",
    }
    return {key: value for key, value in stats.items() if key in allowed}
