#!/usr/bin/env python3
from __future__ import annotations

import argparse
import html
import json
import re
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


DEFAULT_ROUTER_PATH = Path("configs/video/html_anything_template_router.json")
NUMBER_RE = re.compile(r"[-+]?\d+(?:\.\d+)?%?|万亿|亿美元|bp|IPO|VIX|纳指|美债|半导体|比特币", re.I)
VALUE_RE = re.compile(r"[-+]?\d+(?:\.\d+)?\s*(?:%|万亿|亿美元|亿|万|bp|BP|美元)?")


MOTION_POLICY_BY_PART: dict[str, dict[str, Any]] = {
    "article_title": {
        "framework": "hyperframes",
        "animation": "gsap_title_reveal",
        "lottie_role": "ambient_market_open",
        "lottie_keywords": ["finance", "market", "data wave", "abstract trading"],
    },
    "opening_hook": {
        "framework": "hyperframes",
        "animation": "gsap_glitch_punch",
        "lottie_role": "signal_alert",
        "lottie_keywords": ["warning", "signal", "market alert", "breaking news"],
    },
    "overall_outline": {
        "framework": "hyperframes",
        "animation": "gsap_step_highlight",
        "lottie_role": "flow_map",
        "lottie_keywords": ["flowchart", "route", "timeline", "process"],
    },
    "chapter_divider": {
        "framework": "hyperframes",
        "animation": "gsap_cinematic_fade",
        "lottie_role": "chapter_transition",
        "lottie_keywords": ["film grain", "light leak", "transition"],
    },
    "logic_chain": {
        "framework": "hyperframes",
        "animation": "gsap_path_draw",
        "lottie_role": "causal_chain",
        "lottie_keywords": ["network", "flow", "connection", "decision tree"],
    },
    "data_chart": {
        "framework": "hyperframes",
        "animation": "gsap_chart_reveal",
        "lottie_role": "data_accent_only",
        "lottie_keywords": ["data", "chart", "analytics", "dashboard"],
        "fact_rule": "Lottie may decorate only; chart data must be rendered from article variables.",
    },
    "financial_chart": {
        "framework": "hyperframes",
        "animation": "gsap_market_bar_reveal",
        "lottie_role": "market_ticker_accent",
        "lottie_keywords": ["stock market", "candlestick", "finance chart", "trading"],
        "fact_rule": "Lottie may decorate only; financial values must come from article or verified data.",
    },
    "data_table": {
        "framework": "hyperframes",
        "animation": "gsap_table_scan",
        "lottie_role": "table_scan_accent",
        "lottie_keywords": ["spreadsheet", "data table", "scanner", "analytics"],
        "fact_rule": "Table rows must come from article HTML.",
    },
    "warning_or_risk": {
        "framework": "hyperframes",
        "animation": "gsap_alert_stack",
        "lottie_role": "risk_alarm",
        "lottie_keywords": ["alarm", "risk", "warning", "market crash"],
    },
    "quote": {
        "framework": "hyperframes",
        "animation": "gsap_quote_pop",
        "lottie_role": "quote_spark",
        "lottie_keywords": ["quote", "message", "social post"],
    },
    "pull_quote": {
        "framework": "hyperframes",
        "animation": "gsap_quote_pop",
        "lottie_role": "quote_spark",
        "lottie_keywords": ["quote", "highlight", "editorial"],
    },
    "article_image": {
        "framework": "hyperframes",
        "animation": "gsap_document_zoom",
        "lottie_role": "magnifier_accent",
        "lottie_keywords": ["document", "magnifier", "research", "news"],
    },
    "news_or_document": {
        "framework": "hyperframes",
        "animation": "gsap_document_zoom",
        "lottie_role": "document_scan",
        "lottie_keywords": ["document", "news", "report", "scan"],
    },
    "transition": {
        "framework": "hyperframes",
        "animation": "gsap_fast_cut",
        "lottie_role": "transition_accent",
        "lottie_keywords": ["transition", "glitch", "wipe", "energy"],
    },
    "closing_outro": {
        "framework": "hyperframes",
        "animation": "gsap_logo_outro",
        "lottie_role": "brand_outro",
        "lottie_keywords": ["logo reveal", "subscribe", "end card"],
    },
    "brand_mark": {
        "framework": "hyperframes",
        "animation": "gsap_logo_outro",
        "lottie_role": "brand_outro",
        "lottie_keywords": ["logo reveal", "subscribe", "end card"],
    },
}


def motion_policy_for_part(part: str) -> dict[str, Any]:
    default = {
        "framework": "hyperframes",
        "animation": "gsap_fade_rise",
        "lottie_role": "optional_ambient",
        "lottie_keywords": ["abstract", "motion graphics"],
    }
    policy = {**default, **MOTION_POLICY_BY_PART.get(part, {})}
    policy["lottie_allowed"] = True
    policy["lottie_required"] = False
    policy["gsap_required"] = True
    return policy


def evidence_authenticity_for_part(part: str, variables: dict[str, Any] | None = None) -> str | None:
    variables = variables or {}
    if part in {"article_image", "news_or_document", "source_citation"}:
        return "source_screenshot"
    if part in {"data_chart", "financial_chart", "data_table", "kpi_card"}:
        return "real_data" if variables.get("verified") is True else "user_claim_card"
    if part in {"logic_chain", "overall_outline"}:
        return "schematic"
    return None


class QuoteParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._capture = False
        self._buf: list[str] = []
        self.quotes: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"strong", "b", "blockquote"}:
            self._capture = True
            self._buf = []

    def handle_endtag(self, tag: str) -> None:
        if tag in {"strong", "b", "blockquote"} and self._capture:
            text = clean_text("".join(self._buf))
            if 12 <= len(text) <= 120:
                self.quotes.append(text)
            self._capture = False
            self._buf = []

    def handle_data(self, data: str) -> None:
        if self._capture:
            self._buf.append(data)


def clean_text(text: str) -> str:
    text = html.unescape(text)
    text = re.sub(r"\s+", " ", text)
    return text.strip(" 。\n\t")


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def router_entry(router: dict[str, Any], part: str) -> dict[str, Any]:
    entry = (router.get("part_router") or {}).get(part) or {}
    return {
        "content_part": part,
        "template_id": entry.get("primary"),
        "alternates": entry.get("alternates") or [],
        "reason": (entry.get("candidates") or [{}])[0].get("reason", ""),
    }


def estimate_duration(text: str, *, min_sec: float = 2.5, max_sec: float = 14.0, cps: float = 5.2) -> float:
    return round(max(min_sec, min(max_sec, len(clean_text(text)) / cps)), 3)


def extract_quotes(article_html: Path, limit: int = 8) -> list[str]:
    parser = QuoteParser()
    parser.feed(article_html.read_text(encoding="utf-8", errors="ignore"))
    seen = set()
    out = []
    for quote in parser.quotes:
        key = re.sub(r"\W+", "", quote)
        if key in seen:
            continue
        seen.add(key)
        out.append(quote)
        if len(out) >= limit:
            break
    return out


def classify_section_part(scene: dict[str, Any]) -> str:
    title = str(scene.get("title") or "")
    narration = str(scene.get("narration") or "")
    blob = title + " " + narration
    if re.search(r"为什么|怎么|链|传导|结构|逻辑|三把刀|原因|真相", blob):
        return "logic_chain"
    if re.search(r"风险|暴跌|爆破|加息|流动性|黑洞|冲击|危机|踩踏", blob):
        return "warning_or_risk"
    if NUMBER_RE.search(blob):
        return "financial_chart"
    return "chapter_divider"


def extract_numeric_metrics(text: str, limit: int = 6) -> list[dict[str, str]]:
    metrics: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    cleaned = clean_text(text)
    for match in VALUE_RE.finditer(cleaned):
        value = clean_text(match.group(0)).replace(" ", "")
        prefix = cleaned[max(0, match.start() - 22) : match.start()]
        label = re.split(r"[，。；、：:！!？?\s]+", prefix)[-1]
        label = clean_text(label).strip("，。；：:、 ")
        if not label or not value:
            continue
        if label[-1:].isdigit() and value[:1].isdigit():
            continue
        item = (label, value)
        if item in seen:
            continue
        seen.add(item)
        metrics.append({"label": label[-12:], "display": value})
        if len(metrics) >= limit:
            break
    return metrics


def should_keep_transition(previous_part: str, next_scene: dict[str, Any], timeline_length: int) -> bool:
    title = str(next_scene.get("title") or "")
    scene_type = str(next_scene.get("type") or "")
    if scene_type in {"table", "image", "outro"}:
        return False
    if previous_part in {"article_title", "opening_hook"}:
        return False
    if re.search(r"壹|贰|叁|第一|第二|第三|回到正题|结论", title):
        return True
    return timeline_length > 0 and timeline_length % 10 == 0


def should_add_companion_chart(table: list[list[str]]) -> bool:
    if len(table) < 3:
        return False
    numeric_rows = 0
    for row in table[1:8]:
        if len(row) > 1 and VALUE_RE.search(" ".join(row[1:])):
            numeric_rows += 1
    return numeric_rows >= 3


def beat_class_for_part(part: str, text: str, *, source_scene: dict[str, Any] | None, index: int) -> str:
    explicit = {
        "article_title": "hook",
        "opening_hook": "hook",
        "overall_outline": "logic_chain",
        "chapter_divider": "chapter",
        "logic_chain": "logic_chain",
        "data_chart": "evidence_data",
        "financial_chart": "evidence_data",
        "data_table": "evidence_data",
        "article_image": "evidence_document",
        "news_or_document": "evidence_document",
        "warning_or_risk": "objection",
        "quote": "claim",
        "pull_quote": "claim",
        "transition": "chapter",
        "closing_outro": "recap",
        "brand_mark": "recap",
    }.get(part)
    if explicit:
        return explicit
    if source_scene and source_scene.get("beat_class"):
        return str(source_scene["beat_class"])
    return classify_beat(text, index=index)


def make_scene(
    *,
    scene_id: str,
    source_scene_id: str | None,
    part: str,
    title: str,
    narration: str,
    router: dict[str, Any],
    min_sec: float = 2.5,
    max_sec: float = 14.0,
    variables: dict[str, Any] | None = None,
    source_scene: dict[str, Any] | None = None,
    index: int = 1,
    rules: dict[str, Any] | None = None,
) -> dict[str, Any]:
    match = router_entry(router, part)
    duration = estimate_duration(narration or title, min_sec=min_sec, max_sec=max_sec)
    beat_text = f"{title}。{narration or title}"
    preserve_source_driver = bool(source_scene and source_scene.get("content_part") == part)
    beat_class = beat_class_for_part(part, beat_text, source_scene=source_scene, index=index)
    driver_scores = (
        source_scene.get("driver_scores")
        if preserve_source_driver and isinstance(source_scene.get("driver_scores"), dict)
        else score_driver(
            beat_text,
            beat_class=beat_class,
            duration=duration,
            index=index,
            lane="explainer",
        )
    )
    director_state = (
        source_scene.get("director_state")
        if preserve_source_driver and source_scene.get("director_state")
        else explainer_state_for_beat(beat_class, index=index, seconds_since_evidence=0.0)
    )
    scene_variables = variables or {}
    return {
        "id": scene_id,
        "source_scene_id": source_scene_id,
        "beat_class": beat_class,
        "director_state": director_state,
        "driver_scores": driver_scores,
        "driver_score": source_scene.get("driver_score") if preserve_source_driver and source_scene.get("driver_score") is not None else weighted_driver_score(driver_scores, rules),
        "content_part": part,
        "template_id": match["template_id"],
        "template_match": match,
        "title": clean_text(title),
        "narration": clean_text(narration or title),
        "duration_sec": duration,
        "timing": {
            "char_count": len(clean_text(narration or title)),
            "target_cps": 5.2,
            "estimated_speech_sec": duration,
        },
        "motion_policy": motion_policy_for_part(part),
        "transition_to_next": source_scene.get("transition_to_next") if preserve_source_driver and source_scene.get("transition_to_next") else transition_for_beat(beat_class, lane="explainer", duration=duration),
        "audio": source_scene.get("audio") if preserve_source_driver and source_scene.get("audio") else audio_for_beat(beat_class),
        "source_motion": source_scene.get("motion") if source_scene else None,
        "variables": scene_variables,
        "evidence_authenticity": evidence_authenticity_for_part(part, scene_variables),
    }


def build_timeline(storyboard: dict[str, Any], router: dict[str, Any], article_html: Path) -> dict[str, Any]:
    rules = load_driver_rules()
    scenes = storyboard.get("scenes") or []
    source_by_id = {str(scene.get("id")): scene for scene in scenes if isinstance(scene, dict)}
    quotes = extract_quotes(article_html)
    timeline: list[dict[str, Any]] = []

    def add(part: str, title: str, narration: str, source_id: str | None = None, **kwargs: Any) -> None:
        source_scene = source_by_id.get(str(source_id)) if source_id else None
        timeline.append(
            make_scene(
                scene_id=f"html_scene_{len(timeline) + 1:03d}",
                source_scene_id=source_id,
                part=part,
                title=title,
                narration=narration,
                router=router,
                source_scene=source_scene,
                index=len(timeline) + 1,
                rules=rules,
                **kwargs,
            )
        )

    title = storyboard.get("title") or (scenes[0].get("title") if scenes else "未命名视频")
    add("article_title", str(title), f"{title}。先把结论摆出来。", None, min_sec=3.0, max_sec=6.0)
    add("opening_hook", str(title), scenes[0].get("narration", str(title)) if scenes else str(title), None, min_sec=3.0, max_sec=7.0)

    headings = [scene.get("title", "") for scene in scenes if scene.get("type") == "section"][:7]
    add(
        "overall_outline",
        "今天这条线怎么走",
        "这期沿着四层推进：先看事件与核心判断，再拆商业模式和产业结构，然后验证数据与风险，最后回到结论和行动条件。",
        None,
        min_sec=5.0,
        max_sec=9.0,
        variables={"headings": headings},
    )

    quote_cursor = 0
    transition_count = 0
    section_counter = 0
    for scene in scenes:
        source_id = scene.get("id")
        scene_type = scene.get("type")
        scene_title = str(scene.get("title") or "")
        narration = str(scene.get("narration") or scene_title)
        if scene_type == "hook":
            continue
        if scene_type == "outro":
            continue
        if scene_type == "table":
            add("data_table", scene_title, narration, source_id, min_sec=4.0, max_sec=8.0, variables=scene.get("variables") or {})
            table = (scene.get("variables") or {}).get("table") or []
            if should_add_companion_chart(table):
                add("data_chart", scene_title + " 图表化", "把这组表格转成可读的数据图表，用来支撑刚才的判断。", source_id, min_sec=4.0, max_sec=7.0, variables=scene.get("variables") or {})
            continue
        if scene_type == "image":
            add("article_image", scene_title, narration, source_id, min_sec=4.0, max_sec=8.0, variables=scene.get("variables") or {})
            continue

        section_counter += 1
        if section_counter == 1 or (section_counter - 1) % 4 == 0:
            add("chapter_divider", scene_title, scene_title, source_id, min_sec=2.5, max_sec=4.0)
        part = classify_section_part(scene)
        add(part, scene_title, narration, source_id, min_sec=6.0, max_sec=14.0, variables=scene.get("variables") or {})
        metrics = extract_numeric_metrics(f"{scene_title}。{narration}")
        if metrics:
            metric_text = "；".join(f"{item['label']} {item['display']}" for item in metrics[:4])
            add(
                "financial_chart",
                scene_title + "：关键数字",
                f"这里不靠情绪，直接看这组数字：{metric_text}。",
                source_id,
                min_sec=4.0,
                max_sec=6.0,
                variables={"metrics": metrics, "source": "from_article_section"},
            )
        if quote_cursor < len(quotes) and len(timeline) % 4 == 0:
            quote = quotes[quote_cursor]
            quote_cursor += 1
            add("pull_quote", "关键判断", quote, source_id, min_sec=3.0, max_sec=6.0, variables={"quote": quote})
        if transition_count < 2 and should_keep_transition(part, scene, len(timeline)):
            transition_count += 1
            add("transition", f"转场 {transition_count}", "进入下一层判断。", source_id, min_sec=1.2, max_sec=1.8)

    outro = next((scene for scene in scenes if scene.get("type") == "outro"), None)
    if outro:
        add("closing_outro", str(outro.get("title") or "结论"), str(outro.get("narration") or "结论"), outro.get("id"), min_sec=3.0, max_sec=7.0)
    add("brand_mark", "Newma 财经", "关注我，下一期继续拆市场里的信号和噪音。", None, min_sec=3.0, max_sec=5.0)

    target_duration = float(storyboard.get("duration_estimate_sec") or 0.0)
    raw_duration = sum(float(item["duration_sec"]) for item in timeline)
    if target_duration > 0 and raw_duration > target_duration:
        scale = target_duration / raw_duration
        for item in timeline:
            item["duration_sec"] = round(float(item["duration_sec"]) * scale, 3)

    cursor = 0.0
    for item in timeline:
        item["start_sec"] = round(cursor, 3)
        cursor += float(item["duration_sec"])
        item["end_sec"] = round(cursor, 3)

    return {
        "schema_version": "dasheng.html_anything_video_timeline.v1",
        "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "source_storyboard_schema": storyboard.get("schema_version"),
        "template_router_schema": router.get("schema_version"),
        "driver_rules_schema": rules.get("schema_version"),
        "title": title,
        "aspect": storyboard.get("aspect") or "9:16",
        "duration_estimate_sec": round(cursor, 3),
        "scene_count": len(timeline),
        "timeline": timeline,
        "render_policy": {
            "engine": "html-anything-template-parts + html-video/html renderer",
            "audio_master": "voiceover",
            "sync": "scene duration follows narration char count first, then template duration constraints",
            "transition_policy": "Transitions are metadata-first; standalone transition cards are rare chapter punctuation only.",
        },
    }


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build a video timeline routed to HTML Anything templates.")
    parser.add_argument("--storyboard", required=True)
    parser.add_argument("--article-html", required=True)
    parser.add_argument("--template-router", default=str(DEFAULT_ROUTER_PATH))
    parser.add_argument("--output", required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    storyboard = load_json(Path(args.storyboard).expanduser().resolve())
    router = load_json(Path(args.template_router).expanduser().resolve())
    article_html = Path(args.article_html).expanduser().resolve()
    timeline = build_timeline(storyboard, router, article_html)
    output = Path(args.output).expanduser().resolve()
    write_json(output, timeline)
    print(json.dumps({"status": "ok", "output": str(output), "scenes": timeline["scene_count"], "duration": timeline["duration_estimate_sec"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
