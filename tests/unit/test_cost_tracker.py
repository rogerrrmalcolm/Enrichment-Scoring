from __future__ import annotations

import unittest

from src.costing.tracker import CostTracker


class CostTrackerTests(unittest.TestCase):
    def test_snapshot_includes_scale_projections(self) -> None:
        tracker = CostTracker()
        tracker.record_operation("enrichment", prompt_tokens=300, completion_tokens=400, tool_calls=1)
        tracker.record_operation("scoring", prompt_tokens=250, completion_tokens=200)
        tracker.record_cache_hit(estimated_saved_cost_usd=0.02)

        snapshot = tracker.snapshot(total_contacts=10, total_organizations=5)

        self.assertIn("operation_breakdown", snapshot)
        self.assertIn("projections", snapshot)
        self.assertEqual(len(snapshot["projections"]), 3)
        self.assertAlmostEqual(snapshot["dedup_ratio_contacts_per_org"], 2.0)
        self.assertGreater(snapshot["projections"][1]["cold_start_cost_usd"], 0)
        self.assertIn("provider_cache_cost_usd", snapshot["projections"][0])
        self.assertIn("app_cache_cost_usd", snapshot["projections"][0])
        self.assertEqual(snapshot["operation_breakdown"]["enrichment"]["tool_calls"], 1)
        self.assertEqual(snapshot["operation_breakdown"]["scoring"]["vendor"], "local")
        self.assertEqual(snapshot["operation_breakdown"]["scoring"]["cost_usd"], 0.0)
        self.assertEqual(snapshot["total_api_requests"], 1)
        self.assertEqual(snapshot["total_local_calls"], 1)


if __name__ == "__main__":
    unittest.main()
