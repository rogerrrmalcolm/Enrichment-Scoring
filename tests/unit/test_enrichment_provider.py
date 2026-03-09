from __future__ import annotations

import json
import unittest
from pathlib import Path

from src.enrichment.provider import HEURISTIC_ENRICHMENT_MODE, LIVE_ENRICHMENT_MODE, StarterEnrichmentProvider
from src.models.entities import ContactRecord, EnrichmentRecord
from src.utils.prompts import PromptLibrary


class _StubLiveProvider(StarterEnrichmentProvider):
    def __init__(self, response_payload: dict[str, object]) -> None:
        super().__init__(
            PromptLibrary(Path.cwd() / "prompts"),
            enable_live_enrichment=True,
            openai_api_key="test-key",
        )
        self._response_payload = response_payload

    def _request_live_response(self, request_payload: dict[str, object]) -> dict[str, object]:
        return self._response_payload


class StarterEnrichmentProviderTests(unittest.TestCase):
    def test_disabled_live_enrichment_stays_on_heuristic_path(self) -> None:
        provider = StarterEnrichmentProvider(PromptLibrary(Path.cwd() / "prompts"))
        record = provider.enrich(
            "quiet foundation",
            [
                ContactRecord(
                    contact_name="Test Contact",
                    organization="Quiet Foundation",
                    org_type="Foundation",
                    role="Director of Investments",
                    email=None,
                    region="NYC",
                    contact_status="New Contact",
                    relationship_depth=5,
                )
            ],
        )

        self.assertEqual(record.raw_payload["enrichment_mode"], HEURISTIC_ENRICHMENT_MODE)
        self.assertEqual(record.raw_payload["estimated_tool_calls"], 0)

    def test_live_enrichment_uses_citations_and_marks_mode(self) -> None:
        structured = {
            "organization_type": "Foundation",
            "allocator_profile": "Institutional LP allocator with evidence of external-manager selection.",
            "external_allocations": {
                "summary": "The investment office discloses allocations to external private credit and direct lending managers.",
                "confidence": "high",
                "sufficient_evidence": True,
                "citations": [
                    "https://www.examplefoundation.org/investments",
                    "https://www.examplefoundation.org/annual-report.pdf",
                ],
            },
            "sustainability_mandate": {
                "summary": "The foundation states that climate and impact are part of its investment policy.",
                "confidence": "medium",
                "sufficient_evidence": True,
                "citations": ["https://www.examplefoundation.org/investments"],
            },
            "aum": {
                "value": "$3.2B",
                "summary": "The annual report lists the investment pool at $3.2B.",
                "confidence": "high",
                "sufficient_evidence": True,
                "citations": ["https://www.examplefoundation.org/annual-report.pdf"],
            },
            "brand_signal": {
                "summary": "The institution has meaningful public recognition in allocator circles.",
                "confidence": "medium",
                "sufficient_evidence": True,
                "citations": ["https://www.examplefoundation.org/about"],
            },
            "emerging_manager_program": {
                "summary": "Insufficient public evidence of a formal emerging manager program.",
                "confidence": "low",
                "sufficient_evidence": False,
                "citations": [],
            },
            "notes": ["Allocator status supported by primary organization materials."],
            "source_quality": {
                "gaps": ["No formal emerging manager program was found."],
                "corroborated_claims": ["allocator status", "AUM"],
                "needs_manual_review": False,
            },
        }
        response_payload = {
            "output": [
                {
                    "type": "web_search_call",
                    "action": {
                        "sources": [
                            {"url": "https://www.examplefoundation.org/investments"},
                            {"url": "https://www.examplefoundation.org/annual-report.pdf"},
                        ]
                    },
                },
                {
                    "type": "message",
                    "content": [
                        {
                            "type": "output_text",
                            "text": json.dumps(structured),
                            "annotations": [
                                {"type": "url_citation", "url": "https://www.examplefoundation.org/about"}
                            ],
                        }
                    ],
                },
            ]
        }
        provider = _StubLiveProvider(response_payload)

        record = provider.enrich(
            "example foundation",
            [
                ContactRecord(
                    contact_name="Test Contact",
                    organization="Example Foundation",
                    org_type="Foundation",
                    role="Director of Investments",
                    email=None,
                    region="NYC",
                    contact_status="New Contact",
                    relationship_depth=5,
                )
            ],
        )

        self.assertEqual(record.raw_payload["enrichment_mode"], LIVE_ENRICHMENT_MODE)
        self.assertEqual(record.raw_payload["estimated_tool_calls"], 1)
        self.assertEqual(record.aum, "$3.2B")
        self.assertIn("https://www.examplefoundation.org/investments", record.external_allocations.sources)
        self.assertIn("Insufficient public evidence", record.emerging_manager_program.summary)
        self.assertTrue(provider.should_refresh_cached_record(EnrichmentRecord(
            organization="Example Foundation",
            canonical_org_name="example foundation",
            organization_type="Foundation",
            allocator_profile="Likely LP allocator profile based on organization type.",
            raw_payload={"enrichment_mode": HEURISTIC_ENRICHMENT_MODE},
        )))


if __name__ == "__main__":
    unittest.main()
