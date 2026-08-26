#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

from canonical_workflow import WorkflowContractError, canonical_stage_dir, ensure_runtime_output_dir, ensure_stage_manifest, write_json


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content.rstrip() + "\n", encoding="utf-8")


def result_is_published(result: dict[str, Any]) -> bool:
    return (
        bool(result.get("success", True))
        and result.get("status") == "published"
        and result.get("verification_status") == "verified"
        and bool(result.get("platform_url"))
    )


def result_is_draft(result: dict[str, Any]) -> bool:
    return (
        bool(result.get("success", True))
        and result.get("status") in {"draft", "scheduled"}
        and result.get("verification_status") == "verified"
        and bool(result.get("draft_id"))
    )


def channels_for_pack(pack: dict[str, Any]) -> list[str]:
    channel = pack.get("channel")
    channels = pack.get("channels") or ([channel] if channel else [])
    if isinstance(channels, str):
        channels = [channels]
    return [str(item) for item in channels if item]


def topic_groups_from_channel_packs(channel_packs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {}
    for index, pack in enumerate(channel_packs):
        topic_id = str(pack.get("topic_id") or f"topic-{index}").strip()
        group = grouped.setdefault(
            topic_id,
            {
                "topic_id": topic_id,
                "topic_name": pack.get("topic_name") or pack.get("title"),
                "packs": [],
                "channels": [],
                "title_candidates": [],
                "cover_candidates": [],
                "interactive_chart_video_ok": False,
                "motion_narrative_video_ok": False,
                "verified_wechat_article_url": None,
            },
        )
        group["packs"].append(pack)
        if not group.get("topic_name"):
            group["topic_name"] = pack.get("topic_name") or pack.get("title")
        for channel in channels_for_pack(pack):
            if channel not in group["channels"]:
                group["channels"].append(channel)
        group["title_candidates"].extend(pack.get("title_candidates") or [])
        group["cover_candidates"].extend(pack.get("cover_candidates") or [])
        group["interactive_chart_video_ok"] = bool(group["interactive_chart_video_ok"] or pack.get("interactive_chart_video_ok"))
        group["motion_narrative_video_ok"] = bool(group["motion_narrative_video_ok"] or pack.get("motion_narrative_video_ok"))
    return list(grouped.values())


def verified_wechat_url_from_results(results: list[dict[str, Any]], topic_id: str) -> str | None:
    for item in results:
        if item.get("topic_id") != topic_id:
            continue
        if item.get("channel") != "wechat_article":
            continue
        if item.get("verification_status") != "verified":
            continue
        if item.get("status") != "published":
            continue
        if item.get("platform_url"):
            return str(item.get("platform_url"))
    return None


def publish_guard_summary(publish_manifest: dict[str, Any]) -> dict[str, Any]:
    guard = publish_manifest.get("publish_guard")
    if not isinstance(guard, dict):
        return {
            "present": False,
            "status": "missing",
            "passed": False,
            "report_json": None,
            "report_markdown": None,
            "checked_at": None,
        }
    return {
        "present": True,
        "status": guard.get("status") or "unknown",
        "passed": bool(guard.get("passed")),
        "report_json": guard.get("report_json"),
        "report_markdown": guard.get("report_markdown"),
        "checked_at": guard.get("checked_at"),
    }


def ensure_publish_guard_passed(publish_manifest: dict[str, Any]) -> None:
    guard = publish_guard_summary(publish_manifest)
    if not guard["present"]:
        raise WorkflowContractError(
            "Postmortem 要求 Publish Guard 通过，但 publish_manifest.publish_guard 缺失。"
            "请先运行 `python3 scripts/publish_guard.py --publish-manifest <publish_manifest.json>`。"
        )
    if not guard["passed"] or guard["status"] != "passed":
        raise WorkflowContractError(
            f"Postmortem 要求 Publish Guard 通过，但当前状态为 `{guard['status']}` / passed={guard['passed']}。"
            "请先修复发布批次验收问题。"
        )
    missing_reports = [
        label
        for label in ("report_json", "report_markdown")
        if not guard.get(label) or not Path(str(guard[label])).expanduser().exists()
    ]
    if missing_reports:
        raise WorkflowContractError(
            "Postmortem 要求 Publish Guard 报告文件存在，但缺失："
            + ", ".join(missing_reports)
            + "。请重新运行 `python3 scripts/publish_guard.py --publish-manifest <publish_manifest.json>`。"
        )


def build_postmortem_payload(publish_manifest: dict[str, Any], publish_manifest_path: Path) -> dict[str, Any]:
    topic_rows = publish_manifest.get("channel_packs", [])
    result_rows = publish_manifest.get("publish_results") or []
    topic_groups = topic_groups_from_channel_packs(topic_rows)
    selected_channels = Counter()
    video_ok_counter = Counter()

    topic_summaries = []
    performance_metrics = []  # 新增：性能指标列表

    for item in topic_groups:
        channels = item.get("channels") or []
        selected_channels.update(channels)
        item_results = [
            result
            for result in result_rows
            if result.get("topic_id") == item.get("topic_id") and result.get("channel") in channels
        ]
        video_ok_counter.update(
            {
                "interactive_chart_ok": 1 if item.get("interactive_chart_video_ok") else 0,
                "motion_narrative_ok": 1 if item.get("motion_narrative_video_ok") else 0,
            }
        )

        # 尝试从已发布的微信文章提取真实阅读数据
        wechat_url = verified_wechat_url_from_results(result_rows, str(item.get("topic_id") or ""))
        wechat_stats = {}
        if wechat_url and "wechat_article" in channels:
            try:
                from skill_invoker import invoke_skill
                extract_result = invoke_skill(
                    "wechat-article-extractor-skill",
                    {"url": wechat_url}
                )

                if extract_result.get("success"):
                    stats = extract_result.get("stats", {})
                    wechat_stats = {
                        "read_count": stats.get("read_count", 0),
                        "like_count": stats.get("like_count", 0),
                        "share_count": stats.get("share_count", 0),
                        "comment_count": stats.get("comment_count", 0),
                    }
                    performance_metrics.append({
                        "platform": "wechat",
                        "topic_id": item.get("topic_id"),
                        "url": wechat_url,
                        **wechat_stats
                    })
            except Exception:
                # 提取失败不影响主流程
                pass

        topic_summaries.append(
            {
                "topic_id": item.get("topic_id"),
                "topic_name": item.get("topic_name") or item.get("topic_id"),
                "published": any(result_is_published(result) for result in item_results),
                "drafted": any(result_is_draft(result) for result in item_results),
                "selected_channels": channels,
                "publish_results": item_results,
                "selected_title_count": len(item.get("title_candidates") or []),
                "selected_cover_count": len(item.get("cover_candidates") or []),
                "asset_usage": {
                    "interactive_chart_video_ok": bool(item.get("interactive_chart_video_ok")),
                    "motion_narrative_video_ok": bool(item.get("motion_narrative_video_ok")),
                },
                "performance": wechat_stats,  # 新增：性能数据
            }
        )

    guard_summary = publish_guard_summary(publish_manifest)
    return {
        "run_id": publish_manifest["run_id"],
        "stage": "postmortem",
        "status": "completed",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "upstream": {
            "publish_manifest": str(publish_manifest_path),
        },
        "publish_guard": guard_summary,
        "topics": topic_summaries,
        "performance_metrics": performance_metrics,  # 新增：性能指标
        "writeback": {
            "topic_pattern_library": {
                "selected_channel_counts": dict(selected_channels),
                "published_topics": sum(1 for item in topic_summaries if item["published"]),
                "drafted_topics": sum(1 for item in topic_summaries if item["drafted"]),
            },
            "evidence_pattern_library": {
                "interactive_chart_ok_topics": video_ok_counter["interactive_chart_ok"],
                "motion_narrative_ok_topics": video_ok_counter["motion_narrative_ok"],
            },
            "visual_pattern_library": {
                "topics_with_cover_candidates": sum(1 for item in topic_groups if item.get("cover_candidates")),
            },
            "channel_pattern_library": {
                "channel_frequency": dict(selected_channels),
                "publish_guard_passed": guard_summary["passed"],
                "publish_guard_status": guard_summary["status"],
            },
        },
    }


def render_report(payload: dict[str, Any]) -> str:
    lines = [
        "# 08 复盘报告",
        "",
        f"- run_id：`{payload['run_id']}`",
        f"- 发布题数：`{len(payload['topics'])}`",
        f"- Publish Guard：`{payload.get('publish_guard', {}).get('status', 'missing')}` / `passed={payload.get('publish_guard', {}).get('passed', False)}`",
        "",
    ]
    guard = payload.get("publish_guard") or {}
    if guard.get("present"):
        lines.extend(
            [
                "## 发布批次验收",
                "",
                f"- 状态：`{guard.get('status')}`",
                f"- 通过：`{guard.get('passed')}`",
                f"- 检查时间：`{guard.get('checked_at') or ''}`",
                f"- JSON 报告：`{guard.get('report_json') or ''}`",
                f"- Markdown 报告：`{guard.get('report_markdown') or ''}`",
                "",
            ]
        )
    else:
        lines.extend(
            [
                "## 发布批次验收",
                "",
                "- 状态：`missing`",
                "- 说明：未发现 `publish_manifest.publish_guard`，建议先运行 `scripts/publish_guard.py --publish-manifest <publish_manifest.json>`。",
                "",
            ]
        )

    # 性能指标总览
    if payload.get("performance_metrics"):
        lines.extend([
            "## 性能指标总览",
            "",
        ])
        for metric in payload["performance_metrics"]:
            lines.extend([
                f"### {metric.get('platform', 'unknown').upper()} - {metric.get('topic_id', 'N/A')}",
                f"- URL: {metric.get('url', 'N/A')}",
                f"- 阅读数: {metric.get('read_count', 0)}",
                f"- 点赞数: {metric.get('like_count', 0)}",
                f"- 分享数: {metric.get('share_count', 0)}",
                f"- 评论数: {metric.get('comment_count', 0)}",
                "",
            ])

    for item in payload["topics"]:
        lines.extend(
            [
                f"## {item['topic_name']}",
                f"- 已发布：`{item['published']}`",
                f"- 已推草稿：`{item.get('drafted', False)}`",
                f"- 渠道：`{item['selected_channels']}`",
                f"- 标题候选数：`{item['selected_title_count']}`",
                f"- 封面候选数：`{item['selected_cover_count']}`",
                f"- 图表动效视频：`{item['asset_usage']['interactive_chart_video_ok']}`",
                f"- 叙事动效视频：`{item['asset_usage']['motion_narrative_video_ok']}`",
            ]
        )

        # 显示性能数据
        if item.get("performance"):
            perf = item["performance"]
            lines.extend([
                f"- 阅读数：`{perf.get('read_count', 'N/A')}`",
                f"- 点赞数：`{perf.get('like_count', 'N/A')}`",
                f"- 分享数：`{perf.get('share_count', 'N/A')}`",
                f"- 评论数：`{perf.get('comment_count', 'N/A')}`",
            ])

        if item.get("publish_results"):
            lines.extend(["", "### 发布结果"])
            for result in item["publish_results"]:
                lines.extend(
                    [
                        f"- `{result.get('channel')}`：`{result.get('status')}` / `{result.get('verification_status')}`",
                        f"  - URL：`{result.get('platform_url') or ''}`",
                        f"  - 草稿 ID：`{result.get('draft_id') or ''}`",
                    ]
                )

        lines.append("")

    return "\n".join(lines)


def render_l1_writeback(payload: dict[str, Any]) -> str:
    writeback = payload["writeback"]
    return "\n".join(
        [
            "# 08 L1 回写建议",
            "",
            f"- 题材回写：`{writeback['topic_pattern_library']}`",
            f"- 证据回写：`{writeback['evidence_pattern_library']}`",
            f"- 视觉回写：`{writeback['visual_pattern_library']}`",
            f"- 渠道回写：`{writeback['channel_pattern_library']}`",
        ]
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Canonical postmortem writeback")
    parser.add_argument("--publish-manifest", required=True, help="Path to canonical publish_manifest.json")
    parser.add_argument("--output-dir", help="Output directory; default=~/Desktop/自媒体创作/<run_id>/06_复盘")
    parser.add_argument("--require-publish-guard", action="store_true", help="Fail if publish_manifest.publish_guard is missing or not passed.")
    args = parser.parse_args()

    publish_manifest_path = Path(args.publish_manifest).expanduser().resolve()
    publish_manifest = ensure_stage_manifest(publish_manifest_path, "publish")
    if args.require_publish_guard:
        ensure_publish_guard_passed(publish_manifest)
    run_id = str(publish_manifest["run_id"]).strip()
    output_dir = ensure_runtime_output_dir(
        Path(args.output_dir).expanduser().resolve() if args.output_dir else canonical_stage_dir("postmortem", run_id),
        label="postmortem output_dir",
    )
    output_dir.mkdir(parents=True, exist_ok=True)

    payload = build_postmortem_payload(publish_manifest, publish_manifest_path)
    write_json(output_dir / "postmortem_manifest.json", payload)
    write_text(output_dir / "08_复盘报告.md", render_report(payload))
    write_text(output_dir / "08_L1回写建议.md", render_l1_writeback(payload))
    print(str(output_dir / "postmortem_manifest.json"))


if __name__ == "__main__":
    main()
