"""Seven-dimension rule scoring for chart candidates."""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

from advp.charts.registry import ChartIntent
from advp.charts.selector import ArrayContext, Candidate, TableContext

WEIGHTS: dict[str, float] = {
    "data_fit": 0.30,
    "perceptual": 0.20,
    "info_density": 0.15,
    "readability": 0.15,
    "performance": 0.10,
    "accessibility": 0.05,
    "scientific_compliance": 0.05,
}
TOTAL_THRESHOLD = 0.75
GAP_THRESHOLD = 0.08
MAX_RESELECTS = 2

ACCESSIBILITY_SCORES: dict[str, float] = {
    "bar": 0.9,
    "bar_horizontal": 0.92,
    "line_timeseries": 0.95,
    "area_timeseries": 0.85,
    "scatter": 0.85,
    "bubble": 0.7,
    "histogram": 0.85,
    "box": 0.9,
    "violin": 0.8,
    "heatmap": 0.75,
    "pie": 0.6,
    "donut": 0.6,
    "radar": 0.65,
    "parallel": 0.7,
    "regression": 0.85,
    "geo_scatter": 0.7,
    "geo_trajectory": 0.76,
    "geo_density": 0.78,
    "geo_region": 0.74,
    "network_graph": 0.68,
    "sankey_flow": 0.7,
    "sunburst_hierarchy": 0.66,
    "image_slice": 0.8,
    "live_timeseries": 0.84,
    "array_heatmap": 0.75,
}
SCIENTIFIC_SCORES: dict[str, float] = {
    "bar": 0.9,
    "bar_horizontal": 0.9,
    "line_timeseries": 0.95,
    "area_timeseries": 0.85,
    "scatter": 0.9,
    "bubble": 0.75,
    "histogram": 0.9,
    "box": 0.9,
    "violin": 0.85,
    "heatmap": 0.85,
    "pie": 0.5,
    "donut": 0.5,
    "radar": 0.65,
    "parallel": 0.75,
    "regression": 0.85,
    "geo_scatter": 0.8,
    "geo_trajectory": 0.82,
    "geo_density": 0.8,
    "geo_region": 0.82,
    "network_graph": 0.75,
    "sankey_flow": 0.8,
    "sunburst_hierarchy": 0.7,
    "image_slice": 0.9,
    "live_timeseries": 0.9,
    "array_heatmap": 0.85,
}


@dataclass(frozen=True, slots=True)
class ScoredCandidate:
    """A candidate with its seven dimension scores and weighted total."""

    candidate: Candidate
    dimensions: dict[str, float]
    total: float


def score_candidates(
    candidates: Sequence[Candidate],
    context: TableContext | ArrayContext,
    intent: ChartIntent | None = None,
) -> list[ScoredCandidate]:
    """Score candidates and return them from highest to lowest total."""
    scored = [
        ScoredCandidate(
            candidate=candidate,
            dimensions=_dimensions(candidate, context, intent),
            total=0.0,
        )
        for candidate in candidates
    ]
    with_totals = [
        ScoredCandidate(
            candidate=item.candidate,
            dimensions=item.dimensions,
            total=round(
                sum(WEIGHTS[name] * value for name, value in item.dimensions.items()),
                4,
            ),
        )
        for item in scored
    ]
    return sorted(with_totals, key=lambda item: (-item.total, item.candidate.spec.id))


def top_candidates(
    scored: Sequence[ScoredCandidate],
    *,
    limit: int = 3,
) -> list[ScoredCandidate]:
    """Return the highest-scoring candidates."""
    return list(scored[: max(1, limit)])


def needs_reselection(scored: Sequence[ScoredCandidate]) -> bool:
    """Return True when the top score or top1/top2 gap is too weak."""
    if not scored:
        return True
    ordered = sorted(scored, key=lambda item: item.total, reverse=True)
    if ordered[0].total < TOTAL_THRESHOLD:
        return True
    return bool(len(ordered) >= 2 and ordered[0].total - ordered[1].total < GAP_THRESHOLD)


def _dimensions(
    candidate: Candidate,
    context: TableContext | ArrayContext,
    intent: ChartIntent | None,
) -> dict[str, float]:
    spec = candidate.spec
    required = spec.required_types
    filled = sum(1 for role in required if role in candidate.suggested_fields)
    fill_ratio = filled / len(required) if required else 1.0
    exact_ratio = candidate.exact_matches / len(required) if required else 1.0
    intent_match = 1.0 if intent is None or intent in spec.intents else 0.0
    data_fit = 0.5 * fill_ratio + 0.3 * exact_ratio + 0.2 * intent_match

    perceptual = float(spec.perceptual_score)
    info_density = min(1.0, 0.5 + 0.1 * len(candidate.suggested_fields))
    readability = _readability(candidate, context)
    performance = _performance(candidate, context)
    accessibility = ACCESSIBILITY_SCORES.get(spec.id, 0.75)
    scientific = SCIENTIFIC_SCORES.get(spec.id, 0.75)

    return {
        "data_fit": round(_clamp(data_fit), 4),
        "perceptual": round(_clamp(perceptual), 4),
        "info_density": round(_clamp(info_density), 4),
        "readability": round(_clamp(readability), 4),
        "performance": round(_clamp(performance), 4),
        "accessibility": round(_clamp(accessibility), 4),
        "scientific_compliance": round(_clamp(scientific), 4),
    }


def _readability(candidate: Candidate, context: TableContext | ArrayContext) -> float:
    if not isinstance(context, TableContext) or not candidate.spec.max_cardinality:
        return 1.0
    columns = {column.name: column for column in context.columns}
    ratios: list[float] = []
    for role, limit in candidate.spec.max_cardinality.items():
        column_name = candidate.suggested_fields.get(role)
        column = columns.get(column_name) if column_name is not None else None
        if column is not None and limit > 0:
            ratios.append(column.cardinality / limit)
    if not ratios:
        return 1.0
    return 1.0 - 0.5 * min(1.0, max(ratios))


def _performance(candidate: Candidate, context: TableContext | ArrayContext) -> float:
    if isinstance(context, TableContext):
        row_count = context.row_count
        sampled = context.sampled
    else:
        row_count = math.prod(context.shape) if context.shape else 0
        sampled = context.sampled
    ratio = min(1.0, row_count / candidate.spec.max_rows)
    return 1.0 - 0.3 * ratio - (0.1 if sampled else 0.0)


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))
