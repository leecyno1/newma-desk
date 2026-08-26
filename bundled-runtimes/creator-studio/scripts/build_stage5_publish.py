#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from canonical_workflow import (
    WorkflowContractError,
    canonical_stage_dir,
    ensure_runtime_output_dir,
    ensure_publish_decision_gate,
    ensure_stage_manifest,
    write_json,
)
from record_publish_result import aggregate_publish_state
from validate_publish_form import validate_channel_pack


PUBLISH_BROWSER_PROFILE_CONFIG = Path(__file__).resolve().parent.parent / "configs" / "publish" / "browser_profiles.json"
PUBLISH_ACCOUNT_REGISTRY_CONFIG = Path(__file__).resolve().parent.parent / "configs" / "publish" / "account_registry.json"

CHANNEL_RULES = {
    "wechat_article": {
        "executor_skill": "baoyu-post-to-wechat",
        "mode": "draft_push_or_browser_confirm",
        "source_lane": "wechat_article",
    },
    "weibo_post": {
        "executor_skill": "baoyu-post-to-weibo",
        "mode": "browser_confirm",
        "source_lane": "wechat_article",
    },
    "x_post": {
        "executor_skill": "baoyu-post-to-x",
        "mode": "browser_confirm",
        "source_lane": "wechat_article",
    },
    "xiaohongshu_video": {
        "executor_skill": "dasheng-xhs-publish-bridge",
        "mode": "api_first_with_browser_fallback",
        "source_lane": "talking_head_video",
    },
    "douyin_video": {
        "executor_skill": "douyin-upload-skill",
        "mode": "manual_or_openclaw",
        "source_lane": "talking_head_video",
    },
    "bilibili_video": {
        "executor_skill": "manual_upload",
        "mode": "manual_only",
        "source_lane": "talking_head_video",
    },
    "wechat_channels_video": {
        "executor_skill": "social-auto-upload-bridge",
        "mode": "external_cli_confirm",
        "source_lane": "talking_head_video",
    },
    "podcast": {
        "executor_skill": "manual_or_audio_platform_api",
        "mode": "manual_package",
        "source_lane": "podcast",
    },
}

ACCOUNT_OPERATIONS_UPSTREAM = {
    "registry_name": "agent-skills-launch-pack",
    "repo": "https://github.com/chenjin-cmd/agent-skills-launch-pack_",
    "root_env": "AGENT_SKILLS_LAUNCH_PACK_ROOT",
    "default_root": str(Path(__file__).resolve().parents[1] / "vendor/reserved/publish/agent-skills-launch-pack"),
    "bridge_skill": "dasheng-publish-operations-bridge",
}

ACCOUNT_OPERATIONS_RULES = {
    "wechat_article": {
        "platform": "wechat",
        "upstream_skill": "wechat-account-launch-expert",
        "requested_outputs": [
            "positioning_check",
            "title_and_opening_review",
            "series_assignment",
            "publish_cadence",
            "weekly_review_metrics",
        ],
        "post_publish_metrics": ["impressions", "opens", "completion", "shares", "follows", "conversions"],
    },
    "xiaohongshu_video": {
        "platform": "xiaohongshu",
        "upstream_skill": "xiaohongshu-account-launch-expert",
        "requested_outputs": [
            "positioning_check",
            "cover_title_hook_review",
            "keywords_and_tags",
            "series_assignment",
            "comment_cta",
            "weekly_review_metrics",
        ],
        "post_publish_metrics": [
            "impressions",
            "cover_clicks",
            "views",
            "completion",
            "likes",
            "saves",
            "comments",
            "follows",
            "inquiries",
        ],
    },
    "douyin_video": {
        "platform": "douyin",
        "upstream_skill": "douyin-account-launch-expert",
        "requested_outputs": [
            "positioning_check",
            "three_second_hook_review",
            "search_keywords",
            "collection_assignment",
            "comment_prompt",
            "experiment_hypothesis",
            "weekly_review_metrics",
        ],
        "post_publish_metrics": [
            "impressions",
            "plays",
            "three_second_retention",
            "five_second_retention",
            "completion",
            "average_watch_time",
            "likes",
            "comments",
            "shares",
            "follows",
            "search_source",
        ],
    },
    "wechat_channels_video": {
        "platform": "wechat_channels",
        "upstream_skill": "channels-account-launch-expert",
        "requested_outputs": [
            "positioning_check",
            "three_second_hook_review",
            "short_title_review",
            "topic_tags",
            "series_assignment",
            "weekly_review_metrics",
        ],
        "post_publish_metrics": [
            "impressions",
            "plays",
            "completion",
            "average_watch_time",
            "likes",
            "comments",
            "shares",
            "follows",
        ],
    },
    "x_post": {
        "platform": "x",
        "upstream_skill": "x-twitter-cold-start-expert",
        "requested_outputs": [
            "positioning_check",
            "post_or_thread_format",
            "reply_distribution_plan",
            "profile_conversion_check",
            "weekly_review_metrics",
        ],
        "post_publish_metrics": [
            "impressions",
            "engagements",
            "profile_visits",
            "follows",
            "link_clicks",
            "bookmarks",
            "replies",
        ],
    },
}

ACCOUNT_OPERATIONS_REQUIRED_STAGES = {
    "new",
    "cold_start",
    "low_performance",
    "dormant",
    "risk_review",
    "matrix_experiment",
}

PUBLISH_READY_LANE_STATUSES = {"completed", "packageable", "ready_base_package"}
PUBLISH_BLOCKING_LANE_STATUSES = {
    "missing_lane",
    "planned",
    "planned_for_render",
    "ready_for_agent_execution",
    "ready_for_agent_dna_humanize",
    "ready_for_skill_execution",
    "ready_for_audio_generation",
    "blocked_missing_api_key",
    "blocked_missing_provider",
    "blocked_missing_audio_provider",
    "blocked_missing_human_media",
    "waiting_for_human_media",
    "failed_qc",
}

CONFIRM_EXECUTABLE_ROUTE_TYPES = {"skill_draft_push", "qianfan_local_api", "external_uploader_fallback"}


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content.rstrip() + "\n", encoding="utf-8")


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def read_json(path: str | Path) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def mapping_or_empty(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def string_list(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value] if value.strip() else []
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def account_operations_for_channel(decision_row: dict[str, Any], channel: str) -> dict[str, Any] | None:
    rule = ACCOUNT_OPERATIONS_RULES.get(channel)
    if not rule:
        return None

    channel_notes = mapping_or_empty(decision_row.get(channel))
    global_context = mapping_or_empty(decision_row.get("account_context"))
    channel_context = mapping_or_empty(channel_notes.get("account_context"))
    global_options = decision_row.get("account_operations")
    channel_options = channel_notes.get("account_operations")
    options = {
        **mapping_or_empty(global_options),
        **mapping_or_empty(channel_options),
    }
    explicitly_disabled = global_options is False or channel_options is False or options.get("enabled") is False
    account_stage = str(
        channel_notes.get("account_stage")
        or channel_context.get("stage")
        or decision_row.get(f"{channel}_account_stage")
        or decision_row.get("account_stage")
        or global_context.get("stage")
        or "unspecified"
    ).strip()
    required_override = options.get("required")
    required = bool(required_override) if required_override is not None else account_stage in ACCOUNT_OPERATIONS_REQUIRED_STAGES
    requested_outputs = string_list(options.get("requested_outputs")) or list(rule["requested_outputs"])
    context = {
        "account_stage": account_stage,
        "account_goal": channel_context.get("goal") or channel_notes.get("account_goal") or global_context.get("goal") or decision_row.get("account_goal"),
        "account_slot": channel_context.get("slot") or channel_notes.get("account_slot") or global_context.get("slot") or decision_row.get("account_slot"),
        "matrix_role": channel_context.get("matrix_role") or channel_notes.get("matrix_role") or global_context.get("matrix_role") or decision_row.get("matrix_role"),
        "target_audience": channel_context.get("target_audience") or global_context.get("target_audience") or decision_row.get("target_audience"),
        "conversion_goal": channel_context.get("conversion_goal") or global_context.get("conversion_goal") or decision_row.get("conversion_goal"),
        "weekly_capacity": channel_context.get("weekly_capacity") or global_context.get("weekly_capacity") or decision_row.get("weekly_capacity"),
        "prior_metrics": channel_context.get("prior_metrics") or global_context.get("prior_metrics") or decision_row.get("prior_metrics"),
        "review_notes": channel_context.get("review_notes") or global_context.get("review_notes") or decision_row.get("review_notes"),
    }
    return {
        "enabled": not explicitly_disabled,
        "required": bool(required and not explicitly_disabled),
        "blocks_guarded_execution": bool(required and not explicitly_disabled),
        "status": "disabled" if explicitly_disabled else ("required_before_execution" if required else "advisory_pending"),
        "review_completed": False,
        "validation_reason": "advice_not_checked",
        "bridge_skill": ACCOUNT_OPERATIONS_UPSTREAM["bridge_skill"],
        "upstream_skill": rule["upstream_skill"],
        "platform": rule["platform"],
        "requested_outputs": requested_outputs,
        "post_publish_metrics": list(rule["post_publish_metrics"]),
        "account_context": {key: value for key, value in context.items() if value not in (None, "", [], {})},
        "upstream": dict(ACCOUNT_OPERATIONS_UPSTREAM),
    }


def validate_account_operations_advice(path: Path, operations: dict[str, Any]) -> tuple[bool, str]:
    if not path.exists():
        return False, "missing_account_operations_advice"
    try:
        payload = read_json(path)
    except (OSError, json.JSONDecodeError):
        return False, "invalid_account_operations_advice_json"
    if not isinstance(payload, dict) or payload.get("status") != "completed":
        return False, "account_operations_advice_not_completed"
    if payload.get("channel") != operations.get("channel"):
        return False, "account_operations_advice_channel_mismatch"
    if payload.get("platform") != operations.get("platform"):
        return False, "account_operations_advice_platform_mismatch"
    if payload.get("upstream_skill") != operations.get("upstream_skill"):
        return False, "account_operations_advice_skill_mismatch"
    if not isinstance(payload.get("recommendations"), dict):
        return False, "account_operations_advice_missing_recommendations"
    return True, "valid_account_operations_advice"


def publish_browser_profiles() -> dict[str, Any]:
    if not PUBLISH_BROWSER_PROFILE_CONFIG.exists():
        return {}
    payload = read_json(PUBLISH_BROWSER_PROFILE_CONFIG)
    profiles = payload.get("profiles")
    return profiles if isinstance(profiles, dict) else {}


def publish_browser_window_policy() -> dict[str, Any]:
    if not PUBLISH_BROWSER_PROFILE_CONFIG.exists():
        return {}
    payload = read_json(PUBLISH_BROWSER_PROFILE_CONFIG)
    policy = payload.get("window_policy") or {}
    return policy if isinstance(policy, dict) else {}


def publish_account_registry() -> dict[str, Any]:
    registry_path = Path(os.environ.get("DASHENG_PUBLISH_ACCOUNT_REGISTRY") or PUBLISH_ACCOUNT_REGISTRY_CONFIG).expanduser()
    if not registry_path.exists():
        return {}
    payload = read_json(registry_path)
    channels = payload.get("channels")
    return channels if isinstance(channels, dict) else {}


def normalize_account_slot(value: Any) -> str:
    if value in (None, ""):
        return "slot-1"
    text = str(value).strip()
    digits = "".join(char for char in text if char.isdigit())
    if digits:
        return f"slot-{digits}"
    normalized = text.lower().replace("_", "-").replace(" ", "-")
    return normalized if normalized.startswith("slot-") else f"slot-{normalized}"


def account_slot_for_channel(decision_row: dict[str, Any], channel: str) -> str:
    channel_notes = mapping_or_empty(decision_row.get(channel))
    channel_context = mapping_or_empty(channel_notes.get("account_context"))
    global_context = mapping_or_empty(decision_row.get("account_context"))
    return normalize_account_slot(
        channel_notes.get("account_slot")
        or channel_context.get("slot")
        or decision_row.get(f"{channel}_account_slot")
        or decision_row.get("account_slot")
        or global_context.get("slot")
    )


def browser_profile_key_for_account(channel: str, account_slot: str) -> str | None:
    channel_row = publish_account_registry().get(channel)
    if not isinstance(channel_row, dict):
        return None
    slot = (channel_row.get("slots") or {}).get(account_slot)
    return str(slot.get("browser_profile")) if isinstance(slot, dict) and slot.get("browser_profile") else None


def account_profile_for_channel(channel: str, account_slot: str) -> dict[str, Any]:
    channel_row = publish_account_registry().get(channel)
    if not isinstance(channel_row, dict):
        return {}
    slot = (channel_row.get("slots") or {}).get(account_slot)
    if not isinstance(slot, dict):
        return {}
    allowed = {
        "label",
        "cli_account_name",
        "qianfan_account_id",
        "qianfan_account_name",
        "browser_profile",
        "auth_modes",
        "publish_presets",
        "network_policy",
    }
    return {key: value for key, value in slot.items() if key in allowed and value not in (None, "", [], {})}


def browser_profile_for_channel(channel: str, profile_key: str | None = None) -> dict[str, Any] | None:
    profiles = publish_browser_profiles()
    profile = profiles.get(profile_key or channel)
    if not isinstance(profile, dict):
        return None
    profile_dir = profile.get("profile_dir")
    return {
        "platform": profile.get("platform") or channel,
        "profile_key": profile_key or channel,
        "profile_dir": str(Path(str(profile_dir)).expanduser()) if profile_dir else None,
        "entry_url": profile.get("entry_url"),
        "notes": profile.get("notes"),
        "open_command": f"python3 scripts/open_publish_browser.py {profile_key or channel}",
        "window_policy": publish_browser_window_policy(),
    }


def safe_slug(value: Any, fallback: str = "item") -> str:
    text = str(value or "").strip()
    cleaned = "".join(ch.lower() if ch.isalnum() else "-" for ch in text)
    cleaned = "-".join(part for part in cleaned.split("-") if part)
    return cleaned or fallback


def normalize_channels(row: dict[str, Any]) -> list[str]:
    channels = row.get("channels") or row.get("lanes") or ["wechat_article"]
    if isinstance(channels, str):
        channels = [channels]
    return [channel for channel in channels if channel in CHANNEL_RULES]


def topics_by_id(transwrite_manifest: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(topic.get("topic_id")): topic
        for topic in transwrite_manifest.get("topics") or []
        if isinstance(topic, dict) and topic.get("topic_id")
    }


def lane_status(topic: dict[str, Any], lane_name: str) -> tuple[str, str | None, dict[str, Any] | None]:
    lane = (topic.get("lanes") or {}).get(lane_name)
    if not isinstance(lane, dict):
        return "missing_lane", None, None
    manifest_path = lane.get("manifest")
    return str(lane.get("status") or "unknown"), manifest_path, lane


def artifact_exists(value: Any) -> bool:
    if not value:
        return False
    candidate = Path(str(value)).expanduser()
    return candidate.exists()


def lane_final_artifacts(lane: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(lane, dict):
        return {}
    artifacts = lane.get("final_artifacts")
    return artifacts if isinstance(artifacts, dict) else {}


def artifact_hint_for_lane(lane: dict[str, Any] | None) -> dict[str, Any]:
    lane = lane or {}
    final_artifacts = lane_final_artifacts(lane)
    return {
        "wechat_markdown": final_artifacts.get("markdown") or lane.get("final_markdown") or lane.get("base_markdown"),
        "wechat_html": final_artifacts.get("html") or lane.get("final_html") or lane.get("source_html"),
        "video": final_artifacts.get("video") or lane.get("final_video"),
        "video_srt": final_artifacts.get("srt") or lane.get("srt"),
        "video_render_plan": final_artifacts.get("timeline") or lane.get("render_plan"),
        "podcast_audio": final_artifacts.get("audio") or lane.get("audio_file"),
        "podcast_request": lane.get("provider_request"),
        "qc_report": (lane.get("qc") or {}).get("report") if isinstance(lane.get("qc"), dict) else None,
    }


def missing_required_artifacts(channel: str, lane: dict[str, Any] | None, hint: dict[str, Any]) -> list[str]:
    if not lane:
        return ["lane_manifest"]
    if channel in {"wechat_article", "weibo_post", "x_post"}:
        if artifact_exists(hint.get("wechat_html")) or artifact_exists(hint.get("wechat_markdown")):
            return []
        return ["wechat_html_or_markdown"]
    if channel in {"xiaohongshu_video", "douyin_video", "bilibili_video"}:
        return [] if artifact_exists(hint.get("video")) else ["video"]
    if channel == "podcast":
        return [] if artifact_exists(hint.get("podcast_audio")) else ["podcast_audio"]
    return []


def build_channel_pack(topic: dict[str, Any], decision_row: dict[str, Any], channel: str) -> dict[str, Any]:
    rule = CHANNEL_RULES[channel]
    status, manifest_path, lane = lane_status(topic, rule["source_lane"])
    hint = {
        **artifact_hint_for_lane(lane),
        **mapping_or_empty(decision_row.get("artifact_overrides")),
    }
    missing_artifacts = missing_required_artifacts(channel, lane, hint)
    ready = status in PUBLISH_READY_LANE_STATUSES and not missing_artifacts
    if status not in PUBLISH_READY_LANE_STATUSES:
        blocking_reason = f"lane_status_not_publish_ready:{status}"
    elif missing_artifacts:
        blocking_reason = "missing_required_artifacts:" + ",".join(missing_artifacts)
    else:
        blocking_reason = None
    account_slot = account_slot_for_channel(decision_row, channel)
    browser_profile_key = (
        decision_row.get(f"{channel}_browser_profile_key")
        or decision_row.get("browser_profile_key")
        or browser_profile_key_for_account(channel, account_slot)
        or channel
    )
    browser_profile = browser_profile_for_channel(channel, str(browser_profile_key))
    metadata_override = mapping_or_empty(decision_row.get("publish_metadata"))
    platform_notes = {
        **mapping_or_empty(metadata_override.get("platform_notes")),
        **mapping_or_empty(decision_row.get(channel)),
    }
    title = (
        metadata_override.get("title")
        or decision_row.get("title")
        or decision_row.get("topic_name")
        or topic.get("title")
    )
    pack = {
        "task_id": decision_row.get("task_id"),
        "batch_id": decision_row.get("batch_id"),
        "topic_id": topic.get("topic_id"),
        "variant_id": decision_row.get("variant_id") or "main",
        "title": title,
        "channel": channel,
        "source_lane": rule["source_lane"],
        "lane_status": status,
        "lane_manifest": manifest_path,
        "status": "ready_for_execution" if ready else "blocked_or_waiting",
        "blocking_reason": blocking_reason,
        "missing_artifacts": missing_artifacts,
        "executor_skill": rule["executor_skill"],
        "execution_mode": rule["mode"],
        "account_slot": account_slot,
        "account_profile": account_profile_for_channel(channel, account_slot),
        "account_context": mapping_or_empty(decision_row.get("account_context")),
        "matrix_role": decision_row.get("matrix_role") or mapping_or_empty(decision_row.get("account_context")).get("matrix_role"),
        "metadata_inheritance": mapping_or_empty(decision_row.get("metadata_inheritance")),
        "artifact_hint": hint,
        "publish_metadata": {
            **metadata_override,
            "title": title,
            "summary": metadata_override.get("summary") or metadata_override.get("description") or decision_row.get("summary") or decision_row.get("description"),
            "tags": metadata_override.get("tags") or decision_row.get("tags") or [],
            "scheduled_at": metadata_override.get("scheduled_at") or decision_row.get("scheduled_at") or decision_row.get("publish_time"),
            "visibility": metadata_override.get("visibility") or decision_row.get("visibility") or "default",
            "cover": metadata_override.get("cover") or decision_row.get("cover") or hint.get("cover"),
            "account_slot": account_slot,
            "platform_notes": platform_notes,
        },
        "account_operations": account_operations_for_channel(decision_row, channel),
    }
    if browser_profile:
        pack["browser_profile"] = browser_profile
    return pack


def build_account_operations_request(pack: dict[str, Any]) -> dict[str, Any]:
    operations = mapping_or_empty(pack.get("account_operations"))
    metadata = mapping_or_empty(pack.get("publish_metadata"))
    return {
        "schema_version": "dasheng.publish.operations_request.v1",
        "created_at": now_iso(),
        "stage": "publish",
        "mode": "account_operations_advisory",
        "task_id": pack.get("task_id"),
        "batch_id": pack.get("batch_id"),
        "topic_id": pack.get("topic_id"),
        "variant_id": pack.get("variant_id"),
        "title": pack.get("title"),
        "channel": pack.get("channel"),
        "account_slot": pack.get("account_slot"),
        "platform": operations.get("platform"),
        "status": operations.get("status"),
        "required_before_execution": operations.get("required", False),
        "bridge_skill": operations.get("bridge_skill"),
        "upstream_skill": operations.get("upstream_skill"),
        "upstream": operations.get("upstream"),
        "account_context": operations.get("account_context") or {},
        "requested_outputs": operations.get("requested_outputs") or [],
        "post_publish_metrics": operations.get("post_publish_metrics") or [],
        "content_context": {
            "title": metadata.get("title") or pack.get("title"),
            "summary": metadata.get("summary"),
            "tags": metadata.get("tags") or [],
            "scheduled_at": metadata.get("scheduled_at"),
            "visibility": metadata.get("visibility"),
            "artifacts": pack.get("artifact_hint") or {},
        },
        "constraints": {
            "advisory_only": True,
            "does_not_publish": True,
            "does_not_log_in": True,
            "core_facts_frozen": True,
            "core_thesis_frozen": True,
            "runtime_output_must_stay_in_channel_pack": True,
            "current_platform_rules_require_separate_verification": True,
        },
        "handoff": {
            "channel_pack": pack.get("pack_manifest"),
            "advice_json": operations.get("advice_json"),
            "advice_markdown": operations.get("advice_markdown"),
            "rebuild_publish_pack_after_required_review": operations.get("required", False),
        },
    }


def render_channel_readme(pack: dict[str, Any]) -> str:
    lines = [
        f"# {pack['title']}｜{pack['channel']}",
        "",
        f"- 状态：`{pack['status']}`",
        f"- 阻塞原因：`{pack['blocking_reason'] or 'none'}`",
        f"- 执行器：`{pack['executor_skill']}`",
        f"- 执行模式：`{pack['execution_mode']}`",
        f"- 来源 lane：`{pack['source_lane']}`",
        f"- lane manifest：`{pack['lane_manifest']}`",
        "",
        "## 关键产物",
    ]
    for key, value in (pack.get("artifact_hint") or {}).items():
        if value:
            lines.append(f"- {key}: `{value}`")
    browser_profile = pack.get("browser_profile") or {}
    if browser_profile:
        lines.extend(
            [
                "",
                "## 持久化浏览器 Profile",
                f"- 平台：`{browser_profile.get('platform')}`",
                f"- Profile key：`{browser_profile.get('profile_key')}`",
                f"- Profile 目录：`{browser_profile.get('profile_dir')}`",
                f"- 入口：`{browser_profile.get('entry_url')}`",
                f"- 打开命令：`{browser_profile.get('open_command')}`",
            ]
        )
    operations = pack.get("account_operations") or {}
    if operations:
        lines.extend(
            [
                "",
                "## 账号运营 Skill",
                f"- 状态：`{operations.get('status')}`",
                f"- 是否阻断受控执行：`{operations.get('blocks_guarded_execution', False)}`",
                f"- 桥接 Skill：`{operations.get('bridge_skill')}`",
                f"- 上游 Skill：`{operations.get('upstream_skill')}`",
                f"- 账号阶段：`{(operations.get('account_context') or {}).get('account_stage', 'unspecified')}`",
                f"- 请求文件：`{operations.get('request') or 'none'}`",
                f"- 建议 JSON：`{operations.get('advice_json') or 'none'}`",
                f"- 校验：`{operations.get('validation_reason') or 'not_checked'}`",
                "",
                "这一层只做起号、矩阵角色、标题/钩子、关键词、合集、节奏和复盘建议；不执行登录、上传或发布。",
            ]
        )
    if pack.get("missing_artifacts"):
        lines.extend(["", "## 缺失产物", *[f"- `{item}`" for item in pack["missing_artifacts"]]])
    execution_commands = pack.get("execution_commands") or {}
    if execution_commands:
        lines.extend(["", "## 安全执行命令"])
        if execution_commands.get("safe_executor_command"):
            lines.extend(
                [
                    "",
                    "安全执行预演，不发布：",
                    "",
                    "```bash",
                    str(execution_commands["safe_executor_command"]),
                    "```",
                ]
            )
        if execution_commands.get("confirmed_executor_command"):
            lines.extend(
                [
                    "",
                    "当前会话明确确认后才允许执行：",
                    "",
                    "```bash",
                    str(execution_commands["confirmed_executor_command"]),
                    "```",
                ]
            )
    lines.extend(
        [
            "",
            "## 执行说明",
            "",
            "发布前必须取得当前任务/Campaign 对账号、平台、内容、可见性和排期的整体授权。",
            "用户已明确要求发布后，授权范围内的最终发布点击和普通流程弹窗自动处理，不再逐项请求确认。",
            "已同步到当前电脑且能明确匹配平台/账号/时间的一次性验证码自动填写一次，不得输出或持久化。",
        ]
    )
    return "\n".join(lines)


def confirm_execute_supported_for_pack(pack: dict[str, Any]) -> bool:
    if pack.get("status") != "ready_for_execution":
        return False
    operations = mapping_or_empty(pack.get("account_operations"))
    if operations.get("required") and not operations.get("review_completed"):
        return False
    routes = xhs_execution_routes(pack) if pack.get("channel") == "xiaohongshu_video" else generic_execution_routes(pack)
    return any(str(route.get("type") or "") in CONFIRM_EXECUTABLE_ROUTE_TYPES for route in routes)


def execution_commands_for_pack(pack: dict[str, Any]) -> dict[str, str | bool | None]:
    execution_request = pack.get("execution_request")
    if not execution_request:
        return {"safe_executor_command": None, "confirmed_executor_command": None, "confirm_execute_supported": False}
    base = f"python3 scripts/execute_publish_request.py --execution-request {execution_request}"
    supported = confirm_execute_supported_for_pack(pack)
    return {
        "safe_executor_command": base,
        "confirmed_executor_command": f"{base} --confirm-execute" if supported else None,
        "confirm_execute_supported": supported,
    }


def qianfan_execution_route(pack: dict[str, Any]) -> dict[str, Any]:
    return {
        "route": "qianfan-local-api",
        "type": "qianfan_local_api",
        "upstream": "https://github.com/DevilJie/social-auto-upload-web-ui",
        "api_base": "${QIANFAN_API_BASE:-http://127.0.0.1:5409}",
        "account_slot": pack.get("account_slot"),
        "plan": [
            "check_local_backend",
            "resolve_named_qianfan_account",
            "post_video_payload_to_/postVideo",
            "recover_publish_history_or_platform_receipt",
        ],
    }


def xhs_execution_routes(pack: dict[str, Any]) -> list[dict[str, Any]]:
    title = (pack.get("publish_metadata") or {}).get("title") or pack.get("title")
    video_path = (pack.get("artifact_hint") or {}).get("video")
    tags = (pack.get("publish_metadata") or {}).get("tags") or []
    return [
        qianfan_execution_route(pack),
        {
            "route": "social-auto-upload",
            "type": "external_uploader_fallback",
            "upstream": "https://github.com/dreammis/social-auto-upload",
            "plan": ["convert_channel_pack", "check_named_account", "dry_run_upload", "wait_for_user_confirmation"],
        },
        {
            "route": "all-in-one",
            "type": "api_first_cli",
            "upstream": "https://github.com/cv-cat/All-IN-ONE",
            "preflight": ["aione auth xhs status", "aione xhs creator-login check-session --output json"],
            "plan": [
                "upload_media_with_creator_profile",
                "build_note_info_json_from_channel_pack",
                "post_note_with_creator_api",
                "query_published_note_info",
            ],
            "command_templates": [
                'aione xhs media upload --path-or-file "<video_or_image_path>" --media-type "<image_or_video>" --output json',
                'aione xhs creator post-note --note-info "<json>" --output json',
                "aione xhs publish all-note-info --output json",
            ],
            "payload_hint": {
                "title": title,
                "video": video_path,
                "tags": tags,
            },
        },
        {
            "route": "xhs-skills-spider-xhs",
            "type": "api_first_skill",
            "upstream": "https://github.com/cv-cat/XhsSkills + https://github.com/cv-cat/Spider_XHS",
            "plan": [
                "call_creator_media_upload",
                "call_creator_post_note",
                "recover_note_id_or_creator_publish_status",
            ],
        },
        {
            "route": "xiaohongshu-mcp",
            "type": "mcp_fallback",
            "upstream": "https://github.com/xpzouying/xiaohongshu-mcp",
            "plan": ["publish_video_or_image_note", "recover_mcp_result"],
        },
        {
            "route": "rednote-mcp",
            "type": "mcp_fallback",
            "upstream": "https://github.com/TimeCyber/mcp-xiaohongshu",
            "plan": ["publish_note_with_playwright_mcp", "recover_mcp_result"],
        },
        {
            "route": "browser-profile",
            "type": "browser_confirm_fallback",
            "open_command": (pack.get("browser_profile") or {}).get("open_command"),
            "plan": ["open_persistent_profile", "fill_creator_publish_form", "wait_for_user_confirmation"],
        },
    ]


def generic_execution_routes(pack: dict[str, Any]) -> list[dict[str, Any]]:
    channel = pack.get("channel")
    if channel == "wechat_article":
        return [
            {
                "route": "baoyu-post-to-wechat",
                "type": "skill_draft_push",
                "plan": ["push_wechat_draft", "recover_draft_id"],
            },
            {
                "route": "wechat-multi-publisher",
                "type": "skill_batch_draft_push_guarded_required",
                "plan": ["push_batch_draft", "recover_draft_id"],
            },
            {
                "route": "md2wechat",
                "type": "preprocess_fallback",
                "plan": ["convert_markdown_to_wechat_html", "export_browser_package"],
            },
            {
                "route": "browser-profile",
                "type": "browser_confirm_fallback",
                "open_command": (pack.get("browser_profile") or {}).get("open_command"),
                "plan": ["open_persistent_profile", "fill_wechat_editor", "wait_for_user_confirmation"],
            },
        ]
    if channel == "douyin_video":
        platform_notes = mapping_or_empty(mapping_or_empty(pack.get("publish_metadata")).get("platform_notes"))
        activity_selected = mapping_or_empty(platform_notes.get("activity_selected"))
        activity_id = platform_notes.get("activity_id") or activity_selected.get("id")
        social_route = {
            "route": "social-auto-upload",
            "type": "external_uploader_fallback",
            "upstream": "https://github.com/dreammis/social-auto-upload",
            "plan": ["convert_channel_pack", "check_named_account", "dry_run_upload", "wait_for_user_confirmation"],
        }
        opencli_route = {
            "route": "opencli-douyin",
            "type": "browser_cli_activity_capable",
            "upstream": "https://github.com/jackwener/OpenCLI",
            "activity_id": activity_id,
            "plan": ["discover_live_activities", "confirm_activity", "prepare_publish", "wait_for_user_confirmation"],
        }
        routes = [opencli_route, social_route] if activity_id else [social_route, opencli_route]
        return [
            qianfan_execution_route(pack),
            *routes,
            {
                "route": "douyin-upload-skill",
                "type": "skill_or_api_upload",
                "plan": ["doctor", "auth", "prepare_video_upload", "wait_for_user_confirmation"],
            },
            {
                "route": "browser-profile",
                "type": "browser_confirm_fallback",
                "open_command": (pack.get("browser_profile") or {}).get("open_command"),
                "plan": ["open_persistent_profile", "fill_douyin_upload_form", "wait_for_user_confirmation"],
            },
        ]
    if channel == "bilibili_video":
        return [
            qianfan_execution_route(pack),
            {
                "route": "social-auto-upload",
                "type": "external_uploader_fallback",
                "upstream": "https://github.com/dreammis/social-auto-upload",
                "plan": ["convert_channel_pack", "dry_run_upload", "wait_for_user_confirmation"],
            },
            {
                "route": "bilibili-upload-bridge",
                "type": "skill_bridge",
                "plan": ["build_submission_payload", "dry_run_upload", "wait_for_user_confirmation"],
            },
            {
                "route": "biliup-rs",
                "type": "archived_external_cli",
                "upstream": "https://github.com/biliup/biliup-rs",
                "binary": "biliup",
                "plan": ["historical_fallback_only", "do_not_select_as_primary"],
            },
            {
                "route": "manual-package",
                "type": "manual_package",
                "plan": ["export_title_description_cover_video", "wait_for_human_upload"],
            },
        ]
    if channel == "wechat_channels_video":
        return [
            qianfan_execution_route(pack),
            {
                "route": "social-auto-upload",
                "type": "external_uploader_fallback",
                "upstream": "https://github.com/dreammis/social-auto-upload",
                "plan": ["check_tencent_account", "dry_run_upload", "wait_for_user_confirmation"],
            },
            {
                "route": "browser-profile",
                "type": "browser_confirm_fallback",
                "open_command": (pack.get("browser_profile") or {}).get("open_command"),
                "plan": ["open_persistent_profile", "fill_channels_upload_form", "wait_for_user_confirmation"],
            },
            {
                "route": "manual-package",
                "type": "manual_package",
                "plan": ["export_title_description_cover_video", "wait_for_human_upload"],
            },
        ]
    if channel == "weibo_post":
        return [
            {
                "route": "baoyu-post-to-weibo",
                "type": "browser_confirm",
                "plan": ["prepare_weibo_post", "wait_for_user_confirmation"],
            },
        ]
    if channel == "x_post":
        return [
            {
                "route": "baoyu-post-to-x",
                "type": "browser_or_api_confirm",
                "plan": ["prepare_x_post", "wait_for_user_confirmation"],
            },
            {
                "route": "xurl",
                "type": "external_api_cli_fallback",
                "plan": ["check_x_api_auth", "prepare_media_upload"],
            },
        ]
    return [
        {
            "route": pack.get("executor_skill"),
            "type": pack.get("execution_mode"),
            "input_manifest": pack.get("pack_manifest"),
        }
    ]


def platform_for_channel(channel: Any) -> str:
    if channel == "xiaohongshu_video":
        return "xiaohongshu"
    if channel == "douyin_video":
        return "douyin"
    if channel == "bilibili_video":
        return "bilibili"
    if channel == "wechat_channels_video":
        return "wechat_channels"
    if channel == "wechat_article":
        return "wechat"
    if channel == "weibo_post":
        return "weibo"
    if channel == "x_post":
        return "x"
    return str(channel or "unknown")


def build_execution_request(pack: dict[str, Any]) -> dict[str, Any]:
    artifacts = pack.get("artifact_hint") or {}
    operations = mapping_or_empty(pack.get("account_operations"))
    if pack.get("status") != "ready_for_execution":
        request_status = "blocked"
    elif operations.get("required") and not operations.get("review_completed"):
        request_status = "waiting_for_operations_review"
    else:
        request_status = "ready_for_user_confirmation"
    request: dict[str, Any] = {
        "schema_version": "1.0",
        "created_at": now_iso(),
        "task_id": pack.get("task_id"),
        "batch_id": pack.get("batch_id"),
        "topic_id": pack.get("topic_id"),
        "variant_id": pack.get("variant_id"),
        "title": pack.get("title"),
        "channel": pack.get("channel"),
        "account_slot": pack.get("account_slot"),
        "status": request_status,
        "executor_skill": pack.get("executor_skill"),
        "execution_mode": pack.get("execution_mode"),
        "requires_user_confirmation": True,
        "confirmation_scope": "task_or_campaign_authorization",
        "authorized_interaction_policy": {
            "final_publish_click": "continue_without_reconfirming",
            "ordinary_platform_prompts": "auto_resolve_from_approved_publish_metadata",
            "synced_one_time_password": "fill_once_when_platform_account_and_time_match",
            "one_time_password_retention": "memory_only_never_log_or_persist",
            "hard_stop_challenges": [
                "graphical_captcha",
                "slider_captcha",
                "account_or_device_risk_review",
                "ambiguous_or_stale_one_time_password",
                "content_rejection",
                "authorization_scope_change",
            ],
        },
        "browser_window_policy": publish_browser_window_policy(),
        "channel_pack": pack.get("pack_manifest"),
        "inputs": {
            "artifacts": artifacts,
            "publish_metadata": pack.get("publish_metadata") or {},
            "browser_profile": pack.get("browser_profile"),
        },
        "blocking_reason": pack.get("blocking_reason"),
        "account_operations": operations or None,
        "fallback_policy": {
            "on_auth_failure": "open_persistent_browser_profile_or_export_manual_package",
            "on_declaration_agreement_or_cover_prompt": "auto_resolve_from_approved_publish_metadata_and_continue",
            "on_synced_one_time_password": "fill_once_when_platform_account_and_time_match_without_logging",
            "on_graphical_or_slider_captcha": "stop_and_report_without_looping",
            "on_platform_risk": "stop_and_report_without_looping",
            "on_executor_missing": "export_manual_package",
        },
        "output_contract": {
            "write_result_under": "same_channel_pack_directory",
            "required_fields": ["success", "status", "platform", "draft_id_or_url", "screenshot_or_error"],
        },
    }
    if pack.get("channel") == "xiaohongshu_video":
        request["platform"] = "xiaohongshu"
        request["route_priority"] = xhs_execution_routes(pack)
        request["notes"] = [
            "小红书优先 API-first / CLI / MCP，不把浏览器粘贴当主路径。",
            "用户已明确要求发布后，当前任务授权范围内的最终点击、普通弹窗和可明确匹配的一次性验证码不再逐项暂停确认。",
        ]
    else:
        request["platform"] = platform_for_channel(pack.get("channel"))
        request["route_priority"] = generic_execution_routes(pack)
    return request


def build_verification_request(pack: dict[str, Any]) -> dict[str, Any]:
    operations = mapping_or_empty(pack.get("account_operations"))
    return {
        "schema_version": "1.0",
        "created_at": now_iso(),
        "task_id": pack.get("task_id"),
        "batch_id": pack.get("batch_id"),
        "topic_id": pack.get("topic_id"),
        "variant_id": pack.get("variant_id"),
        "title": pack.get("title"),
        "channel": pack.get("channel"),
        "account_slot": pack.get("account_slot"),
        "platform": platform_for_channel(pack.get("channel")),
        "status": "pending_execution",
        "channel_pack": pack.get("pack_manifest"),
        "execution_request": pack.get("execution_request"),
        "required_evidence": [
            "platform_url_or_draft_id",
            "account_identifier",
            "published_or_draft_at",
            "screenshot_or_platform_response",
        ],
        "account_operations": operations or None,
        "requested_performance_metrics": operations.get("post_publish_metrics") or [],
        "guard_skill": "publish-guard",
        "success_condition": "Only mark published after URL/draft id is recovered and checked.",
    }


def write_channel_pack_files(out_dir: Path, pack: dict[str, Any]) -> dict[str, str]:
    pack_dir = out_dir / "channel_packs" / safe_slug(pack.get("topic_id"), "topic") / safe_slug(pack.get("channel"), "channel")
    if pack.get("task_id"):
        pack_dir = pack_dir / safe_slug(pack.get("task_id"), "publish-task")
    pack_path = pack_dir / "channel_pack.json"
    readme_path = pack_dir / "README.md"
    execution_request_path = pack_dir / "execution_request.json"
    verification_request_path = pack_dir / "verification_request.json"
    form_validation_path = pack_dir / "platform_form_validation.json"
    operations_request_path = pack_dir / "account_operations_request.json"
    operations_advice_path = pack_dir / "account_operations_advice.json"
    operations_advice_md_path = pack_dir / "account_operations_advice.md"
    paths = {
        "pack_dir": str(pack_dir.resolve()),
        "pack_manifest": str(pack_path.resolve()),
        "readme": str(readme_path.resolve()),
        "execution_request": str(execution_request_path.resolve()),
        "verification_request": str(verification_request_path.resolve()),
        "platform_form_validation_report": str(form_validation_path.resolve()),
    }
    operations = mapping_or_empty(pack.get("account_operations"))
    if operations:
        operations = {
            **operations,
            "channel": pack.get("channel"),
            "request": str(operations_request_path.resolve()),
            "advice_json": str(operations_advice_path.resolve()),
            "advice_markdown": str(operations_advice_md_path.resolve()),
        }
        if operations.get("enabled"):
            review_completed, validation_reason = validate_account_operations_advice(operations_advice_path, operations)
            operations["review_completed"] = review_completed
            operations["validation_reason"] = validation_reason
            operations["status"] = (
                "completed"
                if review_completed
                else ("required_before_execution" if operations.get("required") else "advisory_pending")
            )
        else:
            operations["review_completed"] = False
            operations["validation_reason"] = "account_operations_disabled"
            operations["status"] = "disabled"
        paths.update(
            {
                "account_operations_request": operations["request"],
                "account_operations_advice": operations["advice_json"],
                "account_operations_advice_markdown": operations["advice_markdown"],
            }
        )
    pack_with_paths = {**pack, **paths, "account_operations": operations or None}
    form_validation = validate_channel_pack(pack_with_paths, source_path=pack_path)
    write_json(form_validation_path, form_validation)
    pack_with_paths["platform_form_validation"] = {
        "status": form_validation["status"],
        "report": str(form_validation_path.resolve()),
        "blocking_error_count": form_validation["summary"]["blocking_error_count"],
        "warning_count": form_validation["summary"]["warning_count"],
    }
    if form_validation["status"] == "blocked" and pack_with_paths.get("status") == "ready_for_execution":
        codes = [str(item.get("code")) for item in form_validation.get("blocking_errors") or []]
        pack_with_paths["status"] = "blocked_or_waiting"
        pack_with_paths["blocking_reason"] = "platform_form_validation_failed:" + ",".join(codes)
    pack_with_paths["execution_commands"] = execution_commands_for_pack(pack_with_paths)
    write_json(pack_path, pack_with_paths)
    write_text(readme_path, render_channel_readme(pack_with_paths))
    if operations and operations.get("enabled"):
        write_json(operations_request_path, build_account_operations_request(pack_with_paths))
    write_json(execution_request_path, build_execution_request(pack_with_paths))
    write_json(verification_request_path, build_verification_request(pack_with_paths))
    return {
        **paths,
        "execution_commands": pack_with_paths["execution_commands"],
        "account_operations": pack_with_paths.get("account_operations"),
        "platform_form_validation": pack_with_paths["platform_form_validation"],
        "status": pack_with_paths["status"],
        "blocking_reason": pack_with_paths.get("blocking_reason"),
    }


def build_execution_manifest(run_id: str, channel_packs: list[dict[str, Any]]) -> dict[str, Any]:
    executions = []
    for pack in channel_packs:
        blocked = pack["status"] != "ready_for_execution"
        operations = mapping_or_empty(pack.get("account_operations"))
        operations_waiting = bool(operations.get("required") and not operations.get("review_completed"))
        if blocked:
            execution_status = (
                "blocked_platform_form_validation"
                if str(pack.get("blocking_reason") or "").startswith("platform_form_validation_failed:")
                else "waiting_for_transwrite_lane"
            )
        elif operations_waiting:
            execution_status = "waiting_for_operations_review"
        else:
            execution_status = "pending_user_confirmation"
        executions.append(
            {
                "task_id": pack.get("task_id"),
                "batch_id": pack.get("batch_id"),
                "topic_id": pack["topic_id"],
                "variant_id": pack.get("variant_id"),
                "title": pack["title"],
                "channel": pack["channel"],
                "account_slot": pack.get("account_slot"),
                "status": execution_status,
                "executor_skill": pack["executor_skill"],
                "executor_invocation": {
                    "type": "skill_or_manual_package",
                    "mode": pack["execution_mode"],
                    "input_manifest": pack.get("pack_manifest") or pack["lane_manifest"],
                    "execution_request": pack.get("execution_request"),
                    "verification_request": pack.get("verification_request"),
                    "safe_executor_command": (pack.get("execution_commands") or {}).get("safe_executor_command"),
                    "confirmed_executor_command": (pack.get("execution_commands") or {}).get("confirmed_executor_command"),
                    "confirm_execute_supported": (pack.get("execution_commands") or {}).get("confirm_execute_supported", False),
                    "notes": "发布前必须先获得当前任务/Campaign 的整体授权；授权后的最终点击、普通弹窗和可明确匹配的一次性验证码按交互策略自动处理。",
                    "browser_profile": pack.get("browser_profile"),
                    "account_operations": operations or None,
                },
            }
        )
    return {
        "run_id": run_id,
        "stage": "publish",
        "status": "pending_execution",
        "executions": executions,
    }


def render_publish_plan(run_id: str, channel_packs: list[dict[str, Any]]) -> str:
    lines = [
        f"# 07 发布执行计划｜{run_id}",
        "",
        "Publish 只做验收、平台衍生包装、推草稿/发布包和链接回收；不重写核心正文、事实或主视频。",
        "",
    ]
    for pack in channel_packs:
        operations = mapping_or_empty(pack.get("account_operations"))
        operations_suffix = f"；运营审查 {operations.get('status')}" if operations else ""
        lines.append(f"- {pack['title']}｜{pack['channel']}：{pack['status']}（{pack['executor_skill']}）{operations_suffix}")
    return "\n".join(lines)


def render_publish_package(channel_packs: list[dict[str, Any]]) -> str:
    lines = ["# 07 发布包", ""]
    for pack in channel_packs:
        operations = mapping_or_empty(pack.get("account_operations"))
        lines.extend(
            [
                f"## {pack['title']}｜{pack['channel']}",
                "",
                f"- 状态：`{pack['status']}`",
                f"- 来源 lane：`{pack['source_lane']}`",
                f"- lane manifest：`{pack['lane_manifest']}`",
                f"- 执行器：`{pack['executor_skill']}`",
                f"- 运营 Skill：`{operations.get('upstream_skill') or 'none'}`",
                f"- 运营审查：`{operations.get('status') or 'not_applicable'}`",
                "",
            ]
        )
    return "\n".join(lines)


def build_publish_outputs(
    *,
    transwrite_manifest_path: Path,
    publish_decision_path: Path,
    output_dir: Path | None = None,
) -> dict[str, Any]:
    transwrite_manifest = ensure_stage_manifest(transwrite_manifest_path, "transwrite")
    publish_decision = ensure_publish_decision_gate(publish_decision_path)
    run_id = str(transwrite_manifest.get("run_id") or publish_decision.get("run_id") or "").strip()
    if not run_id:
        raise WorkflowContractError("无法从 transwrite_manifest 或 publish_decision 推断 run_id")
    out_dir = ensure_runtime_output_dir(output_dir or canonical_stage_dir("publish", run_id), label="publish output_dir")
    out_dir.mkdir(parents=True, exist_ok=True)
    topic_map = topics_by_id(transwrite_manifest)

    channel_packs: list[dict[str, Any]] = []
    decision_tasks = publish_decision.get("tasks")
    decision_rows = decision_tasks if isinstance(decision_tasks, list) and decision_tasks else publish_decision.get("topics") or []
    for row in decision_rows:
        topic_id = str(row.get("topic_id") or "").strip()
        topic = topic_map.get(topic_id)
        if not topic:
            raise WorkflowContractError(f"publish_decision 中的 topic_id 未命中 transwrite_manifest：{topic_id or '<empty>'}")
        channels = [str(row.get("channel"))] if row.get("task_id") and row.get("channel") in CHANNEL_RULES else normalize_channels(row)
        for channel in channels:
            channel_packs.append(build_channel_pack(topic, row, channel))

    channel_packs = [{**pack, **write_channel_pack_files(out_dir, pack)} for pack in channel_packs]

    plan_path = out_dir / "07_发布计划.md"
    package_path = out_dir / "07_发布包.md"
    execution_path = out_dir / "channel_execution_manifest.json"
    verification_path = out_dir / "publish_verification_report.json"
    manifest_path = out_dir / "publish_manifest.json"
    write_text(plan_path, render_publish_plan(run_id, channel_packs))
    write_text(package_path, render_publish_package(channel_packs))
    execution_manifest = build_execution_manifest(run_id, channel_packs)
    write_json(execution_path, execution_manifest)
    initial_manifest_stub = {"channel_packs": channel_packs}
    publish_summary = aggregate_publish_state(out_dir, [], initial_manifest_stub)
    verification = {
        "run_id": run_id,
        "stage": "publish",
        "status": publish_summary["status"],
        "records": [],
        "published_links": [],
        "draft_records": [],
        "publish_summary": publish_summary,
        "instructions": ["发布后回填平台链接、发布时间、账号、截图或草稿 ID。"],
    }
    write_json(verification_path, verification)
    publish_manifest = {
        "run_id": run_id,
        "batch_id": publish_decision.get("batch_id") or publish_decision.get("run_id"),
        "stage": "publish",
        "status": "pending_execution",
        "created_at": now_iso(),
        "source_transwrite_manifest": str(transwrite_manifest_path.resolve()),
        "publish_decision": str(publish_decision_path.resolve()),
        "channel_packs": channel_packs,
        "publish_results": [],
        "publish_summary": publish_summary,
        "artifacts": [
            str(plan_path.resolve()),
            str(package_path.resolve()),
            str(execution_path.resolve()),
            str(verification_path.resolve()),
        ],
        "next_stage": "postmortem",
    }
    write_json(manifest_path, publish_manifest)
    return {**publish_manifest, "manifest_file": str(manifest_path.resolve()), "out_dir": str(out_dir.resolve())}


def main() -> None:
    parser = argparse.ArgumentParser(description="Newma Stage 5 Publish execution pack builder")
    parser.add_argument("--transwrite-manifest", required=True)
    parser.add_argument("--publish-decision", required=True)
    parser.add_argument("--output-dir")
    args = parser.parse_args()
    result = build_publish_outputs(
        transwrite_manifest_path=Path(args.transwrite_manifest).expanduser().resolve(),
        publish_decision_path=Path(args.publish_decision).expanduser().resolve(),
        output_dir=Path(args.output_dir).expanduser().resolve() if args.output_dir else None,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
