from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class OperationPricing:
    operation: str
    vendor: str
    model: str #data classses used later
    prompt_cost_per_1k_tokens: float
    completion_cost_per_1k_tokens: float
    default_prompt_tokens: int
    default_completion_tokens: int


DEFAULT_PRICING: dict[str, OperationPricing] = {
    "enrichment": OperationPricing(
        operation="enrichment",
        vendor="estimated",
        model="org-research-sim",
        prompt_cost_per_1k_tokens=0.003,
        completion_cost_per_1k_tokens=0.015,
        default_prompt_tokens=320,
        default_completion_tokens=420,
    ),
    "scoring": OperationPricing(
        operation="scoring",
        vendor="estimated",
        model="scoring-sim",
        prompt_cost_per_1k_tokens=0.003,
        completion_cost_per_1k_tokens=0.015,
        default_prompt_tokens=300,
        default_completion_tokens=260,
    ),
}


def estimate_operation_cost(prompt_tokens: int, completion_tokens: int, pricing: OperationPricing) -> float:
    prompt_cost = (prompt_tokens / 1000.0) * pricing.prompt_cost_per_1k_tokens
    completion_cost = (completion_tokens / 1000.0) * pricing.completion_cost_per_1k_tokens
    return round(prompt_cost + completion_cost, 6)
#function for the rate limiting/tracking the token costs