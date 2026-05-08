from __future__ import annotations

import os
import sys
from pathlib import Path


APP_NAME = "Ticker Scope"
APP_SLUG = "ticker-scope"
DB_FILENAME = "ticker_scope.sqlite3"


def is_frozen_app() -> bool:
    return bool(getattr(sys, "frozen", False))


def is_standalone_runtime() -> bool:
    return is_frozen_app() or os.getenv("TICKER_SCOPE_STANDALONE") == "1"


def get_user_data_dir() -> Path:
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / APP_NAME

    if sys.platform.startswith("win"):
        base = os.getenv("APPDATA")
        if base:
            return Path(base) / APP_NAME
        return Path.home() / "AppData" / "Roaming" / APP_NAME

    base = os.getenv("XDG_DATA_HOME")
    if base:
        return Path(base) / APP_SLUG
    return Path.home() / ".local" / "share" / APP_SLUG


def get_standalone_db_path() -> Path:
    return get_user_data_dir() / DB_FILENAME


def get_packaged_resource_path(relative_path: str) -> Path:
    if is_frozen_app():
        return Path(sys._MEIPASS) / relative_path  # type: ignore[attr-defined]
    return Path(__file__).resolve().parents[1] / relative_path
