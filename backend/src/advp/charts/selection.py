"""AI chart selection orchestration, scoring, fallback, and persistence."""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import httpx
from sqlalchemy.orm import Session

from advp.charts.prompts import (
    PROMPT_VERSION,
    SelectionOutput,
    SelectionValidationError,
    build_correction_messages,
    build_dataset_context,
    build_selection_messages,
    candidate_payload,
    validate_selection,
)
from advp.charts.registry import ChartIntent
from advp.charts.scoring import (
    MAX_RESELECTS,
    ScoredCandidate,
    needs_reselection,
    score_candidates,
    top_candidates,
)
from advp.charts.selector import (
    ArrayContext,
    Candidate,
    ChartSelectionError,
    TableContext,
    build_array_context,
    build_table_context,
    select_array_candidates,
    select_table_candidates,
)
from advp.costs import check_budget
from advp.llm import credentials
from advp.llm import providers as provider_service
from advp.llm.client import ProviderError
from advp.llm.cost import estimate_cost
from advp.llm.structured import (
    StructuredOutputError,
    complete_structured_for_provider,
)
from advp.models import ChartSelection, Dataset, Provider

logger = logging.getLogger("advp.selection")


@dataclass(slots=True)
class _UsageTotals:
    input_tokens: int = 0
    output_tokens: int = 0
    cached_tokens: int = 0
    estimated_cost: float = 0.0
    currency: str = "USD"


@dataclass(slots=True)
class _SelectionState:
    scored: list[ScoredCandidate]
    context: TableContext | ArrayContext
    context_payload: dict[str, Any]
    candidates_payload: list[dict[str, Any]]
    attempts: int = 0
    reselects: int = 0
    usage: _UsageTotals = field(default_factory=_UsageTotals)
    last_error: str | None = None


def create_chart_selection(
    session: Session,
    dataset: Dataset,
    *,
    intent: ChartIntent | None = None,
    provider_id: str | None = None,
    max_reselects: int = MAX_RESELECTS,
    transport: httpx.BaseTransport | None = None,
    run_id: str | None = None,
) -> ChartSelection:
    """Run AI selection with provider failover, scoring, and rule fallback."""
    state = _prepare_state(dataset, intent)
    budget = check_budget(session, dataset.project_id).to_dict()
    if budget["exceeded"]:
        return _persist_degraded(
            session,
            dataset,
            state,
            intent,
            failures=[f"budget: {budget['reason']}"],
            budget=budget,
        )
    providers = _ordered_providers(session, provider_id)
    if not providers:
        return _persist_degraded(
            session,
            dataset,
            state,
            intent,
            failures=["no provider configured"],
            budget=budget,
        )

    feedback: str | None = None
    limit = max(0, min(int(max_reselects), MAX_RESELECTS))
    for provider in providers:
        while True:
            state.attempts += 1
            messages = build_selection_messages(
                context_payload=state.context_payload,
                candidates=state.candidates_payload,
                intent=intent,
                feedback=feedback,
            )
            try:
                structured = complete_structured_for_provider(
                    session,
                    provider,
                    messages,
                    SelectionOutput,
                    operation="chart_selection",
                    temperature=0.0,
                    max_tokens=1200,
                    repair_attempts=1,
                    transport=transport,
                    project_id=dataset.project_id,
                    run_id=run_id,
                    tag="reselect" if state.reselects else "initial",
                )
            except (ProviderError, StructuredOutputError, credentials.CredentialError) as exc:
                if isinstance(exc, StructuredOutputError):
                    _add_usage(state.usage, provider, exc.usages)
                state.last_error = f"{provider.name}: {exc}"
                break
            _add_usage(state.usage, provider, structured.usages)
            try:
                output = validate_selection(
                    structured.data,
                    _candidate_list(state),
                    state.context,
                )
            except SelectionValidationError as exc:
                state.last_error = f"{provider.name}: {exc}"
                break

            if needs_reselection(state.scored) and state.reselects < limit:
                state.reselects += 1
                feedback = _reselect_feedback(state.scored, output)
                continue
            return _persist_success(
                session,
                dataset,
                state,
                provider,
                output,
                intent,
                needs_confirmation=needs_reselection(state.scored),
                budget=budget,
            )

    return _persist_degraded(
        session,
        dataset,
        state,
        intent,
        failures=[state.last_error or "all providers failed"],
        budget=budget,
    )


def correct_chart_selection(
    session: Session,
    parent: ChartSelection,
    instruction: str,
    *,
    provider_id: str | None = None,
    transport: httpx.BaseTransport | None = None,
    run_id: str | None = None,
) -> ChartSelection:
    """Apply a natural-language correction as a child selection."""
    instruction = instruction.strip()
    if not instruction:
        raise ChartSelectionError("invalid_instruction", "correction instruction is empty")
    dataset = session.get(Dataset, parent.dataset_id)
    if dataset is None:
        raise ChartSelectionError(
            "dataset_not_found",
            "selection dataset no longer exists",
            status_code=404,
        )
    intent = ChartIntent(parent.intent) if parent.intent else None
    state = _prepare_state(dataset, intent)
    budget = check_budget(session, dataset.project_id).to_dict()
    if budget["exceeded"]:
        raise ChartSelectionError(
            "budget_exceeded",
            f"AI correction blocked by budget: {budget['reason']}",
            status_code=409,
        )
    providers = _ordered_providers(session, provider_id)
    if not providers:
        raise ChartSelectionError(
            "no_provider",
            "no provider is configured for correction",
            status_code=503,
        )

    previous = parent.result_json or {}
    last_error: str | None = None
    for provider in providers:
        state.attempts += 1
        messages = build_correction_messages(
            context_payload=state.context_payload,
            candidates=state.candidates_payload,
            intent=intent,
            previous=previous,
            instruction=instruction,
        )
        try:
            structured = complete_structured_for_provider(
                session,
                provider,
                messages,
                SelectionOutput,
                operation="chart_correction",
                temperature=0.0,
                max_tokens=1200,
                repair_attempts=1,
                transport=transport,
                project_id=dataset.project_id,
                run_id=run_id,
                tag="correction",
            )
        except (ProviderError, StructuredOutputError, credentials.CredentialError) as exc:
            if isinstance(exc, StructuredOutputError):
                _add_usage(state.usage, provider, exc.usages)
            last_error = f"{provider.name}: {exc}"
            continue
        _add_usage(state.usage, provider, structured.usages)
        try:
            output = validate_selection(
                structured.data,
                _candidate_list(state),
                state.context,
            )
        except SelectionValidationError as exc:
            last_error = f"{provider.name}: {exc}"
            continue
        winner = next(
            (item for item in state.scored if item.candidate.spec.id == output.selected.chart_id),
            None,
        )
        if winner is None:
            last_error = f"{provider.name}: selected chart is not in the candidate set"
            continue
        return _persist_success(
            session,
            dataset,
            state,
            provider,
            output,
            intent,
            needs_confirmation=needs_reselection([winner]),
            budget=budget,
            winner=winner,
            parent_selection_id=parent.id,
            correction_instruction=instruction,
        )
    raise ChartSelectionError(
        "correction_failed",
        last_error or "all providers failed",
        status_code=502,
    )


def selection_result(row: ChartSelection) -> dict[str, Any]:
    """Return the stored API result for one selection row."""
    return dict(row.result_json)


def selection_summary(row: ChartSelection) -> dict[str, Any]:
    """Return a compact list-view summary for one selection."""
    return {
        "id": row.id,
        "dataset_id": row.dataset_id,
        "selected_chart_id": row.selected_chart_id,
        "score": row.selected_score,
        "degraded": row.degraded,
        "needs_confirmation": row.needs_confirmation,
        "provider_name": row.provider_name,
        "created_at": row.created_at,
    }


def list_dataset_selections(
    session: Session,
    dataset_id: str,
    *,
    limit: int = 20,
) -> list[ChartSelection]:
    """Return recent selections for one dataset, newest first."""
    from sqlalchemy import select

    statement = (
        select(ChartSelection)
        .where(ChartSelection.dataset_id == dataset_id)
        .order_by(ChartSelection.created_at.desc())
        .limit(limit)
    )
    return list(session.scalars(statement).all())


def get_selection(session: Session, selection_id: str) -> ChartSelection | None:
    """Return one persisted selection."""
    return session.get(ChartSelection, selection_id)


def _prepare_state(dataset: Dataset, intent: ChartIntent | None) -> _SelectionState:
    if dataset.kind == "table":
        table_context = build_table_context(
            dataset.schema_json,
            row_count=dataset.row_count,
            sampled=dataset.sampled,
            is_stream=str(dataset.options.get("source_kind") or "") in {"websocket", "kafka"},
        )
        context: TableContext | ArrayContext = table_context
        candidates = select_table_candidates(table_context, intent).candidates
    elif dataset.kind == "array":
        schema = dataset.schema_json
        context = build_array_context(
            variable=str(schema.get("variable", dataset.name)),
            shape=schema.get("shape", []),
            dims=schema.get("dims", []),
            dtype=str(schema.get("dtype", "")),
            units=schema.get("units"),
            sampled=dataset.sampled,
            format=dataset.format,
        )
        candidates = select_array_candidates(context, intent).candidates
    else:
        raise ChartSelectionError(
            "unsupported_kind",
            f"dataset kind {dataset.kind!r} has no chart selection",
        )
    if not candidates:
        raise ChartSelectionError(
            "no_candidates",
            "the rule engine returned no chart candidates",
            "relax the intent, fix blocking quality issues, or add a provider",
        )
    scored = score_candidates(candidates, context, intent)
    context_payload = build_dataset_context(
        schema_definition=dataset.schema_json,
        profile=dataset.profile_json,
        row_count=dataset.row_count,
        sampled=dataset.sampled,
        kind=dataset.kind,
    )
    return _SelectionState(
        scored=scored,
        context=context,
        context_payload=context_payload,
        candidates_payload=[candidate_payload(candidate) for candidate in candidates],
    )


def _candidate_list(state: _SelectionState) -> list[Candidate]:
    return [item.candidate for item in state.scored]


def _ordered_providers(session: Session, provider_id: str | None) -> list[Provider]:
    if provider_id:
        provider = provider_service.get_provider(session, provider_id)
        return [provider] if provider is not None else []
    return provider_service.list_providers(session)


def _add_usage(
    totals: _UsageTotals,
    provider: Provider,
    usages: list[Any],
) -> None:
    totals.currency = provider.currency
    for usage in usages:
        totals.input_tokens += usage.input_tokens
        totals.output_tokens += usage.output_tokens
        totals.cached_tokens += usage.cached_tokens
        totals.estimated_cost += estimate_cost(
            usage.input_tokens,
            usage.output_tokens,
            provider.input_price_per_million,
            provider.output_price_per_million,
        )


def _reselect_feedback(scored: list[ScoredCandidate], output: SelectionOutput) -> str:
    top = top_candidates(scored, limit=3)
    lines = [
        f"The previous selection {output.selected.chart_id!r} scored "
        f"{_score_for(scored, output.selected.chart_id):.4f}.",
        "Top candidates by rule score:",
    ]
    for item in top:
        lines.append(f"- {item.candidate.spec.id}: {item.total:.4f} ({item.candidate.why})")
    lines.append(
        "Re-select the chart that best fits the data and intent. "
        "Do not exceed the candidate set and keep all fields valid."
    )
    return "\n".join(lines)


def _score_for(scored: list[ScoredCandidate], chart_id: str) -> float:
    return next(
        (item.total for item in scored if item.candidate.spec.id == chart_id),
        0.0,
    )


def _persist_success(
    session: Session,
    dataset: Dataset,
    state: _SelectionState,
    provider: Provider,
    output: SelectionOutput,
    intent: ChartIntent | None,
    *,
    needs_confirmation: bool,
    budget: dict[str, Any] | None = None,
    winner: ScoredCandidate | None = None,
    parent_selection_id: str | None = None,
    correction_instruction: str | None = None,
) -> ChartSelection:
    if winner is None:
        winner = state.scored[0]
    options = [output.selected, *output.alternatives]
    match = next(
        (option for option in options if option.chart_id == winner.candidate.spec.id),
        None,
    )
    fields = match.fields if match is not None else winner.candidate.suggested_fields
    reason = match.reason if match is not None else winner.candidate.why
    confidence = match.confidence if match is not None else None
    style = (
        match.style.model_dump(exclude_none=True, exclude_defaults=True)
        if match is not None and match.style is not None
        else None
    )
    result = _result_payload(
        selection_id=uuid.uuid4().hex,
        created_at=datetime.now(UTC),
        dataset=dataset,
        intent=intent,
        provider=provider,
        state=state,
        winner=winner,
        output=output,
        fields=fields,
        reason=reason,
        confidence=confidence,
        style=style,
        degraded=False,
        degradation_reason=None,
        needs_confirmation=needs_confirmation,
        budget=budget,
        parent_selection_id=parent_selection_id,
        correction_instruction=correction_instruction,
    )
    row = ChartSelection(
        id=result["id"],
        dataset_id=dataset.id,
        project_id=dataset.project_id,
        provider_id=provider.id,
        parent_selection_id=parent_selection_id,
        provider_name=provider.name,
        model=provider.model,
        prompt_version=PROMPT_VERSION,
        intent=intent.value if intent is not None else None,
        selected_chart_id=winner.candidate.spec.id,
        selected_score=winner.total,
        confidence=confidence,
        degraded=False,
        needs_confirmation=needs_confirmation,
        attempts=state.attempts,
        reselects=state.reselects,
        input_tokens=state.usage.input_tokens,
        output_tokens=state.usage.output_tokens,
        cached_tokens=state.usage.cached_tokens,
        estimated_cost=round(state.usage.estimated_cost, 8),
        currency=provider.currency,
        degradation_reason=None,
        result_json=result,
        context_json=state.context_payload,
        candidates_json=state.candidates_payload,
        output_json=output.model_dump(),
        created_at=datetime.fromisoformat(result["created_at"]),
    )
    session.add(row)
    session.commit()
    session.refresh(row)
    logger.info(
        "selection_succeeded",
        extra={
            "selection_id": row.id,
            "project_id": dataset.project_id,
            "chart_id": row.selected_chart_id,
            "provider": provider.name,
            "model": row.model,
            "attempts": row.attempts,
            "reselects": row.reselects,
            "input_tokens": row.input_tokens,
            "output_tokens": row.output_tokens,
            "estimated_cost": row.estimated_cost,
            "degraded": False,
        },
    )
    return row


def _persist_degraded(
    session: Session,
    dataset: Dataset,
    state: _SelectionState,
    intent: ChartIntent | None,
    *,
    failures: list[str],
    budget: dict[str, Any] | None = None,
) -> ChartSelection:
    winner = state.scored[0]
    reason = "Rule fallback: " + "; ".join(failures)
    result = _result_payload(
        selection_id=uuid.uuid4().hex,
        created_at=datetime.now(UTC),
        dataset=dataset,
        intent=intent,
        provider=None,
        state=state,
        winner=winner,
        output=None,
        fields=winner.candidate.suggested_fields,
        reason=reason,
        confidence=None,
        degraded=True,
        degradation_reason="; ".join(failures),
        needs_confirmation=needs_reselection(state.scored),
        budget=budget,
    )
    row = ChartSelection(
        id=result["id"],
        dataset_id=dataset.id,
        project_id=dataset.project_id,
        provider_id=None,
        provider_name=None,
        model=None,
        prompt_version=PROMPT_VERSION,
        intent=intent.value if intent is not None else None,
        selected_chart_id=winner.candidate.spec.id,
        selected_score=winner.total,
        confidence=None,
        degraded=True,
        needs_confirmation=needs_reselection(state.scored),
        attempts=state.attempts,
        reselects=state.reselects,
        input_tokens=state.usage.input_tokens,
        output_tokens=state.usage.output_tokens,
        cached_tokens=state.usage.cached_tokens,
        estimated_cost=round(state.usage.estimated_cost, 8),
        currency=state.usage.currency,
        degradation_reason="; ".join(failures),
        result_json=result,
        context_json=state.context_payload,
        candidates_json=state.candidates_payload,
        output_json=None,
        created_at=datetime.fromisoformat(result["created_at"]),
    )
    session.add(row)
    session.commit()
    session.refresh(row)
    logger.warning(
        "selection_degraded",
        extra={
            "selection_id": row.id,
            "project_id": dataset.project_id,
            "chart_id": row.selected_chart_id,
            "failures": failures,
            "attempts": row.attempts,
            "input_tokens": row.input_tokens,
            "output_tokens": row.output_tokens,
            "estimated_cost": row.estimated_cost,
            "degraded": True,
        },
    )
    return row


def _result_payload(
    *,
    selection_id: str,
    created_at: datetime,
    dataset: Dataset,
    intent: ChartIntent | None,
    provider: Provider | None,
    state: _SelectionState,
    winner: ScoredCandidate,
    output: SelectionOutput | None,
    fields: dict[str, str],
    reason: str,
    confidence: float | None,
    degraded: bool,
    degradation_reason: str | None,
    needs_confirmation: bool,
    style: dict[str, Any] | None = None,
    budget: dict[str, Any] | None = None,
    parent_selection_id: str | None = None,
    correction_instruction: str | None = None,
) -> dict[str, Any]:
    by_id = {
        option.chart_id: option
        for option in ([output.selected, *output.alternatives] if output is not None else [])
    }
    top3 = []
    for item in top_candidates(state.scored, limit=3):
        option = by_id.get(item.candidate.spec.id)
        top3.append(
            {
                "chart_id": item.candidate.spec.id,
                "name": {
                    "zh": item.candidate.spec.name_zh,
                    "en": item.candidate.spec.name_en,
                },
                "score": item.total,
                "selected": item.candidate.spec.id == winner.candidate.spec.id,
                "reason": (option.reason if option is not None else item.candidate.why),
            }
        )
    spec = winner.candidate.spec
    return {
        "id": selection_id,
        "dataset_id": dataset.id,
        "project_id": dataset.project_id,
        "provider_id": provider.id if provider is not None else None,
        "provider_name": provider.name if provider is not None else None,
        "model": provider.model if provider is not None else None,
        "prompt_version": PROMPT_VERSION,
        "intent": intent.value if intent is not None else None,
        "selected": {
            "chart_id": spec.id,
            "name": {"zh": spec.name_zh, "en": spec.name_en},
            "family": spec.family,
            "backend": spec.backend,
            "fields": fields,
            "aggregation": (
                next(
                    (
                        option.aggregation
                        for option in ([output.selected, *output.alternatives] if output else [])
                        if option.chart_id == spec.id
                    ),
                    None,
                )
                if output is not None
                else None
            ),
            "reason": reason,
            "confidence": confidence,
            "style": style,
            "score": winner.total,
            "dimensions": winner.dimensions,
        },
        "top3": top3,
        "attempts": state.attempts,
        "reselects": state.reselects,
        "degraded": degraded,
        "degradation_reason": degradation_reason,
        "needs_confirmation": needs_confirmation,
        "budget": budget,
        "parent_selection_id": parent_selection_id,
        "correction_instruction": correction_instruction,
        "usage": {
            "input_tokens": state.usage.input_tokens,
            "output_tokens": state.usage.output_tokens,
            "cached_tokens": state.usage.cached_tokens,
            "estimated_cost": round(state.usage.estimated_cost, 8),
            "currency": state.usage.currency,
        },
        "created_at": created_at.isoformat(),
    }
