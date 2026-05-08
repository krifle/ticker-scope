from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch
import unittest

from ticker_scope.data.database import DB_PATH, resolve_db_path
from ticker_scope.runtime import get_user_data_dir


class RuntimePathTests(unittest.TestCase):
    def test_default_db_path_uses_project_data_during_development(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(resolve_db_path(), DB_PATH)

    def test_configured_db_path_takes_precedence(self) -> None:
        configured = Path("~/custom-ticker-scope.sqlite3").expanduser()

        with patch.dict(
            os.environ,
            {
                "TICKER_SCOPE_STANDALONE": "1",
                "TICKER_SCOPE_DB_PATH": str(configured),
            },
            clear=True,
        ):
            self.assertEqual(resolve_db_path(), configured)

    def test_linux_standalone_db_path_uses_xdg_data_home(self) -> None:
        data_home = Path("/tmp/ticker-scope-data")

        with patch("ticker_scope.runtime.sys.platform", "linux"), patch.dict(
            os.environ,
            {
                "TICKER_SCOPE_STANDALONE": "1",
                "XDG_DATA_HOME": str(data_home),
            },
            clear=True,
        ):
            self.assertEqual(
                resolve_db_path(),
                data_home / "ticker-scope" / "ticker_scope.sqlite3",
            )

    def test_windows_user_data_path_uses_appdata(self) -> None:
        appdata = Path(r"C:\Users\tester\AppData\Roaming")

        with patch("ticker_scope.runtime.sys.platform", "win32"), patch.dict(
            os.environ,
            {"APPDATA": str(appdata)},
            clear=True,
        ):
            self.assertEqual(get_user_data_dir(), appdata / "Ticker Scope")


if __name__ == "__main__":
    unittest.main()
