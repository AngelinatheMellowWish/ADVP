"""Provider CRUD, connectivity, model, and usage endpoints."""

from __future__ import annotations

from typing import NoReturn

from fastapi import APIRouter, HTTPException, Query, Response
from sqlalchemy.orm import Session

from advp import audit
from advp.api.deps import DbSession
from advp.api.schemas import (
    ProviderCreate,
    ProviderModelsResponse,
    ProviderSummary,
    ProviderTestResponse,
    ProviderUpdate,
    ProviderUsageRecord,
)
from advp.llm import credentials
from advp.llm import providers as provider_service
from advp.llm.client import ProviderError
from advp.models import Provider

router = APIRouter(prefix="/providers", tags=["providers"])


def _not_found(provider_id: str) -> NoReturn:
    raise HTTPException(
        status_code=404,
        detail={"code": "provider_not_found", "message": f"provider was not found: {provider_id}"},
    )


def _provider_or_404(session: Session, provider_id: str) -> Provider:
    provider = provider_service.get_provider(session, provider_id)
    if provider is None:
        _not_found(provider_id)
    return provider


def _raise_credential(exc: credentials.CredentialError) -> NoReturn:
    raise HTTPException(
        status_code=exc.status_code,
        detail={"code": exc.code, "message": str(exc), "hint": exc.hint},
    )


def _raise_provider(exc: ProviderError) -> NoReturn:
    raise HTTPException(
        status_code=exc.status_code,
        detail={"code": exc.code, "message": str(exc), "hint": exc.hint},
    )


@router.get("", response_model=list[ProviderSummary])
def list_providers(session: DbSession) -> list[Provider]:
    return provider_service.list_providers(session)


@router.post("", response_model=ProviderSummary, status_code=201)
def create_provider(payload: ProviderCreate, session: DbSession) -> Provider:
    try:
        provider = provider_service.create_provider(session, payload)
    except credentials.CredentialError as exc:
        _raise_credential(exc)
    audit.record_event(
        session,
        "provider_created",
        target_type="provider",
        target_id=provider.id,
        detail=payload.model_dump(),
    )
    return provider


@router.get("/{provider_id}", response_model=ProviderSummary)
def get_provider(provider_id: str, session: DbSession) -> Provider:
    return _provider_or_404(session, provider_id)


@router.patch("/{provider_id}", response_model=ProviderSummary)
def update_provider(
    provider_id: str,
    payload: ProviderUpdate,
    session: DbSession,
) -> Provider:
    provider = _provider_or_404(session, provider_id)
    try:
        updated = provider_service.update_provider(session, provider, payload)
    except credentials.CredentialError as exc:
        _raise_credential(exc)
    audit.record_event(
        session,
        "provider_updated",
        target_type="provider",
        target_id=provider_id,
        detail=payload.model_dump(exclude_unset=True),
    )
    return updated


@router.delete("/{provider_id}", status_code=204)
def delete_provider(provider_id: str, session: DbSession) -> Response:
    provider = _provider_or_404(session, provider_id)
    provider_name = provider.name
    try:
        provider_service.delete_provider(session, provider)
    except credentials.CredentialError as exc:
        _raise_credential(exc)
    audit.record_event(
        session,
        "provider_deleted",
        target_type="provider",
        target_id=provider_id,
        detail={"name": provider_name},
    )
    return Response(status_code=204)


@router.post("/{provider_id}/test", response_model=ProviderTestResponse)
def test_provider(provider_id: str, session: DbSession) -> dict[str, object]:
    provider = _provider_or_404(session, provider_id)
    try:
        result = provider_service.test_provider(provider)
    except credentials.CredentialError as exc:
        _raise_credential(exc)
    except ProviderError as exc:
        _raise_provider(exc)
    return {
        "ok": result.ok,
        "latency_ms": result.latency_ms,
        "models_supported": result.models_supported,
        "message": result.message,
    }


@router.get("/{provider_id}/models", response_model=ProviderModelsResponse)
def list_models(provider_id: str, session: DbSession) -> dict[str, object]:
    provider = _provider_or_404(session, provider_id)
    try:
        result = provider_service.list_provider_models(provider)
    except credentials.CredentialError as exc:
        _raise_credential(exc)
    except ProviderError as exc:
        _raise_provider(exc)
    return {"models": result.models, "latency_ms": result.latency_ms}


@router.get("/{provider_id}/usage", response_model=list[ProviderUsageRecord])
def list_usage(
    provider_id: str,
    session: DbSession,
    limit: int = Query(default=50, ge=1, le=500),
) -> list[object]:
    _provider_or_404(session, provider_id)
    return list(provider_service.provider_usage(session, provider_id, limit=limit))
