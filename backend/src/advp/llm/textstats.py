"""Optional AI enhancement for extracted text statistics with strict guards."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from advp.ingest.textstats import TextFactInvalidError
from advp.llm import credentials
from advp.llm.client import CompletionResult, ProviderError
from advp.llm.cost import estimate_cost
from advp.llm.structured import (
    StructuredOutputError,
    complete_structured_for_provider,
)
from advp.models import Provider

PROMPT_VERSION = "textstats-ai-v1"
NUMBER_RE = re.compile(r"\d")


class TextStatsAIItem(BaseModel):
    fact_id: str
    subject_path: str | None = None
    metric: str | None = None
    unit: str | None = None
    qualifier: str | None = None
    relation: str | None = None
    note: str | None = None
    canonical_group: str | None = None
    drop: bool = False


class TextStatsAIResult(BaseModel):
    items: list[TextStatsAIItem] = Field(default_factory=list)


@dataclass(slots=True)
class AIEnhancement:
    facts: list[dict[str, Any]]
    warnings: list[dict[str, str]]
    used: bool
    model: str | None
    input_tokens: int
    output_tokens: int
    estimated_cost: float
    fragments_sent: int
    attempts: int
    provider_id: str
    extra: dict[str, Any] = field(default_factory=dict)

    def summary(self) -> dict[str, Any]:
        return {
            "used": self.used,
            "model": self.model,
            "provider_id": self.provider_id,
            "prompt_version": PROMPT_VERSION,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "estimated_cost": self.estimated_cost,
            "fragments_sent": self.fragments_sent,
            "attempts": self.attempts,
            **self.extra,
        }


def enhance_facts(
    session: Session,
    provider: Provider,
    *,
    facts: list[dict[str, Any]],
    document_text: str,
    max_snippets: int,
    project_id: str | None = None,
) -> AIEnhancement:
    """Send only numeric snippets and apply relabeling/corrections without changing values."""
    numeric: list[dict[str, Any]] = []
    for fact in facts:
        if fact.get("include") is False or not fact.get("fact_id"):
            continue
        snippet = str((fact.get("source") or {}).get("snippet") or "")
        if not snippet or not NUMBER_RE.search(snippet):
            continue
        if snippet not in document_text:
            raise TextFactInvalidError(
                f"source snippet is no longer present: {fact.get('subject_path')} / "
                f"{fact.get('metric')}"
            )
        numeric.append(
            {
                "fact_id": fact.get("fact_id"),
                "subject_path": fact.get("subject_path"),
                "metric": fact.get("metric"),
                "value_text": fact.get("value_text"),
                "unit": fact.get("unit"),
                "qualifier": fact.get("qualifier"),
                "relation": fact.get("relation"),
                "note": fact.get("note"),
                "snippet": snippet[:500],
            }
        )
        if len(numeric) >= max_snippets:
            break
    if not numeric:
        return AIEnhancement(
            facts=facts,
            warnings=[
                {
                    "code": "ai_no_numeric_snippets",
                    "severity": "warning",
                    "message": "no numeric snippets were available for AI enhancement",
                }
            ],
            used=False,
            model=None,
            input_tokens=0,
            output_tokens=0,
            estimated_cost=0.0,
            fragments_sent=0,
            attempts=0,
            provider_id=provider.id,
        )

    messages = [
        {
            "role": "system",
            "content": (
                "You normalize extracted statistical facts. You may only group, correct, "
                "or label the supplied facts. Never add facts, never change numeric values, "
                "units' numeric meaning, or invent source evidence. Return one item per "
                "provided fact_id. Set drop=true only when the fact is not a statistic. "
                "Use the original language for labels."
            ),
        },
        {
            "role": "user",
            "content": json.dumps({"facts": numeric}, ensure_ascii=False),
        },
    ]
    try:
        result = complete_structured_for_provider(
            session,
            provider,
            messages,
            TextStatsAIResult,
            operation="text_stats_ai",
            temperature=0.0,
            max_tokens=1500,
            project_id=project_id,
            tag="text_stats_ai",
        )
    except StructuredOutputError as exc:
        return _failure(
            facts,
            provider,
            exc,
            usages=exc.usages,
            fragments_sent=len(numeric),
        )
    except (ProviderError, credentials.CredentialError) as exc:
        return _failure(
            facts,
            provider,
            exc,
            usages=[],
            fragments_sent=len(numeric),
        )

    known = {str(fact.get("fact_id")): fact for fact in facts}
    updates = {item.fact_id: item for item in result.data.items if item.fact_id in known}
    unknown = len(result.data.items) - len(updates)
    dropped = 0
    enhanced: list[dict[str, Any]] = []
    for fact in facts:
        item = updates.get(str(fact.get("fact_id")))
        if item is None:
            enhanced.append(fact)
            continue
        if item.drop:
            dropped += 1
            continue
        updated = dict(fact)
        for key in ("subject_path", "metric", "unit", "qualifier", "relation", "note"):
            value = getattr(item, key)
            if value is not None:
                updated[key] = value
        if item.canonical_group is not None:
            updated["canonical_group"] = item.canonical_group
        updated["ai_enhanced"] = True
        enhanced.append(updated)

    warnings: list[dict[str, str]] = [
        {
            "code": "ai_enhancement_applied",
            "severity": "info",
            "message": f"AI enhanced {len(updates) - dropped} fact(s)",
        }
    ]
    if unknown:
        warnings.append(
            {
                "code": "ai_unknown_facts",
                "severity": "warning",
                "message": f"discarded {unknown} AI item(s) with unknown fact ids",
            }
        )
    if dropped:
        warnings.append(
            {
                "code": "ai_dropped_facts",
                "severity": "info",
                "message": f"AI dropped {dropped} fact(s)",
            }
        )
    input_tokens, output_tokens, cost = _usage(result.usages, provider)
    return AIEnhancement(
        facts=enhanced,
        warnings=warnings,
        used=True,
        model=result.usages[-1].model if result.usages else provider.model,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        estimated_cost=cost,
        fragments_sent=len(numeric),
        attempts=result.attempts,
        provider_id=provider.id,
    )


def _failure(
    facts: list[dict[str, Any]],
    provider: Provider,
    exc: Exception,
    *,
    usages: list[CompletionResult],
    fragments_sent: int,
) -> AIEnhancement:
    input_tokens, output_tokens, cost = _usage(usages, provider)
    return AIEnhancement(
        facts=facts,
        warnings=[
            {
                "code": "ai_enhancement_failed",
                "severity": "warning",
                "message": f"AI enhancement failed; rule results were kept: {exc}",
            }
        ],
        used=False,
        model=usages[-1].model if usages else provider.model,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        estimated_cost=cost,
        fragments_sent=fragments_sent,
        attempts=len(usages),
        provider_id=provider.id,
        extra={"error": exc.code if isinstance(exc, ProviderError) else "structured_output_error"},
    )


def _usage(
    usages: list[CompletionResult],
    provider: Provider,
) -> tuple[int, int, float]:
    input_tokens = sum(usage.input_tokens for usage in usages)
    output_tokens = sum(usage.output_tokens for usage in usages)
    cost = sum(
        estimate_cost(
            usage.input_tokens,
            usage.output_tokens,
            provider.input_price_per_million,
            provider.output_price_per_million,
        )
        for usage in usages
    )
    return input_tokens, output_tokens, round(cost, 8)


__all__ = [
    "AIEnhancement",
    "TextStatsAIItem",
    "TextStatsAIResult",
    "enhance_facts",
]
