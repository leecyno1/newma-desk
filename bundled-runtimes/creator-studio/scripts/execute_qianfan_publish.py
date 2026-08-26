#!/usr/bin/env python3
"""Preview or execute one video publish through the local Qianfan API."""

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


def normalize_accounts(response: Any) -> list[dict[str, Any]]:
    rows = response.get("data", response) if isinstance(response, dict) else response
    normalized: list[dict[str, Any]] = []
    for row in rows if isinstance(rows, list) else []:
        if isinstance(row, list):
            values = row + [None] * 6
            normalized.append(
                {"id": values[0], "type": values[1], "file_path": values[2], "name": values[3], "status": values[4]}
            )
        elif isinstance(row, dict):
            normalized.append(
                {
                    "id": row.get("id"),
                    "type": row.get("type") or row.get("platform_type") or row.get("platformId"),
                    "file_path": row.get("filePath") or row.get("cookie_path") or row.get("cookiePath"),
                    "name": row.get("userName") or row.get("name") or row.get("label") or row.get("account_name"),
                    "status": row.get("status"),
                }
            )
    return normalized


def resolve_account(accounts: list[dict[str, Any]], selector: dict[str, Any], platform_id: int) -> dict[str, Any] | None:
    compatible = [row for row in accounts if str(row.get("type")) == str(platform_id)]
    account_id = selector.get("account_id")
    if account_id not in (None, ""):
        return next((row for row in compatible if str(row.get("id")) == str(account_id)), None)
    account_name = str(selector.get("account_name") or "").strip()
    if account_name:
        return next((row for row in compatible if account_name in {str(row.get("name") or ""), str(row.get("file_path") or "")}), None)
    return None


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
    post_payload = dict(request_payload["post_video_payload"])
    api_base = expand_api_base(str(request_payload.get("api_base") or ""))
    base.update({"platform": request_payload.get("platform"), "request": str(request_path), "api_base": api_base})
    if not confirm_execute:
        return {
            **base,
            "success": True,
            "status": "ready_for_user_confirmation",
            "will_not_publish": True,
            "endpoint": f"{api_base}/postVideo",
            "account_selector": request_payload.get("account_selector"),
        }

    client = http_client or default_http_client
    try:
        account_response = client("GET", f"{api_base}/getAccounts", None, min(timeout_seconds, 30))
        accounts = normalize_accounts(account_response)
        account = resolve_account(accounts, request_payload.get("account_selector") or {}, int(post_payload["type"]))
        if not account or not account.get("file_path"):
            return {
                **base,
                "success": False,
                "status": "blocked_qianfan_account_mapping",
                "will_not_publish": True,
                "compatible_account_count": sum(1 for row in accounts if str(row.get("type")) == str(post_payload["type"])),
                "error": "No exact Qianfan account mapping for this account slot. Configure qianfan_account_id or qianfan_account_name in a local account registry.",
            }
        post_payload["accountList"] = [account["file_path"]]
        response = client("POST", f"{api_base}/postVideo", post_payload, timeout_seconds)
    except (OSError, TimeoutError, urllib.error.URLError, urllib.error.HTTPError, json.JSONDecodeError) as exc:
        return {**base, "success": False, "status": "blocked_qianfan_api_unavailable", "will_not_publish": True, "error": str(exc)}

    response_code = response.get("code") if isinstance(response, dict) else None
    success = response_code in (None, 0, 200)
    return {
        **base,
        "success": success,
        "status": "pending_verification" if success else "failed",
        "will_not_publish": False,
        "verification_status": "needs_manual_verification" if success else "failed",
        "account": request_payload.get("account_selector"),
        "platform_response": response,
        "error": None if success else str(response.get("msg") or "Qianfan publish failed"),
    }


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
