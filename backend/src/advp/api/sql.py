"""Read-only SQL connection test, browsing, and preview endpoints."""

from __future__ import annotations

from typing import NoReturn

from fastapi import APIRouter, HTTPException

from advp.api.schemas import (
    SqlColumnsRequest,
    SqlColumnsResponse,
    SqlConnectionRequest,
    SqlConnectionResponse,
    SqlPreviewRequest,
    SqlPreviewResponse,
    SqlTablesResponse,
)
from advp.ingest.sql import (
    SqlError,
    list_columns,
    list_tables,
    normalize_url,
    preview_query,
    test_connection,
)

router = APIRouter(prefix="/sql", tags=["sql"])


def _raise_sql(exc: SqlError) -> NoReturn:
    raise HTTPException(
        status_code=exc.status_code,
        detail={"code": exc.code, "message": str(exc), "hint": exc.hint},
    )


@router.post("/test", response_model=SqlConnectionResponse)
def test_sql_connection(payload: SqlConnectionRequest) -> dict[str, object]:
    try:
        return test_connection(normalize_url(payload.url))
    except SqlError as exc:
        _raise_sql(exc)


@router.post("/tables", response_model=SqlTablesResponse)
def sql_tables(payload: SqlConnectionRequest) -> dict[str, object]:
    try:
        url = normalize_url(payload.url)
        return {
            "dialect": url.get_backend_name(),
            "tables": list_tables(url),
        }
    except SqlError as exc:
        _raise_sql(exc)


@router.post("/columns", response_model=SqlColumnsResponse)
def sql_columns(payload: SqlColumnsRequest) -> dict[str, object]:
    try:
        url = normalize_url(payload.url)
        return {
            "dialect": url.get_backend_name(),
            "table": payload.table,
            "columns": list_columns(url, payload.table),
        }
    except SqlError as exc:
        _raise_sql(exc)


@router.post("/preview", response_model=SqlPreviewResponse)
def sql_preview(payload: SqlPreviewRequest) -> dict[str, object]:
    try:
        url = normalize_url(payload.url)
        return preview_query(url, payload.query, limit=payload.limit, offset=payload.offset)
    except SqlError as exc:
        _raise_sql(exc)
