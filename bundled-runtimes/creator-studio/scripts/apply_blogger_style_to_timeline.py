#!/usr/bin/env python3
"""Apply a learned blogger style to a new Newma video timeline.

Example:
    python3 scripts/apply_blogger_style_to_timeline.py \
        --style-profile ~/Desktop/自媒体创作/00_范式学习/视频训练/xiaolin_finance_v1/style_profile.json \
        --storyboard ~/Desktop/自媒体创作/2026-06-24_xxx/04_转写/storyboard.json \
        --article-html ~/Desktop/自媒体创作/2026-06-24_xxx/03_初稿/article.html \
        --output-timeline ~/Desktop/自媒体创作/2026-06-24_xxx/04_转写/timeline_style.json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))
_SCRIPTS_DIR = _PROJECT_ROOT / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from canonical_workflow import ensure_runtime_output_dir  # noqa: E402
from scripts.build_html_anything_video_timeline import build_timeline  # noqa: E402
from scripts.video_driver_rules import audio_for_beat, transition_for_beat  # noqa: E402

DEFAULT_ROUTER_PATH = Path("configs/video/html_anything_template_router.json")


class StyleApplyError(RuntimeError):
    pass


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def resolve_aspect_from_style(style: dict[str, Any]) -> str:
    visual = style.get("visual_dna", {})
    return str(visual.get("aspect_ratio", "9:16"))


def override_scene_from_style(scene: dict[str, Any], style: dict[str, Any]) -> dict[str, Any]:
    """Patch a single scene with learned style preferences."""
    part = str(scene.get("content_part") or "")
    prefs = style.get("template_preferences", {})
    editing = style.get("editing_dna", {})
    part_pref = prefs.get(part)

    out = dict(scene)

    # Template override
    if part_pref:
        primary = part_pref.get("primary")
        if primary:
            out["template_id"] = primary
            out.setdefault("template_match", {})
            out["template_match"]["style_primary"] = primary
        alternates = part_pref.get("alternates") or []
        if alternates:
            out.setdefault("template_match", {})["style_alternates"] = alternates

        # Motion policy override
        motion = part_pref.get("motion_policy") or {}
        if motion:
            out["motion_policy"] = {**(out.get("motion_policy") or {}), **motion}
            out["motion_policy"]["style_applied"] = True

        # Duration guidance
        duration_range = part_pref.get("duration_range_sec")
        if isinstance(duration_range, (list, tuple)) and len(duration_range) == 2:
            lo, hi = duration_range
            out["duration_sec"] = clamp(float(out.get("duration_sec", lo)), float(lo), float(hi))
            # Recompute timing boundaries later

    # Transition override based on style signature and beat class
    beat = str(out.get("beat_class") or "")
    transitions = editing.get("transitions", {})
    if beat == "hook" and transitions.get("hook_transition"):
        out["transition_to_next"] = transitions["hook_transition"]
    elif beat == "chapter" and transitions.get("chapter_transition"):
        out["transition_to_next"] = transitions["chapter_transition"]
    elif beat == "recap" and transitions.get("recap_transition"):
        out["transition_to_next"] = transitions["recap_transition"]

    # Mark style-influenced fields
    out["style_source"] = style.get("style_id")
    return out


def build_talking_head_segments(timeline: list[dict[str, Any]], style: dict[str, Any]) -> list[dict[str, Any]]:
    """Generate placeholder segments for user's own talking-head footage."""
    policy = style.get("editing_dna", {}).get("talking_head_policy", {})
    if not policy.get("presence"):
        return []

    placement = policy.get("placement", "bottom_pip")
    segments: list[dict[str, Any]] = []

    # Place talking head at hook, first claim after evidence, and recap by default
    for scene in timeline:
        beat = str(scene.get("beat_class") or "")
        if beat in {"hook", "claim", "recap"}:
            segments.append(
                {
                    "scene_id": scene.get("id"),
                    "start_sec": scene.get("start_sec"),
                    "end_sec": scene.get("end_sec"),
                    "placement": placement,
                    "blank_placeholder": bool(policy.get("blank_placeholder", True)),
                    "notes": policy.get("notes", "留给用户自己的口播素材"),
                }
            )
    return segments


def apply_style_to_timeline(
    style: dict[str, Any],
    storyboard: dict[str, Any],
    article_html: Path,
    router_path: Path = DEFAULT_ROUTER_PATH,
) -> dict[str, Any]:
    if not router_path.exists():
        raise StyleApplyError(f"模板路由器不存在: {router_path}")
    router = load_json(router_path)

    baseline = build_timeline(storyboard, router, article_html)
    timeline = baseline.get("timeline") or []

    # Apply style per scene
    patched = [override_scene_from_style(scene, style) for scene in timeline]

    # Recompute timing because durations may have changed
    cursor = 0.0
    for scene in patched:
        scene["start_sec"] = round(cursor, 3)
        cursor += float(scene.get("duration_sec", 0))
        scene["end_sec"] = round(cursor, 3)

    # Build talking-head placeholder segments
    talking_head_segments = build_talking_head_segments(patched, style)

    # Assemble final style-driven timeline
    final: dict[str, Any] = {
        **baseline,
        "schema_version": "dasheng.html_anything_video_timeline.style_v1",
        "style_id": style.get("style_id"),
        "style_reference": style.get("reference_prompt", ""),
        "aspect": resolve_aspect_from_style(style),
        "timeline": patched,
        "talking_head_segments": talking_head_segments,
        "style_overrides": {
            "color_palette": style.get("visual_dna", {}).get("color_palette", {}),
            "typography": style.get("visual_dna", {}).get("typography", {}),
            "motion_signature": style.get("editing_dna", {}).get("motion_style", {}),
            "audio_mood": style.get("editing_dna", {}).get("audio_mood", {}),
        },
        "render_policy": {
            **(baseline.get("render_policy") or {}),
            "engine": "html-anything-template-parts + html-video/html renderer",
            "talking_head": "blank_placeholder_for_user_footage",
            "style_source": style.get("style_id"),
        },
    }
    final["duration_estimate_sec"] = round(cursor, 3)
    final["scene_count"] = len(patched)
    return final


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Apply learned blogger style to a Newma video timeline")
    parser.add_argument("--style-profile", required=True, help="style_profile.json 路径")
    parser.add_argument("--storyboard", required=True, help="stage3/4 生成的 storyboard.json")
    parser.add_argument("--article-html", required=True, help="对应文章 HTML 文件")
    parser.add_argument("--template-router", default=str(DEFAULT_ROUTER_PATH))
    parser.add_argument("--output-timeline", required=True, help="输出 timeline JSON 路径")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    style_path = Path(args.style_profile).expanduser().resolve()
    storyboard_path = Path(args.storyboard).expanduser().resolve()
    article_html_path = Path(args.article_html).expanduser().resolve()
    output_path = Path(args.output_timeline).expanduser().resolve()
    router_path = Path(args.template_router).expanduser().resolve()

    if not style_path.exists():
        raise StyleApplyError(f"风格文件不存在: {style_path}")
    if not storyboard_path.exists():
        raise StyleApplyError(f"storyboard 不存在: {storyboard_path}")
    if not article_html_path.exists():
        raise StyleApplyError(f"article html 不存在: {article_html_path}")
    ensure_runtime_output_dir(output_path.parent, label="style timeline output_dir")

    style = load_json(style_path)
    storyboard = load_json(storyboard_path)

    final_timeline = apply_style_to_timeline(style, storyboard, article_html_path, router_path)
    write_json(output_path, final_timeline)

    print(json.dumps(
        {
            "status": "ok",
            "style_id": style.get("style_id"),
            "output": str(output_path),
            "scenes": final_timeline["scene_count"],
            "duration_sec": final_timeline["duration_estimate_sec"],
            "talking_head_segments": len(final_timeline.get("talking_head_segments", [])),
        },
        ensure_ascii=False,
        indent=2,
    ))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
