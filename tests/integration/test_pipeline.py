from __future__ import annotations

from contextlib import closing
import csv
import sqlite3
import unittest 
import uuid
from pathlib import Path

from config.settings import AppSettings
from src.orchestration.pipeline import ProspectPipeline


class ProspectPipelineIntegrationTests(unittest.TestCase):
    def test_pipeline_persists_results(self) -> None:
        sandbox_dir = Path.cwd() / "tests" / "tmp"
        sandbox_dir.mkdir(parents=True, exist_ok=True)
        root = sandbox_dir / f"fixture_{uuid.uuid4().hex}"
        (root / "prompts" / "enrichment").mkdir(parents=True)
        (root / "prompts" / "scoring").mkdir(parents=True)
        (root / "data" / "incoming").mkdir(parents=True)
        (root / "data" / "cache").mkdir(parents=True)
        (root / "data" / "processed").mkdir(parents=True)
        (root / "data" / "exports").mkdir(parents=True)
        (root / "storage" / "db").mkdir(parents=True)
        (root / "storage" / "logs").mkdir(parents=True)
        (root / "storage" / "state").mkdir(parents=True)
        csv_path = root / "data" / "incoming" / "challenge_contacts.csv"

        with csv_path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(
                [
                    "Contact Name",
                    "Organization",
                    "Org Type",
                    "Role",
                    "Email",
                    "Region",
                    "Contact Status",
                    "Relationship Depth",
                ]
            )
            writer.writerow(
                [
                    "Jane Doe",
                    "Example Foundation",
                    "Foundation",
                    "Director of Investments",
                    "",
                    "NYC",
                    "New Contact",
                    "7",
                ]
            )
        (root / "prompts" / "enrichment" / "system.txt").write_text("Research prompt system.", encoding="utf-8")
        (root / "prompts" / "enrichment" / "organization_research.txt").write_text(
            "Org {{organization}} type {{org_type}} regions {{regions}} roles {{roles}} count {{contact_count}} trusted {{trusted_sources}} blocked {{blocked_sources}} corroboration {{minimum_corroboration}}",
            encoding="utf-8",
        )
        (root / "prompts" / "scoring" / "system.txt").write_text("Scoring prompt system.", encoding="utf-8")
        (root / "prompts" / "scoring" / "prospect_scorecard.txt").write_text(
            "Score {{organization}} {{org_type}} {{relationship_depth}} {{allocator_profile}} {{external_allocations}} {{sustainability_mandate}} {{brand_signal}} {{emerging_manager_program}} {{aum}}",
            encoding="utf-8",
        )
        (root / "prompts" / "scoring" / "validation_review.txt").write_text(
            "Validate {{organization}} {{org_type}} {{sector_fit}} {{halo_value}} {{emerging_fit}} {{composite}} {{flags}}",
            encoding="utf-8",
        )

        settings = AppSettings.from_root(root)
        pipeline = ProspectPipeline(settings)
        run_id = pipeline.run()

        with closing(sqlite3.connect(settings.database_path)) as connection:
            prospect_count = connection.execute(
                "SELECT COUNT(*) FROM prospects WHERE run_id = ?",
                (run_id,),
            ).fetchone()[0]

        self.assertEqual(prospect_count, 1)
        self.assertTrue(settings.processed_output_path(run_id).exists())
        self.assertTrue(settings.leaderboard_path(run_id).exists())
        self.assertTrue(settings.run_summary_path(run_id).exists())
        self.assertTrue(settings.cost_breakdown_path(run_id).exists())
        self.assertTrue(settings.cost_projections_path(run_id).exists())
        self.assertTrue(settings.report_path(run_id).exists())
        self.assertTrue(settings.cache_path.exists())

    def test_two_immediate_runs_get_distinct_run_ids(self) -> None:
        sandbox_dir = Path.cwd() / "tests" / "tmp"
        sandbox_dir.mkdir(parents=True, exist_ok=True)
        root = sandbox_dir / f"fixture_{uuid.uuid4().hex}"
        (root / "prompts" / "enrichment").mkdir(parents=True)
        (root / "prompts" / "scoring").mkdir(parents=True)
        (root / "data" / "incoming").mkdir(parents=True)
        (root / "data" / "cache").mkdir(parents=True)
        (root / "data" / "processed").mkdir(parents=True)
        (root / "data" / "exports").mkdir(parents=True)
        (root / "storage" / "db").mkdir(parents=True)
        (root / "storage" / "logs").mkdir(parents=True)
        (root / "storage" / "state").mkdir(parents=True)
        csv_path = root / "data" / "incoming" / "challenge_contacts.csv"

        with csv_path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(
                [
                    "Contact Name",
                    "Organization",
                    "Org Type",
                    "Role",
                    "Email",
                    "Region",
                    "Contact Status",
                    "Relationship Depth",
                ]
            )
            writer.writerow(
                [
                    "Jane Doe",
                    "Example Foundation",
                    "Foundation",
                    "Director of Investments",
                    "",
                    "NYC",
                    "New Contact",
                    "7",
                ]
            )
        (root / "prompts" / "enrichment" / "system.txt").write_text("Research prompt system.", encoding="utf-8")
        (root / "prompts" / "enrichment" / "organization_research.txt").write_text(
            "Org {{organization}} type {{org_type}} regions {{regions}} roles {{roles}} count {{contact_count}} trusted {{trusted_sources}} blocked {{blocked_sources}} corroboration {{minimum_corroboration}}",
            encoding="utf-8",
        )
        (root / "prompts" / "scoring" / "system.txt").write_text("Scoring prompt system.", encoding="utf-8")
        (root / "prompts" / "scoring" / "prospect_scorecard.txt").write_text(
            "Score {{organization}} {{org_type}} {{relationship_depth}} {{allocator_profile}} {{external_allocations}} {{sustainability_mandate}} {{brand_signal}} {{emerging_manager_program}} {{aum}}",
            encoding="utf-8",
        )
        (root / "prompts" / "scoring" / "validation_review.txt").write_text(
            "Validate {{organization}} {{org_type}} {{sector_fit}} {{halo_value}} {{emerging_fit}} {{composite}} {{flags}}",
            encoding="utf-8",
        )

        settings = AppSettings.from_root(root)
        pipeline = ProspectPipeline(settings)

        first_run_id = pipeline.run()
        second_run_id = pipeline.run()

        self.assertNotEqual(first_run_id, second_run_id)
        self.assertTrue(settings.run_manifest_path(first_run_id).exists())
        self.assertTrue(settings.run_manifest_path(second_run_id).exists())

    def test_pipeline_skips_malformed_rows_and_exports_tableau_safe_placeholders(self) -> None:
        sandbox_dir = Path.cwd() / "tests" / "tmp"
        sandbox_dir.mkdir(parents=True, exist_ok=True)
        root = sandbox_dir / f"fixture_{uuid.uuid4().hex}"
        (root / "prompts" / "enrichment").mkdir(parents=True)
        (root / "prompts" / "scoring").mkdir(parents=True)
        (root / "data" / "incoming").mkdir(parents=True)
        (root / "data" / "cache").mkdir(parents=True)
        (root / "data" / "processed").mkdir(parents=True)
        (root / "data" / "exports").mkdir(parents=True)
        (root / "storage" / "db").mkdir(parents=True)
        (root / "storage" / "logs").mkdir(parents=True)
        (root / "storage" / "state").mkdir(parents=True)
        csv_path = root / "data" / "incoming" / "challenge_contacts.csv"

        with csv_path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(
                [
                    "Contact Name",
                    "Organization",
                    "Org Type",
                    "Role",
                    "Email",
                    "Region",
                    "Contact Status",
                    "Relationship Depth",
                ]
            )
            writer.writerow(
                [
                    "Jane Doe",
                    "Example Foundation",
                    "Foundation",
                    "Director of Investments",
                    "",
                    "NYC",
                    "New Contact",
                    "7",
                ]
            )
            writer.writerow(["", "", "", "", "", "", "", "5"])
        (root / "prompts" / "enrichment" / "system.txt").write_text("Research prompt system.", encoding="utf-8")
        (root / "prompts" / "enrichment" / "organization_research.txt").write_text(
            "Org {{organization}} type {{org_type}} regions {{regions}} roles {{roles}} count {{contact_count}} trusted {{trusted_sources}} blocked {{blocked_sources}} corroboration {{minimum_corroboration}}",
            encoding="utf-8",
        )
        (root / "prompts" / "scoring" / "system.txt").write_text("Scoring prompt system.", encoding="utf-8")
        (root / "prompts" / "scoring" / "prospect_scorecard.txt").write_text(
            "Score {{organization}} {{org_type}} {{relationship_depth}} {{allocator_profile}} {{external_allocations}} {{sustainability_mandate}} {{brand_signal}} {{emerging_manager_program}} {{aum}}",
            encoding="utf-8",
        )
        (root / "prompts" / "scoring" / "validation_review.txt").write_text(
            "Validate {{organization}} {{org_type}} {{sector_fit}} {{halo_value}} {{emerging_fit}} {{composite}} {{flags}}",
            encoding="utf-8",
        )

        settings = AppSettings.from_root(root)
        pipeline = ProspectPipeline(settings)
        run_id = pipeline.run()

        with closing(sqlite3.connect(settings.database_path)) as connection:
            prospect_count = connection.execute(
                "SELECT COUNT(*) FROM prospects WHERE run_id = ?",
                (run_id,),
            ).fetchone()[0]

        self.assertEqual(prospect_count, 1)
        with settings.leaderboard_path(run_id).open("r", encoding="utf-8", newline="") as handle:
            exported_rows = list(csv.DictReader(handle))

        self.assertEqual(len(exported_rows), 1)
        self.assertEqual(exported_rows[0]["run_id"], run_id)
        self.assertEqual(exported_rows[0]["enrichment_mode"], "heuristic_offline")
        self.assertEqual(exported_rows[0]["enrichment_org_type"], "Foundation")
        self.assertEqual(
            exported_rows[0]["allocator_profile"],
            "Likely LP allocator profile based on organization type.",
        )
        self.assertEqual(exported_rows[0]["aum"], "Unknown")
        self.assertEqual(exported_rows[0]["trusted_source_count"], "0")
        self.assertEqual(exported_rows[0]["blocked_source_count"], "0")
        self.assertEqual(exported_rows[0]["minimum_corroboration_met"], "False")
        self.assertEqual(exported_rows[0]["manual_review_required"], "False")
        self.assertEqual(exported_rows[0]["validation_flags"], "None")
        self.assertEqual(exported_rows[0]["check_size_estimate"], "Unknown")
        self.assertIn("run_total_cost_usd", exported_rows[0])
        self.assertIn("run_effective_cost_per_contact_usd", exported_rows[0])
        self.assertIn("run_enrichment_cost_usd", exported_rows[0])
        self.assertEqual(
            exported_rows[0]["insufficient_evidence_dimensions"],
            "sector_fit; halo_value; emerging_fit",
        )
        with settings.run_summary_path(run_id).open("r", encoding="utf-8", newline="") as handle:
            run_summary_rows = list(csv.DictReader(handle))
        with settings.cost_breakdown_path(run_id).open("r", encoding="utf-8", newline="") as handle:
            cost_breakdown_rows = list(csv.DictReader(handle))
        with settings.cost_projections_path(run_id).open("r", encoding="utf-8", newline="") as handle:
            cost_projection_rows = list(csv.DictReader(handle))

        self.assertEqual(len(run_summary_rows), 1)
        self.assertEqual(run_summary_rows[0]["run_id"], run_id)
        self.assertEqual(run_summary_rows[0]["prospect_count"], "1")
        self.assertEqual(len(cost_breakdown_rows), 2)
        self.assertEqual(cost_breakdown_rows[0]["run_id"], run_id)
        self.assertEqual(len(cost_projection_rows), 3)
        self.assertEqual(cost_projection_rows[0]["run_id"], run_id)


if __name__ == "__main__":
    unittest.main()
