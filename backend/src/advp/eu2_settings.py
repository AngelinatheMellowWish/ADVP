"""Editable EU2 settings and their atomic JSON store."""

from __future__ import annotations

import contextlib
import json
import os
import threading
import time
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any, Literal, get_args

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from advp.config import Settings


class SettingsStorageError(RuntimeError):
    """Raised when settings storage cannot be read reliably."""


class Eu2Settings(BaseModel):
    """Settings a user may edit without restarting the service."""

    model_config = ConfigDict(extra="ignore")

    language: Literal["zh", "en"] = "zh"
    workspace: str | None = None
    analysis_sample_rows: int = Field(default=10_000, ge=1, le=100_000)
    render_sample_rows: int = Field(default=20_000, ge=1, le=100_000)
    default_provider_id: str | None = None
    global_budget: float | None = Field(default=None, ge=0)
    monthly_budget: float | None = Field(default=None, ge=0)
    search_raw_content: bool = False
    search_sensitive: bool = False
    search_excluded_projects: list[str] = Field(default_factory=list)
    sandbox_timeout_seconds: int = Field(default=30, ge=1, le=600)
    log_redaction: bool = True
    update_channel: Literal["stable", "beta"] = "stable"


EDITABLE_FIELDS: tuple[str, ...] = tuple(Eu2Settings.model_fields)
NULLABLE_FIELDS: frozenset[str] = frozenset(
    name
    for name, field in Eu2Settings.model_fields.items()
    if type(None) in get_args(field.annotation)
)
NON_NULLABLE_FIELDS: frozenset[str] = frozenset(EDITABLE_FIELDS) - NULLABLE_FIELDS

ENV_OVERRIDES: dict[str, str] = {
    "language": "ADVP_LANGUAGE",
    "workspace": "ADVP_WORKSPACE_DIR",
    "analysis_sample_rows": "ADVP_ANALYSIS_SAMPLE_ROWS",
    "render_sample_rows": "ADVP_RENDER_SAMPLE_ROWS",
    "default_provider_id": "ADVP_DEFAULT_PROVIDER_ID",
    "global_budget": "ADVP_GLOBAL_BUDGET",
    "monthly_budget": "ADVP_MONTHLY_BUDGET",
    "search_raw_content": "ADVP_SEARCH_RAW_CONTENT",
    "search_sensitive": "ADVP_SEARCH_SENSITIVE",
    "search_excluded_projects": "ADVP_SEARCH_EXCLUDED_PROJECTS",
    "sandbox_timeout_seconds": "ADVP_SANDBOX_TIMEOUT_SECONDS",
    "log_redaction": "ADVP_LOG_REDACTION",
    "update_channel": "ADVP_UPDATE_CHANNEL",
}


def _validate_field_value(name: str, value: Any) -> Any:
    payload = Eu2Settings().model_dump()
    payload[name] = value
    model = Eu2Settings.model_validate(payload)
    return getattr(model, name)


def parse_setting_value(name: str, raw: Any) -> Any:
    """Validate one raw value against the full editable model constraints."""
    if name not in Eu2Settings.model_fields:
        raise ValueError(f"unknown settings field: {name}")
    try:
        return _validate_field_value(name, raw)
    except ValidationError:
        if not isinstance(raw, str):
            raise
        try:
            decoded = json.loads(raw)
        except json.JSONDecodeError:
            raise
        return _validate_field_value(name, decoded)


def env_override(name: str) -> Any | None:
    """Return a validated environment override, or None when absent or invalid.

    Invalid values are treated exactly like an absent override so reads and
    writes use the same predicate and never claim an invalid value as ``env``.
    """
    variable = ENV_OVERRIDES.get(name)
    if variable is None:
        return None
    raw = os.environ.get(variable)
    if not raw:
        return None
    try:
        return parse_setting_value(name, raw)
    except ValueError:
        return None


def effective_settings(settings: Settings) -> dict[str, dict[str, Any]]:
    """Return every editable field with its value and provenance.

    Invalid environment overrides are ignored so reads stay available; the
    stored or default value is reported instead.
    """
    store = SettingsStore(settings.eu2_settings_file)
    stored = store.load()
    model = Eu2Settings.model_validate(stored)
    result: dict[str, dict[str, Any]] = {}
    for name in EDITABLE_FIELDS:
        value = env_override(name)
        if value is not None:
            result[name] = {"value": value, "source": "env"}
            continue
        if name in stored:
            result[name] = {"value": getattr(model, name), "source": "settings"}
            continue
        value = getattr(model, name)
        if name == "workspace" and value is None:
            value = str(settings.workspace_dir)
        result[name] = {"value": value, "source": "default"}
    return result


def runtime_setting(settings: Settings, name: str) -> Any:
    """Resolve one editable setting for runtime: env > stored > default."""
    if name not in Eu2Settings.model_fields:
        raise ValueError(f"unknown settings field: {name}")
    value = env_override(name)
    if value is not None:
        return value
    stored = SettingsStore(settings.eu2_settings_file).load()
    if name in stored:
        return getattr(Eu2Settings.model_validate(stored), name)
    return getattr(Eu2Settings(), name)


_SAVE_LOCK = threading.RLock()
_REPLACE_ATTEMPTS = 5
_REPLACE_DELAY_SECONDS = 0.02


def _replace_with_retry(source: Path, destination: Path) -> None:
    for attempt in range(_REPLACE_ATTEMPTS):
        try:
            os.replace(source, destination)
            return
        except PermissionError:
            if attempt == _REPLACE_ATTEMPTS - 1:
                raise
            time.sleep(_REPLACE_DELAY_SECONDS * (attempt + 1))


class SettingsStore:
    """Persist editable settings as one atomically replaced JSON document."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)

    def load(self) -> dict[str, Any]:
        """Load stored fields, falling back only for missing or corrupt files.

        A missing file, invalid UTF-8, malformed JSON, or constraint-violating
        values return an empty stored set. Other I/O failures raise
        ``SettingsStorageError`` so a transient sharing violation is not
        mistaken for a deleted settings file.
        """
        with _SAVE_LOCK:
            try:
                text = self.path.read_text(encoding="utf-8")
            except FileNotFoundError:
                return {}
            except UnicodeDecodeError:
                return {}
            except OSError as exc:
                raise SettingsStorageError(str(exc)) from exc
            try:
                data = json.loads(text)
            except json.JSONDecodeError:
                return {}
            if not isinstance(data, dict):
                return {}
            candidate = {name: data[name] for name in EDITABLE_FIELDS if name in data}
            try:
                model = Eu2Settings.model_validate(candidate)
            except ValidationError:
                return {}
            return {name: getattr(model, name) for name in candidate}

    def save(self, values: dict[str, Any]) -> dict[str, Any]:
        """Validate the merged model and atomically write settings fields."""
        with _SAVE_LOCK:
            return self._save_locked(values)

    def save_with_commit(
        self,
        values: dict[str, Any],
        commit: Callable[[dict[str, Any]], None],
    ) -> dict[str, Any]:
        """Persist values, run commit, and restore the prior file if commit fails.

        The settings file and the audit database cannot share one transaction, so
        a failed commit rolls the file back to keep the two stores consistent.
        """
        with _SAVE_LOCK:
            try:
                previous = self.path.read_bytes()
            except FileNotFoundError:
                previous = None
            except OSError as exc:
                raise SettingsStorageError(str(exc)) from exc
            ordered = self._save_locked(values)
            try:
                commit(ordered)
            except Exception:
                self._restore_locked(previous)
                raise
            return ordered

    def _save_locked(self, values: dict[str, Any]) -> dict[str, Any]:
        unknown = sorted(set(values) - set(EDITABLE_FIELDS))
        if unknown:
            raise ValueError(f"unknown settings fields: {', '.join(unknown)}")
        candidate = {**self.load(), **values}
        model = Eu2Settings.model_validate(candidate)
        ordered = {name: getattr(model, name) for name in candidate if name in EDITABLE_FIELDS}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_name(f"{self.path.name}.{uuid.uuid4().hex}.tmp")
        try:
            temporary.write_text(
                json.dumps(ordered, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            _replace_with_retry(temporary, self.path)
        finally:
            with contextlib.suppress(OSError):
                temporary.unlink()
        return ordered

    def _restore_locked(self, previous: bytes | None) -> None:
        try:
            if previous is None:
                self.path.unlink(missing_ok=True)
                return
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temporary = self.path.with_name(f"{self.path.name}.{uuid.uuid4().hex}.tmp")
            try:
                temporary.write_bytes(previous)
                _replace_with_retry(temporary, self.path)
            finally:
                with contextlib.suppress(OSError):
                    temporary.unlink()
        except OSError as exc:
            raise SettingsStorageError(f"settings rollback failed: {exc}") from exc
