#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PGDATA_DIR="${PGDATA_DIR:-$ROOT_DIR/.data/postgres}"
PGPORT="${PGPORT:-5432}"
DB_NAME="${DB_NAME:-fund_analysis}"
DB_USER="${DB_USER:-postgres}"
DATABASE_URL="${DATABASE_URL:-postgresql://postgres@localhost:${PGPORT}/${DB_NAME}}"

if ! command -v initdb >/dev/null 2>&1 || ! command -v pg_ctl >/dev/null 2>&1; then
  echo "未找到 initdb/pg_ctl，请先安装 PostgreSQL，或改用 scripts/start-db.sh 启动 Docker 数据库。"
  exit 1
fi

if [[ -d "$PGDATA_DIR" && ! -f "$PGDATA_DIR/PG_VERSION" ]]; then
  BACKUP_DIR="${PGDATA_DIR}.invalid.$(date +%Y%m%d%H%M%S)"
  echo "检测到不完整 PostgreSQL 数据目录，已隔离到：$BACKUP_DIR"
  mv "$PGDATA_DIR" "$BACKUP_DIR"
fi

if [[ ! -d "$PGDATA_DIR" ]]; then
  echo "初始化本地 PostgreSQL 数据目录：$PGDATA_DIR"
  mkdir -p "$(dirname "$PGDATA_DIR")"
  initdb -D "$PGDATA_DIR" -U "$DB_USER" --auth=trust
fi

if pg_ctl -D "$PGDATA_DIR" status >/dev/null 2>&1; then
  :
elif pg_isready -h localhost -p "$PGPORT" >/dev/null 2>&1; then
  echo "端口 ${PGPORT} 已由其他 PostgreSQL 数据目录占用，请先停止该实例或设置 PGPORT。" >&2
  exit 1
else
  echo "启动本地 PostgreSQL：localhost:$PGPORT"
  pg_ctl -D "$PGDATA_DIR" -l "$PGDATA_DIR.log" -o "-p $PGPORT" start
fi

createdb -U "$DB_USER" -h localhost -p "$PGPORT" "$DB_NAME" >/dev/null 2>&1 || true

PYTHON_BIN=""
for candidate in "${BACKEND_PYTHON:-}" "$ROOT_DIR/.venv/bin/python" "/opt/anaconda3/bin/python" "/usr/local/bin/python3" "/opt/homebrew/bin/python3" "$(command -v python3 || true)"; do
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

if [[ -n "$PYTHON_BIN" ]]; then
  echo "初始化项目表结构"
  (
    cd "$ROOT_DIR/backend"
    DATABASE_URL="$DATABASE_URL" "$PYTHON_BIN" - <<'PY'
from database import init_database
init_database()
PY
  )

  if [[ "${SEED_COMPLETION_SAMPLE:-0}" == "1" ]]; then
    echo "导入基金研究方法论配置"
    psql "$DATABASE_URL" -f "$ROOT_DIR/scripts/seed_methodology_config.sql"
    echo "导入完成验收样本数据"
    psql "$DATABASE_URL" -f "$ROOT_DIR/scripts/seed_completion_sample.sql"
    echo "导入策略族谱与可解释同类池"
    psql "$DATABASE_URL" -f "$ROOT_DIR/scripts/seed_research_taxonomy_peer_groups.sql"
    echo "导入基准映射与归因解释"
    psql "$DATABASE_URL" -f "$ROOT_DIR/scripts/seed_benchmark_attribution.sql"
    echo "生成样本滚动评价指标"
    DATABASE_URL="$DATABASE_URL" "$PYTHON_BIN" "$ROOT_DIR/scripts/seed_rolling_metrics.py"
  fi
else
  echo "未找到带 psycopg2/sqlalchemy 的 Python；已启动数据库，但跳过建表和样本导入。"
fi

echo "本地 PostgreSQL 已就绪：localhost:$PGPORT/$DB_NAME"
