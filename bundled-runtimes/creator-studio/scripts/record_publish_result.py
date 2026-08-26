#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from canonical_workflow import WorkflowContractError, ensure_runtime_output_dir, write_json


FAILURE_RULES = {
    "authentication": {"retryable": True, "requires_user_action": True, "base_delay_seconds": 0, "required_action": "refresh_account_login"},
    "platform_risk": {"retryable": False, "requires_user_action": True, "base_delay_seconds": 3600, "required_action": "resolve_platform_risk_or_captcha"},
    "rate_limit": {"retryable": True, "requires_user_action": False, "base_delay_seconds": 900, "required_action": "wait_for_rate_limit_window"},
    "validation": {"retryable": True, "requires_user_action": True, "base_delay_seconds": 0, "required_action": "fix_platform_form_or_artifact"},
    "network": {"retryable": True, "requires_user_action": False, "base_delay_seconds": 60, "required_action": "retry_after_network_backoff"},
    "timeout": {"retryable": True, "requires_user_action": False, "base_delay_seconds": 120, "required_action": "retry_after_timeout_backoff"},
    "dependency": {"retryable": True, "requires_user_action": True, "base_delay_seconds": 0, "required_action": "install_or_repair_executor_dependency"},
    "content_rejected": {"retryable": False, "requires_user_action": True, "base_delay_seconds": 0, "required_action": "review_and_reapprove_content"},
    "unknown": {"retryable": False, "requires_user_action": True, "base_delay_seconds": 0, "required_action": "inspect_failure_before_retry"},
}


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content.rstrip() + "\n", encoding="utf-8")


def bool_from_text(value: str | None) -> bool | None:
    if value is None:
        return None
    lowered = value.strip().lower()
    if lowered in {"1", "true", "yes", "y", "ok", "success"}:
        return True
    if lowered in {"0", "false", "no", "n", "fail", "failed"}:
        return False
    raise WorkflowContractError(f"无法解析布尔值：{value}")


def normalize_status(
    status: str | None,
    success: bool | None,
    platform_url: str | None,
    draft_id: str | None,
    draft_url: str | None,
    error: str | None,
) -> str:
    if status:
        return status
    if success is False or error:
        return "failed"
    if draft_id or draft_url:
        return "draft"
    if platform_url:
        return "published"
    return "pending_verification"


def normalize_verification_status(
    *,
    status: str,
    success: bool,
) -> str:
    if not success or status in {"failed", "error"}:
        return "failed"
    return "needs_manual_verification"


def normalize_raw_verification_status(value: Any) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    if normalized in {"verified", "failed", "needs_manual_verification"}:
        return normalized
    raise WorkflowContractError(f"无法解析验真状态：{value}")


def nonnegative_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise WorkflowContractError(f"无法解析非负整数：{value}") from exc
    if parsed < 0:
        raise WorkflowContractError(f"数值不能为负数：{value}")
    return parsed


def classify_failure(raw: dict[str, Any], *, status: str, success: bool, error: Any) -> str | None:
    failed = success is False or status in {"failed", "error"} or status.startswith("blocked_")
    if not failed:
        return None
    explicit = str(raw.get("failure_category") or "").strip()
    if explicit:
        if explicit not in FAILURE_RULES:
            raise WorkflowContractError(f"未知失败分类：{explicit}")
        return explicit
    response = raw.get("platform_response") or raw.get("response") or {}
    try:
        response_text = json.dumps(response, ensure_ascii=False)
    except (TypeError, ValueError):
        response_text = str(response)
    text = f"{status} {error or ''} {response_text}".lower()
    keyword_groups = [
        ("platform_risk", ("captcha", "risk control", "platform risk", "challenge required", "风控", "人机验证")),
        ("rate_limit", ("rate limit", "too many requests", "http 429", "status 429", "频率限制")),
        ("authentication", ("auth required", "authentication", "login", "session expired", "cookie expired", "登录失效")),
        ("timeout", ("timed out", "timeout", "timed_out")),
        ("network", ("connection reset", "connection refused", "network unreachable", "dns", "网络错误")),
        ("validation", ("form validation", "missing_required", "required field", "invalid channel pack", "参数校验")),
        ("dependency", ("missing upstream", "missing cli", "missing executor", "module not found", "binary not found")),
        ("content_rejected", ("content rejected", "policy violation", "prohibited content", "内容违规", "审核拒绝")),
    ]
    for category, keywords in keyword_groups:
        if any(keyword in text for keyword in keywords):
            return category
    return "unknown"


def retry_policy(category: str | None, *, attempt_number: int, override_seconds: int | None) -> dict[str, Any]:
    if not category:
        return {
            "failure_category": None,
            "retryable": False,
            "requires_user_action": False,
            "retry_after_seconds": None,
            "retry_not_before": None,
            "required_action": None,
        }
    rule = FAILURE_RULES[category]
    base_delay = int(rule["base_delay_seconds"])
    delay = override_seconds if override_seconds is not None else min(base_delay * (2 ** max(attempt_number - 1, 0)), 21600)
    not_before = (
        (datetime.now(timezone.utc).astimezone() + timedelta(seconds=delay)).isoformat(timespec="seconds")
        if delay > 0
        else None
    )
    return {
        "failure_category": category,
        "retryable": bool(rule["retryable"]),
        "requires_user_action": bool(rule["requires_user_action"]),
        "retry_after_seconds": delay,
        "retry_not_before": not_before,
        "required_action": rule["required_action"],
    }


def normalize_result(raw: dict[str, Any], *, channel_pack: dict[str, Any], source: str) -> dict[str, Any]:
    success = raw.get("success")
    if success is not None:
        success = bool(success)
    raw_status = str(raw.get("status") or "").strip()
    raw_url = raw.get("url")
    draft_url = raw.get("draft_url")
    platform_url = raw.get("platform_url") or raw_url
    if raw_status in {"draft", "scheduled"} and raw_url and not raw.get("platform_url"):
        draft_url = draft_url or raw_url
        platform_url = None
    draft_id = raw.get("draft_id") or raw.get("msg_id") or raw.get("draft_id_or_url")
    error = raw.get("error")
    status = normalize_status(raw.get("status"), success, platform_url, draft_id, draft_url, error)
    if success is None:
        success = status in {"draft", "published", "scheduled", "manual_uploaded"}
    verification_status = normalize_raw_verification_status(raw.get("verification_status")) or normalize_verification_status(
        status=status,
        success=success,
    )
    failure_category = classify_failure(raw, status=status, success=success, error=error)
    return {
        "schema_version": "1.0",
        "recorded_at": now_iso(),
        "source": source,
        "task_id": channel_pack.get("task_id"),
        "batch_id": channel_pack.get("batch_id"),
        "topic_id": channel_pack.get("topic_id"),
        "variant_id": channel_pack.get("variant_id"),
        "title": channel_pack.get("title"),
        "channel": channel_pack.get("channel"),
        "account_slot": channel_pack.get("account_slot"),
        "platform": raw.get("platform") or channel_pack.get("platform") or channel_pack.get("channel"),
        "success": success,
        "status": status,
        "platform_url": platform_url,
        "draft_url": draft_url,
        "platform_post_id": raw.get("platform_post_id") or raw.get("post_id") or raw.get("note_id"),
        "draft_id": draft_id,
        "account": raw.get("account") or raw.get("account_identifier"),
        "published_or_draft_at": raw.get("published_or_draft_at") or raw.get("published_at") or raw.get("draft_at") or now_iso(),
        "screenshot": raw.get("screenshot") or raw.get("screenshot_path"),
        "platform_response": raw.get("platform_response") or raw.get("response"),
        "error": error,
        "failure_category": failure_category,
        "_retry_after_seconds_override": nonnegative_int(raw.get("retry_after_seconds")),
        "_retry_of_attempt_id": raw.get("retry_of_attempt_id"),
        "verification_status": verification_status,
        "notes": raw.get("notes"),
    }


def load_result(args: argparse.Namespace) -> dict[str, Any]:
    if args.result_file:
        return read_json(Path(args.result_file).expanduser().resolve())
    raw: dict[str, Any] = {
        "success": bool_from_text(args.success),
        "status": args.status,
        "platform": args.platform,
        "platform_url": args.platform_url,
        "platform_post_id": args.platform_post_id,
        "draft_id": args.draft_id,
        "draft_url": args.draft_url,
        "verification_status": args.verification_status,
        "account": args.account,
        "published_or_draft_at": args.published_or_draft_at,
        "screenshot": args.screenshot,
        "error": args.error,
        "failure_category": args.failure_category,
        "retry_after_seconds": args.retry_after_seconds,
        "retry_of_attempt_id": args.retry_of_attempt_id,
        "notes": args.notes,
    }
    return {key: value for key, value in raw.items() if value is not None}


def publish_root_from_pack(pack_path: Path) -> Path:
    for parent in pack_path.parents:
        if parent.name == "channel_packs":
            return parent.parent
    raise WorkflowContractError(f"channel_pack 路径不符合 publish 输出结构：{pack_path}")


def update_pack(
    pack_path: Path,
    result_path: Path,
    result: dict[str, Any],
    *,
    history_path: Path,
    attempt_path: Path,
    retry_request_path: Path,
    retry_request: dict[str, Any],
) -> dict[str, Any]:
    pack = read_json(pack_path)
    pack["publish_result"] = str(result_path.resolve())
    pack["publish_result_history"] = str(history_path.resolve())
    pack["latest_publish_attempt"] = str(attempt_path.resolve())
    pack["publish_attempt_count"] = result["attempt_number"]
    pack["publish_retry_request"] = str(retry_request_path.resolve())
    pack["publish_retry_status"] = retry_request.get("status")
    pack["next_retry_not_before"] = retry_request.get("retry_not_before")
    pack["publish_status"] = result["status"]
    pack["verification_status"] = result["verification_status"]
    pack["platform_url"] = result.get("platform_url")
    pack["draft_url"] = result.get("draft_url")
    pack["draft_id"] = result.get("draft_id")
    pack["last_result_recorded_at"] = result["recorded_at"]
    write_json(pack_path, pack)
    return pack


def result_identity(row: dict[str, Any]) -> tuple[str, str, str]:
    task_id = str(row.get("task_id") or "").strip()
    if task_id:
        return ("task", task_id, "")
    return (
        "legacy",
        str(row.get("topic_id") or "").strip(),
        str(row.get("channel") or "").strip(),
    )


def identity_payload(row: dict[str, Any]) -> dict[str, Any]:
    return {
        key: row.get(key)
        for key in ("task_id", "batch_id", "topic_id", "variant_id", "channel", "account_slot")
        if row.get(key) not in (None, "")
    }


def channel_targets_from_manifest(manifest: dict[str, Any], publish_root: Path) -> list[dict[str, Any]]:
    targets: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for pack in manifest.get("channel_packs") or []:
        key = result_identity(pack)
        if key in {("legacy", "", ""), ("task", "", "")} or key in seen:
            continue
        seen.add(key)
        targets.append({**identity_payload(pack), "title": pack.get("title"), "platform": pack.get("platform")})

    if targets:
        return targets

    packs_root = publish_root / "channel_packs"
    if not packs_root.exists():
        return []
    for pack_path in sorted(packs_root.rglob("channel_pack.json")):
        try:
            pack = read_json(pack_path)
        except (OSError, json.JSONDecodeError):
            continue
        key = result_identity(pack)
        if key in {("legacy", "", ""), ("task", "", "")} or key in seen:
            continue
        seen.add(key)
        targets.append({**identity_payload(pack), "title": pack.get("title"), "platform": pack.get("platform")})
    return targets


def result_is_failed(row: dict[str, Any]) -> bool:
    return row.get("success") is False or str(row.get("status") or "").strip() in {"failed", "error"}


def result_is_published(row: dict[str, Any]) -> bool:
    return (
        bool(row.get("success"))
        and str(row.get("status") or "").strip() == "published"
        and row.get("verification_status") == "verified"
        and bool(row.get("platform_url"))
    )


def result_is_draft(row: dict[str, Any]) -> bool:
    return (
        bool(row.get("success"))
        and str(row.get("status") or "").strip() in {"draft", "scheduled"}
        and row.get("verification_status") == "verified"
        and bool(row.get("draft_id"))
    )


def aggregate_publish_state(publish_root: Path, records: list[dict[str, Any]], manifest: dict[str, Any] | None = None) -> dict[str, Any]:
    manifest = manifest or {}
    targets = channel_targets_from_manifest(manifest, publish_root)
    target_keys = {result_identity(item) for item in targets}
    latest_records: dict[tuple[str, str, str], dict[str, Any]] = {}
    for record in records:
        key = result_identity(record)
        if key == ("legacy", "", ""):
            continue
        latest_records[key] = record

    recorded_keys = set(latest_records)
    pending_keys = target_keys - recorded_keys if target_keys else set()
    failed_records = [item for item in latest_records.values() if result_is_failed(item)]
    published_records = [item for item in latest_records.values() if result_is_published(item)]
    draft_records = [item for item in latest_records.values() if result_is_draft(item)]
    verified_records = [item for item in latest_records.values() if item.get("verification_status") == "verified"]
    manual_verification_records = [
        item
        for item in latest_records.values()
        if item.get("verification_status") == "needs_manual_verification"
    ]
    total_channels = len(target_keys) if target_keys else len(recorded_keys)
    recorded_count = len(recorded_keys & target_keys) if target_keys else len(recorded_keys)
    pending_count = max(total_channels - recorded_count, 0) if target_keys else 0

    if failed_records:
        status = "failed"
    elif recorded_count == 0:
        status = "pending_execution"
    elif pending_count > 0:
        status = "partially_recorded"
    elif manual_verification_records:
        status = "needs_manual_verification"
    elif total_channels > 0 and len(published_records) == total_channels:
        status = "all_published"
    elif total_channels > 0 and len(draft_records) == total_channels:
        status = "all_drafted"
    elif total_channels > 0 and recorded_count == total_channels:
        status = "completed_with_mixed_status"
    else:
        status = "partially_recorded"

    targets_by_key = {result_identity(item): item for item in targets}
    pending_channels = [identity_payload(targets_by_key[key]) for key in sorted(pending_keys)]
    return {
        "status": status,
        "total_channels": total_channels,
        "recorded_count": recorded_count,
        "pending_count": pending_count,
        "failed_count": len(failed_records),
        "draft_count": len(draft_records),
        "published_count": len(published_records),
        "verified_count": len(verified_records),
        "needs_manual_verification_count": len(manual_verification_records),
        "pending_channels": pending_channels,
    }


def update_publish_manifest(publish_root: Path, result: dict[str, Any], result_path: Path) -> None:
    manifest_path = publish_root / "publish_manifest.json"
    if not manifest_path.exists():
        return
    manifest = read_json(manifest_path)
    result_key = result_identity(result)
    results = [item for item in manifest.get("publish_results") or [] if result_identity(item) != result_key]
    results.append({**result, "result_file": str(result_path.resolve())})
    summary = aggregate_publish_state(publish_root, results, manifest)
    manifest["publish_results"] = results
    manifest["publish_summary"] = summary
    manifest["status"] = summary["status"]
    manifest["last_result_recorded_at"] = now_iso()
    write_json(manifest_path, manifest)


def update_execution_manifest(publish_root: Path, result: dict[str, Any]) -> None:
    execution_path = publish_root / "channel_execution_manifest.json"
    if not execution_path.exists():
        return
    manifest = read_json(execution_path)
    for execution in manifest.get("executions") or []:
        if result_identity(execution) == result_identity(result):
            execution["status"] = result["status"]
            execution["result"] = {
                "success": result["success"],
                "platform_url": result.get("platform_url"),
                "draft_url": result.get("draft_url"),
                "draft_id": result.get("draft_id"),
                "verification_status": result.get("verification_status"),
                "attempt_number": result.get("attempt_number"),
                "attempt_id": result.get("attempt_id"),
                "failure_category": result.get("failure_category"),
                "retryable": result.get("retryable"),
                "retry_not_before": result.get("retry_not_before"),
            }
    write_json(execution_path, manifest)


def update_verification_report(publish_root: Path, result: dict[str, Any], result_path: Path) -> dict[str, Any]:
    verification_path = publish_root / "publish_verification_report.json"
    report = read_json(verification_path) if verification_path.exists() else {"stage": "publish", "published_links": []}
    result_key = result_identity(result)
    records = [item for item in report.get("records") or [] if result_identity(item) != result_key]
    records.append({**result, "result_file": str(result_path.resolve())})
    report["records"] = records
    report["published_links"] = [
        {
            **identity_payload(item),
            "platform": item.get("platform"),
            "url": item.get("platform_url"),
            "status": item.get("status"),
        }
        for item in records
        if result_is_published(item)
    ]
    report["draft_records"] = [
        {
            **identity_payload(item),
            "platform": item.get("platform"),
            "draft_id": item.get("draft_id"),
            "draft_url": item.get("draft_url") or (item.get("platform_url") if item.get("status") == "draft" else None),
            "status": item.get("status"),
        }
        for item in records
        if result_is_draft(item)
    ]
    manifest_path = publish_root / "publish_manifest.json"
    publish_manifest = read_json(manifest_path) if manifest_path.exists() else {}
    summary = aggregate_publish_state(publish_root, records, publish_manifest)
    report["publish_summary"] = summary
    report["status"] = summary["status"]
    report["updated_at"] = now_iso()
    write_json(verification_path, report)
    return report


def render_result_markdown(result: dict[str, Any]) -> str:
    return "\n".join(
        [
            f"# 发布结果｜{result.get('title') or result.get('topic_id')}｜{result.get('channel')}",
            "",
            f"- 任务：`{result.get('task_id') or 'legacy'}`",
            f"- 尝试次数：`{result.get('attempt_number') or 1}`",
            f"- 内容版本：`{result.get('variant_id') or 'main'}`",
            f"- 账号槽位：`{result.get('account_slot') or 'slot-1'}`",
            f"- 状态：`{result['status']}`",
            f"- 成功：`{result['success']}`",
            f"- 验真：`{result['verification_status']}`",
            f"- 平台：`{result.get('platform')}`",
            f"- URL：`{result.get('platform_url') or ''}`",
            f"- 草稿 URL：`{result.get('draft_url') or ''}`",
            f"- 草稿 ID：`{result.get('draft_id') or ''}`",
            f"- 账号：`{result.get('account') or ''}`",
            f"- 截图：`{result.get('screenshot') or ''}`",
            f"- 错误：`{result.get('error') or ''}`",
            f"- 失败分类：`{result.get('failure_category') or ''}`",
            f"- 可重试：`{result.get('retryable')}`",
            f"- 最早重试：`{result.get('retry_not_before') or ''}`",
            f"- 人工动作：`{result.get('required_action') or ''}`",
        ]
    )


def build_retry_request(channel_pack_path: Path, channel_pack: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
    if not result_is_failed(result):
        status = "not_required_latest_attempt_succeeded"
    elif not result.get("retryable"):
        status = "blocked_non_retryable"
    elif result.get("requires_user_action"):
        status = "blocked_user_action_required"
    elif result.get("retry_not_before"):
        status = "scheduled_backoff"
    else:
        status = "ready_for_user_confirmation"
    execution_request = channel_pack.get("execution_request")
    commands = channel_pack.get("execution_commands") or {}
    return {
        "schema_version": "1.0",
        "created_at": now_iso(),
        **identity_payload(result),
        "status": status,
        "source_attempt_id": result.get("attempt_id"),
        "source_attempt_number": result.get("attempt_number"),
        "failure_category": result.get("failure_category"),
        "retryable": result.get("retryable"),
        "requires_user_action": result.get("requires_user_action"),
        "required_action": result.get("required_action"),
        "retry_after_seconds": result.get("retry_after_seconds"),
        "retry_not_before": result.get("retry_not_before"),
        "execution_request": execution_request,
        "safe_preview_command": commands.get("safe_executor_command"),
        "confirmed_execution_command": commands.get("confirmed_executor_command"),
        "requires_user_confirmation": True,
        "automatic_execution": False,
        "safety": {
            "does_not_publish": True,
            "does_not_bypass_login_or_captcha": True,
            "does_not_retry_content_rejection": True,
        },
        "source_channel_pack": str(channel_pack_path.resolve()),
    }


def record_result(channel_pack_path: Path, raw_result: dict[str, Any], *, source: str) -> dict[str, Any]:
    channel_pack_path = channel_pack_path.expanduser().resolve()
    channel_pack = read_json(channel_pack_path)
    publish_root = ensure_runtime_output_dir(publish_root_from_pack(channel_pack_path), label="publish result root")
    result = normalize_result(raw_result, channel_pack=channel_pack, source=source)
    result_dir = channel_pack_path.parent
    history_path = result_dir / "publish_result_history.json"
    history = read_json(history_path) if history_path.exists() else {"schema_version": "1.0", "attempts": []}
    attempts = history.get("attempts") if isinstance(history, dict) else None
    attempts = attempts if isinstance(attempts, list) else []
    result["attempt_number"] = len(attempts) + 1
    attempt_owner = str(result.get("task_id") or f"{result.get('topic_id')}:{result.get('channel')}")
    result["attempt_id"] = f"{attempt_owner}:attempt-{result['attempt_number']:04d}"
    retry_override = result.pop("_retry_after_seconds_override", None)
    explicit_retry_of = result.pop("_retry_of_attempt_id", None)
    result["retry_of_attempt_id"] = explicit_retry_of or (attempts[-1].get("attempt_id") if attempts else None)
    result.update(retry_policy(result.get("failure_category"), attempt_number=result["attempt_number"], override_seconds=retry_override))
    attempts_dir = result_dir / "publish_results"
    attempt_path = attempts_dir / f"attempt-{result['attempt_number']:04d}.json"
    result_path = result_dir / "publish_result.json"
    result_md_path = result_dir / "publish_result.md"
    retry_request_path = result_dir / "publish_retry_request.json"
    retry_request = build_retry_request(channel_pack_path, channel_pack, result)
    write_json(attempt_path, result)
    write_json(result_path, result)
    write_text(result_md_path, render_result_markdown(result))
    write_json(retry_request_path, retry_request)
    history = {
        "schema_version": "1.0",
        "task": identity_payload(result),
        "latest_attempt_number": result["attempt_number"],
        "attempts": [*attempts, {**result, "attempt_file": str(attempt_path.resolve())}],
    }
    write_json(history_path, history)
    update_pack(
        channel_pack_path,
        result_path,
        result,
        history_path=history_path,
        attempt_path=attempt_path,
        retry_request_path=retry_request_path,
        retry_request=retry_request,
    )
    update_publish_manifest(publish_root, result, result_path)
    update_execution_manifest(publish_root, result)
    verification = update_verification_report(publish_root, result, result_path)
    return {
        "status": "recorded",
        "will_not_publish": True,
        "channel_pack": str(channel_pack_path),
        "publish_result": str(result_path.resolve()),
        "publish_result_markdown": str(result_md_path.resolve()),
        "publish_result_history": str(history_path.resolve()),
        "publish_attempt": str(attempt_path.resolve()),
        "publish_retry_request": str(retry_request_path.resolve()),
        "publish_retry_status": retry_request["status"],
        "attempt_number": result["attempt_number"],
        "attempt_id": result["attempt_id"],
        "failure_category": result.get("failure_category"),
        "retryable": result.get("retryable"),
        "requires_user_action": result.get("requires_user_action"),
        "retry_not_before": result.get("retry_not_before"),
        "verification_status": result["verification_status"],
        "publish_verification_status": verification.get("status"),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Record a platform publish/draft result back into a Newma channel pack.")
    parser.add_argument("--channel-pack", required=True)
    parser.add_argument("--result-file")
    parser.add_argument("--source", default="manual_or_executor")
    parser.add_argument("--success")
    parser.add_argument("--status")
    parser.add_argument("--platform")
    parser.add_argument("--platform-url")
    parser.add_argument("--platform-post-id")
    parser.add_argument("--draft-id")
    parser.add_argument("--draft-url")
    parser.add_argument("--verification-status")
    parser.add_argument("--account")
    parser.add_argument("--published-or-draft-at")
    parser.add_argument("--screenshot")
    parser.add_argument("--error")
    parser.add_argument("--failure-category", choices=sorted(FAILURE_RULES))
    parser.add_argument("--retry-after-seconds", type=int)
    parser.add_argument("--retry-of-attempt-id")
    parser.add_argument("--notes")
    args = parser.parse_args()

    payload = record_result(Path(args.channel_pack), load_result(args), source=args.source)
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
