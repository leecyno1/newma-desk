from __future__ import annotations

import json
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
CHATLOG_ROOT = PROJECT_ROOT / "third_party" / "chatlog"


def test_chatlog_source_and_license_are_vendored():
    assert (CHATLOG_ROOT / "go.mod").is_file()
    assert (CHATLOG_ROOT / "go.sum").is_file()
    assert (CHATLOG_ROOT / "main.go").is_file()
    assert (CHATLOG_ROOT / "internal" / "chatlog" / "app.go").is_file()
    assert "MIT License" in (CHATLOG_ROOT / "LICENSE").read_text(encoding="utf-8")
    assert (CHATLOG_ROOT / "DISCLAIMER.md").is_file()
    assert (CHATLOG_ROOT / "DEEPSEE_VENDOR.md").is_file()


def test_chatlog_installer_builds_vendored_source_instead_of_downloading_it():
    installer = (PROJECT_ROOT / "scripts" / "install_wechat_local_deps.py").read_text(encoding="utf-8")
    sidecar = (PROJECT_ROOT / "scripts" / "chatlog_sidecar.sh").read_text(encoding="utf-8")
    runner = (PROJECT_ROOT / "scripts" / "run_chatlog_5031.sh").read_text(encoding="utf-8")
    deps = json.loads((PROJECT_ROOT / "deps" / "wechat-local-deps.json").read_text(encoding="utf-8"))

    assert 'ROOT / "third_party" / "chatlog"' in installer
    assert "build_vendored_chatlog" in installer
    assert "go install github.com/sjzar/chatlog" not in sidecar
    assert '"$ROOT_DIR/scripts/build_chatlog.sh"' in runner
    assert "configured CHATLOG_BIN is unavailable, falling back to vendored source" in runner
    assert deps["chatlog_alpha"]["source"] == "third_party/chatlog"


def test_chatlog_build_output_stays_outside_vendored_source():
    build_script = (PROJECT_ROOT / "scripts" / "build_chatlog.sh").read_text(encoding="utf-8")
    assert 'SOURCE_DIR="${CHATLOG_SOURCE_DIR:-$ROOT_DIR/third_party/chatlog}"' in build_script
    assert 'OUTPUT_DIR="${CHATLOG_BUILD_DIR:-$ROOT_DIR/.local/chatlog/bin}"' in build_script
