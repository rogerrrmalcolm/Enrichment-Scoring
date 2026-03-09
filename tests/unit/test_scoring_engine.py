from __future__ import annotations

import unittest

from src.models.entities import ContactRecord, EnrichmentRecord
from src.scoring.engine import StarterScoringEngine


class StarterScoringEngineTests(unittest.TestCase):
    def test_allocator_type_scores_into_strong_fit_band(self) -> None:
        engine = StarterScoringEngine()
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


if __name__ == "__main__":
    unittest.main()
