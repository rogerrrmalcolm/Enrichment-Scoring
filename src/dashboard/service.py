from __future__ import annotations

import csv
import sqlite3
from pathlib import Path
from typing import Any


class DashboardService:
    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path

    def fetch_top_prospects(self, run_id: str, limit: int = 20) -> list[dict[str, Any]]:
        with sqlite3.connect(self.database_path) as connection:
            connection.row_factory = sqlite3.Row
            rows = connection.execute(
                """
                SELECT
                    contact_name,
                    organization,
                    org_type,
                    region,
                    contact_status,
                    relationship_depth,
                    sector_fit,
                    halo_value,
                    emerging_fit,
                    composite,
                    tier
                FROM prospects
                WHERE run_id = ?
                ORDER BY composite DESC, relationship_depth DESC, organization ASC
                LIMIT ?
                """,
                (run_id, limit),
            ).fetchall()
        return [dict(row) for row in rows]

    def export_run_csv(self, run_id: str, destination: Path) -> None:
        rows = self.fetch_top_prospects(run_id, limit=10_000)
        if not rows:
            return
        destination.parent.mkdir(parents=True, exist_ok=True)
        with destination.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)
