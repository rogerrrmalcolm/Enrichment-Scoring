from __future__ import annotations

from dataclasses import asdict, dataclass, field
from math import ceil

from .pricing import DEFAULT_PRICING, OperationPricing, estimate_operation_cost


@dataclass(slots=True)
class OperationTotals:
    requests: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cost_usd: float = 0.0

    def average_prompt_tokens(self, default_value: int) -> int:
        if self.requests == 0:
            return default_value
        return max(1, round(self.prompt_tokens / self.requests))

    def average_completion_tokens(self, default_value: int) -> int:
        if self.requests == 0:
            return default_value
        return max(1, round(self.completion_tokens / self.requests))


@dataclass(slots=True)
class CostTracker:
    pricing: dict[str, OperationPricing] = field(default_factory=lambda: DEFAULT_PRICING.copy())
    total_cost_usd: float = 0.0
    total_requests: int = 0
    total_prompt_tokens: int = 0
    total_completion_tokens: int = 0
    cache_hits: int = 0
    cache_misses: int = 0
    avoided_cost_usd: float = 0.0
    total_rate_limit_wait_seconds: float = 0.0
    operations: dict[str, OperationTotals] = field(default_factory=dict)
    vendor_breakdown: dict[str, dict[str, float]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for operation in self.pricing:
            self.operations.setdefault(operation, OperationTotals())

    def record_operation(
        self,
        operation: str,
        prompt_tokens: int,
        completion_tokens: int,
    ) -> float:
        pricing = self.pricing[operation]
        cost_usd = estimate_operation_cost(prompt_tokens, completion_tokens, pricing)
        totals = self.operations.setdefault(operation, OperationTotals())
        totals.requests += 1
        totals.prompt_tokens += prompt_tokens
        totals.completion_tokens += completion_tokens
        totals.cost_usd = round(totals.cost_usd + cost_usd, 6)

        self.total_requests += 1
        self.total_prompt_tokens += prompt_tokens
        self.total_completion_tokens += completion_tokens
        self.total_cost_usd = round(self.total_cost_usd + cost_usd, 6)

        vendor_key = f"{pricing.vendor}:{pricing.model}"
        if vendor_key not in self.vendor_breakdown:
            self.vendor_breakdown[vendor_key] = {
                "requests": 0,
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "cost_usd": 0.0,
            }
        bucket = self.vendor_breakdown[vendor_key]
        bucket["requests"] += 1
        bucket["prompt_tokens"] += prompt_tokens
        bucket["completion_tokens"] += completion_tokens
        bucket["cost_usd"] = round(bucket["cost_usd"] + cost_usd, 6)
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
        projections = self._build_scale_projections(dedup_ratio)
        return {
            "total_cost_usd": round(self.total_cost_usd, 6),
            "total_requests": self.total_requests,
            "total_prompt_tokens": self.total_prompt_tokens,
            "total_completion_tokens": self.total_completion_tokens,
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
            "projections": projections,
        }

    def _operation_breakdown(self) -> dict[str, dict[str, float | int | str]]:
        payload: dict[str, dict[str, float | int | str]] = {}
        for operation, totals in self.operations.items():
            pricing = self.pricing[operation]
            payload[operation] = {
                "operation": operation,
                "vendor": pricing.vendor,
                "model": pricing.model,
                "requests": totals.requests,
                "prompt_tokens": totals.prompt_tokens,
                "completion_tokens": totals.completion_tokens,
                "cost_usd": round(totals.cost_usd, 6),
                "avg_prompt_tokens": totals.average_prompt_tokens(pricing.default_prompt_tokens),
                "avg_completion_tokens": totals.average_completion_tokens(pricing.default_completion_tokens),
            }
        return payload

    def _build_scale_projections(self, dedup_ratio: float) -> list[dict[str, object]]:
        projections: list[dict[str, object]] = []
        enrichment_totals = self.operations.get("enrichment", OperationTotals())
        scoring_totals = self.operations.get("scoring", OperationTotals())
        for target_contacts in (100, 1000, 5000):
            estimated_orgs = max(1, ceil(target_contacts / max(dedup_ratio, 1.0)))
            cold_cost = self._project_operation_cost("enrichment", estimated_orgs, enrichment_totals) + self._project_operation_cost(
                "scoring",
                target_contacts,
                scoring_totals,
            )
            warm_cost = self._project_operation_cost("scoring", target_contacts, scoring_totals)
            projections.append(
                {
                    "target_contacts": target_contacts,
                    "estimated_organizations": estimated_orgs,
                    "cold_start_cost_usd": round(cold_cost, 6),
                    "warm_cache_cost_usd": round(warm_cost, 6),
                    "estimated_savings_usd": round(cold_cost - warm_cost, 6),
                }
            )
        return projections

    def _project_operation_cost(
        self,
        operation: str,
        projected_requests: int,
        totals: OperationTotals,
    ) -> float:
        pricing = self.pricing[operation]
        avg_prompt_tokens = totals.average_prompt_tokens(pricing.default_prompt_tokens)
        avg_completion_tokens = totals.average_completion_tokens(pricing.default_completion_tokens)
        unit_cost = estimate_operation_cost(avg_prompt_tokens, avg_completion_tokens, pricing)
        return projected_requests * unit_cost
