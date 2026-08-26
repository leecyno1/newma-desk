#!/usr/bin/env bash
set -euo pipefail

BACKEND_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ROOT_DIR="$(cd "$BACKEND_DIR/.." && pwd)"
HOST="${HOST:-127.0.0.1}"
PORT="${PORT:-8005}"

check_python() {
  local python_bin="$1"
  "$python_bin" - <<'PY' >/dev/null 2>&1
required = [
    "fastapi",
    "uvicorn",
    "sqlalchemy",
    "psycopg2",
    "pymongo",
    "tushare",
]
for module in required:
    __import__(module)
PY
}

add_candidate() {
  local candidate="$1"
  if [[ -n "$candidate" && -x "$candidate" ]]; then
    PYTHON_CANDIDATES+=("$candidate")
  fi
}

PYTHON_CANDIDATES=()
add_candidate "${BACKEND_PYTHON:-}"
add_candidate "$ROOT_DIR/.venv/bin/python"
add_candidate "/usr/local/bin/python3"
add_candidate "/opt/homebrew/bin/python3"
add_candidate "$(command -v python3 || true)"

selected_python=""
for python_bin in "${PYTHON_CANDIDATES[@]}"; do
  if [[ " ${CHECKED_PYTHONS:-} " == *" $python_bin "* ]]; then
    continue
  fi
  CHECKED_PYTHONS="${CHECKED_PYTHONS:-} $python_bin"

  if check_python "$python_bin"; then
    selected_python="$python_bin"
    break
  fi
done

if [[ -z "$selected_python" ]]; then
  cat >&2 <<'EOF'
No Python interpreter with the required backend imports was found.
Required imports: fastapi, uvicorn, sqlalchemy, psycopg2, pymongo, tushare

Set BACKEND_PYTHON=/path/to/python or install backend/requirements.txt into your active Python.
EOF
  exit 1
fi

if [[ "${1:-}" == "--check" ]]; then
  echo "Selected Python: $selected_python"
  echo "Required imports: OK"
  exit 0
fi

cd "$BACKEND_DIR"
exec "$selected_python" -m uvicorn main:app --host "$HOST" --port "$PORT" "$@"
