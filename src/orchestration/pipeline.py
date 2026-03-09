from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime, timezone

from config.settings import AppSettings
from src.costing.tracker import CostTracker
from src.dashboard.service import DashboardService
from src.dedup.org_registry import build_org_index
from src.enrichment.provider import StarterEnrichmentProvider
from src.ingest.csv_loader import load_contacts
from src.models.entities import ProspectResult
from src.persistence.repository import ProspectRepository
from src.scoring.engine import StarterScoringEngine
from src.validation.rules import ValidationEngine


class ProspectPipeline:
    def __init__(self, settings: AppSettings) -> None:
        self.settings = settings
        self.enrichment_provider = StarterEnrichmentProvider()
        self.scoring_engine = StarterScoringEngine()
        self.validation_engine = ValidationEngine()
        self.cost_tracker = CostTracker()
        self.repository = ProspectRepository(settings.database_path)
        self.dashboard = DashboardService(settings.database_path)

    def run(self) -> str:
        contacts = load_contacts(self.settings.input_csv)
        org_index = build_org_index(contacts)
        run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        results: list[ProspectResult] = []

        for organization_key, org_contacts in org_index.items():
            enrichment = self.enrichment_provider.enrich(organization_key, org_contacts)
            for contact in org_contacts:
                score = self.scoring_engine.score(contact, enrichment)
                flags = self.validation_engine.validate(contact, enrichment, score)
                results.append(
                    ProspectResult(
                        contact=contact,
                        enrichment=enrichment,
                        score=score,
                        validation_flags=flags,
                    )
                )

        results.sort(key=lambda item: item.score.composite, reverse=True)
        self.repository.initialize()
        self.repository.save_run(
            run_id=run_id,
            results=results,
            org_count=len(org_index),
            cost_snapshot=self.cost_tracker.snapshot(),
        )
        self._write_processed_output(run_id, results)
        self._write_state(run_id, len(results), len(org_index))
        self.dashboard.export_run_csv(run_id, self.settings.export_dir / f"{run_id}_leaderboard.csv")
        return run_id

    def _write_processed_output(self, run_id: str, results: list[ProspectResult]) -> None:
        self.settings.processed_dir.mkdir(parents=True, exist_ok=True)
        output_path = self.settings.processed_dir / f"{run_id}_results.json"
        payload = {
            "run_id": run_id,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "results": [asdict(result) for result in results],
            "cost_summary": self.cost_tracker.snapshot(),
        }
        output_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def _write_state(self, run_id: str, prospect_count: int, org_count: int) -> None:
        self.settings.state_dir.mkdir(parents=True, exist_ok=True)
        state_path = self.settings.state_dir / "latest_run.json"
        state = {
            "run_id": run_id,
            "prospect_count": prospect_count,
            "organization_count": org_count,
            "database_path": str(self.settings.database_path),
        }
        state_path.write_text(json.dumps(state, indent=2), encoding="utf-8")
