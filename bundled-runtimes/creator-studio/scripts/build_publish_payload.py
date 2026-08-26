#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from validate_publish_form import validate_channel_pack


TEXT_CHANNELS = {"wechat_article", "weibo_post", "x_post"}
VIDEO_CHANNELS = {"xiaohongshu_video", "douyin_video", "bilibili_video", "wechat_channels_video"}


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def existing_or_raw(value: Any) -> str | None:
    if not value:
        return None
    candidate = Path(str(value)).expanduser()
    return str(candidate.resolve()) if candidate.exists() else str(value)


def common_metadata(pack: dict[str, Any]) -> dict[str, Any]:
    metadata = pack.get("publish_metadata") or {}
    return {
        "task_id": pack.get("task_id"),
        "batch_id": pack.get("batch_id"),
        "topic_id": pack.get("topic_id"),
        "variant_id": pack.get("variant_id"),
        "account_slot": pack.get("account_slot"),
        "title": metadata.get("title") or pack.get("title"),
        "summary": metadata.get("summary") or metadata.get("description") or "",
        "tags": metadata.get("tags") or [],
        "scheduled_at": metadata.get("scheduled_at"),
        "visibility": metadata.get("visibility") or "default",
        "cover": existing_or_raw(metadata.get("cover")),
        "platform_notes": metadata.get("platform_notes") or {},
    }


def build_wechat_payload(pack: dict[str, Any], channel_pack_path: Path) -> dict[str, Any]:
    metadata = common_metadata(pack)
    artifacts = pack.get("artifact_hint") or {}
    return {
        "skill": pack.get("executor_skill") or "baoyu-post-to-wechat",
        "mode": "draft",
        "title": metadata["title"],
        "summary": metadata["summary"],
        "content_html": existing_or_raw(artifacts.get("wechat_html")),
        "content_markdown": existing_or_raw(artifacts.get("wechat_markdown")),
        "cover_path": metadata["cover"],
        "source_channel_pack": str(channel_pack_path.resolve()),
        "result_writeback": {
            "command": "python3 scripts/record_publish_result.py",
            "channel_pack": str(channel_pack_path.resolve()),
        },
    }


def build_weibo_payload(pack: dict[str, Any], channel_pack_path: Path) -> dict[str, Any]:
    metadata = common_metadata(pack)
    artifacts = pack.get("artifact_hint") or {}
    return {
        "skill": pack.get("executor_skill") or "baoyu-post-to-weibo",
        "text_source": existing_or_raw(artifacts.get("wechat_markdown") or artifacts.get("wechat_html")),
        "title": metadata["title"],
        "summary": metadata["summary"],
        "images": [item for item in [metadata["cover"]] if item],
        "tags": metadata["tags"],
        "source_channel_pack": str(channel_pack_path.resolve()),
        "result_writeback": {
            "command": "python3 scripts/record_publish_result.py",
            "channel_pack": str(channel_pack_path.resolve()),
        },
    }


def build_x_payload(pack: dict[str, Any], channel_pack_path: Path) -> dict[str, Any]:
    metadata = common_metadata(pack)
    artifacts = pack.get("artifact_hint") or {}
    return {
        "skill": pack.get("executor_skill") or "baoyu-post-to-x",
        "article_source": existing_or_raw(artifacts.get("wechat_markdown") or artifacts.get("wechat_html")),
        "title": metadata["title"],
        "summary": metadata["summary"],
        "media": [item for item in [metadata["cover"]] if item],
        "tags": metadata["tags"],
        "source_channel_pack": str(channel_pack_path.resolve()),
        "result_writeback": {
            "command": "python3 scripts/record_publish_result.py",
            "channel_pack": str(channel_pack_path.resolve()),
        },
    }


def build_video_payload(pack: dict[str, Any], channel_pack_path: Path) -> dict[str, Any]:
    metadata = common_metadata(pack)
    artifacts = pack.get("artifact_hint") or {}
    return {
        "skill": pack.get("executor_skill"),
        "channel": pack.get("channel"),
        "title": metadata["title"],
        "description": metadata["summary"],
        "tags": metadata["tags"],
        "cover": metadata["cover"],
        "video": existing_or_raw(artifacts.get("video")),
        "subtitle": existing_or_raw(artifacts.get("video_srt")),
        "render_plan": existing_or_raw(artifacts.get("video_render_plan")),
        "source_channel_pack": str(channel_pack_path.resolve()),
        "requires_user_confirmation": True,
        "auto_publish": False,
        "browser_profile": pack.get("browser_profile"),
        "result_writeback": {
            "command": "python3 scripts/record_publish_result.py",
            "channel_pack": str(channel_pack_path.resolve()),
        },
    }


def build_payload(pack: dict[str, Any], channel_pack_path: Path) -> dict[str, Any]:
    channel = pack.get("channel")
    if channel == "wechat_article":
        payload = build_wechat_payload(pack, channel_pack_path)
    elif channel == "weibo_post":
        payload = build_weibo_payload(pack, channel_pack_path)
    elif channel == "x_post":
        payload = build_x_payload(pack, channel_pack_path)
    elif channel in VIDEO_CHANNELS:
        payload = build_video_payload(pack, channel_pack_path)
    else:
        payload = {
            "skill": pack.get("executor_skill"),
            "channel": channel,
            "source_channel_pack": str(channel_pack_path.resolve()),
        }
    return {
        "schema_version": "1.0",
        "created_at": now_iso(),
        "status": "ready_for_executor",
        "will_not_publish": True,
        "requires_user_confirmation": True,
        "channel": channel,
        "task_id": pack.get("task_id"),
        "batch_id": pack.get("batch_id"),
        "topic_id": pack.get("topic_id"),
        "variant_id": pack.get("variant_id"),
        "account_slot": pack.get("account_slot"),
        "platform": pack.get("platform") or channel,
        "payload": payload,
        "safety": {
            "does_not_publish": True,
            "final_publish_requires_confirmation": True,
            "writeback_required": True,
        },
    }


def build_package(channel_pack_path: Path) -> dict[str, Any]:
    pack = read_json(channel_pack_path)
    validation = validate_channel_pack(pack, source_path=channel_pack_path)
    validation_path = channel_pack_path.parent / "platform_form_validation.json"
    write_json(validation_path, validation)
    errors = [str(item.get("code")) for item in validation.get("blocking_errors") or []]
    payload = build_payload(pack, channel_pack_path)
    payload["platform_form_validation"] = {
        "status": validation["status"],
        "report": str(validation_path.resolve()),
        "blocking_error_count": validation["summary"]["blocking_error_count"],
        "warning_count": validation["summary"]["warning_count"],
    }
    if errors:
        payload["status"] = "blocked"
        payload["errors"] = errors
    output_path = channel_pack_path.parent / "publish_payload.json"
    write_json(output_path, payload)
    return {
        "schema_version": "1.0",
        "status": payload["status"],
        "channel_pack": str(channel_pack_path.resolve()),
        "publish_payload": str(output_path.resolve()),
        "platform_form_validation": str(validation_path.resolve()),
        "errors": errors,
        "warnings": [str(item.get("code")) for item in validation.get("warnings") or []],
        "will_not_publish": True,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a standard executor payload from Newma channel_pack.json without publishing.")
    parser.add_argument("--channel-pack", required=True)
    parser.add_argument("--output", help="Optional report path.")
    args = parser.parse_args()

    channel_pack = Path(args.channel_pack).expanduser().resolve()
    report = build_package(channel_pack)
    if args.output:
        write_json(Path(args.output).expanduser().resolve(), report)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
