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


if __name__ == "__main__":
    unittest.main()
