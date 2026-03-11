from __future__ import annotations

import csv
import unittest
from pathlib import Path
import uuid

from src.ingest.csv_loader import load_contacts


class CsvLoaderTests(unittest.TestCase):
    def test_loader_skips_rows_with_invalid_relationship_depth(self) -> None:
        sandbox_dir = Path.cwd() / "tests" / "tmp"
        sandbox_dir.mkdir(parents=True, exist_ok=True)
        csv_path = sandbox_dir / f"loader_fixture_{uuid.uuid4().hex}.csv"
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
                    "Valid Contact",
                    "Valid Foundation",
                    "Foundation",
                    "Director of Investments",
                    "",
                    "NYC",
                    "New Contact",
                    "7",
                ]
            )
            writer.writerow(
                [
                    "Broken Contact",
                    "Broken Foundation",
                    "Foundation",
                    "Director of Investments",
                    "",
                    "NYC",
                    "New Contact",
                    "abc",
                ]
            )
            writer.writerow(
                [
                    "Out Of Range",
                    "Broken Foundation",
                    "Foundation",
                    "Director of Investments",
                    "",
                    "NYC",
                    "New Contact",
                    "12",
                ]
            )

        contacts = load_contacts(csv_path)

        self.assertEqual(len(contacts), 1)
        self.assertEqual(contacts[0].contact_name, "Valid Contact")


if __name__ == "__main__":
    unittest.main()
