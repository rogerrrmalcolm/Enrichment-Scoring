from __future__ import annotations

from src.enrichment.provider import ALLOCATOR_ORG_TYPES, SERVICE_PROVIDER_TYPES
from src.models.entities import Confidence, ContactRecord, EnrichmentRecord, ProspectScore, ScoreDimension
from src.scoring.check_size import estimate_check_size
from src.utils.prompts import PromptLibrary


class StarterScoringEngine:
    def __init__(self, prompts: PromptLibrary | None = None) -> None:
        self.prompts = prompts

    def score(self, contact: ContactRecord, enrichment: EnrichmentRecord) -> ProspectScore:
        sector_fit = self._score_sector_fit(contact, enrichment)
        relationship_depth = ScoreDimension(
            value=float(contact.relationship_depth),
            confidence=Confidence.HIGH,
            rationale="Uses the pre-computed Relationship Depth value from the input CSV.",
        )
        halo_value = self._score_halo(contact, enrichment)
        emerging_fit = self._score_emerging(contact, enrichment)
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
            check_size_estimate=estimate_check_size(enrichment.aum, contact.org_type),
            metadata={"prompt_artifacts": self._build_prompt_artifacts(contact, enrichment)},
        )

    def _score_sector_fit(
        self,
        contact: ContactRecord,
        enrichment: EnrichmentRecord,
    ) -> ScoreDimension:
        org_type = contact.org_type.strip().lower()
        signals = _signals(enrichment)
        has_allocator_evidence = bool(signals["allocator"] or _has_sources(enrichment.external_allocations))
        has_sustainability_evidence = bool(
            signals["sustainability"] or _has_sources(enrichment.sustainability_mandate)
        )

        if org_type in SERVICE_PROVIDER_TYPES or signals["service_provider"]:
            return ScoreDimension(
                2.0,
                Confidence.MEDIUM,
                "Org type and captured signals read more like a GP, advisor, or service provider than an LP allocator.",
            )
        if org_type in {"foundation", "endowment", "pension", "insurance", "fund of funds"}:
            if has_allocator_evidence and has_sustainability_evidence:
                return ScoreDimension(
                    8.5,
                    Confidence.HIGH,
                    "Allocator profile is strong and enrichment includes mandate-aligned sustainability evidence.",
                )
            return ScoreDimension(
                8.0,
                Confidence.MEDIUM,
                "Institutional allocator archetype is a strong LP fit, but mandate proof is still partial.",
            )
        if org_type in {"single family office", "multi-family office", "hnwi"}:
            if has_sustainability_evidence:
                return ScoreDimension(
                    7.5,
                    Confidence.MEDIUM,
                    "Private allocator profile looks investable and enrichment suggests thematic alignment.",
                )
            return ScoreDimension(
                7.0,
                Confidence.MEDIUM,
                "Private allocator archetype can fit well, but mandate proof is missing.",
            )
        if has_allocator_evidence:
            return ScoreDimension(
                6.0,
                Confidence.MEDIUM,
                "Signals suggest allocator behavior, but the organization type remains ambiguous.",
            )
        return ScoreDimension(
            4.5,
            Confidence.LOW,
            "Starter score is conservative because no live mandate evidence exists yet.",
        )

    def _score_halo(
        self,
        contact: ContactRecord,
        enrichment: EnrichmentRecord,
    ) -> ScoreDimension:
        org_type = contact.org_type.strip().lower()
        brand_sources = _has_sources(enrichment.brand_signal)

        if org_type in {"foundation", "endowment", "pension"}:
            if brand_sources:
                return ScoreDimension(
                    8.5,
                    Confidence.HIGH,
                    "Recognizable institutional allocator with corroborating brand evidence should create market signaling value.",
                )
            return ScoreDimension(
                8.0,
                Confidence.MEDIUM,
                "Recognizable institutional allocators tend to provide stronger signaling.",
            )
        if org_type in {"insurance", "fund of funds", "multi-family office"}:
            return ScoreDimension(
                6.5,
                Confidence.MEDIUM,
                "Could provide validation if the organization is well known.",
            )
        if org_type in {"single family office", "hnwi"}:
            return ScoreDimension(
                4.5,
                Confidence.LOW,
                "Private allocators may matter, but halo value is hard to verify publicly.",
            )
        return ScoreDimension(
            3.0,
            Confidence.LOW,
            "Starter scoring assumes limited signaling value until evidence is collected.",
        )

    def _score_emerging(
        self,
        contact: ContactRecord,
        enrichment: EnrichmentRecord,
    ) -> ScoreDimension:
        org_type = contact.org_type.strip().lower()
        signals = _signals(enrichment)
        has_emerging_evidence = bool(
            signals["emerging"] or _has_sources(enrichment.emerging_manager_program)
        )

        if org_type in {"single family office", "multi-family office", "foundation", "endowment"}:
            if has_emerging_evidence:
                return ScoreDimension(
                    8.0,
                    Confidence.HIGH,
                    "Captured signals suggest the organization could back a Fund I or Fund II manager.",
                )
            return ScoreDimension(
                7.5,
                Confidence.MEDIUM,
                "This org type can be structurally open to emerging managers.",
            )
        if org_type in {"pension", "insurance"}:
            return ScoreDimension(
                5.0,
                Confidence.LOW,
                "Institutional allocators can back emerging managers, but thresholds are higher.",
            )
        if org_type in SERVICE_PROVIDER_TYPES or signals["service_provider"]:
            return ScoreDimension(
                1.5,
                Confidence.MEDIUM,
                "Service-provider and manager profiles are poor LP targets.",
            )
        return ScoreDimension(
            4.0,
            Confidence.LOW,
            "No direct evidence yet on emerging manager appetite.",
        )

    def _build_prompt_artifacts(
        self,
        contact: ContactRecord,
        enrichment: EnrichmentRecord,
    ) -> dict[str, str]:
        if self.prompts is None:
            return {}

        prompt_context = {
            "organization": contact.organization,
            "org_type": contact.org_type,
            "relationship_depth": contact.relationship_depth,
            "allocator_profile": enrichment.allocator_profile,
            "external_allocations": enrichment.external_allocations.summary,
            "sustainability_mandate": enrichment.sustainability_mandate.summary,
            "brand_signal": enrichment.brand_signal.summary,
            "emerging_manager_program": enrichment.emerging_manager_program.summary,
            "aum": enrichment.aum or "Unknown",
        }
        return {
            "system_prompt": self.prompts.load("scoring/system.txt"),
            "scorecard_prompt": self.prompts.render("scoring/prospect_scorecard.txt", **prompt_context),
        }


def _tier_for_score(composite: float) -> str:
    if composite >= 8.0:
        return "PRIORITY CLOSE"
    if composite >= 6.5:
        return "STRONG FIT"
    if composite >= 5.0:
        return "MODERATE FIT"
    return "WEAK FIT"


def _signals(enrichment: EnrichmentRecord) -> dict[str, list[str]]:
    raw_signals = enrichment.raw_payload.get("signals", {})
    return {
        "allocator": list(raw_signals.get("allocator", [])),
        "service_provider": list(raw_signals.get("service_provider", [])),
        "sustainability": list(raw_signals.get("sustainability", [])),
        "brand": list(raw_signals.get("brand", [])),
        "emerging": list(raw_signals.get("emerging", [])),
    }


def _has_sources(evidence: object) -> bool:
    return bool(getattr(evidence, "sources", []))

