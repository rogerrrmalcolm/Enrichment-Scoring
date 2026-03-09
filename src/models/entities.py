from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class Confidence(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


@dataclass(slots=True)
class ContactRecord:
    contact_name: str
    organization: str
    org_type: str
    role: str
    email: str | None
    region: str
    contact_status: str
    relationship_depth: int


@dataclass(slots=True)
class Evidence:
    summary: str
    sources: list[str] = field(default_factory=list)


@dataclass(slots=True)
class EnrichmentRecord:
    organization: str
    canonical_org_name: str
    organization_type: str
    allocator_profile: str
    external_allocations: Evidence = field(default_factory=lambda: Evidence(summary="No evidence collected yet."))
    sustainability_mandate: Evidence = field(default_factory=lambda: Evidence(summary="No evidence collected yet."))
    aum: str | None = None
    brand_signal: Evidence = field(default_factory=lambda: Evidence(summary="No evidence collected yet."))
    emerging_manager_program: Evidence = field(default_factory=lambda: Evidence(summary="No evidence collected yet."))
    notes: list[str] = field(default_factory=list)
    raw_payload: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ScoreDimension:
    value: float
    confidence: Confidence
    rationale: str
    insufficient_evidence: bool = False


@dataclass(slots=True)
class ProspectScore:
    sector_fit: ScoreDimension
    relationship_depth: ScoreDimension
    halo_value: ScoreDimension
    emerging_fit: ScoreDimension
    composite: float
    tier: str
    check_size_estimate: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ProspectResult:
    contact: ContactRecord
    enrichment: EnrichmentRecord
    score: ProspectScore
    validation_flags: list[str] = field(default_factory=list)
