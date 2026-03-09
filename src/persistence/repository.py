from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from src.models.entities import ProspectResult


class ProspectRepository:
    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path

    def initialize(self) -> None:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.database_path) as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS pipeline_runs (
                    run_id TEXT PRIMARY KEY,
                    started_at TEXT NOT NULL,
                    prospect_count INTEGER NOT NULL,
                    org_count INTEGER NOT NULL,
                    total_cost_usd REAL NOT NULL,
                    cost_json TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS prospects (
                    run_id TEXT NOT NULL,
                    contact_name TEXT NOT NULL,
                    organization TEXT NOT NULL,
                    org_type TEXT NOT NULL,
                    region TEXT NOT NULL,
                    contact_status TEXT NOT NULL,
                    relationship_depth INTEGER NOT NULL,
                    sector_fit REAL NOT NULL,
                    halo_value REAL NOT NULL,
                    emerging_fit REAL NOT NULL,
                    composite REAL NOT NULL,
                    tier TEXT NOT NULL,
                    validation_flags TEXT NOT NULL,
                    enrichment_json TEXT NOT NULL,
                    score_json TEXT NOT NULL,
                    PRIMARY KEY (run_id, contact_name, organization)
                )
                """
            )

    def save_run(
        self,
        run_id: str,
        results: Iterable[ProspectResult],
        org_count: int,
        cost_snapshot: dict[str, object],
    ) -> None:
        rows = list(results)
        with sqlite3.connect(self.database_path) as connection:
            connection.execute(
                """
                INSERT OR REPLACE INTO pipeline_runs (
                    run_id,
                    started_at,
                    prospect_count,
                    org_count,
                    total_cost_usd,
                    cost_json
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    datetime.now(timezone.utc).isoformat(),
                    len(rows),
                    org_count,
                    float(cost_snapshot["total_cost_usd"]),
                    json.dumps(cost_snapshot),
                ),
            )
            connection.executemany(
                """
                INSERT OR REPLACE INTO prospects (
                    run_id,
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
                    tier,
                    validation_flags,
                    enrichment_json,
                    score_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        run_id,
                        result.contact.contact_name,
                        result.contact.organization,
                        result.contact.org_type,
                        result.contact.region,
                        result.contact.contact_status,
                        result.contact.relationship_depth,
                        result.score.sector_fit.value,
                        result.score.halo_value.value,
                        result.score.emerging_fit.value,
                        result.score.composite,
                        result.score.tier,
                        json.dumps(result.validation_flags),
                        json.dumps(asdict(result.enrichment)),
                        json.dumps(asdict(result.score)),
                    )
                    for result in rows
                ],
            )
