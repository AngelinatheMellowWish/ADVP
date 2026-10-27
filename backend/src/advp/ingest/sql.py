"""Read-only SQL connectors and derived Parquet materialization."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import date, datetime, time
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import UUID

import polars as pl
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import URL, Engine, make_url
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.pool import NullPool

ALLOWED_DRIVERS = {
    "sqlite",
    "sqlite+pysqlite",
    "postgresql+psycopg",
    "mysql+pymysql",
}
WRITE_KEYWORDS = re.compile(
    r"\b(insert|update|delete|drop|alter|create|truncate|grant|revoke|"
    r"attach|detach|vacuum|replace|merge|call|exec|execute)\b",
    re.IGNORECASE,
)


class SqlError(Exception):
    """Base error for SQL connector failures."""

    code = "sql_error"
    status_code = 400

    def __init__(self, message: str, hint: str | None = None) -> None:
        super().__init__(message)
        self.hint = hint


class InvalidConnectionError(SqlError):
    code = "invalid_connection"
    status_code = 400


class UnsupportedDialectError(SqlError):
    code = "unsupported_sql_dialect"
    status_code = 415


class SqlConnectionError(SqlError):
    code = "sql_connection_failed"
    status_code = 400


class SqlQueryError(SqlError):
    code = "sql_query_failed"
    status_code = 422


class ReadOnlyError(SqlError):
    code = "read_only_required"
    status_code = 400


@dataclass(slots=True)
class MaterializedSql:
    row_count: int
    truncated: bool
    dialect: str
    label: str
    columns: list[str]


def normalize_url(raw: str) -> URL:
    """Accept common URL aliases and reject unsupported dialects."""
    value = raw.strip()
    if value.startswith("postgres://"):
        value = "postgresql+psycopg://" + value[len("postgres://") :]
    elif value.startswith("postgresql://"):
        value = "postgresql+psycopg://" + value[len("postgresql://") :]
    elif value.startswith("mysql://"):
        value = "mysql+pymysql://" + value[len("mysql://") :]
    try:
        url = make_url(value)
    except Exception as exc:
        raise InvalidConnectionError(
            "connection URL is not valid",
            hint="use sqlite:///path, postgresql://user:pass@host/db, or mysql://user:pass@host/db",
        ) from exc
    if url.drivername in {"postgresql", "postgresql+psycopg2"}:
        url = url.set(drivername="postgresql+psycopg")
    elif url.drivername == "mysql":
        url = url.set(drivername="mysql+pymysql")
    if url.drivername not in ALLOWED_DRIVERS:
        raise UnsupportedDialectError(
            f"unsupported SQL dialect: {url.drivername}",
            hint="supported: SQLite, PostgreSQL (psycopg), MySQL (pymysql)",
        )
    return url


def redact_url(url: URL) -> str:
    return url.render_as_string(hide_password=True)


def _redact_message(message: str, url: URL) -> str:
    if url.password:
        message = message.replace(url.password, "***")
    return message


def _connect_args(url: URL) -> dict[str, Any]:
    backend = url.get_backend_name()
    if backend == "sqlite":
        return {"timeout": 10}
    if backend == "postgresql":
        return {"connect_timeout": 5}
    if backend == "mysql":
        return {"connect_timeout": 5, "read_timeout": 30}
    return {}


def _engine(url: URL) -> Engine:
    return create_engine(url, poolclass=NullPool, connect_args=_connect_args(url))


def test_connection(url: URL) -> dict[str, Any]:
    engine = _engine(url)
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        return {
            "ok": True,
            "dialect": url.get_backend_name(),
            "database": url.database or "",
            "label": redact_url(url),
        }
    except SQLAlchemyError as exc:
        raise SqlConnectionError(f"connection failed: {_redact_message(str(exc), url)}") from exc
    finally:
        engine.dispose()


def list_tables(url: URL) -> list[dict[str, Any]]:
    engine = _engine(url)
    try:
        inspector = inspect(engine)
        result = [
            {"name": name, "schema_name": None, "type": "table"}
            for name in inspector.get_table_names()
        ]
        result.extend(
            {"name": name, "schema_name": None, "type": "view"}
            for name in inspector.get_view_names()
        )
        return result
    except SQLAlchemyError as exc:
        raise SqlQueryError(f"cannot list tables: {_redact_message(str(exc), url)}") from exc
    finally:
        engine.dispose()


def list_columns(url: URL, table: str) -> list[dict[str, Any]]:
    engine = _engine(url)
    try:
        inspector = inspect(engine)
        return [
            {
                "name": column["name"],
                "type": str(column.get("type", "")),
                "nullable": bool(column.get("nullable", True)),
                "default": (str(column["default"]) if column.get("default") is not None else None),
            }
            for column in inspector.get_columns(table)
        ]
    except SQLAlchemyError as exc:
        raise SqlQueryError(f"cannot list columns: {_redact_message(str(exc), url)}") from exc
    finally:
        engine.dispose()


def _strip_comments(query: str) -> str:
    without_block = re.sub(r"/\*.*?\*/", " ", query, flags=re.DOTALL)
    return re.sub(r"--[^\n]*", " ", without_block)


def validate_read_only(query: str) -> str:
    """Reject multi-statement and non-SELECT queries before execution."""
    cleaned = _strip_comments(query).strip()
    while cleaned.endswith(";"):
        cleaned = cleaned[:-1].rstrip()
    if not cleaned:
        raise ReadOnlyError("query is empty")
    if ";" in cleaned:
        raise ReadOnlyError("only one read-only statement is allowed")
    match = re.match(r"([A-Za-z]+)", cleaned)
    if not match or match.group(1).lower() not in {"select", "with"}:
        raise ReadOnlyError(
            "only SELECT and WITH queries are allowed",
            hint="use a read-only database user for production connections",
        )
    if WRITE_KEYWORDS.search(cleaned):
        raise ReadOnlyError(
            "query contains a write keyword",
            hint="read-only mode rejects INSERT/UPDATE/DELETE/DDL statements",
        )
    return cleaned


def _json_value(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (datetime, date, time)):
        return value.isoformat()
    if isinstance(value, (bytes, bytearray, memoryview)):
        return bytes(value).decode("utf-8", errors="replace")
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    return value


def _python_value(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (bytes, bytearray, memoryview)):
        return bytes(value).decode("utf-8", errors="replace")
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, dict):
        return json.dumps(_json_value(value), ensure_ascii=False)
    if isinstance(value, list):
        return json.dumps(_json_value(value), ensure_ascii=False)
    return value


def _columns(keys: list[str]) -> list[dict[str, Any]]:
    return [
        {
            "name": key,
            "physical_type": "unknown",
            "semantic_type": "unknown",
            "nullable": True,
            "cardinality": 0,
            "value_range": None,
            "unit": None,
            "source_column": key,
        }
        for key in keys
    ]


def _run_query(
    url: URL, query: str, limit: int, offset: int
) -> tuple[list[str], list[dict[str, Any]], bool]:
    cleaned = validate_read_only(query)
    engine = _engine(url)
    try:
        with engine.connect() as connection:
            if url.get_backend_name() == "sqlite":
                connection.exec_driver_sql("PRAGMA query_only = ON")
            sql = f"SELECT * FROM ({cleaned}) AS advp_query LIMIT :advp_limit"
            params: dict[str, Any] = {"advp_limit": limit + 1}
            if offset:
                sql += " OFFSET :advp_offset"
                params["advp_offset"] = offset
            result = connection.execute(text(sql), params)
            keys = [str(key) for key in list(result.keys())]
            rows = [dict(row._mapping) for row in result]
            truncated = len(rows) > limit
            return keys, rows[:limit], truncated
    except SQLAlchemyError as exc:
        raise SqlQueryError(f"query failed: {_redact_message(str(exc), url)}") from exc
    finally:
        engine.dispose()


def preview_query(url: URL, query: str, *, limit: int, offset: int) -> dict[str, Any]:
    keys, rows, truncated = _run_query(url, query, limit, offset)
    return {
        "rows": [{key: _json_value(value) for key, value in row.items()} for row in rows],
        "columns": _columns(keys),
        "limit": limit,
        "offset": offset,
        "truncated": truncated,
        "dialect": url.get_backend_name(),
    }


def materialize_query(url: URL, query: str, output: Path, *, max_rows: int) -> MaterializedSql:
    keys, rows, truncated = _run_query(url, query, max_rows, 0)
    output.parent.mkdir(parents=True, exist_ok=True)
    if rows:
        frame = pl.DataFrame(
            [{key: _python_value(value) for key, value in row.items()} for row in rows],
            infer_schema_length=max(len(rows), 1),
            strict=False,
        )
    else:
        frame = pl.DataFrame({key: [] for key in keys})
    frame.write_parquet(output)
    return MaterializedSql(
        row_count=len(rows),
        truncated=truncated,
        dialect=url.get_backend_name(),
        label=redact_url(url),
        columns=keys,
    )
