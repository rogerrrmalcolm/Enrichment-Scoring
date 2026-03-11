from __future__ import annotations

import argparse
import csv
from dataclasses import replace
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config.settings import AppSettings
from src.dashboard.service import DashboardService
from src.orchestration.pipeline import ProspectPipeline
from src.utils.logging import configure_logging


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    settings = AppSettings.from_root(ROOT)
    if args.input is not None:
        settings = replace(settings, input_csv=args.input)
    configure_logging(settings.log_dir)
    pipeline = ProspectPipeline(settings)
    run_id = pipeline.run()
    dashboard = DashboardService(settings.database_path)
    top_rows = dashboard.fetch_top_prospects(run_id, limit=10)
    summary = dashboard.fetch_run_summary(run_id)
    enrichment_modes = _count_enrichment_modes(settings.leaderboard_path(run_id))

    print(f"Completed run: {run_id}")
    print(f"Input CSV: {settings.input_csv}")
    print(f"Database: {settings.database_path}")
    print(f"Top prospects exported to: {settings.leaderboard_path(run_id)}")
    print(f"Run summary CSV: {settings.run_summary_path(run_id)}")
    print(f"Cost breakdown CSV: {settings.cost_breakdown_path(run_id)}")
    print(f"Cost projections CSV: {settings.cost_projections_path(run_id)}")
    print(f"HTML report: {settings.report_path(run_id)}")
    print(f"Estimated API cost: ${summary['cost'].get('total_cost_usd', 0):.4f}")
    if enrichment_modes:
        print(
            "Enrichment modes: "
            + ", ".join(f"{mode}={count}" for mode, count in sorted(enrichment_modes.items()))
        )
    for row in top_rows[:5]:
        print(
            f"{row['composite']:>4.2f} | {row['tier']:<14} | "
            f"{row['organization']} | {row['contact_name']}"
        )
    return 0


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the prospect enrichment pipeline.",
    )
    parser.add_argument(
        "--input",
        type=Path,
        help="Path to a CSV file. Defaults to data/incoming/challenge_contacts.csv.",
    )
    args = parser.parse_args(argv)
    if args.input is not None:
        args.input = _resolve_input_csv(args.input)
        if not args.input.exists():
            parser.error(f"input CSV not found: {args.input}")
        if not args.input.is_file():
            parser.error(f"input CSV must be a file: {args.input}")
    return args


def _resolve_input_csv(input_path: Path, cwd: Path | None = None) -> Path:
    base_dir = cwd or Path.cwd()
    expanded = input_path.expanduser()
    if expanded.is_absolute():
        return expanded.resolve(strict=False)
    return (base_dir / expanded).resolve(strict=False)


def _count_enrichment_modes(leaderboard_path: Path) -> dict[str, int]:
    if not leaderboard_path.exists():
        return {}
    counts: dict[str, int] = {}
    with leaderboard_path.open("r", encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            mode = (row.get("enrichment_mode") or "unknown").strip() or "unknown"
            counts[mode] = counts.get(mode, 0) + 1
    return counts


if __name__ == "__main__":
    raise SystemExit(main())
