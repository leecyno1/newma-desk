#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from validate_storyboard_review_gate import validate as validate_review_gate


DATA_PARTS = {"data_table", "financial_chart", "data_chart"}
IMAGE_PARTS = {"article_image", "news_or_document"}


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def asset_lookup(inventory: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {str(asset.get("id")): asset for asset in inventory.get("assets", []) if asset.get("id")}


def number_value(text: str, fallback: float) -> float:
    match = re.search(r"[-+]?\d+(?:\.\d+)?", str(text).replace(",", ""))
    if not match:
        return fallback
    try:
        return float(match.group(0))
    except ValueError:
        return fallback


def metrics_from_table(table: list[list[str]], limit: int = 6) -> list[dict[str, Any]]:
    metrics: list[dict[str, Any]] = []
    for idx, row in enumerate(table[1 : limit + 1], 1):
        if not row:
            continue
        label = str(row[0])[:12]
        display = ""
        for cell in row[1:]:
            if re.search(r"\d|%|万|亿|x|倍", str(cell), re.I):
                display = str(cell)
                break
        if not display and len(row) > 1:
            display = str(row[1])
        metrics.append({"label": label, "display": display, "value": number_value(display, idx * 10.0)})
    return metrics


def motion_policy_from_director(scene: dict[str, Any]) -> dict[str, Any]:
    motion = scene.get("motion") or {}
    content_part = str(scene.get("content_part") or "")
    animation = {
        "opening_hook": "gsap_glitch_punch",
        "chapter_divider": "gsap_cinematic_fade",
        "logic_chain": "gsap_path_draw",
        "overall_outline": "gsap_step_highlight",
        "data_table": "gsap_table_scan",
        "financial_chart": "gsap_market_bar_reveal",
        "data_chart": "gsap_chart_reveal",
        "warning_or_risk": "gsap_alert_stack",
        "pull_quote": "gsap_quote_pop",
        "closing_outro": "gsap_logo_outro",
    }.get(content_part, "gsap_fade_rise")
    return {
        "framework": "hyperframes",
        "animation": animation,
        "lottie_allowed": True,
        "lottie_required": False,
        "lottie_role": motion.get("lottie_role") or "optional_ambient",
        "lottie_keywords": [motion.get("lottie_role") or "finance motion", content_part],
        "fact_rule": "Lottie is decorative only; facts come from article variables.",
        "director_motion": motion,
    }


def build_variables(scene: dict[str, Any], assets: dict[str, dict[str, Any]]) -> dict[str, Any]:
    variables = dict(scene.get("variables") or {})
    evidence_refs = list(scene.get("evidence_refs") or [])
    variables["asset_refs"] = evidence_refs
    variables["evidence_refs"] = evidence_refs
    variables["core_meaning_lock"] = scene.get("core_meaning_lock")
    variables["visual_intent"] = scene.get("visual_intent")

    table_assets = [assets[ref] for ref in evidence_refs if ref in assets and assets[ref].get("type") == "table"]
    image_assets = [assets[ref] for ref in evidence_refs if ref in assets and assets[ref].get("type") == "image"]

    if table_assets:
        table = table_assets[0].get("rows") or []
        variables["table"] = table
        variables["tables"] = [
            {
                "id": asset.get("id"),
                "heading": asset.get("heading"),
                "summary": asset.get("summary"),
                "headers": asset.get("headers"),
                "rows": asset.get("rows"),
            }
            for asset in table_assets
        ]
        variables["metrics"] = metrics_from_table(table)

    if image_assets:
        image = image_assets[0]
        variables["src"] = image.get("local_copy") or image.get("original_src") or ""
        variables["alt"] = image.get("alt") or image.get("summary") or ""
        variables["images"] = [
            {
                "id": asset.get("id"),
                "src": asset.get("local_copy") or asset.get("original_src") or "",
                "alt": asset.get("alt") or asset.get("summary") or "",
            }
            for asset in image_assets
        ]

    return variables


def convert(storyboard: dict[str, Any], inventory: dict[str, Any], review_gate: dict[str, Any] | None = None) -> dict[str, Any]:
    assets = asset_lookup(inventory)
    timeline: list[dict[str, Any]] = []
    for idx, scene in enumerate(storyboard.get("scenes", []), 1):
        scene_id = scene.get("scene_id") or scene.get("id") or f"director_scene_{idx:03d}"
        narration = scene.get("voiceover_text") or scene.get("narration") or ""
        duration = float(scene.get("duration_sec") or 5)
        start = float(scene.get("start_sec") or 0)
        item = {
            "id": scene_id,
            "source_scene_id": scene_id,
            "beat_class": scene.get("beat_class"),
            "director_state": scene.get("director_state"),
            "driver_scores": scene.get("driver_scores"),
            "driver_score": scene.get("driver_score"),
            "content_part": scene.get("content_part"),
            "template_id": scene.get("template_id"),
            "template_match": scene.get("template_match"),
            "title": scene.get("title"),
            "narration": narration,
            "narration_tts": scene.get("narration_tts"),
            "duration_sec": duration,
            "start_sec": start,
            "end_sec": float(scene.get("end_sec") or start + duration),
            "timing": {
                "char_count": len(str(narration)),
                "target_cps": 5.2,
                "estimated_speech_sec": duration,
            },
            "motion_policy": motion_policy_from_director(scene),
            "transition_to_next": scene.get("transition_to_next"),
            "audio": scene.get("audio"),
            "variables": build_variables(scene, assets),
            "voice_audio": scene.get("voice_audio"),
            "provider_subtitles": scene.get("provider_subtitles"),
            "caption_cues": scene.get("caption_cues") or [],
            "audio_tail_sec": scene.get("audio_tail_sec"),
            "core_claim_id": scene.get("core_claim_id"),
            "core_claim_refs": scene.get("core_claim_refs") or [],
            "evidence_refs": scene.get("evidence_refs") or [],
            "main_visual": scene.get("main_visual"),
            "real_insert_plan": scene.get("real_insert_plan") or [],
            "emphasis_text": scene.get("emphasis_text"),
            "entity_labels": scene.get("entity_labels") or [],
            "interaction_or_retention": scene.get("interaction_or_retention") or [],
            "risk_notes": scene.get("risk_notes") or [],
            "qc_notes": scene.get("qc_notes") or [],
            "original_refs": scene.get("original_refs") or [],
        }
        timeline.append(item)

    return {
        "schema_version": "dasheng.html_anything_video_timeline.v1",
        "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "source_storyboard_schema": storyboard.get("schema_version"),
        "source_inventory_schema": inventory.get("schema_version"),
        "title": storyboard.get("title"),
        "aspect": storyboard.get("aspect") or (storyboard.get("format") or {}).get("aspect_ratio") or "16:9",
        "width": (storyboard.get("format") or {}).get("width", 1920),
        "height": (storyboard.get("format") or {}).get("height", 1080),
        "fps": (storyboard.get("format") or {}).get("fps", 30),
        "duration_estimate_sec": round(sum(float(item.get("duration_sec") or 0) for item in timeline), 3),
        "scene_count": len(timeline),
        "timeline": timeline,
        "render_policy": {
            "engine": "director_storyboard -> html-anything scene pack -> html-video/ffmpeg",
            "audio_master": "single MiniMax voiceover",
            "bgm": "MiniMax instrumental, ducked under narration after visual render",
            "subtitle_timing_source": (storyboard.get("timeline_alignment") or {}).get("subtitle_timing_source"),
        },
        "timeline_alignment": storyboard.get("timeline_alignment"),
        "voice": storyboard.get("voice"),
        "review_gate": review_gate
        or {
            "status": "missing",
            "render_allowed": False,
            "note": "No storyboard_review_decision.json was provided; production render must validate the review gate first.",
        },
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Convert Newma director storyboard into renderable video timeline.")
    parser.add_argument("--storyboard", required=True)
    parser.add_argument("--inventory", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--review-decision", default="", help="storyboard_review_decision.json exported from the review table.")
    parser.add_argument("--review-gate-report", default="", help="Optional path to write the gate validation report.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    storyboard_path = Path(args.storyboard).expanduser().resolve()
    storyboard = load_json(storyboard_path)
    inventory = load_json(Path(args.inventory).expanduser().resolve())
    output = Path(args.output).expanduser().resolve()
    review_gate = None
    if args.review_decision:
        decision_path = Path(args.review_decision).expanduser().resolve()
        review_gate = validate_review_gate(storyboard, load_json(decision_path))
        review_gate["paths"] = {"storyboard": str(storyboard_path), "decision": str(decision_path)}
        report_path = Path(args.review_gate_report).expanduser().resolve() if args.review_gate_report else output.with_suffix(".review_gate.json")
        write_json(report_path, review_gate)
        if review_gate["status"] != "approved":
            raise SystemExit(f"Storyboard review gate blocked: {report_path}")
    timeline = convert(storyboard, inventory, review_gate=review_gate)
    write_json(output, timeline)
    print(
        json.dumps(
            {
                "status": "ok",
                "output": str(output),
                "scenes": timeline["scene_count"],
                "duration": timeline["duration_estimate_sec"],
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
