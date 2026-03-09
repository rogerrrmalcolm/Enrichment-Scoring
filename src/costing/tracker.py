from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class CostTracker:
    total_cost_usd: float = 0.0
    total_requests: int = 0
    total_prompt_tokens: int = 0
    total_completion_tokens: int = 0
    cache_hits: int = 0
    cache_misses: int = 0
    avoided_cost_usd: float = 0.0
    vendor_breakdown: dict[str, dict[str, float]] = field(default_factory=dict)

    def record(
        self,
        vendor: str,
        model: str,
        prompt_tokens: int,
        completion_tokens: int,
        cost_usd: float,
    ) -> None:
        self.total_requests += 1
        self.total_prompt_tokens += prompt_tokens
        self.total_completion_tokens += completion_tokens
        self.total_cost_usd = round(self.total_cost_usd + cost_usd, 6)
        key = f"{vendor}:{model}"
        if key not in self.vendor_breakdown:
            self.vendor_breakdown[key] = {
                "requests": 0,
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "cost_usd": 0.0,
            }
        bucket = self.vendor_breakdown[key]
        bucket["requests"] += 1
        bucket["prompt_tokens"] += prompt_tokens
        bucket["completion_tokens"] += completion_tokens
        bucket["cost_usd"] = round(bucket["cost_usd"] + cost_usd, 6)

    def record_cache_hit(self, estimated_saved_cost_usd: float) -> None:
        self.cache_hits += 1
        self.avoided_cost_usd = round(self.avoided_cost_usd + estimated_saved_cost_usd, 6)

    def record_cache_miss(self) -> None:
        self.cache_misses += 1

    def snapshot(self) -> dict[str, object]:
        return {
            "total_cost_usd": round(self.total_cost_usd, 6),
            "total_requests": self.total_requests,
            "total_prompt_tokens": self.total_prompt_tokens,
            "total_completion_tokens": self.total_completion_tokens,
            "cache_hits": self.cache_hits,
            "cache_misses": self.cache_misses,
            "avoided_cost_usd": round(self.avoided_cost_usd, 6),
            "vendor_breakdown": self.vendor_breakdown,
        }
