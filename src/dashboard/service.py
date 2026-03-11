from __future__ import annotations

from contextlib import closing
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
        with closing(self._connect()) as connection:
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
        with closing(self._connect()) as connection:
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
        summary = self.fetch_run_summary(run_id)
        run_cost_fields = _summary_cost_fields(summary)
        flat_rows = []
        for row in rows:
            enrichment = row["enrichment"]
            insufficient_dimensions = row["score"].get("metadata", {}).get("insufficient_evidence_dimensions", [])
            source_quality = _source_quality_fields(enrichment)
            flat_rows.append(
                {
                    "run_id": run_id,
                    "contact_name": row["contact_name"],
                    "organization": row["organization"],
                    "org_type": row["org_type"],
                    "enrichment_org_type": _csv_text(enrichment.get("organization_type"), fallback="Unknown"),
                    "region": row["region"],
                    "contact_status": row["contact_status"],
                    "enrichment_mode": _csv_text(
                        enrichment.get("raw_payload", {}).get("enrichment_mode"),
                        fallback="unknown",
                    ),
                    "allocator_profile": _csv_text(enrichment.get("allocator_profile"), fallback="Unknown"),
                    "aum": _csv_text(enrichment.get("aum"), fallback="Unknown"),
                    "trusted_source_count": source_quality["trusted_source_count"],
                    "blocked_source_count": source_quality["blocked_source_count"],
                    "minimum_corroboration_met": source_quality["minimum_corroboration_met"],
                    "manual_review_required": source_quality["manual_review_required"],
                    "relationship_depth": row["relationship_depth"],
                    "sector_fit": row["sector_fit"],
                    "halo_value": row["halo_value"],
                    "emerging_fit": row["emerging_fit"],
                    "composite": row["composite"],
                    "tier": row["tier"],
                    "sector_confidence": row["score"]["sector_fit"]["confidence"],
                    "halo_confidence": row["score"]["halo_value"]["confidence"],
                    "emerging_confidence": row["score"]["emerging_fit"]["confidence"],
                    "insufficient_evidence_dimensions": _csv_text("; ".join(insufficient_dimensions), fallback="None"),
                    "check_size_estimate": _csv_text(row["score"].get("check_size_estimate"), fallback="Unknown"),
                    "validation_flags": _csv_text("; ".join(row["validation_flags"]), fallback="None"),
                    **run_cost_fields,
                }
            )
        _write_csv_rows(destination, flat_rows)

    def export_run_summary_csv(self, run_id: str, destination: Path) -> None:
        summary = self.fetch_run_summary(run_id)
        row = {
            "run_id": summary["run_id"],
            "prospect_count": summary["prospect_count"],
            "org_count": summary["org_count"],
            "avg_composite": summary["avg_composite"],
            "flagged_count": summary["flagged_count"],
            "priority_close_count": summary["tier_counts"].get("PRIORITY CLOSE", 0),
            "strong_fit_count": summary["tier_counts"].get("STRONG FIT", 0),
            "moderate_fit_count": summary["tier_counts"].get("MODERATE FIT", 0),
            "weak_fit_count": summary["tier_counts"].get("WEAK FIT", 0),
            **_summary_cost_fields(summary),
        }
        _write_csv_rows(destination, [row])

    def export_run_cost_breakdown_csv(self, run_id: str, destination: Path) -> None:
        summary = self.fetch_run_summary(run_id)
        cost = summary.get("cost", {})
        rows = []
        for operation_name, payload in sorted(cost.get("operation_breakdown", {}).items()):
            rows.append(
                {
                    "run_id": run_id,
                    "operation": operation_name,
                    "vendor": payload.get("vendor", "unknown"),
                    "model": payload.get("model", "unknown"),
                    "requests": payload.get("requests", 0),
                    "prompt_tokens": payload.get("prompt_tokens", 0),
                    "search_content_input_tokens": payload.get("search_content_input_tokens", 0),
                    "tool_calls": payload.get("tool_calls", 0),
                    "completion_tokens": payload.get("completion_tokens", 0),
                    "cost_usd": payload.get("cost_usd", 0.0),
                    "avg_prompt_tokens": payload.get("avg_prompt_tokens", 0),
                    "avg_completion_tokens": payload.get("avg_completion_tokens", 0),
                    "avg_search_content_input_tokens": payload.get("avg_search_content_input_tokens", 0),
                    "avg_tool_calls": payload.get("avg_tool_calls", 0),
                    "cached_input_supported": payload.get("cached_input_supported", False),
                }
            )
        if rows:
            _write_csv_rows(destination, rows)

    def export_run_cost_projections_csv(self, run_id: str, destination: Path) -> None:
        summary = self.fetch_run_summary(run_id)
        cost = summary.get("cost", {})
        rows = []
        for projection in cost.get("projections", []):
            rows.append(
                {
                    "run_id": run_id,
                    "target_contacts": projection.get("target_contacts", 0),
                    "estimated_organizations": projection.get("estimated_organizations", 0),
                    "cold_start_cost_usd": projection.get("cold_start_cost_usd", 0.0),
                    "provider_cache_cost_usd": projection.get("provider_cache_cost_usd", 0.0),
                    "app_cache_cost_usd": projection.get("app_cache_cost_usd", 0.0),
                    "provider_cache_savings_usd": projection.get("provider_cache_savings_usd", 0.0),
                    "app_cache_savings_usd": projection.get("app_cache_savings_usd", 0.0),
                }
            )
        if rows:
            _write_csv_rows(destination, rows)

    def export_run_html(self, run_id: str, destination: Path) -> None:
        rows = self.fetch_run_rows(run_id)
        if not rows:
            return
        summary = self.fetch_run_summary(run_id)
        flagged_rows = [row for row in rows if row["validation_flags"]]
        methodology = _extract_methodology(rows)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(
            self._build_html(summary, rows[:25], flagged_rows[:25], methodology),
            encoding="utf-8",
        )

    def _connect(self) -> sqlite3.Connection:
        if not self.database_path.exists():
            raise sqlite3.OperationalError(f"Database file not found: {self.database_path}")
        connection = sqlite3.connect(self.database_path, timeout=30.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout = 30000")
        return connection

    def _build_html(
        self,
        summary: dict[str, Any],
        top_rows: list[dict[str, Any]],
        flagged_rows: list[dict[str, Any]],
        methodology: dict[str, Any],
    ) -> str:
        # Keep the report static and dependency-free so it is easy to share.
        cards = "".join(
            [
                _summary_card("Prospects", str(summary["prospect_count"])),
                _summary_card("Organizations", str(summary["org_count"])),
                _summary_card("Avg Composite", f"{summary['avg_composite']:.2f}"),
                _summary_card("Flagged", str(summary["flagged_count"])),
                _summary_card("Estimated API Cost", f"${summary['cost'].get('total_cost_usd', 0):.4f}"),
                _summary_card("Cost / Contact", f"${summary['cost'].get('effective_cost_per_contact_usd', 0):.4f}"),
                _summary_card("Avoided Cost", f"${summary['cost'].get('avoided_cost_usd', 0):.4f}"),
            ]
        )
        tier_list = "".join(
            f"<li><strong>{escape(tier)}</strong>: {count}</li>"
            for tier, count in sorted(summary["tier_counts"].items())
        )
        operation_table = _cost_operation_table(summary["cost"].get("operation_breakdown", {}))
        projection_table = _cost_projection_table(summary["cost"].get("projections", []))
        methodology_html = _methodology_section(methodology)
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
    <h2>Cost Breakdown</h2>
    {operation_table}
  </div>
  <div class="section">
    <h2>Scaling Projection</h2>
    {projection_table}
  </div>
  <div class="section">
    <h2>Research Method</h2>
    {methodology_html}
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
    headers = [
        "Organization",
        "Contact",
        "Tier",
        "Composite",
        "Sector",
        "Halo",
        "Emerging",
        "Confidence",
        "Evidence Gaps",
        "Check Size",
    ]
    if include_flags:
        headers.append("Flags")
    header_html = "".join(f"<th>{escape(header)}</th>" for header in headers)
    body_parts: list[str] = []
    for row in rows:
        insufficient_dimensions = row["score"].get("metadata", {}).get("insufficient_evidence_dimensions", [])
        confidence_summary = "/".join(
            [
                row["score"]["sector_fit"]["confidence"],
                row["score"]["halo_value"]["confidence"],
                row["score"]["emerging_fit"]["confidence"],
            ]
        )
        columns = [
            escape(row["organization"]),
            escape(row["contact_name"]),
            escape(row["tier"]),
            f"{row['composite']:.2f}",
            f"{row['sector_fit']:.2f}",
            f"{row['halo_value']:.2f}",
            f"{row['emerging_fit']:.2f}",
            escape(confidence_summary),
            escape(", ".join(insufficient_dimensions) or "None"),
            escape(str(row["score"].get("check_size_estimate") or "Unknown")),
        ]
        if include_flags:
            columns.append(
                '<div class="flags">' + escape("; ".join(row["validation_flags"]) or "None") + "</div>"
            )
        body_parts.append("<tr>" + "".join(f"<td>{column}</td>" for column in columns) + "</tr>")
    return f"<table><thead><tr>{header_html}</tr></thead><tbody>{''.join(body_parts)}</tbody></table>"


def _cost_operation_table(operation_breakdown: dict[str, Any]) -> str:
    if not operation_breakdown:
        return "<p>No cost data available.</p>"
    headers = ["Operation", "Model", "Calls", "Prompt Tokens", "Search Tokens", "Tool Calls", "Completion Tokens", "Cost (USD)"]
    header_html = "".join(f"<th>{escape(header)}</th>" for header in headers)
    body_parts: list[str] = []
    for operation_name, payload in sorted(operation_breakdown.items()):
        columns = [
            escape(operation_name),
            escape(str(payload.get("model", "unknown"))),
            str(payload.get("requests", 0)),
            str(payload.get("prompt_tokens", 0)),
            str(payload.get("search_content_input_tokens", 0)),
            str(payload.get("tool_calls", 0)),
            str(payload.get("completion_tokens", 0)),
            f"{float(payload.get('cost_usd', 0)):.4f}",
        ]
        body_parts.append("<tr>" + "".join(f"<td>{column}</td>" for column in columns) + "</tr>")
    return f"<table><thead><tr>{header_html}</tr></thead><tbody>{''.join(body_parts)}</tbody></table>"


def _cost_projection_table(projections: list[dict[str, Any]]) -> str:
    if not projections:
        return "<p>No projections available.</p>"
    headers = [
        "Target Contacts",
        "Estimated Orgs",
        "Cold Start (USD)",
        "Provider Cache (USD)",
        "App Cache (USD)",
        "Provider Savings (USD)",
        "App Savings (USD)",
    ]
    header_html = "".join(f"<th>{escape(header)}</th>" for header in headers)
    body_parts: list[str] = []
    for row in projections:
        columns = [
            str(row.get("target_contacts", 0)),
            str(row.get("estimated_organizations", 0)),
            f"{float(row.get('cold_start_cost_usd', 0)):.4f}",
            f"{float(row.get('provider_cache_cost_usd', 0)):.4f}",
            f"{float(row.get('app_cache_cost_usd', 0)):.4f}",
            f"{float(row.get('provider_cache_savings_usd', 0)):.4f}",
            f"{float(row.get('app_cache_savings_usd', 0)):.4f}",
        ]
        body_parts.append("<tr>" + "".join(f"<td>{column}</td>" for column in columns) + "</tr>")
    return f"<table><thead><tr>{header_html}</tr></thead><tbody>{''.join(body_parts)}</tbody></table>"


def _extract_methodology(rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not rows:
        return {}
    enrichment = rows[0].get("enrichment", {})
    raw_payload = enrichment.get("raw_payload", {})
    return {
        "research_methodology": raw_payload.get("research_methodology", []),
        "source_policy": raw_payload.get("source_policy", {}),
    }


def _methodology_section(methodology: dict[str, Any]) -> str:
    steps = methodology.get("research_methodology", [])
    source_policy = methodology.get("source_policy", {})
    if not steps and not source_policy:
        return "<p>No methodology recorded.</p>"
    step_list = "".join(f"<li>{escape(str(step))}</li>" for step in steps)
    blocked = ", ".join(source_policy.get("blocked_source_patterns", []))
    corroboration = source_policy.get("minimum_corroborating_sources", "Unknown")
    tiers = source_policy.get("trusted_source_tiers", {})
    tier_list = "".join(
        f"<li><strong>{escape(str(tier))}</strong>: {escape(', '.join(values))}</li>"
        for tier, values in tiers.items()
    )
    return (
        f"<p><strong>Minimum corroboration:</strong> {escape(str(corroboration))} trusted sources for material claims.</p>"
        f"<p><strong>Blocked/noisy sources:</strong> {escape(blocked or 'None recorded')}</p>"
        f"<h3>Method Steps</h3><ul>{step_list}</ul>"
        f"<h3>Trusted Source Tiers</h3><ul>{tier_list}</ul>"
    )


def _csv_text(value: Any, *, fallback: str) -> str:
    text = str(value).strip() if value is not None else ""
    return text or fallback


def _write_csv_rows(destination: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def _summary_cost_fields(summary: dict[str, Any]) -> dict[str, Any]:
    cost = summary.get("cost", {})
    operation_breakdown = cost.get("operation_breakdown", {})
    enrichment_cost = operation_breakdown.get("enrichment", {}).get("cost_usd", 0.0)
    scoring_cost = operation_breakdown.get("scoring", {}).get("cost_usd", 0.0)
    return {
        "run_total_cost_usd": cost.get("total_cost_usd", 0.0),
        "run_total_requests": cost.get("total_requests", 0),
        "run_total_operation_calls": cost.get("total_operation_calls", cost.get("total_requests", 0)),
        "run_total_api_requests": cost.get("total_api_requests", 0),
        "run_total_local_calls": cost.get("total_local_calls", 0),
        "run_total_tool_calls": cost.get("total_tool_calls", 0),
        "run_effective_cost_per_contact_usd": cost.get("effective_cost_per_contact_usd", 0.0),
        "run_effective_cost_per_organization_usd": cost.get("effective_cost_per_organization_usd", 0.0),
        "run_cache_hit_rate": cost.get("cache_hit_rate", 0.0),
        "run_avoided_cost_usd": cost.get("avoided_cost_usd", 0.0),
        "run_total_rate_limit_wait_seconds": cost.get("total_rate_limit_wait_seconds", 0.0),
        "run_enrichment_cost_usd": enrichment_cost,
        "run_scoring_cost_usd": scoring_cost,
    }


def _source_quality_fields(enrichment: dict[str, Any]) -> dict[str, int | bool]:
    raw_payload = enrichment.get("raw_payload", {})
    source_quality = raw_payload.get("source_quality", {})
    if not isinstance(source_quality, dict):
        source_quality = {}
    return {
        "trusted_source_count": int(source_quality.get("trusted_source_count", 0) or 0),
        "blocked_source_count": int(source_quality.get("blocked_source_count", 0) or 0),
        "minimum_corroboration_met": bool(source_quality.get("minimum_corroboration_met", False)),
        "manual_review_required": bool(source_quality.get("needs_manual_review", False)),
    }
