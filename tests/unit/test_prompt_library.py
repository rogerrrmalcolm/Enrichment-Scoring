from __future__ import annotations

import unittest
from pathlib import Path

from src.utils.prompts import PromptLibrary


class PromptLibraryTests(unittest.TestCase):
    def test_renders_template_variables(self) -> None:
        prompts = PromptLibrary(Path.cwd() / "prompts")

        rendered = prompts.render(
            "enrichment/organization_research.txt",
            organization="Example Foundation",
            org_type="Foundation",
            regions="NYC",
            roles="Director of Investments",
            contact_count=1,
            trusted_sources="tier_1_primary: official website",
            blocked_sources="social media",
            minimum_corroboration=2,
        )

        self.assertIn("Example Foundation", rendered)
        self.assertIn("Foundation", rendered)


if __name__ == "__main__":
    unittest.main()
