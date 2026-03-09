from __future__ import annotations
import asyncio
import hmac
import logging
import re
import sqlite3
import threading
from pathlib import Path
from typing import Any

from config.settings import AppSettings
from src.dashboard.service import DashboardService
from src.orchestration.pipeline import ProspectPipeline
from src.orchestration.state import RunStateStore


RUN_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


def create_app(settings: AppSettings | None = None) -> Any:
    """Build the FastAPI app only when FastAPI is installed."""
    try:
        from fastapi import Depends, FastAPI, Header, HTTPException, Query
        from fastapi.responses import HTMLResponse
    except ImportError as exc:
        raise RuntimeError(_fastapi_dependency_message()) from exc

    app_settings = settings or AppSettings.from_root()
    dashboard = DashboardService(app_settings.database_path)
    state_store = RunStateStore(app_settings.state_dir)
    logger = logging.getLogger(__name__)
    run_lock = threading.Lock()

    def require_api_key(x_api_key: str | None = Header(default=None, alias="X-API-Key")) -> None:
        if not _api_key_is_valid(x_api_key, app_settings.api_key):
            raise HTTPException(status_code=401, detail="Invalid or missing API key.")

    protected_route_dependencies = [Depends(require_api_key)] if app_settings.api_key else []

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
            "api_key_required": bool(app_settings.api_key),
        }

    @app.get("/health")
    def health() -> dict[str, object]:
        latest = state_store.load_latest()
        return {
            "status": "ok",
            "input_csv_exists": app_settings.input_csv.exists(),
            "database_exists": app_settings.database_path.exists(),
            "latest_run_id": latest.get("run_id") if latest else None,
            "latest_run_status": latest.get("status") if latest else None,
        }

    @app.post("/runs", dependencies=protected_route_dependencies)
    async def run_pipeline() -> dict[str, object]:
        if not run_lock.acquire(blocking=False):
            raise HTTPException(status_code=409, detail="A pipeline run is already in progress.")
        try:
            pipeline = ProspectPipeline(app_settings)
            run_id = await asyncio.to_thread(pipeline.run)
            return _build_run_payload(run_id, dashboard, state_store, HTTPException)
        except Exception as exc:
            logger.exception("Pipeline execution failed")
            raise HTTPException(status_code=500, detail="Pipeline run failed. Check server logs.") from exc
        finally:
            run_lock.release()

    @app.get("/runs/latest", dependencies=protected_route_dependencies)
    def latest_run() -> dict[str, object]:
        latest = state_store.load_latest()
        if latest is None:
            raise HTTPException(status_code=404, detail="No pipeline runs have been recorded yet.")
        run_id = _coerce_run_id(str(latest["run_id"]), HTTPException)
        return _build_run_payload(run_id, dashboard, state_store, HTTPException)

    @app.get("/runs/{run_id}", dependencies=protected_route_dependencies)
    def get_run(run_id: str) -> dict[str, object]:
        safe_run_id = _coerce_run_id(run_id, HTTPException)
        return _build_run_payload(safe_run_id, dashboard, state_store, HTTPException)

    @app.get("/runs/{run_id}/prospects", dependencies=protected_route_dependencies)
    def get_run_prospects(
        run_id: str,
        limit: int = Query(default=50, ge=1, le=500),
        flagged_only: bool = False,
    ) -> dict[str, object]:
        safe_run_id = _coerce_run_id(run_id, HTTPException)
        rows = _load_rows(safe_run_id, dashboard, state_store, HTTPException)
        if flagged_only:
            rows = [row for row in rows if row["validation_flags"]]
        return {
            "run_id": safe_run_id,
            "count": min(len(rows), limit),
            "total_available": len(rows),
            "flagged_only": flagged_only,
            "prospects": rows[:limit],
        }

    @app.get("/runs/{run_id}/report", response_class=HTMLResponse, dependencies=protected_route_dependencies)
    def get_run_report(run_id: str) -> HTMLResponse:
        safe_run_id = _coerce_run_id(run_id, HTTPException)
        manifest = state_store.load(safe_run_id)
        try:
            report_path = _resolve_report_path(safe_run_id, manifest, app_settings)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        if not report_path.exists():
            raise HTTPException(status_code=404, detail="HTML report not found for this run.")
        return HTMLResponse(report_path.read_text(encoding="utf-8"))

    return app


def _build_run_payload(
    run_id: str,
    dashboard: DashboardService,
    state_store: RunStateStore,
    http_exception_type: type[Any],
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
    http_exception_type: type[Any],
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


def _coerce_run_id(run_id: str, http_exception_type: type[Any]) -> str:
    try:
        return _validate_run_id(run_id)
    except ValueError as exc:
        raise http_exception_type(status_code=400, detail=str(exc)) from exc


def _validate_run_id(run_id: str) -> str:
    if not RUN_ID_PATTERN.fullmatch(run_id):
        raise ValueError("run_id may only contain letters, numbers, dots, underscores, and dashes.")
    return run_id


def _resolve_report_path(
    run_id: str,
    manifest: dict[str, object] | None,
    settings: AppSettings,
) -> Path:
    candidate = None
    if manifest is not None:
        artifacts = manifest.get("artifacts", {})
        if isinstance(artifacts, dict):
            candidate = artifacts.get("html_report")

    report_path = Path(candidate) if candidate else settings.report_path(run_id)
    if not report_path.is_absolute():
        report_path = settings.export_dir / report_path.name

    resolved_report = report_path.resolve(strict=False)
    resolved_export_dir = settings.export_dir.resolve(strict=False)
    if not _is_relative_to(resolved_report, resolved_export_dir):
        raise ValueError("Resolved report path is outside the allowed export directory.")
    return resolved_report


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _api_key_is_valid(provided_api_key: str | None, configured_api_key: str | None) -> bool:
    if not configured_api_key:
        return True
    return bool(provided_api_key) and hmac.compare_digest(provided_api_key, configured_api_key)


def _fastapi_dependency_message() -> str:
    return (
        "FastAPI support is present in the codebase, but the runtime dependencies are missing. "
        "Install 'fastapi' and 'uvicorn' to start the API server."
    )
