from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest
import uuid


def _load_run_pipeline_module():
    module_path = Path.cwd() / "scripts" / "run_pipeline.py"
    spec = importlib.util.spec_from_file_location("run_pipeline_script", module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError("Unable to load scripts/run_pipeline.py for testing.")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


run_pipeline_script = _load_run_pipeline_module()


class RunPipelineScriptTests(unittest.TestCase):
    def test_resolve_input_csv_makes_relative_paths_absolute(self) -> None:
        sandbox = self._sandbox_dir()
        resolved = run_pipeline_script._resolve_input_csv(Path("custom_contacts.csv"), sandbox)
        self.assertEqual(resolved, (sandbox / "custom_contacts.csv").resolve(strict=False))

    def test_parse_args_accepts_existing_input_file(self) -> None:
        sandbox = self._sandbox_dir()
        csv_path = sandbox / "custom_contacts.csv"
        csv_path.write_text("Contact Name,Organization,Org Type,Role,Email,Region,Contact Status,Relationship Depth\n", encoding="utf-8")

        args = run_pipeline_script._parse_args(["--input", str(csv_path)])

        self.assertEqual(args.input, csv_path.resolve(strict=False))

    def test_parse_args_rejects_missing_input_file(self) -> None:
        sandbox = self._sandbox_dir()
        missing_path = sandbox / "missing_contacts.csv"

        with self.assertRaises(SystemExit) as exc:
            run_pipeline_script._parse_args(["--input", str(missing_path)])

        self.assertEqual(exc.exception.code, 2)

    def _sandbox_dir(self) -> Path:
        sandbox = Path.cwd() / "tests" / "tmp" / f"run_pipeline_{uuid.uuid4().hex}"
        sandbox.mkdir(parents=True, exist_ok=True)
        return sandbox


if __name__ == "__main__":
    unittest.main()
