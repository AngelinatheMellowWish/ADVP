"""Saved SQL connections with secrets kept in the OS credential store."""

from __future__ import annotations

import contextlib
import json
import os
import threading
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import keyring
from keyring.errors import KeyringError, PasswordDeleteError
from sqlalchemy.engine import URL

from advp.config import Settings
from advp.ingest.sql import (
    SqlError,
    normalize_url,
    redact_url,
    test_connection,
)

KEYRING_SERVICE = "advp.sql"
_STORE_LOCK = threading.RLock()


class SqlConnectionError(Exception):
    """Stable error for saved-connection storage failures."""

    def __init__(self, code: str, message: str, hint: str | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.hint = hint
        self.status_code = 400


@dataclass(slots=True)
class SavedConnection:
    id: str
    name: str
    url: str
    dialect: str
    database: str
    host: str | None
    username: str | None
    label: str

    def to_dict(self, *, has_password: bool) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "dialect": self.dialect,
            "database": self.database,
            "host": self.host,
            "username": self.username,
            "label": self.label,
            "has_password": has_password,
        }


def _store_path(settings: Settings) -> Path:
    return settings.resolved_eu2_dir / "sql_connections.json"


def _read(settings: Settings) -> list[SavedConnection]:
    path = _store_path(settings)
    with _STORE_LOCK:
        try:
            raw = path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return []
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return []
    if not isinstance(data, dict):
        return []
    rows = data.get("connections")
    if not isinstance(rows, list):
        return []
    result: list[SavedConnection] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        try:
            result.append(
                SavedConnection(
                    id=str(row["id"]),
                    name=str(row["name"]),
                    url=str(row["url"]),
                    dialect=str(row["dialect"]),
                    database=str(row.get("database") or ""),
                    host=str(row["host"]) if row.get("host") is not None else None,
                    username=str(row["username"]) if row.get("username") is not None else None,
                    label=str(row.get("label") or row["name"]),
                )
            )
        except KeyError:
            continue
    return result


def _write(settings: Settings, rows: list[SavedConnection]) -> None:
    path = _store_path(settings)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"connections": [asdict(row) for row in rows]}
    temporary = path.with_name(f"{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        os.replace(temporary, path)
    finally:
        with contextlib.suppress(OSError):
            temporary.unlink()


def _get_password(connection_id: str) -> str | None:
    try:
        return keyring.get_password(KEYRING_SERVICE, connection_id)
    except KeyringError as exc:
        raise SqlConnectionError(
            "credential_store_unavailable",
            "the OS credential store is unavailable",
            "run ADVP in a signed-in Windows desktop session and retry",
        ) from exc


def _set_password(connection_id: str, password: str | None) -> None:
    try:
        if password:
            keyring.set_password(KEYRING_SERVICE, connection_id, password)
        else:
            _delete_password(connection_id)
    except KeyringError as exc:
        raise SqlConnectionError(
            "credential_store_unavailable",
            "the OS credential store is unavailable",
            "run ADVP in a signed-in Windows desktop session and retry",
        ) from exc


def _delete_password(connection_id: str) -> None:
    try:
        keyring.delete_password(KEYRING_SERVICE, connection_id)
    except PasswordDeleteError:
        return
    except KeyringError as exc:
        raise SqlConnectionError(
            "credential_store_unavailable",
            "the OS credential store is unavailable",
            "run ADVP in a signed-in Windows desktop session and retry",
        ) from exc


def _passwordless(url: URL) -> str:
    return url._replace(password=None).render_as_string(hide_password=False)


def list_connections(settings: Settings) -> list[dict[str, Any]]:
    return [row.to_dict(has_password=_get_password(row.id) is not None) for row in _read(settings)]


def create_connection(
    settings: Settings,
    *,
    name: str,
    raw_url: str,
    password: str | None = None,
) -> dict[str, Any]:
    clean_name = name.strip()
    if not clean_name:
        raise SqlConnectionError("invalid_connection_name", "connection name is required")
    rows = _read(settings)
    if any(row.name == clean_name for row in rows):
        raise SqlConnectionError(
            "sql_connection_name_exists",
            f"a saved connection named {clean_name!r} already exists",
        )
    url = normalize_url(raw_url)
    secret = password or url.password
    stored_url = _passwordless(url)
    connection_id = uuid.uuid4().hex
    saved = SavedConnection(
        id=connection_id,
        name=clean_name,
        url=stored_url,
        dialect=url.get_backend_name(),
        database=url.database or "",
        host=url.host,
        username=url.username,
        label=redact_url(url),
    )
    _set_password(connection_id, secret)
    rows.append(saved)
    _write(settings, rows)
    return saved.to_dict(has_password=bool(secret))


def delete_connection(settings: Settings, connection_id: str) -> str:
    rows = _read(settings)
    row = next((item for item in rows if item.id == connection_id), None)
    if row is None:
        raise SqlConnectionError("sql_connection_not_found", "saved connection not found")
    _delete_password(connection_id)
    _write(settings, [item for item in rows if item.id != connection_id])
    return row.name


def forget_credentials(settings: Settings, connection_id: str) -> dict[str, Any]:
    rows = _read(settings)
    row = next((item for item in rows if item.id == connection_id), None)
    if row is None:
        raise SqlConnectionError("sql_connection_not_found", "saved connection not found")
    _delete_password(connection_id)
    return row.to_dict(has_password=False)


def clear_all_credentials(settings: Settings) -> int:
    """Remove every saved database password while keeping connections."""
    rows = _read(settings)
    for row in rows:
        _delete_password(row.id)
    return len(rows)


def _connection(settings: Settings, connection_id: str) -> SavedConnection:
    row = next((item for item in _read(settings) if item.id == connection_id), None)
    if row is None:
        raise SqlConnectionError("sql_connection_not_found", "saved connection not found")
    return row


def test_saved_connection(settings: Settings, connection_id: str) -> dict[str, Any]:
    row = _connection(settings, connection_id)
    url = normalize_url(row.url)
    password = _get_password(connection_id)
    if password is not None:
        url = url._replace(password=password)
    try:
        return test_connection(url)
    except SqlError:
        raise
