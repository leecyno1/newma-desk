#!/usr/bin/env python3
"""Validate or enqueue one Qianfan draft through the local Qianfan API."""

from __future__ import annotations

import argparse
import json
import os
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from build_video_upload_package import build_package


HttpClient = Callable[[str, str, dict[str, Any] | None, int], Any]


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def default_http_client(method: str, url: str, payload: dict[str, Any] | None, timeout: int) -> Any:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload is not None else None
    request = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        text = response.read().decode("utf-8")
        return json.loads(text) if text.strip() else {}


def expand_api_base(raw: str) -> str:
    configured = os.getenv("QIANFAN_API_BASE")
    if configured:
        return configured.rstrip("/")
    if raw.startswith("${QIANFAN_API_BASE"):
        return "http://127.0.0.1:5409"
    return raw.rstrip("/")


def ledger_path_for(request_path: Path) -> Path:
    for parent in request_path.parents:
        if (parent / "account_routes.json").is_file():
            return parent / "qianfan_enqueue_ledger.json"
    return request_path.parent / "qianfan_enqueue_ledger.json"


def load_ledger(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {"schema_version": "newma.qianfan_enqueue_ledger.v1", "records": {}}
    try:
        payload = read_json(path)
    except (OSError, json.JSONDecodeError):
        return {"schema_version": "newma.qianfan_enqueue_ledger.v1", "records": {}}
    if not isinstance(payload.get("records"), dict):
        payload["records"] = {}
    return payload


def idempotency_keys(request_payload: dict[str, Any], account_ids: list[Any]) -> list[str]:
    run_id = str(request_payload.get("run_id") or "unknown-run")
    task_id = str(request_payload.get("task_id") or request_payload.get("qianfan_draft_id") or "unknown-task")
    revision = str(request_payload.get("content_revision") or "unversioned")
    return [f"{run_id}:{task_id}:{account_id}:{revision}" for account_id in sorted(account_ids, key=str)]


def validation_data(response: Any) -> dict[str, Any]:
    if not isinstance(response, dict) or response.get("code") not in (None, 0, 200):
        return {"valid": False, "errors": [str((response or {}).get("msg") or "草稿校验失败")], "account_ids": []}
    data = response.get("data")
    return data if isinstance(data, dict) else {"valid": False, "errors": ["草稿校验响应无效"], "account_ids": []}


def build_result(
    channel_pack: Path,
    *,
    confirm_execute: bool,
    timeout_seconds: int = 14_400,
    http_client: HttpClient | None = None,
) -> dict[str, Any]:
    package = build_package(channel_pack)
    base = {
        "schema_version": "dasheng.qianfan_publish_result.v1",
        "created_at": now_iso(),
        "adapter": "qianfan-local-api",
        "source_channel_pack": str(channel_pack.resolve()),
        "confirm_execute": confirm_execute,
        "requires_user_confirmation": True,
    }
    if package.get("status") != "ready":
        return {**base, "success": False, "status": "blocked_invalid_channel_pack", "will_not_publish": True, "errors": package.get("errors") or []}

    request_path = Path(package["outputs"]["qianfan_video_request"])
    request_payload = read_json(request_path)
    api_base = expand_api_base(str(request_payload.get("api_base") or ""))
    draft_id = request_payload.get("qianfan_draft_id")
    base.update(
        {
            "platform": request_payload.get("platform"),
            "request": str(request_path),
            "api_base": api_base,
            "qianfan_draft_id": draft_id,
        }
    )
    if draft_id in (None, ""):
        return {
            **base,
            "success": False,
            "status": "blocked_missing_qianfan_draft",
            "will_not_publish": True,
            "error": "缺少 qianfan_draft_id，请先从 Newma 平台包同步千帆草稿。",
        }

    client = http_client or default_http_client
    try:
        validation_response = client(
            "GET",
            f"{api_base}/api/v2/drafts/{draft_id}/validate",
            None,
            min(timeout_seconds, 30),
        )
    except (OSError, TimeoutError, urllib.error.URLError, urllib.error.HTTPError, json.JSONDecodeError) as exc:
        return {**base, "success": False, "status": "blocked_qianfan_api_unavailable", "will_not_publish": True, "error": str(exc)}

    validation = validation_data(validation_response)
    if validation.get("valid") is not True:
        return {
            **base,
            "success": False,
            "status": "blocked_qianfan_draft_validation",
            "will_not_publish": True,
            "draft_validation": validation,
            "errors": validation.get("errors") or [],
        }
    if not confirm_execute:
        return {
            **base,
            "success": True,
            "status": "ready_for_user_confirmation",
            "will_not_publish": True,
            "endpoint": f"{api_base}/api/v2/drafts/batch-publish",
            "draft_validation": validation,
        }

    keys = idempotency_keys(request_payload, list(validation.get("account_ids") or []))
    ledger_path = ledger_path_for(request_path)
    ledger = load_ledger(ledger_path)
    request_key = "|".join(keys)
    existing = ledger["records"].get(request_key)
    if isinstance(existing, dict):
        return {
            **base,
            **existing,
            "success": True,
            "status": "already_queued",
            "will_not_publish": False,
            "idempotency_keys": keys,
            "draft_validation": validation,
            "ledger": str(ledger_path),
        }

    enqueue_payload = {"draft_ids": [int(draft_id)], "idempotency_keys": keys}
    try:
        response = client(
            "POST",
            f"{api_base}/api/v2/drafts/batch-publish",
            enqueue_payload,
            timeout_seconds,
        )
    except (OSError, TimeoutError, urllib.error.URLError, urllib.error.HTTPError, json.JSONDecodeError) as exc:
        return {**base, "success": False, "status": "blocked_qianfan_api_unavailable", "will_not_publish": True, "error": str(exc)}

    response_code = response.get("code") if isinstance(response, dict) else None
    task_ids = list(response.get("task_ids") or []) if isinstance(response, dict) else []
    batch_ids = list(response.get("batch_ids") or []) if isinstance(response, dict) else []
    failed = list(response.get("failed") or []) if isinstance(response, dict) else []
    success = response_code in (None, 0, 200) and bool(task_ids) and not failed
    result = {
        **base,
        "success": success,
        "status": "queued_for_publish" if success else "failed",
        "will_not_publish": False,
        "verification_status": "needs_manual_verification" if success else "failed",
        "draft_validation": validation,
        "idempotency_keys": keys,
        "task_ids": task_ids,
        "batch_ids": batch_ids,
        "failed": failed,
        "tasks_url": f"{api_base}/api/v2/tasks",
        "history_urls": [f"{api_base}/api/v2/history/{batch_id}" for batch_id in batch_ids],
        "platform_response": response,
        "error": None if success else str(response.get("msg") or "Qianfan publish failed"),
    }
    if success:
        ledger["records"][request_key] = {
            "queued_at": now_iso(),
            "qianfan_draft_id": draft_id,
            "task_ids": task_ids,
            "batch_ids": batch_ids,
            "tasks_url": result["tasks_url"],
            "history_urls": result["history_urls"],
            "platform_response": response,
            "verification_status": "needs_manual_verification",
        }
        ledger["updated_at"] = now_iso()
        write_json(ledger_path, ledger)
        result["ledger"] = str(ledger_path)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--channel-pack", required=True)
    parser.add_argument("--confirm-execute", action="store_true")
    parser.add_argument("--timeout-seconds", type=int, default=14_400)
    parser.add_argument("--output")
    args = parser.parse_args()
    result = build_result(
        Path(args.channel_pack).expanduser().resolve(),
        confirm_execute=args.confirm_execute,
        timeout_seconds=max(1, args.timeout_seconds),
    )
    if args.output:
        write_json(Path(args.output).expanduser().resolve(), result)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
