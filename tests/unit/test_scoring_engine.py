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


if __name__ == "__main__":
    unittest.main()
