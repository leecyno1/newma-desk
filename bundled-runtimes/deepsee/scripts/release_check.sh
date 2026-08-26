#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

PYTHON_BIN="${PYTHON_BIN:-python3}"
export CHATLOG_HTTP_BASE="${RELEASE_CHECK_CHATLOG_HTTP_BASE:-http://127.0.0.1:5030}"

echo "== Python syntax =="
"$PYTHON_BIN" -m py_compile \
  app/main.py \
  app/config.py \
  app/routers/sync.py \
  app/services/sync_service.py \
  app/services/deployment_status.py \
  app/services/wx_cli_client.py \
  scripts/install_wechat_local_deps.py

echo "== Frontend script syntax =="
"$PYTHON_BIN" - <<'PY'
from pathlib import Path
import os
import re
import subprocess
import tempfile

path = Path("static/index.html")
size_mb = path.stat().st_size / 1024 / 1024
print(f"index_html_size_mb={size_mb:.2f}")
if size_mb > 5:
    print("warning=static/index.html is still oversized; follow docs/frontend-modularization.md for new UI work")
html = path.read_text(encoding="utf-8", errors="ignore")
scripts = re.findall(r"<script[^>]*>(.*?)</script>", html, flags=re.S | re.I)
with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf-8") as fh:
    fh.write("\n;\n".join(scripts))
    name = fh.name
try:
    subprocess.run(["node", "--check", name], check=True)
    print(f"script_blocks={len(scripts)}")
finally:
    os.unlink(name)
PY

echo "== Shell syntax =="
bash -n scripts/manage.sh scripts/chatlog_sidecar.sh scripts/run_chatlog_5031.sh scripts/release_check.sh

echo "== Focused tests =="
if [[ "${SKIP_PYTEST:-0}" != "1" ]]; then
  if ! "$PYTHON_BIN" - <<'PY' >/dev/null 2>&1
import pytest  # noqa: F401
PY
  then
    echo "pytest is missing. Install dev dependencies with: $PYTHON_BIN -m pip install -r requirements-dev.txt" >&2
    exit 2
  fi
  "$PYTHON_BIN" -m pytest -q \
    tests/test_chatlog_client_timeout.py \
    tests/test_chatlog_media_url.py \
    tests/test_sync_stability.py \
    tests/test_wechat_gateway_trigger_rules.py \
    tests/test_agent_api_auth.py \
    tests/test_local_content_sources.py \
    tests/test_production_guardrails.py
else
  echo "pytest skipped (SKIP_PYTEST=1)"
fi

echo "release_check=ok"
