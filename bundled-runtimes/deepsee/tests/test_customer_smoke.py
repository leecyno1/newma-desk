from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = PROJECT_ROOT / "scripts" / "customer_smoke.py"


def test_customer_smoke_help_documents_low_resource_options():
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--help"],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
        timeout=10,
    )
    assert result.returncode == 0, result.stdout
    assert "--max-rss-mb" in result.stdout
    assert "--iterations" in result.stdout
    assert "--base-url" in result.stdout


def test_customer_smoke_report_mode_parses_ready_payload(tmp_path):
    payload = {
        "status": "ok",
        "healthy": True,
        "checks": [{"name": "database", "status": "ok"}],
    }
    ready_file = tmp_path / "ready.json"
    ready_file.write_text(json.dumps(payload), encoding="utf-8")
    out_file = tmp_path / "report.json"
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--offline-ready-json",
            str(ready_file),
            "--output",
            str(out_file),
            "--max-rss-mb",
            "250",
        ],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
        timeout=10,
    )
    assert result.returncode == 0, result.stdout
    report = json.loads(out_file.read_text(encoding="utf-8"))
    assert report["ready"]["healthy"] is True
    assert report["thresholds"]["max_rss_mb"] == 250
    assert report["process"] == {"pid": None, "rss_mb": None, "inspected": False}
    assert report["status"] == "ok"
