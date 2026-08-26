#!/usr/bin/env python3
"""Build Image2 still, crop, storyboard and image-to-video jobs for VOX director shots."""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw


ASPECTS = {
    "16:9": (1920, 1080),
    "1:1": (1080, 1080),
    "9:16": (1080, 1920),
}

SHOT_SIZES = ["EST_WIDE", "MEDIUM", "CLOSE", "DETAIL"]
SHOT_CROP_SCALES = {
    "EST_WIDE": 1.0,
    "WIDE": 0.92,
    "MEDIUM": 0.82,
    "CLOSE": 0.66,
    "DETAIL": 0.50,
}


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def clean(text: Any) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()


def narration_chunks(text: str, count: int) -> list[str]:
    sentences = [clean(item) for item in re.split(r"(?<=[。！？；!?;])", clean(text)) if clean(item)]
    if not sentences:
        return [""] * count
    groups = [""] * count
    total = sum(len(item) for item in sentences)
    target = max(1, total / count)
    index = 0
    for sentence in sentences:
        if index < count - 1 and groups[index] and len(groups[index]) + len(sentence) > target:
            index += 1
        groups[index] += sentence
    for index in range(1, count):
        if not groups[index]:
            groups[index] = groups[index - 1]
    return groups


def style_contract(plan: dict[str, Any]) -> str:
    bible = plan.get("visual_bible") or {}
    materials = ", ".join(bible.get("materials") or ["torn newsprint", "cardboard depth", "paper cutouts", "red thread"])
    palette = ", ".join((bible.get("palette") or {}).values())
    world = clean(bible.get("world") or "one continuous tabletop evidence world")
    return (
        f"Keep one continuous VOX editorial world: {world}. "
        f"Materials: {materials}. Palette: {palette or 'ink black, warm paper, signal red, evidence teal, muted gold'}. "
        "Preserve the same paper texture, lighting direction, camera height and recurring evidence objects across every shot."
    )


def resolve_shot_size(micro: dict[str, Any], index: int) -> str:
    value = clean(micro.get("shot_size") or micro.get("framing")).upper().replace(" ", "_")
    return value if value in SHOT_CROP_SCALES else SHOT_SIZES[index % len(SHOT_SIZES)]


def resolve_focus(micro: dict[str, Any], index: int) -> tuple[float, float]:
    focus = micro.get("focus") or micro.get("focal_point") or {}
    if isinstance(focus, dict) and "x" in focus and "y" in focus:
        return min(1.0, max(0.0, float(focus["x"]))), min(1.0, max(0.0, float(focus["y"])))
    position = clean(micro.get("subject_position") or micro.get("composition_anchor")).lower()
    if position in {"left", "左", "左侧"}:
        return 0.34, 0.50
    if position in {"right", "右", "右侧"}:
        return 0.66, 0.50
    if position in {"top", "上", "上方"}:
        return 0.50, 0.35
    if position in {"bottom", "下", "下方"}:
        return 0.50, 0.65
    return 0.50, 0.50


def shot_prompt(
    *,
    scene: dict[str, Any],
    micro: dict[str, Any],
    narration: str,
    shot_size: str,
    focus_x: float,
    focus_y: float,
    crop_scale: float,
    style: str,
    style_reference: str,
) -> str:
    visual = scene.get("visual") or {}
    nodes = visual.get("nodes") or visual.get("points") or visual.get("labels") or []
    mechanism = clean(micro.get("visual_mechanism") or micro.get("action") or scene.get("visual_grammar"))
    reference = (
        f"Use the supplied master reference image at {style_reference} as the strict style and world reference. "
        if style_reference
        else "This image will become the master reference frame for the same visual world. "
    )
    return "\n".join(
        [
            "Use case: stylized-concept",
            "Asset type: Image2 VOX director-shot scene still, horizontal 2048x1152 master canvas",
            f"Primary request: {scene.get('title')}. Narration beat: {narration}",
            reference + style,
            f"Scene mechanism: {mechanism or 'assemble the evidence into one readable causal composition'}.",
            f"Evidence objects: {', '.join(map(str, nodes[:5])) or 'source documents, physical evidence objects and one clear causal path'}.",
            f"Composition/framing: {shot_size}; focal point near normalized position ({focus_x:.2f}, {focus_y:.2f}). Keep the main action inside the central 45% so 1:1 and 9:16 crops remain usable.",
            f"Crop intent: preserve a clean editorial crop at scale {crop_scale:.2f}; keep the primary evidence object, faces, hands and causal path fully visible after reframing.",
            "Lighting/mood: flat editorial paper collage, tactile fibers, crisp cut edges, short paper shadows and clear negative space; no room, desk or realistic 3D diorama.",
            "Text policy: do not render final headlines, numbers, dates, citations or chart labels. Use blank paper labels and empty title areas; exact text will be added in Remotion.",
            "Constraints: one finished scene, not a mood board; no split-screen UI, no white dashboard, no watermark, no logo, no black frame, no border.",
        ]
    )


def resolve_sound_cue(micro: dict[str, Any]) -> str:
    return clean(micro.get("sound_cue") or "paper slide, marker stroke or restrained mechanical click")


def motion_prompt(micro: dict[str, Any], duration: float, sound_cue: str) -> str:
    camera = clean(micro.get("camera_move") or "slow controlled push-in")
    action = clean(micro.get("visual_mechanism") or micro.get("action") or "evidence objects assemble and the causal path activates")
    assembly_order = [clean(item) for item in micro.get("assembly_order") or [] if clean(item)]
    generation_contract = (
        "Use the generated scene still as the exact target composition. Start with the same matte background and optional base panel, "
        f"then assemble each named group once in this order: {'; '.join(assembly_order)}. Keep every arrived object visible. "
        if assembly_order
        else "Use the generated scene still as the locked composition and animate only the declared local evidence action. "
    )
    return " ".join(
        [
            f"{generation_contract}Duration {duration:.2f} seconds.",
            f"Generated camera: locked, no pan or zoom. Remotion camera cue after generation: {camera}.",
            f"Object action: {action}.",
            "Treat the still as a target object map, not one flat animation plate. Finish the meaningful motion before the last second and hold the completed composition.",
            "No new objects, object disappearance, text mutation, camera teleport, full-frame fade, black or white transition frame, readable text, logo, watermark or generated sound.",
            f"End on a stable readable frame for the next Remotion match cut. Remotion sound cue: {sound_cue}.",
        ]
    )


def build_manifest(plan: dict[str, Any], output_dir: Path, style_reference: str = "") -> dict[str, Any]:
    style = style_contract(plan)
    jobs: list[dict[str, Any]] = []
    master_reference_image = ""
    master_reference_shot_id = ""
    for scene_index, scene in enumerate(plan.get("scenes") or [], start=1):
        micros = scene.get("director_shots") or scene.get("micro_shots") or (scene.get("visual") or {}).get("micro_shots") or []
        if not micros:
            micros = [{"id": f"{scene.get('id')}_{index + 1:02d}", "action": "build the evidence"} for index in range(3)]
        chunks = narration_chunks(clean(scene.get("narration")), len(micros))
        scene_duration = float(scene.get("duration_sec") or (float(scene.get("end_sec", 0)) - float(scene.get("start_sec", 0))) or len(micros) * 4)
        for shot_index, micro in enumerate(micros):
            start_ratio = float(micro.get("start_ratio", shot_index / len(micros)))
            end_ratio = float(micro.get("end_ratio", (shot_index + 1) / len(micros)))
            duration = max(2.5, scene_duration * max(0.05, end_ratio - start_ratio))
            shot_id = clean(micro.get("id") or f"{scene.get('id')}_{shot_index + 1:02d}")
            shot_size = resolve_shot_size(micro, shot_index)
            focus_x, focus_y = resolve_focus(micro, shot_index)
            crop_scale = float(micro.get("crop_scale") or SHOT_CROP_SCALES[shot_size])
            shot_dir = output_dir / "shots" / str(scene.get("id") or f"scene_{scene_index:03d}") / shot_id
            source_image = shot_dir / "image2_source.png"
            effective_style_reference = style_reference or master_reference_image
            crops = {aspect: str(shot_dir / f"crop_{aspect.replace(':', 'x')}.png") for aspect in ASPECTS}
            image_prompt = shot_prompt(
                scene=scene,
                micro=micro,
                narration=chunks[shot_index],
                shot_size=shot_size,
                focus_x=focus_x,
                focus_y=focus_y,
                crop_scale=crop_scale,
                style=style,
                style_reference=effective_style_reference,
            )
            sound_cue = resolve_sound_cue(micro)
            video_prompt = motion_prompt(micro, duration, sound_cue)
            visual = scene.get("visual") or {}
            layer_objects = micro.get("layer_objects") or visual.get("nodes") or visual.get("points") or [
                "background paper field",
                "hero evidence object",
                "secondary evidence object",
                "foreground occluder",
                "exact-text card",
                "route or chart overlay",
            ]
            shot_dir.mkdir(parents=True, exist_ok=True)
            (shot_dir / "image_prompt.txt").write_text(image_prompt + "\n", encoding="utf-8")
            (shot_dir / "video_prompt.txt").write_text(video_prompt + "\n", encoding="utf-8")
            job = {
                "scene_id": scene.get("id"),
                "shot_id": shot_id,
                "narrative_function": scene.get("narrative_function") or scene.get("type"),
                "narration": chunks[shot_index],
                "start_sec": round(float(scene.get("start_sec") or 0) + scene_duration * start_ratio, 3),
                "end_sec": round(float(scene.get("start_sec") or 0) + scene_duration * end_ratio, 3),
                "duration_sec": round(duration, 3),
                "shot_size": shot_size,
                "camera_move": clean(micro.get("camera_move") or "slow controlled push-in"),
                "focus": {"x": focus_x, "y": focus_y},
                "crop_scale": crop_scale,
                "crop_plan": {
                    "focus": {"x": focus_x, "y": focus_y},
                    "scale": crop_scale,
                    "protect": ["primary evidence object", "faces and hands", "causal path", "blank Remotion text area"],
                },
                "style_reference": effective_style_reference,
                "style_reference_role": "external_master" if style_reference else ("creates_master" if not master_reference_image else "generated_master"),
                "depends_on": [] if style_reference or not master_reference_shot_id else [master_reference_shot_id],
                "image_model": "image2",
                "image_prompt": image_prompt,
                "source_image": str(source_image),
                "crop_outputs": crops,
                "video_prompt": video_prompt,
                "sound_cue": sound_cue,
                "video_output": str(shot_dir / "generated_scene.mp4"),
                "layer_decomposition": {
                    "mode": "independent_object_layers",
                    "source_strategy": "generate_or_segment_each_object_individually",
                    "object_inventory": list(map(str, layer_objects)),
                    "minimum_layer_count": 8,
                    "layer_manifest": str(shot_dir / "layer_manifest.json"),
                    "whole_scene_plate_role": "layout_reference_only",
                },
                "camera_keyframes": micro.get("camera_keyframes") or [
                    {"at": 0, "x": 0, "y": 0, "z": 0},
                    {"at": 0.55, "x": 24, "y": -12, "z": 120},
                    {"at": 1, "x": 0, "y": 0, "z": 240},
                ],
                "layer_motion_requirements": {
                    "minimum_motion_dimensions": 3,
                    "require_depth_separation": True,
                    "require_foreground_occlusion": True,
                    "stepped_fps": 10,
                },
                "exact_text_overlay": "remotion_only",
                "evidence_role": "illustrative",
                "status": "image_pending",
            }
            jobs.append(job)
            (shot_dir / "shot_card.json").write_text(json.dumps(job, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            if not master_reference_image:
                master_reference_image = str(source_image)
                master_reference_shot_id = shot_id
    return {
        "schema_version": "dasheng.video.image2_shot_manifest.v1",
        "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "lane": "vox_explainer_video",
        "source_scene_plan": plan.get("source_html") or "",
        "style_reference": style_reference or master_reference_image,
        "reference_strategy": "external_master" if style_reference else "generate_first_shot_then_lock_world",
        "master_canvas": {"width": 2048, "height": 1152, "safe_center_width_ratio": 0.45},
        "workflow": ["image2_prompt", "scene_still", "crop", "storyboard_review", "layer_decomposition", "layer_motion_design", "image_to_video", "remotion_composite"],
        "jobs": jobs,
    }


def crop_box(
    width: int,
    height: int,
    target_ratio: float,
    focus_x: float,
    focus_y: float,
    crop_scale: float = 1.0,
) -> tuple[int, int, int, int]:
    source_ratio = width / height
    if source_ratio > target_ratio:
        base_h = height
        base_w = round(height * target_ratio)
    else:
        base_w = width
        base_h = round(width / target_ratio)
    scale = min(1.0, max(0.35, crop_scale))
    crop_w = max(2, round(base_w * scale))
    crop_h = max(2, round(base_h * scale))
    center_x = round(width * focus_x)
    center_y = round(height * focus_y)
    left = min(max(0, center_x - crop_w // 2), width - crop_w)
    top = min(max(0, center_y - crop_h // 2), height - crop_h)
    return left, top, left + crop_w, top + crop_h


def crop_existing(manifest: dict[str, Any]) -> int:
    completed = 0
    for job in manifest.get("jobs") or []:
        source = Path(job["source_image"])
        if not source.exists():
            continue
        with Image.open(source) as image:
            image = image.convert("RGB")
            focus = job.get("focus") or {"x": 0.5, "y": 0.5}
            crop_boxes: dict[str, list[int]] = {}
            for aspect, target in ASPECTS.items():
                box = crop_box(
                    image.width,
                    image.height,
                    target[0] / target[1],
                    float(focus["x"]),
                    float(focus["y"]),
                    float(job.get("crop_scale") or 1.0),
                )
                output = Path(job["crop_outputs"][aspect])
                output.parent.mkdir(parents=True, exist_ok=True)
                image.crop(box).resize(target, Image.Resampling.LANCZOS).save(output)
                crop_boxes[aspect] = list(box)
        job["crop_boxes"] = crop_boxes
        job["status"] = "storyboard_review_pending"
        (source.parent / "shot_card.json").write_text(json.dumps(job, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        completed += 1
    return completed


def contact_sheet(manifest: dict[str, Any], output: Path) -> Path | None:
    jobs = [job for job in manifest.get("jobs") or [] if Path(job["source_image"]).exists()]
    if not jobs:
        return None
    thumb_w, thumb_h, label_h, cols = 420, 236, 52, 4
    sheet = Image.new("RGB", (cols * thumb_w, len(jobs) * (thumb_h + label_h)), "#171411")
    draw = ImageDraw.Draw(sheet)
    variants = [("SOURCE", "source_image"), ("16:9", "16:9"), ("1:1", "1:1"), ("9:16", "9:16")]
    for row, job in enumerate(jobs):
        for col, (label, key) in enumerate(variants):
            path = Path(job["source_image"] if key == "source_image" else job["crop_outputs"][key])
            if not path.exists():
                continue
            with Image.open(path) as source:
                source = source.convert("RGB")
                source.thumbnail((thumb_w - 16, thumb_h - 16), Image.Resampling.LANCZOS)
                frame = Image.new("RGB", (thumb_w, thumb_h), "#2a2520")
                frame.paste(source, ((thumb_w - source.width) // 2, (thumb_h - source.height) // 2))
            x = col * thumb_w
            y = row * (thumb_h + label_h)
            sheet.paste(frame, (x, y))
            caption = f"{job['scene_id']} · {job['shot_id']} · {job['shot_size']} · {label}"
            draw.text((x + 12, y + thumb_h + 12), caption, fill="#f4ead4")
    output.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(output, quality=92)
    manifest["review_assets"] = {"storyboard_contact_sheet": str(output), "columns": [item[0] for item in variants]}
    return output


def storyboard_review(manifest: dict[str, Any], output: Path) -> Path:
    shots = []
    for job in manifest.get("jobs") or []:
        source_exists = Path(job["source_image"]).exists()
        crops_exist = all(Path(path).exists() for path in job["crop_outputs"].values())
        shots.append(
            {
                "scene_id": job["scene_id"],
                "shot_id": job["shot_id"],
                "source_image": job["source_image"],
                "crop_outputs": job["crop_outputs"],
                "source_exists": source_exists,
                "crops_exist": crops_exist,
                "checks": ["primary subject intact", "evidence object intact", "crop-safe text area", "continuity with adjacent shot"],
                "decision": "pending" if source_exists and crops_exist else "blocked_missing_scene_still",
            }
        )
    complete = all(item["source_exists"] and item["crops_exist"] for item in shots)
    payload = {
        "schema_version": "dasheng.video.review.v1",
        "review_type": "image2_crop_storyboard",
        "status": "needs_revision" if complete else "blocked",
        "review_state": "pending_director_approval" if complete else "blocked_missing_scene_stills",
        "decision": "pending",
        "render_allowed": False,
        "review_items": [
            {
                "code": "director_crop_approval_pending" if complete else "scene_stills_missing",
                "severity": "warn" if complete else "fail",
                "message": "Approve the real SOURCE and aspect crops before image-to-video." if complete else "Generate and crop every Image2 scene still before director approval.",
            }
        ],
        "generated_shots": sum(1 for item in shots if item["source_exists"]),
        "total_shots": len(shots),
        "contact_sheet": (manifest.get("review_assets") or {}).get("storyboard_contact_sheet"),
        "shots": shots,
    }
    write_json(output, payload)
    manifest.setdefault("review_assets", {})["storyboard_review"] = str(output)
    return output


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build the Image2-first VOX micro-shot production manifest.")
    parser.add_argument("--scene-plan", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--style-reference", default="")
    parser.add_argument("--crop-existing", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    output_dir = Path(args.output_dir).expanduser().resolve()
    manifest_path = output_dir / "image2_shot_manifest.json"
    if args.crop_existing and manifest_path.exists():
        manifest = read_json(manifest_path)
    else:
        manifest = build_manifest(
            read_json(Path(args.scene_plan).expanduser().resolve()),
            output_dir,
            style_reference=str(Path(args.style_reference).expanduser().resolve()) if args.style_reference else "",
        )
    cropped = crop_existing(manifest) if args.crop_existing else 0
    sheet = contact_sheet(manifest, output_dir / "storyboard_contact_sheet.jpg") if args.crop_existing else None
    review = storyboard_review(manifest, output_dir / "storyboard_review.json") if args.crop_existing else None
    write_json(manifest_path, manifest)
    print(
        json.dumps(
            {
                "manifest": str(manifest_path),
                "job_count": len(manifest["jobs"]),
                "cropped": cropped,
                "contact_sheet": str(sheet) if sheet else None,
                "storyboard_review": str(review) if review else None,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
