#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

set -a
for env_file in .env.local .env backend/.env; do
  if [[ -f "$env_file" ]]; then
    # shellcheck disable=SC1090
    source "$env_file"
  fi
done
set +a

PYTHON_BIN=""
for candidate in "${BACKEND_PYTHON:-}" "$ROOT_DIR/.venv/bin/python" "/opt/anaconda3/bin/python" "/usr/local/bin/python3" "/opt/homebrew/bin/python3" "$(command -v python3 || true)" "$(command -v python || true)"; do
  if [[ -n "$candidate" && -x "$candidate" ]] && "$candidate" - <<'PY' >/dev/null 2>&1
required = ["sqlalchemy", "psycopg2"]
for module in required:
    __import__(module)
PY
  then
    PYTHON_BIN="$candidate"
    break
  fi
done

if [[ -z "$PYTHON_BIN" ]]; then
  echo "未找到带 sqlalchemy/psycopg2 的 Python，请配置 BACKEND_PYTHON。"
  exit 1
fi

"$PYTHON_BIN" backend/scripts/sync_fund_classification_universe.py "$@"
