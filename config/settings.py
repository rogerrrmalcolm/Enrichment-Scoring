from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class AppSettings:
    root_dir: Path
    prompt_dir: Path
    input_csv: Path
    database_path: Path
    processed_dir: Path
    export_dir: Path
    state_dir: Path
    log_dir: Path

    @classmethod
    def from_root(cls, root_dir: Path | None = None) -> "AppSettings":
        resolved_root = root_dir or Path(__file__).resolve().parents[1]
        return cls(
            root_dir=resolved_root,
            prompt_dir=resolved_root / "prompts",
            input_csv=resolved_root / "data" / "incoming" / "challenge_contacts.csv",
            database_path=resolved_root / "storage" / "db" / "prospects.sqlite3",
            processed_dir=resolved_root / "data" / "processed",
            export_dir=resolved_root / "data" / "exports",
            state_dir=resolved_root / "storage" / "state",
            log_dir=resolved_root / "storage" / "logs",
        )
