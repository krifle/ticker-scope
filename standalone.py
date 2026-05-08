from __future__ import annotations

import os
import sys

from streamlit.web import cli as streamlit_cli

import app as _packaged_app  # noqa: F401
from ticker_scope.runtime import get_packaged_resource_path, get_standalone_db_path


def main() -> None:
    os.environ.setdefault("TICKER_SCOPE_STANDALONE", "1")
    os.environ.setdefault("TICKER_SCOPE_DB_PATH", str(get_standalone_db_path()))

    app_path = get_packaged_resource_path("app.py")
    headless = os.getenv("TICKER_SCOPE_SERVER_HEADLESS", "false")
    sys.argv = [
        "streamlit",
        "run",
        str(app_path),
        "--global.developmentMode=false",
        f"--server.headless={headless}",
    ]

    port = os.getenv("TICKER_SCOPE_SERVER_PORT")
    if port:
        sys.argv.append(f"--server.port={port}")

    streamlit_cli.main()


if __name__ == "__main__":
    main()
