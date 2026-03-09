from __future__ import annotations

from src.enrichment.provider import ALLOCATOR_ORG_TYPES, SERVICE_PROVIDER_TYPES
from src.models.entities import Confidence, ContactRecord, EnrichmentRecord, ProspectScore


class ValidationEngine:
    def validate(
        self,
        contact: ContactRecord,
        enrichment: EnrichmentRecord,
        score: ProspectScore,
    ) -> list[str]:
        flags: list[str] = []
        org_type = contact.org_type.strip().lower()
        if org_type in SERVICE_PROVIDER_TYPES and score.sector_fit.value >= 5.0:
            flags.append("Service-provider-like org scored too high on sector fit.")
        if org_type in ALLOCATOR_ORG_TYPES and score.sector_fit.value <= 3.5:
            flags.append("Allocator-like org scored unexpectedly low on sector fit.")
        if score.composite >= 7.5 and (
            score.sector_fit.confidence == Confidence.LOW
            or score.halo_value.confidence == Confidence.LOW
            or score.emerging_fit.confidence == Confidence.LOW
        ):
            flags.append("High composite score built on low-confidence dimensions.")
        if score.metadata.get("insufficient_evidence_dimensions") and score.composite >= 6.5:
            flags.append(
                "Strong-fit or better score includes dimensions marked as insufficient-evidence and should be reviewed."
            )
        if org_type in SERVICE_PROVIDER_TYPES and score.tier in {"STRONG FIT", "PRIORITY CLOSE"}:
            flags.append("Non-LP profile reached a top outreach tier and should be reviewed.")
        if score.tier == "PRIORITY CLOSE" and contact.relationship_depth <= 3:
            flags.append("Priority-close tier with weak relationship depth deserves manual review.")
        if score.check_size_estimate is None and enrichment.aum is not None:
            flags.append("AUM was present but check-size estimation failed.")
        return flags
