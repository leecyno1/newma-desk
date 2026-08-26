#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from canonical_workflow import (
    WorkflowContractError,
    canonical_stage_dir,
    ensure_publish_decision_gate,
    ensure_stage_manifest,
)


ROOT = Path(__file__).resolve().parents[1]
FINANCE_PROJECT = Path(os.getenv("DASHENG_FINANCE_MOTION_ROOT", str(ROOT.parent / "finance-motion-8787")))
FINANCE_SCENES = FINANCE_PROJECT / "dashboard/scenes.json"
FINANCE_EXPORT_SCRIPT = FINANCE_PROJECT / "dashboard/scripts/export-scene-videos.mjs"
EXPORT_TIMEOUT_SECONDS = int(os.getenv("DASHENG_PUBLISH_EXPORT_TIMEOUT_SECONDS", "120"))

OPENCLAW_INSTALLER_ROOT = Path(os.getenv("DASHENG_OPENCLAW_INSTALLER_ROOT", str(ROOT.parent / "OpenClawInstaller")))


def _skill(skill_name: str) -> str:
    """解析OpenClaw skill路径，支持环境变量覆盖"""
    return str(OPENCLAW_INSTALLER_ROOT / f"skills/default/{skill_name}/SKILL.md")


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def compact_count(text: str) -> int:
    return len(re.sub(r"\s+", "", text))


def parse_float(text: str) -> float | None:
    if text is None:
        return None
    value = str(text).strip().replace(",", "")
    if not value:
        return None
    if value.endswith("%"):
        value = value[:-1]
    try:
        return float(value)
    except ValueError:
        return None


def human_label(stem: str) -> str:
    label = stem
    label = re.sub(r"^chart-\d+_?", "", label)
    label = label.replace("_", " ").replace("-", " ").strip()
    return label or stem


def is_date_like(values: list[str]) -> bool:
    if not values:
        return False
    pattern = re.compile(r"^\d{2,4}[-/]\d{1,2}([-/]\d{1,2})?$")
    hit = sum(1 for value in values if pattern.match(value.strip()))
    return hit / max(len(values), 1) >= 0.4


@dataclass
class Prototypes:
    line_rise: dict[str, Any]
    multi_line: dict[str, Any]
    bar_grow: dict[str, Any]
    timeline: dict[str, Any]
    ticker: dict[str, Any]
    gauge: dict[str, Any]
    donut: dict[str, Any]
    base_meta: dict[str, Any]
    base_global: dict[str, Any]


@dataclass
class RewriteTopicSource:
    topic_id: str
    topic_name: str
    topic_prefix: str
    rewrite_source: Path


PublishTopicSource = RewriteTopicSource


CHANNEL_ALIASES = {
    "wechat": "wechat_article",
    "wechat_article": "wechat_article",
    "wechat_mp": "wechat_article",
    "public_wechat": "wechat_article",
    "wechat_official_account": "wechat_article",
    "wechat_video": "wechat_channels_video",
    "wechat_channels_video": "wechat_channels_video",
    "video_channel": "wechat_channels_video",
    "shipinhao": "wechat_channels_video",
    "xhs": "xiaohongshu_video",
    "xiaohongshu": "xiaohongshu_video",
    "xiaohongshu_video": "xiaohongshu_video",
    "xhs_video": "xiaohongshu_video",
    "xiaohongshu_image": "xiaohongshu_image",
    "xhs_image": "xiaohongshu_image",
    "douyin": "douyin_video",
    "douyin_video": "douyin_video",
    "weibo": "weibo_post",
    "weibo_post": "weibo_post",
    "weibo_article": "weibo_article",
    "x": "x_post",
    "twitter": "x_post",
    "x_post": "x_post",
    "x_article": "x_article",
    "bilibili": "bilibili_video",
    "bilibili_video": "bilibili_video",
    "zhihu": "zhihu_post",
    "zhihu_post": "zhihu_post",
    "zhihu_article": "zhihu_post",
}

PUBLISH_SKILL_STACK = {
    "video_supplement": [
        {"skill": "dasheng-stage-publish-video", "role": "chart_and_narrative_video", "source": "repo-local"},
        {"skill": "remotion", "role": "motion_best_practice", "source": "openclaw-default"},
        {"skill": "remotion-video", "role": "motion_workflow", "source": "openclaw-default"},
        {"skill": "remotion-video-toolkit", "role": "motion_toolkit", "source": "openclaw-default"},
    ],
    "wechat": [
        {"skill": "baoyu-post-to-wechat", "role": "primary_executor", "source": "openclaw-default"},
        {"skill": "wechat-multi-publisher", "role": "batch_draft_executor", "source": "openclaw-default"},
        {"skill": "md2wechat", "role": "html_preprocessor", "source": "codex-local"},
        {"skill": "wechat-public-cli", "role": "cli_executor_fallback", "source": "openclaw-default"},
    ],
    "weibo": [
        {"skill": "weibo-manager", "role": "approval_flow_executor", "source": "openclaw-default"},
        {"skill": "baoyu-post-to-weibo", "role": "article_executor", "source": "openclaw-default"},
    ],
    "x": [
        {"skill": "baoyu-post-to-x", "role": "x_executor", "source": "openclaw-default"},
    ],
    "xiaohongshu": [
        {"skill": "xiaohongshu-auto", "role": "publish_executor", "source": "openclaw-default"},
        {"skill": "xiaohongshu-ops", "role": "ops_helper", "source": "openclaw-default"},
    ],
    "douyin": [
        {"skill": "douyin-upload-skill", "role": "publish_executor", "source": "openclaw-default"},
    ],
    "zhihu": [
        {"skill": "zhihu-post", "role": "publish_executor", "source": "openclaw-default"},
    ],
    "manual_support": [
        {"skill": "bilibili-youtube-watcher", "role": "bilibili_manual_research", "source": "openclaw-default"},
        {"skill": "publish-guard", "role": "post_publish_verifier", "source": "openclaw-default"},
    ],
}

CHANNEL_EXECUTION_RULES = {
    "wechat_article": {
        "executor_skill": "baoyu-post-to-wechat",
        "source_skill_path": None,
        "automation_level": "semi_automated",
        "mode": "draft_or_browser_confirm",
        "requires_video": False,
        "helper_skills": ["wechat-multi-publisher", "md2wechat", "wechat-public-cli", "publish-guard"],
    },
    "wechat_channels_video": {
        "executor_skill": "social-auto-upload-bridge",
        "source_skill_path": None,
        "supporting_skill": "publish-guard",
        "automation_level": "guarded_external_cli",
        "mode": "dry_run_then_confirm_execute",
        "requires_video": True,
        "helper_skills": ["publish-guard"],
    },
    "xiaohongshu_video": {
        "executor_skill": "xiaohongshu-auto",
        "source_skill_path": str(OPENCLAW_INSTALLER_ROOT / "skills/default/xiaohongshu-auto/SKILL.md"),
        "automation_level": "automated",
        "mode": "auto_publish",
        "requires_video": True,
        "helper_skills": ["xiaohongshu-ops", "publish-guard"],
    },
    "xiaohongshu_image": {
        "executor_skill": "xiaohongshu-auto",
        "source_skill_path": str(OPENCLAW_INSTALLER_ROOT / "skills/default/xiaohongshu-auto/SKILL.md"),
        "automation_level": "automated",
        "mode": "auto_publish",
        "requires_video": False,
        "helper_skills": ["xiaohongshu-ops", "publish-guard"],
    },
    "douyin_video": {
        "executor_skill": "douyin-upload-skill",
        "source_skill_path": str(OPENCLAW_INSTALLER_ROOT / "skills/default/douyin-upload-skill/SKILL.md"),
        "automation_level": "automated",
        "mode": "official_api_or_fallback",
        "requires_video": True,
        "helper_skills": ["publish-guard"],
    },
    "weibo_post": {
        "executor_skill": "weibo-manager",
        "source_skill_path": None,
        "automation_level": "approval_required",
        "mode": "request_approve_execute",
        "requires_video": False,
        "helper_skills": ["publish-guard"],
    },
    "weibo_article": {
        "executor_skill": "baoyu-post-to-weibo",
        "source_skill_path": None,
        "automation_level": "semi_automated",
        "mode": "browser_confirm",
        "requires_video": False,
        "helper_skills": ["publish-guard"],
    },
    "x_post": {
        "executor_skill": "baoyu-post-to-x",
        "source_skill_path": None,
        "automation_level": "semi_automated",
        "mode": "browser_confirm",
        "requires_video": False,
        "helper_skills": ["publish-guard"],
    },
    "x_article": {
        "executor_skill": "baoyu-post-to-x",
        "source_skill_path": None,
        "automation_level": "semi_automated",
        "mode": "browser_confirm",
        "requires_video": False,
        "helper_skills": ["publish-guard"],
    },
    "bilibili_video": {
        "executor_skill": None,
        "source_skill_path": None,
        "supporting_skill": "bilibili-youtube-watcher",
        "supporting_skill_path": str(OPENCLAW_INSTALLER_ROOT / "skills/default/bilibili-youtube-watcher/SKILL.md"),
        "automation_level": "manual_only",
        "mode": "export_only",
        "requires_video": True,
        "helper_skills": ["bilibili-youtube-watcher", "publish-guard"],
    },
    "zhihu_post": {
        "executor_skill": "zhihu-post",
        "source_skill_path": str(OPENCLAW_INSTALLER_ROOT / "skills/default/zhihu-post/SKILL.md"),
        "automation_level": "semi_automated",
        "mode": "browser_confirm",
        "requires_video": False,
        "helper_skills": ["publish-guard"],
    },
}

CHANNEL_VARIANT_PREFERENCES = {
    "wechat_article": ["draft_publish", "wechat_luxun_hot", "wechat_lemon_normal"],
    "wechat_channels_video": ["xhs_video_luxun_hot", "xhs_video_lemon_normal"],
    "xiaohongshu_video": ["xhs_video_luxun_hot", "xhs_video_lemon_normal"],
    "xiaohongshu_image": ["draft_publish", "xhs_video_luxun_hot", "xhs_video_lemon_normal", "wechat_luxun_hot"],
    "douyin_video": ["xhs_video_luxun_hot", "xhs_video_lemon_normal"],
    "weibo_post": ["draft_publish", "wechat_luxun_hot", "wechat_lemon_normal", "xhs_video_luxun_hot"],
    "weibo_article": ["draft_publish", "wechat_luxun_hot", "wechat_lemon_normal"],
    "x_post": ["draft_publish", "wechat_luxun_hot", "wechat_lemon_normal", "xhs_video_luxun_hot"],
    "x_article": ["draft_publish", "wechat_luxun_hot", "wechat_lemon_normal"],
    "bilibili_video": ["xhs_video_luxun_hot", "xhs_video_lemon_normal"],
    "zhihu_post": ["draft_publish", "wechat_luxun_hot", "wechat_lemon_normal"],
}

DEFAULT_TEXT_CHANNELS = ["wechat_article", "weibo_post", "x_post"]
DEFAULT_VIDEO_CHANNELS = ["xiaohongshu_video", "douyin_video", "bilibili_video"]


def load_prototypes() -> Prototypes:
    deck = read_json(FINANCE_SCENES)
    scenes = deck.get("scenes", [])

    def first(template: str) -> dict[str, Any]:
        scene = next((item for item in scenes if item.get("template") == template), None)
        if not scene:
            raise RuntimeError(f"missing template prototype: {template}")
        return scene

    return Prototypes(
        line_rise=first("lineRise"),
        multi_line=first("multiLine"),
        bar_grow=first("barGrow"),
        timeline=first("timeline"),
        ticker=first("ticker"),
        gauge=first("gauge"),
        donut=first("donutKpi"),
        base_meta=deck.get("meta", {}),
        base_global=deck.get("global", {}),
    )


def has_preferred_variant(topic: dict[str, Any], channels: list[str]) -> bool:
    variants = topic.get("variants") or []
    variant_keys = {
        str(item.get("variant") or "").strip().lower()
        for item in variants
        if isinstance(item, dict) and str(item.get("variant") or "").strip()
    }
    for channel in channels:
        for wanted in CHANNEL_VARIANT_PREFERENCES.get(channel, []):
            if wanted in variant_keys:
                return True
    return False


def derive_default_channels(rewrite_topic: dict[str, Any]) -> list[str]:
    channels = list(DEFAULT_TEXT_CHANNELS)
    if has_preferred_variant(rewrite_topic, DEFAULT_VIDEO_CHANNELS):
        channels.extend(DEFAULT_VIDEO_CHANNELS)
    return channels


def build_draft_publish_manifest(draft_manifest: dict[str, Any], draft_manifest_path: Path) -> tuple[dict[str, Any], Path]:
    topics: list[dict[str, Any]] = []
    for index, draft in enumerate(draft_manifest.get("drafts") or [], start=1):
        if not isinstance(draft, dict):
            continue
        draft_file = Path(str(draft.get("draft_file") or "")).expanduser().resolve()
        if not draft_file.exists():
            continue
        topic_id = str(draft.get("topic_id") or f"topic-{index}").strip()
        title = str(draft.get("title") or topic_id).strip()
        topics.append(
            {
                "topic_id": topic_id,
                "title": title,
                "topic_name": title,
                "topic_prefix": normalize_topic_prefix(topic_id),
                "rewrite_source": str(draft_file),
                "variants": [
                    {
                        "variant": "draft_publish",
                        "file": str(draft_file),
                        "channel_family": "text",
                    }
                ],
            }
        )
    return (
        {
            "run_id": draft_manifest["run_id"],
            "stage": "draft_publish",
            "status": "ready",
            "output_root": str(draft_manifest_path.parent),
            "source_draft_manifest": str(draft_manifest_path),
            "topics": topics,
        },
        draft_manifest_path.parent,
    )


def derive_title_candidates(topic_name: str) -> list[str]:
    clean = str(topic_name or "").strip()
    return [clean] if clean else []


def derive_publish_time(index: int) -> str:
    slots = [(9, 30), (12, 30), (18, 30), (21, 0)]
    hour, minute = slots[index % len(slots)]
    now = datetime.now()
    scheduled = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if scheduled <= now:
        scheduled = scheduled + timedelta(days=1)
    return scheduled.astimezone().isoformat(timespec="seconds")


def autofill_publish_decision(
    *,
    publish_decision: dict[str, Any],
    rewrite_manifest: dict[str, Any],
) -> tuple[dict[str, Any], bool]:
    changed = False
    instructions = list(publish_decision.get("instructions") or [])
    rewrite_topics = [
        item for item in (rewrite_manifest.get("topics") or [])
        if isinstance(item, dict) and str(item.get("topic_id") or "").strip()
    ]
    existing_topics = {
        str(item.get("topic_id") or "").strip(): item
        for item in (publish_decision.get("topics") or [])
        if isinstance(item, dict) and str(item.get("topic_id") or "").strip()
    }

    normalized_topics: list[dict[str, Any]] = []
    for index, rewrite_topic in enumerate(rewrite_topics):
        topic_id = str(rewrite_topic.get("topic_id") or "").strip()
        topic_name = str(rewrite_topic.get("title") or rewrite_topic.get("topic_name") or topic_id).strip()
        row = dict(existing_topics.get(topic_id) or {})
        if not row:
            changed = True
            row["topic_id"] = topic_id
        if not str(row.get("topic_name") or "").strip():
            row["topic_name"] = topic_name
            changed = True
        default_channels = derive_default_channels(rewrite_topic)
        channels = [normalize_channel_name(item) for item in (row.get("channels") or []) if str(item or "").strip()]
        editor_status = str(row.get("editor_status") or "").strip()
        should_extend_defaults = bool(channels) and editor_status in {"auto_filled_default", "auto_filled_publish_defaults"}
        if not channels:
            row["channels"] = default_channels
            changed = True
        elif should_extend_defaults:
            merged = []
            for item in channels + [channel for channel in default_channels if channel not in channels]:
                if item not in merged:
                    merged.append(item)
            if merged != channels:
                row["channels"] = merged
                changed = True
        if not (row.get("title_candidates") or []):
            row["title_candidates"] = derive_title_candidates(topic_name)
            changed = True
        if not str(row.get("publish_time") or "").strip():
            row["publish_time"] = derive_publish_time(index)
            changed = True
        if not str(row.get("editor_status") or "").strip():
            row["editor_status"] = "auto_filled_publish_defaults"
            changed = True
        normalized_topics.append(row)

    if normalized_topics != (publish_decision.get("topics") or []):
        publish_decision["topics"] = normalized_topics
        changed = True

    auto_note = "已自动补齐默认发布矩阵：公众号 / 微博 / X / 小红书视频 / 抖音视频 / B站人工投稿包；人工仍可继续微调。"
    if auto_note not in instructions:
        instructions.append(auto_note)
        publish_decision["instructions"] = instructions
        changed = True
    if publish_decision.get("status") != "ready":
        publish_decision["status"] = "ready"
        changed = True
    if publish_decision.get("gate") != "Channel Gate":
        publish_decision["gate"] = "Channel Gate"
        changed = True
    return publish_decision, changed


def clone_scene(prototype: dict[str, Any], scene_id: str, label: str, tag: str, data: dict[str, Any], duration_ms: int) -> dict[str, Any]:
    scene = json.loads(json.dumps(prototype))
    scene["id"] = scene_id
    scene["label"] = label
    scene["tag"] = tag
    scene["durationMs"] = duration_ms
    scene["data"] = data
    animation = scene.get("animation") or {}
    animation["durationMs"] = duration_ms
    scene["animation"] = animation
    return scene


def detect_chart_scene(csv_path: Path, prototypes: Prototypes, scene_prefix: str, index: int) -> dict[str, Any] | None:
    with csv_path.open("r", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        fields = reader.fieldnames or []
        if len(fields) < 2:
            return None
        rows = list(reader)
    if not rows:
        return None

    x_field = fields[0]
    labels = [str(row.get(x_field, "")).strip() for row in rows if str(row.get(x_field, "")).strip()]
    labels = labels[-12:]
    if not labels:
        return None

    numeric_fields: list[str] = []
    for field in fields[1:]:
        values = [parse_float(row.get(field, "")) for row in rows]
        if sum(1 for value in values if value is not None) >= max(3, len(values) // 2):
            numeric_fields.append(field)

    if not numeric_fields:
        # fallback: categorical-only flow CSV (e.g. node lists)
        category_field = fields[1] if len(fields) > 1 else x_field
        category_values = [str(row.get(category_field, "")).strip() for row in rows if str(row.get(category_field, "")).strip()]
        category_values = category_values[:10]
        if len(category_values) >= 2:
            values = [index + 1 for index in range(len(category_values))]
            scene_id = f"{scene_prefix}-chart-{index:02d}"
            data = {"bars": values, "labels": category_values}
            return clone_scene(
                prototypes.bar_grow,
                scene_id=scene_id,
                label=f"图表：{human_label(csv_path.stem)}",
                tag="interactive-chart",
                data=data,
                duration_ms=6800,
            )
        return None

    file_label = human_label(csv_path.stem)
    scene_id = f"{scene_prefix}-chart-{index:02d}"
    scene_tag = "interactive-chart"
    duration_ms = 6800

    # Multi-line scene
    if len(numeric_fields) >= 2:
        picked = numeric_fields[:3]
        line_payload = []
        aligned_labels = []
        for row in rows[-12:]:
            label = str(row.get(x_field, "")).strip()
            if not label:
                continue
            aligned_labels.append(label)
        for field in picked:
            values = []
            for row in rows[-12:]:
                value = parse_float(row.get(field, ""))
                values.append(value if value is not None else 0.0)
            line_payload.append({"name": field, "values": values})
        data = {"lines": line_payload, "xLabels": aligned_labels}
        return clone_scene(
            prototypes.multi_line,
            scene_id=scene_id,
            label=f"图表：{file_label}",
            tag=scene_tag,
            data=data,
            duration_ms=duration_ms,
        )

    # Single series scene
    field = numeric_fields[0]
    values = []
    aligned_labels = []
    for row in rows[-12:]:
        label = str(row.get(x_field, "")).strip()
        value = parse_float(row.get(field, ""))
        if not label or value is None:
            continue
        aligned_labels.append(label)
        values.append(value)
    if len(values) < 2:
        return None
    if len(values) == 2:
        values = values + [values[-1]]
        aligned_labels = aligned_labels + [aligned_labels[-1]]

    if is_date_like(aligned_labels):
        data = {"series": values, "xLabels": aligned_labels}
        return clone_scene(
            prototypes.line_rise,
            scene_id=scene_id,
            label=f"图表：{file_label}",
            tag=scene_tag,
            data=data,
            duration_ms=duration_ms,
        )

    data = {"bars": values, "labels": aligned_labels}
    return clone_scene(
        prototypes.bar_grow,
        scene_id=scene_id,
        label=f"图表：{file_label}",
        tag=scene_tag,
        data=data,
        duration_ms=duration_ms,
    )


def split_sentences(text: str) -> list[str]:
    normalized = re.sub(r"\n+", "\n", text)
    raw = re.split(r"[。！？!?]\s*|\n", normalized)
    return [item.strip() for item in raw if len(item.strip()) >= 12]


def extract_key_numbers(text: str) -> list[str]:
    matches = re.findall(r"\d+(?:\.\d+)?%?", text)
    numbers = []
    for item in matches:
        if item not in numbers:
            numbers.append(item)
        if len(numbers) >= 8:
            break
    return numbers


def build_narrative_scenes(rewrite_file: Path, prototypes: Prototypes, scene_prefix: str) -> list[dict[str, Any]]:
    text = rewrite_file.read_text(encoding="utf-8")
    headings = re.findall(r"^##\s+(.+)$", text, flags=re.MULTILINE)
    sentences = split_sentences(text)
    numbers = extract_key_numbers(text)

    timeline_events = []
    for index, heading in enumerate(headings[:6], start=1):
        timeline_events.append({"time": f"段落{index}", "title": heading[:28]})
    if not timeline_events:
        for index, sentence in enumerate(sentences[:5], start=1):
            timeline_events.append({"time": f"段落{index}", "title": sentence[:28]})

    ticker_items = []
    for number in numbers[:5]:
        context = next((sentence for sentence in sentences if number in sentence), f"关键数据 {number}")
        ticker_items.append({"title": context[:42], "score": min(95, 58 + len(ticker_items) * 6)})
    if len(ticker_items) < 5:
        for sentence in sentences[: 5 - len(ticker_items)]:
            ticker_items.append({"title": sentence[:42], "score": min(95, 58 + len(ticker_items) * 6)})

    risk_score = min(95, max(55, 58 + len(numbers) * 4))
    execution_score = min(95, max(60, 64 + len(headings) * 3))

    scenes = [
        clone_scene(
            prototypes.timeline,
            scene_id=f"{scene_prefix}-narrative-01",
            label="框架精华：结构时间线",
            tag="motion-summary",
            data={"events": timeline_events[:5]},
            duration_ms=7600,
        ),
        clone_scene(
            prototypes.ticker,
            scene_id=f"{scene_prefix}-narrative-02",
            label="关键数据：滚动条",
            tag="motion-summary",
            data={"items": ticker_items[:5]},
            duration_ms=7200,
        ),
        clone_scene(
            prototypes.gauge,
            scene_id=f"{scene_prefix}-narrative-03",
            label="风险强度评估",
            tag="motion-summary",
            data={"score": risk_score, "label": "Narrative Risk"},
            duration_ms=6200,
        ),
        clone_scene(
            prototypes.donut,
            scene_id=f"{scene_prefix}-narrative-04",
            label="执行优先级",
            tag="motion-summary",
            data={"value": execution_score, "target": 85, "label": "Action Priority"},
            duration_ms=6200,
        ),
    ]
    return scenes


def build_deck(meta_title: str, meta_desc: str, prototypes: Prototypes, scenes: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "meta": {
            "title": meta_title,
            "description": meta_desc,
            "version": datetime.now().strftime("%Y.%m.%d"),
        },
        "global": {
            **prototypes.base_global,
            "autoplay": True,
            "autoplayGapMs": 800,
        },
        "scenes": scenes,
    }


def run_export(deck_path: Path, out_dir: Path) -> dict[str, Any]:
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    try:
        payload = read_json(deck_path)
    except Exception:
        payload = {}
    if not (payload.get("scenes") or []):
        return {
            "ok": True,
            "skipped": True,
            "reason": "no_scenes",
            "command": None,
            "stdout": "",
            "stderr": "",
            "returncode": 0,
            "timed_out": False,
        }
    command = [
        "node",
        str(FINANCE_EXPORT_SCRIPT),
        "--scenes",
        str(deck_path),
        "--out",
        str(out_dir),
    ]
    try:
        process = subprocess.run(
            command,
            cwd=str(FINANCE_PROJECT),
            capture_output=True,
            text=True,
            timeout=EXPORT_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired as exc:
        return {
            "ok": False,
            "command": " ".join(command),
            "stdout": (exc.stdout or "")[-4000:],
            "stderr": ((exc.stderr or "") + f"\nTIMEOUT after {EXPORT_TIMEOUT_SECONDS}s")[-4000:],
            "returncode": None,
            "timed_out": True,
        }
    return {
        "ok": process.returncode == 0,
        "command": " ".join(command),
        "stdout": process.stdout[-4000:],
        "stderr": process.stderr[-4000:],
        "returncode": process.returncode,
        "timed_out": False,
    }


PREFERRED_VARIANT_ORDER = [
    "xhs_video_luxun_hot",
    "xiaohongshu_hot",
    "xhs_video_lemon_normal",
    "xiaohongshu_normal",
    "wechat_luxun_hot",
    "wechat_hot",
    "wechat_lemon_normal",
    "wechat_normal",
]


def normalize_topic_prefix(value: str) -> str:
    text = re.sub(r"[^0-9A-Za-z\u4e00-\u9fa5]+", "_", str(value or "").strip()).strip("_")
    return text or "topic"


def pick_rewrite_source_from_candidates(candidates: list[tuple[str, Path]] | list[Path]) -> Path:
    normalized: list[tuple[str, Path]] = []
    for item in candidates:
        if isinstance(item, tuple):
            variant_key, file_path = item
        else:
            variant_key, file_path = "", item
        normalized.append((str(variant_key or "").strip().lower(), Path(file_path).expanduser().resolve()))
    normalized = [(variant_key, file_path) for variant_key, file_path in normalized if file_path.exists()]
    if not normalized:
        raise RuntimeError("no rewrite markdown candidates found")

    def rank(variant_key: str, file_path: Path) -> tuple[int, str]:
        lower_name = file_path.name.lower()
        for index, preferred in enumerate(PREFERRED_VARIANT_ORDER):
            if variant_key == preferred or preferred in lower_name:
                return (index, lower_name)
        return (len(PREFERRED_VARIANT_ORDER), lower_name)

    return sorted(normalized, key=lambda item: rank(item[0], item[1]))[0][1]


def pick_rewrite_source(topic_dir: Path) -> Path:
    candidates = [(path.name.lower(), path) for path in sorted(topic_dir.glob("*.md"))]
    if not candidates:
        raise RuntimeError(f"no rewrite markdown found in {topic_dir}")
    return pick_rewrite_source_from_candidates(candidates)


def extract_rewrite_topic_sources(rewrite_manifest: dict[str, Any], rewrite_root: Path) -> list[RewriteTopicSource]:
    topics = rewrite_manifest.get("topics")
    if isinstance(topics, list) and topics:
        collected: list[RewriteTopicSource] = []
        for index, topic in enumerate(topics, start=1):
            if not isinstance(topic, dict):
                continue
            topic_id = str(topic.get("topic_id") or topic.get("topic_prefix") or topic.get("topic") or f"topic-{index}").strip()
            topic_name = str(topic.get("title") or topic.get("topic_name") or topic.get("topic") or topic_id).strip()
            topic_prefix = normalize_topic_prefix(topic.get("topic_prefix") or topic_id)
            variants = topic.get("variants") or []
            candidate_files: list[tuple[str, Path]] = []
            if isinstance(variants, dict):
                for variant_name, payload in variants.items():
                    if not isinstance(payload, dict):
                        continue
                    file_value = payload.get("file")
                    if file_value:
                        candidate_files.append((str(variant_name), Path(str(file_value))))
            elif isinstance(variants, list):
                for payload in variants:
                    if not isinstance(payload, dict):
                        continue
                    file_value = payload.get("file")
                    if file_value:
                        candidate_files.append((str(payload.get("variant") or ""), Path(str(file_value))))
            if not candidate_files and topic.get("rewrite_source"):
                candidate_files.append(("", Path(str(topic["rewrite_source"]))))
            if not candidate_files:
                continue
            rewrite_source = pick_rewrite_source_from_candidates(candidate_files)
            collected.append(
                RewriteTopicSource(
                    topic_id=topic_id,
                    topic_name=topic_name,
                    topic_prefix=topic_prefix,
                    rewrite_source=rewrite_source,
                )
            )
        if collected:
            return collected

    topic_dirs = sorted([item for item in rewrite_root.iterdir() if item.is_dir() and item.name.startswith("topic")])
    return [
        RewriteTopicSource(
            topic_id=topic_dir.name,
            topic_name=topic_dir.name,
            topic_prefix=normalize_topic_prefix(topic_dir.name.split("_")[0]),
            rewrite_source=pick_rewrite_source(topic_dir),
        )
        for topic_dir in topic_dirs
    ]


def extract_publish_topic_sources(source_manifest: dict[str, Any], source_root: Path) -> list[PublishTopicSource]:
    return extract_rewrite_topic_sources(source_manifest, source_root)


def build_minimal_topic_manifest(rewrite_topic: RewriteTopicSource, output_root: Path) -> dict[str, Any]:
    topic_out = output_root / normalize_topic_prefix(rewrite_topic.topic_prefix)
    topic_out.mkdir(parents=True, exist_ok=True)
    topic_manifest_path = topic_out / "topic_video_manifest.json"
    topic_manifest = {
        "topic_id": rewrite_topic.topic_id,
        "topic": rewrite_topic.topic_name,
        "topic_prefix": rewrite_topic.topic_prefix,
        "rewrite_source": str(rewrite_topic.rewrite_source),
        "chart_csvs": [],
        "decks": {},
        "exports": {
            "interactive_charts": {"ok": False, "skipped": True, "reason": "charts are generated in draft html"},
            "motion_narrative": {"ok": False, "skipped": True, "reason": "video supplement is optional"},
        },
        "topic_video_manifest": str(topic_manifest_path),
    }
    write_json(topic_manifest_path, topic_manifest)
    return topic_manifest


def _video_dir_line(topic_manifest: dict[str, Any], deck_key: str, video_subdir: str) -> str:
    deck_path = (topic_manifest.get("decks") or {}).get(deck_key)
    if not deck_path:
        return "按需补充"
    return str(Path(deck_path).parent.parent / video_subdir)


def build_report(run_manifest: dict[str, Any], report_path: Path) -> None:
    lines = [
        "# 发布环节视频补充报告",
        "",
        f"- 生成时间：`{run_manifest['generated_at']}`",
        f"- 正文源目录：`{run_manifest['source_root']}`",
        "- 图表与配图：Draft HTML 内生成，Publish 不再读取独立素材包",
        f"- 动态图表工程：`{run_manifest['finance_project']}`",
        f"- 线程对接：`{run_manifest['integration_thread']}`",
        "",
    ]
    for item in run_manifest["topics"]:
        lines.extend(
            [
                f"## {item['topic']}",
                f"- 正文源：`{item['rewrite_source']}`",
                f"- 图表 CSV 数：`{len(item['chart_csvs'])}`",
                f"- 互动图表导出状态：`{item['exports']['interactive_charts']['ok']}`",
                f"- Motion 动画导出状态：`{item['exports']['motion_narrative']['ok']}`",
                f"- 互动图表目录：`{_video_dir_line(item, 'interactive_charts_deck', 'videos/interactive_charts')}`",
                f"- Motion 动画目录：`{_video_dir_line(item, 'motion_narrative_deck', 'videos/motion_narrative')}`",
                "",
            ]
        )
    write_text(report_path, "\n".join(lines).strip() + "\n")


def load_existing_topic_manifests(output_root: Path) -> list[dict[str, Any]]:
    manifests: list[dict[str, Any]] = []
    for path in sorted(output_root.glob("*/topic_video_manifest.json")):
        try:
            payload = read_json(path)
        except Exception:
            continue
        if isinstance(payload, dict) and payload.get("topic_id"):
            payload.setdefault("topic_video_manifest", str(path))
            manifests.append(payload)
    return manifests


def normalize_channel_name(channel: str) -> str:
    key = str(channel or "").strip().lower()
    return CHANNEL_ALIASES.get(key, key or "unknown")


def collect_video_exports(topic_video_manifest_path: Path) -> dict[str, list[str]]:
    topic_dir = topic_video_manifest_path.parent
    interactive = sorted(str(path) for path in (topic_dir / "videos" / "interactive_charts").glob("*") if path.is_file())
    narrative = sorted(str(path) for path in (topic_dir / "videos" / "motion_narrative").glob("*") if path.is_file())
    return {
        "interactive_charts": interactive,
        "motion_narrative": narrative,
        "all_video_files": interactive + narrative,
    }


def pick_variant_for_channel(topic: dict[str, Any], normalized_channel: str) -> dict[str, Any] | None:
    variants = topic.get("variants") or []
    if not isinstance(variants, list):
        return None
    preferred = CHANNEL_VARIANT_PREFERENCES.get(normalized_channel) or []
    lowered = []
    for variant in variants:
        if not isinstance(variant, dict):
            continue
        variant_key = str(variant.get("variant") or "").strip().lower()
        lowered.append((variant_key, variant))
    for wanted in preferred:
        for variant_key, variant in lowered:
            if variant_key == wanted:
                return variant
    return lowered[0][1] if lowered else None


def build_channel_adaptation_manifest(
    *,
    run_id: str,
    rewrite_manifest: dict[str, Any],
    publish_decision: dict[str, Any],
    topic_manifests: list[dict[str, Any]],
) -> dict[str, Any]:
    rewrite_topics = {
        str(item.get("topic_id") or "").strip(): item
        for item in (rewrite_manifest.get("topics") or [])
        if isinstance(item, dict) and str(item.get("topic_id") or "").strip()
    }
    video_topics = {str(item.get("topic_id") or "").strip(): item for item in topic_manifests}
    packs: list[dict[str, Any]] = []
    blockers: list[str] = []

    for topic_decision in publish_decision.get("topics", []):
        if not isinstance(topic_decision, dict):
            continue
        topic_id = str(topic_decision.get("topic_id") or "").strip()
        if not topic_id:
            continue
        rewrite_topic = rewrite_topics.get(topic_id, {})
        video_topic = video_topics.get(topic_id, {})
        channels = topic_decision.get("channels") or []
        normalized_channels = [normalize_channel_name(item) for item in channels if str(item or "").strip()]
        if not normalized_channels:
            blockers.append(f"{topic_id}: 未配置 channels")

        video_exports = collect_video_exports(Path(video_topic["topic_video_manifest"])) if video_topic.get("topic_video_manifest") else {
            "interactive_charts": [],
            "motion_narrative": [],
            "all_video_files": [],
        }
        channel_packs = []
        for raw_channel, normalized_channel in zip(channels, normalized_channels):
            execution_rule = CHANNEL_EXECUTION_RULES.get(normalized_channel, {
                "executor_skill": None,
                "automation_level": "manual_only",
                "mode": "export_only",
                "requires_video": False,
            })
            variant = pick_variant_for_channel(rewrite_topic, normalized_channel)
            variant_file = str(variant.get("file")) if variant else None
            variant_name = str(variant.get("variant")) if variant else None
            requires_video = bool(execution_rule.get("requires_video"))
            available_videos = video_exports["all_video_files"] if requires_video else []
            assets_ready = (not requires_video) or bool(available_videos)
            if requires_video and not available_videos:
                blockers.append(f"{topic_id}:{normalized_channel} 缺少视频补充产物")
            channel_packs.append(
                {
                    "channel": normalized_channel,
                    "raw_channel": raw_channel,
                    "variant": variant_name,
                    "variant_file": variant_file,
                    "title_candidates": topic_decision.get("title_candidates") or [],
                    "cover_candidates": topic_decision.get("cover_candidates") or [],
                    "publish_time": topic_decision.get("publish_time"),
                    "executor_skill": execution_rule["executor_skill"],
                    "source_skill_path": execution_rule.get("source_skill_path"),
                    "supporting_skill": execution_rule.get("supporting_skill"),
                    "supporting_skill_path": execution_rule.get("supporting_skill_path"),
                    "helper_skills": execution_rule.get("helper_skills") or [],
                    "automation_level": execution_rule["automation_level"],
                    "mode": execution_rule["mode"],
                    "requires_video": requires_video,
                    "available_videos": available_videos,
                    "assets_ready": assets_ready,
                    "topic_video_manifest": video_topic.get("topic_video_manifest"),
                }
            )

        packs.append(
            {
                "topic_id": topic_id,
                "topic_name": str(topic_decision.get("topic_name") or rewrite_topic.get("title") or topic_id),
                "editor_status": topic_decision.get("editor_status"),
                "selected_channels": normalized_channels,
                "channel_packs": channel_packs,
                "interactive_chart_video_ok": bool(video_topic.get("exports", {}).get("interactive_charts", {}).get("ok")),
                "motion_narrative_video_ok": bool(video_topic.get("exports", {}).get("motion_narrative", {}).get("ok")),
            }
        )

    status = "ready_for_execution" if packs and not blockers else "pending_channel_preflight"
    return {
        "run_id": run_id,
        "stage": "publish",
        "layer": "channel_adaptation",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "status": status,
        "blockers": blockers,
        "topics": packs,
    }


def first_available_video(pack: dict[str, Any]) -> str | None:
    videos = pack.get("available_videos") or []
    if not isinstance(videos, list):
        return None
    return str(videos[0]) if videos else None


def first_cover_candidate(pack: dict[str, Any]) -> str | None:
    covers = pack.get("cover_candidates") or []
    if not isinstance(covers, list):
        return None
    return str(covers[0]) if covers else None


def build_executor_invocation(pack: dict[str, Any], topic_name: str) -> dict[str, Any]:
    channel = str(pack.get("channel") or "")
    executor_skill = pack.get("executor_skill")
    variant_file = str(pack.get("variant_file") or "")
    video_file = first_available_video(pack)
    cover_file = first_cover_candidate(pack)

    base = {
        "executor_skill": executor_skill,
        "channel": channel,
        "requires_user_confirmation": pack.get("automation_level") != "automated",
        "dry_run_default": True,
    }
    if not executor_skill:
        return {
            **base,
            "type": "manual_export",
            "command": None,
            "notes": "当前渠道缺少正式自动发布执行器，只导出人工发布包。",
        }
    if channel == "xiaohongshu_video":
        command = ["openclaw", "skill", "xiaohongshu-auto", "publish", "--title", topic_name, "--content-file", variant_file]
        if video_file:
            command.extend(["--video", video_file])
        return {**base, "type": "cli_command", "command": command, "notes": "小红书视频发布命令，执行前仍需平台登录态与人工确认策略。"}
    if channel == "xiaohongshu_image":
        command = ["openclaw", "skill", "xiaohongshu-auto", "publish", "--title", topic_name, "--content-file", variant_file]
        if cover_file:
            command.extend(["--images", cover_file])
        return {**base, "type": "cli_command", "command": command, "notes": "小红书图文发布命令，图片组不足时需先补齐首图/配图。"}
    if channel == "douyin_video":
        command = [
            "node",
            str(OPENCLAW_INSTALLER_ROOT / "skills/default/douyin-upload-skill/scripts/douyin.js"),
            "publish",
        ]
        if video_file:
            command.extend(["--video", video_file])
        command.extend(["--text-file", variant_file, "--private-status", "0", "--auto-confirm", "false"])
        return {**base, "type": "cli_command", "command": command, "notes": "抖音官方 API / fallback 执行命令，默认不自动确认。"}
    if channel == "zhihu_post":
        return {
            **base,
            "type": "browser_procedure",
            "command": None,
            "procedure": [
                "打开 https://zhuanlan.zhihu.com/write 或知乎首页想法入口",
                "确认 Chrome Browser Relay 已 attach 并登录知乎",
                f"读取本地稿件 {variant_file}，填入标题与正文",
                "停在发布按钮前等待用户确认；发布后截图并回写 platform_url",
            ],
            "notes": "知乎发布依赖浏览器 Relay，不直接构造无确认发布命令。",
        }
    if channel == "wechat_article":
        return {
            **base,
            "type": "skill_procedure",
            "command": None,
            "procedure": [
                "优先使用 baoyu-post-to-wechat 创建公众号草稿或打开浏览器确认",
                "如需 CLI fallback，使用 helper_invocations 中的 wechat-public-cli 草稿命令",
            ],
            "notes": "公众号默认先草稿/确认，不直接群发。",
        }
    return {
        **base,
        "type": "skill_procedure",
        "command": None,
        "notes": "该渠道已有 executor_skill，但当前脚本只生成可调用计划，不自动执行。",
    }


def build_helper_invocations(pack: dict[str, Any], topic_name: str) -> list[dict[str, Any]]:
    variant_file = str(pack.get("variant_file") or "")
    helpers = pack.get("helper_skills") or []
    if not isinstance(helpers, list):
        return []
    invocations: list[dict[str, Any]] = []
    for helper in helpers:
        helper_name = str(helper or "")
        if helper_name == "wechat-public-cli" and variant_file:
            invocations.append(
                {
                    "helper_skill": helper_name,
                    "type": "cli_command",
                    "command": ["wechat-public-cli", "wechat:draft", "--file", variant_file],
                    "notes": "公众号 CLI fallback：只创建草稿，不直接群发。",
                }
            )
        elif helper_name == "xiaohongshu-ops":
            invocations.append(
                {
                    "helper_skill": helper_name,
                    "type": "ops_procedure",
                    "command": None,
                    "procedure": [
                        "按账号定位与发布前演练检查标题、标签、封面、互动问句。",
                        "到发布按钮可见处停手，默认不直接点击发布。",
                        f"主题：{topic_name}",
                    ],
                    "notes": "小红书运营辅助，不替代 xiaohongshu-auto 执行器。",
                }
            )
        elif helper_name == "publish-guard":
            invocations.append(
                {
                    "helper_skill": helper_name,
                    "type": "verification_procedure",
                    "command": None,
                    "notes": "平台执行完成并获得 URL/草稿状态后，再执行验真。",
                }
            )
        elif helper_name:
            invocations.append(
                {
                    "helper_skill": helper_name,
                    "type": "reference_procedure",
                    "command": None,
                    "notes": "辅助 skill 已记录，按该 skill 的 SKILL.md 执行。",
                }
            )
    return invocations


def build_channel_execution_manifest(
    *,
    run_id: str,
    adaptation_manifest: dict[str, Any],
) -> dict[str, Any]:
    executions: list[dict[str, Any]] = []
    blockers: list[str] = []
    for topic in adaptation_manifest.get("topics", []):
        topic_id = topic.get("topic_id")
        topic_name = topic.get("topic_name")
        for pack in topic.get("channel_packs", []):
            executor_skill = pack.get("executor_skill")
            requires_video = bool(pack.get("requires_video"))
            assets_ready = bool(pack.get("assets_ready"))
            if not pack.get("variant_file"):
                status = "blocked_missing_variant"
                blockers.append(f"{topic_id}:{pack.get('channel')} 缺少改写变体")
            elif requires_video and not assets_ready:
                status = "blocked_missing_assets"
                blockers.append(f"{topic_id}:{pack.get('channel')} 缺少视频素材")
            elif not executor_skill:
                status = "manual_only"
            elif pack.get("automation_level") == "approval_required":
                status = "pending_approval_request"
            elif pack.get("automation_level") == "semi_automated":
                status = "pending_user_confirmation"
            else:
                status = "pending_execution"
            executions.append(
                {
                    "topic_id": topic_id,
                    "topic_name": topic_name,
                    "channel": pack.get("channel"),
                    "variant": pack.get("variant"),
                    "variant_file": pack.get("variant_file"),
                    "executor_skill": executor_skill,
                    "source_skill_path": pack.get("source_skill_path"),
                    "supporting_skill": pack.get("supporting_skill"),
                    "supporting_skill_path": pack.get("supporting_skill_path"),
                    "helper_skills": pack.get("helper_skills") or [],
                    "automation_level": pack.get("automation_level"),
                    "mode": pack.get("mode"),
                    "status": status,
                    "manual_action_required": status in {"manual_only", "pending_user_confirmation", "pending_approval_request"},
                    "platform_url": None,
                    "platform_post_id": None,
                    "available_videos": pack.get("available_videos") or [],
                    "title_candidates": pack.get("title_candidates") or [],
                    "cover_candidates": pack.get("cover_candidates") or [],
                    "publish_time": pack.get("publish_time"),
                    "executor_invocation": build_executor_invocation(pack, topic_name),
                    "helper_invocations": build_helper_invocations(pack, topic_name),
                }
            )
    status = "pending_channel_execution"
    if executions and all(item["status"] == "manual_only" for item in executions):
        status = "manual_delivery_only"
    elif executions and not blockers and all(
        item["status"] in {"pending_execution", "pending_user_confirmation", "pending_approval_request", "manual_only"}
        for item in executions
    ):
        status = "ready_for_channel_execution"
    elif blockers:
        status = "blocked"
    return {
        "run_id": run_id,
        "stage": "publish",
        "layer": "channel_execution",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "status": status,
        "blockers": blockers,
        "executions": executions,
    }


def build_publish_verification_report(
    *,
    run_id: str,
    execution_manifest: dict[str, Any],
) -> dict[str, Any]:
    items = []
    for execution in execution_manifest.get("executions", []):
        if execution.get("platform_url"):
            status = "pending_verify"
            diagnosis = "已有平台链接，待调用 publish-guard 验真"
        elif execution.get("status") == "manual_only":
            status = "manual_publish_required"
            diagnosis = "当前平台缺少正式自动执行器，仅导出待人工发布包"
        elif str(execution.get("status")).startswith("blocked_"):
            status = "blocked"
            diagnosis = "执行前置条件未满足"
        else:
            status = "pending_execution"
            diagnosis = "尚未执行平台发布，无法验真"
        items.append(
            {
                "topic_id": execution.get("topic_id"),
                "channel": execution.get("channel"),
                "executor_skill": execution.get("executor_skill"),
                "source_skill_path": execution.get("source_skill_path"),
                "supporting_skill": execution.get("supporting_skill"),
                "supporting_skill_path": execution.get("supporting_skill_path"),
                "helper_skills": execution.get("helper_skills") or [],
                "execution_status": execution.get("status"),
                "verification_status": status,
                "diagnosis": diagnosis,
                "retry_suggestion": "先完成平台执行，再接入 publish-guard 做 URL/草稿状态验真",
            }
        )
    overall_status = "pending_execution"
    if items and all(item["verification_status"] == "manual_publish_required" for item in items):
        overall_status = "manual_publish_required"
    elif items and all(item["verification_status"] == "verified" for item in items):
        overall_status = "verified"
    elif any(item["verification_status"] == "blocked" for item in items):
        overall_status = "blocked"
    return {
        "run_id": run_id,
        "stage": "publish",
        "layer": "publish_guard",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "status": overall_status,
        "items": items,
    }


def summarize_publish_status(
    adaptation_manifest: dict[str, Any],
    execution_manifest: dict[str, Any],
    verification_report: dict[str, Any],
) -> tuple[str, str | None]:
    if verification_report.get("status") == "verified":
        return "ready_for_postmortem", "postmortem"
    if execution_manifest.get("status") == "blocked" or adaptation_manifest.get("status") == "pending_channel_preflight":
        return "blocked", None
    if verification_report.get("status") == "manual_publish_required":
        return "manual_publish_required", None
    if execution_manifest.get("status") in {"ready_for_channel_execution", "pending_channel_execution"}:
        return "pending_channel_execution", None
    return "pending_publish_verification", None


def build_publish_stage_outputs(
    *,
    run_id: str,
    rewrite_manifest_path: Path,
    publish_decision_path: Path,
    rewrite_manifest: dict[str, Any],
    publish_decision: dict[str, Any],
    topic_manifests: list[dict[str, Any]],
    video_supplement_manifest_path: Path,
    video_supplement_report_path: Path,
) -> dict[str, Any]:
    adaptation_manifest = build_channel_adaptation_manifest(
        run_id=run_id,
        rewrite_manifest=rewrite_manifest,
        publish_decision=publish_decision,
        topic_manifests=topic_manifests,
    )
    execution_manifest = build_channel_execution_manifest(
        run_id=run_id,
        adaptation_manifest=adaptation_manifest,
    )
    verification_report = build_publish_verification_report(
        run_id=run_id,
        execution_manifest=execution_manifest,
    )
    publish_status, next_stage = summarize_publish_status(
        adaptation_manifest=adaptation_manifest,
        execution_manifest=execution_manifest,
        verification_report=verification_report,
    )

    channel_packs = []
    for topic in adaptation_manifest.get("topics", []):
        flattened_channels = [pack.get("channel") for pack in topic.get("channel_packs", [])]
        first_topic_execution = [item for item in execution_manifest.get("executions", []) if item.get("topic_id") == topic.get("topic_id")]
        first_pack = topic.get("channel_packs", [{}])[0] if topic.get("channel_packs") else {}
        channel_packs.append(
            {
                "topic_id": topic.get("topic_id"),
                "topic_name": topic.get("topic_name"),
                "channels": flattened_channels,
                "title_candidates": first_pack.get("title_candidates") or [],
                "cover_candidates": first_pack.get("cover_candidates") or [],
                "interactive_chart_video_ok": bool(topic.get("interactive_chart_video_ok")),
                "motion_narrative_video_ok": bool(topic.get("motion_narrative_video_ok")),
                "execution_statuses": [item.get("status") for item in first_topic_execution],
                "topic_video_manifest": next(
                    (pack.get("topic_video_manifest") for pack in topic.get("channel_packs", []) if pack.get("topic_video_manifest")),
                    None,
                ),
            }
        )

    publish_manifest = {
        "run_id": run_id,
        "stage": "publish",
        "status": publish_status,
        "source_manifest": str(rewrite_manifest_path),
        "source_stage": str(rewrite_manifest.get("stage") or "unknown"),
        "rewrite_manifest": str(rewrite_manifest_path),
        "publish_decision": str(publish_decision_path),
        "video_supplement_manifest": str(video_supplement_manifest_path),
        "video_supplement_report": str(video_supplement_report_path),
        "publish_skill_stack": PUBLISH_SKILL_STACK,
        "channel_adaptation_manifest": "channel_adaptation_manifest.json",
        "channel_execution_manifest": "channel_execution_manifest.json",
        "publish_verification_report": "publish_verification_report.json",
        "channel_packs": channel_packs,
        "next_stage": next_stage,
    }
    return {
        "adaptation_manifest": adaptation_manifest,
        "execution_manifest": execution_manifest,
        "verification_report": verification_report,
        "publish_manifest": publish_manifest,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Canonical publish video supplement builder")
    parser.add_argument("--draft-manifest", help="Path to canonical draft_manifest.json; formal mainline input")
    parser.add_argument("--rewrite-manifest", help="Legacy path to canonical rewrite_manifest.json")
    parser.add_argument("--publish-decision", required=True, help="Path to publish_decision.json")
    parser.add_argument("--output-dir", help="Output directory; default=~/Desktop/自媒体创作/<run_id>/05_发布/video_supplement")
    parser.add_argument("--reuse-existing-video-supplement", action="store_true", help="Reuse existing topic_video_manifest.json outputs instead of rerendering videos")
    args = parser.parse_args()

    publish_decision_path = Path(args.publish_decision).expanduser().resolve()

    if args.draft_manifest:
        draft_manifest_path = Path(args.draft_manifest).expanduser().resolve()
        draft_manifest = ensure_stage_manifest(draft_manifest_path, "draft")
        rewrite_manifest, rewrite_root = build_draft_publish_manifest(draft_manifest, draft_manifest_path)
        rewrite_manifest_path = draft_manifest_path
    else:
        if not args.rewrite_manifest:
            raise WorkflowContractError("publish 阶段必须提供 --draft-manifest，或兼容模式下提供 --rewrite-manifest。")
        rewrite_manifest_path = Path(args.rewrite_manifest).expanduser().resolve()
        rewrite_manifest = ensure_stage_manifest(rewrite_manifest_path, "rewrite")
        rewrite_root = Path(rewrite_manifest["output_root"]).expanduser().resolve()

    publish_decision = ensure_publish_decision_gate(publish_decision_path)
    run_id = str(rewrite_manifest["run_id"]).strip()
    if not rewrite_root.exists():
        raise WorkflowContractError(f"rewrite_root 不存在：{rewrite_root}")

    publish_decision, decision_changed = autofill_publish_decision(
        publish_decision=publish_decision,
        rewrite_manifest=rewrite_manifest,
    )
    if decision_changed:
        write_json(publish_decision_path, publish_decision)

    output_root = Path(args.output_dir).expanduser().resolve() if args.output_dir else canonical_stage_dir("publish", run_id) / "video_supplement"
    output_root.mkdir(parents=True, exist_ok=True)

    topic_manifests: list[dict[str, Any]]
    if args.reuse_existing_video_supplement:
        topic_manifests = load_existing_topic_manifests(output_root)
        if not topic_manifests:
            raise WorkflowContractError(f"未找到可复用的视频补充产物：{output_root}")
    else:
        rewrite_topics = extract_rewrite_topic_sources(rewrite_manifest, rewrite_root)
        topic_manifests = [build_minimal_topic_manifest(rewrite_topic, output_root) for rewrite_topic in rewrite_topics]

    run_manifest = {
        "run_id": run_id,
        "stage": "publish",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "status": "video_supplement_ready",
        "source_manifest": str(rewrite_manifest_path),
        "source_stage": str(rewrite_manifest.get("stage") or "unknown"),
        "rewrite_manifest": str(rewrite_manifest_path),
        "publish_decision": str(publish_decision_path),
        "source_root": str(rewrite_root),
        "rewrite_root": str(rewrite_root),
        "finance_project": str(FINANCE_PROJECT),
        "integration_thread": "codex://threads/019d31c5-bb7f-7a40-a087-9d219e9bd6ab",
        "reused_existing_video_supplement": bool(args.reuse_existing_video_supplement),
        "topics": topic_manifests,
    }
    manifest_path = output_root / "publish_video_supplement_manifest.json"
    report_path = output_root / "publish_video_supplement_report.md"
    write_json(manifest_path, run_manifest)
    build_report(run_manifest, report_path)

    publish_stage_root = output_root.parent
    stage_outputs = build_publish_stage_outputs(
        run_id=run_id,
        rewrite_manifest_path=rewrite_manifest_path,
        publish_decision_path=publish_decision_path,
        rewrite_manifest=rewrite_manifest,
        publish_decision=publish_decision,
        topic_manifests=topic_manifests,
        video_supplement_manifest_path=manifest_path,
        video_supplement_report_path=report_path,
    )
    adaptation_manifest_path = publish_stage_root / "channel_adaptation_manifest.json"
    execution_manifest_path = publish_stage_root / "channel_execution_manifest.json"
    verification_report_path = publish_stage_root / "publish_verification_report.json"
    publish_manifest_path = publish_stage_root / "publish_manifest.json"
    write_json(adaptation_manifest_path, stage_outputs["adaptation_manifest"])
    write_json(execution_manifest_path, stage_outputs["execution_manifest"])
    write_json(verification_report_path, stage_outputs["verification_report"])

    publish_manifest = stage_outputs["publish_manifest"]
    publish_manifest["channel_adaptation_manifest"] = str(adaptation_manifest_path)
    publish_manifest["channel_execution_manifest"] = str(execution_manifest_path)
    publish_manifest["publish_verification_report"] = str(verification_report_path)
    write_json(publish_manifest_path, publish_manifest)
    write_text(
        publish_stage_root / "07_发布计划.md",
        "\n".join(
            [
                "# 07 发布计划",
                "",
                f"- run_id：`{run_id}`",
                f"- 当前状态：`{publish_manifest['status']}`",
                f"- publish_decision：`{publish_decision_path}`",
                f"- 渠道包数量：`{len(publish_manifest['channel_packs'])}`",
                f"- 渠道适配清单：`{adaptation_manifest_path}`",
                f"- 渠道执行清单：`{execution_manifest_path}`",
                f"- 发后验真清单：`{verification_report_path}`",
            ]
        )
        + "\n",
    )
    write_text(
        publish_stage_root / "07_发布包.md",
        "\n".join(
            ["# 07 发布包", ""]
            + [
                f"- `{item['topic_name']}`｜channels={item['channels']}｜互动图表={item['interactive_chart_video_ok']}｜motion={item['motion_narrative_video_ok']}｜执行状态={item['execution_statuses']}"
                for item in publish_manifest["channel_packs"]
            ]
        )
        + "\n",
    )

    # Copy concise delivery alias for editors
    editor_alias = publish_stage_root / "视频补充"
    if editor_alias.exists():
        shutil.rmtree(editor_alias)
    shutil.copytree(output_root, editor_alias)

    print(str(publish_manifest_path))


if __name__ == "__main__":
    main()
