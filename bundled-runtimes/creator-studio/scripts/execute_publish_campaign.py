#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from path_config import get_project_root


ROOT = get_project_root()


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def run_task(execution_request: Path, *, confirm_execute: bool) -> dict[str, Any]:
    command = [sys.executable, str(ROOT / "scripts" / "execute_publish_request.py"), "--execution-request", str(execution_request)]
    if confirm_execute:
        command.append("--confirm-execute")
    completed = subprocess.run(command, cwd=str(ROOT), capture_output=True, text=True, check=False)
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError:
        payload = {
            "success": False,
            "status": "invalid_executor_output",
            "stderr": completed.stderr[-4000:],
        }
    payload["command_returncode"] = completed.returncode
    return payload


def execute_campaign(campaign_path: Path, *, confirm_execute: bool) -> dict[str, Any]:
    campaign = read_json(campaign_path)
    account_auth_status = str((campaign.get("summary") or {}).get("account_auth_status") or "not_checked")
    if confirm_execute and account_auth_status != "valid":
        return {
            "schema_version": "dasheng.publish.campaign_execution.v1",
            "created_at": now_iso(),
            "source_campaign": str(campaign_path.resolve()),
            "confirm_execute": True,
            "will_not_publish": True,
            "status": "blocked_account_auth_not_valid",
            "account_auth_status": account_auth_status,
            "results": [],
            "summary": {
                "requested_task_count": len(campaign.get("tasks") or []),
                "processed_task_count": 0,
                "success_count": 0,
                "blocked_or_failed_count": len(campaign.get("tasks") or []),
            },
        }
    results = []
    for task in campaign.get("tasks") or []:
        request = Path(str(task.get("execution_request") or "")).expanduser()
        if not request.exists():
            results.append({"task_id": task.get("task_id"), "status": "missing_execution_request", "success": False})
            continue
        result = run_task(request.resolve(), confirm_execute=confirm_execute)
        results.append({"task_id": task.get("task_id"), "channel": task.get("channel"), "account_slot": task.get("account_slot"), **result})
        if confirm_execute and result.get("status") in {"blocked_auth_required", "failed", "blocked"}:
            break
    ready_count = sum(1 for row in results if row.get("status") == "ready_for_user_confirmation")
    blocked_or_failed_count = sum(
        1
        for row in results
        if row.get("success") is False
        or str(row.get("status") or "").startswith(("blocked", "failed", "missing", "invalid"))
    )
    return {
        "schema_version": "dasheng.publish.campaign_execution.v1",
        "created_at": now_iso(),
        "source_campaign": str(campaign_path.resolve()),
        "confirm_execute": confirm_execute,
        "will_not_publish": not confirm_execute,
        "account_auth_status": account_auth_status,
        "status": "execution_attempted" if confirm_execute else "dry_run_completed",
        "results": results,
        "summary": {
            "requested_task_count": len(campaign.get("tasks") or []),
            "processed_task_count": len(results),
            "ready_count": ready_count,
            "success_count": sum(1 for row in results if row.get("success") is True),
            "blocked_or_failed_count": blocked_or_failed_count,
            "attention_required_count": len(results) - ready_count - sum(1 for row in results if row.get("success") is True) - blocked_or_failed_count,
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Dry-run or explicitly execute every task in a Publish campaign.")
    parser.add_argument("--campaign", required=True)
    parser.add_argument("--confirm-execute", action="store_true", help="Actually invoke guarded platform routes; requires current-session user confirmation.")
    parser.add_argument("--output")
    args = parser.parse_args()
    campaign_path = Path(args.campaign).expanduser().resolve()
    report = execute_campaign(campaign_path, confirm_execute=args.confirm_execute)
    output = Path(args.output).expanduser().resolve() if args.output else campaign_path.parent / "publish_campaign_execution.json"
    write_json(output, report)
    report["output"] = str(output)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
