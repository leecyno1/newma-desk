#!/usr/bin/env python3
"""Build a governed commercial script and scene-plan package."""

from __future__ import annotations

import argparse
import html
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from video_director_tool_router import apply_routes_to_scene_plan  # noqa: E402
from video_pipeline_governance import validate_artifact  # noqa: E402
from video_scene_plan_quality_gate import audit_scene_plan  # noqa: E402


LANE = "commercial_promo_video"
MODES = {"brand_film", "product_promo", "launch_trailer", "performance_ad"}
ASPECTS = {"9:16", "16:9", "1:1", "4:5"}

ROLE_WEIGHTS = {
    "hook": 1.2,
    "audience_pain": 1.2,
    "product_promise": 1.4,
    "feature_benefit": 1.6,
    "proof": 1.4,
    "offer": 1.0,
    "brand_memory": 0.9,
    "cta": 1.0,
}

ROLE_TITLES = {
    "hook": "开场钩子",
    "audience_pain": "目标用户痛点",
    "product_promise": "产品承诺",
    "feature_benefit": "卖点与收益",
    "proof": "结果与证明",
    "offer": "Offer",
    "brand_memory": "品牌记忆",
    "cta": "行动指令",
}

ROLE_TEMPLATES = {
    "hook": "frame-liquid-bg-hero",
    "audience_pain": "frame-light-leak-cinema",
    "product_promise": "frame-product-promo",
    "feature_benefit": "frame-product-promo-30s",
    "proof": "frame-data-rollup",
    "offer": "frame-bold-signal",
    "brand_memory": "frame-logo-outro",
    "cta": "frame-logo-outro",
}

ROLE_MOTION = {
    "hook": "hero_result_reveal_with_brand_color_hit",
    "audience_pain": "problem_moment_then_friction_labels_lock",
    "product_promise": "product_enters_then_single_promise_resolves",
    "feature_benefit": "real_product_action_then_benefit_callout",
    "proof": "proof_asset_enters_then_metric_or_quote_highlight",
    "offer": "offer_terms_stack_then_primary_value_locks",
    "brand_memory": "logo_or_brand_device_reassembles_from_product_elements",
    "cta": "single_cta_enters_then_holds_with_legal_copy",
}


def read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Commercial brief must be a JSON object.")
    return payload


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def text_item(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        text = str(value.get("text") or "").strip()
        return {
            "text": text,
            "on_screen": str(value.get("on_screen") or text).strip(),
            "evidence_refs": [str(item) for item in value.get("evidence_refs") or [] if item],
        }
    text = str(value or "").strip()
    return {"text": text, "on_screen": text, "evidence_refs": []}


def list_items(value: Any) -> list[dict[str, Any]]:
    values = value if isinstance(value, list) else [value]
    return [item for item in (text_item(raw) for raw in values) if item["text"]]


def short_copy(value: str, limit: int = 18) -> str:
    collapsed = " ".join(value.split())
    return collapsed if len(collapsed) <= limit else collapsed[: limit - 1] + "…"


def normalize_brief(payload: dict[str, Any]) -> dict[str, Any]:
    source = payload.get("campaign") if isinstance(payload.get("campaign"), dict) else payload
    merged = {**payload, **source}
    mode = str(merged.get("mode") or "product_promo")
    if mode not in MODES:
        raise ValueError(f"Unsupported commercial mode: {mode}")
    aspect = str(merged.get("aspect") or "9:16")
    if aspect not in ASPECTS:
        raise ValueError(f"Unsupported aspect: {aspect}")

    brief = {
        "title": str(merged.get("title") or "").strip(),
        "mode": mode,
        "brand": str(merged.get("brand") or "").strip(),
        "product": str(merged.get("product") or "").strip(),
        "audience": str(merged.get("audience") or "").strip(),
        "objective": str(merged.get("objective") or "").strip(),
        "duration_sec": float(merged.get("duration_sec") or 30),
        "aspect": aspect,
        "hook": text_item(merged.get("hook")),
        "pain": text_item(merged.get("pain")),
        "promise": text_item(merged.get("promise")),
        "benefits": list_items(merged.get("benefits")),
        "proof": list_items(merged.get("proof")),
        "offer": text_item(merged.get("offer")),
        "brand_memory": text_item(merged.get("brand_memory")),
        "cta": text_item(merged.get("cta")),
        "disclaimer": str(merged.get("disclaimer") or "").strip(),
        "brand_tokens": merged.get("brand_tokens") or {},
        "brand_assets": merged.get("brand_assets") or {},
        "product_assets": merged.get("product_assets") or [],
        "source_materials": merged.get("source_materials") or [],
        "voice": merged.get("voice") or {"provider": "minimax", "speed": 1.0},
        "platforms": merged.get("platforms") or [],
        "allow_generated_brand_visuals": bool(merged.get("allow_generated_brand_visuals", False)),
    }

    required_text = ["title", "brand", "product", "audience", "objective"]
    missing = [key for key in required_text if not brief[key]]
    for key in ["hook", "promise", "brand_memory", "cta"]:
        if not brief[key]["text"]:
            missing.append(key)
    if mode != "brand_film" and not brief["pain"]["text"]:
        missing.append("pain")
    if not brief["benefits"]:
        missing.append("benefits")
    if not brief["proof"]:
        missing.append("proof")
    if not brief["brand_tokens"]:
        missing.append("brand_tokens")
    if missing:
        raise ValueError("Commercial brief missing: " + ", ".join(sorted(set(missing))))
    if brief["duration_sec"] < 6 or brief["duration_sec"] > 120:
        raise ValueError("duration_sec must be between 6 and 120 seconds")
    return brief


def build_beats(brief: dict[str, Any]) -> list[dict[str, Any]]:
    duration = brief["duration_sec"]
    benefit_limit = 1 if duration <= 15 else 2 if duration <= 30 else 3
    proof_limit = 1 if duration <= 30 else 2
    beats: list[dict[str, Any]] = [{"role": "hook", **brief["hook"]}]
    if brief["pain"]["text"]:
        beats.append({"role": "audience_pain", **brief["pain"]})
    beats.append({"role": "product_promise", **brief["promise"]})
    beats.extend({"role": "feature_benefit", **item} for item in brief["benefits"][:benefit_limit])
    beats.extend({"role": "proof", **item} for item in brief["proof"][:proof_limit])
    if brief["offer"]["text"]:
        beats.append({"role": "offer", **brief["offer"]})
    beats.extend(
        [
            {"role": "brand_memory", **brief["brand_memory"]},
            {"role": "cta", **brief["cta"]},
        ]
    )
    fixed_duration: dict[int, float] = {}
    fixed_ratio_caps = {
        "hook": (0.10, 3.0),
        "audience_pain": (0.10, 3.0),
        "offer": (0.10, 4.0),
        "brand_memory": (0.08, 3.0),
        "cta": (0.10, 4.0),
    }
    for index, beat in enumerate(beats):
        if beat["role"] in fixed_ratio_caps:
            ratio, cap = fixed_ratio_caps[beat["role"]]
            fixed_duration[index] = min(duration * ratio, cap)
    flexible_indexes = [index for index in range(len(beats)) if index not in fixed_duration]
    flexible_weight = sum(ROLE_WEIGHTS[beats[index]["role"]] for index in flexible_indexes)
    flexible_duration = max(0.0, duration - sum(fixed_duration.values()))
    cursor = 0.0
    for index, beat in enumerate(beats):
        if index == len(beats) - 1:
            end = duration
        else:
            allocated = fixed_duration.get(index)
            if allocated is None:
                allocated = flexible_duration * ROLE_WEIGHTS[beat["role"]] / flexible_weight
            end = cursor + allocated
        beat["start_sec"] = round(cursor, 3)
        beat["end_sec"] = round(end, 3)
        beat["duration_sec"] = round(end - cursor, 3)
        cursor = end
    return beats


def build_script(brief: dict[str, Any], beats: list[dict[str, Any]]) -> dict[str, Any]:
    segments = []
    for index, beat in enumerate(beats, 1):
        segments.append(
            {
                "id": f"seg_{index:02d}",
                "text": beat["text"],
                "beat_class": beat["role"],
                "narrative_role": ROLE_TITLES[beat["role"]],
                "start_sec": beat["start_sec"],
                "end_sec": beat["end_sec"],
                "evidence_refs": beat["evidence_refs"],
                "on_screen_copy": short_copy(beat["on_screen"]),
                "legal_copy": brief["disclaimer"] if beat["role"] == "cta" else "",
            }
        )
    return {
        "schema_version": "dasheng.video.script.v1",
        "title": brief["title"],
        "lane": LANE,
        "commercial": {
            "mode": brief["mode"],
            "brand": brief["brand"],
            "product": brief["product"],
            "audience": brief["audience"],
            "objective": brief["objective"],
            "duration_sec": brief["duration_sec"],
            "aspect": brief["aspect"],
            "cta": brief["cta"]["text"],
            "offer": brief["offer"]["text"],
            "disclaimer": brief["disclaimer"],
        },
        "core_claims": [brief["promise"]["text"], *[item["text"] for item in brief["benefits"]], *[item["text"] for item in brief["proof"]]],
        "retention_plan": {
            "hook_deadline_sec": min(3, brief["duration_sec"] * 0.2),
            "product_reveal_role": "product_promise",
            "proof_before_cta": True,
        },
        "voice": brief["voice"],
        "segments": segments,
    }


def scene_route(role: str, brief: dict[str, Any]) -> str:
    if role in {"product_promise", "feature_benefit"}:
        return "commercial_product_capture" if brief["product_assets"] else "commercial_motion_graphics"
    if role == "proof":
        return "real_evidence_remotion"
    if role in {"hook", "audience_pain"} and brief["allow_generated_brand_visuals"]:
        return "commercial_generated_shot"
    return "commercial_motion_graphics"


def composition_for(role: str, index: int) -> tuple[str, str, str, str]:
    if role == "hook":
        return "hidden", "broll_fullscreen", "none", "broll-fullscreen"
    if role == "audience_pain":
        return "hidden", "split_screen", "none", "split-comparison"
    if role in {"product_promise", "feature_benefit"}:
        pip = "phone_mockup" if index % 2 else "rounded_rect"
        return "hidden", "evidence_fullscreen", pip, "product-ui"
    if role == "proof":
        return "hidden", "document_fullscreen", "none", "evidence-table"
    if role == "offer":
        return "hidden", "split_screen", "rounded_rect", "split-comparison"
    return "hidden", "transparent_overlay", "none", "recap-outro"


def safe_area_slots_for(role: str, *, product_visible: bool, brand_visible: bool, disclaimer: str) -> dict[str, str]:
    slots = {"subtitle": "bottom_caption"}
    if product_visible:
        slots["product"] = "center_content"
    if brand_visible:
        slots["logo"] = "top_brand"
    if role == "offer":
        slots["offer"] = "upper_offer"
    if role == "cta":
        slots["cta"] = "center_action"
        if disclaimer:
            slots["legal_copy"] = "bottom_legal"
    return slots


def build_scene_plan(brief: dict[str, Any], beats: list[dict[str, Any]]) -> dict[str, Any]:
    scenes = []
    for index, beat in enumerate(beats, 1):
        role = beat["role"]
        speaker_state, material_state, pip_shape, family = composition_for(role, index)
        product_visible = role in {"product_promise", "feature_benefit", "proof", "offer"}
        brand_visible = role in {"hook", "brand_memory", "cta"}
        scenes.append(
            {
                "id": f"scene_{index:02d}",
                "title": ROLE_TITLES[role],
                "start_sec": beat["start_sec"],
                "end_sec": beat["end_sec"],
                "duration_sec": beat["duration_sec"],
                "beat_class": role,
                "narration": beat["text"],
                "narration_tts": beat["text"],
                "on_screen_copy": short_copy(beat["on_screen"]),
                "evidence_refs": beat["evidence_refs"],
                "evidence_authenticity": "real_data" if role == "proof" else "brand_asset" if role in {"product_promise", "feature_benefit", "brand_memory", "cta"} else "schematic",
                "production_route": scene_route(role, brief),
                "template_id": ROLE_TEMPLATES[role],
                "preferred_renderer_family": family,
                "speaker_state": speaker_state,
                "material_state": material_state,
                "pip_shape": pip_shape,
                "html_animation_behavior": ROLE_MOTION[role],
                "transition_to_next": "brand_match_cut" if role not in {"brand_memory", "cta"} else "logo_shared_element",
                "product_visibility": product_visible,
                "brand_visibility": brand_visible,
                "cta": brief["cta"]["text"] if role == "cta" else "",
                "legal_copy": brief["disclaimer"] if role == "cta" else "",
                "safe_area_slots": safe_area_slots_for(
                    role,
                    product_visible=product_visible,
                    brand_visible=brand_visible,
                    disclaimer=brief["disclaimer"],
                ),
                "safe_area_status": "planned_no_collision",
                "motion": {"engine": "hyperframes_or_remotion", "brand_tokens": brief["brand_tokens"]},
                "visual": {
                    "brand": brief["brand"],
                    "product": brief["product"],
                    "product_assets": brief["product_assets"],
                    "brand_assets": brief["brand_assets"],
                },
            }
        )
    return {
        "schema_version": "dasheng.video.scene_plan.v1",
        "lane": LANE,
        "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "title": brief["title"],
        "aspect": brief["aspect"],
        "duration_estimate_sec": brief["duration_sec"],
        "commercial": {
            "mode": brief["mode"],
            "brand": brief["brand"],
            "product": brief["product"],
            "audience": brief["audience"],
            "objective": brief["objective"],
            "cta": brief["cta"]["text"],
            "offer": brief["offer"]["text"],
            "disclaimer": brief["disclaimer"],
            "brand_tokens": brief["brand_tokens"],
        },
        "visual_rhythm_policy": {
            "minimum_strong_visual_changes_per_minute": 12,
            "product_reveal_deadline_sec": min(8, brief["duration_sec"] * 0.35),
        },
        "safe_area_policy": {
            "status": "planned_no_collision",
            "reserved_regions": ["top_brand", "upper_offer", "center_content", "center_action", "bottom_caption", "bottom_legal"],
            "validate_all_aspects": [brief["aspect"], "16:9", "1:1", "4:5"],
        },
        "scenes": scenes,
    }


def build_review_html(brief: dict[str, Any], scene_plan: dict[str, Any]) -> str:
    rows = []
    for scene in scene_plan["scenes"]:
        rows.append(
            "<tr>"
            f"<td>{html.escape(scene['id'])}</td>"
            f"<td>{scene['start_sec']:.1f}-{scene['end_sec']:.1f}s</td>"
            f"<td>{html.escape(scene['beat_class'])}</td>"
            f"<td>{html.escape(scene['narration'])}</td>"
            f"<td>{html.escape(scene['on_screen_copy'])}</td>"
            f"<td>{html.escape(scene['production_route'])}</td>"
            f"<td>{html.escape(scene['template_id'])}</td>"
            f"<td>{html.escape(', '.join(scene.get('evidence_refs') or []) or '—')}</td>"
            "<td>□ 通过　□ 修改</td>"
            "</tr>"
        )
    return f"""<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><title>{html.escape(brief['title'])}｜广告分镜审核</title>
<style>body{{font:14px/1.5 -apple-system,BlinkMacSystemFont,'PingFang SC',sans-serif;margin:28px;color:#181818}}h1{{margin-bottom:8px}}p{{color:#666}}table{{border-collapse:collapse;width:100%}}th,td{{border:1px solid #ddd;padding:9px;vertical-align:top}}th{{background:#f4f1ea;position:sticky;top:0}}td:nth-child(4){{min-width:260px}}td:nth-child(5){{min-width:120px}}</style></head><body>
<h1>{html.escape(brief['title'])}</h1><p>{html.escape(brief['mode'])}｜{brief['duration_sec']:.0f}s｜{html.escape(brief['aspect'])}｜CTA：{html.escape(brief['cta']['text'])}</p>
<table><thead><tr><th>镜头</th><th>时间</th><th>职责</th><th>口播</th><th>屏幕文案</th><th>制作路线</th><th>模板</th><th>证据</th><th>审核</th></tr></thead><tbody>{''.join(rows)}</tbody></table></body></html>"""


def build_package(payload: dict[str, Any], output_dir: Path, *, route_tools: bool = True) -> dict[str, Path]:
    brief = normalize_brief(payload)
    beats = build_beats(brief)
    script = build_script(brief, beats)
    scene_plan = build_scene_plan(brief, beats)

    script_errors = validate_artifact("script", script)
    scene_errors = validate_artifact("scene_plan", scene_plan)
    if script_errors or scene_errors:
        raise ValueError(json.dumps({"script": script_errors, "scene_plan": scene_errors}, ensure_ascii=False))

    output_dir.mkdir(parents=True, exist_ok=True)
    brief_path = output_dir / "commercial_brief.normalized.json"
    script_path = output_dir / "script.json"
    scene_plan_path = output_dir / "scene_plan.json"
    routing_path = output_dir / "tool_routing_plan.json"
    quality_path = output_dir / "scene_plan_quality_gate.json"
    review_path = output_dir / "storyboard_template_review.html"
    brand_gate_path = output_dir / "brand_brief_gate.json"
    checkpoint_path = output_dir / "director_checkpoint.json"

    if route_tools:
        scene_plan, routing = apply_routes_to_scene_plan(scene_plan)
        write_json(routing_path, routing)
    write_json(brief_path, brief)
    write_json(script_path, script)
    write_json(scene_plan_path, scene_plan)
    write_json(quality_path, audit_scene_plan(scene_plan))
    review_path.write_text(build_review_html(brief, scene_plan), encoding="utf-8")
    write_json(
        brand_gate_path,
        {
            "schema_version": "dasheng.video.brand_brief_gate.v1",
            "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
            "status": "pending_review",
            "passed": False,
            "lane": LANE,
            "brand": brief["brand"],
            "product": brief["product"],
            "audience": brief["audience"],
            "objective": brief["objective"],
            "primary_cta": brief["cta"]["text"],
            "review_required": ["brand_system", "official_assets", "claims", "offer_validity", "rights"],
        },
    )
    write_json(
        checkpoint_path,
        {
            "schema_version": "dasheng.video.pipeline_checkpoint.v1",
            "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
            "pipeline_id": "commercial_promo",
            "lane": LANE,
            "stage": "scene_plan",
            "status": "pending_review",
            "checkpoint_required": True,
            "human_approval_default": True,
            "artifact_paths": {
                "script": str(script_path.resolve()),
                "scene_plan": str(scene_plan_path.resolve()),
                "review": str(review_path.resolve()),
                "brand_brief_gate": str(brand_gate_path.resolve()),
                **({"tool_routing_plan": str(routing_path.resolve())} if route_tools else {}),
            },
            "notes": "Approve brand, claims, product demonstration, brand memory and CTA before asset generation.",
        },
    )
    return {
        "brief": brief_path,
        "script": script_path,
        "scene_plan": scene_plan_path,
        "scene_plan_quality_gate": quality_path,
        "review_html": review_path,
        "brand_brief_gate": brand_gate_path,
        "checkpoint": checkpoint_path,
        **({"tool_routing_plan": routing_path} if route_tools else {}),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Build Newma commercial promo script and storyboard package.")
    parser.add_argument("--input", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--disable-tool-routing", action="store_true")
    args = parser.parse_args()
    outputs = build_package(
        read_json(Path(args.input).expanduser().resolve()),
        Path(args.output_dir).expanduser().resolve(),
        route_tools=not args.disable_tool_routing,
    )
    print(json.dumps({"status": "pending_review", "lane": LANE, "outputs": {key: str(path) for key, path in outputs.items()}}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
