from __future__ import annotations

import re
from pathlib import Path


class PromptLibrary:
    def __init__(self, root_dir: Path) -> None:
        self.root_dir = root_dir

    def load(self, relative_path: str) -> str:
        prompt_path = self.root_dir / relative_path
        return prompt_path.read_text(encoding="utf-8").strip()

    def render(self, relative_path: str, **values: object) -> str:
        template = self.load(relative_path)

        def replace(match: re.Match[str]) -> str:
            key = match.group(1)
            if key not in values:
                raise KeyError(f"Missing prompt variable: {key}")
            return str(values[key])

        return re.sub(r"\{\{\s*([a-zA-Z0-9_]+)\s*\}\}", replace, template)
