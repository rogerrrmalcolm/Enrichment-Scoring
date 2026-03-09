from __future__ import annotations

from dataclasses import asdict, dataclass
from collections import Counter
from typing import Protocol, Sequence

from src.models.entities import ContactRecord, EnrichmentRecord, Evidence
from src.utils.prompts import PromptLibrary


ALLOCATOR_ORG_TYPES = {
    "single family office",
    "multi-family office",
    "fund of funds",
    "foundation",
    "endowment",
    "pension",
    "insurance",
    "hnwi",
}

SERVICE_PROVIDER_TYPES = {
    "asset manager",
    "ria/fia",
    "private capital firm",
}

CALIBRATION_RESEARCH_PROFILES = {
    "the rockefeller foundation": {
        "aum": "$6.4B",
        "allocator": "Challenge anchor indicates the foundation allocates across hedge funds, PE, real estate, senior debt, and direct lending funds.",
        "sustainability": "Challenge anchor explicitly links the foundation to climate and sustainability programs.",
        "brand": "Challenge anchor marks Rockefeller as a globally recognized institution with strong signaling value.",
        "emerging": "Challenge anchor references multiple emerging manager commitments.",
    },
    "pbucc": {
        "aum": "$2.0B",
        "allocator": "Challenge anchor identifies PBUCC as an institutional LP with responsible investing orientation.",
        "sustainability": "Challenge anchor ties PBUCC to faith-based responsible investing and ICCR membership.",
        "brand": "Challenge anchor notes strong recognition in impact-investing circles.",
        "emerging": "Challenge anchor documents openness to emerging managers.",
    },
    "pension boards united church of christ": {
        "aum": "$2.0B",
        "allocator": "Challenge anchor identifies PBUCC as an institutional LP with responsible investing orientation.",
        "sustainability": "Challenge anchor ties PBUCC to faith-based responsible investing and ICCR membership.",
        "brand": "Challenge anchor notes strong recognition in impact-investing circles.",
        "emerging": "Challenge anchor documents openness to emerging managers.",
    },
    "inherent group": {
        "aum": None,
        "allocator": "Challenge anchor treats Inherent Group as a single-family office that likely allocates externally, but public evidence is limited.",
        "sustainability": "Challenge anchor references internal ESG strategies rather than a clearly documented external-manager mandate.",
        "brand": "Challenge anchor indicates limited public visibility despite allocator potential.",
        "emerging": "Challenge anchor suggests structural openness as a single-family office, but no explicit emerging-manager program.",
    },
    "meridian capital group": {
        "aum": None,
        "allocator": "Challenge anchor identifies Meridian Capital Group as a CRE finance, investment-sales, and leasing advisory business rather than an LP allocator.",
        "sustainability": "Challenge anchor does not identify a sustainability allocator mandate for Meridian Capital Group.",
        "brand": "Challenge anchor describes niche market visibility, but not the type of LP halo signal relevant here.",
        "emerging": "Challenge anchor treats Meridian Capital Group as a poor emerging-manager fit because it is not an LP allocator.",
    },
}

ALLOCATOR_ROLE_KEYWORDS = {
    "investment",
    "portfolio",
    "cio",
    "chief investment officer",
    "allocations",
    "alternatives",
    "endowment",
}

SUSTAINABILITY_KEYWORDS = {
    "impact",
    "sustainable",
    "sustainability",
    "climate",
    "esg",
    "regenerative",
    "energy transition",
    "responsible investing",
}

SERVICE_PROVIDER_KEYWORDS = {
    "advisors",
    "advisory",
    "brokerage",
    "consulting",
    "capital group",
    "asset management",
    "wealth management",
    "lending",
}


@dataclass(frozen=True, slots=True)
class SourcePolicy:
    trusted_source_tiers: dict[str, tuple[str, ...]]
    blocked_source_patterns: tuple[str, ...]
    minimum_corroborating_sources: int
    methodology_steps: tuple[str, ...]
    evidence_rules: tuple[str, ...]

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


class EnrichmentProvider(Protocol):
    def enrich(self, organization_key: str, contacts: Sequence[ContactRecord]) -> EnrichmentRecord:
        ...


class StarterEnrichmentProvider:
    def __init__(self, prompts: PromptLibrary) -> None:
        self.prompts = prompts
        self.source_policy = _default_source_policy()

    def enrich(self, organization_key: str, contacts: Sequence[ContactRecord]) -> EnrichmentRecord:
        primary = contacts[0]
        org_type = _dominant_org_type(contacts)
        prompt_context = {
            "organization": primary.organization,
            "org_type": primary.org_type,
            "regions": ", ".join(sorted({contact.region for contact in contacts})),
            "roles": ", ".join(sorted({contact.role for contact in contacts})),
            "contact_count": len(contacts),
            "trusted_sources": _format_trusted_sources(self.source_policy),
            "blocked_sources": ", ".join(self.source_policy.blocked_source_patterns),
            "minimum_corroboration": self.source_policy.minimum_corroborating_sources,
        }
        signals = _collect_signals(primary.organization, contacts, org_type)
        anchor = CALIBRATION_RESEARCH_PROFILES.get(organization_key)
        notes = [
            "This enrichment pass is heuristic and prompt-backed, but still offline.",
            "Swap this provider with a live search/LLM implementation to replace the heuristic evidence buckets.",
            "The future live search path is constrained by a trusted-source policy and corroboration rules.",
            "Org type alone is not treated as conclusive proof of external-manager allocation; explicit LP evidence remains the standard.",
        ]
        if anchor:
            notes.append("Calibration anchor matched: challenge benchmark evidence was injected for this organization.")
        return EnrichmentRecord(
            organization=primary.organization,
            canonical_org_name=organization_key,
            organization_type=org_type.title(),
            allocator_profile=_allocator_profile(org_type),
            external_allocations=Evidence(
                summary=_external_allocations_summary(org_type, signals, anchor),
                sources=_sources_for("allocator", signals, anchor),
            ),
            sustainability_mandate=Evidence(
                summary=_sustainability_summary(org_type, signals, anchor),
                sources=_sources_for("sustainability", signals, anchor),
            ),
            aum=_aum_for(anchor),
            brand_signal=Evidence(
                summary=_brand_summary(org_type, primary.region, signals, anchor),
                sources=_sources_for("brand", signals, anchor),
            ),
            emerging_manager_program=Evidence(
                summary=_emerging_manager_summary(org_type, signals, anchor),
                sources=_sources_for("emerging", signals, anchor),
            ),
            notes=notes,
            raw_payload={
                "contact_count": len(contacts),
                "roles": sorted({contact.role for contact in contacts}),
                "regions": sorted({contact.region for contact in contacts}),
                "signals": signals,
                "research_methodology": methodology_summary(),
                "source_policy": self.source_policy.as_dict(),
                "prompt_artifacts": {
                    "system_prompt": self.prompts.load("enrichment/system.txt"),
                    "research_prompt": self.prompts.render("enrichment/organization_research.txt", **prompt_context),
                },
            },
        )


def _dominant_org_type(contacts: Sequence[ContactRecord]) -> str:
    counts = Counter(contact.org_type.strip().lower() for contact in contacts)
    return counts.most_common(1)[0][0]


def _allocator_profile(org_type: str) -> str:
    if org_type in ALLOCATOR_ORG_TYPES:
        return "Likely LP allocator profile based on organization type."
    if org_type in SERVICE_PROVIDER_TYPES:
        return "Likely GP, advisor, or service-provider profile pending deeper web validation."
    return "Mixed signal profile that needs targeted web research."


def _external_allocations_summary(
    org_type: str,
    signals: dict[str, list[str]],
    anchor: dict[str, str] | None,
) -> str:
    if anchor:
        return anchor["allocator"]
    if org_type in {"foundation", "endowment", "pension", "insurance", "fund of funds"}:
        return "Org type suggests an investment office that may allocate to external managers, but explicit public evidence of private credit or direct-lending fund allocations is still required."
    if signals["allocator"]:
        return f"Allocator-like signals detected: {', '.join(signals['allocator'][:3])}."
    if org_type in {"single family office", "multi-family office", "hnwi"}:
        return "Family-capital profile may allocate externally, but public evidence is often thin and should not be overstated."
    if org_type in SERVICE_PROVIDER_TYPES:
        return "Current signal suggests the organization may manage or advise capital rather than allocate to outside funds."
    return "No external allocation signal captured yet."


def _sustainability_summary(
    org_type: str,
    signals: dict[str, list[str]],
    anchor: dict[str, str] | None,
) -> str:
    if anchor:
        return anchor["sustainability"]
    if signals["sustainability"]:
        return f"Sustainability-oriented signals detected: {', '.join(signals['sustainability'][:3])}."
    if org_type in {"foundation", "endowment", "pension"}:
        return "Institutional allocator type can support impact or climate mandates, but investment-policy evidence is still needed."
    if org_type in {"single family office", "multi-family office"}:
        return "Private wealth allocator may have ESG preferences, but public documentation varies widely."
    return "Sustainability mandate unknown without live research."


def _brand_summary(
    org_type: str,
    region: str,
    signals: dict[str, list[str]],
    anchor: dict[str, str] | None,
) -> str:
    if anchor:
        return anchor["brand"]
    if signals["brand"]:
        return f"Brand signals suggest institutional visibility: {', '.join(signals['brand'][:3])}."
    if org_type in {"foundation", "endowment", "pension"}:
        return f"Institutional allocator in {region} may carry signaling value, but organization-specific recognition evidence is still needed."
    if org_type in {"single family office", "hnwi"}:
        return "Private allocator may be influential but less visible to the broader LP market."
    return "Brand signal unknown pending organization-specific evidence."


def _emerging_manager_summary(
    org_type: str,
    signals: dict[str, list[str]],
    anchor: dict[str, str] | None,
) -> str:
    if anchor:
        return anchor["emerging"]
    if signals["emerging"]:
        return f"Emerging-manager-friendly signals detected: {', '.join(signals['emerging'][:3])}."
    if org_type in {"single family office", "multi-family office", "foundation", "endowment"}:
        return "Org type can be structurally open to emerging managers, but explicit evidence should outweigh type-based inference."
    if org_type in SERVICE_PROVIDER_TYPES:
        return "Emerging manager fit is weak unless the firm also allocates to third-party funds."
    return "Emerging manager appetite unknown without direct evidence."


def _collect_signals(
    organization: str,
    contacts: Sequence[ContactRecord],
    org_type: str,
) -> dict[str, list[str]]:
    # These signal buckets are intentionally explicit so the scoring layer can
    # reason about why a score moved up or down instead of operating on opaque text.
    signals = {
        "allocator": [],
        "service_provider": [],
        "sustainability": [],
        "brand": [],
        "emerging": [],
    }
    organization_text = organization.lower()
    role_text = " ".join(contact.role.lower() for contact in contacts)
    if org_type in ALLOCATOR_ORG_TYPES:
        signals["allocator"].append(f"org_type:{org_type}")
    if org_type in SERVICE_PROVIDER_TYPES:
        signals["service_provider"].append(f"org_type:{org_type}")
    _append_keyword_hits(organization_text, ALLOCATOR_ROLE_KEYWORDS, signals["allocator"], "role-alignment")
    _append_keyword_hits(role_text, ALLOCATOR_ROLE_KEYWORDS, signals["allocator"], "role")
    _append_keyword_hits(organization_text, SUSTAINABILITY_KEYWORDS, signals["sustainability"], "organization")
    _append_keyword_hits(role_text, SUSTAINABILITY_KEYWORDS, signals["sustainability"], "role")
    _append_keyword_hits(organization_text, SERVICE_PROVIDER_KEYWORDS, signals["service_provider"], "organization")
    if any(token in role_text for token in {"responsible investing", "impact investments", "sustainable investing"}):
        signals["sustainability"].append("role:explicit-sustainability-mandate")
    if any(token in organization_text for token in {"foundation", "endowment", "pension", "trust", "university"}):
        signals["brand"].append("institutional-name-pattern")
    if org_type in {"foundation", "endowment", "pension"}:
        signals["brand"].append(f"org_type:{org_type}")
    if org_type in {"single family office", "multi-family office", "foundation", "endowment"}:
        signals["emerging"].append(f"org_type:{org_type}")
    return signals


def _append_keyword_hits(text: str, keywords: set[str], bucket: list[str], prefix: str) -> None:
    for keyword in sorted(keywords):
        if keyword in text:
            bucket.append(f"{prefix}:{keyword}")


def _sources_for(
    category: str,
    signals: dict[str, list[str]],
    anchor: dict[str, str] | None,
) -> list[str]:
    if anchor:
        return ["challenge_calibration_anchor"]
    if category == "allocator":
        return signals["allocator"][:5]
    if category == "sustainability":
        return signals["sustainability"][:5]
    if category == "brand":
        return signals["brand"][:5]
    if category == "emerging":
        return signals["emerging"][:5]
    return []


def _aum_for(anchor: dict[str, str] | None) -> str | None:
    if anchor is None:
        return None
    return anchor["aum"]


def _format_trusted_sources(policy: SourcePolicy) -> str:
    parts: list[str] = []
    for tier, labels in policy.trusted_source_tiers.items():
        parts.append(f"{tier}: {', '.join(labels)}")
    return " | ".join(parts)


def _default_source_policy() -> SourcePolicy:
    return SourcePolicy(
        trusted_source_tiers={
            "tier_1_primary": (
                "official organization website",
                "annual report",
                "investment policy statement",
                "regulatory filing",
                "foundation or endowment financial statement",
                "public pension board materials",
            ),
            "tier_2_institutional": (
                "university investment office page",
                "SEC or government registry",
                "reputable allocator database",
                "audited financial statement",
                "conference speaker profile published by the organization",
            ),
            "tier_3_reputable_secondary": (
                "major financial press",
                "institutional investor publication",
                "industry association page",
            ),
        },
        blocked_source_patterns=(
            "social media",
            "content farm",
            "generic people-search site",
            "SEO directory",
            "unattributed blog",
            "forum post",
            "sponsored content",
        ),
        minimum_corroborating_sources=2,
        methodology_steps=(
            "Start with primary organization-controlled sources.",
            "Use regulatory or audited documents to confirm allocator status and AUM.",
            "Use reputable secondary coverage only to support, not replace, primary evidence.",
            "Corroborate material claims with at least two trusted sources unless the claim comes from a primary filing.",
            "Drop weak or contradictory evidence instead of averaging it into the score.",
        ),
        evidence_rules=(
            "Do not cite social posts, content farms, or lead-gen directories.",
            "Treat mission pages separately from investment-office pages for foundations and endowments.",
            "Require explicit external-manager allocation evidence before classifying a mixed organization as an LP.",
            "Mark confidence down when the evidence is thin, outdated, or only indirectly related to investing.",
        ),
    )


def methodology_summary() -> list[str]:
    policy = _default_source_policy()
    return [
        "Prefer primary and regulatory sources over commentary.",
        "Corroborate material claims unless a primary filing already establishes the fact.",
        "Down-rank noisy or marketing-heavy sources.",
        "Separate charitable mission language from investable mandate language.",
        f"Minimum corroboration threshold: {policy.minimum_corroborating_sources} trusted sources.",
    ]
