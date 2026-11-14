"""Read-only SQL connection test, browsing, and preview endpoints."""

from __future__ import annotations

from typing import NoReturn

from fastapi import APIRouter, HTTPException, Query, Response

from advp import audit
from advp.api.deps import DbSession
from advp.api.schemas import (
    SqlColumnsRequest,
    SqlColumnsResponse,
    SqlConnectionRequest,
    SqlConnectionResponse,
    SqlPreviewRequest,
    SqlPreviewResponse,
    SqlSavedConnectionCreate,
    SqlSavedConnectionInfo,
    SqlSavedConnectionsResponse,
    SqlTablesResponse,
)
from advp.config import get_settings
from advp.ingest.sql import (
    SqlError,
    list_columns,
    list_tables,
    normalize_url,
    preview_query,
    test_connection,
)
from advp.sql_connections import (
    SqlConnectionError,
    clear_all_credentials,
    create_connection,
    delete_connection,
    forget_credentials,
    list_connections,
    test_saved_connection,
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


def _raise_saved(exc: SqlConnectionError) -> NoReturn:
    raise HTTPException(
        status_code=exc.status_code,
        detail={"code": exc.code, "message": str(exc), "hint": exc.hint},
    )


@router.get("/connections", response_model=SqlSavedConnectionsResponse)
def sql_connections() -> dict[str, object]:
    try:
        return {"connections": list_connections(get_settings())}
    except SqlConnectionError as exc:
        _raise_saved(exc)


@router.post("/connections", response_model=SqlSavedConnectionInfo, status_code=201)
def create_sql_connection(
    payload: SqlSavedConnectionCreate,
    session: DbSession,
) -> dict[str, object]:
    try:
        result = create_connection(
            get_settings(),
            name=payload.name,
            raw_url=payload.url,
            password=payload.password.get_secret_value() if payload.password else None,
        )
    except SqlConnectionError as exc:
        _raise_saved(exc)
    except SqlError as exc:
        _raise_sql(exc)
    audit.record_event(
        session,
        "sql_connection_saved",
        target_type="sql_connection",
        target_id=str(result["id"]),
        detail={"name": result["name"], "dialect": result["dialect"]},
    )
    return result


@router.post("/connections/{connection_id}/test", response_model=SqlConnectionResponse)
def test_saved_sql_connection(connection_id: str) -> dict[str, object]:
    try:
        return test_saved_connection(get_settings(), connection_id)
    except SqlConnectionError as exc:
        _raise_saved(exc)
    except SqlError as exc:
        _raise_sql(exc)


@router.post("/connections/{connection_id}/forget", response_model=SqlSavedConnectionInfo)
def forget_saved_sql_connection(connection_id: str, session: DbSession) -> dict[str, object]:
    try:
        result = forget_credentials(get_settings(), connection_id)
    except SqlConnectionError as exc:
        _raise_saved(exc)
    audit.record_event(
        session,
        "sql_connection_credentials_cleared",
        target_type="sql_connection",
        target_id=connection_id,
    )
    return result


@router.delete("/connections/credentials")
def clear_saved_sql_credentials(
    session: DbSession,
    confirm: bool = Query(default=False),
) -> dict[str, int]:
    if not confirm:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "confirmation_required",
                "message": "clearing database credentials requires explicit confirmation",
                "hint": "review the impact and retry with confirm=true",
            },
        )
    try:
        cleared = clear_all_credentials(get_settings())
    except SqlConnectionError as exc:
        _raise_saved(exc)
    audit.record_event(
        session,
        "sql_credentials_cleared",
        target_type="sql_connection",
        detail={"cleared": cleared},
    )
    return {"cleared": cleared}


@router.delete("/connections/{connection_id}", status_code=204)
def delete_saved_sql_connection(connection_id: str, session: DbSession) -> Response:
    try:
        name = delete_connection(get_settings(), connection_id)
    except SqlConnectionError as exc:
        _raise_saved(exc)
    audit.record_event(
        session,
        "sql_connection_deleted",
        target_type="sql_connection",
        target_id=connection_id,
        detail={"name": name},
    )
    return Response(status_code=204)
