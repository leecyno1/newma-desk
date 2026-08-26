#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd -P)"
VENV_DIR="$ROOT_DIR/.venv"
REQ_FILE="$ROOT_DIR/requirements.txt"
ENV_FILE="$ROOT_DIR/.env"
PID_FILE="$ROOT_DIR/.uvicorn.pid"
LOG_FILE="$ROOT_DIR/uvicorn.log"
REQ_HASH_FILE="$VENV_DIR/.requirements.sha256"
BACKUP_DIR="$ROOT_DIR/backups"
PROD_LITE_ENV_FILE="$ROOT_DIR/.env.production-lite.example"
LAUNCHD_LABEL="com.dasheng.aiintel.8001"
LAUNCHD_PLIST_PATH="$HOME/Library/LaunchAgents/${LAUNCHD_LABEL}.plist"

APP_IMPORT="app.main:app"
PYTHON_BIN="${PYTHON_BIN:-python3}"

color() { printf "\033[%sm%s\033[0m\n" "$1" "$2"; }
info() { color "36" "$1"; }
ok() { color "32" "$1"; }
warn() { color "33" "$1"; }
err() { color "31" "$1"; }

ensure_env() {
  if [[ ! -f "$ENV_FILE" ]]; then
    warn "未找到 .env，使用 .env.example 作为模板"
    cp "$ROOT_DIR/.env.example" "$ENV_FILE" || true
  fi
}

ensure_venv() {
  # 项目移动目录后，旧的 venv shebang 可能指向旧路径导致 "bad interpreter"
  if [[ -d "$VENV_DIR" ]]; then
    if [[ ! -x "$VENV_DIR/bin/python" && ! -x "$VENV_DIR/bin/python3" ]]; then
      warn "检测到虚拟环境已损坏（缺少 python 可执行文件），将重建: $VENV_DIR"
      rm -rf "$VENV_DIR"
    else
      # pip 可能存在但 shebang 已失效；用 python -m pip 做一次自检
      if ! ("$VENV_DIR/bin/python" -m pip --version >/dev/null 2>&1 || "$VENV_DIR/bin/python3" -m pip --version >/dev/null 2>&1); then
        warn "检测到虚拟环境 pip 不可用（可能路径已变更），将重建: $VENV_DIR"
        rm -rf "$VENV_DIR"
      fi
    fi
  fi
  if [[ ! -d "$VENV_DIR" ]]; then
    info "创建虚拟环境: $VENV_DIR"
    python3 -m venv "$VENV_DIR"
  fi
  info "升级 pip/setuptools/wheel"
  "$VENV_DIR/bin/pip" install -U pip setuptools wheel >/dev/null
  info "安装依赖: $REQ_FILE"
  "$VENV_DIR/bin/pip" install -r "$REQ_FILE"
}

calc_requirements_hash() {
  if command -v shasum >/dev/null 2>&1; then
    shasum -a 256 "$REQ_FILE" | awk '{print $1}'
    return 0
  fi
  "$VENV_DIR/bin/python" - <<'PY'
import hashlib, pathlib
path = pathlib.Path("requirements.txt")
print(hashlib.sha256(path.read_bytes()).hexdigest())
PY
}

# 在网络受限或本地已装好的场景，允许跳过安装
maybe_ensure_venv() {
  if [[ "${NO_INSTALL:-}" == "1" && -d "$VENV_DIR" ]]; then
    warn "跳过依赖安装 (NO_INSTALL=1)"
    return 0
  fi

  # 首次创建或虚拟环境损坏时，走完整安装流程
  if [[ ! -d "$VENV_DIR" || ! -x "$VENV_DIR/bin/python" ]]; then
    ensure_venv
    calc_requirements_hash > "$REQ_HASH_FILE" 2>/dev/null || true
    return 0
  fi

  # 若 requirements 未变化，跳过重复安装以加快启动
  local current_hash cached_hash
  current_hash="$(calc_requirements_hash 2>/dev/null || true)"
  cached_hash="$(cat "$REQ_HASH_FILE" 2>/dev/null || true)"
  if [[ -n "$current_hash" && "$current_hash" == "$cached_hash" ]]; then
    info "依赖未变化，跳过安装"
    return 0
  fi

  ensure_venv
  calc_requirements_hash > "$REQ_HASH_FILE" 2>/dev/null || true
}

ensure_data_dirs() {
  mkdir -p "$ROOT_DIR/data" "$ROOT_DIR/data/datasets" "$BACKUP_DIR"
}

install_prod_lite_env() {
  ensure_data_dirs
  if [[ -f "$ENV_FILE" ]]; then
    warn ".env 已存在，保留当前配置。如需覆盖请先备份/删除 .env"
    return 0
  fi
  if [[ -f "$PROD_LITE_ENV_FILE" ]]; then
    cp "$PROD_LITE_ENV_FILE" "$ENV_FILE"
    ok "已生成生产轻量配置: .env"
  else
    cp "$ROOT_DIR/.env.example" "$ENV_FILE"
    warn "未找到 .env.production-lite.example，已回退使用 .env.example"
  fi
}

prod_lite_install() {
  ensure_data_dirs
  install_prod_lite_env
  if [[ "${NO_INSTALL:-}" == "1" && ! -d "$VENV_DIR" ]]; then
    warn "跳过依赖安装 (NO_INSTALL=1)"
  else
    maybe_ensure_venv
  fi
  if [[ "${SKIP_DB_INIT:-}" == "1" ]]; then
    warn "跳过数据库初始化 (SKIP_DB_INIT=1)"
  else
    "$VENV_DIR/bin/python" - <<'PYAPP'
from app.db import init_db
init_db()
print('database=initialized')
PYAPP
  fi
  ok "prod-lite 初始化完成"
}

backup_svc() {
  ensure_data_dirs
  local ts dest manifest
  ts=$(date +%Y%m%d-%H%M%S)
  dest="$BACKUP_DIR/backup-$ts"
  mkdir -p "$dest"
  [[ -f "$ENV_FILE" ]] && cp "$ENV_FILE" "$dest/.env"
  [[ -f "$ROOT_DIR/data/app.db" ]] && cp "$ROOT_DIR/data/app.db" "$dest/app.db"
  [[ -f "$ROOT_DIR/data/app.db-wal" ]] && cp "$ROOT_DIR/data/app.db-wal" "$dest/app.db-wal"
  [[ -f "$ROOT_DIR/data/app.db-shm" ]] && cp "$ROOT_DIR/data/app.db-shm" "$dest/app.db-shm"
  [[ -f "$ROOT_DIR/data/ai_config.json" ]] && cp "$ROOT_DIR/data/ai_config.json" "$dest/ai_config.json"
  manifest="$dest/manifest.txt"
  {
    echo "created_at=$ts"
    echo "root=$ROOT_DIR"
    du -sh "$dest" 2>/dev/null || true
    find "$dest" -maxdepth 1 -type f -print | sort
  } > "$manifest"
  ok "备份完成: $dest"
}

restore_svc() {
  local src confirm
  src=${1:-}
  if [[ -z "$src" || ! -d "$src" ]]; then
    err "请提供备份目录: bash scripts/manage.sh restore backups/backup-YYYYmmdd-HHMMSS"
    return 2
  fi
  confirm=${CONFIRM_RESTORE:-}
  if [[ "$confirm" != "RESTORE" ]]; then
    err "恢复会覆盖当前 .env/data/app.db。请设置 CONFIRM_RESTORE=RESTORE 后重试。"
    return 2
  fi
  stop_svc || true
  ensure_data_dirs
  [[ -f "$src/.env" ]] && cp "$src/.env" "$ENV_FILE"
  [[ -f "$src/app.db" ]] && cp "$src/app.db" "$ROOT_DIR/data/app.db"
  [[ -f "$src/app.db-wal" ]] && cp "$src/app.db-wal" "$ROOT_DIR/data/app.db-wal" || rm -f "$ROOT_DIR/data/app.db-wal"
  [[ -f "$src/app.db-shm" ]] && cp "$src/app.db-shm" "$ROOT_DIR/data/app.db-shm" || rm -f "$ROOT_DIR/data/app.db-shm"
  [[ -f "$src/ai_config.json" ]] && cp "$src/ai_config.json" "$ROOT_DIR/data/ai_config.json"
  ok "恢复完成: $src"
}

diagnose_svc() {
  export_env || true
  local host port pid pid_on_port
  host=${HOST:-127.0.0.1}
  port=${PORT:-8001}
  pid=$(read_pid)
  pid_on_port=$(lsof -nPiTCP:"$port" -sTCP:LISTEN -t 2>/dev/null | head -n1 || true)
  if [[ -n "$pid_on_port" && "$pid_on_port" != "${pid:-}" ]]; then
    warn "诊断发现 PID 文件陈旧，已同步为端口监听进程: $pid_on_port"
    echo "$pid_on_port" > "$PID_FILE"
    pid="$pid_on_port"
  fi
  echo "=== Dasheng Local Diagnostics ==="
  echo "root=$ROOT_DIR"
  echo "time=$(date -Iseconds)"
  echo "host=$host"
  echo "port=$port"
  echo "pid_file=${pid:-<empty>}"
  echo "port_listen_pid=${pid_on_port:-<none>}"
  echo "python=$(command -v python3 || true)"
  echo "venv_python=$([[ -x "$VENV_DIR/bin/python" ]] && echo yes || echo no)"
  echo "disk_root=$(df -h "$ROOT_DIR" | tail -n1)"
  echo "data_size=$(du -sh "$ROOT_DIR/data" 2>/dev/null | awk '{print $1}')"
  echo "db_size=$(du -sh "$ROOT_DIR/data/app.db" 2>/dev/null | awk '{print $1}')"
  if [[ -n "$pid_on_port" ]]; then
    ps -p "$pid_on_port" -o pid,%cpu,%mem,rss,command || true
  fi
  local auth_args=()
  if [[ -n "${API_TOKEN:-}" ]]; then
    auth_args=(-H "Authorization: Bearer ${API_TOKEN}")
  fi
  if health_ok "$host" "$port"; then
    echo "health=ok"
    curl -fsS --max-time 5 "http://$host:$port/api/ready" || true
    echo
    curl -fsS --max-time 5 "${auth_args[@]}" "http://$host:$port/api/admin/diagnostics" || true
    echo
  else
    echo "health=fail"
  fi
  echo "recent_log:"
  tail -n 80 "$LOG_FILE" 2>/dev/null || true
}

export_env() {
  # 将 .env 中的变量导出到当前 shell
  set -a
  # shellcheck disable=SC1090
  source "$ENV_FILE"
  set +a
}

read_pid() {
  if [[ -f "$PID_FILE" ]]; then
    cat "$PID_FILE" 2>/dev/null || true
  fi
}

tracked_pid_running() {
  local pid
  pid=$(read_pid)
  [[ -n "$pid" ]] && ps -p "$pid" >/dev/null 2>&1
}

is_port_listening() {
  local port=${1:-8001}
  lsof -nPiTCP:"$port" -sTCP:LISTEN -t >/dev/null 2>&1
}

pid_on_port() {
  local port=${1:-8001}
  lsof -nPiTCP:"$port" -sTCP:LISTEN -t 2>/dev/null | head -n1 || true
}

launchd_service_configured() {
  [[ "$(uname -s 2>/dev/null || true)" == "Darwin" ]] \
    && [[ -f "$LAUNCHD_PLIST_PATH" ]] \
    && [[ -x "$ROOT_DIR/scripts/launchd_8001.sh" ]] \
    && grep -Fq "<string>${ROOT_DIR}/scripts/run_uvicorn_8001.sh</string>" "$LAUNCHD_PLIST_PATH"
}

launchd_service_loaded() {
  launchd_service_configured \
    && launchctl print "gui/$(id -u)/${LAUNCHD_LABEL}" >/dev/null 2>&1
}

sync_pid_file_from_port() {
  local port=${1:-${PORT:-8001}}
  local live_pid
  live_pid=$(pid_on_port "$port")
  if [[ -n "$live_pid" ]]; then
    echo "$live_pid" > "$PID_FILE"
  fi
}

pid_cwd() {
  local pid=${1:-}
  [[ -n "$pid" ]] || return 1
  lsof -a -p "$pid" -d cwd -Fn 2>/dev/null | sed -n 's/^n//p' | head -n1
}

pid_belongs_to_root() {
  local pid=${1:-}
  local cwd
  cwd=$(pid_cwd "$pid")
  [[ -n "$cwd" && "$cwd" == "$ROOT_DIR" ]]
}

health_ok() {
  local host=${1:-127.0.0.1}
  local port=${2:-8001}
  curl -fsS --max-time 3 "http://$host:$port/api/health" >/dev/null 2>&1
}

is_running() {
  local port
  port=${1:-${PORT:-8001}}
  local pid
  pid=$(read_pid)
  if [[ -n "${pid}" ]] && ps -p "$pid" >/dev/null 2>&1; then
    if ! pid_belongs_to_root "$pid"; then
      rm -f "$PID_FILE"
      return 1
    fi
    local bound_pid
    bound_pid=$(pid_on_port "$port")
    if [[ -n "$bound_pid" ]] && [[ "$bound_pid" == "$pid" ]]; then
      return 0
    fi
  fi
  local pid2
  pid2=$(pid_on_port "$port")
  if [[ -n "$pid2" ]] && ps -p "$pid2" >/dev/null 2>&1; then
    if pid_belongs_to_root "$pid2"; then
      echo "$pid2" > "$PID_FILE"
      return 0
    fi
  fi
  return 1
}

wait_health() {
  local host=${1:-127.0.0.1}
  local port=${2:-8001}
  local max_try=${3:-10}
  local i
  for ((i=1; i<=max_try; i++)); do
    if curl -fsS "http://$host:$port/api/health" >/dev/null 2>&1; then
      return 0
    fi
    sleep 1
  done
  return 1
}

start_bg() {
  ensure_env
  maybe_ensure_venv
  export_env
  local host port
  host=${HOST:-127.0.0.1}
  port=${PORT:-8001}
  if is_running "$port"; then
    ok "服务已在运行 (PID: $(cat "$PID_FILE"))"
    exit 0
  fi
  if launchd_service_configured; then
    info "检测到 launchd 托管配置，交由 launchd 启动"
    bash "$ROOT_DIR/scripts/launchd_8001.sh" start
    if wait_health "$host" "$port" 12; then
      sync_pid_file_from_port "$port"
      ok "launchd 服务已启动 (PID: $(cat "$PID_FILE"), http://$host:$port)"
      return 0
    fi
    err "launchd 服务启动后健康检查失败"
    return 1
  fi
  if tracked_pid_running; then
    err "检测到已有受管服务正在运行，但不在端口 $port 上。该脚本当前按单实例管理，请先执行: bash scripts/manage.sh stop"
    return 1
  fi

  # 检测端口冲突（非本 PID 占用）
  if is_port_listening "$port"; then
    local pid_on_port pid_file
    pid_on_port=$(lsof -nPiTCP:"$port" -sTCP:LISTEN -t 2>/dev/null | head -n1 || true)
    pid_file=$(read_pid)
    if [[ -n "$pid_on_port" ]] && [[ "$pid_on_port" != "$pid_file" ]]; then
      err "端口 $port 已被其他进程占用 (PID: $pid_on_port)"
      err "请先执行: bash scripts/manage.sh stop"
      return 1
    fi
  fi

  info "以后台方式启动: http://$host:$port"
  cd "$ROOT_DIR"
  local pybin
  pybin="$VENV_DIR/bin/python"
  if [[ ! -x "$pybin" ]]; then
    pybin="$VENV_DIR/bin/python3"
  fi
  nohup "$pybin" -m uvicorn "$APP_IMPORT" --host "$host" --port "$port" >"$LOG_FILE" 2>&1 < /dev/null & echo $! > "$PID_FILE"
  disown || true
  if wait_health "$host" "$port" 8; then
    local live_pid
    live_pid=$(pid_on_port "$port")
    if [[ -n "$live_pid" ]]; then
      echo "$live_pid" > "$PID_FILE"
    fi
    sleep 1
    if ! is_running "$port" || ! is_port_listening "$port"; then
      err "服务启动后未保持存活，请查看日志: $LOG_FILE"
      tail -n 120 "$LOG_FILE" || true
      return 1
    fi
    ok "已启动 (PID: $(cat "$PID_FILE"))，日志: $LOG_FILE"
    return 0
  fi
  warn "默认模式启动后健康检查失败，尝试兼容模式重启（--loop asyncio）"
  if [[ -f "$PID_FILE" ]]; then
    local oldpid
    oldpid=$(cat "$PID_FILE" || true)
    if [[ -n "$oldpid" ]] && ps -p "$oldpid" >/dev/null 2>&1; then
      kill "$oldpid" || true
      sleep 1
    fi
    rm -f "$PID_FILE"
  fi
  nohup "$pybin" -m uvicorn "$APP_IMPORT" --host "$host" --port "$port" --loop asyncio >"$LOG_FILE" 2>&1 < /dev/null & echo $! > "$PID_FILE"
  disown || true
  if wait_health "$host" "$port" 12; then
    local live_pid
    live_pid=$(pid_on_port "$port")
    if [[ -n "$live_pid" ]]; then
      echo "$live_pid" > "$PID_FILE"
    fi
    sleep 1
    if ! is_running "$port" || ! is_port_listening "$port"; then
      err "兼容模式启动后未保持存活，请查看日志: $LOG_FILE"
      tail -n 120 "$LOG_FILE" || true
      return 1
    fi
    ok "已启动(兼容模式) (PID: $(cat "$PID_FILE"))，日志: $LOG_FILE"
    return 0
  fi
  err "启动失败，请查看日志: $LOG_FILE"
  tail -n 120 "$LOG_FILE" || true
  return 1
}

start_fg() {
  ensure_env
  maybe_ensure_venv
  export_env
  local host port
  host=${HOST:-127.0.0.1}
  port=${PORT:-8001}
  info "以前台方式启动: Ctrl+C 退出"
  cd "$ROOT_DIR"
  local pybin
  pybin="$VENV_DIR/bin/python"
  if [[ ! -x "$pybin" ]]; then
    pybin="$VENV_DIR/bin/python3"
  fi
  "$pybin" -m uvicorn "$APP_IMPORT" --host "$host" --port "$port"
}

stop_svc() {
  ensure_env
  export_env
  local host port
  host=${HOST:-127.0.0.1}
  port=${PORT:-8001}
  if launchd_service_loaded; then
    info "检测到 launchd 托管服务，交由 launchd 停止"
    bash "$ROOT_DIR/scripts/launchd_8001.sh" stop
    rm -f "$PID_FILE"
    if is_port_listening "$port"; then
      err "launchd 已停止，但端口 $port 仍被占用"
      return 1
    fi
    ok "launchd 服务已停止"
    return 0
  fi
  if is_running "$port"; then
    local pid
    pid=$(cat "$PID_FILE")
    info "停止服务 (PID: $pid)"
    kill "$pid" || true
    sleep 1
    if ps -p "$pid" >/dev/null 2>&1; then
      warn "进程未退出，发送 SIGKILL"
      kill -9 "$pid" || true
    fi
    rm -f "$PID_FILE"
    ok "已停止"
    return 0
  fi
  # fallback: 通过端口查找
  local pid2
  pid2=$(lsof -nPiTCP:$port -sTCP:LISTEN -t 2>/dev/null || true)
  if [[ -n "$pid2" ]]; then
    if ! pid_belongs_to_root "$pid2"; then
      warn "端口 $port 被其他目录的进程占用 (PID: $pid2)，不会自动结束"
      warn "如需处理，请到对应项目目录执行停止命令"
      return 1
    fi
    warn "发现占用端口 $port 的本项目进程 (PID: $pid2)，尝试结束"
    kill "$pid2" || true
    sleep 1
    if ps -p "$pid2" >/dev/null 2>&1; then
      warn "发送 SIGKILL"
      kill -9 "$pid2" || true
    fi
    ok "已释放端口 $port"
  else
    warn "服务未在运行"
  fi
}

restart_svc() {
  ensure_env
  maybe_ensure_venv
  export_env
  local host port
  host=${HOST:-127.0.0.1}
  port=${PORT:-8001}
  if launchd_service_configured; then
    info "检测到 launchd 托管配置，交由 launchd 重启"
    bash "$ROOT_DIR/scripts/launchd_8001.sh" restart
    if wait_health "$host" "$port" 12; then
      sync_pid_file_from_port "$port"
      ok "launchd 服务已重启 (PID: $(cat "$PID_FILE"), http://$host:$port)"
      return 0
    fi
    err "launchd 服务重启后健康检查失败"
    return 1
  fi
  stop_svc
  start_bg
}

status_svc() {
  ensure_env
  export_env
  local host port pid
  host=${HOST:-127.0.0.1}
  port=${PORT:-8001}
  pid=$(read_pid)
  if is_running "$port"; then
    pid=$(read_pid)
    if is_port_listening "$port" && health_ok "$host" "$port"; then
      ok "运行中且健康 (PID: $pid, http://$host:$port)"
    else
      warn "运行中但不健康 (PID: $pid, code: SYS-STATE-001)"
      warn "建议执行: bash scripts/manage.sh restart"
    fi
    return 0
  fi
  if [[ -n "$pid" ]]; then
    warn "发现陈旧 PID 文件 (PID: $pid)，已判定未运行"
    rm -f "$PID_FILE"
  fi
  warn "未运行"
}

logs_svc() {
  local follow=${1:-}
  [[ -f "$LOG_FILE" ]] || { warn "暂无日志"; return 0; }
  if [[ "$follow" == "-f" ]]; then
    tail -n 200 -f "$LOG_FILE"
  else
    tail -n 200 "$LOG_FILE"
  fi
}

sync_once() {
  export_env || true
  local port
  port=${PORT:-8001}
  info "触发一次拉取同步: /api/sync/chatlog"
  curl -fsS -X POST "http://127.0.0.1:$port/api/sync/chatlog" || true
  echo
}

sync_full() {
  export_env || true
  local port days
  port=${PORT:-8001}
  days=${1:-30}
  info "触发微信三轨同步近${days}天: /api/sync/wechat/dual-track"
  curl -fsS -X POST "http://127.0.0.1:$port/api/sync/wechat/dual-track?days=$days" || true
  echo
}

migrate_svc() {
  local action
  action=${1:-status}
  "$PYTHON_BIN" "$ROOT_DIR/scripts/migrate_db.py" "$action"
}

launchd_svc() {
  local action
  action=${1:-status}
  case "$action" in
    install|start|stop|restart|status|logs|health|uninstall|remove)
      bash "$ROOT_DIR/scripts/launchd_8001.sh" "$action"
      ;;
    *)
      err "用法: bash scripts/manage.sh launchd <install|start|stop|restart|status|logs|health|uninstall>"
      return 2
      ;;
  esac
}

usage() {
  printf '%s\n' '用法: bash scripts/manage.sh <命令>'
  printf '%s\n' ''
  printf '%s\n' '命令：'
  printf '%s\n' '  install        创建虚拟环境并安装依赖'
  printf '%s\n' '  prod-lite      初始化客户机生产轻量配置与数据库'
  printf '%s\n' '  start          后台启动服务（nohup + PID 文件）'
  printf '%s\n' '  run            前台启动服务（阻塞，Ctrl+C 退出）'
  printf '%s\n' '  dev            前台启动（--reload 热重载，建议开发环境使用；可配合 NO_INSTALL=1）'
  printf '%s\n' '  stop           停止后台服务'
  printf '%s\n' '  status         查看服务状态'
  printf '%s\n' '  doctor         诊断状态（进程/端口/health）'
  printf '%s\n' '  diagnose       输出客户机完整诊断报告'
  printf '%s\n' '  backup         备份 .env、数据库和 AI 配置'
  printf '%s\n' '  restore <dir>  恢复备份（需 CONFIRM_RESTORE=RESTORE）'
  printf '%s\n' '  migrate [status|apply|plan]  查看或执行数据库迁移'
  printf '%s\n' '  release-check  运行发布前静态检查与关键测试'
  printf '%s\n' '  launchd <install|start|stop|restart|status|logs|health|uninstall>  管理 macOS 开机自启'
  printf '%s\n' '  logs [-f]      查看日志（-f 持续跟随）'
  printf '%s\n' '  sync           触发一次从 chatlog 拉取增量'
  printf '%s\n' '  emailsync [id] 同步邮箱（可选账户ID，省略则同步全部已启用账户）'
  printf '%s\n' ''
  printf '%s\n' '示例：'
  printf '%s\n' '  bash scripts/manage.sh install'
  printf '%s\n' '  bash scripts/manage.sh prod-lite'
  printf '%s\n' '  bash scripts/manage.sh start'
  printf '%s\n' '  bash scripts/manage.sh status'
  printf '%s\n' '  bash scripts/manage.sh launchd install'
  printf '%s\n' '  bash scripts/manage.sh logs -f'
  printf '%s\n' '  bash scripts/manage.sh sync'
  printf '%s\n' '  bash scripts/manage.sh emailsync 1'
  printf '%s\n' '  bash scripts/manage.sh stop'
}

doctor_svc() {
  ensure_env
  export_env
  local host port pid pid_on_port
  host=${HOST:-127.0.0.1}
  port=${PORT:-8001}
  pid=$(read_pid)
  pid_on_port=$(lsof -nPiTCP:"$port" -sTCP:LISTEN -t 2>/dev/null | head -n1 || true)
  echo "pid_file=${pid:-<empty>}"
  echo "pid_alive=$([[ -n "$pid" ]] && ps -p "$pid" >/dev/null 2>&1 && echo yes || echo no)"
  echo "port_listen_pid=${pid_on_port:-<none>}"
  if health_ok "$host" "$port"; then
    echo "health=ok"
  else
    echo "health=fail"
  fi
}

cmd=${1:-}
case "$cmd" in
  install) ensure_env; ensure_venv ;;
  prod-lite) prod_lite_install ;;
  start) start_bg ;;
  run) start_fg ;;
  dev)
    ensure_env
    maybe_ensure_venv
    export_env
    cd "$ROOT_DIR"
    pybin="$VENV_DIR/bin/python"
    [[ -x "$pybin" ]] || pybin="$VENV_DIR/bin/python3"
    "$pybin" -m uvicorn "$APP_IMPORT" --host "${HOST:-127.0.0.1}" --port "${PORT:-8001}" --reload
    ;;
  stop) stop_svc ;;
  status) status_svc ;;
  doctor) doctor_svc ;;
  diagnose) diagnose_svc ;;
  backup) backup_svc ;;
  restore) shift || true; restore_svc "${1:-}" ;;
  migrate) shift || true; export_env || true; migrate_svc "${1:-status}" ;;
  release-check) bash "$ROOT_DIR/scripts/release_check.sh" ;;
  launchd) shift || true; launchd_svc "${1:-status}" ;;
  logs) shift || true; logs_svc "${1:-}" ;;
  restart) restart_svc ;;
  sync) sync_once ;;
  emailsync)
    export_env || true
    id=${2:-}
    port=${PORT:-8001}
    if [[ -n "$id" ]]; then
      info "同步邮箱账户 #$id"
      curl -fsS -X POST "http://127.0.0.1:$port/api/email/accounts/$id/sync" || true
      echo
    else
      info "同步全部邮箱账户（逐个尝试）"
      ids=$(curl -fsS "http://127.0.0.1:$port/api/email/accounts" | python3 -c "import sys, json; data = json.load(sys.stdin); print(' '.join(str(i.get('id')) for i in data))")
      for i in $ids; do
        curl -fsS -X POST "http://127.0.0.1:$port/api/email/accounts/$i/sync" || true
        echo
      done
    fi
    ;;
  syncfull) shift || true; sync_full "${1:-30}" ;;
  *) usage ;;
esac
