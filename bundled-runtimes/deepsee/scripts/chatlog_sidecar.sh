#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
ENV_FILE="$ROOT_DIR/.env"
LOG_DIR="${CHATLOG_LOG_DIR:-/private/tmp}"
GRAY_PID_FILE="$ROOT_DIR/.chatlog-gray.pid"
GRAY_LOG_FILE="${CHATLOG_GRAY_LOG_FILE:-$LOG_DIR/chatlog_5031.log}"
LAUNCHD_LABEL="${CHATLOG_LAUNCHD_LABEL:-com.deepsee.chatlog.5031}"
LAUNCHD_PLIST="$HOME/Library/LaunchAgents/$LAUNCHD_LABEL.plist"

load_env() {
  if [[ -f "$ENV_FILE" ]]; then
    set -a
    # shellcheck disable=SC1090
    source "$ENV_FILE"
    set +a
  fi
}

info() { printf '\033[36m%s\033[0m\n' "$1"; }
ok() { printf '\033[32m%s\033[0m\n' "$1"; }
warn() { printf '\033[33m%s\033[0m\n' "$1"; }
err() { printf '\033[31m%s\033[0m\n' "$1"; }

candidate_bin() {
  local explicit="${CHATLOG_BIN:-}"
  if [[ -n "$explicit" && -x "$explicit" ]]; then
    printf '%s\n' "$explicit"
    return 0
  fi
  for path in \
    "$ROOT_DIR/.local/chatlog/bin/chatlog" \
    "$ROOT_DIR/.local/wechat-local/chatlog_alpha/chatlog" \
    "$ROOT_DIR/.local/wechat-local/chatlog_alpha/chatlog-darwin-arm64" \
    "$ROOT_DIR/.local/wechat-local/chatlog_alpha/chatlog-darwin-amd64" \
    "$ROOT_DIR/.local/chatlog_0.0.31_darwin_arm64/chatlog"
  do
    if [[ -x "$path" ]]; then
      printf '%s\n' "$path"
      return 0
    fi
  done
  command -v chatlog 2>/dev/null || true
}

http_probe() {
  local base="${1:-${CHATLOG_HTTP_BASE:-http://127.0.0.1:5030}}"
  local timeout="${2:-${CHATLOG_HTTP_SESSION_TIMEOUT_SECONDS:-5}}"
  python3 - "$base" "$timeout" <<'PY'
import json
import sys
import time
from urllib.request import urlopen

base = sys.argv[1].rstrip("/")
timeout = float(sys.argv[2])
url = f"{base}/api/v1/session"
t0 = time.perf_counter()
try:
    with urlopen(url, timeout=timeout) as resp:
        body = resp.read(512)
        print(json.dumps({
            "ok": True,
            "url": url,
            "status": resp.status,
            "latency_ms": int((time.perf_counter() - t0) * 1000),
            "bytes": len(body),
        }, ensure_ascii=False))
except Exception as exc:
    print(json.dumps({
        "ok": False,
        "url": url,
        "latency_ms": int((time.perf_counter() - t0) * 1000),
        "error": str(exc),
    }, ensure_ascii=False))
    sys.exit(1)
PY
}

build_v031() {
  info "从仓库内置源码编译 chatlog"
  "$ROOT_DIR/scripts/build_chatlog.sh"
  ok "完成: $ROOT_DIR/.local/chatlog/bin/chatlog"
}

pid_on_port() {
  local port="$1"
  lsof -nPiTCP:"$port" -sTCP:LISTEN -t 2>/dev/null | head -n1 || true
}

status() {
  local primary_base="${CHATLOG_HTTP_BASE:-http://127.0.0.1:5030}"
  local primary_port
  primary_port="$(python3 - "$primary_base" <<'PY'
from urllib.parse import urlparse
import sys
u = urlparse(sys.argv[1])
print(u.port or (443 if u.scheme == "https" else 80))
PY
)"
  local gray_port="${CHATLOG_GRAY_PORT:-5031}"
  local gray_base="${CHATLOG_GRAY_BASE:-http://127.0.0.1:$gray_port}"
  echo "primary_base=$primary_base"
  echo "primary_pid=$(pid_on_port "$primary_port" || true)"
  http_probe "$primary_base" "${CHATLOG_HTTP_SESSION_TIMEOUT_SECONDS:-5}" || true
  echo "gray_base=$gray_base"
  echo "gray_pid=$(pid_on_port "$gray_port" || true)"
  http_probe "$gray_base" "${CHATLOG_HTTP_SESSION_TIMEOUT_SECONDS:-5}" || true
}

require_start_config() {
  CHATLOG_BIN_RESOLVED="$(candidate_bin)"
  if [[ -z "${CHATLOG_BIN_RESOLVED:-}" || ! -x "$CHATLOG_BIN_RESOLVED" ]]; then
    err "未找到 chatlog 可执行文件；先从仓库内置源码编译: bash scripts/chatlog_sidecar.sh build"
    return 2
  fi
  CHATLOG_DATA_DIR="${CHATLOG_DATA_DIR:-}"
  CHATLOG_WORK_DIR="${CHATLOG_WORK_DIR:-${CHATLOG_DIR:-}}"
  if [[ -z "$CHATLOG_DATA_DIR" ]]; then
    err "缺少 CHATLOG_DATA_DIR。它应指向微信原始数据目录 xwechat_files/<账号>。"
    return 2
  fi
  if [[ -z "$CHATLOG_WORK_DIR" ]]; then
    err "缺少 CHATLOG_WORK_DIR 或 CHATLOG_DIR。它应指向 chatlog 解密后的工作目录。"
    return 2
  fi
}

start_gray() {
  require_start_config
  local port="${CHATLOG_GRAY_PORT:-5031}"
  local bind="${CHATLOG_GRAY_BIND:-127.0.0.1:$port}"
  local existing
  existing="$(pid_on_port "$port")"
  if [[ -n "$existing" ]]; then
    warn "灰度端口已在运行: pid=$existing port=$port"
    return 0
  fi
  mkdir -p "$(dirname "$GRAY_LOG_FILE")" "$CHATLOG_WORK_DIR"
  local args=(
    server
    --addr "$bind"
    --platform "${CHATLOG_PLATFORM:-darwin}"
    --version "${CHATLOG_VERSION:-4}"
    --data-dir "$CHATLOG_DATA_DIR"
    --work-dir "$CHATLOG_WORK_DIR"
  )
  if [[ -n "${CHATLOG_DATA_KEY:-}" ]]; then
    args+=(--data-key "$CHATLOG_DATA_KEY")
  fi
  if [[ -n "${CHATLOG_IMG_KEY:-}" ]]; then
    args+=(--img-key "$CHATLOG_IMG_KEY")
  fi
  if [[ "${CHATLOG_AUTO_DECRYPT:-0}" == "1" || "${CHATLOG_AUTO_DECRYPT:-false}" == "true" ]]; then
    args+=(--auto-decrypt)
  fi
  info "启动 chatlog 灰度服务: $bind"
  nohup "$CHATLOG_BIN_RESOLVED" "${args[@]}" >>"$GRAY_LOG_FILE" 2>&1 &
  echo $! > "$GRAY_PID_FILE"
  local deadline="${CHATLOG_STARTUP_TIMEOUT_SECONDS:-45}"
  local elapsed=0
  until http_probe "http://127.0.0.1:$port" "${CHATLOG_HTTP_SESSION_TIMEOUT_SECONDS:-5}" >/dev/null 2>&1; do
    if ! kill -0 "$(cat "$GRAY_PID_FILE" 2>/dev/null)" 2>/dev/null; then
      warn "灰度服务已退出，查看日志: $GRAY_LOG_FILE"
      return 1
    fi
    if (( elapsed >= deadline )); then
      warn "灰度服务启动超时，查看日志: $GRAY_LOG_FILE"
      return 1
    fi
    sleep 1
    elapsed=$((elapsed + 1))
  done
  http_probe "http://127.0.0.1:$port" "${CHATLOG_HTTP_SESSION_TIMEOUT_SECONDS:-5}" || true
  ok "chatlog 灰度服务已可用"
}

stop_gray() {
  local port="${CHATLOG_GRAY_PORT:-5031}"
  local pid
  pid="$(pid_on_port "$port")"
  if [[ -z "$pid" && -f "$GRAY_PID_FILE" ]]; then
    pid="$(cat "$GRAY_PID_FILE" 2>/dev/null || true)"
  fi
  if [[ -z "$pid" ]]; then
    warn "灰度服务未运行"
    return 0
  fi
  kill "$pid" 2>/dev/null || true
  rm -f "$GRAY_PID_FILE"
  ok "已停止灰度服务: pid=$pid"
}

logs() {
  tail -n "${CHATLOG_LOG_LINES:-120}" "$GRAY_LOG_FILE" 2>/dev/null \
    | sed -E 's/(DataKey[:=][[:space:]]*)[^,\" ]+/\1<redacted>/g; s/(ImgKey[:=][[:space:]]*)[^,\" ]+/\1<redacted>/g; s/(\"DataKey\":\"?)[^\"]+/\1<redacted>/g; s/(\"ImgKey\":\"?)[^\"]+/\1<redacted>/g' \
    || warn "暂无灰度日志: $GRAY_LOG_FILE"
}

launchd_install() {
  mkdir -p "$HOME/Library/LaunchAgents"
  chmod +x "$ROOT_DIR/scripts/run_chatlog_5031.sh"
  cat > "$LAUNCHD_PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>$LAUNCHD_LABEL</string>
  <key>ProgramArguments</key>
  <array>
    <string>/bin/bash</string>
    <string>$ROOT_DIR/scripts/run_chatlog_5031.sh</string>
  </array>
  <key>WorkingDirectory</key>
  <string>$ROOT_DIR</string>
  <key>RunAtLoad</key>
  <true/>
  <key>KeepAlive</key>
  <true/>
  <key>StandardOutPath</key>
  <string>/private/tmp/chatlog_5031_launchd.out</string>
  <key>StandardErrorPath</key>
  <string>/private/tmp/chatlog_5031_launchd.err</string>
</dict>
</plist>
EOF
  plutil -lint "$LAUNCHD_PLIST" >/dev/null
  launchctl bootout "gui/$(id -u)" "$LAUNCHD_PLIST" >/dev/null 2>&1 || true
  launchctl bootstrap "gui/$(id -u)" "$LAUNCHD_PLIST"
  launchctl kickstart -k "gui/$(id -u)/$LAUNCHD_LABEL" >/dev/null 2>&1 || true
  ok "已安装并启动 launchd: $LAUNCHD_LABEL"
}

launchd_stop() {
  launchctl bootout "gui/$(id -u)" "$LAUNCHD_PLIST" >/dev/null 2>&1 || true
  ok "已停止 launchd: $LAUNCHD_LABEL"
}

launchd_status() {
  launchctl print "gui/$(id -u)/$LAUNCHD_LABEL" 2>/dev/null | sed -n '1,80p' || warn "launchd 未加载: $LAUNCHD_LABEL"
}

disable_old_autostart() {
  local old="$HOME/Library/LaunchAgents/com.chatlog.autostart.plist"
  if [[ -f "$old" ]]; then
    launchctl bootout "gui/$(id -u)" "$old" >/dev/null 2>&1 || true
    ok "已停用旧 chatlog autostart: com.chatlog.autostart"
  else
    warn "未找到旧 autostart plist"
  fi
}

load_env
cmd="${1:-status}"
case "$cmd" in
  build|build-v031) build_v031 ;;
  probe) http_probe "${2:-${CHATLOG_HTTP_BASE:-http://127.0.0.1:5030}}" "${3:-${CHATLOG_HTTP_SESSION_TIMEOUT_SECONDS:-5}}" ;;
  status) status ;;
  start-gray) start_gray ;;
  stop-gray) stop_gray ;;
  restart-gray) stop_gray; start_gray ;;
  launchd-install) launchd_install ;;
  launchd-restart) launchd_stop; launchd_install ;;
  launchd-stop) launchd_stop ;;
  launchd-status) launchd_status ;;
  disable-old-autostart) disable_old_autostart ;;
  logs) logs ;;
  *)
    cat <<'EOF'
用法: bash scripts/chatlog_sidecar.sh <command>

commands:
  status        同时探测主链路 5030 与灰度链路 5031
  probe [url]   探测指定 chatlog HTTP 地址
  build         从仓库内置源码编译 chatlog（build-v031 为兼容别名）
  start-gray    启动 5031 灰度服务，不影响 5030
  stop-gray     停止 5031 灰度服务
  restart-gray  重启 5031 灰度服务
  launchd-install  安装并启动 5031 launchd 保活服务
  launchd-restart  重启 5031 launchd 保活服务
  launchd-stop     停止 5031 launchd 保活服务
  launchd-status   查看 5031 launchd 状态
  disable-old-autostart  停用旧 5030 自动启动项
  logs          查看灰度服务日志
EOF
    ;;
esac
