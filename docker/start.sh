#!/usr/bin/env bash
set -euo pipefail

CODE_DIR="${CODE_DIR:-/app}"
APP_MODULE="${APP_MODULE:-app.main:app}"
HOST="${HOST:-0.0.0.0}"
PORT="${PORT:-8001}"

if [[ ! -f "${CODE_DIR}/app/main.py" ]]; then
    echo "ERROR: project code not found at ${CODE_DIR}."
    exit 1
fi

cd "${CODE_DIR}"
exec python3 -m uvicorn "${APP_MODULE}" --host "${HOST}" --port "${PORT}"
