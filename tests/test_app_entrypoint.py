from __future__ import annotations

import importlib
import unittest


class AppEntrypointTests(unittest.TestCase):
    def test_app_import_exposes_main_without_running_ui(self) -> None:
        app = importlib.import_module("app")

        self.assertTrue(callable(app.main))


if __name__ == "__main__":
    unittest.main()
