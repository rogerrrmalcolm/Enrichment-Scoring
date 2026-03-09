from __future__ import annotations

from dataclasses import dataclass
#PRICING OF ALL THE DATACLASSES, WORKS WITH PRICING.PY
@dataclass(frozen=True, slots=True)
class OperationPricing:
    operation: str
    vendor: str
    model: str
    source_label: str
    source_url: str
    input_cost_per_1m_tokens: float
    cached_input_cost_per_1m_tokens: float | None
    output_cost_per_1m_tokens: float
    web_search_cost_per_1k_calls: float = 0.0
    fixed_search_content_input_tokens: int = 0
    default_prompt_tokens: int = 0
    default_completion_tokens: int = 0
    default_tool_calls: int = 0


DEFAULT_PRICING: dict[str, OperationPricing] = {
    "enrichment": OperationPricing(
        operation="enrichment",
        vendor="openai",
        model="gpt-4.1-mini + web search",
        source_label="OpenAI platform pricing and web-search pricing",
        source_url="https://platform.openai.com/pricing",
        input_cost_per_1m_tokens=0.40,
        cached_input_cost_per_1m_tokens=0.10,
        output_cost_per_1m_tokens=1.60,
        web_search_cost_per_1k_calls=10.0,
        fixed_search_content_input_tokens=8000,
        default_prompt_tokens=320,
        default_completion_tokens=420,
        default_tool_calls=1,
    ),
    "scoring": OperationPricing(
        operation="scoring",
        vendor="openai",
        model="gpt-5-mini",
        source_label="OpenAI API pricing",
        source_url="https://openai.com/api/pricing/",
        input_cost_per_1m_tokens=0.25,
        cached_input_cost_per_1m_tokens=0.025,
        output_cost_per_1m_tokens=2.00,
        default_prompt_tokens=300,
        default_completion_tokens=260,
        default_tool_calls=0,
    ),
}


def estimate_operation_cost(
    *,
    prompt_tokens: int,
    completion_tokens: int,
    pricing: OperationPricing,
    tool_calls: int = 0,
    use_cached_input_rate: bool = False,
    search_content_input_tokens: int | None = None,
) -> float:
    search_tokens = (
        pricing.fixed_search_content_input_tokens
        if search_content_input_tokens is None
        else search_content_input_tokens
    )
    total_input_tokens = prompt_tokens + search_tokens
    input_rate = (
        pricing.cached_input_cost_per_1m_tokens
        if use_cached_input_rate and pricing.cached_input_cost_per_1m_tokens is not None
        else pricing.input_cost_per_1m_tokens
    )
    input_cost = (total_input_tokens / 1_000_000) * input_rate
    output_cost = (completion_tokens / 1_000_000) * pricing.output_cost_per_1m_tokens
    tool_cost = (tool_calls / 1000.0) * pricing.web_search_cost_per_1k_calls
    return round(input_cost + output_cost + tool_cost, 6)
