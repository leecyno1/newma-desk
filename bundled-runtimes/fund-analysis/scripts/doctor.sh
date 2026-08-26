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

DATABASE_URL="${DATABASE_URL:-postgresql://postgres:fundanalysis2024@localhost:5432/fund_analysis}"
BACKEND_URL="${BACKEND_URL:-http://127.0.0.1:8005}"
FRONTEND_URL="${FRONTEND_URL:-http://127.0.0.1:3000}"
MIN_FUND_COUNT="${MIN_FUND_COUNT:-10000}"

fail() {
  echo "FAIL $1"
  exit 1
}

ok() {
  echo "OK $1"
}

command -v pg_isready >/dev/null 2>&1 || fail "未找到 pg_isready，请先安装 PostgreSQL 客户端。"
command -v psql >/dev/null 2>&1 || fail "未找到 psql，请先安装 PostgreSQL 客户端。"
command -v curl >/dev/null 2>&1 || fail "未找到 curl。"

pg_isready -d "$DATABASE_URL" >/dev/null 2>&1 || fail "PostgreSQL 未就绪；请先运行 scripts/start-local-postgres.sh 或启动 Docker 数据库。"
ok "PostgreSQL 可连接"

fund_count="$(psql "$DATABASE_URL" -Atc "SELECT COUNT(*) FROM funds" 2>/dev/null || echo "ERR")"
[[ "$fund_count" =~ ^[0-9]+$ ]] || fail "无法读取 funds 表；请先初始化数据库结构。"
if (( fund_count < MIN_FUND_COUNT )); then
  fail "基金库数量不足：当前 ${fund_count}，期望至少 ${MIN_FUND_COUNT}；请运行 npm run funds:update-universe。"
fi
ok "基金库数量 ${fund_count}"

backend_health="$(curl -fsS "${BACKEND_URL}/api/health" 2>/dev/null || true)"
[[ -n "$backend_health" ]] || fail "后端不可达：${BACKEND_URL}"
if ! printf '%s' "$backend_health" | grep -q '"status"[[:space:]]*:[[:space:]]*"ok"'; then
  echo "$backend_health"
  fail "后端健康检查未通过。"
fi
ok "后端健康检查通过"

fund_payload="$(curl -fsS "${FRONTEND_URL}/api/funds?limit=1&tradableOnly=true" 2>/dev/null || true)"
[[ -n "$fund_payload" ]] || fail "前端基金接口不可达：${FRONTEND_URL}"
if printf '%s' "$fund_payload" | grep -q '"total"[[:space:]]*:[[:space:]]*0'; then
  echo "$fund_payload"
  fail "前端基金接口返回空研究池。"
fi
ok "前端基金接口有数据"

echo "OK 基金研究平台本地验收前置条件通过"
