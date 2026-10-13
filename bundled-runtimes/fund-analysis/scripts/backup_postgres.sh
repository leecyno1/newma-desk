#!/usr/bin/env bash
# scripts/backup_postgres.sh
#
# 每日 PostgreSQL 备份：pg_dump 自定义压缩格式，保留最近 14 份。
# 由 scheduled_update.sh 的 daily bucket 调用，也可单独执行。
#
# 用法：
#   bash scripts/backup_postgres.sh            # 执行备份
#   bash scripts/backup_postgres.sh --prune    # 只清理过期备份，不执行新备份

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKUP_DIR="${BACKUP_DIR:-$ROOT_DIR/backups/postgres}"
RETENTION_COUNT="${RETENTION_COUNT:-14}"
DB_NAME="${POSTGRES_DB:-fund_analysis}"

# launchd 等极简环境的 PATH 不含 Homebrew 目录，psql/pg_dump 会找不到
for brew_bin in /opt/homebrew/bin /usr/local/bin; do
  if [[ -d "$brew_bin" && ":$PATH:" != *":$brew_bin:"* ]]; then
    PATH="$brew_bin:$PATH"
  fi
done
export PATH

# 优先使用与服务器大版本匹配的 pg_dump；否则回退 PATH 中的 pg_dump
PG_DUMP="${PG_DUMP:-}"
if [[ -z "$PG_DUMP" ]]; then
  SERVER_VERSION="$(psql -d "$DB_NAME" -tAc 'SHOW server_version' 2>/dev/null | cut -d. -f1 || true)"
  if [[ -z "$SERVER_VERSION" ]]; then
    echo "backup WARN: psql 不可用或数据库未启动，无法判定服务端大版本，回退 PATH 中的 pg_dump" >&2
  fi
  for candidate in "/opt/homebrew/opt/postgresql@${SERVER_VERSION}/bin/pg_dump" "/usr/local/opt/postgresql@${SERVER_VERSION}/bin/pg_dump"; do
    if [[ -n "$SERVER_VERSION" && -x "$candidate" ]]; then
      PG_DUMP="$candidate"
      break
    fi
  done
  if [[ -z "$PG_DUMP" ]]; then
    PG_DUMP="$(command -v pg_dump || true)"
  fi
fi

# 二进制缺失必须显式报错：`command -v` 失败叠加 set -euo pipefail 会静默 exit 1，
# 曾导致连续 20 天备份全败而日志里一行错误都没有。
if [[ -z "$PG_DUMP" || ! -x "$PG_DUMP" ]]; then
  echo "backup FAILED: 找不到 pg_dump（PATH=$PATH）。launchd 环境需确保 /opt/homebrew/bin 在 PATH 中。" >&2
  exit 1
fi

# pg_restore 与 pg_dump 同目录（用于备份内容自检）
PG_RESTORE="$(dirname "$PG_DUMP")/pg_restore"
if [[ ! -x "$PG_RESTORE" ]]; then
  PG_RESTORE="$(command -v pg_restore || true)"
fi
if [[ -z "$PG_RESTORE" || ! -x "$PG_RESTORE" ]]; then
  echo "backup FAILED: 找不到 pg_restore，无法执行备份内容自检（PATH=$PATH）" >&2
  exit 1
fi

mkdir -p "$BACKUP_DIR"

if [[ "${1:-}" != "--prune" ]]; then
  TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
  TARGET="$BACKUP_DIR/${DB_NAME}_${TIMESTAMP}.dump"

  # -Fc 自定义压缩格式；-d 显式指定库名；连接串走本地 socket，无需密码
  if "$PG_DUMP" -Fc -d "$DB_NAME" -f "$TARGET"; then
    # 内容自检：dump 清单必须含关键表数据，防止静默产出不完整备份
    # （2026-08-19 曾出现 dump 内容为旧时点状态的异常，此检查即为此后验）
    TOC="$($PG_RESTORE -l "$TARGET" 2>/dev/null || true)"
    for required_table in funds fund_nav portfolios; do
      if ! grep -q "TABLE DATA public ${required_table}" <<<"$TOC"; then
        echo "backup FAILED: dump 缺少关键表 ${required_table}，疑似不完整" >&2
        rm -f "$TARGET"
        exit 1
      fi
    done
    SIZE_BYTES="$(stat -f %z "$TARGET" 2>/dev/null || stat -c %s "$TARGET")"
    echo "backup OK: $TARGET ($(( SIZE_BYTES / 1024 / 1024 )) MB)"
  else
    echo "backup FAILED: pg_dump exit $?" >&2
    rm -f "$TARGET"
    exit 1
  fi
fi

# 保留最近 RETENTION_COUNT 份，删除更早的
ls -1t "$BACKUP_DIR/${DB_NAME}"_*.dump 2>/dev/null | tail -n +"$(( RETENTION_COUNT + 1 ))" | while read -r old; do
  rm -f "$old"
  echo "pruned old backup: $old"
done
