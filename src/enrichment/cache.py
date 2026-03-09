from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from src.models.entities import EnrichmentRecord, Evidence


class EnrichmentCache:
    def __init__(self, cache_path: Path) -> None:
        self.cache_path = cache_path
        self._records = self._load()

    def get(self, organization_key: str) -> EnrichmentRecord | None:
        payload = self._records.get(organization_key)
        if payload is None:
            return None
        return _enrichment_from_dict(payload)

    def set(self, organization_key: str, record: EnrichmentRecord) -> None:
        self._records[organization_key] = asdict(record)

    def save(self) -> None:
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        self.cache_path.write_text(json.dumps(self._records, indent=2), encoding="utf-8")

    def _load(self) -> dict[str, dict[str, object]]:
        if not self.cache_path.exists():
            return {}
        return json.loads(self.cache_path.read_text(encoding="utf-8"))


def _enrichment_from_dict(payload: dict[str, object]) -> EnrichmentRecord:
    return EnrichmentRecord(
        organization=str(payload["organization"]),
        canonical_org_name=str(payload["canonical_org_name"]),
        organization_type=str(payload["organization_type"]),
        allocator_profile=str(payload["allocator_profile"]),
        external_allocations=_evidence_from_dict(payload["external_allocations"]),
        sustainability_mandate=_evidence_from_dict(payload["sustainability_mandate"]),
        aum=payload.get("aum"),
        brand_signal=_evidence_from_dict(payload["brand_signal"]),
        emerging_manager_program=_evidence_from_dict(payload["emerging_manager_program"]),
        notes=list(payload.get("notes", [])),
        raw_payload=dict(payload.get("raw_payload", {})),
    )


def _evidence_from_dict(payload: object) -> Evidence:
    if not isinstance(payload, dict):
        return Evidence(summary="No evidence collected yet.")
    return Evidence(
        summary=str(payload.get("summary", "No evidence collected yet.")),
        sources=[str(source) for source in payload.get("sources", [])],
    )
