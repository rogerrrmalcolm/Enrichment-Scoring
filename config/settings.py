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
    api_key: str | None
    enable_live_enrichment: bool
    openai_api_key: str | None
    openai_base_url: str
    openai_enrichment_model: str
    openai_timeout_seconds: float

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
            enrichment_requests_per_minute=_env_non_negative_int("PACEZERO_ENRICHMENT_RPM", 30),
            scoring_requests_per_minute=_env_non_negative_int("PACEZERO_SCORING_RPM", 120),
            webhook_urls=_parse_webhook_urls(os.getenv("PACEZERO_WEBHOOK_URLS", "")),
            webhook_timeout_seconds=_env_positive_float("PACEZERO_WEBHOOK_TIMEOUT_SECONDS", 5.0),
            api_host=os.getenv("PACEZERO_API_HOST", "127.0.0.1"),
            api_port=_env_port("PACEZERO_API_PORT", 8000),
            api_key=_optional_env("PACEZERO_API_KEY"),
            enable_live_enrichment=_env_bool("PACEZERO_ENABLE_LIVE_ENRICHMENT", False),
            openai_api_key=_optional_env("OPENAI_API_KEY"),
            openai_base_url=os.getenv("PACEZERO_OPENAI_BASE_URL", "https://api.openai.com/v1/responses").strip(),
            openai_enrichment_model=os.getenv("PACEZERO_OPENAI_MODEL", "gpt-4.1-mini").strip() or "gpt-4.1-mini",
            openai_timeout_seconds=_env_positive_float("PACEZERO_OPENAI_TIMEOUT_SECONDS", 45.0),
        )

    def processed_output_path(self, run_id: str) -> Path:
        return self.processed_dir / f"{run_id}_results.json"

    def leaderboard_path(self, run_id: str) -> Path:
        return self.export_dir / f"{run_id}_leaderboard.csv"

    def run_summary_path(self, run_id: str) -> Path:
        return self.export_dir / f"{run_id}_run_summary.csv"

    def cost_breakdown_path(self, run_id: str) -> Path:
        return self.export_dir / f"{run_id}_cost_breakdown.csv"

    def cost_projections_path(self, run_id: str) -> Path:
        return self.export_dir / f"{run_id}_cost_projections.csv"

    def report_path(self, run_id: str) -> Path:
        return self.export_dir / f"{run_id}_report.html"

    def run_manifest_path(self, run_id: str) -> Path:
        return self.state_dir / f"{run_id}.json"


def _parse_webhook_urls(value: str) -> tuple[str, ...]:
    urls = [item.strip() for item in value.split(",") if item.strip()]
    return tuple(urls)


def _env_non_negative_int(name: str, default: int) -> int:
    raw_value = os.getenv(name, str(default))
    try:
        parsed = int(raw_value)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer, got {raw_value!r}.") from exc
    if parsed < 0:
        raise ValueError(f"{name} must be zero or greater, got {parsed}.")
    return parsed


def _env_positive_float(name: str, default: float) -> float:
    raw_value = os.getenv(name, str(default))
    try:
        parsed = float(raw_value)
    except ValueError as exc:
        raise ValueError(f"{name} must be a number, got {raw_value!r}.") from exc
    if parsed <= 0:
        raise ValueError(f"{name} must be greater than zero, got {parsed}.")
    return parsed


def _env_port(name: str, default: int) -> int:
    parsed = _env_non_negative_int(name, default)
    if parsed == 0 or parsed > 65535:
        raise ValueError(f"{name} must be between 1 and 65535, got {parsed}.")
    return parsed


def _optional_env(name: str) -> str | None:
    value = os.getenv(name, "").strip()
    return value or None


def _env_bool(name: str, default: bool) -> bool:
    raw_value = os.getenv(name, "true" if default else "false").strip().lower()
    if raw_value in {"1", "true", "yes", "on"}:
        return True
    if raw_value in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"{name} must be a boolean-like value, got {raw_value!r}.")
