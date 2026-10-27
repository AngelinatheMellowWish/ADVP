"""JSON structured-output validation with one repair retry."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Protocol

import httpx
from pydantic import BaseModel, ValidationError
from sqlalchemy.orm import Session

from advp.llm import providers as provider_service
from advp.llm.client import CompletionResult
from advp.llm.cost import estimate_cost
from advp.models import Provider


class CompletionClient(Protocol):
    """The subset of ProviderClient used by structured output."""

    def complete(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float = 0.0,
        max_tokens: int = 1024,
        json_mode: bool = False,
    ) -> CompletionResult: ...


class StructuredOutputError(Exception):
    """The provider did not return schema-valid JSON."""

    code = "structured_output_error"
    status_code = 502

    def __init__(
        self,
        message: str,
        *,
        hint: str | None = None,
        usages: list[CompletionResult] | None = None,
    ) -> None:
        super().__init__(message)
        self.hint = hint
        self.usages = usages or []


@dataclass(frozen=True, slots=True)
class StructuredResult[T: BaseModel]:
    """Validated model plus the raw text and per-attempt usage."""

    data: T
    text: str
    attempts: int
    usages: list[CompletionResult]


def complete_structured[T: BaseModel](
    client: CompletionClient,
    messages: list[dict[str, str]],
    schema: type[T],
    *,
    temperature: float = 0.0,
    max_tokens: int = 1024,
    repair_attempts: int = 1,
) -> StructuredResult[T]:
    """Request JSON, validate it, and repair once on failure."""
    schema_json = json.dumps(schema.model_json_schema(), ensure_ascii=False)
    instruction = (
        "Return only one JSON object. Do not use markdown fences or commentary. "
        "It must validate against this JSON Schema:\n"
        f"{schema_json}"
    )
    base_messages = [{"role": "system", "content": instruction}, *messages]
    attempt_messages = list(base_messages)
    usages: list[CompletionResult] = []
    last_error: ValidationError | None = None

    for attempt in range(repair_attempts + 1):
        result = client.complete(
            attempt_messages,
            temperature=temperature,
            max_tokens=max_tokens,
            json_mode=True,
        )
        usages.append(result)
        text = _strip_code_fence(result.text)
        try:
            data = schema.model_validate_json(text)
        except ValidationError as exc:
            last_error = exc
            if attempt >= repair_attempts:
                break
            errors = "; ".join(
                f"{'.'.join(str(part) for part in error['loc']) or 'root'}: {error['msg']}"
                for error in exc.errors()
            )
            attempt_messages = [
                *base_messages,
                {"role": "assistant", "content": result.text},
                {
                    "role": "user",
                    "content": (
                        f"The previous response was invalid JSON for the schema: {errors}. "
                        "Return only corrected JSON that validates against the schema."
                    ),
                },
            ]
        else:
            return StructuredResult(
                data=data,
                text=text,
                attempts=attempt + 1,
                usages=usages,
            )

    assert last_error is not None
    raise StructuredOutputError(
        f"provider did not return valid {schema.__name__} JSON after {len(usages)} attempt(s)",
        hint=str(last_error),
        usages=usages,
    )


def complete_structured_for_provider[T: BaseModel](
    session: Session,
    provider: Provider,
    messages: list[dict[str, str]],
    schema: type[T],
    *,
    operation: str = "structured",
    temperature: float = 0.0,
    max_tokens: int = 1024,
    repair_attempts: int = 1,
    transport: httpx.BaseTransport | None = None,
    project_id: str | None = None,
    run_id: str | None = None,
    tag: str = "initial",
) -> StructuredResult[T]:
    """Run structured output and persist every attempt's usage."""
    client = provider_service.build_client(provider, transport=transport)
    try:
        result = complete_structured(
            client,
            messages,
            schema,
            temperature=temperature,
            max_tokens=max_tokens,
            repair_attempts=repair_attempts,
        )
    except StructuredOutputError as exc:
        _record_usages(
            session,
            provider,
            exc.usages,
            operation,
            project_id,
            run_id=run_id,
            tag=tag,
        )
        raise
    _record_usages(
        session,
        provider,
        result.usages,
        operation,
        project_id,
        run_id=run_id,
        tag=tag,
    )
    return result


def _record_usages(
    session: Session,
    provider: Provider,
    usages: list[CompletionResult],
    operation: str,
    project_id: str | None = None,
    *,
    run_id: str | None = None,
    tag: str = "initial",
) -> None:
    for index, usage in enumerate(usages, start=1):
        cost = estimate_cost(
            usage.input_tokens,
            usage.output_tokens,
            provider.input_price_per_million,
            provider.output_price_per_million,
        )
        provider_service.record_usage(
            session,
            provider,
            usage,
            operation=operation,
            estimated_cost=cost,
            attempts=index,
            project_id=project_id,
            run_id=run_id,
            tag=tag,
        )


def _strip_code_fence(text: str) -> str:
    stripped = text.strip()
    if not stripped.startswith("```"):
        return stripped
    lines = stripped.splitlines()
    if lines and lines[0].startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].strip() == "```":
        lines = lines[:-1]
    return "\n".join(lines).strip()
