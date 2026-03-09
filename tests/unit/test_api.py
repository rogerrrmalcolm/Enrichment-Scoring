from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest
import uuid

from config.settings import AppSettings
from src.api import _api_key_is_valid, _resolve_report_path, _validate_run_id, create_app


class ApiModuleTests(unittest.TestCase):
    def test_create_app_requires_fastapi_runtime(self) -> None:
        if importlib.util.find_spec("fastapi") is not None:
            self.assertIsNotNone(create_app())
            return

        with self.assertRaises(RuntimeError):
            create_app()

    def test_validate_run_id_rejects_path_traversal(self) -> None:
        with self.assertRaises(ValueError):
            _validate_run_id("../latest_run")

    def test_validate_run_id_accepts_expected_format(self) -> None:
        self.assertEqual(_validate_run_id("20260309T200706Z"), "20260309T200706Z")

    def test_resolve_report_path_stays_inside_export_directory(self) -> None:
        root = self._sandbox_root()
        settings = AppSettings.from_root(root)
        settings.export_dir.mkdir(parents=True, exist_ok=True)
        safe_path = settings.report_path("20260309T200706Z")
        resolved = _resolve_report_path("20260309T200706Z", None, settings)
        self.assertEqual(resolved, safe_path.resolve(strict=False))

    def test_resolve_report_path_rejects_escape_attempts(self) -> None:
        root = self._sandbox_root()
        settings = AppSettings.from_root(root)
        manifest = {"artifacts": {"html_report": str(root.parent / "escape.html")}}
        with self.assertRaises(ValueError):
            _resolve_report_path("20260309T200706Z", manifest, settings)

    def test_api_key_helper_allows_public_mode(self) -> None:
        self.assertTrue(_api_key_is_valid(None, None))

    def test_api_key_helper_requires_exact_match_when_configured(self) -> None:
        self.assertFalse(_api_key_is_valid(None, "secret"))
        self.assertFalse(_api_key_is_valid("wrong", "secret"))
        self.assertTrue(_api_key_is_valid("secret", "secret"))

    def _sandbox_root(self) -> Path:
        root = Path.cwd() / "tests" / "tmp" / f"api_fixture_{uuid.uuid4().hex}"
        root.mkdir(parents=True, exist_ok=True)
        return root


if __name__ == "__main__":
    unittest.main()
