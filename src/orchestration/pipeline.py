from __future__ import annotations

import json
import logging
from dataclasses import asdict
from datetime import datetime, timezone

from config.settings import AppSettings
from src.control.rate_limiter import TokenBucketRateLimiter
from src.control.webhooks import WebhookNotifier
from src.costing.tracker import CostTracker
from src.dashboard.service import DashboardService
from src.dedup.org_registry import build_org_index
from src.enrichment.cache import EnrichmentCache
from src.enrichment.provider import StarterEnrichmentProvider
from src.ingest.csv_loader import load_contacts
from src.models.entities import ProspectResult
from src.orchestration.state import RunStateStore
from src.persistence.repository import ProspectRepository
from src.scoring.engine import StarterScoringEngine
from src.utils.prompts import PromptLibrary
from src.validation.rules import ValidationEngine


class ProspectPipeline:
    def __init__(self, settings: AppSettings) -> None:
        self.settings = settings
        self.logger = logging.getLogger(__name__)
        self.prompts = PromptLibrary(settings.prompt_dir)
        self.enrichment_provider = StarterEnrichmentProvider(self.prompts)
        self.scoring_engine = StarterScoringEngine(self.prompts)
        self.validation_engine = ValidationEngine()
        self.cost_tracker = CostTracker()
        self.cache = EnrichmentCache(settings.cache_path)
        self.state_store = RunStateStore(settings.state_dir)
        self.repository = ProspectRepository(settings.database_path)
        self.dashboard = DashboardService(settings.database_path)
        self.enrichment_limiter = TokenBucketRateLimiter(settings.enrichment_requests_per_minute)
        self.scoring_limiter = TokenBucketRateLimiter(settings.scoring_requests_per_minute)
        self.webhooks = WebhookNotifier(
            settings.webhook_urls,
            timeout_seconds=settings.webhook_timeout_seconds,
        )

    def run(self) -> str:
        contacts = load_contacts(self.settings.input_csv)
        org_index = build_org_index(contacts)
        run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        results: list[ProspectResult] = []
        manifest = self.state_store.start_run(run_id, len(contacts), len(org_index))
        manifest["runtime_controls"] = {
            "enrichment_requests_per_minute": self.settings.enrichment_requests_per_minute,
            "scoring_requests_per_minute": self.settings.scoring_requests_per_minute,
            "webhook_count": len(self.settings.webhook_urls),
        }
        self._emit_webhook(
            "run.started",
            {
                "run_id": run_id,
                "contact_count": len(contacts),
                "organization_count": len(org_index),
            },
        )

        for organization_key, org_contacts in org_index.items():
            try:
                enrichment = self.cache.get(organization_key)
                if enrichment is None:
                    self._wait_for_rate_limit(self.enrichment_limiter)
                    enrichment = self.enrichment_provider.enrich(organization_key, org_contacts)
                    self.cache.set(organization_key, enrichment)
                    self.cost_tracker.record_cache_miss()
                    self._record_estimated_cost(
                        vendor="estimated",
                        model="org-research-sim",
                        prompt_artifacts=enrichment.raw_payload.get("prompt_artifacts", {}),
                        completion_tokens=420,
                    )
                else:
                    self.cost_tracker.record_cache_hit(estimated_saved_cost_usd=0.012)

                for contact in org_contacts:
                    self._wait_for_rate_limit(self.scoring_limiter)
                    score = self.scoring_engine.score(contact, enrichment)
                    self._record_estimated_cost(
                        vendor="estimated",
                        model="scoring-sim",
                        prompt_artifacts=score.metadata.get("prompt_artifacts", {}),
                        completion_tokens=260,
                    )
                    flags = self.validation_engine.validate(contact, enrichment, score)
                    results.append(
                        ProspectResult(
                            contact=contact,
                            enrichment=enrichment,
                            score=score,
                            validation_flags=flags,
                        )
                    )
                manifest["completed_organizations"] = int(manifest["completed_organizations"]) + 1
                self.state_store.update_progress(run_id, manifest)
            except Exception as exc:
                self.logger.exception("Failed to process organization %s", organization_key)
                failures = manifest["failed_organizations"]
                if isinstance(failures, list):
                    failures.append({"organization_key": organization_key, "error": str(exc)})
                self.state_store.update_progress(run_id, manifest)
                self._emit_webhook(
                    "run.organization_failed",
                    {
                        "run_id": run_id,
                        "organization_key": organization_key,
                        "error": str(exc),
                    },
                )

        results.sort(key=lambda item: item.score.composite, reverse=True)
        self.cache.save()
        self.repository.initialize()
        self.repository.save_run(
            run_id=run_id,
            results=results,
            org_count=len(org_index),
            cost_snapshot=self.cost_tracker.snapshot(),
        )
        self._write_processed_output(run_id, results)
        self.dashboard.export_run_csv(run_id, self.settings.leaderboard_path(run_id))
        self.dashboard.export_run_html(run_id, self.settings.report_path(run_id))
        manifest["artifacts"] = {
            "database": str(self.settings.database_path),
            "processed_json": str(self.settings.processed_output_path(run_id)),
            "leaderboard_csv": str(self.settings.leaderboard_path(run_id)),
            "html_report": str(self.settings.report_path(run_id)),
        }
        manifest["cost_summary"] = self.cost_tracker.snapshot()
        self.state_store.complete_run(run_id, manifest)
        self._emit_webhook(
            "run.completed",
            {
                "run_id": run_id,
                "completed_organizations": manifest["completed_organizations"],
                "failed_organizations": manifest["failed_organizations"],
                "artifacts": manifest["artifacts"],
                "cost_summary": manifest["cost_summary"],
            },
        )
        return run_id

    def _write_processed_output(self, run_id: str, results: list[ProspectResult]) -> None:
        self.settings.processed_dir.mkdir(parents=True, exist_ok=True)
        output_path = self.settings.processed_output_path(run_id)
        payload = {
            "run_id": run_id,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "results": [asdict(result) for result in results],
            "cost_summary": self.cost_tracker.snapshot(),
        }
        output_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def _record_estimated_cost(
        self,
        vendor: str,
        model: str,
        prompt_artifacts: dict[str, object],
        completion_tokens: int,
    ) -> None:
        # Until a live AI/search provider is wired in, we keep a transparent
        # simulated cost model so run-level economics are visible and testable.
        prompt_tokens = sum(_estimate_tokens(str(value)) for value in prompt_artifacts.values())
        prompt_cost = prompt_tokens * 0.000003
        completion_cost = completion_tokens * 0.000015
        self.cost_tracker.record(
            vendor=vendor,
            model=model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            cost_usd=round(prompt_cost + completion_cost, 6),
        )

    def _wait_for_rate_limit(self, limiter: TokenBucketRateLimiter) -> None:
        waited = limiter.acquire()
        if waited > 0:
            self.logger.info("Rate limiter waited %.3f seconds", waited)
            self.cost_tracker.record_rate_limit_wait(waited)

    def _emit_webhook(self, event_type: str, payload: dict[str, object]) -> None:
        deliveries = self.webhooks.emit(event_type, payload)
        if deliveries:
            self.logger.info("Webhook deliveries for %s: %s", event_type, deliveries)


def _estimate_tokens(text: str) -> int:
    return max(1, len(text) // 4)
