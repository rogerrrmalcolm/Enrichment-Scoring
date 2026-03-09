from __future__ import annotations

from collections import Counter
from typing import Protocol, Sequence

from src.models.entities import ContactRecord, EnrichmentRecord, Evidence


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


class EnrichmentProvider(Protocol):
    def enrich(self, organization_key: str, contacts: Sequence[ContactRecord]) -> EnrichmentRecord:
        ...


class StarterEnrichmentProvider:
    def enrich(self, organization_key: str, contacts: Sequence[ContactRecord]) -> EnrichmentRecord:
        primary = contacts[0]
        org_type = _dominant_org_type(contacts)
        notes = [
            "Starter enrichment uses CSV metadata only.",
            "Replace this provider with an LLM/search-backed implementation for live web research.",
        ]
        return EnrichmentRecord(
            organization=primary.organization,
            canonical_org_name=organization_key,
            organization_type=org_type.title(),
            allocator_profile=_allocator_profile(org_type),
            external_allocations=Evidence(summary=_external_allocations_summary(org_type)),
            sustainability_mandate=Evidence(summary=_sustainability_summary(org_type)),
            brand_signal=Evidence(summary=_brand_summary(org_type, primary.region)),
            emerging_manager_program=Evidence(summary=_emerging_manager_summary(org_type)),
            notes=notes,
            raw_payload={
                "contact_count": len(contacts),
                "roles": sorted({contact.role for contact in contacts}),
                "regions": sorted({contact.region for contact in contacts}),
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


def _external_allocations_summary(org_type: str) -> str:
    if org_type in {"foundation", "endowment", "pension", "insurance", "fund of funds"}:
        return "Org type commonly allocates to external managers; confirm specific private credit exposure."
    if org_type in {"single family office", "multi-family office", "hnwi"}:
        return "Family-capital profile may allocate externally, but public evidence is often thin."
    if org_type in SERVICE_PROVIDER_TYPES:
        return "Current signal suggests the organization may manage or advise capital rather than allocate to outside funds."
    return "No external allocation signal captured yet."


def _sustainability_summary(org_type: str) -> str:
    if org_type in {"foundation", "endowment", "pension"}:
        return "Institutional allocator type can support impact or climate mandates; verify fund-policy language."
    if org_type in {"single family office", "multi-family office"}:
        return "Private wealth allocator may have ESG preferences, but public documentation varies widely."
    return "Sustainability mandate unknown without live research."


def _brand_summary(org_type: str, region: str) -> str:
    if org_type in {"foundation", "endowment", "pension"}:
        return f"Institutional allocator in {region} may carry strong signaling value if publicly recognizable."
    if org_type in {"single family office", "hnwi"}:
        return "Private allocator may be influential but less visible to the broader LP market."
    return "Brand signal unknown pending organization-specific evidence."


def _emerging_manager_summary(org_type: str) -> str:
    if org_type in {"single family office", "multi-family office", "foundation", "endowment"}:
        return "Org type can be structurally open to emerging managers if mandate flexibility exists."
    if org_type in SERVICE_PROVIDER_TYPES:
        return "Emerging manager fit is weak unless the firm also allocates to third-party funds."
    return "Emerging manager appetite unknown without direct evidence."
