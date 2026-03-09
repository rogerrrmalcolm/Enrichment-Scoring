from __future__ import annotations

import importlib.util
import unittest

from src.api import create_app


class ApiModuleTests(unittest.TestCase):
    def test_create_app_requires_fastapi_runtime(self) -> None:
        if importlib.util.find_spec("fastapi") is not None:
            self.assertIsNotNone(create_app())
            return

        with self.assertRaises(RuntimeError):
            create_app()


if __name__ == "__main__":
    unittest.main()
