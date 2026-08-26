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

if [[ -z "${TUSHARE_TOKEN:-}" ]]; then
  echo "缺少 TUSHARE_TOKEN，请先在 backend/.env 或环境变量中配置。"
  exit 1
fi

PYTHON_BIN=""
for candidate in "${BACKEND_PYTHON:-}" "$ROOT_DIR/.venv/bin/python" "/opt/anaconda3/bin/python" "/usr/local/bin/python3" "/opt/homebrew/bin/python3" "$(command -v python3 || true)" "$(command -v python || true)"; do
  if [[ -n "$candidate" && -x "$candidate" ]] && "$candidate" - <<'PY' >/dev/null 2>&1
required = ["sqlalchemy", "psycopg2", "tushare"]
for module in required:
    __import__(module)
PY
  then
    PYTHON_BIN="$candidate"
    break
  fi
done

if [[ -z "$PYTHON_BIN" ]]; then
  echo "未找到带 sqlalchemy/psycopg2/tushare 的 Python，请配置 BACKEND_PYTHON。"
  exit 1
fi

echo "开始更新 Tushare 全市场基金基础库..."
"$PYTHON_BIN" backend/scripts/sync_tushare_and_generate_reports.py --sync-universe --universe-only "$@"

echo "开始更新高置信度基金分类、份额、同类组和基准映射..."
"$PYTHON_BIN" backend/scripts/sync_fund_classification_universe.py --apply

"$PYTHON_BIN" - <<'PY'
import os
from sqlalchemy import create_engine, text

engine = create_engine(os.environ.get("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/fund_analysis"))
with engine.connect() as conn:
    row = conn.execute(text("""
        SELECT
          COUNT(*) AS total,
          COUNT(*) FILTER (WHERE raw_data->>'source' = 'tushare') AS tushare_total,
          COUNT(*) FILTER (
            WHERE raw_data->>'source' = 'tushare'
              AND NOT (
                name ILIKE '%清算%'
                OR name ILIKE '%终止%'
                OR name ILIKE '%退市%'
                OR COALESCE(raw_data#>>'{info,status}', raw_data#>>'{universe,status}', raw_data->>'status', '') IN ('D', 'DELIST', 'TERMINATED', 'LIQUIDATED')
              )
          ) AS research_universe
        FROM funds
    """)).fetchone()

print(f"更新完成：全库 {row.total} 只，Tushare 来源 {row.tushare_total} 只，存续研究池 {row.research_universe} 只。")
PY
