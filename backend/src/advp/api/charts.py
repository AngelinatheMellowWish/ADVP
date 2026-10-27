"""Chart registry and rule-based candidate endpoints."""

from __future__ import annotations

import math
from typing import Any, NoReturn

from fastapi import APIRouter, HTTPException

from advp.api.schemas import (
    ArrayChartCandidatesRequest,
    ChartCandidatesRequest,
    ChartCandidatesResponse,
    ChartRegistryResponse,
    TableChartCandidatesRequest,
)
from advp.charts.registry import REGISTRY_VERSION, list_charts
from advp.charts.selector import (
    ChartSelectionError,
    build_array_context,
    build_table_context,
    select_array_candidates,
    select_table_candidates,
    to_response,
)

router = APIRouter(prefix="/charts", tags=["charts"])


def _raise_selection(exc: ChartSelectionError) -> NoReturn:
    raise HTTPException(
        status_code=exc.status_code,
        detail={"code": exc.code, "message": str(exc), "hint": exc.hint},
    )


@router.get("/registry", response_model=ChartRegistryResponse)
def get_registry() -> dict[str, Any]:
    """Return the versioned chart capability registry."""
    return {"registry_version": REGISTRY_VERSION, "charts": list_charts()}


@router.post("/candidates", response_model=ChartCandidatesResponse)
def get_candidates(payload: ChartCandidatesRequest) -> dict[str, Any]:
    """Select candidates from a standalone table or array schema."""
    try:
        if isinstance(payload, TableChartCandidatesRequest):
            table_context = build_table_context(
                payload.schema_definition,
                row_count=payload.row_count,
                sampled=payload.sampled,
            )
            table_result = select_table_candidates(table_context)
            return to_response(
                table_result,
                kind="table",
                row_count=payload.row_count,
            )
        if isinstance(payload, ArrayChartCandidatesRequest):
            array = payload.array
            array_context = build_array_context(
                variable=array.variable,
                shape=array.shape,
                dims=array.dims,
                dtype=array.dtype,
                units=array.units,
                sampled=array.sampled,
            )
            array_result = select_array_candidates(array_context)
            return to_response(
                array_result,
                kind="array",
                row_count=math.prod(array_context.shape),
            )
    except ChartSelectionError as exc:
        _raise_selection(exc)
    raise HTTPException(
        status_code=422,
        detail={"code": "invalid_schema", "message": "unsupported chart payload kind"},
    )
