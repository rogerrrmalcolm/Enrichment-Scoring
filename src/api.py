from __future__ import annotations

import asyncio
import sqlite3
from pathlib import Path
from typing import Any

from config.settings import AppSettings
from src.dashboard.service import DashboardService
from src.orchestration.pipeline import ProspectPipeline
from src.orchestration.state import RunStateStore


def create_app(settings: AppSettings | None = None) -> Any:
    """Build the FastAPI app only when FastAPI is installed."""
    try:
        from fastapi import FastAPI, HTTPException, Query
        from fastapi.responses import HTMLResponse
    except ImportError as exc:
        raise RuntimeError(_fastapi_dependency_message()) from exc

    app_settings = settings or AppSettings.from_root()
    dashboard = DashboardService(app_settings.database_path)
    state_store = RunStateStore(app_settings.state_dir)

    app = FastAPI(
        title="PaceZero Enrichment API",
        version="0.1.0",
        description=(
            "HTTP layer for triggering pipeline runs and reviewing scored LP prospects "
            "from the existing SQLite-backed workflow."
        ),
    )

    @app.get("/")
    def root() -> dict[str, object]:
        latest = state_store.load_latest()
        return {
            "service": "pacezero-enrichment-api",
            "status": "ok",
            "docs_path": "/docs",
            "latest_run_id": latest.get("run_id") if latest else None,
        }

    @app.get("/health")
    def health() -> dict[str, object]:
        latest = state_store.load_latest()
        return {
            "status": "ok",
            "input_csv_exists": app_settings.input_csv.exists(),
            "database_path": str(app_settings.database_path),
            "database_exists": app_settings.database_path.exists(),
            "latest_run_id": latest.get("run_id") if latest else None,
        }

    @app.post("/runs")
    async def run_pipeline() -> dict[str, object]:
        # The pipeline is synchronous today, so the API pushes it to a worker thread
        # to avoid blocking the event loop for other requests.
        pipeline = ProspectPipeline(app_settings)
        run_id = await asyncio.to_thread(pipeline.run)
        return _build_run_payload(run_id, dashboard, state_store, HTTPException)

    @app.get("/runs/latest")
    def latest_run() -> dict[str, object]:
        latest = state_store.load_latest()
        if latest is None:
            raise HTTPException(status_code=404, detail="No pipeline runs have been recorded yet.")
        run_id = str(latest["run_id"])
        return _build_run_payload(run_id, dashboard, state_store, HTTPException)

    @app.get("/runs/{run_id}")
    def get_run(run_id: str) -> dict[str, object]:
        return _build_run_payload(run_id, dashboard, state_store, HTTPException)

    @app.get("/runs/{run_id}/prospects")
    def get_run_prospects(
        run_id: str,
        limit: int = Query(default=50, ge=1, le=500),
        flagged_only: bool = False,
    ) -> dict[str, object]:
        rows = _load_rows(run_id, dashboard, state_store, HTTPException)
        if flagged_only:
            rows = [row for row in rows if row["validation_flags"]]
        return {
            "run_id": run_id,
            "count": min(len(rows), limit),
            "total_available": len(rows),
            "flagged_only": flagged_only,
            "prospects": rows[:limit],
        }

    @app.get("/runs/{run_id}/report", response_class=HTMLResponse)
    def get_run_report(run_id: str) -> HTMLResponse:
        manifest = state_store.load(run_id)
        candidate = None
        if manifest is not None:
            artifacts = manifest.get("artifacts", {})
            if isinstance(artifacts, dict):
                candidate = artifacts.get("html_report")
        report_path = Path(candidate) if candidate else app_settings.report_path(run_id)
        if not report_path.exists():
            raise HTTPException(status_code=404, detail="HTML report not found for this run.")
        return HTMLResponse(report_path.read_text(encoding="utf-8"))

    return app


def _build_run_payload(
    run_id: str,
    dashboard: DashboardService,
    state_store: RunStateStore,
    http_exception_type: type[Exception],
) -> dict[str, object]:
    manifest = state_store.load(run_id)
    summary = _safe_fetch_summary(run_id, dashboard)
    if manifest is None and summary is None:
        raise http_exception_type(status_code=404, detail=f"Run '{run_id}' was not found.")
    return {
        "run_id": run_id,
        "manifest": manifest,
        "summary": summary,
        "top_prospects": _safe_fetch_top_prospects(run_id, dashboard, limit=10),
    }


def _load_rows(
    run_id: str,
    dashboard: DashboardService,
    state_store: RunStateStore,
    http_exception_type: type[Exception],
) -> list[dict[str, Any]]:
    try:
        rows = dashboard.fetch_run_rows(run_id)
    except sqlite3.Error as exc:
        if state_store.load(run_id) is None:
            raise http_exception_type(status_code=404, detail=f"Run '{run_id}' was not found.") from exc
        rows = []
    if not rows and state_store.load(run_id) is None:
        raise http_exception_type(status_code=404, detail=f"Run '{run_id}' was not found.")
    return rows


def _safe_fetch_summary(run_id: str, dashboard: DashboardService) -> dict[str, Any] | None:
    try:
        return dashboard.fetch_run_summary(run_id)
    except sqlite3.Error:
        return None


def _safe_fetch_top_prospects(
    run_id: str,
    dashboard: DashboardService,
    *,
    limit: int,
) -> list[dict[str, Any]]:
    try:
        return dashboard.fetch_top_prospects(run_id, limit=limit)
    except sqlite3.Error:
        return []


def _fastapi_dependency_message() -> str:
    return (
        "FastAPI support is present in the codebase, but the runtime dependencies are missing. "
        "Install 'fastapi' and 'uvicorn' to start the API server."
    )

