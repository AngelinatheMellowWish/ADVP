"""Provider CRUD, connectivity, and usage recording."""

from __future__ import annotations

import threading
import uuid

import httpx
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from advp.api.schemas import ProviderCreate, ProviderUpdate
from advp.llm import credentials
from advp.llm.client import (
    CompletionResult,
    ConnectionResult,
    ModelListResult,
    ProviderClient,
)
from advp.models import LlmUsage, Provider

DEFAULT_BASE_URLS = {
    "openai": "https://api.openai.com/v1",
    "anthropic": "https://api.anthropic.com/v1",
}

_SLOT_LOCK = threading.Lock()
_PROVIDER_SLOTS: dict[str, tuple[threading.BoundedSemaphore, int]] = {}


def create_provider(session: Session, payload: ProviderCreate) -> Provider:
    """Create a provider and persist its secrets outside the database."""
    provider_id = uuid.uuid4().hex
    base_url = (payload.base_url or DEFAULT_BASE_URLS[payload.kind]).rstrip("/")
    provider = Provider(
        id=provider_id,
        name=payload.name,
        kind=payload.kind,
        base_url=base_url,
        model=payload.model,
        organization=payload.organization,
        project=payload.project,
        anthropic_version=payload.anthropic_version,
        timeout_seconds=payload.timeout_seconds,
        max_retries=payload.max_retries,
        proxy_url=payload.proxy_url,
        input_price_per_million=payload.input_price_per_million,
        output_price_per_million=payload.output_price_per_million,
        currency=payload.currency,
        priority=payload.priority,
        max_concurrency=payload.max_concurrency,
        concurrency_wait_seconds=payload.concurrency_wait_seconds,
        task_budget=payload.task_budget,
        is_default=payload.is_default,
        egress_mode=payload.egress_mode,
        sample_rows=payload.sample_rows,
    )
    api_key = payload.api_key.get_secret_value() if payload.api_key is not None else None
    headers = payload.headers or {}
    secret = credentials.save_secret(provider_id, api_key=api_key, headers=headers)
    provider.key_last4 = credentials.mask_key(secret.api_key)
    provider.has_key = bool(secret.api_key)
    provider.header_names = sorted(secret.headers)
    if payload.is_default or session.scalar(select(func.count(Provider.id))) == 0:
        session.execute(update(Provider).values(is_default=False))
        provider.is_default = True
    session.add(provider)
    try:
        session.commit()
    except Exception:
        credentials.delete_secret(provider_id)
        raise
    session.refresh(provider)
    return provider


def list_providers(session: Session) -> list[Provider]:
    """Return providers with the default entry first."""
    statement = select(Provider).order_by(
        Provider.is_default.desc(),
        Provider.priority,
        Provider.created_at,
    )
    return list(session.scalars(statement).all())


def get_provider(session: Session, provider_id: str) -> Provider | None:
    """Return one provider or None."""
    return session.get(Provider, provider_id)


def update_provider(session: Session, provider: Provider, payload: ProviderUpdate) -> Provider:
    """Update non-secret fields and optionally replace secrets."""
    fields = payload.model_fields_set
    if payload.kind is not None:
        provider.kind = payload.kind
    if payload.name is not None:
        provider.name = payload.name
    if "base_url" in fields:
        provider.base_url = (payload.base_url or DEFAULT_BASE_URLS[provider.kind]).rstrip("/")
    if payload.model is not None:
        provider.model = payload.model
    if "organization" in fields:
        provider.organization = payload.organization
    if "project" in fields:
        provider.project = payload.project
    if payload.anthropic_version is not None:
        provider.anthropic_version = payload.anthropic_version
    if payload.timeout_seconds is not None:
        provider.timeout_seconds = payload.timeout_seconds
    if payload.max_retries is not None:
        provider.max_retries = payload.max_retries
    if "proxy_url" in fields:
        provider.proxy_url = payload.proxy_url
    if payload.input_price_per_million is not None:
        provider.input_price_per_million = payload.input_price_per_million
    if payload.output_price_per_million is not None:
        provider.output_price_per_million = payload.output_price_per_million
    if payload.currency is not None:
        provider.currency = payload.currency
    if payload.priority is not None:
        provider.priority = payload.priority
    if payload.max_concurrency is not None:
        provider.max_concurrency = payload.max_concurrency
    if payload.concurrency_wait_seconds is not None:
        provider.concurrency_wait_seconds = payload.concurrency_wait_seconds
    if payload.task_budget is not None:
        provider.task_budget = payload.task_budget
    if payload.egress_mode is not None:
        provider.egress_mode = payload.egress_mode
    if payload.sample_rows is not None:
        provider.sample_rows = payload.sample_rows
    if payload.is_default is True:
        session.execute(update(Provider).where(Provider.id != provider.id).values(is_default=False))
        provider.is_default = True
    elif payload.is_default is False:
        provider.is_default = False

    secret_changed = (
        "api_key" in fields or "headers" in fields or payload.clear_key or payload.clear_headers
    )
    if secret_changed:
        api_key = payload.api_key.get_secret_value() if payload.api_key is not None else None
        if api_key == "":
            api_key = None
        secret = credentials.save_secret(
            provider.id,
            api_key=api_key,
            headers=payload.headers if "headers" in fields else None,
            clear_key=payload.clear_key,
            clear_headers=payload.clear_headers,
        )
        provider.key_last4 = credentials.mask_key(secret.api_key)
        provider.has_key = bool(secret.api_key)
        provider.header_names = sorted(secret.headers)
    session.commit()
    session.refresh(provider)
    return provider


def delete_provider(session: Session, provider: Provider) -> None:
    """Delete a provider and its OS credential entry."""
    credentials.delete_secret(provider.id)
    session.delete(provider)
    session.commit()


def clear_provider_credentials(session: Session) -> int:
    """Remove every provider secret while keeping provider configuration."""
    providers = list(session.scalars(select(Provider)).all())
    for provider in providers:
        credentials.delete_secret(provider.id)
        provider.has_key = False
        provider.key_last4 = None
        provider.header_names = []
    session.commit()
    return len(providers)


def provider_slot(provider: Provider) -> threading.BoundedSemaphore:
    """Return the process-local concurrency slot for one provider."""
    limit = max(1, min(int(provider.max_concurrency or 1), 16))
    with _SLOT_LOCK:
        entry = _PROVIDER_SLOTS.get(provider.id)
        if entry is None or entry[1] != limit:
            entry = (threading.BoundedSemaphore(limit), limit)
            _PROVIDER_SLOTS[provider.id] = entry
        return entry[0]


def acquire_provider_slot(provider: Provider) -> bool:
    """Acquire one provider slot, waiting up to the configured threshold."""
    wait_seconds = max(1, min(int(provider.concurrency_wait_seconds or 30), 120))
    return provider_slot(provider).acquire(timeout=float(wait_seconds))


def release_provider_slot(provider: Provider) -> None:
    """Release a provider slot; ignore duplicate releases."""
    try:
        provider_slot(provider).release()
    except ValueError:
        return


def task_budget_exceeded(provider: Provider, spent: float) -> bool:
    """Return True when one provider's task budget has been reached."""
    budget = float(provider.task_budget or 0.0)
    return budget > 0.0 and spent >= budget


def build_client(
    provider: Provider,
    *,
    transport: httpx.BaseTransport | None = None,
) -> ProviderClient:
    """Build a provider client using the current keyring values."""
    secret = credentials.load_secret(provider.id)
    if not secret.api_key:
        raise credentials.CredentialError(
            "credential_missing",
            f"provider {provider.name!r} has no API key",
            "set the API key before testing the connection",
        )
    return ProviderClient(
        kind=provider.kind,
        base_url=provider.base_url,
        model=provider.model,
        api_key=secret.api_key,
        headers=secret.headers,
        timeout_seconds=provider.timeout_seconds,
        max_retries=provider.max_retries,
        proxy_url=provider.proxy_url,
        anthropic_version=provider.anthropic_version,
        organization=provider.organization,
        project=provider.project,
        transport=transport,
    )


def test_provider(
    provider: Provider,
    *,
    transport: httpx.BaseTransport | None = None,
) -> ConnectionResult:
    """Test provider reachability without exposing secrets."""
    return build_client(provider, transport=transport).test_connection()


def list_provider_models(
    provider: Provider,
    *,
    transport: httpx.BaseTransport | None = None,
) -> ModelListResult:
    """List models through the provider adapter."""
    return build_client(provider, transport=transport).list_models()


def record_usage(
    session: Session,
    provider: Provider,
    result: CompletionResult,
    *,
    operation: str,
    estimated_cost: float,
    attempts: int = 1,
    project_id: str | None = None,
    run_id: str | None = None,
    tag: str = "initial",
) -> LlmUsage:
    """Persist one successful provider request."""
    usage = LlmUsage(
        id=uuid.uuid4().hex,
        provider_id=provider.id,
        project_id=project_id,
        run_id=run_id,
        provider_name=provider.name,
        kind=provider.kind,
        model=result.model,
        operation=operation,
        tag=tag,
        input_tokens=result.input_tokens,
        output_tokens=result.output_tokens,
        cached_tokens=result.cached_tokens,
        latency_ms=result.latency_ms,
        estimated_cost=estimated_cost,
        currency=provider.currency,
        attempts=attempts,
    )
    session.add(usage)
    session.commit()
    session.refresh(usage)
    return usage


def provider_usage(session: Session, provider_id: str, *, limit: int = 50) -> list[LlmUsage]:
    """Return the most recent usage entries for one provider."""
    statement = (
        select(LlmUsage)
        .where(LlmUsage.provider_id == provider_id)
        .order_by(LlmUsage.created_at.desc())
        .limit(limit)
    )
    return list(session.scalars(statement).all())
