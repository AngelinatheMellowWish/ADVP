"""Dataset detail, preview, reprofile, and relocation endpoints."""

from __future__ import annotations

import csv
import io
import math
from typing import Any, NoReturn

from fastapi import APIRouter, HTTPException, Query, Response
from sqlalchemy.orm import Session

from advp import analysis as analysis_service
from advp.api.deps import DbSession
from advp.api.schemas import (
    ChartBuilderRequest,
    ChartCandidatesResponse,
    ChartSelectionRequest,
    ChartSelectionResult,
    ChartSelectionSummary,
    DatasetAnalysisResponse,
    DatasetChartCandidatesRequest,
    DatasetDetail,
    PreviewResponse,
    ProfileOverridesRequest,
    RelocateRequest,
)
from advp.charts import builder as builder_service
from advp.charts import selection as selection_service
from advp.charts.selector import (
    ChartSelectionError,
    build_array_context,
    build_table_context,
    select_array_candidates,
    select_table_candidates,
    to_response,
)
from advp.config import get_settings
from advp.ingest.files import IngestError, read_preview
from advp.llm import providers as provider_service
from advp.models import Dataset
from advp.services import projects as project_service

router = APIRouter(prefix="/datasets", tags=["datasets"])


def _not_found(dataset_id: str) -> NoReturn:
    raise HTTPException(
        status_code=404,
        detail={
            "code": "dataset_not_found",
            "message": f"dataset was not found: {dataset_id}",
        },
    )


def _raise_ingest(exc: IngestError) -> NoReturn:
    raise HTTPException(
        status_code=exc.status_code,
        detail={"code": exc.code, "message": str(exc), "hint": exc.hint},
    )


def _raise_selection(exc: ChartSelectionError) -> NoReturn:
    raise HTTPException(
        status_code=exc.status_code,
        detail={"code": exc.code, "message": str(exc), "hint": exc.hint},
    )


def _raise_analysis(exc: analysis_service.AnalysisError) -> NoReturn:
    raise HTTPException(
        status_code=exc.status_code,
        detail={"code": exc.code, "message": str(exc)},
    )


def _dataset_or_404(session: Session, dataset_id: str) -> Dataset:
    dataset = project_service.get_dataset(session, dataset_id)
    if dataset is None:
        _not_found(dataset_id)
    return dataset


@router.get("/{dataset_id}", response_model=DatasetDetail)
def get_dataset(dataset_id: str, session: DbSession) -> dict[str, object]:
    dataset = _dataset_or_404(session, dataset_id)
    return project_service.dataset_detail(dataset)


@router.get("/{dataset_id}/preview", response_model=PreviewResponse)
def get_preview(
    dataset_id: str,
    session: DbSession,
    limit: int = Query(default=20, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> dict[str, object]:
    dataset = _dataset_or_404(session, dataset_id)
    try:
        return project_service.preview_dataset(dataset, limit=limit, offset=offset)
    except IngestError as exc:
        _raise_ingest(exc)


@router.get("/{dataset_id}/export/sample")
def export_sample_csv(
    dataset_id: str,
    session: DbSession,
    rows: int = Query(default=1000, ge=1),
    full: bool = Query(default=False),
) -> Response:
    dataset = _dataset_or_404(session, dataset_id)
    settings = get_settings()
    requested = dataset.row_count if full else min(rows, dataset.row_count or rows)
    limit = max(1, min(requested, 1_000_000))
    try:
        records = read_preview(
            dataset.source_path,
            dataset.options or {},
            limit=limit,
            offset=0,
            max_file_bytes=settings.max_file_bytes,
            schema=dataset.schema_json,
            max_limit=limit,
        )
    except IngestError as exc:
        _raise_ingest(exc)
    columns = [
        str(column["name"])
        for column in dataset.schema_json.get("columns", [])
        if isinstance(column, dict) and column.get("name")
    ]
    sensitive = {
        str(column["name"])
        for column in dataset.profile_json.get("columns", [])
        if isinstance(column, dict) and column.get("sensitive") and column.get("name")
    }
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(columns)
    for record in records:
        writer.writerow(
            ["***" if column in sensitive else record.get(column, "") for column in columns]
        )
    writer.writerow([f"# Sensitive columns are masked; export limited to {limit} rows."])
    safe_name = (
        "".join(char if char.isalnum() or char in "._-" else "-" for char in dataset.name)
        or "sample"
    )
    return Response(
        content=buffer.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{safe_name}-sample.csv"'},
    )


@router.post("/{dataset_id}/reprofile", response_model=DatasetDetail)
def reprofile_dataset(dataset_id: str, session: DbSession) -> dict[str, object]:
    dataset = _dataset_or_404(session, dataset_id)
    try:
        dataset = project_service.reprofile_dataset(session, dataset)
    except IngestError as exc:
        _raise_ingest(exc)
    return project_service.dataset_detail(dataset)


@router.post("/{dataset_id}/profile-overrides", response_model=DatasetDetail)
def update_profile_overrides(
    dataset_id: str,
    payload: ProfileOverridesRequest,
    session: DbSession,
) -> dict[str, object]:
    dataset = _dataset_or_404(session, dataset_id)
    if dataset.kind != "table":
        raise HTTPException(
            status_code=422,
            detail={
                "code": "unsupported_kind",
                "message": f"dataset kind {dataset.kind!r} has no profile overrides",
                "hint": "profile overrides are only available for tabular datasets",
            },
        )
    try:
        dataset = project_service.update_profile_overrides(
            session,
            dataset,
            sensitive_columns=payload.sensitive_columns,
            type_overrides=payload.type_overrides,
        )
    except IngestError as exc:
        _raise_ingest(exc)
    return project_service.dataset_detail(dataset)


@router.post("/{dataset_id}/relocate", response_model=DatasetDetail)
def relocate_dataset(
    dataset_id: str,
    payload: RelocateRequest,
    session: DbSession,
) -> dict[str, object]:
    dataset = _dataset_or_404(session, dataset_id)
    try:
        dataset = project_service.relocate_dataset(
            session, dataset, path=payload.path, force=payload.force
        )
    except IngestError as exc:
        _raise_ingest(exc)
    return project_service.dataset_detail(dataset)


@router.post("/{dataset_id}/chart-candidates", response_model=ChartCandidatesResponse)
def chart_candidates(
    dataset_id: str,
    payload: DatasetChartCandidatesRequest,
    session: DbSession,
) -> dict[str, object]:
    dataset = _dataset_or_404(session, dataset_id)
    try:
        if dataset.kind == "table":
            table_context = build_table_context(
                dataset.schema_json,
                row_count=dataset.row_count,
                sampled=dataset.sampled,
                is_stream=str(dataset.options.get("source_kind") or "") in {"websocket", "kafka"},
            )
            table_result = select_table_candidates(table_context, payload.intent)
            return to_response(
                table_result,
                kind="table",
                intent=payload.intent,
                dataset_id=dataset.id,
                row_count=dataset.row_count,
            )
        if dataset.kind == "array":
            schema = dataset.schema_json
            array_context = build_array_context(
                variable=str(schema.get("variable", dataset.name)),
                shape=schema.get("shape", []),
                dims=schema.get("dims", []),
                dtype=str(schema.get("dtype", "")),
                units=schema.get("units"),
                sampled=dataset.sampled,
                format=dataset.format,
            )
            array_result = select_array_candidates(array_context, payload.intent)
            return to_response(
                array_result,
                kind="array",
                intent=payload.intent,
                dataset_id=dataset.id,
                row_count=math.prod(array_context.shape),
            )
    except ChartSelectionError as exc:
        _raise_selection(exc)
    raise HTTPException(
        status_code=422,
        detail={
            "code": "unsupported_kind",
            "message": f"dataset kind {dataset.kind!r} has no chart candidates",
        },
    )


@router.post("/{dataset_id}/chart-selection", response_model=ChartSelectionResult)
def create_chart_selection(
    dataset_id: str,
    payload: ChartSelectionRequest,
    session: DbSession,
) -> dict[str, Any]:
    dataset = _dataset_or_404(session, dataset_id)
    if payload.provider_id and provider_service.get_provider(session, payload.provider_id) is None:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "provider_not_found",
                "message": f"provider was not found: {payload.provider_id}",
            },
        )
    try:
        row = selection_service.create_chart_selection(
            session,
            dataset,
            intent=payload.intent,
            provider_id=payload.provider_id,
            max_reselects=payload.max_reselects,
        )
    except ChartSelectionError as exc:
        _raise_selection(exc)
    return selection_service.selection_result(row)


@router.get("/{dataset_id}/chart-selections", response_model=list[ChartSelectionSummary])
def list_chart_selections(
    dataset_id: str,
    session: DbSession,
    limit: int = Query(default=20, ge=1, le=100),
) -> list[dict[str, object]]:
    _dataset_or_404(session, dataset_id)
    rows = selection_service.list_dataset_selections(session, dataset_id, limit=limit)
    return [selection_service.selection_summary(row) for row in rows]


@router.post(
    "/{dataset_id}/chart-builder",
    response_model=ChartSelectionResult,
    status_code=201,
)
def build_chart(
    dataset_id: str,
    payload: ChartBuilderRequest,
    session: DbSession,
) -> dict[str, Any]:
    dataset = _dataset_or_404(session, dataset_id)
    try:
        row = builder_service.build_manual_selection(
            session,
            dataset,
            chart_id=payload.chart_id,
            fields=payload.fields,
            aggregation=payload.aggregation,
            style=payload.style,
            parent_selection_id=payload.parent_selection_id,
            reason=payload.reason,
        )
    except builder_service.ChartBuilderError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail={"code": exc.code, "message": str(exc)},
        ) from exc
    return selection_service.selection_result(row)


@router.post("/{dataset_id}/analysis", response_model=DatasetAnalysisResponse)
def compute_dataset_analysis(dataset_id: str, session: DbSession) -> dict[str, Any]:
    dataset = _dataset_or_404(session, dataset_id)
    try:
        analysis = analysis_service.compute_and_store(session, dataset, force=True)
    except analysis_service.AnalysisError as exc:
        _raise_analysis(exc)
    return {"dataset_id": dataset.id, "analysis": analysis}


@router.get("/{dataset_id}/analysis", response_model=DatasetAnalysisResponse)
def get_dataset_analysis(dataset_id: str, session: DbSession) -> dict[str, Any]:
    dataset = _dataset_or_404(session, dataset_id)
    analysis = analysis_service.cached_analysis(dataset)
    if analysis is None:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "analysis_not_available",
                "message": "no analysis summary has been computed for this dataset",
            },
        )
    return {"dataset_id": dataset.id, "analysis": analysis}
