#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$ROOT_DIR/.venv"
PYTHON_BIN="${PYTHON_BIN:-python3}"
SERVER_HEADLESS="${TICKER_SCOPE_SERVER_HEADLESS:-false}"
REQ_STAMP="$VENV_DIR/.requirements.txt.cksum"

cd "$ROOT_DIR"

if [ ! -x "$VENV_DIR/bin/python" ]; then
  echo "Creating virtual environment..."
  "$PYTHON_BIN" -m venv "$VENV_DIR"
fi

CURRENT_REQ_STAMP="$(cksum requirements.txt)"
if [ ! -f "$REQ_STAMP" ] || [ "$(cat "$REQ_STAMP")" != "$CURRENT_REQ_STAMP" ]; then
  echo "Installing dependencies..."
  "$VENV_DIR/bin/python" -m pip install -r requirements.txt
  echo "$CURRENT_REQ_STAMP" > "$REQ_STAMP"
fi

echo "Starting Ticker Scope..."
STREAMLIT_ARGS=(
  run
  app.py
  --server.headless="$SERVER_HEADLESS"
)

if [ -n "${TICKER_SCOPE_SERVER_PORT:-}" ]; then
  STREAMLIT_ARGS+=(--server.port="$TICKER_SCOPE_SERVER_PORT")
fi

exec "$VENV_DIR/bin/python" -m streamlit "${STREAMLIT_ARGS[@]}"
