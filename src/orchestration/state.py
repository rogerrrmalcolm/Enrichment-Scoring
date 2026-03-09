from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path


class RunStateStore:
    def __init__(self, state_dir: Path) -> None:
        self.state_dir = state_dir

    def start_run(self, run_id: str, total_contacts: int, total_organizations: int) -> dict[str, object]:
        manifest = {
            "run_id": run_id,
            "status": "running",
            "started_at": datetime.now(timezone.utc).isoformat(),
            "total_contacts": total_contacts,
            "total_organizations": total_organizations,
            "completed_organizations": 0,
            "failed_organizations": [],
            "artifacts": {},
        }
        self._write(run_id, manifest)
        return manifest

    def update_progress(self, run_id: str, manifest: dict[str, object]) -> None:
        self._write(run_id, manifest)

    def complete_run(self, run_id: str, manifest: dict[str, object]) -> None:
        manifest["status"] = "completed"
        manifest["completed_at"] = datetime.now(timezone.utc).isoformat()
        self._write(run_id, manifest)

    def load(self, run_id: str) -> dict[str, object] | None:
        run_path = self.state_dir / f"{run_id}.json"
        if not run_path.exists():
            return None
        return json.loads(run_path.read_text(encoding="utf-8"))

    def load_latest(self) -> dict[str, object] | None:
        latest_path = self.state_dir / "latest_run.json"
        if not latest_path.exists():
            return None
        return json.loads(latest_path.read_text(encoding="utf-8"))

    def _write(self, run_id: str, manifest: dict[str, object]) -> None:
        self.state_dir.mkdir(parents=True, exist_ok=True)
        run_path = self.state_dir / f"{run_id}.json"
        latest_path = self.state_dir / "latest_run.json"
        payload = json.dumps(manifest, indent=2)
        run_path.write_text(payload, encoding="utf-8")
        latest_path.write_text(payload, encoding="utf-8")
