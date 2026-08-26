#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
LABEL="com.dasheng.aiintel.8001"
UID_NUM="$(id -u)"
DOMAIN="gui/${UID_NUM}"
SERVICE_TARGET="${DOMAIN}/${LABEL}"
LAUNCH_AGENT_DIR="$HOME/Library/LaunchAgents"
PLIST_PATH="${LAUNCH_AGENT_DIR}/${LABEL}.plist"
LOG_DIR="$HOME/Library/Logs/0913"
STDOUT_LOG="${LOG_DIR}/launchd-8001.out.log"
STDERR_LOG="${LOG_DIR}/launchd-8001.err.log"
RUNNER_PATH="${ROOT_DIR}/scripts/run_uvicorn_8001.sh"

color() { printf "\033[%sm%s\033[0m\n" "$1" "$2"; }
info() { color "36" "$1"; }
ok() { color "32" "$1"; }
warn() { color "33" "$1"; }
err() { color "31" "$1"; }

ensure_dirs() {
  mkdir -p "$LAUNCH_AGENT_DIR" "$LOG_DIR"
}

write_plist() {
  cat >"$PLIST_PATH" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>${LABEL}</string>
  <key>ProgramArguments</key>
  <array>
    <string>${RUNNER_PATH}</string>
  </array>
  <key>WorkingDirectory</key>
  <string>${ROOT_DIR}</string>
  <key>RunAtLoad</key>
  <true/>
  <key>KeepAlive</key>
  <true/>
  <key>StandardOutPath</key>
  <string>${STDOUT_LOG}</string>
  <key>StandardErrorPath</key>
  <string>${STDERR_LOG}</string>
  <key>EnvironmentVariables</key>
  <dict>
    <key>PYTHONUNBUFFERED</key>
    <string>1</string>
  </dict>
</dict>
</plist>
EOF
}

bootout_if_loaded() {
  launchctl bootout "$DOMAIN" "$PLIST_PATH" >/dev/null 2>&1 || true
}

install_service() {
  ensure_dirs
  chmod +x "$RUNNER_PATH"
  write_plist
  bootout_if_loaded
  launchctl bootstrap "$DOMAIN" "$PLIST_PATH"
  launchctl enable "$SERVICE_TARGET" >/dev/null 2>&1 || true
  launchctl kickstart -k "$SERVICE_TARGET"
  sleep 1
  ok "launchd service installed and started: ${SERVICE_TARGET}"
}

uninstall_service() {
  bootout_if_loaded
  rm -f "$PLIST_PATH"
  ok "launchd service removed: ${SERVICE_TARGET}"
}

start_service() {
  if [[ ! -f "$PLIST_PATH" ]]; then
    err "plist not found: $PLIST_PATH"
    exit 1
  fi
  ensure_dirs
  chmod +x "$RUNNER_PATH"
  if ! launchctl print "$SERVICE_TARGET" >/dev/null 2>&1; then
    launchctl bootstrap "$DOMAIN" "$PLIST_PATH"
    launchctl enable "$SERVICE_TARGET" >/dev/null 2>&1 || true
  fi
  launchctl kickstart -k "$SERVICE_TARGET"
  sleep 1
  ok "service started: ${SERVICE_TARGET}"
}

stop_service() {
  if launchctl print "$SERVICE_TARGET" >/dev/null 2>&1; then
    launchctl bootout "$DOMAIN" "$PLIST_PATH"
  fi
  ok "service stopped: ${SERVICE_TARGET}"
}

status_service() {
  if launchctl print "$SERVICE_TARGET" >/dev/null 2>&1; then
    ok "service loaded: ${SERVICE_TARGET}"
    launchctl print "$SERVICE_TARGET" | sed -n '1,80p'
  else
    warn "service not loaded: ${SERVICE_TARGET}"
    exit 1
  fi
}

restart_service() {
  if [[ ! -f "$PLIST_PATH" ]]; then
    err "plist not found: $PLIST_PATH"
    exit 1
  fi
  bootout_if_loaded
  launchctl bootstrap "$DOMAIN" "$PLIST_PATH"
  launchctl kickstart -k "$SERVICE_TARGET"
  sleep 1
  ok "service restarted: ${SERVICE_TARGET}"
}

logs_service() {
  info "stdout: $STDOUT_LOG"
  info "stderr: $STDERR_LOG"
  touch "$STDOUT_LOG" "$STDERR_LOG"
  tail -n 80 "$STDOUT_LOG" "$STDERR_LOG"
}

health_check() {
  local host port
  host="$(grep -E '^HOST=' "$ROOT_DIR/.env" 2>/dev/null | tail -n1 | cut -d= -f2- || true)"
  port="$(grep -E '^PORT=' "$ROOT_DIR/.env" 2>/dev/null | tail -n1 | cut -d= -f2- || true)"
  host="${host:-127.0.0.1}"
  port="${port:-8001}"
  if curl -fsS --max-time 5 "http://${host}:${port}/api/health" >/dev/null 2>&1; then
    ok "health ok: http://${host}:${port}/api/health"
  else
    err "health failed: http://${host}:${port}/api/health"
    exit 1
  fi
}

cmd="${1:-install}"
case "$cmd" in
  install) install_service ;;
  start) start_service ;;
  stop) stop_service ;;
  uninstall|remove) uninstall_service ;;
  restart) restart_service ;;
  status) status_service ;;
  logs) logs_service ;;
  health) health_check ;;
  *)
    echo "Usage: $0 [install|start|stop|uninstall|restart|status|logs|health]"
    exit 2
    ;;
esac
