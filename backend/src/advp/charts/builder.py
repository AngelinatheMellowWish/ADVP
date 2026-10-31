"""Build chart selections from explicit user choices without an LLM provider."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

from advp.charts.registry import SEMANTIC_GROUPS, ChartSpec, get_chart
from advp.charts.scoring import score_candidates
from advp.charts.selector import OPTIONAL_ROLE_GROUPS, Candidate, build_table_context
from advp.models import ChartSelection, Dataset

MANUAL_PROMPT_VERSION = "manual-v1"
AGGREGATIONS = frozenset({"sum", "mean", "median", "min", "max", "count"})


class ChartBuilderError(Exception):
    """A manual chart request violates the registry or dataset schema."""

    def __init__(self, code: str, message: str, status_code: int = 422) -> None:
        super().__init__(message)
        self.code = code
        self.status_code = status_code


def build_manual_selection(
    session: Session,
    dataset: Dataset,
    *,
    chart_id: str,
    fields: dict[str, str],
    aggregation: str | None = None,
    style: dict[str, Any] | None = None,
    parent_selection_id: str | None = None,
    reason: str | None = None,
) -> ChartSelection:
    """Validate and persist one manual chart selection with real scores."""
    if dataset.kind != "table":
        raise ChartBuilderError(
            "unsupported_kind",
            "manual chart building currently supports tabular datasets",
        )
    spec = get_chart(chart_id)
    if spec is None:
        raise ChartBuilderError("chart_not_found", f"unknown chart: {chart_id}")
    if aggregation is not None and aggregation not in AGGREGATIONS:
        raise ChartBuilderError("invalid_aggregation", f"unsupported aggregation: {aggregation}")

    context = build_table_context(
        dataset.schema_json,
        row_count=dataset.row_count,
        sampled=dataset.sampled,
        is_stream=str(dataset.options.get("source_kind") or "") in {"websocket", "kafka"},
    )
    columns = {column.name: column for column in context.columns}
    if dataset.row_count < spec.min_rows:
        raise ChartBuilderError(
            "insufficient_rows",
            f"{spec.id} needs at least {spec.min_rows} rows",
        )
    if dataset.row_count > spec.max_rows:
        raise ChartBuilderError(
            "row_limit_exceeded",
            f"{spec.id} supports at most {spec.max_rows} rows",
        )

    cleaned = {str(role): str(name) for role, name in fields.items()}
    for role, column_name in cleaned.items():
        if role not in spec.required_types and role not in OPTIONAL_ROLE_GROUPS:
            raise ChartBuilderError("unknown_field_role", f"unknown field role: {role}")
        if column_name not in columns:
            raise ChartBuilderError("unknown_field", f"column not found: {column_name}")
    for role, group in spec.required_types.items():
        if role not in cleaned:
            raise ChartBuilderError("missing_field", f"missing required field: {role}")
        if group not in SEMANTIC_GROUPS.get(columns[cleaned[role]].semantic_type, frozenset()):
            raise ChartBuilderError(
                "field_type_mismatch",
                f"field {cleaned[role]!r} does not satisfy role {role!r}",
            )
    for role, group in OPTIONAL_ROLE_GROUPS.items():
        if (
            role in cleaned
            and role not in spec.required_types
            and group not in SEMANTIC_GROUPS.get(columns[cleaned[role]].semantic_type, frozenset())
        ):
            raise ChartBuilderError(
                "field_type_mismatch",
                f"field {cleaned[role]!r} does not satisfy role {role!r}",
            )
    for role, limit in spec.max_cardinality.items():
        if role in cleaned and columns[cleaned[role]].cardinality > limit:
            raise ChartBuilderError(
                "cardinality_too_high",
                f"field {cleaned[role]!r} exceeds the {role} cardinality limit",
            )

    if parent_selection_id:
        parent = session.get(ChartSelection, parent_selection_id)
        if parent is None or parent.dataset_id != dataset.id:
            raise ChartBuilderError(
                "parent_selection_not_found",
                f"parent selection was not found for this dataset: {parent_selection_id}",
            )

    candidate = Candidate(
        spec=spec,
        suggested_fields=cleaned,
        why=reason or f"Manual {spec.name_en}",
        rule_rank=1,
    )
    scored = score_candidates([candidate], context, None)[0]
    selection_id = uuid.uuid4().hex
    created_at = datetime.now(UTC)
    result = _result_payload(
        selection_id=selection_id,
        created_at=created_at,
        dataset=dataset,
        spec=spec,
        fields=cleaned,
        aggregation=aggregation,
        style=style or None,
        score=scored.total,
        dimensions=scored.dimensions,
        reason=candidate.why,
        parent_selection_id=parent_selection_id,
    )
    row = ChartSelection(
        id=selection_id,
        dataset_id=dataset.id,
        project_id=dataset.project_id,
        provider_id=None,
        parent_selection_id=parent_selection_id,
        provider_name=None,
        model=None,
        prompt_version=MANUAL_PROMPT_VERSION,
        source="manual",
        intent=None,
        selected_chart_id=spec.id,
        selected_score=scored.total,
        confidence=None,
        degraded=False,
        needs_confirmation=False,
        attempts=0,
        reselects=0,
        input_tokens=0,
        output_tokens=0,
        cached_tokens=0,
        estimated_cost=0.0,
        currency="USD",
        degradation_reason=None,
        result_json=result,
        context_json={
            "schema_definition": dataset.schema_json,
            "row_count": dataset.row_count,
            "sampled": dataset.sampled,
            "kind": dataset.kind,
        },
        candidates_json=[{"chart_id": spec.id, "fields": cleaned}],
        output_json={"source": "manual"},
        created_at=created_at,
    )
    session.add(row)
    session.commit()
    session.refresh(row)
    return row


def _result_payload(
    *,
    selection_id: str,
    created_at: datetime,
    dataset: Dataset,
    spec: ChartSpec,
    fields: dict[str, str],
    aggregation: str | None,
    style: dict[str, Any] | None,
    score: float,
    dimensions: dict[str, float],
    reason: str,
    parent_selection_id: str | None,
) -> dict[str, Any]:
    return {
        "id": selection_id,
        "dataset_id": dataset.id,
        "project_id": dataset.project_id,
        "provider_id": None,
        "provider_name": None,
        "model": None,
        "prompt_version": MANUAL_PROMPT_VERSION,
        "source": "manual",
        "intent": None,
        "selected": {
            "chart_id": spec.id,
            "name": {"zh": spec.name_zh, "en": spec.name_en},
            "family": spec.family,
            "backend": spec.backend,
            "fields": fields,
            "aggregation": aggregation,
            "reason": reason,
            "confidence": None,
            "style": style,
            "score": score,
            "dimensions": dimensions,
        },
        "top3": [
            {
                "chart_id": spec.id,
                "name": {"zh": spec.name_zh, "en": spec.name_en},
                "score": score,
                "selected": True,
                "reason": reason,
            }
        ],
        "attempts": 0,
        "reselects": 0,
        "degraded": False,
        "degradation_reason": None,
        "needs_confirmation": False,
        "budget": None,
        "parent_selection_id": parent_selection_id,
        "correction_instruction": None,
        "usage": {
            "input_tokens": 0,
            "output_tokens": 0,
            "cached_tokens": 0,
            "estimated_cost": 0.0,
            "currency": "USD",
        },
        "created_at": created_at.isoformat(),
    }
