from __future__ import annotations

import csv
import json
import sqlite3
from html import escape
from pathlib import Path
from typing import Any


class DashboardService:
    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path

    def fetch_top_prospects(self, run_id: str, limit: int = 20) -> list[dict[str, Any]]:
        rows = self.fetch_run_rows(run_id)
        return rows[:limit]

    def fetch_run_rows(self, run_id: str) -> list[dict[str, Any]]:
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
                    tier,
                    validation_flags,
                    enrichment_json,
                    score_json
                FROM prospects
                WHERE run_id = ?
                ORDER BY composite DESC, relationship_depth DESC, organization ASC
                """,
                (run_id,),
            ).fetchall()
        dataset: list[dict[str, Any]] = []
        for row in rows:
            record = dict(row)
            record["validation_flags"] = json.loads(record["validation_flags"])
            record["enrichment"] = json.loads(record.pop("enrichment_json"))
            record["score"] = json.loads(record.pop("score_json"))
            dataset.append(record)
        return dataset

    def fetch_run_summary(self, run_id: str) -> dict[str, Any]:
        rows = self.fetch_run_rows(run_id)
        with sqlite3.connect(self.database_path) as connection:
            connection.row_factory = sqlite3.Row
            run_row = connection.execute(
                """
                SELECT
                    prospect_count,
                    org_count,
                    total_cost_usd,
                    cost_json
                FROM pipeline_runs
                WHERE run_id = ?
                """,
                (run_id,),
            ).fetchone()
        tier_counts: dict[str, int] = {}
        for row in rows:
            tier_counts[row["tier"]] = tier_counts.get(row["tier"], 0) + 1
        return {
            "run_id": run_id,
            "prospect_count": run_row["prospect_count"] if run_row else len(rows),
            "org_count": run_row["org_count"] if run_row else len({row["organization"] for row in rows}),
            "avg_composite": round(sum(row["composite"] for row in rows) / max(len(rows), 1), 2),
            "flagged_count": sum(1 for row in rows if row["validation_flags"]),
            "tier_counts": tier_counts,
            "cost": json.loads(run_row["cost_json"]) if run_row else {},
        }

    def export_run_csv(self, run_id: str, destination: Path) -> None:
        rows = self.fetch_run_rows(run_id)
        if not rows:
            return
        flat_rows = []
        for row in rows:
            flat_rows.append(
                {
                    "contact_name": row["contact_name"],
                    "organization": row["organization"],
                    "org_type": row["org_type"],
                    "region": row["region"],
                    "contact_status": row["contact_status"],
                    "relationship_depth": row["relationship_depth"],
                    "sector_fit": row["sector_fit"],
                    "halo_value": row["halo_value"],
                    "emerging_fit": row["emerging_fit"],
                    "composite": row["composite"],
                    "tier": row["tier"],
                    "check_size_estimate": row["score"].get("check_size_estimate"),
                    "validation_flags": "; ".join(row["validation_flags"]),
                }
            )
        destination.parent.mkdir(parents=True, exist_ok=True)
        with destination.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(flat_rows[0].keys()))
            writer.writeheader()
            writer.writerows(flat_rows)

    def export_run_html(self, run_id: str, destination: Path) -> None:
        rows = self.fetch_run_rows(run_id)
        if not rows:
            return
        summary = self.fetch_run_summary(run_id)
        flagged_rows = [row for row in rows if row["validation_flags"]]
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(
            self._build_html(summary, rows[:25], flagged_rows[:25]),
            encoding="utf-8",
        )

    def _build_html(
        self,
        summary: dict[str, Any],
        top_rows: list[dict[str, Any]],
        flagged_rows: list[dict[str, Any]],
    ) -> str:
        # Keep the report static and dependency-free so it is easy to share.
        cards = "".join(
            [
                _summary_card("Prospects", str(summary["prospect_count"])),
                _summary_card("Organizations", str(summary["org_count"])),
                _summary_card("Avg Composite", f"{summary['avg_composite']:.2f}"),
                _summary_card("Flagged", str(summary["flagged_count"])),
                _summary_card("Estimated Cost", f"${summary['cost'].get('total_cost_usd', 0):.4f}"),
                _summary_card("Avoided Cost", f"${summary['cost'].get('avoided_cost_usd', 0):.4f}"),
            ]
        )
        tier_list = "".join(
            f"<li><strong>{escape(tier)}</strong>: {count}</li>"
            for tier, count in sorted(summary["tier_counts"].items())
        )
        top_table = _rows_to_table(top_rows)
        flagged_table = _rows_to_table(flagged_rows, include_flags=True)
        return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>PaceZero Pipeline Report</title>
  <style>
    body {{ font-family: Georgia, serif; margin: 32px; color: #1f2933; background: #f7f4ed; }}
    h1, h2 {{ margin-bottom: 12px; }}
    .cards {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 12px; margin: 20px 0 28px; }}
    .card {{ background: white; padding: 16px; border-radius: 10px; border: 1px solid #d9d2c3; }}
    .label {{ font-size: 12px; text-transform: uppercase; color: #7a6f5a; letter-spacing: 0.08em; }}
    .value {{ font-size: 28px; font-weight: 700; margin-top: 6px; }}
    table {{ width: 100%; border-collapse: collapse; background: white; border-radius: 10px; overflow: hidden; }}
    th, td {{ padding: 10px 12px; border-bottom: 1px solid #ece6db; text-align: left; vertical-align: top; }}
    th {{ background: #efe7d6; }}
    .section {{ margin-top: 28px; }}
    .flags {{ color: #9b2226; font-weight: 600; }}
  </style>
</head>
<body>
  <h1>PaceZero LP Pipeline Report</h1>
  <p>Run <strong>{escape(summary['run_id'])}</strong></p>
  <div class="cards">{cards}</div>
  <div class="section">
    <h2>Tier Mix</h2>
    <ul>{tier_list}</ul>
  </div>
  <div class="section">
    <h2>Top Prospects</h2>
    {top_table}
  </div>
  <div class="section">
    <h2>Flagged Prospects</h2>
    {flagged_table}
  </div>
</body>
</html>"""


def _summary_card(label: str, value: str) -> str:
    return f'<div class="card"><div class="label">{escape(label)}</div><div class="value">{escape(value)}</div></div>'


def _rows_to_table(rows: list[dict[str, Any]], include_flags: bool = False) -> str:
    if not rows:
        return "<p>No rows available.</p>"
    headers = ["Organization", "Contact", "Tier", "Composite", "Sector", "Halo", "Emerging", "Check Size"]
    if include_flags:
        headers.append("Flags")
    header_html = "".join(f"<th>{escape(header)}</th>" for header in headers)
    body_parts: list[str] = []
    for row in rows:
        columns = [
            escape(row["organization"]),
            escape(row["contact_name"]),
            escape(row["tier"]),
            f"{row['composite']:.2f}",
            f"{row['sector_fit']:.2f}",
            f"{row['halo_value']:.2f}",
            f"{row['emerging_fit']:.2f}",
            escape(str(row["score"].get("check_size_estimate") or "Unknown")),
        ]
        if include_flags:
            columns.append(
                '<div class="flags">' + escape("; ".join(row["validation_flags"]) or "None") + "</div>"
            )
        body_parts.append("<tr>" + "".join(f"<td>{column}</td>" for column in columns) + "</tr>")
    return f"<table><thead><tr>{header_html}</tr></thead><tbody>{''.join(body_parts)}</tbody></table>"
