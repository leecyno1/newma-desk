#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import textwrap
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps

from path_config import get_project_root


ROOT = get_project_root()
DEFAULT_ACCOUNT_REGISTRY = ROOT / "configs" / "publish" / "account_registry.json"
DEFAULT_CONTENT_RULES = ROOT / "configs" / "publish" / "platform_content_rules.json"
CHANNELS = (
    "xiaohongshu_video",
    "douyin_video",
    "bilibili_video",
    "wechat_channels_video",
)
FONT_CANDIDATES = (
    Path("/System/Library/Fonts/PingFang.ttc"),
    Path("/System/Library/Fonts/STHeiti Medium.ttc"),
    Path("/Library/Fonts/Arial Unicode.ttf"),
)


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value.rstrip() + "\n", encoding="utf-8")


def mapping(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def string_list(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def resolve_path(value: Any, *, base_dir: Path) -> Path:
    path = Path(str(value)).expanduser()
    return path.resolve() if path.is_absolute() else (base_dir / path).resolve()


def find_font_path() -> Path:
    for path in FONT_CANDIDATES:
        if path.exists():
            return path
    raise RuntimeError("No Chinese-capable font found for publish cover rendering.")


def font(size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(find_font_path()), size=max(size, 12))


def rounded_mask(size: tuple[int, int], radius: int) -> Image.Image:
    mask = Image.new("L", size, 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, size[0], size[1]), radius=radius, fill=255)
    return mask


def extract_video_frame(video: Path, output: Path, at_seconds: float) -> Path:
    output.parent.mkdir(parents=True, exist_ok=True)
    command = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-ss",
        f"{max(at_seconds, 0.0):.3f}",
        "-i",
        str(video),
        "-frames:v",
        "1",
        "-q:v",
        "2",
        str(output),
    ]
    completed = subprocess.run(command, capture_output=True, text=True, check=False)
    if completed.returncode != 0 or not output.exists():
        raise RuntimeError(f"Failed to extract publish cover frame: {completed.stderr.strip()}")
    return output


def split_cover_lines(value: Any, *, max_chars: int) -> list[str]:
    explicit = string_list(value)
    if len(explicit) > 1:
        return explicit[:3]
    text = explicit[0] if explicit else ""
    if not text:
        return []
    lines: list[str] = []
    current = ""
    for char in text:
        if len(current) >= max_chars and char not in "，。！？、：；,.!?":
            lines.append(current)
            current = char
        else:
            current += char
    if current:
        lines.append(current)
    return lines[:3]


def draw_fitted_text(
    draw: ImageDraw.ImageDraw,
    lines: list[str],
    box: tuple[int, int, int, int],
    *,
    start_size: int,
    min_size: int,
    fill: str,
    spacing: int,
) -> tuple[int, int]:
    left, top, right, bottom = box
    size = start_size
    chosen = font(size)
    while size > min_size:
        chosen = font(size)
        widths = [draw.textbbox((0, 0), line, font=chosen)[2] for line in lines]
        line_height = draw.textbbox((0, 0), "科技Ag", font=chosen)[3]
        total_height = line_height * len(lines) + spacing * max(len(lines) - 1, 0)
        if max(widths or [0]) <= right - left and total_height <= bottom - top:
            break
        size -= 2
    y = top
    line_height = draw.textbbox((0, 0), "科技Ag", font=chosen)[3]
    for line in lines:
        draw.text((left, y), line, font=chosen, fill=fill)
        y += line_height + spacing
    return size, y


def render_cover(
    *,
    source: Path,
    output: Path,
    width: int,
    height: int,
    title: Any,
    kicker: str,
    subtitle: str,
    account_label: str,
    accent: str,
) -> Path:
    with Image.open(source) as opened:
        source_image = opened.convert("RGB")

    background = ImageOps.fit(source_image, (width, height), method=Image.Resampling.LANCZOS)
    background = background.filter(ImageFilter.GaussianBlur(radius=max(width, height) / 90))
    canvas = background.convert("RGBA")
    canvas.alpha_composite(Image.new("RGBA", canvas.size, (3, 12, 15, 150)))

    portrait = height > width
    if not portrait:
        card_height = height - 132
        card_width = card_height
        card = ImageOps.fit(source_image, (card_width, card_height), method=Image.Resampling.LANCZOS)
        card_x = width - card_width - 66
        card_y = 66

    overlay = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    margin = 72 if portrait else 82
    draw.rounded_rectangle((margin, margin, margin + 224, margin + 56), radius=28, fill=(6, 22, 25, 220))
    draw.text((margin + 22, margin + 12), account_label, font=font(26), fill=accent)

    kicker_y = margin + 86
    draw.text((margin, kicker_y), kicker, font=font(30 if portrait else 34), fill="#7fffd4")
    line_width = 170 if portrait else 210
    draw.rounded_rectangle((margin, kicker_y + 52, margin + line_width, kicker_y + 60), radius=4, fill=accent)

    lines = split_cover_lines(title, max_chars=9 if portrait else 10)
    if portrait:
        title_box = (margin, kicker_y + 82, width - margin, int(height * 0.36))
        start_size = 78
    else:
        title_box = (margin, kicker_y + 88, card_x - 46, int(height * 0.67))
        start_size = 82
    _, title_bottom = draw_fitted_text(
        draw,
        lines,
        title_box,
        start_size=start_size,
        min_size=48,
        fill="#f4f5ea",
        spacing=12,
    )
    subtitle_lines = textwrap.wrap(subtitle, width=28 if portrait else 22)[:2]
    if portrait:
        subtitle_top = title_bottom + 18
        subtitle_bottom = subtitle_top + 42 * len(subtitle_lines)
        card_y = max(int(height * 0.36), subtitle_bottom + 28)
        card_size = min(width - 112, height - card_y - 144)
        if card_size < 480:
            raise ValueError(f"Portrait publish cover has insufficient room for a complete source card: {width}x{height}")
        card = ImageOps.contain(source_image, (card_size, card_size), method=Image.Resampling.LANCZOS)
        card_width, card_height = card.size
        card_x = (width - card_width) // 2
    else:
        subtitle_top = min(title_bottom + 36, height - 170)
    for index, line in enumerate(subtitle_lines):
        draw.text((margin, subtitle_top + index * 42), line, font=font(28 if portrait else 30), fill="#d4ddd7")
    draw.text((margin, height - 66), "数据口径以视频与来源稿为准｜不构成投资建议", font=font(22), fill="#95a39e")
    canvas.alpha_composite(overlay)

    card_layer = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    mask = rounded_mask(card.size, radius=28)
    card_layer.paste(card.convert("RGBA"), (card_x, card_y), mask)
    canvas.alpha_composite(card_layer)

    border = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    ImageDraw.Draw(border).rounded_rectangle(
        (card_x, card_y, card_x + card_width - 1, card_y + card_height - 1),
        radius=28,
        outline=(127, 255, 212, 72),
        width=2,
    )
    canvas.alpha_composite(border)
    output.parent.mkdir(parents=True, exist_ok=True)
    canvas.convert("RGB").save(output, quality=94, optimize=True)
    return output


def logical_slot(registry: dict[str, Any], logical_account: str, channel: str) -> str:
    logical = mapping(mapping(registry.get("logical_accounts")).get(logical_account))
    slot = mapping(logical.get("routes")).get(channel)
    if not slot:
        raise ValueError(f"Logical account {logical_account!r} has no route for {channel}.")
    channel_slots = mapping(mapping(mapping(registry.get("channels")).get(channel)).get("slots"))
    if slot not in channel_slots:
        raise ValueError(f"Logical account {logical_account!r} maps {channel} to unknown slot {slot!r}.")
    return str(slot)


def packaging_warnings(packaging: dict[str, Any], rule: dict[str, Any]) -> list[str]:
    warnings: list[str] = []
    title = str(packaging.get("title") or "")
    title_limit = mapping(rule.get("title")).get("recommended_max_chars")
    if title_limit and len(title) > int(title_limit):
        warnings.append(f"title_over_recommended_length:{len(title)}>{title_limit}")
    tags = string_list(packaging.get("tags"))
    tag_rule = mapping(rule.get("tags"))
    if tag_rule.get("recommended_min") and len(tags) < int(tag_rule["recommended_min"]):
        warnings.append("too_few_tags")
    if tag_rule.get("recommended_max") and len(tags) > int(tag_rule["recommended_max"]):
        warnings.append("too_many_tags")
    return warnings


def build_matrix(
    spec: dict[str, Any],
    *,
    spec_path: Path,
    output_dir: Path,
    registry: dict[str, Any],
    rules: dict[str, Any],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    items: list[dict[str, Any]] = []
    packaging_index: list[dict[str, Any]] = []
    topic_id = str(spec.get("topic_id") or "").strip()
    if not topic_id:
        raise ValueError("Campaign spec requires topic_id.")
    for variant in spec.get("variants") or []:
        variant_id = str(variant.get("variant_id") or "").strip()
        logical_account = str(variant.get("logical_account") or "").strip()
        video = resolve_path(variant.get("video"), base_dir=spec_path.parent)
        if not variant_id or not logical_account or not video.exists():
            raise ValueError(f"Invalid campaign variant: {variant_id or '<missing>'}")
        cover_source_value = variant.get("cover_source")
        if cover_source_value:
            cover_source = resolve_path(cover_source_value, base_dir=spec_path.parent)
        else:
            cover_source = output_dir / "assets" / variant_id / "source_frame.jpg"
            extract_video_frame(video, cover_source, float(variant.get("cover_at_seconds") or 3.0))
        if not cover_source.exists():
            raise ValueError(f"Cover source does not exist: {cover_source}")

        targets: list[dict[str, Any]] = []
        for channel in CHANNELS:
            packaging = mapping(mapping(variant.get("packaging")).get(channel))
            if not packaging:
                raise ValueError(f"Variant {variant_id} lacks packaging for {channel}.")
            rule = mapping(mapping(rules.get("channels")).get(channel))
            cover_rule = mapping(rule.get("cover"))
            cover_path = output_dir / "assets" / variant_id / channel / "cover.jpg"
            logical = mapping(mapping(registry.get("logical_accounts")).get(logical_account))
            render_cover(
                source=cover_source,
                output=cover_path,
                width=int(cover_rule.get("width") or 1080),
                height=int(cover_rule.get("height") or 1440),
                title=packaging.get("cover_title") or packaging.get("title"),
                kicker=str(packaging.get("cover_kicker") or spec.get("cover_kicker") or "三组反常识数字"),
                subtitle=str(packaging.get("cover_subtitle") or spec.get("cover_subtitle") or "TMT持仓、融资余额与海外去杠杆"),
                account_label=str(logical.get("label") or logical_account),
                accent=str(packaging.get("accent") or variant.get("accent") or "#ff6b6b"),
            )
            activity_selected = mapping(packaging.get("activity_selected"))
            platform_notes = {
                **mapping(packaging.get("platform_notes")),
                "activity_status": "selected_pending_confirmation" if activity_selected.get("id") else "live_discovery_required",
                "activity_candidates": packaging.get("activity_candidates") or [],
                "activity_selected": activity_selected or None,
                "activity_discovery": rule.get("activity_discovery"),
                "source_video_strategy": mapping(rule.get("video")).get("source_1x1_strategy"),
            }
            if channel == "wechat_channels_video":
                platform_notes.setdefault("short_title", packaging.get("short_title") or packaging.get("title"))
                platform_notes.setdefault("thumbnail_portrait", str(cover_path.resolve()))
            if channel == "douyin_video" and packaging.get("declaration"):
                platform_notes["declaration"] = str(packaging["declaration"])
            target = {
                "channel": channel,
                "account_slots": [logical_slot(registry, logical_account, channel)],
                "artifact_overrides": {"video": str(video.resolve())},
                "publish_metadata": {
                    "title": packaging.get("title"),
                    "summary": packaging.get("description"),
                    "description": packaging.get("description"),
                    "tags": string_list(packaging.get("tags")),
                    "cover": str(cover_path.resolve()),
                    "visibility": packaging.get("visibility") or "default",
                    "scheduled_at": packaging.get("scheduled_at"),
                    "platform_notes": platform_notes,
                },
            }
            targets.append(target)
            packaging_index.append(
                {
                    "variant_id": variant_id,
                    "logical_account": logical_account,
                    "channel": channel,
                    "account_slot": target["account_slots"][0],
                    "title": packaging.get("title"),
                    "description": packaging.get("description"),
                    "tags": string_list(packaging.get("tags")),
                    "cover": str(cover_path.resolve()),
                    "video": str(video.resolve()),
                    "activity_status": platform_notes["activity_status"],
                    "packaging_warnings": packaging_warnings(packaging, rule),
                }
            )
        items.append(
            {
                "topic_id": topic_id,
                "variant_id": variant_id,
                "artifact_overrides": {"video": str(video.resolve())},
                "publish_metadata": {"logical_account": logical_account},
                "targets": targets,
            }
        )
    return {
        "schema_version": "1.0",
        "run_id": spec.get("run_id"),
        "batch_id": spec.get("batch_id") or spec.get("run_id"),
        "status": "approved",
        "defaults": {"publish_metadata": {"campaign_id": spec.get("campaign_id") or spec.get("run_id")}},
        "items": items,
    }, packaging_index


def build_transwrite_manifest(spec: dict[str, Any], matrix: dict[str, Any], output_dir: Path) -> dict[str, Any]:
    first_video = str(matrix["items"][0]["artifact_overrides"]["video"])
    lane_manifest_path = output_dir / "source" / "talking_head_video_manifest.json"
    lane_manifest = {
        "schema_version": "1.0",
        "created_at": now_iso(),
        "lane": "talking_head_video",
        "status": "completed",
        "final_video": first_video,
        "campaign_variants": [item["variant_id"] for item in matrix["items"]],
    }
    write_json(lane_manifest_path, lane_manifest)
    return {
        "schema_version": "1.0",
        "run_id": spec.get("run_id"),
        "stage": "transwrite",
        "status": "prepared_for_skill_execution",
        "topics": [
            {
                "topic_id": spec.get("topic_id"),
                "title": spec.get("title"),
                "lanes": {
                    "talking_head_video": {
                        "status": "completed",
                        "manifest": str(lane_manifest_path.resolve()),
                        "final_video": first_video,
                    }
                },
            }
        ],
    }


def run_json_command(command: list[str], *, cwd: Path) -> dict[str, Any]:
    completed = subprocess.run(command, cwd=str(cwd), capture_output=True, text=True, check=False)
    if completed.returncode != 0:
        raise RuntimeError(f"Command failed ({completed.returncode}): {' '.join(command)}\n{completed.stderr.strip()}")
    try:
        return json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Command returned invalid JSON: {' '.join(command)}") from exc


def render_campaign_markdown(campaign: dict[str, Any]) -> str:
    lines = [
        f"# Publish Campaign｜{campaign['run_id']}",
        "",
        f"- 状态：`{campaign['status']}`",
        f"- 任务数：`{campaign['summary']['task_count']}`",
        f"- Dry Run 可用：`{campaign['summary']['dry_run_ready_count']}`",
        f"- Dry Run 阻断：`{campaign['summary']['dry_run_blocked_count']}`",
        f"- 账号登录状态：`{campaign['summary']['account_auth_status']}`",
        "- 最终发布：必须由当前会话显式确认",
        "",
        "## 账号与平台路由",
        "",
    ]
    for task in campaign.get("tasks") or []:
        lines.extend(
            [
                f"### {task.get('variant_id')}｜{task.get('channel')}｜{task.get('account_slot')}",
                "",
                f"- 标题：{task.get('title')}",
                f"- 封面：`{task.get('cover')}`",
                f"- 视频：`{task.get('video')}`",
                f"- 活动：`{task.get('activity_status')}`",
                f"- Dry Run：`{task.get('dry_run_status')}`",
                f"- 账号登录：`{task.get('account_auth_status') or 'not_checked'}`",
                f"- 登录命令：`{task.get('login_command') or 'none'}`",
                "",
            ]
        )
    lines.extend(
        [
            "## 活动规则",
            "",
            "活动名称必须来自发布当日的平台实时页面；只有主题高度相关且经编辑确认后，才写入 activity_selected。",
            "抖音可用 OpenCLI 读取当前活动；其他平台使用对应持久化浏览器 Profile 复核。",
        ]
    )
    return "\n".join(lines)


def account_auth_index(report: dict[str, Any] | None) -> dict[tuple[str, str], dict[str, Any]]:
    if not isinstance(report, dict):
        return {}
    return {
        (str(row.get("channel")), str(row.get("slot"))): row
        for row in report.get("accounts") or []
        if isinstance(row, dict)
    }


def primary_account_auth_status(
    index: dict[tuple[str, str], dict[str, Any]],
    *,
    channel: str,
    account_slot: str,
) -> str:
    row = index.get((channel, account_slot))
    if not row:
        return "not_checked"
    social_auth = next(
        (
            auth
            for auth in row.get("auth") or []
            if isinstance(auth, dict) and auth.get("mode") == "social_auto_upload"
        ),
        None,
    )
    if social_auth:
        return str(social_auth.get("status") or "attention_required")
    return str(row.get("status") or "attention_required")


def build_campaign(spec_path: Path, output_dir: Path) -> dict[str, Any]:
    spec = read_json(spec_path)
    registry = read_json(DEFAULT_ACCOUNT_REGISTRY)
    rules = read_json(DEFAULT_CONTENT_RULES)
    output_dir.mkdir(parents=True, exist_ok=True)

    matrix, packaging_index = build_matrix(
        spec,
        spec_path=spec_path,
        output_dir=output_dir,
        registry=registry,
        rules=rules,
    )
    matrix_path = output_dir / "publish_matrix.json"
    decision_path = output_dir / "publish_decision.json"
    transwrite_path = output_dir / "transwrite_manifest.json"
    publish_stage_dir = output_dir / "publish_stage"
    write_json(matrix_path, matrix)
    transwrite = build_transwrite_manifest(spec, matrix, output_dir)
    write_json(transwrite_path, transwrite)

    expanded = run_json_command(
        [sys.executable, str(ROOT / "scripts" / "expand_publish_matrix.py"), "--matrix", str(matrix_path), "--output", str(decision_path), "--fail-on-error"],
        cwd=ROOT,
    )
    stage = run_json_command(
        [
            sys.executable,
            str(ROOT / "scripts" / "build_stage5_publish.py"),
            "--transwrite-manifest",
            str(transwrite_path),
            "--publish-decision",
            str(decision_path),
            "--output-dir",
            str(publish_stage_dir),
        ],
        cwd=ROOT,
    )

    auth_report_path = output_dir / "account_auth_report.json"
    auth_report = read_json(auth_report_path) if auth_report_path.exists() else None
    auth_index = account_auth_index(auth_report)
    activity_reports: dict[str, dict[str, Any]] = {}
    for channel in CHANNELS:
        report_path = output_dir / "activity_discovery" / f"{channel}.json"
        if report_path.exists():
            activity_reports[channel] = {
                "path": str(report_path.resolve()),
                **mapping(read_json(report_path)),
            }
    packaging_lookup = {(row["variant_id"], row["channel"], row["account_slot"]): row for row in packaging_index}
    tasks: list[dict[str, Any]] = []
    for pack in stage.get("channel_packs") or []:
        pack_path = Path(str(pack["pack_manifest"]))
        dry_run_path = pack_path.parent / "social_auto_upload_dry_run.json"
        dry_run = run_json_command(
            [
                sys.executable,
                str(ROOT / "scripts" / "execute_social_auto_upload.py"),
                "--channel-pack",
                str(pack_path),
                "--output",
                str(dry_run_path),
            ],
            cwd=ROOT,
        )
        row = packaging_lookup.get((pack.get("variant_id"), pack.get("channel"), pack.get("account_slot")), {})
        auth_status = primary_account_auth_status(
            auth_index,
            channel=str(pack.get("channel") or ""),
            account_slot=str(pack.get("account_slot") or ""),
        )
        activity_report = activity_reports.get(str(pack.get("channel") or "")) or {}
        tasks.append(
            {
                **row,
                "task_id": pack.get("task_id"),
                "batch_id": pack.get("batch_id"),
                "channel_pack": str(pack_path.resolve()),
                "execution_request": pack.get("execution_request"),
                "platform_form_validation": pack.get("platform_form_validation"),
                "dry_run": str(dry_run_path.resolve()),
                "dry_run_status": dry_run.get("status"),
                "auth_check_command": dry_run.get("auth_check_command"),
                "login_command": dry_run.get("login_command"),
                "upload_command": dry_run.get("upload_command"),
                "account_auth_status": auth_status,
                "activity_status": activity_report.get("status") or row.get("activity_status"),
                "activity_discovery_report": activity_report.get("path"),
                "requires_user_confirmation": True,
            }
        )

    dry_run_ready_count = sum(1 for task in tasks if task.get("dry_run_status") == "ready_for_user_confirmation")
    dry_run_blocked_count = len(tasks) - dry_run_ready_count
    auth_statuses = [str(task.get("account_auth_status") or "not_checked") for task in tasks]
    if not auth_index:
        account_auth_status = "not_checked"
    elif auth_statuses and all(status == "valid" for status in auth_statuses):
        account_auth_status = "valid"
    elif any(status in {"login_required", "invalid"} for status in auth_statuses):
        account_auth_status = "login_required"
    else:
        account_auth_status = "attention_required"
    if not tasks:
        campaign_status = "blocked"
    elif dry_run_blocked_count:
        campaign_status = "blocked_by_publish_preflight"
    elif account_auth_status == "valid":
        campaign_status = "ready_for_final_confirmation"
    elif account_auth_status == "not_checked":
        campaign_status = "ready_for_account_auth_check"
    else:
        campaign_status = "ready_for_account_login"
    campaign = {
        "schema_version": "dasheng.publish.campaign.v1",
        "created_at": now_iso(),
        "run_id": spec.get("run_id"),
        "campaign_id": spec.get("campaign_id") or spec.get("run_id"),
        "topic_id": spec.get("topic_id"),
        "title": spec.get("title"),
        "status": campaign_status,
        "source_spec": str(spec_path.resolve()),
        "publish_matrix": str(matrix_path.resolve()),
        "publish_decision": str(decision_path.resolve()),
        "transwrite_manifest": str(transwrite_path.resolve()),
        "publish_manifest": stage.get("outputs", {}).get("publish_manifest") or str((publish_stage_dir / "publish_manifest.json").resolve()),
        "account_auth_report": str(auth_report_path.resolve()) if auth_report_path.exists() else None,
        "activity_discovery_reports": {
            channel: report.get("path")
            for channel, report in activity_reports.items()
        },
        "tasks": tasks,
        "summary": {
            "variant_count": len(spec.get("variants") or []),
            "task_count": len(tasks),
            "dry_run_ready_count": dry_run_ready_count,
            "dry_run_blocked_count": dry_run_blocked_count,
            "account_auth_status": account_auth_status,
            "account_auth_valid_count": sum(1 for status in auth_statuses if status == "valid"),
            "account_auth_attention_count": sum(1 for status in auth_statuses if status != "valid"),
            "tasks_by_channel": expanded.get("summary", {}).get("tasks_by_channel") or {},
        },
        "safety": {
            "dry_run_only": True,
            "will_not_publish": True,
            "cookie_contents_read": False,
            "cookie_contents_exported": False,
            "activities_require_live_discovery_and_confirmation": True,
            "final_publish_requires_current_session_confirmation": True,
        },
    }
    campaign_path = output_dir / "publish_campaign.json"
    campaign_md_path = output_dir / "PUBLISH_CAMPAIGN.md"
    write_json(campaign_path, campaign)
    write_text(campaign_md_path, render_campaign_markdown(campaign))
    campaign["outputs"] = {
        "campaign_json": str(campaign_path.resolve()),
        "campaign_markdown": str(campaign_md_path.resolve()),
        "publish_stage": str(publish_stage_dir.resolve()),
    }
    return campaign


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a two-account, multi-platform Publish campaign without publishing.")
    parser.add_argument("--spec", required=True, help="Campaign specification JSON.")
    parser.add_argument("--output-dir", required=True, help="Runtime Publish campaign output directory.")
    args = parser.parse_args()
    campaign = build_campaign(Path(args.spec).expanduser().resolve(), Path(args.output_dir).expanduser().resolve())
    print(json.dumps(campaign, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
