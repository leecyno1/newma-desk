#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any


DEFAULT_ROUTER_PATH = Path("configs/video/html_anything_template_router.json")
DEFAULT_OUTPUT = Path("docs/technical/html-anything-template-matrix.md")


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def md_escape(value: Any) -> str:
    text = str(value or "").replace("\n", " ")
    return text.replace("|", "\\|")


def write_matrix(router: dict[str, Any], output: Path) -> None:
    part_router = router.get("part_router") or {}
    role_map = router.get("role_map") or {}
    matrix = router.get("template_usage_matrix") or []

    lines: list[str] = []
    lines.append("# HTML Anything 模板使用矩阵")
    lines.append("")
    lines.append(f"生成时间：{datetime.now().astimezone().isoformat(timespec='seconds')}")
    lines.append("")
    lines.append(
        "用途：把文章/口播稿拆成可执行的视觉部件，自动匹配 HTML Anything 模板，再进入视频时间轴。"
    )
    lines.append("")
    lines.append("## 内容部件到模板")
    lines.append("")
    lines.append("| 内容部件 | 触发场景 | 主模板 | 备选模板 | 时间轴策略 |")
    lines.append("| --- | --- | --- | --- | --- |")
    for part, item in part_router.items():
        lines.append(
            "| "
            + " | ".join(
                [
                    f"`{md_escape(part)}` / {md_escape(item.get('label'))}",
                    md_escape(item.get("trigger")),
                    f"`{md_escape(item.get('primary'))}`",
                    ", ".join(f"`{template_id}`" for template_id in item.get("alternates", [])),
                    md_escape(item.get("timing_policy")),
                ]
            )
            + " |"
        )

    lines.append("")
    lines.append("## 关键文章元素映射")
    lines.append("")
    lines.append("| 文章/视频元素 | 应用规则 | 首选模板 |")
    lines.append("| --- | --- | --- |")
    element_map = [
        ("标题", "进入视频的第一视觉锚点；主标题逐字或分层入场。", "article_title"),
        ("副标题/导语", "承接标题，不承担复杂信息密度。", "article_subtitle"),
        ("文章总体架构大纲", "转成章节地图，随口播逐项高亮。", "overall_outline"),
        ("章节标题", "短节奏卡，2-4 秒，不要长篇文字。", "chapter_divider"),
        ("逻辑链路", "政策、市场、产业、资金之间的因果关系。", "logic_chain"),
        ("真实数据图表", "必须来自文章数据或重新取数，不能造假图。", "data_chart"),
        ("金融市场图表", "资产价格、收益率、估值、财务指标。", "financial_chart"),
        ("表格", "只展示关键行列，适合逐行扫光。", "data_table"),
        ("文章图片/资料图", "复用文章图片，做裁切、放大、重点标注。", "article_image"),
        ("引用/金句", "短引用用社交卡，作者判断用 pull quote。", "quote"),
        ("开头钩子", "冲突、反常识、悬念句。", "opening_hook"),
        ("结尾", "结论、CTA、品牌落版。", "closing_outro"),
        ("手机框展示", "微信、小红书、交易软件、App 截图。", "phone_mockup"),
        ("桌面框展示", "网页、后台、大屏、PC 端材料。", "desktop_mockup"),
        ("聊天框/评论", "评论区、私信、问答式内容。", "chat_box"),
    ]
    for label, rule, part in element_map:
        templates = role_map.get(part) or []
        lines.append(f"| {label} | {rule} | {', '.join(f'`{item}`' for item in templates[:4])} |")

    lines.append("")
    lines.append("## 模板到使用场景")
    lines.append("")
    lines.append("| 模板 | 中文名 | 类别 | 适合内容 | 推荐触发 | 填充要求 |")
    lines.append("| --- | --- | --- | --- | --- | --- |")
    for item in matrix:
        lines.append(
            "| "
            + " | ".join(
                [
                    f"`{md_escape(item.get('template_id'))}`",
                    md_escape(item.get("zh_name")),
                    md_escape(item.get("category")),
                    "、".join(md_escape(slot) for slot in item.get("article_slots", [])[:6]),
                    md_escape(item.get("recommended_trigger")),
                    md_escape(item.get("fill_requirements")),
                ]
            )
            + " |"
        )

    lines.append("")
    lines.append("## 时间轴原则")
    lines.append("")
    lines.append("- 先由口播稿或文章段落估算语速，再把视觉部件贴到对应句群。")
    lines.append("- 一个内容部件只解决一个视觉任务：标题、总纲、图表、表格、引用、证据、转场不要混在一张卡里。")
    lines.append("- 图表、表格、金融数据必须复用 Draft 文章里的真实数据；没有数据就回到 Draft/取数环节补，不允许生成假图。")
    lines.append("- 转场和章节卡要短；数据图、逻辑链、证据画面可以稍长，但必须跟口播语义同步 reveal。")
    lines.append("- 最终视频不显示开发标签、模板名、调试进度条。")

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(lines) + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export readable HTML Anything template matrix.")
    parser.add_argument("--router", default=str(DEFAULT_ROUTER_PATH))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    router_path = Path(args.router).expanduser().resolve()
    output = Path(args.output).expanduser().resolve()
    write_matrix(load_json(router_path), output)
    print(json.dumps({"status": "ok", "output": str(output)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
