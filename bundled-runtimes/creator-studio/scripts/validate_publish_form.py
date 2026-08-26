#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from path_config import get_project_root


ROOT = get_project_root()
DEFAULT_RULES = ROOT / "configs" / "publish" / "platform_form_rules.json"


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def rules_path() -> Path:
    return Path(os.environ.get("DASHENG_PUBLISH_FORM_RULES") or DEFAULT_RULES).expanduser()


def load_rules() -> dict[str, Any]:
    path = rules_path()
    if not path.exists():
        return {"schema_version": "missing", "channels": {}}
    payload = read_json(path)
    return payload if isinstance(payload, dict) else {"schema_version": "invalid", "channels": {}}


def mapping(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def normalize_account_slot(value: Any) -> str:
    if value in (None, ""):
        return "slot-1"
    text = str(value).strip()
    digits = "".join(char for char in text if char.isdigit())
    if digits:
        return f"slot-{digits}"
    normalized = text.lower().replace("_", "-").replace(" ", "-")
    return normalized if normalized.startswith("slot-") else f"slot-{normalized}"


def normalize_context(pack: dict[str, Any]) -> dict[str, Any]:
    metadata = mapping(pack.get("publish_metadata"))
    notes = mapping(metadata.get("platform_notes"))
    artifacts = mapping(pack.get("artifact_hint"))
    operations = mapping(pack.get("account_operations"))
    account_context = mapping(operations.get("account_context"))
    return {
        "channel": pack.get("channel"),
        "title": metadata.get("title") or pack.get("title"),
        "summary": metadata.get("summary") or metadata.get("description"),
        "description": metadata.get("description") or metadata.get("summary"),
        "tags": metadata.get("tags") or [],
        "scheduled_at": metadata.get("scheduled_at"),
        "visibility": metadata.get("visibility"),
        "cover": metadata.get("cover"),
        "video": artifacts.get("video"),
        "subtitle": artifacts.get("video_srt"),
        "text_html": artifacts.get("wechat_html"),
        "text_markdown": artifacts.get("wechat_markdown"),
        "account_slot": normalize_account_slot(
            notes.get("account_slot")
            or metadata.get("account_slot")
            or pack.get("account_slot")
            or account_context.get("account_slot")
        ),
        "platform_options": notes,
    }


def get_value(context: dict[str, Any], field: str) -> Any:
    value: Any = context
    for part in field.split("."):
        if not isinstance(value, dict):
            return None
        value = value.get(part)
    return value


def is_present(value: Any) -> bool:
    return value not in (None, "", [], {})


def issue(*, severity: str, code: str, field: str | list[str], message: str) -> dict[str, Any]:
    return {
        "severity": severity,
        "code": code,
        "field": field,
        "message": message,
    }


def validate_channel_pack(pack: dict[str, Any], *, source_path: Path | None = None) -> dict[str, Any]:
    rules = load_rules()
    channel = str(pack.get("channel") or "")
    channel_rule = mapping((rules.get("channels") or {}).get(channel))
    context = normalize_context(pack)
    errors: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []

    if not channel:
        errors.append(
            issue(
                severity="error",
                code="missing_channel",
                field="channel",
                message="发布包缺少渠道标识。",
            )
        )

    if not channel_rule:
        warnings.append(
            issue(
                severity="warning",
                code="missing_platform_form_rules",
                field="channel",
                message=f"渠道 {channel or '<empty>'} 尚未配置平台表单规则。",
            )
        )

    for row in channel_rule.get("required") or []:
        field = str(row.get("field") or "")
        if field and not is_present(get_value(context, field)):
            errors.append(
                issue(
                    severity="error",
                    code=str(row.get("code") or f"missing_{field}"),
                    field=field,
                    message=str(row.get("message") or f"缺少必填字段：{field}"),
                )
            )

    for row in channel_rule.get("required_any") or []:
        fields = [str(field) for field in row.get("fields") or []]
        if fields and not any(is_present(get_value(context, field)) for field in fields):
            errors.append(
                issue(
                    severity="error",
                    code=str(row.get("code") or "missing_required_group"),
                    field=fields,
                    message=str(row.get("message") or f"至少填写一项：{', '.join(fields)}"),
                )
            )

    for field in channel_rule.get("existing_files") or []:
        field = str(field)
        value = get_value(context, field)
        if not is_present(value):
            continue
        candidate = Path(str(value)).expanduser()
        if not candidate.is_absolute() and source_path:
            candidate = source_path.parent / candidate
        if not candidate.exists():
            errors.append(
                issue(
                    severity="error",
                    code=f"file_not_found:{field}",
                    field=field,
                    message=f"字段 {field} 指向的文件不存在：{candidate}",
                )
            )

    for row in channel_rule.get("recommended") or []:
        field = str(row.get("field") or "")
        if field and not is_present(get_value(context, field)):
            warnings.append(
                issue(
                    severity="warning",
                    code=str(row.get("code") or f"recommended_{field}"),
                    field=field,
                    message=str(row.get("message") or f"建议填写：{field}"),
                )
            )

    for row in channel_rule.get("limits") or []:
        field = str(row.get("field") or "")
        value = get_value(context, field)
        max_chars = row.get("max_chars")
        if not field or not is_present(value) or not isinstance(max_chars, int):
            continue
        if len(str(value)) <= max_chars:
            continue
        target = errors if row.get("severity") == "error" else warnings
        target.append(
            issue(
                severity="error" if target is errors else "warning",
                code=str(row.get("code") or f"max_chars_exceeded:{field}"),
                field=field,
                message=str(row.get("message") or f"字段 {field} 超过 {max_chars} 字。"),
            )
        )

    return {
        "schema_version": "1.0",
        "created_at": now_iso(),
        "mode": "platform_form_preflight",
        "task_id": pack.get("task_id"),
        "batch_id": pack.get("batch_id"),
        "topic_id": pack.get("topic_id"),
        "variant_id": pack.get("variant_id"),
        "account_slot": pack.get("account_slot"),
        "source_channel_pack": str(source_path.resolve()) if source_path else None,
        "rules_file": str(rules_path().resolve()),
        "rules_version": rules.get("schema_version"),
        "channel": channel,
        "platform": channel_rule.get("platform") or channel,
        "status": "blocked" if errors else "passed",
        "ready_for_executor": not errors,
        "blocking_errors": errors,
        "warnings": warnings,
        "summary": {
            "blocking_error_count": len(errors),
            "warning_count": len(warnings),
        },
        "normalized_fields": context,
        "safety": {
            "does_not_publish": True,
            "does_not_open_browser": True,
            "does_not_read_cookies": True,
            "does_not_include_credentials": True,
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate one Publish channel pack against platform form rules.")
    parser.add_argument("--channel-pack", required=True)
    parser.add_argument("--output", help="Optional JSON report path; defaults beside channel_pack.json.")
    parser.add_argument("--fail-on-error", action="store_true")
    args = parser.parse_args()

    channel_pack = Path(args.channel_pack).expanduser().resolve()
    report = validate_channel_pack(read_json(channel_pack), source_path=channel_pack)
    output = Path(args.output).expanduser().resolve() if args.output else channel_pack.parent / "platform_form_validation.json"
    write_json(output, report)
    report["report_file"] = str(output.resolve())
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if args.fail_on_error and report["status"] == "blocked":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
