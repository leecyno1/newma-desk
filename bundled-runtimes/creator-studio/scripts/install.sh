#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="${DASHENG_PYTHON_BIN:-python3}"
WITH_MEDIA=0
WITH_RESERVES=0
INSTALL_SKILLS=0

usage() {
  cat <<'EOF'
Usage: ./scripts/install.sh [options]

Options:
  --with-media       Install ASR and media Python dependencies.
  --with-reserves    Clone all retained/candidate upstream projects and apply patches.
  --install-skills   Copy project Skills into the OpenClaw Skills directory.
  -h, --help         Show this help.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --with-media) WITH_MEDIA=1 ;;
    --with-reserves) WITH_RESERVES=1 ;;
    --install-skills) INSTALL_SKILLS=1 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown option: $1" >&2; usage >&2; exit 2 ;;
  esac
  shift
done

cd "$PROJECT_ROOT"

echo "=== Newma Media Studio installer ==="

if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  echo "Python not found: $PYTHON_BIN" >&2
  exit 1
fi

"$PYTHON_BIN" - <<'PY'
import sys
if sys.version_info < (3, 10):
    raise SystemExit(f"Python 3.10+ required; current: {sys.version.split()[0]}")
print(f"Python: {sys.version.split()[0]}")
PY

if ! command -v git >/dev/null 2>&1; then
  echo "Git 2.x is required." >&2
  exit 1
fi

if command -v node >/dev/null 2>&1; then
  echo "Node: $(node --version)"
else
  echo "Node.js 18+ not found; animation and browser publishing remain optional."
fi

if [[ ! -d .venv ]]; then
  "$PYTHON_BIN" -m venv .venv
fi

source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt

if [[ "$WITH_MEDIA" -eq 1 ]]; then
  python -m pip install -r requirements-media.txt
fi

if [[ ! -f configs/paths.local.yaml ]]; then
  cp configs/paths.default.yaml configs/paths.local.yaml
  echo "Created configs/paths.local.yaml"
fi

DASHENG_INSTALL_OUTPUT_ROOT="${DASHENG_OUTPUT_ROOT:-${HOME}/Desktop/自媒体创作}"
mkdir -p \
  "$DASHENG_INSTALL_OUTPUT_ROOT/素材" \
  "$DASHENG_INSTALL_OUTPUT_ROOT/00_范式学习/视频训练" \
  "$DASHENG_INSTALL_OUTPUT_ROOT/05_初稿生成" \
  "$DASHENG_INSTALL_OUTPUT_ROOT/06_转写生产" \
  "$DASHENG_INSTALL_OUTPUT_ROOT/07_发布执行" \
  "$DASHENG_INSTALL_OUTPUT_ROOT/_tmp"

if [[ "$WITH_RESERVES" -eq 1 ]]; then
  python scripts/sync_reserved_projects.py --mode clone
  python scripts/apply_upstream_patches.py --mode apply
fi

if [[ "$INSTALL_SKILLS" -eq 1 ]]; then
  bash install_to_openclaw.sh
fi

python scripts/verify_installation.py

echo
echo "Installation complete."
echo "Activate: source .venv/bin/activate"
echo "Configure: cp .env.template .env"
echo "Diagnose: python scripts/run_mainline_stage.py doctor --strict"
