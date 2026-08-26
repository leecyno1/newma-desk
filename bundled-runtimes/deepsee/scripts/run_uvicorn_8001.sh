#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
ENV_FILE="$ROOT_DIR/.env"
PYBIN="$ROOT_DIR/.venv/bin/python"

cd "$ROOT_DIR"

if [[ -f "$ENV_FILE" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "$ENV_FILE"
  set +a
fi

HOST="${HOST:-127.0.0.1}"
PORT="${PORT:-8001}"

if [[ ! -x "$PYBIN" ]]; then
  PYBIN="$ROOT_DIR/.venv/bin/python3"
fi

if [[ ! -x "$PYBIN" ]]; then
  echo "ERROR: Python executable not found in $ROOT_DIR/.venv/bin" >&2
  exit 1
fi

exec "$PYBIN" -m uvicorn app.main:app --host "$HOST" --port "$PORT"
