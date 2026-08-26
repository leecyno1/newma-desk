#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import shutil
import socket
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from path_config import get_project_root
from publish_accounts import initialize_session_storage, load_registry, qianfan_data_dir
from publish_window_policy import resolve_publish_window, window_environment


ROOT = get_project_root()
QIANFAN_ROOT = ROOT / "vendor" / "reserved" / "publish" / "qianfan-sync"
BACKEND_PORT = 5409
FRONTEND_PORT = 5173


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def port_open(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as connection:
        connection.settimeout(0.2)
        return connection.connect_ex(("127.0.0.1", port)) == 0


def console_plan() -> dict[str, Any]:
    registry = load_registry()
    data_dir = qianfan_data_dir(registry)
    backend_python = QIANFAN_ROOT / "backend" / ".venv" / "bin" / "python"
    backend_app = QIANFAN_ROOT / "backend" / "app.py"
    frontend_dir = QIANFAN_ROOT / "frontend"
    npm = shutil.which("npm")
    backend_command = [str(backend_python), str(backend_app)]
    frontend_command = [npm or "npm", "run", "dev", "--", "--host", "127.0.0.1", "--port", str(FRONTEND_PORT)]
    missing = []
    if not backend_python.exists():
        missing.append(str(backend_python))
    if not backend_app.exists():
        missing.append(str(backend_app))
    if not (frontend_dir / "node_modules").exists():
        missing.append(str(frontend_dir / "node_modules"))
    if not npm:
        missing.append("npm")
    browser_window = resolve_publish_window()
    return {
        "schema_version": "dasheng.publish.console.v1",
        "created_at": now_iso(),
        "upstream": str(QIANFAN_ROOT),
        "data_dir": str(data_dir),
        "backend": {
            "url": f"http://127.0.0.1:{BACKEND_PORT}",
            "command": backend_command,
            "cwd": str(QIANFAN_ROOT / "backend"),
            "already_running": port_open(BACKEND_PORT),
        },
        "frontend": {
            "url": f"http://127.0.0.1:{FRONTEND_PORT}",
            "command": frontend_command,
            "cwd": str(frontend_dir),
            "already_running": port_open(FRONTEND_PORT),
        },
        "missing_dependencies": missing,
        "cookie_contents_read": False,
        "will_not_publish": True,
        "browser_window": browser_window,
    }


def launch(plan: dict[str, Any]) -> dict[str, Any]:
    if plan["missing_dependencies"]:
        plan["status"] = "blocked_missing_dependencies"
        return plan
    registry = load_registry()
    initialization = initialize_session_storage(registry)
    data_dir = Path(str(plan["data_dir"]))
    logs_dir = data_dir / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    logs_dir.chmod(0o700)
    environment = os.environ.copy()
    environment["SAU_DATA_DIR"] = str(data_dir)
    environment["SAU_PORT"] = str(BACKEND_PORT)
    environment.update(window_environment(plan["browser_window"]))
    started = []
    for service in ("backend", "frontend"):
        row = plan[service]
        if row["already_running"]:
            continue
        log_path = logs_dir / f"publish-console-{service}.log"
        log_handle = log_path.open("ab")
        process = subprocess.Popen(
            row["command"],
            cwd=row["cwd"],
            env=environment,
            stdin=subprocess.DEVNULL,
            stdout=log_handle,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        log_handle.close()
        row["pid"] = process.pid
        row["log"] = str(log_path)
        started.append(service)
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        backend_ready = port_open(BACKEND_PORT)
        frontend_ready = port_open(FRONTEND_PORT)
        if backend_ready and frontend_ready:
            break
        time.sleep(0.25)
    plan["initialization"] = initialization
    plan["backend"]["ready"] = port_open(BACKEND_PORT)
    plan["frontend"]["ready"] = port_open(FRONTEND_PORT)
    plan["started_services"] = started
    plan["status"] = (
        "running"
        if plan["backend"]["ready"] and plan["frontend"]["ready"]
        else "started_with_attention_required"
    )
    return plan


def main() -> None:
    parser = argparse.ArgumentParser(description="Start the local Qianfan Publish account-management console.")
    parser.add_argument("--confirm-start", action="store_true", help="Start backend and frontend services. Default is a read-only plan.")
    parser.add_argument("--output", help="Optional JSON report path.")
    args = parser.parse_args()
    plan = console_plan()
    if args.confirm_start:
        plan = launch(plan)
    else:
        plan["status"] = "ready_to_start" if not plan["missing_dependencies"] else "blocked_missing_dependencies"
    if args.output:
        output = Path(args.output).expanduser().resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(plan, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
