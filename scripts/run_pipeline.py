from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config.settings import AppSettings
from src.dashboard.service import DashboardService
from src.orchestration.pipeline import ProspectPipeline
from src.utils.logging import configure_logging


def main() -> int:
    settings = AppSettings.from_root(ROOT)
    configure_logging(settings.log_dir)
    pipeline = ProspectPipeline(settings)
    run_id = pipeline.run()
    dashboard = DashboardService(settings.database_path)
    top_rows = dashboard.fetch_top_prospects(run_id, limit=10)

    print(f"Completed run: {run_id}")
    print(f"Database: {settings.database_path}")
    print(f"Top prospects exported to: {settings.leaderboard_path(run_id)}")
    print(f"HTML report: {settings.report_path(run_id)}")
    for row in top_rows[:5]:
        print(
            f"{row['composite']:>4.2f} | {row['tier']:<14} | "
            f"{row['organization']} | {row['contact_name']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
