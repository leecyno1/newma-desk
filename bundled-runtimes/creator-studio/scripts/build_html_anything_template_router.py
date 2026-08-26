#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_HTML_ANYTHING_ROOT = Path(
    os.environ.get("HTML_ANYTHING_ROOT", str(PROJECT_ROOT / "vendor/reserved/render/html-anything"))
).expanduser()


PART_RULES: list[tuple[str, list[str]]] = [
    ("article_title", ["frame-liquid-bg-hero", "vfx-text-cursor", "frame-glitch-title", "poster-hero", "magazine-poster"]),
    ("article_subtitle", ["frame-light-leak-cinema", "deck-guizang-editorial", "deck-swiss-international"]),
    ("opening_hook", ["frame-glitch-title", "frame-liquid-bg-hero", "vfx-text-cursor", "motion-frames"]),
    ("closing_outro", ["frame-logo-outro", "poster-hero", "card-twitter"]),
    ("chapter_divider", ["frame-light-leak-cinema", "frame-glitch-title", "deck-swiss-international", "deck-dir-key-nav"]),
    ("overall_outline", ["frame-flowchart-sticky", "deck-blueprint", "deck-swiss-international", "deck-guizang-editorial"]),
    ("logic_chain", ["frame-flowchart-sticky", "deck-blueprint", "wireframe-sketch", "deck-graphify-dark"]),
    ("timeline", ["deck-blueprint", "weekly-update", "deck-dir-key-nav", "frame-flowchart-sticky"]),
    ("data_chart", ["frame-data-chart-nyt", "data-report", "finance-report", "frame-flowchart-sticky"]),
    ("financial_chart", ["finance-report", "frame-data-chart-nyt", "data-report", "dashboard"]),
    ("data_table", ["data-report", "finance-report", "dashboard", "invoice"]),
    ("kpi_card", ["data-report", "finance-report", "dashboard", "frame-data-chart-nyt"]),
    ("article_image", ["doc-kami-parchment", "article-magazine", "mockup-device-3d", "frame-light-leak-cinema"]),
    ("quote", ["card-twitter", "blog-post", "article-magazine", "doc-kami-parchment"]),
    ("pull_quote", ["blog-post", "article-magazine", "card-twitter", "deck-guizang-editorial"]),
    ("warning_or_risk", ["deck-safety-alert", "frame-glitch-title", "deck-hermes-cyber"]),
    ("news_or_document", ["doc-kami-parchment", "article-magazine", "docs-page", "blog-post"]),
    ("source_citation", ["doc-kami-parchment", "docs-page", "eng-runbook", "article-magazine"]),
    ("phone_mockup", ["mobile-app", "mobile-onboarding", "mockup-device-3d", "gamified-app"]),
    ("desktop_mockup", ["mockup-device-3d", "web-proto-editorial", "web-proto-soft", "prototype-web"]),
    ("chat_box", ["social-x-post-card", "social-reddit-card", "frame-macos-notification", "card-twitter"]),
    ("social_post", ["social-x-post-card", "social-reddit-card", "card-twitter", "social-carousel"]),
    ("xiaohongshu_card", ["card-xiaohongshu", "deck-xhs-post", "deck-xhs-white", "deck-xhs-pastel"]),
    ("dashboard_screen", ["dashboard", "live-dashboard", "social-media-dashboard", "social-media-matrix"]),
    ("kanban_or_process", ["kanban-board", "team-okrs", "pm-spec", "eng-runbook"]),
    ("product_or_app_ui", ["mobile-app", "saas-landing", "prototype-web", "web-proto-soft"]),
    ("broll_mood", ["frame-light-leak-cinema", "motion-frames", "sprite-animation", "frame-liquid-bg-hero"]),
    ("transition", ["frame-glitch-title", "vfx-text-cursor", "frame-light-leak-cinema", "motion-frames"]),
    ("brand_mark", ["frame-logo-outro", "poster-hero", "card-twitter"]),
    ("deck_explainer", ["video-hyperframes", "deck-swiss-international", "deck-guizang-editorial", "deck-magazine-web"]),
]


FALLBACK_BY_CATEGORY = {
    "article": ["news_or_document", "pull_quote"],
    "card": ["quote", "social_post", "chat_box"],
    "dashboard": ["dashboard_screen", "data_table", "kpi_card"],
    "data": ["data_chart", "data_table"],
    "doc": ["news_or_document", "source_citation"],
    "email": ["news_or_document"],
    "finance": ["financial_chart", "data_table", "kpi_card"],
    "mobile": ["phone_mockup", "product_or_app_ui"],
    "poster": ["article_title", "broll_mood"],
    "prototype": ["desktop_mockup", "product_or_app_ui"],
    "resume": ["news_or_document"],
    "slides": ["chapter_divider", "overall_outline", "deck_explainer"],
    "video": ["transition", "opening_hook", "broll_mood"],
}


PART_LABELS = {
    "article_title": "标题 / 封面",
    "article_subtitle": "副标题 / 氛围解释",
    "opening_hook": "开头钩子",
    "closing_outro": "结尾 / CTA",
    "chapter_divider": "章节标题",
    "overall_outline": "文章总纲 / 大纲",
    "logic_chain": "逻辑链路 / 推导",
    "timeline": "时间线 / 进度",
    "data_chart": "图表 / 数据可视化",
    "financial_chart": "金融市场图表",
    "data_table": "表格 / 指标清单",
    "kpi_card": "关键数字卡",
    "article_image": "文章图片 / 资料截图",
    "quote": "引用 / 社交观点",
    "pull_quote": "正文金句",
    "warning_or_risk": "风险警示",
    "news_or_document": "新闻 / 文档证据",
    "source_citation": "来源引用",
    "phone_mockup": "手机框展示",
    "desktop_mockup": "桌面框展示",
    "chat_box": "聊天框 / 评论",
    "social_post": "社交帖子",
    "xiaohongshu_card": "小红书卡片",
    "dashboard_screen": "仪表盘",
    "kanban_or_process": "流程 / 看板",
    "product_or_app_ui": "产品界面",
    "broll_mood": "氛围 B-roll",
    "transition": "转场",
    "brand_mark": "品牌落版",
    "deck_explainer": "连续解释 Deck",
}


PART_TRIGGERS = {
    "article_title": "文章标题、视频主标题、封面标题。",
    "article_subtitle": "副标题、导语、背景气氛句。",
    "opening_hook": "开场 3-8 秒强钩子、反常识判断、冲突句。",
    "closing_outro": "结尾总结、关注提示、下期预告。",
    "chapter_divider": "一、二、三等章节切换，或口播进入下一段。",
    "overall_outline": "文章总框架、目录、核心问题列表。",
    "logic_chain": "因果推导、传导路径、政策/市场/产业三段链。",
    "timeline": "事件先后、政策节奏、口播进度。",
    "data_chart": "折线、柱状、对比、散点、范围带等真实数据。",
    "financial_chart": "股指、债券、汇率、商品、估值、财务指标。",
    "data_table": "文章表格、指标清单、财务明细、横向对比。",
    "kpi_card": "单个关键数字、同比环比、概率、估值、融资额。",
    "article_image": "文章内图片、截图、资料图、报告截屏。",
    "quote": "社交媒体引用、外部人物原话、短观点。",
    "pull_quote": "作者金句、需要居中放大的判断句。",
    "warning_or_risk": "风险、暴跌、踩踏、政策红线、反转信号。",
    "news_or_document": "新闻事实、官方文件、研究报告、公告。",
    "source_citation": "数据来源、脚注、报告出处。",
    "phone_mockup": "App、手机截图、微信/小红书/交易软件界面。",
    "desktop_mockup": "网页、后台、大屏、PC 软件截图。",
    "chat_box": "聊天记录、评论区、问答对话。",
    "social_post": "X/Reddit/小红书/微博式帖子。",
    "xiaohongshu_card": "小红书封面、笔记页、图文轮播。",
    "dashboard_screen": "数据后台、监控面板、组合指标。",
    "kanban_or_process": "流程拆解、任务状态、执行步骤。",
    "product_or_app_ui": "产品原型、功能页、应用落地演示。",
    "broll_mood": "无具体数据但需要视觉情绪承托的段落。",
    "transition": "段落之间 1-3 秒节奏切换。",
    "brand_mark": "片尾署名、栏目品牌、Logo 落版。",
    "deck_explainer": "需要多页连续解释的复杂段落。",
}


TIMING_BY_PART = {
    "article_title": "3-6s，随主标题逐字或分层入场。",
    "article_subtitle": "3-6s，接标题后轻过渡。",
    "opening_hook": "4-8s，必须卡住口播第一句冲突点。",
    "closing_outro": "4-7s，跟最后一句结论对齐。",
    "chapter_divider": "2-4s，短，不抢正文。",
    "overall_outline": "6-10s，覆盖口播总纲，允许逐项高亮。",
    "logic_chain": "6-12s，节点跟随口播逐步点亮。",
    "timeline": "5-10s，按事件顺序推进。",
    "data_chart": "6-12s，先出现坐标/指标，再 reveal 数据结论。",
    "financial_chart": "6-12s，跟关键市场数据或财务指标同步。",
    "data_table": "5-10s，表格只显示关键行，逐行扫光。",
    "kpi_card": "3-6s，适合口播中单个强数字。",
    "article_image": "4-8s，配合放大/裁切/标注，不要静止堆图。",
    "quote": "3-6s，随引用句出现。",
    "pull_quote": "3-6s，跟金句同步放大。",
    "warning_or_risk": "4-8s，适合突然转折或风险提示。",
    "news_or_document": "5-9s，证据画面可做局部 zoom。",
    "source_citation": "2-4s，短停留，不占主节奏。",
    "phone_mockup": "5-9s，手机画面滑入并局部放大。",
    "desktop_mockup": "5-9s，网页/桌面画面进入再局部强调。",
    "chat_box": "4-8s，按对话气泡逐条出现。",
    "social_post": "4-8s，按帖文标题和核心句出现。",
    "xiaohongshu_card": "4-8s，适合竖版轮播节奏。",
    "dashboard_screen": "6-10s，KPI 和图表分层显示。",
    "kanban_or_process": "5-9s，步骤逐列推进。",
    "product_or_app_ui": "5-9s，随功能点切换。",
    "broll_mood": "3-7s，作为过渡或情绪缓冲。",
    "transition": "1-3s，只做节奏，不放开发提示文字。",
    "brand_mark": "3-5s，片尾落版。",
    "deck_explainer": "8-20s，拆成多页或多个子场景。",
}


def parse_frontmatter(path: Path) -> dict[str, str]:
    text = path.read_text(encoding="utf-8", errors="ignore")
    if not text.startswith("---"):
        return {}
    end = text.find("\n---", 3)
    if end == -1:
        return {}
    frontmatter: dict[str, str] = {}
    for line in text[3:end].splitlines():
        if ":" not in line or line.startswith(" "):
            continue
        key, value = line.split(":", 1)
        frontmatter[key.strip()] = value.strip().strip("\"'")
    return frontmatter


def template_index(html_anything_root: Path) -> list[dict[str, Any]]:
    skill_root = html_anything_root / "next/src/lib/templates/skills"
    items = []
    for skill_md in sorted(skill_root.glob("*/SKILL.md")):
        fm = parse_frontmatter(skill_md)
        items.append(
            {
                "id": skill_md.parent.name,
                "zh_name": fm.get("zh_name", ""),
                "en_name": fm.get("en_name", ""),
                "category": fm.get("category", ""),
                "scenario": fm.get("scenario", ""),
                "aspect_hint": fm.get("aspect_hint", ""),
                "description": fm.get("description", ""),
                "tags": fm.get("tags", ""),
                "featured": fm.get("featured", ""),
                "recommended": fm.get("recommended", ""),
                "skill_path": str(skill_md.relative_to(html_anything_root)),
                "example_html": str((skill_md.parent / "example.html").relative_to(html_anything_root)) if (skill_md.parent / "example.html").exists() else None,
            }
        )
    return items


def build_template_roles(templates: list[dict[str, Any]]) -> dict[str, list[str]]:
    roles: dict[str, list[str]] = {item["id"]: [] for item in templates}
    for part, ids in PART_RULES:
        for template_id in ids:
            roles.setdefault(template_id, []).append(part)
    by_id = {item["id"]: item for item in templates}
    for template_id, item in by_id.items():
        for part in FALLBACK_BY_CATEGORY.get(item.get("category", ""), []):
            if part not in roles[template_id]:
                roles[template_id].append(part)
        blob = " ".join([item.get("id", ""), item.get("zh_name", ""), item.get("description", ""), item.get("tags", "")]).lower()
        keyword_parts = {
            "chat_box": ["chat", "tweet", "reddit", "通知", "comment"],
            "phone_mockup": ["iphone", "mobile", "手机", "app"],
            "data_chart": ["chart", "图表", "data", "数据"],
            "data_table": ["table", "表", "财报", "invoice"],
            "quote": ["quote", "金句", "pull"],
            "timeline": ["weekly", "roadmap", "timeline", "进度"],
            "warning_or_risk": ["risk", "alert", "safety", "incident", "警示"],
            "transition": ["frame", "vfx", "glitch", "cinema", "motion"],
        }
        for part, keywords in keyword_parts.items():
            if any(keyword in blob for keyword in keywords) and part not in roles[template_id]:
                roles[template_id].append(part)
    return roles


def build_part_router(templates: list[dict[str, Any]], roles: dict[str, list[str]]) -> dict[str, Any]:
    by_id = {item["id"]: item for item in templates}
    router: dict[str, Any] = {}
    for part, preferred in PART_RULES:
        candidates = []
        seen = set()
        for template_id in preferred + [tid for tid, parts in roles.items() if part in parts]:
            if template_id in seen or template_id not in by_id:
                continue
            seen.add(template_id)
            item = by_id[template_id]
            candidates.append(
                {
                    "template_id": template_id,
                    "zh_name": item.get("zh_name", ""),
                    "category": item.get("category", ""),
                    "aspect_hint": item.get("aspect_hint", ""),
                    "reason": reason_for_part(part, item),
                }
            )
        router[part] = {
            "label": PART_LABELS.get(part, part),
            "trigger": PART_TRIGGERS.get(part, ""),
            "timing_policy": TIMING_BY_PART.get(part, ""),
            "primary": candidates[0]["template_id"] if candidates else None,
            "alternates": [item["template_id"] for item in candidates[1:5]],
            "candidates": candidates,
        }
    return router


def build_role_map(templates: list[dict[str, Any]], roles: dict[str, list[str]]) -> dict[str, list[str]]:
    by_id = {item["id"]: item for item in templates}
    role_map: dict[str, list[str]] = {}
    for part, preferred in PART_RULES:
        ordered: list[str] = []
        for template_id in preferred + [tid for tid, parts in roles.items() if part in parts]:
            if template_id in by_id and template_id not in ordered:
                ordered.append(template_id)
        role_map[part] = ordered
    return role_map


def template_usage_matrix(templates: list[dict[str, Any]], roles: dict[str, list[str]]) -> list[dict[str, Any]]:
    matrix: list[dict[str, Any]] = []
    for item in templates:
        template_roles = roles.get(item["id"], [])
        primary_role = template_roles[0] if template_roles else "broll_mood"
        labels = [PART_LABELS.get(role, role) for role in template_roles]
        triggers = [PART_TRIGGERS.get(role, "") for role in template_roles[:4]]
        matrix.append(
            {
                "template_id": item["id"],
                "zh_name": item.get("zh_name", ""),
                "en_name": item.get("en_name", ""),
                "category": item.get("category", ""),
                "aspect_hint": item.get("aspect_hint", ""),
                "primary_content_part": primary_role,
                "content_parts": template_roles,
                "article_slots": labels,
                "recommended_trigger": triggers[0] if triggers else "",
                "timing_policy": TIMING_BY_PART.get(primary_role, ""),
                "fill_requirements": fill_requirements_for_roles(primary_role, template_roles),
            }
        )
    return matrix


def fill_requirements_for_roles(primary_role: str, roles: list[str]) -> str:
    if primary_role in {"data_chart", "financial_chart", "data_table", "kpi_card", "dashboard_screen"}:
        return "必须使用文章已验证数据、表格或图表；禁止虚构指标。"
    if primary_role in {"article_image", "news_or_document", "source_citation"}:
        return "必须复用文章图片、截图、报告或来源材料；需要局部标注。"
    if primary_role in {"quote", "pull_quote", "chat_box", "social_post"}:
        return "必须填入原文句子、评论、引用或口播金句；避免泛泛文案。"
    if primary_role in {"article_title", "opening_hook", "chapter_divider", "transition", "closing_outro", "brand_mark"}:
        return "填入标题、章节名、结论或转场词；画面只服务节奏。"
    if primary_role in {"phone_mockup", "desktop_mockup", "product_or_app_ui"}:
        return "填入真实界面截图或文章中提到的平台画面。"
    if any(role in roles for role in {"data_chart", "financial_chart", "data_table", "kpi_card", "dashboard_screen"}):
        return "可承载数据，但只有在文章提供真实数据时使用。"
    return "按内容部件填入标题、短句、要点或画面素材。"


def reason_for_part(part: str, item: dict[str, Any]) -> str:
    reasons = {
        "article_title": "承担标题/封面冲击，适合开场视觉锚点。",
        "article_subtitle": "适合副标题、背景情绪和短解释。",
        "opening_hook": "适合开头钩子和强视觉入场。",
        "closing_outro": "适合结尾品牌落版和 CTA。",
        "chapter_divider": "适合章节卡、段落切换和节奏重置。",
        "overall_outline": "适合总架构、大纲、提纲和章节地图。",
        "logic_chain": "适合因果链、推导链和多节点关系。",
        "timeline": "适合时间推进、事件序列和进度条。",
        "data_chart": "适合折线/柱状/范围带等数据图表。",
        "financial_chart": "适合财务、宏观、市场指标和资产表现。",
        "data_table": "适合表格、指标清单和财务明细。",
        "kpi_card": "适合单指标、核心数字和对比卡。",
        "quote": "适合金句、引用、观点摘录。",
        "pull_quote": "适合正文中的放大引语和强调句。",
        "warning_or_risk": "适合风险、警示、市场冲击和政策红线。",
        "news_or_document": "适合新闻、文档、截图和来源材料展示。",
        "source_citation": "适合来源说明、注释、报告引用。",
        "phone_mockup": "适合手机框、App 页面和移动端截图。",
        "desktop_mockup": "适合网页、桌面产品和大屏截图。",
        "chat_box": "适合聊天框、评论、社交媒体对话。",
        "social_post": "适合推文、Reddit、小红书等社交内容。",
        "xiaohongshu_card": "适合小红书图文卡和轮播。",
        "dashboard_screen": "适合仪表盘、后台、控制台画面。",
        "kanban_or_process": "适合流程、任务板、协作看板。",
        "product_or_app_ui": "适合产品界面和 App 原型展示。",
        "broll_mood": "适合氛围 B-roll、过渡背景和视觉隐喻。",
        "transition": "适合转场、故障、闪白、光标揭示。",
        "brand_mark": "适合品牌、署名、结尾落版。",
        "deck_explainer": "适合把多段内容组织成连续解释帧。",
    }
    base = reasons.get(part, "适合该内容部件。")
    return f"{base} 模板说明：{item.get('description', '')}"


def write_outputs(output: Path, payload: dict[str, Any]) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build Newma routing map for HTML Anything templates.")
    parser.add_argument("--html-anything-root", default=str(DEFAULT_HTML_ANYTHING_ROOT))
    parser.add_argument("--output", default="configs/video/html_anything_template_router.json")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    root = Path(args.html_anything_root).expanduser().resolve()
    templates = template_index(root)
    roles = build_template_roles(templates)
    payload = {
        "schema_version": "dasheng.html_anything_template_router.v1",
        "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "html_anything_root": "${HTML_ANYTHING_ROOT:-vendor/reserved/render/html-anything}",
        "template_paths_relative_to_root": True,
        "template_count": len(templates),
        "routing_policy": {
            "principle": "content_part -> template candidates -> storyboard scene -> renderer",
            "version_locking": False,
            "selection": "Use primary unless aspect, density, or platform constraints require an alternate.",
        },
        "part_router": build_part_router(templates, roles),
        "role_map": build_role_map(templates, roles),
        "template_usage_matrix": template_usage_matrix(templates, roles),
        "templates": [{**item, "roles": roles.get(item["id"], [])} for item in templates],
    }
    write_outputs(Path(args.output).expanduser().resolve(), payload)
    print(json.dumps({"status": "ok", "output": str(Path(args.output).resolve()), "template_count": len(templates)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
