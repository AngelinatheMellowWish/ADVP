"""Token-cost estimation for provider requests."""

from __future__ import annotations


def estimate_cost(
    input_tokens: int,
    output_tokens: int,
    input_price_per_million: float,
    output_price_per_million: float,
) -> float:
    """Estimate cost from per-million-token prices."""
    cost = max(0, input_tokens) / 1_000_000 * max(0.0, input_price_per_million) + max(
        0, output_tokens
    ) / 1_000_000 * max(0.0, output_price_per_million)
    return round(cost, 8)
