from __future__ import annotations

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
        (root / "data" / "incoming").mkdir(parents=True)
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

        settings = AppSettings.from_root(root)
        pipeline = ProspectPipeline(settings)
        run_id = pipeline.run()

        with sqlite3.connect(settings.database_path) as connection:
            prospect_count = connection.execute(
                "SELECT COUNT(*) FROM prospects WHERE run_id = ?",
                (run_id,),
            ).fetchone()[0]

        self.assertEqual(prospect_count, 1)


if __name__ == "__main__":
    unittest.main()
