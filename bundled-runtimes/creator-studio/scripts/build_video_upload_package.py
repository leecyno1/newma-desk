#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from validate_publish_form import validate_channel_pack


VIDEO_CHANNELS = {
    "xiaohongshu_video": "xiaohongshu",
    "douyin_video": "douyin",
    "bilibili_video": "bilibili",
    "wechat_channels_video": "wechat_channels",
}
QIANFAN_PLATFORM_IDS = {
    "xiaohongshu": 1,
    "wechat_channels": 2,
    "douyin": 3,
    "bilibili": 5,
}


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def existing_path(value: Any) -> str | None:
    if not value:
        return None
    candidate = Path(str(value)).expanduser()
    return str(candidate.resolve()) if candidate.exists() else str(candidate)


def mapping_or_empty(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def qianfan_draft_metadata(pack: dict[str, Any], channel_pack_path: Path) -> dict[str, Any]:
    for parent in channel_pack_path.parents:
        routes_path = parent / "account_routes.json"
        if not routes_path.is_file():
            continue
        routes = read_json(routes_path)
        draft_payload_path = parent / "qianfan_draft_payload.json"
        draft_payload = read_json(draft_payload_path) if draft_payload_path.is_file() else {}
        draft_data = mapping_or_empty(draft_payload.get("draft_data"))
        content_revision = mapping_or_empty(draft_data.get("newma")).get("content_revision")
        if not content_revision and draft_data:
            encoded = json.dumps(draft_data, ensure_ascii=False, sort_keys=True).encode("utf-8")
            content_revision = hashlib.sha256(encoded).hexdigest()[:16]
        draft_id = routes.get("qianfan_draft_id")
        topic_id = routes.get("topic_id") or pack.get("topic_id") or pack.get("task_id")
        return {
            "run_id": routes.get("run_id") or mapping_or_empty(draft_data.get("newma")).get("run_id"),
            "task_id": f"{topic_id}:qianfan-draft-{draft_id}" if draft_id else topic_id,
            "content_revision": content_revision or "unversioned",
            "qianfan_draft_id": draft_id,
        }
    return {
        "run_id": pack.get("run_id"),
        "task_id": pack.get("task_id"),
        "content_revision": pack.get("content_revision") or pack.get("revision") or "unversioned",
        "qianfan_draft_id": pack.get("qianfan_draft_id"),
    }


def normalize_schedule(value: Any) -> str | None:
    if not value:
        return None
    text = str(value).strip()
    if len(text) == 16 and text[4] == "-" and text[7] == "-" and text[10] in {" ", "T"}:
        return text.replace("T", " ")
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return text
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone()
    return parsed.strftime("%Y-%m-%d %H:%M")


def account_name_for_pack(pack: dict[str, Any], metadata: dict[str, Any], notes: dict[str, Any]) -> tuple[str, str]:
    operations = mapping_or_empty(pack.get("account_operations"))
    account_context = mapping_or_empty(operations.get("account_context"))
    account_profile = mapping_or_empty(pack.get("account_profile"))
    explicit = (
        notes.get("account_name")
        or metadata.get("account_name")
        or pack.get("account_name")
        or account_context.get("account_name")
        or account_profile.get("cli_account_name")
    )
    if explicit:
        return str(explicit).strip(), "explicit_account_name"

    slot = notes.get("account_slot") or metadata.get("account_slot") or pack.get("account_slot") or account_context.get("account_slot")
    if slot not in (None, ""):
        digits = "".join(char for char in str(slot) if char.isdigit())
        suffix = digits or str(slot).strip().replace(" ", "-")
        return f"slot-{suffix}", "account_slot"
    return "slot-1", "default_slot"


def platform_options_for_pack(pack: dict[str, Any], metadata: dict[str, Any]) -> dict[str, Any]:
    notes = mapping_or_empty(metadata.get("platform_notes"))
    account_profile = mapping_or_empty(pack.get("account_profile"))
    activity_selected = mapping_or_empty(notes.get("activity_selected"))
    return {
        "tid": notes.get("tid") or notes.get("category_id"),
        "category_id": notes.get("category_id"),
        "short_title": notes.get("short_title"),
        "category": notes.get("category"),
        "draft": bool(notes.get("draft") or notes.get("save_draft")),
        "thumbnail_landscape": existing_path(notes.get("thumbnail_landscape")),
        "thumbnail_portrait": existing_path(notes.get("thumbnail_portrait")),
        "activity_id": notes.get("activity_id") or activity_selected.get("id"),
        "activity_title": activity_selected.get("title"),
        "declaration": notes.get("declaration"),
        "qianfan_account_id": notes.get("qianfan_account_id") or account_profile.get("qianfan_account_id"),
        "qianfan_account_name": notes.get("qianfan_account_name") or account_profile.get("qianfan_account_name"),
    }


def common_payload(pack: dict[str, Any], channel_pack_path: Path) -> dict[str, Any]:
    artifacts = pack.get("artifact_hint") or {}
    metadata = pack.get("publish_metadata") or {}
    notes = mapping_or_empty(metadata.get("platform_notes"))
    title = metadata.get("title") or pack.get("title")
    description = metadata.get("summary") or metadata.get("description") or ""
    tags = metadata.get("tags") or []
    account_name, account_source = account_name_for_pack(pack, metadata, notes)
    return {
        "task_id": pack.get("task_id"),
        "batch_id": pack.get("batch_id"),
        "topic_id": pack.get("topic_id"),
        "variant_id": pack.get("variant_id"),
        "account_slot": pack.get("account_slot"),
        "title": title,
        "description": description,
        "tags": tags,
        "cover": existing_path(metadata.get("cover")),
        "video": existing_path(artifacts.get("video")),
        "subtitle": existing_path(artifacts.get("video_srt")),
        "account_name": account_name,
        "account_source": account_source,
        "scheduled_at": normalize_schedule(metadata.get("scheduled_at") or notes.get("scheduled_at")),
        "headless": bool(notes.get("headless", False)),
        "debug": bool(notes.get("debug", False)),
        "platform_options": platform_options_for_pack(pack, metadata),
        "source_channel_pack": str(channel_pack_path.resolve()),
        "requires_user_confirmation": True,
        "auto_publish": False,
    }


def build_social_auto_upload_request(pack: dict[str, Any], channel_pack_path: Path) -> dict[str, Any]:
    payload = common_payload(pack, channel_pack_path)
    return {
        "schema_version": "1.0",
        "created_at": now_iso(),
        "task_id": pack.get("task_id"),
        "batch_id": pack.get("batch_id"),
        "topic_id": pack.get("topic_id"),
        "variant_id": pack.get("variant_id"),
        "account_slot": pack.get("account_slot"),
        "adapter": "social-auto-upload",
        "platform": VIDEO_CHANNELS.get(pack.get("channel")),
        "status": "ready_for_external_dry_run",
        "upload": payload,
        "safety": {
            "will_not_publish_without_confirmation": True,
            "credentials_handling": "external_tool_session_only",
            "runtime_output_root": "same_channel_pack_directory",
        },
    }


def build_qianfan_request(pack: dict[str, Any], channel_pack_path: Path) -> dict[str, Any]:
    payload = common_payload(pack, channel_pack_path)
    draft_metadata = qianfan_draft_metadata(pack, channel_pack_path)
    platform = VIDEO_CHANNELS.get(pack.get("channel"))
    options = payload["platform_options"]
    account_selector = {
        "account_id": options.get("qianfan_account_id"),
        "account_name": options.get("qianfan_account_name") or payload["account_name"],
        "account_slot": payload.get("account_slot"),
    }
    activity_id = options.get("activity_id")
    cover = payload.get("cover") or ""
    post_video_payload = {
        "type": QIANFAN_PLATFORM_IDS.get(platform),
        "title": payload.get("title") or "",
        "description": payload.get("description") or "",
        "tags": payload.get("tags") or [],
        "activities": [activity_id] if activity_id else [],
        "fileList": [payload["video"]] if payload.get("video") else [],
        "accountList": [],
        "thumbnailLandscape": options.get("thumbnail_landscape") or cover,
        "thumbnailPortrait": options.get("thumbnail_portrait") or cover,
        "enableTimer": 1 if payload.get("scheduled_at") else 0,
        "scheduleTime": payload.get("scheduled_at") or "",
        "videosPerDay": 1,
        "dailyTimes": ["10:00"],
        "startDays": 0,
        "category": options.get("tid") or options.get("category_id") or options.get("category") or "",
        "creationDeclaration": options.get("declaration") or "",
        "isDraft": bool(options.get("draft")),
    }
    return {
        "schema_version": "dasheng.qianfan_video_request.v1",
        "created_at": now_iso(),
        "adapter": "qianfan-local-api",
        "api_base": "${QIANFAN_API_BASE:-http://127.0.0.1:5409}",
        **draft_metadata,
        "platform": platform,
        "status": "ready_for_local_api_dry_run",
        "account_selector": account_selector,
        "post_video_payload": post_video_payload,
        "source_channel_pack": str(channel_pack_path.resolve()),
        "safety": {
            "will_not_publish_without_confirmation": True,
            "account_resolution": "use account ids stored in the validated Qianfan draft",
            "credentials_handling": "qianfan external session only",
        },
    }


def build_bilibili_submission(pack: dict[str, Any], channel_pack_path: Path) -> dict[str, Any]:
    payload = common_payload(pack, channel_pack_path)
    return {
        "schema_version": "1.0",
        "created_at": now_iso(),
        "adapter": "bilibili-upload-bridge",
        "platform": "bilibili",
        "status": "ready_for_external_dry_run",
        "submission": {
            "title": payload["title"],
            "desc": payload["description"],
            "tags": payload["tags"],
            "cover": payload["cover"],
            "video": payload["video"],
            "subtitle": payload["subtitle"],
            "source_channel_pack": payload["source_channel_pack"],
            "copyright": "original_or_user_confirmed",
        },
        "preferred_tools": ["biliup-rs", "social-auto-upload", "manual-package"],
        "safety": {
            "will_not_publish_without_confirmation": True,
            "credentials_handling": "external_tool_session_only",
            "runtime_output_root": "same_channel_pack_directory",
        },
    }


def build_package(channel_pack_path: Path) -> dict[str, Any]:
    pack = read_json(channel_pack_path)
    validation = validate_channel_pack(pack, source_path=channel_pack_path)
    validation_path = channel_pack_path.parent / "platform_form_validation.json"
    write_json(validation_path, validation)
    errors = [str(item.get("code")) for item in validation.get("blocking_errors") or []]
    if pack.get("channel") not in VIDEO_CHANNELS:
        errors.append(f"unsupported_video_channel:{pack.get('channel')}")
    pack_dir = channel_pack_path.parent
    social_path = pack_dir / "social_auto_upload_request.json"
    qianfan_path = pack_dir / "qianfan_video_request.json"
    bilibili_path = pack_dir / "bilibili_submission.json"

    outputs: dict[str, str] = {}
    outputs["platform_form_validation"] = str(validation_path.resolve())
    if not errors:
        qianfan_request = build_qianfan_request(pack, channel_pack_path)
        write_json(qianfan_path, qianfan_request)
        outputs["qianfan_video_request"] = str(qianfan_path.resolve())
        social_request = build_social_auto_upload_request(pack, channel_pack_path)
        write_json(social_path, social_request)
        outputs["social_auto_upload_request"] = str(social_path.resolve())
        if pack.get("channel") == "bilibili_video":
            bilibili_submission = build_bilibili_submission(pack, channel_pack_path)
            write_json(bilibili_path, bilibili_submission)
            outputs["bilibili_submission"] = str(bilibili_path.resolve())

    status = "ready" if not errors else "blocked"
    return {
        "schema_version": "1.0",
        "created_at": now_iso(),
        "status": status,
        "channel_pack": str(channel_pack_path.resolve()),
        "channel": pack.get("channel"),
        "platform": VIDEO_CHANNELS.get(pack.get("channel")),
        "errors": errors,
        "warnings": [str(item.get("code")) for item in validation.get("warnings") or []],
        "outputs": outputs,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Build external video upload package from Newma channel_pack.json.")
    parser.add_argument("--channel-pack", required=True)
    parser.add_argument("--output", help="Optional conversion report path.")
    args = parser.parse_args()

    channel_pack = Path(args.channel_pack).expanduser().resolve()
    report = build_package(channel_pack)
    if args.output:
        write_json(Path(args.output).expanduser().resolve(), report)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
