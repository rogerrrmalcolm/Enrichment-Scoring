from __future__ import annotations

import unittest
from pathlib import Path

from src.models.entities import ContactRecord, EnrichmentRecord
from src.scoring.engine import StarterScoringEngine
from src.utils.prompts import PromptLibrary


class StarterScoringEngineTests(unittest.TestCase):
    def test_allocator_type_scores_into_strong_fit_band(self) -> None:
        engine = StarterScoringEngine(PromptLibrary(Path.cwd() / "prompts"))
        contact = ContactRecord(
            contact_name="A Contact",
            organization="Impact Foundation",
            org_type="Foundation",
            role="Director of Investments",
            email=None,
            region="NYC",
            contact_status="New Contact",
            relationship_depth=7,
        )
        enrichment = EnrichmentRecord(
            organization="Impact Foundation",
            canonical_org_name="impact foundation",
            organization_type="Foundation",
            allocator_profile="Likely LP allocator profile based on organization type.",
        )

        result = engine.score(contact, enrichment)

        self.assertGreaterEqual(result.composite, 6.5)
        self.assertEqual(result.tier, "STRONG FIT")

    def test_service_provider_stays_out_of_top_tiers(self) -> None:
        engine = StarterScoringEngine(PromptLibrary(Path.cwd() / "prompts"))
        contact = ContactRecord(
            contact_name="Broker Contact",
            organization="Meridian Capital Group",
            org_type="RIA/FIA",
            role="Managing Director",
            email=None,
            region="NYC",
            contact_status="New Contact",
            relationship_depth=4,
        )
        enrichment = EnrichmentRecord(
            organization="Meridian Capital Group",
            canonical_org_name="meridian capital group",
            organization_type="Ria/Fia",
            allocator_profile="Likely GP, advisor, or service-provider profile pending deeper web validation.",
            raw_payload={"signals": {"service_provider": ["org_type:ria/fia"], "allocator": [], "sustainability": [], "brand": [], "emerging": []}},
        )

        result = engine.score(contact, enrichment)

        self.assertLess(result.sector_fit.value, 4.0)
        self.assertIn(result.tier, {"WEAK FIT", "MODERATE FIT"})

    def test_calibration_anchor_matches_pbucc_benchmark(self) -> None:
        engine = StarterScoringEngine(PromptLibrary(Path.cwd() / "prompts"))
        contact = ContactRecord(
            contact_name="Anchor Contact",
            organization="Pension Boards United Church of Christ",
            org_type="Pension",
            role="Director, Responsible Investing",
            email=None,
            region="NYC",
            contact_status="Existing Contact",
            relationship_depth=9,
        )
        enrichment = EnrichmentRecord(
            organization="Pension Boards United Church of Christ",
            canonical_org_name="pension boards united church of christ",
            organization_type="Pension",
            allocator_profile="Likely LP allocator profile based on organization type.",
        )

        result = engine.score(contact, enrichment)

        self.assertEqual(result.sector_fit.value, 8.0)
        self.assertEqual(result.halo_value.value, 6.0)
        self.assertEqual(result.emerging_fit.value, 8.0)

    def test_generic_foundation_does_not_jump_to_priority_close_without_explicit_lp_evidence(self) -> None:
        engine = StarterScoringEngine(PromptLibrary(Path.cwd() / "prompts"))
        contact = ContactRecord(
            contact_name="Careful Score",
            organization="Climate Foundation",
            org_type="Foundation",
            role="Director of Investments",
            email=None,
            region="NYC",
            contact_status="New Contact",
            relationship_depth=8,
        )
        enrichment = EnrichmentRecord(
            organization="Climate Foundation",
            canonical_org_name="climate foundation",
            organization_type="Foundation",
            allocator_profile="Likely LP allocator profile based on organization type.",
        )

        result = engine.score(contact, enrichment)

        self.assertLess(result.composite, 8.0)
        self.assertLess(result.sector_fit.value, 8.0)
        self.assertTrue(result.sector_fit.insufficient_evidence)
        self.assertIn("sector_fit", result.metadata["insufficient_evidence_dimensions"])

    def test_sparse_profile_is_explicitly_marked_as_insufficient_evidence(self) -> None:
        engine = StarterScoringEngine(PromptLibrary(Path.cwd() / "prompts"))
        contact = ContactRecord(
            contact_name="Sparse Contact",
            organization="Quiet Family Office",
            org_type="Single Family Office",
            role="Principal",
            email=None,
            region="NYC",
            contact_status="New Contact",
            relationship_depth=3,
        )
        enrichment = EnrichmentRecord(
            organization="Quiet Family Office",
            canonical_org_name="quiet family office",
            organization_type="Single Family Office",
            allocator_profile="Likely LP allocator profile based on organization type.",
        )

        result = engine.score(contact, enrichment)

        self.assertTrue(result.sector_fit.insufficient_evidence)
        self.assertTrue(result.halo_value.insufficient_evidence)
        self.assertTrue(result.emerging_fit.insufficient_evidence)
        self.assertIn("Insufficient public evidence", result.sector_fit.rationale)
        self.assertGreaterEqual(len(result.metadata["insufficient_evidence_dimensions"]), 1)

    def test_enrichment_org_type_overrides_crm_org_type_for_scoring_and_check_size(self) -> None:
        engine = StarterScoringEngine(PromptLibrary(Path.cwd() / "prompts"))
        contact = ContactRecord(
            contact_name="Corrected Contact",
            organization="Corrected Foundation",
            org_type="Asset Manager",
            role="Director of Investments",
            email=None,
            region="NYC",
            contact_status="New Contact",
            relationship_depth=7,
        )
        enrichment = EnrichmentRecord(
            organization="Corrected Foundation",
            canonical_org_name="corrected foundation",
            organization_type="Foundation",
            allocator_profile="Institutional LP allocator with evidence of external-manager selection.",
            aum="$1.0B",
        )

        result = engine.score(contact, enrichment)

        self.assertGreater(result.sector_fit.value, 4.0)
        self.assertEqual(result.check_size_estimate, "$10.00M-$30.00M")


if __name__ == "__main__":
    unittest.main()
