from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass
import json
import re
from typing import Protocol, Sequence
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from src.models.entities import ContactRecord, EnrichmentRecord, Evidence
from src.utils.prompts import PromptLibrary


ALLOCATOR_ORG_TYPES = {
    "single family office",
    "multi-family office",
    "fund of funds",
    "foundation",
    "endowment",
    "pension",
    "insurance",
    "hnwi",
}

SERVICE_PROVIDER_TYPES = {
    "asset manager",
    "ria/fia",
    "private capital firm",
}

CALIBRATION_RESEARCH_PROFILES = {
    "the rockefeller foundation": {
        "aum": "$6.4B",
        "allocator": "Challenge anchor indicates the foundation allocates across hedge funds, PE, real estate, senior debt, and direct lending funds.",
        "sustainability": "Challenge anchor explicitly links the foundation to climate and sustainability programs.",
        "brand": "Challenge anchor marks Rockefeller as a globally recognized institution with strong signaling value.",
        "emerging": "Challenge anchor references multiple emerging manager commitments.",
    },
    "pbucc": {
        "aum": "$2.0B",
        "allocator": "Challenge anchor identifies PBUCC as an institutional LP with responsible investing orientation.",
        "sustainability": "Challenge anchor ties PBUCC to faith-based responsible investing and ICCR membership.",
        "brand": "Challenge anchor notes strong recognition in impact-investing circles.",
        "emerging": "Challenge anchor documents openness to emerging managers.",
    },
    "pension boards united church of christ": {
        "aum": "$2.0B",
        "allocator": "Challenge anchor identifies PBUCC as an institutional LP with responsible investing orientation.",
        "sustainability": "Challenge anchor ties PBUCC to faith-based responsible investing and ICCR membership.",
        "brand": "Challenge anchor notes strong recognition in impact-investing circles.",
        "emerging": "Challenge anchor documents openness to emerging managers.",
    },
    "inherent group": {
        "aum": None,
        "allocator": "Challenge anchor treats Inherent Group as a single-family office that likely allocates externally, but public evidence is limited.",
        "sustainability": "Challenge anchor references internal ESG strategies rather than a clearly documented external-manager mandate.",
        "brand": "Challenge anchor indicates limited public visibility despite allocator potential.",
        "emerging": "Challenge anchor suggests structural openness as a single-family office, but no explicit emerging-manager program.",
    },
    "meridian capital group": {
        "aum": None,
        "allocator": "Challenge anchor identifies Meridian Capital Group as a CRE finance, investment-sales, and leasing advisory business rather than an LP allocator.",
        "sustainability": "Challenge anchor does not identify a sustainability allocator mandate for Meridian Capital Group.",
        "brand": "Challenge anchor describes niche market visibility, but not the type of LP halo signal relevant here.",
        "emerging": "Challenge anchor treats Meridian Capital Group as a poor emerging-manager fit because it is not an LP allocator.",
    },
}

ALLOCATOR_ROLE_KEYWORDS = {
    "investment",
    "portfolio",
    "cio",
    "chief investment officer",
    "allocations",
    "alternatives",
    "endowment",
}

SUSTAINABILITY_KEYWORDS = {
    "impact",
    "sustainable",
    "sustainability",
    "climate",
    "esg",
    "regenerative",
    "energy transition",
    "responsible investing",
}

SERVICE_PROVIDER_KEYWORDS = {
    "advisors",
    "advisory",
    "brokerage",
    "consulting",
    "capital group",
    "asset management",
    "wealth management",
    "lending",
}

HEURISTIC_ENRICHMENT_MODE = "heuristic_offline"
LIVE_ENRICHMENT_MODE = "live_openai_web_search"
DEFAULT_OPENAI_BASE_URL = "https://api.openai.com/v1/responses"
DEFAULT_OPENAI_MODEL = "gpt-4.1-mini"
DEFAULT_OPENAI_TIMEOUT_SECONDS = 45.0
AUM_UNAVAILABLE_MARKERS = (
    "unknown",
    "n/a",
    "na",
    "none",
    "not publicly disclosed",
    "not disclosed",
    "not publicly available",
    "unavailable",
    "undisclosed",
)


@dataclass(frozen=True, slots=True)
class SourcePolicy:
    trusted_source_tiers: dict[str, tuple[str, ...]]
    blocked_source_patterns: tuple[str, ...]
    minimum_corroborating_sources: int
    methodology_steps: tuple[str, ...]
    evidence_rules: tuple[str, ...]

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


class EnrichmentProvider(Protocol):
    def enrich(self, organization_key: str, contacts: Sequence[ContactRecord]) -> EnrichmentRecord:
        ...

    def should_refresh_cached_record(self, record: EnrichmentRecord) -> bool:
        ...


class StarterEnrichmentProvider:
    def __init__(
        self,
        prompts: PromptLibrary,
        *,
        enable_live_enrichment: bool = False,
        openai_api_key: str | None = None,
        openai_base_url: str = DEFAULT_OPENAI_BASE_URL,
        openai_model: str = DEFAULT_OPENAI_MODEL,
        timeout_seconds: float = DEFAULT_OPENAI_TIMEOUT_SECONDS,
    ) -> None:
        self.prompts = prompts
        self.source_policy = _default_source_policy()
        self.enable_live_enrichment = enable_live_enrichment
        self.openai_api_key = openai_api_key
        self.openai_base_url = openai_base_url
        self.openai_model = openai_model
        self.timeout_seconds = timeout_seconds

    def enrich(self, organization_key: str, contacts: Sequence[ContactRecord]) -> EnrichmentRecord:
        if self._can_use_live_enrichment():
            try:
                return self._live_enrich(organization_key, contacts)
            except Exception as exc:
                fallback = self._heuristic_enrich(organization_key, contacts)
                fallback.notes.insert(
                    0,
                    f"Live OpenAI web-search enrichment failed and the provider fell back to the offline heuristic path: {exc}",
                )
                fallback.raw_payload["live_error"] = str(exc)
                return fallback
        return self._heuristic_enrich(organization_key, contacts)

    def should_refresh_cached_record(self, record: EnrichmentRecord) -> bool:
        cached_mode = str(record.raw_payload.get("enrichment_mode", ""))
        return self._can_use_live_enrichment() and cached_mode != LIVE_ENRICHMENT_MODE

    def _can_use_live_enrichment(self) -> bool:
        return self.enable_live_enrichment and bool(self.openai_api_key)

    def _heuristic_enrich(self, organization_key: str, contacts: Sequence[ContactRecord]) -> EnrichmentRecord:
        primary = contacts[0]
        org_type = _dominant_org_type(contacts)
        prompt_context = _prompt_context(primary, contacts, self.source_policy)
        signals = _collect_signals(primary.organization, contacts, org_type)
        anchor = CALIBRATION_RESEARCH_PROFILES.get(organization_key)
        notes = [
            "This enrichment pass is heuristic and prompt-backed, but still offline.",
            "Set PACEZERO_ENABLE_LIVE_ENRICHMENT=true with a valid OPENAI_API_KEY to switch to live web-search enrichment.",
            "The live search path is constrained by the same trusted-source policy and corroboration rules stored in this record.",
            "Org type alone is not treated as conclusive proof of external-manager allocation; explicit LP evidence remains the standard.",
        ]
        if anchor:
            notes.append("Calibration anchor matched: challenge benchmark evidence was injected for this organization.")
        return EnrichmentRecord(
            organization=primary.organization,
            canonical_org_name=organization_key,
            organization_type=org_type.title(),
            allocator_profile=_allocator_profile(org_type),
            external_allocations=Evidence(
                summary=_external_allocations_summary(org_type, signals, anchor),
                sources=_sources_for("allocator", signals, anchor),
            ),
            sustainability_mandate=Evidence(
                summary=_sustainability_summary(org_type, signals, anchor),
                sources=_sources_for("sustainability", signals, anchor),
            ),
            aum=_aum_for(anchor),
            brand_signal=Evidence(
                summary=_brand_summary(org_type, primary.region, signals, anchor),
                sources=_sources_for("brand", signals, anchor),
            ),
            emerging_manager_program=Evidence(
                summary=_emerging_manager_summary(org_type, signals, anchor),
                sources=_sources_for("emerging", signals, anchor),
            ),
            notes=notes,
            raw_payload={
                "contact_count": len(contacts),
                "roles": sorted({contact.role for contact in contacts}),
                "regions": sorted({contact.region for contact in contacts}),
                "signals": signals,
                "research_methodology": methodology_summary(),
                "source_policy": self.source_policy.as_dict(),
                "enrichment_mode": HEURISTIC_ENRICHMENT_MODE,
                "estimated_tool_calls": 0,
                "prompt_artifacts": {
                    "system_prompt": self.prompts.load("enrichment/system.txt"),
                    "research_prompt": self.prompts.render("enrichment/organization_research.txt", **prompt_context),
                },
            },
        )

    def _live_enrich(self, organization_key: str, contacts: Sequence[ContactRecord]) -> EnrichmentRecord:
        primary = contacts[0]
        org_type = _dominant_org_type(contacts)
        prompt_context = _prompt_context(primary, contacts, self.source_policy)
        signals = _collect_signals(primary.organization, contacts, org_type)
        system_prompt = self.prompts.load("enrichment/system.txt")
        research_prompt = self.prompts.render("enrichment/organization_research.txt", **prompt_context)
        request_payload = self._build_live_request_payload(system_prompt, research_prompt, primary, contacts)
        response_payload = self._request_live_response(request_payload)
        response_text = _extract_response_text(response_payload)
        structured = _extract_json_object(response_text)
        if not structured:
            raise ValueError("OpenAI response did not contain parseable JSON.")

        response_urls = _extract_response_source_urls(response_payload)
        filtered_response_urls, blocked_response_urls = _partition_urls(response_urls, self.source_policy)
        source_quality = _build_source_quality(structured, filtered_response_urls, blocked_response_urls, self.source_policy)

        fallback = self._heuristic_enrich(organization_key, contacts)
        external_allocations = _evidence_from_live_field(
            structured.get("external_allocations"),
            fallback_summary=fallback.external_allocations.summary,
            fallback_urls=[],
            policy=self.source_policy,
        )
        sustainability_mandate = _evidence_from_live_field(
            structured.get("sustainability_mandate"),
            fallback_summary=fallback.sustainability_mandate.summary,
            fallback_urls=[],
            policy=self.source_policy,
        )
        brand_signal = _evidence_from_live_field(
            structured.get("brand_signal"),
            fallback_summary=fallback.brand_signal.summary,
            fallback_urls=[],
            policy=self.source_policy,
        )
        emerging_manager_program = _evidence_from_live_field(
            structured.get("emerging_manager_program"),
            fallback_summary=fallback.emerging_manager_program.summary,
            fallback_urls=[],
            policy=self.source_policy,
        )

        organization_type_value = str(structured.get("organization_type", "")).strip() or org_type.title()
        allocator_profile_value = str(structured.get("allocator_profile", "")).strip() or _allocator_profile(org_type)
        live_aum_value = _parse_aum_value(structured.get("aum"))
        aum_value = live_aum_value
        if aum_value is None and fallback.aum:
            aum_value = fallback.aum
        live_notes = _live_notes(structured, source_quality)
        if aum_value == fallback.aum and fallback.aum and live_aum_value is None:
            live_notes.append(
                "AUM fell back to the challenge calibration anchor because the live search response did not return a usable public value."
            )

        return EnrichmentRecord(
            organization=primary.organization,
            canonical_org_name=organization_key,
            organization_type=organization_type_value,
            allocator_profile=allocator_profile_value,
            external_allocations=external_allocations,
            sustainability_mandate=sustainability_mandate,
            aum=aum_value,
            brand_signal=brand_signal,
            emerging_manager_program=emerging_manager_program,
            notes=live_notes,
            raw_payload={
                "contact_count": len(contacts),
                "roles": sorted({contact.role for contact in contacts}),
                "regions": sorted({contact.region for contact in contacts}),
                "signals": signals,
                "research_methodology": methodology_summary(),
                "source_policy": self.source_policy.as_dict(),
                "enrichment_mode": LIVE_ENRICHMENT_MODE,
                "estimated_tool_calls": 1,
                "source_quality": source_quality,
                "response_sources": filtered_response_urls,
                "blocked_response_sources": blocked_response_urls,
                "structured_research": structured,
                "prompt_artifacts": {
                    "system_prompt": system_prompt,
                    "research_prompt": research_prompt,
                    "model": self.openai_model,
                },
            },
        )

    def _build_live_request_payload(
        self,
        system_prompt: str,
        research_prompt: str,
        primary: ContactRecord,
        contacts: Sequence[ContactRecord],
    ) -> dict[str, object]:
        user_prompt = _live_user_prompt(
            research_prompt=research_prompt,
            organization=primary.organization,
            org_type=primary.org_type,
            roles=sorted({contact.role for contact in contacts}),
            regions=sorted({contact.region for contact in contacts}),
            policy=self.source_policy,
        )
        return {
            "model": self.openai_model,
            "tools": [{"type": "web_search"}],
            "include": ["web_search_call.action.sources"],
            "input": [
                {
                    "role": "system",
                    "content": [{"type": "input_text", "text": system_prompt}],
                },
                {
                    "role": "user",
                    "content": [{"type": "input_text", "text": user_prompt}],
                },
            ],
        }

    def _request_live_response(self, request_payload: dict[str, object]) -> dict[str, object]:
        if not self.openai_api_key:
            raise ValueError("OPENAI_API_KEY is missing.")
        request = Request(
            self.openai_base_url or DEFAULT_OPENAI_BASE_URL,
            data=json.dumps(request_payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.openai_api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                payload = response.read().decode("utf-8")
        except HTTPError as exc:
            payload = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"OpenAI enrichment request failed with HTTP {exc.code}: {payload}") from exc
        except URLError as exc:
            raise RuntimeError(f"OpenAI enrichment request failed: {exc.reason}") from exc
        return json.loads(payload)


def _prompt_context(
    primary: ContactRecord,
    contacts: Sequence[ContactRecord],
    policy: SourcePolicy,
) -> dict[str, object]:
    return {
        "organization": primary.organization,
        "org_type": primary.org_type,
        "regions": ", ".join(sorted({contact.region for contact in contacts})),
        "roles": ", ".join(sorted({contact.role for contact in contacts})),
        "contact_count": len(contacts),
        "trusted_sources": _format_trusted_sources(policy),
        "blocked_sources": ", ".join(policy.blocked_source_patterns),
        "minimum_corroboration": policy.minimum_corroborating_sources,
    }


def _live_user_prompt(
    *,
    research_prompt: str,
    organization: str,
    org_type: str,
    roles: Sequence[str],
    regions: Sequence[str],
    policy: SourcePolicy,
) -> str:
    return (
        f"{research_prompt}\n\n"
        "Use the web_search tool and rely on trusted public sources only.\n"
        "Prefer official organization pages, annual reports, audited financial statements, board materials, filings, and other institutional sources.\n"
        "Ignore social media, lead-generation pages, SEO directories, generic blogs, sponsored content, and unattributed commentary.\n"
        "If a dimension lacks enough trusted public evidence, say that directly and set sufficient_evidence to false instead of guessing.\n"
        f"Minimum corroboration threshold: {policy.minimum_corroborating_sources} trusted sources unless a primary filing directly establishes the fact.\n"
        f"Observed organization: {organization}\n"
        f"Observed CRM org type: {org_type}\n"
        f"Observed roles: {', '.join(roles)}\n"
        f"Observed regions: {', '.join(regions)}\n\n"
        "Return JSON only. Do not wrap it in markdown. Use this exact shape:\n"
        "{\n"
        '  "organization_type": "string",\n'
        '  "allocator_profile": "string",\n'
        '  "external_allocations": {"summary": "string", "confidence": "low|medium|high", "sufficient_evidence": true, "citations": ["https://..."]},\n'
        '  "sustainability_mandate": {"summary": "string", "confidence": "low|medium|high", "sufficient_evidence": true, "citations": ["https://..."]},\n'
        '  "aum": {"value": "string or null", "summary": "string", "confidence": "low|medium|high", "sufficient_evidence": true, "citations": ["https://..."]},\n'
        '  "brand_signal": {"summary": "string", "confidence": "low|medium|high", "sufficient_evidence": true, "citations": ["https://..."]},\n'
        '  "emerging_manager_program": {"summary": "string", "confidence": "low|medium|high", "sufficient_evidence": true, "citations": ["https://..."]},\n'
        '  "notes": ["string"],\n'
        '  "source_quality": {"gaps": ["string"], "corroborated_claims": ["string"], "needs_manual_review": true}\n'
        "}\n"
        "Citations must be the exact URLs you relied on.\n"
        "Do not claim allocator status from org type alone. Separate mission language from investable mandate language.\n"
        "Be explicit about whether the organization is an LP allocator, a GP, a lender, an advisor, or a mixed case."
    )


def _dominant_org_type(contacts: Sequence[ContactRecord]) -> str:
    counts = Counter(contact.org_type.strip().lower() for contact in contacts)
    return counts.most_common(1)[0][0]


def _allocator_profile(org_type: str) -> str:
    if org_type in ALLOCATOR_ORG_TYPES:
        return "Likely LP allocator profile based on organization type."
    if org_type in SERVICE_PROVIDER_TYPES:
        return "Likely GP, advisor, or service-provider profile pending deeper web validation."
    return "Mixed signal profile that needs targeted web research."


def _external_allocations_summary(
    org_type: str,
    signals: dict[str, list[str]],
    anchor: dict[str, str] | None,
) -> str:
    if anchor:
        return anchor["allocator"]
    if org_type in {"foundation", "endowment", "pension", "insurance", "fund of funds"}:
        return "Org type suggests an investment office that may allocate to external managers, but explicit public evidence of private credit or direct-lending fund allocations is still required."
    if signals["allocator"]:
        return f"Allocator-like signals detected: {', '.join(signals['allocator'][:3])}."
    if org_type in {"single family office", "multi-family office", "hnwi"}:
        return "Family-capital profile may allocate externally, but public evidence is often thin and should not be overstated."
    if org_type in SERVICE_PROVIDER_TYPES:
        return "Current signal suggests the organization may manage or advise capital rather than allocate to outside funds."
    return "No external allocation signal captured yet."


def _sustainability_summary(
    org_type: str,
    signals: dict[str, list[str]],
    anchor: dict[str, str] | None,
) -> str:
    if anchor:
        return anchor["sustainability"]
    if signals["sustainability"]:
        return f"Sustainability-oriented signals detected: {', '.join(signals['sustainability'][:3])}."
    if org_type in {"foundation", "endowment", "pension"}:
        return "Institutional allocator type can support impact or climate mandates, but investment-policy evidence is still needed."
    if org_type in {"single family office", "multi-family office"}:
        return "Private wealth allocator may have ESG preferences, but public documentation varies widely."
    return "Sustainability mandate unknown without live research."


def _brand_summary(
    org_type: str,
    region: str,
    signals: dict[str, list[str]],
    anchor: dict[str, str] | None,
) -> str:
    if anchor:
        return anchor["brand"]
    if signals["brand"]:
        return f"Brand signals suggest institutional visibility: {', '.join(signals['brand'][:3])}."
    if org_type in {"foundation", "endowment", "pension"}:
        return f"Institutional allocator in {region} may carry signaling value, but organization-specific recognition evidence is still needed."
    if org_type in {"single family office", "hnwi"}:
        return "Private allocator may be influential but less visible to the broader LP market."
    return "Brand signal unknown pending organization-specific evidence."


def _emerging_manager_summary(
    org_type: str,
    signals: dict[str, list[str]],
    anchor: dict[str, str] | None,
) -> str:
    if anchor:
        return anchor["emerging"]
    if signals["emerging"]:
        return f"Emerging-manager-friendly signals detected: {', '.join(signals['emerging'][:3])}."
    if org_type in {"single family office", "multi-family office", "foundation", "endowment"}:
        return "Org type can be structurally open to emerging managers, but explicit evidence should outweigh type-based inference."
    if org_type in SERVICE_PROVIDER_TYPES:
        return "Emerging manager fit is weak unless the firm also allocates to third-party funds."
    return "Emerging manager appetite unknown without direct evidence."


def _collect_signals(
    organization: str,
    contacts: Sequence[ContactRecord],
    org_type: str,
) -> dict[str, list[str]]:
    signals = {
        "allocator": [],
        "service_provider": [],
        "sustainability": [],
        "brand": [],
        "emerging": [],
    }
    organization_text = organization.lower()
    role_text = " ".join(contact.role.lower() for contact in contacts)
    if org_type in ALLOCATOR_ORG_TYPES:
        signals["allocator"].append(f"org_type:{org_type}")
    if org_type in SERVICE_PROVIDER_TYPES:
        signals["service_provider"].append(f"org_type:{org_type}")
    _append_keyword_hits(organization_text, ALLOCATOR_ROLE_KEYWORDS, signals["allocator"], "role-alignment")
    _append_keyword_hits(role_text, ALLOCATOR_ROLE_KEYWORDS, signals["allocator"], "role")
    _append_keyword_hits(organization_text, SUSTAINABILITY_KEYWORDS, signals["sustainability"], "organization")
    _append_keyword_hits(role_text, SUSTAINABILITY_KEYWORDS, signals["sustainability"], "role")
    _append_keyword_hits(organization_text, SERVICE_PROVIDER_KEYWORDS, signals["service_provider"], "organization")
    if any(token in role_text for token in {"responsible investing", "impact investments", "sustainable investing"}):
        signals["sustainability"].append("role:explicit-sustainability-mandate")
    if any(token in organization_text for token in {"foundation", "endowment", "pension", "trust", "university"}):
        signals["brand"].append("institutional-name-pattern")
    if org_type in {"foundation", "endowment", "pension"}:
        signals["brand"].append(f"org_type:{org_type}")
    if org_type in {"single family office", "multi-family office", "foundation", "endowment"}:
        signals["emerging"].append(f"org_type:{org_type}")
    return signals


def _append_keyword_hits(text: str, keywords: set[str], bucket: list[str], prefix: str) -> None:
    for keyword in sorted(keywords):
        if keyword in text:
            bucket.append(f"{prefix}:{keyword}")


def _sources_for(
    category: str,
    signals: dict[str, list[str]],
    anchor: dict[str, str] | None,
) -> list[str]:
    if anchor:
        return ["challenge_calibration_anchor"]
    if category == "allocator":
        return signals["allocator"][:5]
    if category == "sustainability":
        return signals["sustainability"][:5]
    if category == "brand":
        return signals["brand"][:5]
    if category == "emerging":
        return signals["emerging"][:5]
    return []


def _aum_for(anchor: dict[str, str] | None) -> str | None:
    if anchor is None:
        return None
    return anchor["aum"]


def _format_trusted_sources(policy: SourcePolicy) -> str:
    parts: list[str] = []
    for tier, labels in policy.trusted_source_tiers.items():
        parts.append(f"{tier}: {', '.join(labels)}")
    return " | ".join(parts)


def _default_source_policy() -> SourcePolicy:
    return SourcePolicy(
        trusted_source_tiers={
            "tier_1_primary": (
                "official organization website",
                "annual report",
                "investment policy statement",
                "regulatory filing",
                "foundation or endowment financial statement",
                "public pension board materials",
            ),
            "tier_2_institutional": (
                "university investment office page",
                "SEC or government registry",
                "reputable allocator database",
                "audited financial statement",
                "conference speaker profile published by the organization",
            ),
            "tier_3_reputable_secondary": (
                "major financial press",
                "institutional investor publication",
                "industry association page",
            ),
        },
        blocked_source_patterns=(
            "social media",
            "content farm",
            "generic people-search site",
            "seo directory",
            "unattributed blog",
            "forum post",
            "sponsored content",
            "linkedin.com",
            "facebook.com",
            "instagram.com",
            "x.com",
            "twitter.com",
            "tiktok.com",
            "reddit.com",
            "medium.com",
            "substack.com",
            "blogspot.",
        ),
        minimum_corroborating_sources=2,
        methodology_steps=(
            "Start with primary organization-controlled sources.",
            "Use regulatory or audited documents to confirm allocator status and AUM.",
            "Use reputable secondary coverage only to support, not replace, primary evidence.",
            "Corroborate material claims with at least two trusted sources unless a primary filing or official report already establishes the fact.",
            "Drop weak or contradictory evidence instead of averaging it into the score.",
        ),
        evidence_rules=(
            "Do not cite social posts, content farms, or lead-gen directories.",
            "Treat mission pages separately from investment-office pages for foundations and endowments.",
            "Require explicit external-manager allocation evidence before classifying a mixed organization as an LP.",
            "Mark confidence down when the evidence is thin, outdated, or only indirectly related to investing.",
        ),
    )


def methodology_summary() -> list[str]:
    policy = _default_source_policy()
    return [
        "Prefer primary and regulatory sources over commentary.",
        "Corroborate material claims unless a primary filing or official report already establishes the fact.",
        "Down-rank noisy or marketing-heavy sources.",
        "Separate charitable mission language from investable mandate language.",
        f"Minimum corroboration threshold: {policy.minimum_corroborating_sources} trusted sources.",
    ]


def _extract_response_text(payload: dict[str, object]) -> str:
    direct_text = payload.get("output_text")
    if isinstance(direct_text, str) and direct_text.strip():
        return direct_text.strip()

    chunks: list[str] = []
    for item in payload.get("output", []):
        if not isinstance(item, dict) or item.get("type") != "message":
            continue
        for content in item.get("content", []):
            if not isinstance(content, dict):
                continue
            if content.get("type") in {"output_text", "text"}:
                text = content.get("text")
                if isinstance(text, str) and text.strip():
                    chunks.append(text.strip())
    return "\n".join(chunks).strip()


def _extract_response_source_urls(payload: dict[str, object]) -> list[str]:
    urls: list[str] = []
    for item in payload.get("output", []):
        if not isinstance(item, dict):
            continue
        if item.get("type") == "web_search_call":
            action = item.get("action", {})
            if isinstance(action, dict):
                urls.extend(_urls_from_source_objects(action.get("sources", [])))
        if item.get("type") == "message":
            for content in item.get("content", []):
                if not isinstance(content, dict):
                    continue
                for annotation in content.get("annotations", []):
                    if not isinstance(annotation, dict):
                        continue
                    url = annotation.get("url")
                    if isinstance(url, str) and url.strip():
                        urls.append(url.strip())
    return _dedupe_strings(urls)


def _urls_from_source_objects(raw_sources: object) -> list[str]:
    urls: list[str] = []
    if not isinstance(raw_sources, list):
        return urls
    for source in raw_sources:
        if not isinstance(source, dict):
            continue
        url = source.get("url")
        if isinstance(url, str) and url.strip():
            urls.append(url.strip())
    return urls


def _extract_json_object(text: str) -> dict[str, object] | None:
    stripped = text.strip()
    if not stripped:
        return None
    candidates = [stripped]
    candidates.extend(re.findall(r"```(?:json)?\s*(\{.*?\})\s*```", stripped, flags=re.DOTALL))
    brace_match = re.search(r"\{.*\}", stripped, flags=re.DOTALL)
    if brace_match:
        candidates.append(brace_match.group(0))
    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return parsed
    return None


def _partition_urls(urls: Sequence[str], policy: SourcePolicy) -> tuple[list[str], list[str]]:
    allowed: list[str] = []
    blocked: list[str] = []
    for url in urls:
        normalized = url.strip()
        if not normalized:
            continue
        lowered = normalized.lower()
        if any(pattern in lowered for pattern in policy.blocked_source_patterns):
            blocked.append(normalized)
            continue
        allowed.append(normalized)
    return _dedupe_strings(allowed), _dedupe_strings(blocked)


def _build_source_quality(
    structured: dict[str, object],
    response_urls: list[str],
    blocked_urls: list[str],
    policy: SourcePolicy,
) -> dict[str, object]:
    source_quality = structured.get("source_quality", {})
    gaps = list(source_quality.get("gaps", [])) if isinstance(source_quality, dict) else []
    corroborated_claims = list(source_quality.get("corroborated_claims", [])) if isinstance(source_quality, dict) else []
    needs_manual_review = bool(source_quality.get("needs_manual_review")) if isinstance(source_quality, dict) else False
    return {
        "trusted_source_count": len(response_urls),
        "trusted_domains": sorted({_domain_from_url(url) for url in response_urls if _domain_from_url(url)}),
        "blocked_source_count": len(blocked_urls),
        "blocked_sources": blocked_urls,
        "minimum_corroboration_required": policy.minimum_corroborating_sources,
        "minimum_corroboration_met": len(response_urls) >= policy.minimum_corroborating_sources,
        "gaps": [str(gap) for gap in gaps],
        "corroborated_claims": [str(claim) for claim in corroborated_claims],
        "needs_manual_review": needs_manual_review or len(response_urls) < policy.minimum_corroborating_sources,
    }


def _evidence_from_live_field(
    payload: object,
    *,
    fallback_summary: str,
    fallback_urls: list[str],
    policy: SourcePolicy,
) -> Evidence:
    field = payload if isinstance(payload, dict) else {}
    summary = str(field.get("summary", "")).strip() or fallback_summary
    sufficient_evidence = bool(field.get("sufficient_evidence"))
    citations, _blocked = _partition_urls([str(url) for url in field.get("citations", [])], policy)
    if not citations and fallback_urls:
        citations = list(fallback_urls)
    if not sufficient_evidence or not citations:
        summary = _prefix_insufficient_evidence(summary)
    return Evidence(summary=summary, sources=citations)


def _prefix_insufficient_evidence(summary: str) -> str:
    if not summary:
        return "Insufficient public evidence was found for this dimension."
    if "insufficient public evidence" in summary.lower():
        return summary
    return f"Insufficient public evidence. {summary}"


def _parse_aum_value(payload: object) -> str | None:
    if isinstance(payload, dict):
        value = payload.get("value")
        if value is None:
            return None
        return _normalize_aum_value(str(value))
    if payload is None:
        return None
    return _normalize_aum_value(str(payload))


def _normalize_aum_value(value: str) -> str | None:
    parsed = " ".join(value.strip().split()).rstrip(".")
    if not parsed:
        return None
    lowered = parsed.lower()
    if lowered in AUM_UNAVAILABLE_MARKERS:
        return None
    if any(marker in lowered for marker in ("not publicly disclosed", "not disclosed", "not publicly available")):
        return None
    return parsed


def _live_notes(structured: dict[str, object], source_quality: dict[str, object]) -> list[str]:
    notes = [
        "Live enrichment used the OpenAI Responses API with web_search enabled.",
        "The provider asked the model to rely on primary, regulatory, and institutional sources and to reject noisy sources.",
        "Field-level summaries were kept conservative when citations were missing or the model marked evidence as insufficient.",
    ]
    for note in structured.get("notes", []):
        notes.append(str(note))
    if not bool(source_quality.get("minimum_corroboration_met")):
        notes.append("Minimum corroboration was not met across trusted cited sources; manual review is recommended.")
    if bool(source_quality.get("needs_manual_review")):
        notes.append("Source quality checks still recommend manual review for at least one claim.")
    return notes


def _domain_from_url(url: str) -> str:
    try:
        return urlparse(url).netloc.lower()
    except ValueError:
        return ""


def _dedupe_strings(values: Sequence[str]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        deduped.append(value)
    return deduped
