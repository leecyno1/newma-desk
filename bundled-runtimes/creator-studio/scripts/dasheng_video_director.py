#!/usr/bin/env python3
"""Newma video director compatibility entrypoint.

This script turns article HTML or talking-head captions into a governed
scene_plan package before material generation/rendering.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from build_storyboard_template_review_table import build_html as build_review_html
from project_run_manifest import add_artifact, is_safe_output_root, load_manifest, save_manifest, set_stage_status, validate_manifest
from video_director_timeline import (
    build_talking_head_timeline,
    load_captions_json,
    load_srt,
    remap_captions_to_roughcut,
    run_ffprobe_duration,
)
from video_explainer_storyboard import build_explainer_storyboard, load_router, parse_html_article, write_preview_html
from video_pipeline_governance import build_checkpoint, load_pipeline, validate_artifact
from video_director_tool_router import apply_routes_to_scene_plan
from video_scene_plan_quality_gate import audit_scene_plan
from video_vox_storyboard import (
    apply_approved_storyboard,
    audit_vox_script,
    build_vox_script_artifact,
    build_vox_storyboard,
    build_vox_storyboard_review,
    vox_content_brief_markdown,
    vox_script_markdown,
    vox_storyboard_review_markdown,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
COMMERCIAL_PROMO_BUILDER = PROJECT_ROOT / "skills" / "dasheng-commercial-promo-video" / "scripts" / "build_commercial_promo_package.py"


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_commercial_promo_builder() -> Any:
    spec = importlib.util.spec_from_file_location("dasheng_commercial_promo_builder", COMMERCIAL_PROMO_BUILDER)
    if not spec or not spec.loader:
        raise RuntimeError(f"Cannot load commercial promo builder: {COMMERCIAL_PROMO_BUILDER}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def require_approved_storyboard_gate(gate_path: Path, storyboard_path: Path, scene_count: int) -> dict[str, Any]:
    gate = read_json(gate_path)
    if gate.get("status") != "approved" or gate.get("render_allowed") is not True:
        raise RuntimeError("Narrative storyboard gate is not approved.")
    approved_source = str((gate.get("paths") or {}).get("storyboard") or "")
    if not approved_source or Path(approved_source).expanduser().resolve() != storyboard_path.resolve():
        raise RuntimeError("Narrative storyboard gate does not point to this project's narrative_storyboard.json.")
    if int(gate.get("scene_count") or 0) != scene_count:
        raise RuntimeError("Narrative storyboard gate scene count does not match the reviewed storyboard.")
    return gate


def scene_end(scene: dict[str, Any]) -> float:
    if "end_sec" in scene:
        return float(scene["end_sec"])
    if "end" in scene:
        return float(scene["end"])
    start = float(scene.get("start_sec", scene.get("start", 0.0)) or 0.0)
    duration = float(scene.get("duration_sec", scene.get("duration", 0.0)) or 0.0)
    return start + duration


def motion_text(scene: dict[str, Any]) -> str:
    explicit = str(scene.get("html_animation_behavior") or "").strip()
    if explicit:
        return explicit
    motion = scene.get("motion") or {}
    if isinstance(motion, dict):
        parts = [str(motion.get(key) or "").strip() for key in ["entrance", "focus_change", "exit"]]
        return " -> ".join(part for part in parts if part)
    return str(motion or "").strip()


def normalize_explainer_scene_plan(storyboard: dict[str, Any]) -> dict[str, Any]:
    scenes: list[dict[str, Any]] = []
    for index, scene in enumerate(storyboard.get("scenes") or [], 1):
        start = float(scene.get("start_sec", 0.0) or 0.0)
        duration = float(scene.get("duration_sec", 0.0) or 0.0)
        evidence_refs: list[str] = []
        if scene.get("evidence_required"):
            evidence_refs.append(str((scene.get("variables") or {}).get("source") or scene.get("content_part") or "article_html"))
        scenes.append(
            {
                **scene,
                "id": str(scene.get("id") or f"scene_{index:03d}"),
                "title": str(scene.get("title") or f"分镜 {index}"),
                "start_sec": round(start, 3),
                "end_sec": round(scene_end(scene), 3),
                "duration_sec": round(duration, 3),
                "beat_class": str(scene.get("beat_class") or "claim"),
                "template_id": str(scene.get("template_id") or "deck-swiss-international"),
                "evidence_refs": scene.get("evidence_refs") or evidence_refs,
                "html_animation_behavior": motion_text(scene) or "live_html_motion_required",
                "risk_notes": scene.get("risk_notes")
                or [
                    "Verify template is rendered as live HTML motion, not a static screenshot.",
                    "Check subtitle and chart/table safe zones before render.",
                ],
            }
        )
    return {
        "schema_version": "dasheng.video.scene_plan.v1",
        "lane": "explainer_html_video",
        "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "title": storyboard.get("title") or "无真人科普视频",
        "source_storyboard_schema": storyboard.get("schema_version"),
        "source_html": storyboard.get("source_html"),
        "aspect": storyboard.get("aspect") or "9:16",
        "renderer": storyboard.get("renderer") or "html-video",
        "duration_estimate_sec": storyboard.get("duration_estimate_sec"),
        "director_state_machine": storyboard.get("director_state_machine"),
        "style": storyboard.get("style"),
        "scenes": scenes,
    }


def normalize_vox_scene_plan(storyboard: dict[str, Any]) -> dict[str, Any]:
    scene_plan = normalize_explainer_scene_plan(storyboard)
    scene_plan.update(
        {
            "lane": "vox_explainer_video",
            "title": storyboard.get("title") or "VOX 调查解释视频",
            "aspect": storyboard.get("aspect") or "16:9",
            "narrative_mode": storyboard.get("narrative_mode"),
            "central_question": storyboard.get("central_question"),
            "evidence_map": storyboard.get("evidence_map"),
            "research_contract": storyboard.get("research_contract"),
            "visual_bible": storyboard.get("visual_bible"),
        }
    )
    return scene_plan


def segment_index(segment: dict[str, Any]) -> int:
    raw = str(segment.get("id") or "")
    digits = "".join(ch for ch in raw if ch.isdigit())
    if digits:
        return max(1, int(digits))
    return 1


def pick_template(pool: list[str], index: int) -> str:
    if not pool:
        return "frame-electric-studio"
    return pool[(index - 1) % len(pool)]


def template_for_talking_head_shot(segment: dict[str, Any]) -> str:
    index = segment_index(segment)
    shot = str(segment.get("shot") or "")
    beat_class = str(segment.get("beat_class") or "")
    if shot == "chart_card":
        return pick_template(["frame-data-chart-nyt", "frame-nyt-graph", "frame-data-rollup", "frame-pentagram-stat"], index)
    if shot == "document_zoom":
        return pick_template(["doc-kami-parchment", "frame-macos-notification", "social-x-post-card", "article-magazine"], index)
    if shot == "html_logic_overlay":
        return pick_template(["frame-decision-tree", "frame-build-minimal", "frame-swiss-grid", "deck-blueprint"], index)
    if shot == "broll_with_pip":
        return pick_template(
            [
                "frame-light-leak-cinema",
                "frame-liquid-bg-hero",
                "frame-creative-voltage",
                "frame-takram-organic",
                "frame-warm-grain",
                "frame-product-promo",
                "deck-guizang-editorial",
                "deck-swiss-international",
            ],
            index,
        )
    if beat_class == "hook":
        return pick_template(["frame-glitch-title", "vfx-text-cursor", "frame-liquid-bg-hero"], index)
    if beat_class == "recap":
        return pick_template(["frame-logo-outro", "frame-bold-signal", "frame-bold-poster"], index)
    if shot in {"claim_closeup", "talking_head_punch_in"}:
        return pick_template(["frame-electric-studio", "frame-kinetic-type", "frame-bold-signal", "frame-play-mode"], index)
    return pick_template(["frame-electric-studio", "frame-kinetic-type", "frame-swiss-grid", "frame-vignelli", "frame-warm-grain"], index)


def evidence_authenticity_for_segment(segment: dict[str, Any]) -> str | None:
    overlay = segment.get("overlay") or {}
    overlay_type = str(overlay.get("type") or "")
    beat_class = str(segment.get("beat_class") or "")
    shot = str(segment.get("shot") or "")
    if overlay_type == "real_data_chart_or_table":
        return "real_data"
    if overlay_type == "source_document_or_news_card":
        return "source_screenshot"
    if overlay_type in {"logic_chain_overlay", "broll_or_html_sticker"}:
        return "schematic"
    if beat_class in {"evidence_data", "evidence_document"} or shot in {"chart_card", "document_zoom"}:
        return "user_claim_card"
    return None


def normalize_talking_head_scene_plan(timeline: dict[str, Any]) -> dict[str, Any]:
    scenes: list[dict[str, Any]] = []
    for index, segment in enumerate(timeline.get("segments") or [], 1):
        start = float(segment.get("start", 0.0) or 0.0)
        end = float(segment.get("end", start) or start)
        overlay = segment.get("overlay") or {}
        evidence_refs: list[str] = []
        if overlay.get("required"):
            evidence_refs.append(str(overlay.get("source_hint") or overlay.get("type") or "speaker_caption"))
        scenes.append(
            {
                "id": str(segment.get("id") or f"scene_{index:03d}"),
                "title": str(segment.get("caption") or f"口播分镜 {index}")[:42],
                "start_sec": round(start, 3),
                "end_sec": round(end, 3),
                "duration_sec": round(float(segment.get("duration", end - start) or end - start), 3),
                "beat_class": str(segment.get("beat_class") or "claim"),
                "template_id": template_for_talking_head_shot(segment),
                "content_part": str(overlay.get("type") or segment.get("shot") or "talking_head"),
                "narration": segment.get("caption"),
                "evidence_refs": evidence_refs,
                **({"evidence_authenticity": evidence_authenticity_for_segment(segment)} if evidence_authenticity_for_segment(segment) else {}),
                "speaker_state": segment.get("speaker_state"),
                "material_state": segment.get("material_state"),
                "pip_shape": segment.get("pip_shape"),
                "shot": segment.get("shot"),
                "driver_scores": segment.get("driver_scores"),
                "html_animation_behavior": segment.get("html_animation_behavior") or "live_overlay_motion_required",
                "transition_in": segment.get("transition_in"),
                "transition_out": segment.get("transition_out"),
                "transition_to_next": segment.get("transition_out") or segment.get("transition"),
                "audio": segment.get("audio"),
                "collision_policy": segment.get("collision_policy"),
                "risk_notes": [segment.get("qc_risk") or "Verify roughcut gate and subtitle sync before render."],
            }
        )
    return {
        "schema_version": "dasheng.video.scene_plan.v1",
        "lane": "talking_head_video",
        "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "title": timeline.get("title") or "真人口播视频",
        "source_timeline_schema": timeline.get("schema_version"),
        "source_video": timeline.get("source_video"),
        "duration_estimate_sec": timeline.get("duration_sec"),
        "aspect": timeline.get("aspect") or "9:16",
        "roughcut_gate": timeline.get("roughcut_gate"),
        "style_reference": timeline.get("style_reference"),
        "director_state_machine": timeline.get("director_state_machine"),
        "safe_areas": timeline.get("safe_areas"),
        "qc_targets": timeline.get("qc_targets"),
        "timeline_alignment": timeline.get("timeline_alignment"),
        "scenes": scenes,
    }


def register_outputs_to_project_manifest(project_manifest: Path, outputs: dict[str, Path], *, stage_status: str) -> None:
    manifest = load_manifest(project_manifest)
    set_stage_status(
        manifest,
        stage_name="scene_plan",
        status=stage_status,
        checkpoint_path=str(outputs.get("checkpoint", "")),
        review_path=str(outputs.get("review_html", "")),
    )
    for artifact_type, path in outputs.items():
        if path.exists():
            add_artifact(manifest, stage_name="scene_plan", artifact_type=artifact_type, path=str(path.resolve()))
    errors = validate_manifest(manifest)
    if errors:
        raise RuntimeError(f"project_run_manifest invalid: {json.dumps(errors, ensure_ascii=False)}")
    save_manifest(manifest, project_manifest)


def build_explainer_package(args: argparse.Namespace, output_dir: Path) -> dict[str, Path]:
    article_html = Path(args.article_html).expanduser().resolve()
    router = load_router(Path(args.template_router).expanduser().resolve() if args.template_router else None)
    storyboard = build_explainer_storyboard(
        parse_html_article(article_html),
        source_html=str(article_html),
        duration_target_sec=args.duration_target_sec,
        router=router,
    )
    raw_storyboard_path = output_dir / "explainer_storyboard.raw.json"
    scene_plan_path = output_dir / "scene_plan.json"
    quality_gate_path = output_dir / "scene_plan_quality_gate.json"
    preview_path = output_dir / "storyboard_preview.html"
    review_path = output_dir / "storyboard_template_review.html"
    checkpoint_path = output_dir / "director_checkpoint.json"
    routing_plan_path = output_dir / "tool_routing_plan.json"

    scene_plan = normalize_explainer_scene_plan(storyboard)
    disable_tool_routing = bool(getattr(args, "disable_tool_routing", False))
    if not disable_tool_routing:
        tool_registry = getattr(args, "tool_registry", str(PROJECT_ROOT / "configs/video/tool_registry.json"))
        project_registry = getattr(args, "project_registry", str(PROJECT_ROOT / "configs/external/reserved_projects.json"))
        scene_plan, routing_plan = apply_routes_to_scene_plan(
            scene_plan,
            tool_registry_path=Path(tool_registry).expanduser().resolve(),
            project_registry_path=Path(project_registry).expanduser().resolve(),
        )
        write_json(routing_plan_path, routing_plan)
    errors = validate_artifact("scene_plan", scene_plan)
    if errors:
        raise RuntimeError(f"scene_plan invalid: {json.dumps(errors, ensure_ascii=False)}")
    write_json(raw_storyboard_path, storyboard)
    write_json(scene_plan_path, scene_plan)
    write_json(quality_gate_path, audit_scene_plan(scene_plan))
    write_preview_html(preview_path, scene_plan)
    review_path.write_text(
        build_review_html(scene_plan, output=review_path, preview_roots=[Path(item).expanduser().resolve() for item in args.template_preview_root], source_storyboard=scene_plan_path),
        encoding="utf-8",
    )
    checkpoint = build_checkpoint(
        load_pipeline("explainer_html"),
        "scene_plan",
        artifact_paths={
            "scene_plan": str(scene_plan_path),
            "quality_gate": str(quality_gate_path),
            "review": str(review_path),
            **({"tool_routing_plan": str(routing_plan_path)} if not disable_tool_routing else {}),
        },
        status="pending_review",
        notes="Review storyboard_template_review.html before material generation.",
    )
    write_json(checkpoint_path, checkpoint)
    return {
        "raw_storyboard": raw_storyboard_path,
        "scene_plan": scene_plan_path,
        "scene_plan_quality_gate": quality_gate_path,
        "preview_html": preview_path,
        "review_html": review_path,
        "checkpoint": checkpoint_path,
        **({"tool_routing_plan": routing_plan_path} if not disable_tool_routing else {}),
    }


def build_vox_package(args: argparse.Namespace, output_dir: Path) -> dict[str, Path]:
    article_html = Path(args.article_html).expanduser().resolve()
    router = load_router(Path(args.template_router).expanduser().resolve() if args.template_router else None)
    article = parse_html_article(article_html)
    content_brief_path = output_dir / "video_content_brief.md"
    script_path = output_dir / "script.json"
    script_markdown_path = output_dir / "narration_script.rewritten.md"
    script_gate_path = output_dir / "script_rewrite_gate.json"
    narrative_storyboard_path = output_dir / "narrative_storyboard.json"
    storyboard_markdown_path = output_dir / "storyboard_review.md"
    review_path = output_dir / "storyboard_review.html"
    checkpoint_path = output_dir / "director_checkpoint.json"

    gate_arg = str(getattr(args, "storyboard_review_gate", "") or "").strip()
    if not gate_arg:
        review_storyboard = build_vox_storyboard(
            article,
            source_html=str(article_html),
            duration_target_sec=args.duration_target_sec,
            router=router,
            aspect="16:9",
            central_question=getattr(args, "central_question", None),
            include_production_shots=False,
        )
        script = build_vox_script_artifact(
            review_storyboard,
            creator_intro=getattr(args, "creator_intro", "这里是 Newma，我们用证据把答案一步步收窄。"),
        )
        script_errors = validate_artifact("script", script)
        if script_errors:
            raise RuntimeError(f"script invalid: {json.dumps(script_errors, ensure_ascii=False)}")
        script_gate = audit_vox_script(script)
        narrative_storyboard = build_vox_storyboard_review(review_storyboard, script)
        write_json(script_path, script)
        write_json(script_gate_path, script_gate)
        write_json(narrative_storyboard_path, narrative_storyboard)
        content_brief_path.write_text(vox_content_brief_markdown(review_storyboard), encoding="utf-8")
        script_markdown_path.write_text(vox_script_markdown(script), encoding="utf-8")
        storyboard_markdown_path.write_text(vox_storyboard_review_markdown(narrative_storyboard), encoding="utf-8")
        review_path.write_text(
            build_review_html(
                narrative_storyboard,
                output=review_path,
                preview_roots=[Path(item).expanduser().resolve() for item in args.template_preview_root],
                source_storyboard=narrative_storyboard_path,
            ),
            encoding="utf-8",
        )
        checkpoint = build_checkpoint(
            load_pipeline("vox_explainer"),
            "scene_plan",
            artifact_paths={
                "script": str(script_path),
                "script_rewrite_gate": str(script_gate_path),
                "review": str(review_path),
                "narrative_storyboard": str(narrative_storyboard_path),
            },
            status="pending_review" if script_gate["status"] == "pass" else "needs_revision",
            notes=(
                "Approve the rewritten narration and 10-25 second narrative storyboard before production-shot splitting."
                if script_gate["status"] == "pass"
                else "Revise the script until script_rewrite_gate.json passes before storyboard approval."
            ),
        )
        write_json(checkpoint_path, checkpoint)
        return {
            "video_content_brief": content_brief_path,
            "script": script_path,
            "narration_script": script_markdown_path,
            "script_rewrite_gate": script_gate_path,
            "narrative_storyboard": narrative_storyboard_path,
            "storyboard_markdown": storyboard_markdown_path,
            "review_html": review_path,
            "checkpoint": checkpoint_path,
        }

    required_preproduction = [script_path, script_gate_path, narrative_storyboard_path, review_path]
    missing = [str(path) for path in required_preproduction if not path.exists()]
    if missing:
        raise RuntimeError(f"Run the narrative review phase first; missing: {', '.join(missing)}")
    script = read_json(script_path)
    script_errors = validate_artifact("script", script)
    if script_errors:
        raise RuntimeError(f"script invalid: {json.dumps(script_errors, ensure_ascii=False)}")
    if read_json(script_gate_path).get("status") != "pass":
        raise RuntimeError("script_rewrite_gate.json is not pass.")
    narrative_storyboard = read_json(narrative_storyboard_path)
    source_html = str(narrative_storyboard.get("source_html") or "")
    if not source_html or Path(source_html).expanduser().resolve() != article_html:
        raise RuntimeError("The reviewed narrative storyboard belongs to a different article.")
    approved_gate_path = Path(gate_arg).expanduser().resolve()
    require_approved_storyboard_gate(
        approved_gate_path,
        narrative_storyboard_path,
        len(narrative_storyboard.get("scenes") or []),
    )

    storyboard = build_vox_storyboard(
        article,
        source_html=str(article_html),
        duration_target_sec=args.duration_target_sec,
        router=router,
        aspect="16:9",
        central_question=str(narrative_storyboard.get("central_question") or getattr(args, "central_question", None) or ""),
        include_production_shots=True,
    )
    storyboard = apply_approved_storyboard(storyboard, narrative_storyboard, approved_gate_path)
    raw_storyboard_path = output_dir / "vox_storyboard.raw.json"
    scene_plan_path = output_dir / "scene_plan.json"
    quality_gate_path = output_dir / "scene_plan_quality_gate.json"
    preview_path = output_dir / "storyboard_preview.html"
    routing_plan_path = output_dir / "tool_routing_plan.json"
    visual_bible_path = output_dir / "vox_visual_bible.json"

    scene_plan = normalize_vox_scene_plan(storyboard)
    disable_tool_routing = bool(getattr(args, "disable_tool_routing", False))
    if not disable_tool_routing:
        tool_registry = getattr(args, "tool_registry", str(PROJECT_ROOT / "configs/video/tool_registry.json"))
        project_registry = getattr(args, "project_registry", str(PROJECT_ROOT / "configs/external/reserved_projects.json"))
        scene_plan, routing_plan = apply_routes_to_scene_plan(
            scene_plan,
            tool_registry_path=Path(tool_registry).expanduser().resolve(),
            project_registry_path=Path(project_registry).expanduser().resolve(),
        )
        write_json(routing_plan_path, routing_plan)
    errors = validate_artifact("scene_plan", scene_plan)
    if errors:
        raise RuntimeError(f"scene_plan invalid: {json.dumps(errors, ensure_ascii=False)}")
    write_json(raw_storyboard_path, storyboard)
    write_json(scene_plan_path, scene_plan)
    write_json(visual_bible_path, storyboard.get("visual_bible") or {})
    quality_report = audit_scene_plan(scene_plan)
    write_json(quality_gate_path, quality_report)
    write_preview_html(preview_path, scene_plan)
    checkpoint = build_checkpoint(
        load_pipeline("vox_explainer"),
        "scene_plan",
        artifact_paths={
            "script": str(script_path),
            "script_rewrite_gate": str(script_gate_path),
            "narrative_storyboard": str(narrative_storyboard_path),
            "storyboard_review_gate": str(approved_gate_path),
            "scene_plan": str(scene_plan_path),
            "quality_gate": str(quality_gate_path),
            "review": str(review_path),
            "visual_bible": str(visual_bible_path),
            **({"tool_routing_plan": str(routing_plan_path)} if not disable_tool_routing else {}),
        },
        status="approved" if quality_report["status"] == "pass" else "needs_revision",
        notes=(
            "Narrative storyboard approved. Production shots, micro-beats, visual bible and tool routing are ready for reference-image production."
            if quality_report["status"] == "pass"
            else "Production scene plan failed scene_plan_quality_gate.json and must be revised before reference-image production."
        ),
    )
    write_json(checkpoint_path, checkpoint)
    return {
        "video_content_brief": content_brief_path,
        "script": script_path,
        "narration_script": script_markdown_path,
        "script_rewrite_gate": script_gate_path,
        "narrative_storyboard": narrative_storyboard_path,
        "storyboard_markdown": storyboard_markdown_path,
        "storyboard_review_gate": approved_gate_path,
        "raw_storyboard": raw_storyboard_path,
        "scene_plan": scene_plan_path,
        "scene_plan_quality_gate": quality_gate_path,
        "preview_html": preview_path,
        "review_html": review_path,
        "visual_bible": visual_bible_path,
        "checkpoint": checkpoint_path,
        **({"tool_routing_plan": routing_plan_path} if not disable_tool_routing else {}),
    }


def build_talking_head_package(
    args: argparse.Namespace,
    output_dir: Path,
    *,
    lane: str = "talking_head_video",
    pipeline_id: str = "talking_head",
) -> dict[str, Path]:
    if args.captions_json:
        captions = load_captions_json(Path(args.captions_json).expanduser().resolve())
    else:
        captions = load_srt(Path(args.srt).expanduser().resolve())
    timeline_alignment = None
    roughcut_edl = getattr(args, "roughcut_edl", "")
    if roughcut_edl:
        captions, timeline_alignment = remap_captions_to_roughcut(
            captions,
            Path(roughcut_edl).expanduser().resolve(),
        )
    source_video = str(Path(args.source_video).expanduser().resolve()) if args.source_video else None
    duration = args.duration
    if duration is None and source_video:
        duration = run_ffprobe_duration(Path(source_video))
    if duration is None and timeline_alignment:
        duration = float(timeline_alignment["output_duration_sec"])
    timeline = build_talking_head_timeline(
        captions,
        title=args.title,
        source_video=source_video,
        duration=duration,
        roughcut_gate=str(Path(args.roughcut_gate).expanduser().resolve()) if args.roughcut_gate else None,
        timeline_alignment=timeline_alignment,
    )
    raw_timeline_path = output_dir / "talking_head_timeline.raw.json"
    scene_plan_path = output_dir / "scene_plan.json"
    quality_gate_path = output_dir / "scene_plan_quality_gate.json"
    review_path = output_dir / "storyboard_template_review.html"
    checkpoint_path = output_dir / "director_checkpoint.json"
    routing_plan_path = output_dir / "tool_routing_plan.json"

    scene_plan = normalize_talking_head_scene_plan(timeline)
    scene_plan["lane"] = lane
    disable_tool_routing = bool(getattr(args, "disable_tool_routing", False))
    if not disable_tool_routing:
        tool_registry = getattr(args, "tool_registry", str(PROJECT_ROOT / "configs/video/tool_registry.json"))
        project_registry = getattr(args, "project_registry", str(PROJECT_ROOT / "configs/external/reserved_projects.json"))
        scene_plan, routing_plan = apply_routes_to_scene_plan(
            scene_plan,
            tool_registry_path=Path(tool_registry).expanduser().resolve(),
            project_registry_path=Path(project_registry).expanduser().resolve(),
        )
        write_json(routing_plan_path, routing_plan)
    errors = validate_artifact("scene_plan", scene_plan)
    if errors:
        raise RuntimeError(f"scene_plan invalid: {json.dumps(errors, ensure_ascii=False)}")
    write_json(raw_timeline_path, timeline)
    write_json(scene_plan_path, scene_plan)
    write_json(quality_gate_path, audit_scene_plan(scene_plan))
    review_path.write_text(
        build_review_html(scene_plan, output=review_path, preview_roots=[Path(item).expanduser().resolve() for item in args.template_preview_root], source_storyboard=scene_plan_path),
        encoding="utf-8",
    )
    checkpoint = build_checkpoint(
        load_pipeline(pipeline_id),
        "scene_plan",
        artifact_paths={
            "scene_plan": str(scene_plan_path),
            "quality_gate": str(quality_gate_path),
            "review": str(review_path),
            **({"tool_routing_plan": str(routing_plan_path)} if not disable_tool_routing else {}),
        },
        status="pending_review",
        notes="Review director composition and roughcut gate before material generation.",
    )
    write_json(checkpoint_path, checkpoint)
    return {
        "raw_timeline": raw_timeline_path,
        "scene_plan": scene_plan_path,
        "scene_plan_quality_gate": quality_gate_path,
        "review_html": review_path,
        "checkpoint": checkpoint_path,
        **({"tool_routing_plan": routing_plan_path} if not disable_tool_routing else {}),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build a governed Newma video director scene_plan package.")
    parser.add_argument("--lane", choices=["explainer_html_video", "vox_explainer_video", "talking_head_video", "digital_human_video", "commercial_promo_video"], required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--project-manifest", default="")
    parser.add_argument("--title", default="未命名视频")
    parser.add_argument("--template-preview-root", action="append", default=[])
    parser.add_argument("--tool-registry", default=str(PROJECT_ROOT / "configs" / "video" / "tool_registry.json"))
    parser.add_argument("--project-registry", default=str(PROJECT_ROOT / "configs" / "external" / "reserved_projects.json"))
    parser.add_argument("--disable-tool-routing", action="store_true", help="Build a scene plan without director tool routing annotations.")

    parser.add_argument("--article-html", help="Required for explainer_html_video and vox_explainer_video.")
    parser.add_argument("--commercial-brief", help="Required for commercial_promo_video.")
    parser.add_argument("--duration-target-sec", type=int, default=180)
    parser.add_argument("--central-question", default="", help="Optional central question override for vox_explainer_video.")
    parser.add_argument("--creator-intro", default="这里是 Newma，我们用证据把答案一步步收窄。")
    parser.add_argument("--storyboard-review-gate", default="", help="Approved gate report for the narrative_storyboard.json emitted by the first VOX pass.")
    parser.add_argument("--template-router", default=str(PROJECT_ROOT / "configs" / "video" / "html_anything_template_router.json"))

    caption_group = parser.add_mutually_exclusive_group()
    caption_group.add_argument("--captions-json")
    caption_group.add_argument("--srt")
    parser.add_argument("--source-video")
    parser.add_argument("--duration", type=float)
    parser.add_argument("--roughcut-gate")
    parser.add_argument("--roughcut-edl", help="Discrete keep-segment EDL from the rough-cut stage.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    output_dir = Path(args.output_dir).expanduser().resolve()
    if not is_safe_output_root(output_dir):
        raise SystemExit(f"Unsafe output-dir: {output_dir}. Use ~/Desktop/自媒体创作 or another creator output root.")
    output_dir.mkdir(parents=True, exist_ok=True)
    if args.lane == "commercial_promo_video":
        if not args.commercial_brief:
            raise SystemExit("--commercial-brief is required for commercial_promo_video")
        builder = load_commercial_promo_builder()
        outputs = builder.build_package(
            builder.read_json(Path(args.commercial_brief).expanduser().resolve()),
            output_dir,
            route_tools=not args.disable_tool_routing,
        )
    elif args.lane in {"explainer_html_video", "vox_explainer_video"}:
        if not args.article_html:
            raise SystemExit("--article-html is required for explainer_html_video and vox_explainer_video")
        outputs = build_vox_package(args, output_dir) if args.lane == "vox_explainer_video" else build_explainer_package(args, output_dir)
    else:
        if not args.captions_json and not args.srt:
            raise SystemExit("--captions-json or --srt is required for talking_head_video and digital_human_video")
        outputs = build_talking_head_package(
            args,
            output_dir,
            lane=args.lane,
            pipeline_id="digital_human" if args.lane == "digital_human_video" else "talking_head",
        )

    vox_scene_plan_needs_revision = False
    if args.lane == "vox_explainer_video" and "scene_plan_quality_gate" in outputs:
        vox_scene_plan_needs_revision = read_json(outputs["scene_plan_quality_gate"]).get("status") != "pass"
    vox_production_ready = args.lane == "vox_explainer_video" and "scene_plan" in outputs and not vox_scene_plan_needs_revision
    vox_script_needs_revision = False
    if args.lane == "vox_explainer_video" and "script_rewrite_gate" in outputs:
        vox_script_needs_revision = read_json(outputs["script_rewrite_gate"]).get("status") != "pass"
    commercial_scene_plan_needs_revision = False
    if args.lane == "commercial_promo_video" and "scene_plan_quality_gate" in outputs:
        commercial_scene_plan_needs_revision = read_json(outputs["scene_plan_quality_gate"]).get("status") != "pass"
    if args.project_manifest:
        register_outputs_to_project_manifest(
            Path(args.project_manifest).expanduser().resolve(),
            outputs,
            stage_status="approved" if vox_production_ready else "needs_revision" if vox_script_needs_revision or vox_scene_plan_needs_revision or commercial_scene_plan_needs_revision else "pending_review",
        )

    result = {
        "status": (
            "production_plan_ready"
            if vox_production_ready
            else "needs_scene_plan_revision"
            if vox_scene_plan_needs_revision or commercial_scene_plan_needs_revision
            else "needs_script_revision"
            if vox_script_needs_revision
            else "pending_storyboard_review"
            if args.lane == "vox_explainer_video"
            else "pending_review"
        ),
        "lane": args.lane,
        "output_dir": str(output_dir),
        "outputs": {key: str(path) for key, path in outputs.items()},
        "next_step": (
            "Generate Codex reference images from the approved production shots."
            if vox_production_ready
            else "Revise scene_plan.json until scene_plan_quality_gate.json passes."
            if vox_scene_plan_needs_revision or commercial_scene_plan_needs_revision
            else "Revise narration_script.rewritten.md until script_rewrite_gate.json passes."
            if vox_script_needs_revision
            else "Open storyboard_review.html, export storyboard_review_decision.json, validate it, then rerun with --storyboard-review-gate."
            if args.lane == "vox_explainer_video"
            else "Open storyboard_template_review.html, export storyboard_review_decision.json, then validate the review gate."
        ),
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
