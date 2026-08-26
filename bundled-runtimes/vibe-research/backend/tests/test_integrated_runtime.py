"""Research 独立版 / Desk 集成版的启动边界。"""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys


_BACKEND = Path(__file__).resolve().parents[1]
_PROBE = r"""
import json
import sys

import portfolio

scheduler_calls = []
portfolio.start_scheduler = lambda interval: scheduler_calls.append(interval)

import app

print(json.dumps({
    "integrated": app._INTEGRATED_DOMAIN_RUNTIME,
    "chat_route": any(getattr(route, "path", None) == "/api/chat" for route in app.app.routes),
    "chat_imported": "chat" in sys.modules,
    "cli_imported": "cli_runtime" in sys.modules,
    "scheduler_calls": scheduler_calls,
}))
"""


def _probe(*, integrated: bool) -> dict:
    env = os.environ.copy()
    env.pop("NEWMA_DESK_INTEGRATED_DOMAIN_RUNTIME", None)
    env.pop("VIBEDESK_INTEGRATED_DOMAIN_RUNTIME", None)
    if integrated:
        env["NEWMA_DESK_INTEGRATED_DOMAIN_RUNTIME"] = "1"
    result = subprocess.run(
        [sys.executable, "-c", _PROBE],
        cwd=_BACKEND,
        env=env,
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )
    return json.loads(result.stdout.strip().splitlines()[-1])


def test_integrated_runtime_uses_desk_agent_and_scheduler():
    state = _probe(integrated=True)

    assert state == {
        "integrated": True,
        "chat_route": False,
        "chat_imported": False,
        "cli_imported": False,
        "scheduler_calls": [],
    }


def test_standalone_runtime_keeps_chat_and_scheduler_without_eager_model_imports():
    state = _probe(integrated=False)

    assert state == {
        "integrated": False,
        "chat_route": True,
        "chat_imported": False,
        "cli_imported": False,
        "scheduler_calls": [1800],
    }
