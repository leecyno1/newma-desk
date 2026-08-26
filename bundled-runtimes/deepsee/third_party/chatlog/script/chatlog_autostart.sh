#!/bin/zsh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_DIR="${CHATLOG_REPO_DIR:-$(cd "$SCRIPT_DIR/.." && pwd)}"
CHATLOG_BIN="${CHATLOG_BIN:-$REPO_DIR/chatlog}"
DATA_DIR="${WECHAT_DATA_DIR:-}"
ADDR="${CHATLOG_ADDR:-127.0.0.1:5030}"
LOG_FILE="${CHATLOG_LOG_FILE:-/tmp/chatlog_5030.log}"
WORK_ROOT="${CHATLOG_WORK_ROOT:-$HOME/Documents/chatlog}"
WORK_PID_FILE="$WORK_ROOT/chatlog.pid"

if [[ ! -x "$CHATLOG_BIN" ]]; then
  echo "chatlog binary not found: $CHATLOG_BIN" >> "$LOG_FILE"
  exit 1
fi

if [[ -z "$DATA_DIR" || ! -d "$DATA_DIR" ]]; then
  echo "WECHAT_DATA_DIR is not configured or does not exist" >> "$LOG_FILE"
  exit 1
fi

mkdir -p "$WORK_ROOT"

# Remove stale single-instance pid file to avoid non-interactive startup blocking.
if [[ -f "$WORK_PID_FILE" ]]; then
  OLD_PID="$(cat "$WORK_PID_FILE" 2>/dev/null || true)"
  if [[ -n "${OLD_PID:-}" ]] && ! kill -0 "$OLD_PID" 2>/dev/null; then
    rm -f "$WORK_PID_FILE"
  fi
fi

# Ensure target port is free before start.
PORT_PID="$(lsof -nP -tiTCP:5030 -sTCP:LISTEN 2>/dev/null || true)"
if [[ -n "${PORT_PID:-}" ]]; then
  kill -TERM "$PORT_PID" 2>/dev/null || true
  sleep 1
fi

# Pre-decrypt once, then keep incremental updates via auto-decrypt.
"$CHATLOG_BIN" decrypt -d "$DATA_DIR" >> "$LOG_FILE" 2>&1 || true

exec "$CHATLOG_BIN" server --addr "$ADDR" --data-dir "$DATA_DIR" --auto-decrypt >> "$LOG_FILE" 2>&1
