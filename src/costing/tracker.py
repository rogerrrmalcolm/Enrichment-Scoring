from __future__ import annotations

from dataclasses import dataclass, field
from math import ceil

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
        vendor="local",
        model="deterministic_python",
        source_label="Local scoring engine (not billable)",
        source_url="",
        input_cost_per_1m_tokens=0.0,
        cached_input_cost_per_1m_tokens=0.0,
        output_cost_per_1m_tokens=0.0,
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


@dataclass(slots=True)
class OperationTotals:
    requests: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    search_content_input_tokens: int = 0
    tool_calls: int = 0
    cost_usd: float = 0.0

    def average_prompt_tokens(self, default_value: int) -> int:
        if self.requests == 0:
            return default_value
        return max(1, round(self.prompt_tokens / self.requests))

    def average_completion_tokens(self, default_value: int) -> int:
        if self.requests == 0:
            return default_value
        return max(1, round(self.completion_tokens / self.requests))

    def average_tool_calls(self, default_value: int) -> int:
        if self.requests == 0:
            return default_value
        return max(0, round(self.tool_calls / self.requests))

    def average_search_tokens(self, default_value: int) -> int:
        if self.requests == 0:
            return default_value
        return max(0, round(self.search_content_input_tokens / self.requests))


@dataclass(slots=True)
class CostTracker:
    pricing: dict[str, OperationPricing] = field(default_factory=lambda: DEFAULT_PRICING.copy())
    total_cost_usd: float = 0.0
    total_requests: int = 0
    total_prompt_tokens: int = 0
    total_completion_tokens: int = 0
    total_search_content_input_tokens: int = 0
    total_tool_calls: int = 0
    cache_hits: int = 0
    cache_misses: int = 0
    avoided_cost_usd: float = 0.0
    total_rate_limit_wait_seconds: float = 0.0
    operations: dict[str, OperationTotals] = field(default_factory=dict)
    vendor_breakdown: dict[str, dict[str, float | int]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for operation in self.pricing:
            self.operations.setdefault(operation, OperationTotals())

    def record_operation(
        self,
        operation: str,
        prompt_tokens: int,
        completion_tokens: int,
        *,
        tool_calls: int = 0,
        search_content_input_tokens: int | None = None,
    ) -> float:
        pricing = self.pricing[operation]
        effective_search_tokens = (
            pricing.fixed_search_content_input_tokens
            if search_content_input_tokens is None
            else search_content_input_tokens
        )
        cost_usd = estimate_operation_cost(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            pricing=pricing,
            tool_calls=tool_calls,
            search_content_input_tokens=effective_search_tokens,
        )
        totals = self.operations.setdefault(operation, OperationTotals())
        totals.requests += 1
        totals.prompt_tokens += prompt_tokens
        totals.completion_tokens += completion_tokens
        totals.search_content_input_tokens += effective_search_tokens
        totals.tool_calls += tool_calls
        totals.cost_usd = round(totals.cost_usd + cost_usd, 6)

        self.total_requests += 1
        self.total_prompt_tokens += prompt_tokens
        self.total_completion_tokens += completion_tokens
        self.total_search_content_input_tokens += effective_search_tokens
        self.total_tool_calls += tool_calls
        self.total_cost_usd = round(self.total_cost_usd + cost_usd, 6)

        vendor_key = f"{pricing.vendor}:{pricing.model}"
        if vendor_key not in self.vendor_breakdown:
            self.vendor_breakdown[vendor_key] = {
                "requests": 0,
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "search_content_input_tokens": 0,
                "tool_calls": 0,
                "cost_usd": 0.0,
            }
        bucket = self.vendor_breakdown[vendor_key]
        bucket["requests"] += 1
        bucket["prompt_tokens"] += prompt_tokens
        bucket["completion_tokens"] += completion_tokens
        bucket["search_content_input_tokens"] += effective_search_tokens
        bucket["tool_calls"] += tool_calls
        bucket["cost_usd"] = round(float(bucket["cost_usd"]) + cost_usd, 6)
        return cost_usd

    def record_cache_hit(self, estimated_saved_cost_usd: float) -> None:
        self.cache_hits += 1
        self.avoided_cost_usd = round(self.avoided_cost_usd + estimated_saved_cost_usd, 6)

    def record_cache_miss(self) -> None:
        self.cache_misses += 1

    def record_rate_limit_wait(self, wait_seconds: float) -> None:
        self.total_rate_limit_wait_seconds = round(self.total_rate_limit_wait_seconds + wait_seconds, 6)

    def snapshot(self, *, total_contacts: int, total_organizations: int) -> dict[str, object]:
        dedup_ratio = (total_contacts / total_organizations) if total_organizations else 1.0
        effective_cost_per_contact = self.total_cost_usd / max(total_contacts, 1)
        effective_cost_per_organization = self.total_cost_usd / max(total_organizations, 1)
        cache_hit_rate = self.cache_hits / max(self.cache_hits + self.cache_misses, 1)
        total_api_requests = sum(
            totals.requests
            for operation, totals in self.operations.items()
            if self.pricing[operation].vendor != "local"
        )
        total_local_calls = sum(
            totals.requests
            for operation, totals in self.operations.items()
            if self.pricing[operation].vendor == "local"
        )
        return {
            "total_cost_usd": round(self.total_cost_usd, 6),
            "total_requests": self.total_requests,
            "total_operation_calls": self.total_requests,
            "total_api_requests": total_api_requests,
            "total_local_calls": total_local_calls,
            "total_prompt_tokens": self.total_prompt_tokens,
            "total_completion_tokens": self.total_completion_tokens,
            "total_search_content_input_tokens": self.total_search_content_input_tokens,
            "total_tool_calls": self.total_tool_calls,
            "cache_hits": self.cache_hits,
            "cache_misses": self.cache_misses,
            "cache_hit_rate": round(cache_hit_rate, 4),
            "avoided_cost_usd": round(self.avoided_cost_usd, 6),
            "total_rate_limit_wait_seconds": round(self.total_rate_limit_wait_seconds, 6),
            "effective_cost_per_contact_usd": round(effective_cost_per_contact, 6),
            "effective_cost_per_organization_usd": round(effective_cost_per_organization, 6),
            "dedup_ratio_contacts_per_org": round(dedup_ratio, 4),
            "operation_breakdown": self._operation_breakdown(),
            "vendor_breakdown": self.vendor_breakdown,
            "projections": self._build_scale_projections(dedup_ratio),
        }

    def _operation_breakdown(self) -> dict[str, dict[str, float | int | str]]:
        payload: dict[str, dict[str, float | int | str]] = {}
        for operation, totals in self.operations.items():
            pricing = self.pricing[operation]
            payload[operation] = {
                "operation": operation,
                "vendor": pricing.vendor,
                "model": pricing.model,
                "source_label": pricing.source_label,
                "source_url": pricing.source_url,
                "requests": totals.requests,
                "prompt_tokens": totals.prompt_tokens,
                "completion_tokens": totals.completion_tokens,
                "search_content_input_tokens": totals.search_content_input_tokens,
                "tool_calls": totals.tool_calls,
                "cost_usd": round(totals.cost_usd, 6),
                "avg_prompt_tokens": totals.average_prompt_tokens(pricing.default_prompt_tokens),
                "avg_completion_tokens": totals.average_completion_tokens(pricing.default_completion_tokens),
                "avg_search_content_input_tokens": totals.average_search_tokens(pricing.fixed_search_content_input_tokens),
                "avg_tool_calls": totals.average_tool_calls(pricing.default_tool_calls),
                "cached_input_supported": pricing.cached_input_cost_per_1m_tokens is not None,
            }
        return payload

    def _build_scale_projections(self, dedup_ratio: float) -> list[dict[str, object]]:
        projections: list[dict[str, object]] = []
        enrichment_totals = self.operations.get("enrichment", OperationTotals())
        scoring_totals = self.operations.get("scoring", OperationTotals())
        for target_contacts in (100, 1000, 5000):
            estimated_orgs = max(1, ceil(target_contacts / max(dedup_ratio, 1.0)))
            cold_enrichment = self._project_operation_cost("enrichment", estimated_orgs, enrichment_totals, use_cached_input_rate=False)
            cold_scoring = self._project_operation_cost("scoring", target_contacts, scoring_totals, use_cached_input_rate=False)
            provider_cached_enrichment = self._project_operation_cost("enrichment", estimated_orgs, enrichment_totals, use_cached_input_rate=True)
            provider_cached_scoring = self._project_operation_cost("scoring", target_contacts, scoring_totals, use_cached_input_rate=True)
            app_cached_scoring = self._project_operation_cost("scoring", target_contacts, scoring_totals, use_cached_input_rate=False)
            cold_total = cold_enrichment + cold_scoring
            provider_cache_total = provider_cached_enrichment + provider_cached_scoring
            app_cache_total = app_cached_scoring
            projections.append(
                {
                    "target_contacts": target_contacts,
                    "estimated_organizations": estimated_orgs,
                    "cold_start_cost_usd": round(cold_total, 6),
                    "provider_cache_cost_usd": round(provider_cache_total, 6),
                    "app_cache_cost_usd": round(app_cache_total, 6),
                    "provider_cache_savings_usd": round(cold_total - provider_cache_total, 6),
                    "app_cache_savings_usd": round(cold_total - app_cache_total, 6),
                }
            )
        return projections

    def _project_operation_cost(
        self,
        operation: str,
        projected_requests: int,
        totals: OperationTotals,
        *,
        use_cached_input_rate: bool,
    ) -> float:
        pricing = self.pricing[operation]
        avg_prompt_tokens = totals.average_prompt_tokens(pricing.default_prompt_tokens)
        avg_completion_tokens = totals.average_completion_tokens(pricing.default_completion_tokens)
        avg_search_tokens = totals.average_search_tokens(pricing.fixed_search_content_input_tokens)
        avg_tool_calls = totals.average_tool_calls(pricing.default_tool_calls)
        unit_cost = estimate_operation_cost(
            prompt_tokens=avg_prompt_tokens,
            completion_tokens=avg_completion_tokens,
            pricing=pricing,
            tool_calls=avg_tool_calls,
            use_cached_input_rate=use_cached_input_rate,
            search_content_input_tokens=avg_search_tokens,
        )
        return projected_requests * unit_cost
