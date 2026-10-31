"""Editable EU2 settings endpoints."""

from __future__ import annotations

from typing import Any, NoReturn

from fastapi import APIRouter, HTTPException
from pydantic import ValidationError

from advp import audit
from advp.api.deps import DbSession
from advp.api.schemas import Eu2SettingsPatch, SettingValue
from advp.config import get_settings
from advp.eu2_settings import (
    SettingsStorageError,
    SettingsStore,
    effective_settings,
    env_override,
)

router = APIRouter(prefix="/settings", tags=["settings"])


def _read_failed(exc: SettingsStorageError) -> NoReturn:
    raise HTTPException(
        status_code=500,
        detail={
            "code": "settings_read_failed",
            "message": "settings could not be read",
        },
    ) from exc


@router.get("", response_model=dict[str, SettingValue])
def read_settings() -> dict[str, dict[str, Any]]:
    """Return every editable setting with its effective value and source."""
    try:
        return effective_settings(get_settings())
    except SettingsStorageError as exc:
        _read_failed(exc)


@router.patch("", response_model=dict[str, SettingValue])
def update_settings(
    payload: Eu2SettingsPatch,
    session: DbSession,
) -> dict[str, dict[str, Any]]:
    """Persist provided settings unless an environment variable overrides them.

    The settings file is replaced before the audit event is committed; if the
    audit write fails, the store restores the previous file so the two remain
    consistent.
    """
    changes = payload.model_dump(exclude_unset=True)
    overridden = sorted(name for name in changes if env_override(name) is not None)
    if overridden:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "env_override",
                "message": "settings are controlled by environment variables",
                "fields": overridden,
            },
        )
    settings = get_settings()
    store = SettingsStore(settings.eu2_settings_file)
    if changes:

        def _commit(_ordered: dict[str, Any]) -> None:
            audit.record_event(
                session,
                "settings_updated",
                target_type="settings",
                detail={"fields": sorted(changes)},
            )

        try:
            store.save_with_commit(changes, _commit)
        except SettingsStorageError as exc:
            _read_failed(exc)
        except (ValueError, ValidationError) as exc:
            raise HTTPException(
                status_code=422,
                detail={"code": "invalid_settings", "message": str(exc)},
            ) from exc
        except OSError as exc:
            raise HTTPException(
                status_code=500,
                detail={
                    "code": "settings_write_failed",
                    "message": "settings could not be written",
                },
            ) from exc
        except Exception as exc:
            session.rollback()
            raise HTTPException(
                status_code=500,
                detail={
                    "code": "settings_audit_failed",
                    "message": "settings were rolled back because the audit write failed",
                },
            ) from exc
    try:
        return effective_settings(settings)
    except SettingsStorageError as exc:
        _read_failed(exc)
