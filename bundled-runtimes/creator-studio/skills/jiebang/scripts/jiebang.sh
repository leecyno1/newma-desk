#!/usr/bin/env bash
set -euo pipefail

ROOT="${PWD}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
ASSET_DIR="$SKILL_DIR/assets"
ASSET_TEMPLATE_DIR="$ASSET_DIR/templates"
MANIFEST="$ROOT/.jiebang/manifest.yml"
TEMPLATE_DIR="$ROOT/.jiebang/templates"
RUNTIME_DIR="$ROOT/.jiebang/runtime"

usage() {
  cat <<'EOF'
Usage:
  skills/jiebang/scripts/jiebang.sh init
  skills/jiebang/scripts/jiebang.sh bootstrap [--update-agents]
  skills/jiebang/scripts/jiebang.sh remove-agents-hook
  skills/jiebang/scripts/jiebang.sh validate
  skills/jiebang/scripts/jiebang.sh brief <cc|cx|ag>
  skills/jiebang/scripts/jiebang.sh autosave <cc|cx|ag>
  skills/jiebang/scripts/jiebang.sh watch <cc|cx|ag> [seconds]
  skills/jiebang/scripts/jiebang.sh daemon-start <cc|cx|ag> [seconds]
  skills/jiebang/scripts/jiebang.sh daemon-status
  skills/jiebang/scripts/jiebang.sh daemon-stop
EOF
}

require_file() {
  local file="$1"
  if [ ! -f "$file" ]; then
    echo "Missing: $file" >&2
    exit 1
  fi
}

install_project_scaffold() {
  mkdir -p "$ROOT/.jiebang/templates"

  if [ ! -f "$MANIFEST" ]; then
    require_file "$ASSET_DIR/manifest.yml"
    cp "$ASSET_DIR/manifest.yml" "$MANIFEST"
  fi

  for template in project current-task decision-log handoff session; do
    local src="$ASSET_TEMPLATE_DIR/$template.md"
    local dst="$TEMPLATE_DIR/$template.md"
    require_file "$src"
    [ -f "$dst" ] || cp "$src" "$dst"
  done
}

timestamp() {
  date '+%Y-%m-%d %H:%M'
}

agent_file() {
  local agent="$1"
  echo "$RUNTIME_DIR/handoffs/$agent.md"
}

session_file() {
  local agent="$1"
  echo "$RUNTIME_DIR/sessions/$agent.md"
}

pid_file() {
  echo "$RUNTIME_DIR/autosave.pid"
}

log_file() {
  echo "$RUNTIME_DIR/autosave.log"
}

validate_agent() {
  local agent="$1"
  case "$agent" in
    cc|cx|ag) ;;
    *)
      echo "Unknown agent: $agent" >&2
      exit 1
      ;;
  esac
}

init_runtime() {
  install_project_scaffold
  require_file "$MANIFEST"
  require_file "$TEMPLATE_DIR/project.md"
  require_file "$TEMPLATE_DIR/current-task.md"
  require_file "$TEMPLATE_DIR/decision-log.md"
  require_file "$TEMPLATE_DIR/handoff.md"
  require_file "$TEMPLATE_DIR/session.md"

  mkdir -p "$RUNTIME_DIR/handoffs" "$RUNTIME_DIR/sessions"

  [ -f "$RUNTIME_DIR/project.md" ] || cp "$TEMPLATE_DIR/project.md" "$RUNTIME_DIR/project.md"
  [ -f "$RUNTIME_DIR/current-task.md" ] || cp "$TEMPLATE_DIR/current-task.md" "$RUNTIME_DIR/current-task.md"
  [ -f "$RUNTIME_DIR/decision-log.md" ] || cp "$TEMPLATE_DIR/decision-log.md" "$RUNTIME_DIR/decision-log.md"

  local loop_agent
  for loop_agent in cc cx ag; do
    if [ ! -f "$RUNTIME_DIR/handoffs/$loop_agent.md" ]; then
      sed "s/replace-me/$loop_agent/g" "$TEMPLATE_DIR/handoff.md" > "$RUNTIME_DIR/handoffs/$loop_agent.md"
    fi
    [ -f "$RUNTIME_DIR/sessions/$loop_agent.md" ] || cp "$TEMPLATE_DIR/session.md" "$RUNTIME_DIR/sessions/$loop_agent.md"
  done

  echo "Initialized runtime in $RUNTIME_DIR"
}

bootstrap_project() {
  init_runtime

  if [ "${1:-}" = "--update-agents" ]; then
    local agents_file="$ROOT/AGENTS.md"
    local begin_marker="<!-- JIEBANG_HOOK_BEGIN -->"
    local end_marker="<!-- JIEBANG_HOOK_END -->"
    if [ ! -f "$agents_file" ]; then
      cat > "$agents_file" <<'EOF'
# AGENTS.md

> **SCOPE:** Project-level agent instructions.
EOF
    fi

    if ! grep -q "$begin_marker" "$agents_file"; then
      cat >> "$agents_file" <<'EOF'

<!-- JIEBANG_HOOK_BEGIN -->
## Jiebang Hook

If the user says `接棒cc`, `接棒cx`, `接棒ag`, `交棒`, or `自动交棒`, use the installed `jiebang` skill and read `.jiebang/manifest.yml`.

Do not store session logs or temporary progress in this file.
<!-- JIEBANG_HOOK_END -->
EOF
      echo "Updated AGENTS.md with Jiebang hook"
    else
      echo "AGENTS.md already contains Jiebang hook"
    fi
  fi
}

remove_agents_hook() {
  local agents_file="$ROOT/AGENTS.md"
  if [ ! -f "$agents_file" ]; then
    echo "AGENTS.md not found"
    return 0
  fi

  awk '
    /<!-- JIEBANG_HOOK_BEGIN -->/ { skip=1; next }
    /<!-- JIEBANG_HOOK_END -->/ { skip=0; next }
    skip != 1 { print }
  ' "$agents_file" > "$agents_file.tmp"
  mv "$agents_file.tmp" "$agents_file"
  echo "Removed Jiebang hook from AGENTS.md if present"
}

validate_runtime() {
  require_file "$MANIFEST"
  require_file "$RUNTIME_DIR/project.md"
  require_file "$RUNTIME_DIR/current-task.md"
  require_file "$RUNTIME_DIR/decision-log.md"

  local loop_agent
  for loop_agent in cc cx ag; do
    require_file "$RUNTIME_DIR/handoffs/$loop_agent.md"
    require_file "$RUNTIME_DIR/sessions/$loop_agent.md"
  done

  echo "Validation OK"
}

autosave_agent() {
  local agent="${1:-}"
  validate_agent "$agent"
  require_file "$RUNTIME_DIR/current-task.md"
  require_file "$RUNTIME_DIR/decision-log.md"

  local handoff
  local session
  handoff="$(agent_file "$agent")"
  session="$(session_file "$agent")"
  require_file "$handoff"
  require_file "$session"

  local now
  now="$(timestamp)"

  cat > "$handoff" <<EOF
---
agent: $agent
status: active
updated_at: $now
task: auto-snapshot
mode: auto
---

# Handoff

## Goal

[Auto snapshot] See \`.jiebang/runtime/current-task.md\`.

## Done

- [Auto snapshot] Review session log and recent work.

## In Progress

- [Auto snapshot generated at $now]

## Changed Files

- [Update manually if needed]

## Risks

- Automatic handoff may omit important reasoning unless manual \`交棒\` is also done.

## Next Step

Read \`.jiebang/runtime/current-task.md\`, then inspect \`.jiebang/runtime/sessions/$agent.md\`.
EOF

  printf '\n- %s - auto handoff snapshot refreshed\n' "$now" >> "$session"
  echo "Autosaved $handoff"
}

watch_agent() {
  local agent="${1:-}"
  local interval="${2:-180}"
  validate_agent "$agent"

  case "$interval" in
    ''|*[!0-9]*)
      echo "Interval must be a positive integer in seconds" >&2
      exit 1
      ;;
  esac

  echo "Watching $agent every ${interval}s"
  while true; do
    autosave_agent "$agent"
    sleep "$interval"
  done
}

daemon_start() {
  local agent="${1:-}"
  local interval="${2:-180}"
  validate_agent "$agent"
  install_project_scaffold
  init_runtime >/dev/null

  local pid
  pid="$(pid_file)"
  if [ -f "$pid" ] && kill -0 "$(cat "$pid")" 2>/dev/null; then
    echo "Autosave daemon already running: $(cat "$pid")"
    return 0
  fi

  nohup "$0" watch "$agent" "$interval" >> "$(log_file)" 2>&1 &
  echo "$!" > "$pid"
  echo "Started autosave daemon for $agent: $(cat "$pid")"
}

daemon_status() {
  local pid
  pid="$(pid_file)"
  if [ -f "$pid" ] && kill -0 "$(cat "$pid")" 2>/dev/null; then
    echo "Autosave daemon running: $(cat "$pid")"
  else
    echo "Autosave daemon not running"
  fi
}

daemon_stop() {
  local pid
  pid="$(pid_file)"
  if [ -f "$pid" ] && kill -0 "$(cat "$pid")" 2>/dev/null; then
    kill "$(cat "$pid")"
    rm -f "$pid"
    echo "Stopped autosave daemon"
  else
    rm -f "$pid"
    echo "Autosave daemon not running"
  fi
}

brief_agent() {
  local agent="${1:-}"
  if [ -z "$agent" ]; then
    usage
    exit 1
  fi

  validate_agent "$agent"

  for file in \
    "$MANIFEST" \
    "$RUNTIME_DIR/project.md" \
    "$RUNTIME_DIR/current-task.md" \
    "$RUNTIME_DIR/decision-log.md" \
    "$RUNTIME_DIR/handoffs/$agent.md" \
    "$RUNTIME_DIR/sessions/$agent.md"; do
    if [ -f "$file" ]; then
      printf '\n===== %s =====\n' "${file#$ROOT/}"
      cat "$file"
      printf '\n'
    fi
  done
}

main() {
  local cmd="${1:-}"
  case "$cmd" in
    init) init_runtime ;;
    bootstrap) shift; bootstrap_project "${1:-}" ;;
    remove-agents-hook) remove_agents_hook ;;
    validate) validate_runtime ;;
    brief) shift; brief_agent "${1:-}" ;;
    autosave) shift; autosave_agent "${1:-}" ;;
    watch) shift; watch_agent "${1:-}" "${2:-180}" ;;
    daemon-start) shift; daemon_start "${1:-}" "${2:-180}" ;;
    daemon-status) daemon_status ;;
    daemon-stop) daemon_stop ;;
    *) usage; exit 1 ;;
  esac
}

main "$@"
