from __future__ import annotations

import re


ALLOCATION_RANGES = {
    "pension": (0.005, 0.02),
    "insurance": (0.005, 0.02),
    "endowment": (0.01, 0.03),
    "foundation": (0.01, 0.03),
    "fund of funds": (0.02, 0.05),
    "multi-family office": (0.02, 0.05),
    "single family office": (0.03, 0.10),
    "hnwi": (0.03, 0.10),
    "asset manager": (0.005, 0.03),
    "ria/fia": (0.005, 0.03),
    "private capital firm": (0.005, 0.03),
}


def estimate_check_size(aum: str | None, org_type: str) -> str | None:
    if not aum:
        return None
    parsed_aum = _parse_aum_to_dollars(aum)
    allocation_range = ALLOCATION_RANGES.get(org_type.strip().lower())
    if parsed_aum is None or allocation_range is None:
        return None
    low = parsed_aum * allocation_range[0]
    high = parsed_aum * allocation_range[1]
    return f"${_format_dollars(low)}-${_format_dollars(high)}"


def _parse_aum_to_dollars(aum: str) -> float | None:
    normalized = aum.strip().upper().replace(",", "")
    match = re.search(r"(\d+(?:\.\d+)?)\s*([BMK])", normalized)
    if not match:
        return None
    amount = float(match.group(1))
    unit = match.group(2)
    multiplier = {
        "B": 1_000_000_000,
        "M": 1_000_000,
        "K": 1_000,
    }[unit]
    return amount * multiplier


def _format_dollars(value: float) -> str:
    if value >= 1_000_000_000:
        return f"{value / 1_000_000_000:.2f}B"
    if value >= 1_000_000:
        return f"{value / 1_000_000:.2f}M"
    if value >= 1_000:
        return f"{value / 1_000:.2f}K"
    return f"{value:.0f}"
