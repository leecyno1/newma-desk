#!/usr/bin/env python3
from __future__ import annotations

import argparse
import html
import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

from video_driver_rules import (
    audio_for_beat,
    classify_beat,
    explainer_state_for_beat,
    load_driver_rules,
    score_driver,
    transition_for_beat,
    weighted_driver_score,
)


TEXT_CLEAN_RE = re.compile(r"\s+")
DEFAULT_ROUTER_PATH = Path("configs/video/html_anything_template_router.json")


@dataclass
class HtmlArticle:
    title: str = ""
    headings: list[tuple[int, str]] = field(default_factory=list)
    paragraphs: list[str] = field(default_factory=list)
    tables: list[list[list[str]]] = field(default_factory=list)
    images: list[dict[str, str]] = field(default_factory=list)
    blocks: list[dict[str, Any]] = field(default_factory=list)


class ArticleParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.article = HtmlArticle()
        self._tag_stack: list[str] = []
        self._text_buf: list[str] = []
        self._current_heading: int | None = None
        self._current_table: list[list[str]] | None = None
        self._current_row: list[str] | None = None
        self._current_cell: list[str] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_dict = {key: value or "" for key, value in attrs}
        self._tag_stack.append(tag)
        if tag == "title":
            self._text_buf = []
        elif tag in {"h1", "h2", "h3"}:
            self._text_buf = []
            self._current_heading = int(tag[1])
        elif tag == "p":
            self._text_buf = []
        elif tag == "table":
            self._current_table = []
        elif tag == "tr" and self._current_table is not None:
            self._current_row = []
        elif tag in {"td", "th"} and self._current_row is not None:
            self._current_cell = []
        elif tag == "img":
            self.article.images.append(
                {
                    "src": attrs_dict.get("src", ""),
                    "alt": attrs_dict.get("alt", ""),
                }
            )

    def handle_endtag(self, tag: str) -> None:
        text = clean_text("".join(self._text_buf))
        if tag == "title" and text and not self.article.title:
            self.article.title = text
        elif tag in {"h1", "h2", "h3"} and text:
            self.article.headings.append((self._current_heading or 2, text))
            self.article.blocks.append({"type": "heading", "level": self._current_heading or 2, "text": text})
            if tag == "h1" and not self.article.title:
                self.article.title = text
            self._current_heading = None
        elif tag == "p" and len(text) >= 12:
            self.article.paragraphs.append(text)
            self.article.blocks.append({"type": "paragraph", "text": text})
        elif tag in {"td", "th"} and self._current_cell is not None and self._current_row is not None:
            self._current_row.append(clean_text("".join(self._current_cell)))
            self._current_cell = None
        elif tag == "tr" and self._current_row is not None and self._current_table is not None:
            if any(cell for cell in self._current_row):
                self._current_table.append(self._current_row)
            self._current_row = None
        elif tag == "table" and self._current_table is not None:
            if self._current_table:
                self.article.tables.append(self._current_table)
            self._current_table = None
        if self._tag_stack:
            self._tag_stack.pop()
        if tag in {"title", "h1", "h2", "h3", "p"}:
            self._text_buf = []

    def handle_data(self, data: str) -> None:
        if self._current_cell is not None:
            self._current_cell.append(data)
        elif self._tag_stack and self._tag_stack[-1] in {"title", "h1", "h2", "h3", "p"}:
            self._text_buf.append(data)


def clean_text(text: str) -> str:
    return TEXT_CLEAN_RE.sub(" ", html.unescape(text)).strip()


def parse_html_article(path: Path) -> HtmlArticle:
    parser = ArticleParser()
    parser.feed(path.read_text(encoding="utf-8", errors="ignore"))
    article = parser.article
    if not article.title:
        article.title = path.stem
    return article


def section_summaries(article: HtmlArticle) -> list[dict[str, Any]]:
    sections: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    for block in article.blocks:
        if block.get("type") == "heading" and int(block.get("level") or 2) <= 3:
            if current:
                sections.append(current)
            current = {"heading": str(block["text"]), "level": int(block.get("level") or 2), "paragraphs": []}
        elif block.get("type") == "paragraph":
            if current is None:
                current = {"heading": "开场判断", "level": 2, "paragraphs": []}
            current["paragraphs"].append(str(block["text"]))
    if current:
        sections.append(current)
    if not sections:
        paragraphs = list(article.paragraphs)
        for idx in range(0, min(len(paragraphs), 8), 2):
            sections.append(
                {
                    "heading": f"观点 {idx // 2 + 1}",
                    "level": 2,
                    "paragraphs": paragraphs[idx : idx + 2],
                }
            )
    for section in sections:
        section["paragraphs"] = section.get("paragraphs", [])[:3]
    return sections[:16]


def load_router(path: Path | None) -> dict[str, Any]:
    if path and path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    if DEFAULT_ROUTER_PATH.exists():
        return json.loads(DEFAULT_ROUTER_PATH.read_text(encoding="utf-8"))
    return {"part_router": {}}


def scene_content_part(scene_type: str, title: str = "") -> str:
    if scene_type == "hook":
        return "opening_hook"
    if scene_type == "outro":
        return "closing_outro"
    if scene_type == "table":
        return "data_table"
    if scene_type == "image":
        return "article_image"
    if re.search(r"风险|冲击|暴跌|爆破|加息|流动性|危机", title):
        return "warning_or_risk"
    if re.search(r"链|传导|结构|逻辑|三把刀", title):
        return "logic_chain"
    return "chapter_divider"


def template_match(router: dict[str, Any], content_part: str, fallback: str) -> dict[str, Any]:
    item = (router.get("part_router") or {}).get(content_part) or {}
    primary = item.get("primary") or fallback
    return {
        "content_part": content_part,
        "template_id": primary,
        "alternates": item.get("alternates") or [],
        "candidates": item.get("candidates") or [],
        "reason": (item.get("candidates") or [{}])[0].get("reason", "fallback template mapping"),
    }


def short_script(text: str, limit: int = 90) -> str:
    text = clean_text(text)
    return text if len(text) <= limit else text[: limit - 1] + "…"


def scene_motion_for_state(director_state: str, beat_class: str) -> dict[str, Any]:
    if director_state == "evidence_scene" and beat_class == "evidence_data":
        return {
            "entrance": "axis_or_table_reveal",
            "focus_change": "number_count_or_row_scan",
            "exit": "hold_then_cut",
        }
    if director_state == "evidence_scene":
        return {
            "entrance": "document_push_zoom",
            "focus_change": "highlight_source_line",
            "exit": "soft_push_out",
        }
    if director_state == "logic_animation":
        return {
            "entrance": "node_stagger_in",
            "focus_change": "path_highlight",
            "exit": "fade_to_next_node",
        }
    if director_state in {"hook_card", "chapter_card"}:
        return {
            "entrance": "kinetic_title_in",
            "focus_change": "accent_flash_or_light_leak",
            "exit": "impact_cut",
        }
    if director_state == "cinematic_bridge":
        return {
            "entrance": "slow_fade_in",
            "focus_change": "ambient_motion",
            "exit": "light_leak_fade",
        }
    if director_state in {"recap_card", "outro"}:
        return {
            "entrance": "resolve_fade_in",
            "focus_change": "summary_highlight",
            "exit": "brand_or_music_tail",
        }
    return {
        "entrance": "fade_up",
        "focus_change": "subtle_push",
        "exit": "hard_cut_or_short_fade",
    }


def build_explainer_storyboard(
    article: HtmlArticle,
    *,
    source_html: str | None = None,
    duration_target_sec: int = 180,
    router: dict[str, Any] | None = None,
    aspect: str = "9:16",
) -> dict[str, Any]:
    rules = load_driver_rules()
    scenes: list[dict[str, Any]] = []
    cursor = 0.0
    last_evidence_at = 0.0
    router = router or {"part_router": {}}

    def add_scene(scene_type: str, title: str, narration: str, duration: float, variables: dict[str, Any]) -> None:
        nonlocal cursor, last_evidence_at
        char_count = len(clean_text(narration))
        estimated_speech_sec = max(4.0, char_count / 5.2)
        scene_duration = max(duration, estimated_speech_sec)
        beat_text = f"{title}。{narration}"
        beat_class = classify_beat(beat_text, scene_type=scene_type, index=len(scenes) + 1)
        content_part = scene_content_part(scene_type, title)
        if scene_type == "section":
            if beat_class == "evidence_data":
                content_part = "financial_chart"
            elif beat_class == "evidence_document":
                content_part = "news_or_document"
            elif beat_class == "logic_chain":
                content_part = "logic_chain"
            elif beat_class == "objection":
                content_part = "warning_or_risk"
        fallback = {
            "hook": "frame-glitch-title",
            "section": "deck-swiss-international",
            "table": "data-report",
            "image": "doc-kami-parchment",
            "outro": "frame-logo-outro",
        }[scene_type]
        match = template_match(router, content_part, fallback)
        driver_scores = score_driver(
            beat_text,
            beat_class=beat_class,
            duration=scene_duration,
            seconds_since_evidence=cursor - last_evidence_at,
            index=len(scenes) + 1,
            lane="explainer",
        )
        director_state = explainer_state_for_beat(
            beat_class,
            index=len(scenes) + 1,
            seconds_since_evidence=cursor - last_evidence_at,
        )
        if beat_class in {"evidence_data", "evidence_document"} or scene_type in {"table", "image"}:
            last_evidence_at = cursor
        scenes.append(
            {
                "id": f"scene_{len(scenes) + 1:03d}",
                "type": scene_type,
                "beat_class": beat_class,
                "director_state": director_state,
                "driver_scores": driver_scores,
                "driver_score": weighted_driver_score(driver_scores, rules),
                "content_part": content_part,
                "template_id": match["template_id"],
                "template_match": match,
                "start_sec": round(cursor, 3),
                "duration_sec": round(scene_duration, 3),
                "title": title,
                "narration": narration,
                "timing": {
                    "char_count": char_count,
                    "estimated_speech_sec": round(estimated_speech_sec, 3),
                    "target_cps": 5.2,
                },
                "variables": variables,
                "transition_to_next": transition_for_beat(beat_class, lane="explainer", duration=scene_duration),
                "audio": audio_for_beat(beat_class),
                "motion": scene_motion_for_state(director_state, beat_class),
                "evidence_required": scene_type in {"section", "table"},
            }
        )
        cursor += scene_duration

    add_scene(
        "hook",
        article.title,
        f"今天我们用几分钟讲清楚：{article.title}",
        6.0,
        {"headline": article.title, "kicker": "市场分析"},
    )
    for section in section_summaries(article):
        paragraphs = section.get("paragraphs") or []
        narration = short_script("。".join(paragraphs) or section["heading"], 140)
        add_scene(
            "section",
            section["heading"],
            narration,
            10.0,
            {
                "heading": section["heading"],
                "bullets": [short_script(item, 42) for item in paragraphs[:3]],
            },
        )
    for idx, table in enumerate(article.tables[:4], 1):
        rows = table[:6]
        add_scene(
            "table",
            f"关键数据 {idx}",
            "这组数据是本段判断的证据，不使用泛化示意图。",
            8.0,
            {
                "table": rows,
                "source": "from_article_html",
                "chart_policy": "reuse_real_table_or_chart",
            },
        )
    for idx, image in enumerate(article.images[:3], 1):
        add_scene(
            "image",
            f"资料画面 {idx}",
            short_script(image.get("alt") or "这里插入文章中的资料图。", 80),
            6.0,
            {"src": image.get("src", ""), "alt": image.get("alt", "")},
        )
    add_scene(
        "outro",
        "结论",
        "判断市场，不靠单点情绪，靠趋势、数据和约束条件一起校验。",
        5.0,
        {"brand": "Newma", "callout": "数据驱动，谨慎判断"},
    )
    if cursor > duration_target_sec:
        scale = duration_target_sec / cursor
        cursor = 0.0
        for scene in scenes:
            scene["start_sec"] = round(cursor, 3)
            scene["duration_sec"] = round(max(4.0, scene["duration_sec"] * scale), 3)
            cursor += scene["duration_sec"]
    return {
        "schema_version": "dasheng.explainer_storyboard.v1",
        "lane": "explainer_html_video",
        "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "source_html": source_html,
        "title": article.title,
        "aspect": aspect,
        "renderer": "html-video",
        "template_router_schema": router.get("schema_version"),
        "driver_rules_schema": rules.get("schema_version"),
        "director_state_machine": [
            "hook_card",
            "question_setup",
            "chapter_card",
            "evidence_scene",
            "logic_animation",
            "cinematic_bridge",
            "recap_card",
            "outro",
        ],
        "duration_estimate_sec": round(sum(scene["duration_sec"] for scene in scenes), 3),
        "style": {
            "direction": "finance_documentary_horizontal" if aspect == "16:9" else "finance_documentary_vertical",
            "avoid": ["ppt_bullet_dump", "fake_chart", "developer_overlay_labels"],
            "use": ["real_tables", "article_charts", "document_zoom", "kinetic_title"],
        },
        "scenes": scenes,
    }


def write_preview_html(path: Path, storyboard: dict[str, Any]) -> None:
    rows = []
    for scene in storyboard["scenes"]:
        rows.append(
            f"<section><b>{html.escape(scene['id'])}</b><h2>{html.escape(scene['title'])}</h2>"
            f"<p>{html.escape(scene['narration'])}</p>"
            f"<small>{html.escape(scene['template_id'])} · {scene['duration_sec']}s</small></section>"
        )
    content = """<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><style>
body{margin:0;padding:24px;background:#101215;color:#f6f3ec;font-family:-apple-system,BlinkMacSystemFont,"PingFang SC",sans-serif}
section{border:1px solid #334155;border-radius:14px;padding:16px;margin:0 0 14px;background:#172033}
h1,h2,p{margin:0 0 10px} small{color:#9fb1c7}
</style></head><body>
""" + f"<h1>{html.escape(storyboard['title'])}</h1>" + "\n".join(rows) + "</body></html>"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build a Newma no-human explainer storyboard from article HTML.")
    parser.add_argument("--html", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--preview-html")
    parser.add_argument("--duration-target-sec", type=int, default=180)
    parser.add_argument("--template-router", default=str(DEFAULT_ROUTER_PATH))
    parser.add_argument("--aspect", choices=["9:16", "16:9", "3:4"], default="9:16")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    source = Path(args.html).expanduser().resolve()
    article = parse_html_article(source)
    router = load_router(Path(args.template_router).expanduser().resolve() if args.template_router else None)
    storyboard = build_explainer_storyboard(
        article,
        source_html=str(source),
        duration_target_sec=args.duration_target_sec,
        router=router,
        aspect=args.aspect,
    )
    output = Path(args.output).expanduser().resolve()
    write_json(output, storyboard)
    if args.preview_html:
        write_preview_html(Path(args.preview_html).expanduser().resolve(), storyboard)
    print(json.dumps({"status": "ok", "output": str(output), "scenes": len(storyboard["scenes"])}, ensure_ascii=False))


if __name__ == "__main__":
    main()
