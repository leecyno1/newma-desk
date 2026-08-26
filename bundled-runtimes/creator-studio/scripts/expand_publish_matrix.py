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
DEFAULT_ACCOUNT_REGISTRY = ROOT / "configs" / "publish" / "account_registry.json"
SUPPORTED_CHANNELS = {
    "wechat_article",
    "weibo_post",
    "x_post",
    "xiaohongshu_video",
    "douyin_video",
    "bilibili_video",
    "wechat_channels_video",
    "podcast",
}
ARTIFACT_PATH_FIELDS = {
    "wechat_markdown",
    "wechat_html",
    "video",
    "video_srt",
    "video_render_plan",
    "podcast_audio",
    "podcast_request",
    "cover",
}
SENSITIVE_KEY_MARKERS = {
    "password",
    "passwd",
    "cookie",
    "token",
    "secret",
    "api_key",
    "apikey",
    "access_key",
    "private_key",
    "proxy_password",
}


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def mapping(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def account_registry_path() -> Path:
    return Path(os.environ.get("DASHENG_PUBLISH_ACCOUNT_REGISTRY") or DEFAULT_ACCOUNT_REGISTRY).expanduser()


def load_account_channels() -> dict[str, Any]:
    path = account_registry_path()
    if not path.exists():
        return {}
    payload = read_json(path)
    channels = payload.get("channels") if isinstance(payload, dict) else None
    return channels if isinstance(channels, dict) else {}


def safe_slug(value: Any, fallback: str = "item") -> str:
    text = str(value or "").strip()
    cleaned = "".join(char.lower() if char.isalnum() else "-" for char in text)
    cleaned = "-".join(part for part in cleaned.split("-") if part)
    return cleaned or fallback


def normalize_slot(value: Any) -> str:
    text = str(value or "slot-1").strip()
    digits = "".join(char for char in text if char.isdigit())
    if digits:
        return f"slot-{digits}"
    normalized = text.lower().replace("_", "-").replace(" ", "-")
    return normalized if normalized.startswith("slot-") else f"slot-{normalized}"


def registered_slots(channel: str, account_channels: dict[str, Any]) -> dict[str, Any]:
    row = registered_channel(channel, account_channels)
    slots = row.get("slots") if isinstance(row, dict) else None
    return slots if isinstance(slots, dict) else {}


def registered_channel(channel: str, account_channels: dict[str, Any]) -> dict[str, Any]:
    row = account_channels.get(channel)
    return row if isinstance(row, dict) else {}


def slot_config(channel: str, slot: str, account_channels: dict[str, Any]) -> dict[str, Any]:
    row = registered_slots(channel, account_channels).get(slot)
    return row if isinstance(row, dict) else {}


def target_slots(channel: str, raw: Any, account_channels: dict[str, Any]) -> tuple[list[str], list[str]]:
    slots = registered_slots(channel, account_channels)
    errors: list[str] = []
    if raw == "all":
        selected = list(slots) if slots else ["slot-1"]
    elif isinstance(raw, list) and raw:
        selected = [normalize_slot(item) for item in raw]
    elif slots:
        defaults = [name for name, row in slots.items() if isinstance(row, dict) and row.get("default")]
        selected = defaults or [next(iter(slots))]
    else:
        selected = ["slot-1"]
    if slots:
        for slot in selected:
            if slot not in slots:
                errors.append(f"unknown_account_slot:{channel}:{slot}")
    return list(dict.fromkeys(selected)), errors


def profile_for_slot(channel: str, slot: str, account_channels: dict[str, Any]) -> str | None:
    row = slot_config(channel, slot, account_channels)
    value = row.get("browser_profile")
    return str(value) if value else None


def account_context_for_slot(channel: str, slot: str, account_channels: dict[str, Any]) -> dict[str, Any]:
    row = slot_config(channel, slot, account_channels)
    metadata = mapping(row.get("account_metadata"))
    network_policy = mapping(row.get("network_policy"))
    safe_network_policy = {
        key: network_policy.get(key)
        for key in ("mode", "proxy_profile", "region")
        if network_policy.get(key) not in (None, "")
    }
    context = {
        "slot": slot,
        "label": row.get("label"),
        "group": metadata.get("group"),
        "matrix_role": metadata.get("matrix_role"),
        "owner_alias": metadata.get("owner_alias"),
        "operator_alias": metadata.get("operator_alias"),
        "network_policy": safe_network_policy,
        "auth_modes": row.get("auth_modes") if isinstance(row.get("auth_modes"), list) else [],
    }
    return {key: value for key, value in context.items() if value not in (None, "", [], {})}


def resolve_artifacts(value: Any, *, base_dir: Path) -> dict[str, Any]:
    artifacts = mapping(value)
    resolved: dict[str, Any] = {}
    for key, raw in artifacts.items():
        if key in ARTIFACT_PATH_FIELDS and raw:
            path = Path(str(raw)).expanduser()
            resolved[key] = str((base_dir / path).resolve()) if not path.is_absolute() else str(path.resolve())
        else:
            resolved[key] = raw
    return resolved


def merge_metadata(*rows: Any) -> dict[str, Any]:
    merged: dict[str, Any] = {}
    for row in rows:
        merged.update(mapping(row))
    return merged


def strip_sensitive_fields(value: Any, *, prefix: str) -> tuple[Any, list[str]]:
    if isinstance(value, list):
        cleaned_items = []
        issues: list[str] = []
        for index, item in enumerate(value):
            cleaned, nested = strip_sensitive_fields(item, prefix=f"{prefix}[{index}]")
            cleaned_items.append(cleaned)
            issues.extend(nested)
        return cleaned_items, issues
    if not isinstance(value, dict):
        return value, []
    cleaned: dict[str, Any] = {}
    issues: list[str] = []
    for key, item in value.items():
        normalized = str(key).lower().replace("-", "_").replace(" ", "_")
        path = f"{prefix}.{key}"
        if any(marker in normalized for marker in SENSITIVE_KEY_MARKERS):
            issues.append(path)
            continue
        nested_value, nested_issues = strip_sensitive_fields(item, prefix=path)
        cleaned[str(key)] = nested_value
        issues.extend(nested_issues)
    return cleaned, issues


def expand_matrix(matrix: dict[str, Any], *, source_path: Path) -> dict[str, Any]:
    account_channels = load_account_channels()
    defaults = mapping(matrix.get("defaults"))
    errors: list[str] = []
    tasks: list[dict[str, Any]] = []
    task_ids: set[str] = set()

    if str(matrix.get("status") or "") != "approved":
        errors.append(f"matrix_not_approved:{matrix.get('status') or 'missing'}")

    for item_index, item in enumerate(matrix.get("items") or [], start=1):
        if not isinstance(item, dict):
            errors.append(f"invalid_item:{item_index}")
            continue
        topic_id = str(item.get("topic_id") or "").strip()
        if not topic_id:
            errors.append(f"missing_topic_id:{item_index}")
            continue
        variant_id = str(item.get("variant_id") or "main").strip() or "main"
        item_artifacts = resolve_artifacts(item.get("artifact_overrides"), base_dir=source_path.parent)
        targets = item.get("targets") or []
        if not isinstance(targets, list) or not targets:
            errors.append(f"missing_targets:{topic_id}:{variant_id}")
            continue

        for target_index, target in enumerate(targets, start=1):
            if not isinstance(target, dict):
                errors.append(f"invalid_target:{topic_id}:{target_index}")
                continue
            channel = str(target.get("channel") or "").strip()
            if channel not in SUPPORTED_CHANNELS:
                errors.append(f"unsupported_channel:{topic_id}:{channel or '<empty>'}")
                continue
            slots, slot_errors = target_slots(channel, target.get("account_slots"), account_channels)
            errors.extend(f"{topic_id}:{variant_id}:{error}" for error in slot_errors)
            channel_registry = registered_channel(channel, account_channels)
            matrix_channel_defaults = mapping(mapping(defaults.get("channels")).get(channel))
            target_artifacts = {
                **item_artifacts,
                **resolve_artifacts(target.get("artifact_overrides"), base_dir=source_path.parent),
            }

            for slot in slots:
                task_id = safe_slug(f"{topic_id}-{variant_id}-{channel}-{slot}", "publish-task")
                if task_id in task_ids:
                    errors.append(f"duplicate_task_id:{task_id}")
                    continue
                task_ids.add(task_id)
                profile_key = profile_for_slot(channel, slot, account_channels)
                slot_row = slot_config(channel, slot, account_channels)
                raw_metadata_layers = [
                    ("matrix_defaults", defaults.get("publish_metadata")),
                    ("matrix_channel_defaults", matrix_channel_defaults.get("publish_metadata")),
                    ("registry_channel_presets", channel_registry.get("publish_presets")),
                    ("content_variant", item.get("publish_metadata")),
                    ("registry_account_presets", slot_row.get("publish_presets")),
                    ("target_override", target.get("publish_metadata")),
                ]
                metadata_layers = []
                for layer_name, layer in raw_metadata_layers:
                    cleaned_layer, sensitive_paths = strip_sensitive_fields(
                        mapping(layer),
                        prefix=f"{channel}.{slot}.{layer_name}",
                    )
                    metadata_layers.append(cleaned_layer)
                    errors.extend(f"sensitive_publish_metadata:{path}" for path in sensitive_paths)
                metadata = merge_metadata(*metadata_layers)
                clean_target_notes, sensitive_note_paths = strip_sensitive_fields(
                    mapping(target.get("platform_notes")),
                    prefix=f"{channel}.{slot}.target_platform_notes",
                )
                errors.extend(f"sensitive_publish_metadata:{path}" for path in sensitive_note_paths)
                metadata["platform_notes"] = merge_metadata(
                    *(mapping(layer).get("platform_notes") for layer in metadata_layers),
                    clean_target_notes,
                )
                account_context = account_context_for_slot(channel, slot, account_channels)
                task: dict[str, Any] = {
                    "task_id": task_id,
                    "batch_id": str(matrix.get("batch_id") or matrix.get("run_id") or "publish-batch"),
                    "topic_id": topic_id,
                    "variant_id": variant_id,
                    "channel": channel,
                    "channels": [channel],
                    "account_slot": slot,
                    "account_context": account_context,
                    "matrix_role": account_context.get("matrix_role"),
                    "artifact_overrides": target_artifacts,
                    "publish_metadata": metadata,
                    "metadata_inheritance": {
                        "order": [
                            "matrix_defaults",
                            "matrix_channel_defaults",
                            "registry_channel_presets",
                            "content_variant",
                            "registry_account_presets",
                            "target_override",
                        ],
                        "channel_presets_applied": bool(mapping(channel_registry.get("publish_presets"))),
                        "account_presets_applied": bool(mapping(slot_row.get("publish_presets"))),
                        "final_snapshot_frozen": True,
                    },
                    "title": metadata.get("title"),
                    "summary": metadata.get("summary") or metadata.get("description"),
                    "tags": metadata.get("tags") or [],
                    "scheduled_at": metadata.get("scheduled_at"),
                    "cover": metadata.get("cover"),
                    channel: metadata["platform_notes"],
                }
                if profile_key:
                    task["browser_profile_key"] = profile_key
                tasks.append(task)

    topics: dict[str, set[str]] = {}
    for task in tasks:
        topics.setdefault(str(task["topic_id"]), set()).add(str(task["channel"]))
    topic_rows = [
        {"topic_id": topic_id, "channels": sorted(channels)}
        for topic_id, channels in sorted(topics.items())
    ]
    return {
        "schema_version": "1.0",
        "created_at": now_iso(),
        "run_id": matrix.get("run_id"),
        "batch_id": matrix.get("batch_id") or matrix.get("run_id"),
        "gate": "Channel Gate",
        "status": "blocked" if errors else "approved",
        "source_publish_matrix": str(source_path.resolve()),
        "topics": topic_rows,
        "tasks": tasks,
        "errors": errors,
        "summary": {
            "source_item_count": len(matrix.get("items") or []),
            "topic_count": len(topic_rows),
            "task_count": len(tasks),
            "error_count": len(errors),
            "tasks_by_channel": {
                channel: sum(1 for task in tasks if task.get("channel") == channel)
                for channel in sorted({str(task.get("channel")) for task in tasks})
            },
        },
        "safety": {
            "does_not_publish": True,
            "tasks_are_independently_validated": True,
            "tasks_require_independent_results": True,
        }
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Expand content variants, platforms and account slots into independent Publish tasks.")
    parser.add_argument("--matrix", required=True)
    parser.add_argument("--output", help="Expanded publish_decision.json path.")
    parser.add_argument("--fail-on-error", action="store_true")
    args = parser.parse_args()

    matrix_path = Path(args.matrix).expanduser().resolve()
    report = expand_matrix(read_json(matrix_path), source_path=matrix_path)
    output = Path(args.output).expanduser().resolve() if args.output else matrix_path.parent / "publish_decision.expanded.json"
    write_json(output, report)
    report["output"] = str(output.resolve())
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if args.fail_on_error and report["status"] != "approved":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
