from __future__ import annotations
#THIS IS THE FILE USED FOR SCORING LOGIC
from src.enrichment.provider import SERVICE_PROVIDER_TYPES
from src.models.entities import Confidence, ContactRecord, EnrichmentRecord, ProspectScore, ScoreDimension


class StarterScoringEngine:
    def score(self, contact: ContactRecord, enrichment: EnrichmentRecord) -> ProspectScore:
        sector_fit = self._score_sector_fit(contact)
        relationship_depth = ScoreDimension(
            value=float(contact.relationship_depth),
            confidence=Confidence.HIGH,
            rationale="Uses the pre-computed Relationship Depth value from the input CSV.",
        )
        halo_value = self._score_halo(contact)
        emerging_fit = self._score_emerging(contact)
        composite = round(
            (sector_fit.value * 0.35)
            + (relationship_depth.value * 0.30)
            + (halo_value.value * 0.20)
            + (emerging_fit.value * 0.15),
            2,
        )
        return ProspectScore(
            sector_fit=sector_fit,
            relationship_depth=relationship_depth,
            halo_value=halo_value,
            emerging_fit=emerging_fit, 
            composite=composite,
            tier=_tier_for_score(composite),
            check_size_estimate=None,
        )

    def _score_sector_fit(self, contact: ContactRecord) -> ScoreDimension: #this is the function used to score
        org_type = contact.org_type.strip().lower()
        if org_type in {"foundation", "endowment", "pension", "insurance", "fund of funds"}:
            return ScoreDimension(8.0, Confidence.MEDIUM, "Institutional allocator archetype is a strong LP fit.")
        if org_type in {"single family office", "multi-family office", "hnwi"}:
            return ScoreDimension(7.0, Confidence.MEDIUM, "Private allocator archetype can fit well, but mandate proof is missing.")
        if org_type in SERVICE_PROVIDER_TYPES: #use these statements from the csv file to determine whether this comapany is a good fit or not
            return ScoreDimension(2.0, Confidence.MEDIUM, "Org type reads more like a manager, advisor, or service provider.")
        return ScoreDimension(4.5, Confidence.LOW, "Starter score is conservative because no live mandate evidence exists yet.")

    def _score_halo(self, contact: ContactRecord) -> ScoreDimension:
        org_type = contact.org_type.strip().lower()
        if org_type in {"foundation", "endowment", "pension"}:
            return ScoreDimension(8.0, Confidence.MEDIUM, "Recognizable institutional allocators tend to provide stronger signaling.")
        if org_type in {"insurance", "fund of funds", "multi-family office"}:
            return ScoreDimension(6.5, Confidence.MEDIUM, "Could provide validation if the organization is well known.")
        if org_type in {"single family office", "hnwi"}:
            return ScoreDimension(4.5, Confidence.LOW, "Private allocators may matter, but halo value is hard to verify publicly.")
        return ScoreDimension(3.0, Confidence.LOW, "Starter scoring assumes limited signaling value until evidence is collected.")

    def _score_emerging(self, contact: ContactRecord) -> ScoreDimension:
        org_type = contact.org_type.strip().lower()
        if org_type in {"single family office", "multi-family office", "foundation", "endowment"}:
            return ScoreDimension(7.5, Confidence.MEDIUM, "This org type can be structurally open to emerging managers.")
        if org_type in {"pension", "insurance"}:
            return ScoreDimension(5.0, Confidence.LOW, "Institutional allocators can back emerging managers, but thresholds are higher.")
        if org_type in SERVICE_PROVIDER_TYPES:
            return ScoreDimension(1.5, Confidence.MEDIUM, "Service-provider and manager profiles are poor LP targets.")
        return ScoreDimension(4.0, Confidence.LOW, "No direct evidence yet on emerging manager appetite.")


def _tier_for_score(composite: float) -> str:
    if composite >= 8.0: #the final ranking to determine what the score is
        return "PRIORITY CLOSE"
    if composite >= 6.5:
        return "STRONG FIT"
    if composite >= 5.0:
        return "MODERATE FIT"
    return "WEAK FIT"
