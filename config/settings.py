from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path


@dataclass(frozen=True, slots=True)
class AppSettings:
    root_dir: Path
    prompt_dir: Path
    input_csv: Path
    cache_path: Path
    database_path: Path
    processed_dir: Path
    export_dir: Path
    state_dir: Path
    log_dir: Path
    enrichment_requests_per_minute: int
    scoring_requests_per_minute: int
    webhook_urls: tuple[str, ...]
    webhook_timeout_seconds: float
    api_host: str
    api_port: int

    @classmethod
    def from_root(cls, root_dir: Path | None = None) -> "AppSettings":
        resolved_root = root_dir or Path(__file__).resolve().parents[1]
        return cls(
            root_dir=resolved_root,
            prompt_dir=resolved_root / "prompts",
            input_csv=resolved_root / "data" / "incoming" / "challenge_contacts.csv",
            cache_path=resolved_root / "data" / "cache" / "enrichment_cache.json",
            database_path=resolved_root / "storage" / "db" / "prospects.sqlite3",
            processed_dir=resolved_root / "data" / "processed",
            export_dir=resolved_root / "data" / "exports",
            state_dir=resolved_root / "storage" / "state",
            log_dir=resolved_root / "storage" / "logs",
            enrichment_requests_per_minute=int(os.getenv("PACEZERO_ENRICHMENT_RPM", "30")),
            scoring_requests_per_minute=int(os.getenv("PACEZERO_SCORING_RPM", "120")),
            webhook_urls=_parse_webhook_urls(os.getenv("PACEZERO_WEBHOOK_URLS", "")),
            webhook_timeout_seconds=float(os.getenv("PACEZERO_WEBHOOK_TIMEOUT_SECONDS", "5.0")),
            api_host=os.getenv("PACEZERO_API_HOST", "127.0.0.1"),
            api_port=int(os.getenv("PACEZERO_API_PORT", "8000")),
        )

    def processed_output_path(self, run_id: str) -> Path:
        return self.processed_dir / f"{run_id}_results.json"

    def leaderboard_path(self, run_id: str) -> Path:
        return self.export_dir / f"{run_id}_leaderboard.csv"

    def report_path(self, run_id: str) -> Path:
        return self.export_dir / f"{run_id}_report.html"

    def run_manifest_path(self, run_id: str) -> Path:
        return self.state_dir / f"{run_id}.json"


def _parse_webhook_urls(value: str) -> tuple[str, ...]:
    urls = [item.strip() for item in value.split(",") if item.strip()]
    return tuple(urls)
