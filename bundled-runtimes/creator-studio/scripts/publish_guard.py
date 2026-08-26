#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from canonical_workflow import WorkflowContractError, ensure_stage_manifest
from record_publish_result import aggregate_publish_state, identity_payload, result_identity, result_is_draft, result_is_published


CORE_RESULT_FIELDS = {
    "attempt_id",
    "attempt_number",
    "failure_category",
    "retryable",
    "retry_not_before",
    "task_id",
    "batch_id",
    "topic_id",
    "variant_id",
    "channel",
    "account_slot",
    "platform",
    "success",
    "status",
    "platform_url",
    "draft_url",
    "platform_post_id",
    "draft_id",
    "account",
    "screenshot",
    "error",
    "verification_status",
}


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content.rstrip() + "\n", encoding="utf-8")


def publish_root_from_manifest(path: Path) -> Path:
    return path.expanduser().resolve().parent


def latest_records(records: list[dict[str, Any]]) -> dict[tuple[str, str, str], dict[str, Any]]:
    latest: dict[tuple[str, str, str], dict[str, Any]] = {}
    for record in records:
        key = result_identity(record)
        if key == ("legacy", "", ""):
            continue
        latest[key] = record
    return latest


def comparable_record(record: dict[str, Any]) -> dict[str, Any]:
    ignored = {"recorded_at", "result_file"}
    return {key: value for key, value in record.items() if key not in ignored}


def records_match(left: list[dict[str, Any]], right: list[dict[str, Any]]) -> bool:
    left_latest = latest_records(left)
    right_latest = latest_records(right)
    if set(left_latest) != set(right_latest):
        return False
    return all(comparable_record(left_latest[key]) == comparable_record(right_latest[key]) for key in left_latest)


def result_file_issues(record: dict[str, Any]) -> list[str]:
    result_file = record.get("result_file")
    if not result_file:
        return ["missing_result_file"]
    result_path = Path(str(result_file)).expanduser()
    if not result_path.exists():
        return ["missing_result_file_on_disk"]
    try:
        file_record = read_json(result_path)
    except (OSError, json.JSONDecodeError):
        return ["invalid_result_file_json"]
    for field in CORE_RESULT_FIELDS:
        if record.get(field) != file_record.get(field):
            return ["result_file_content_mismatch"]
    return []


def target_rows(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for pack in manifest.get("channel_packs") or []:
        key = result_identity(pack)
        if key == ("legacy", "", "") or key in seen:
            continue
        seen.add(key)
        rows.append(
            {
                **identity_payload(pack),
                "title": pack.get("title"),
                "status": pack.get("status"),
                "pack_manifest": pack.get("pack_manifest"),
            }
        )
    return rows


def classify_record(record: dict[str, Any]) -> tuple[str, list[str]]:
    issues: list[str] = []
    status = str(record.get("status") or "").strip()
    verification_status = record.get("verification_status")
    if record.get("success") is False or status in {"failed", "error"}:
        return "failed", issues
    if status == "published":
        if not record.get("platform_url"):
            issues.append("published_missing_platform_url")
        if verification_status != "verified":
            issues.append("published_not_verified")
        return ("published" if not issues else "needs_manual_verification"), issues
    if status in {"draft", "scheduled"}:
        if not record.get("draft_id"):
            issues.append("draft_missing_draft_id")
        if verification_status != "verified":
            issues.append("draft_not_verified")
        if record.get("platform_url") and not record.get("draft_url"):
            issues.append("draft_has_platform_url_without_draft_url")
        return ("draft" if not issues else "needs_manual_verification"), issues
    if verification_status == "needs_manual_verification":
        issues.append("needs_manual_verification")
        return "needs_manual_verification", issues
    if status == "manual_uploaded":
        issues.append("manual_uploaded_requires_verification")
        return "needs_manual_verification", issues
    issues.append(f"unrecognized_status:{status or 'empty'}")
    return "needs_manual_verification", issues


def expected_published_links(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            **identity_payload(item),
            "platform": item.get("platform"),
            "url": item.get("platform_url"),
            "status": item.get("status"),
        }
        for item in records
        if result_is_published(item)
    ]


def expected_draft_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
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


def simplified_links(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        rows,
        key=lambda item: (
            str(item.get("task_id") or ""),
            str(item.get("topic_id") or ""),
            str(item.get("channel") or ""),
            str(item.get("account_slot") or ""),
            str(item.get("url") or item.get("draft_id") or ""),
        ),
    )


def build_guard_report(publish_manifest_path: Path) -> dict[str, Any]:
    publish_manifest_path = publish_manifest_path.expanduser().resolve()
    manifest = ensure_stage_manifest(publish_manifest_path, "publish")
    publish_root = publish_root_from_manifest(publish_manifest_path)
    verification_path = publish_root / "publish_verification_report.json"
    verification_exists = verification_path.exists()
    verification = read_json(verification_path) if verification_exists else {}
    manifest_records = manifest.get("publish_results") or []
    verification_records = verification.get("records") or []
    if not isinstance(manifest_records, list) or not isinstance(verification_records, list):
        raise WorkflowContractError("publish_results/records 必须是列表")
    records = manifest_records

    targets = target_rows(manifest)
    target_keys = {result_identity(item) for item in targets}
    latest = latest_records(records)
    pending_keys = sorted(target_keys - set(latest))
    unexpected_record_keys = sorted(set(latest) - target_keys) if target_keys else []

    channel_checks = []
    blocking_issue_count = 0
    pending_count = 0
    for row in targets:
        key = result_identity(row)
        record = latest.get(key)
        if not record:
            channel_checks.append({**row, "guard_status": "pending_execution", "issues": ["missing_publish_result"]})
            pending_count += 1
            continue
        guard_status, issues = classify_record(record)
        issues = [*issues, *result_file_issues(record)]
        blocking_issue_count += len(issues)
        channel_checks.append(
            {
                **row,
                "guard_status": guard_status,
                "issues": issues,
                "publish_status": record.get("status"),
                "verification_status": record.get("verification_status"),
                "platform_url": record.get("platform_url"),
                "draft_id": record.get("draft_id"),
                "draft_url": record.get("draft_url"),
                "result_file": record.get("result_file"),
            }
        )

    expected_summary = aggregate_publish_state(publish_root, records, manifest)
    manifest_summary = manifest.get("publish_summary") or {}
    verification_summary = verification.get("publish_summary") or {}
    summary_mismatch = bool(manifest_summary) and manifest_summary != expected_summary
    verification_summary_mismatch = bool(verification_summary) and verification_summary != expected_summary
    manifest_verification_records_mismatch = verification_exists and not records_match(manifest_records, verification_records)
    manifest_verification_summary_mismatch = (
        bool(manifest_summary)
        and bool(verification_summary)
        and manifest_summary != verification_summary
    )

    expected_links = simplified_links(expected_published_links(records))
    actual_links = simplified_links(verification.get("published_links") or [])
    published_links_mismatch = bool(verification) and actual_links != expected_links

    expected_drafts = simplified_links(expected_draft_records(records))
    actual_drafts = simplified_links(verification.get("draft_records") or [])
    draft_records_mismatch = bool(verification) and actual_drafts != expected_drafts

    consistency_issues = []
    if not verification_exists:
        consistency_issues.append("missing_publish_verification_report")
    if summary_mismatch:
        consistency_issues.append("publish_summary_mismatch")
    if verification_summary_mismatch:
        consistency_issues.append("verification_publish_summary_mismatch")
    if manifest_verification_records_mismatch:
        consistency_issues.append("manifest_verification_records_mismatch")
    if manifest_verification_summary_mismatch:
        consistency_issues.append("manifest_verification_summary_mismatch")
    if published_links_mismatch:
        consistency_issues.append("published_links_mismatch")
    if draft_records_mismatch:
        consistency_issues.append("draft_records_mismatch")
    if unexpected_record_keys:
        consistency_issues.append("unexpected_publish_results")

    consistency_issue_count = len(consistency_issues) + len(unexpected_record_keys)
    passed = not pending_keys and pending_count == 0 and blocking_issue_count == 0 and not consistency_issues
    if passed:
        status = "passed"
    elif blocking_issue_count or consistency_issue_count:
        status = "failed"
    elif pending_count:
        status = "pending_execution"
    else:
        status = "failed"
    return {
        "schema_version": "1.0",
        "created_at": now_iso(),
        "mode": "publish_guard",
        "will_not_publish": True,
        "publish_manifest": str(publish_manifest_path),
        "publish_verification_report": str(verification_path),
        "publish_verification_report_exists": verification_exists,
        "status": status,
        "passed": passed,
        "summary": {
            **expected_summary,
            "guard_issue_count": blocking_issue_count + pending_count + consistency_issue_count,
            "blocking_issue_count": blocking_issue_count,
            "pending_guard_count": pending_count,
            "consistency_issues": consistency_issues,
            "unexpected_record_keys": [
                ({"task_id": item[1]} if item[0] == "task" else {"topic_id": item[1], "channel": item[2]})
                for item in unexpected_record_keys
            ],
        },
        "channel_checks": channel_checks,
        "expected_published_links": expected_links,
        "expected_draft_records": expected_drafts,
    }


def render_markdown(report: dict[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        "# Publish Guard｜发布批次验收",
        "",
        "本报告只校验发布批次结果，不上传、不发布、不打开浏览器、不读取 cookies。",
        "",
        "## 总览",
        "",
        f"- 状态：`{report['status']}`",
        f"- 通过：`{report['passed']}`",
        f"- 渠道数：`{summary.get('total_channels', 0)}`",
        f"- 已回填：`{summary.get('recorded_count', 0)}`",
        f"- 待执行：`{summary.get('pending_count', 0)}`",
        f"- 已发布：`{summary.get('published_count', 0)}`",
        f"- 已推草稿：`{summary.get('draft_count', 0)}`",
        f"- 失败：`{summary.get('failed_count', 0)}`",
        f"- 需人工验真：`{summary.get('needs_manual_verification_count', 0)}`",
        f"- Guard 问题数：`{summary.get('guard_issue_count', 0)}`",
        f"- 待回填问题：`{summary.get('pending_guard_count', 0)}`",
        f"- 阻塞问题：`{summary.get('blocking_issue_count', 0)}`",
        "",
        "## 渠道验收",
        "",
    ]
    for item in report["channel_checks"]:
        lines.extend(
            [
                f"### {item.get('title') or item.get('topic_id')}｜{item.get('channel')}",
                "",
                f"- Guard 状态：`{item.get('guard_status')}`",
                f"- 发布状态：`{item.get('publish_status') or ''}`",
                f"- 验真状态：`{item.get('verification_status') or ''}`",
                f"- 正式 URL：`{item.get('platform_url') or ''}`",
                f"- 草稿 ID：`{item.get('draft_id') or ''}`",
                f"- 问题：`{item.get('issues') or []}`",
                "",
            ]
        )
    if summary.get("consistency_issues"):
        lines.extend(["## 一致性问题", ""])
        for issue in summary["consistency_issues"]:
            lines.append(f"- `{issue}`")
        lines.append("")
    return "\n".join(lines)


def write_guard_outputs(
    *,
    publish_manifest_path: Path,
    report: dict[str, Any],
    output_json: str | None,
    output_md: str | None,
) -> tuple[Path, Path]:
    publish_root = publish_root_from_manifest(publish_manifest_path)
    json_path = Path(output_json).expanduser().resolve() if output_json else publish_root / "publish_guard_report.json"
    md_path = Path(output_md).expanduser().resolve() if output_md else publish_root / "publish_guard_report.md"
    report["guard_report_json"] = str(json_path.resolve())
    report["guard_report_markdown"] = str(md_path.resolve())
    write_json(json_path, report)
    write_text(md_path, render_markdown(report))
    return json_path, md_path


def update_manifest_guard_fields(
    *,
    publish_manifest_path: Path,
    report: dict[str, Any],
    json_path: Path,
    md_path: Path,
) -> None:
    manifest = ensure_stage_manifest(publish_manifest_path, "publish")
    manifest["publish_guard"] = {
        "status": report.get("status"),
        "passed": report.get("passed"),
        "checked_at": report.get("created_at"),
        "report_json": str(json_path.resolve()),
        "report_markdown": str(md_path.resolve()),
        "will_not_publish": True,
    }
    write_json(publish_manifest_path, manifest)


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate a Newma publish_manifest without publishing.")
    parser.add_argument("--publish-manifest", required=True)
    parser.add_argument("--output-json")
    parser.add_argument("--output-md")
    parser.add_argument("--no-writeback", action="store_true", help="Do not write guard report paths/status back to publish_manifest.json.")
    parser.add_argument("--fail-on-error", action="store_true", help="Exit non-zero when the guard does not pass; useful for CI or strict gates.")
    args = parser.parse_args()

    publish_manifest_path = Path(args.publish_manifest).expanduser().resolve()
    report = build_guard_report(publish_manifest_path)
    json_path, md_path = write_guard_outputs(
        publish_manifest_path=publish_manifest_path,
        report=report,
        output_json=args.output_json,
        output_md=args.output_md,
    )
    if not args.no_writeback:
        update_manifest_guard_fields(
            publish_manifest_path=publish_manifest_path,
            report=report,
            json_path=json_path,
            md_path=md_path,
        )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if args.fail_on_error and not report.get("passed"):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
