#!/usr/bin/env python3
"""Build the small handoff packet used by Chrome Gemini Omni."""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any


STYLE = (
    "flat 2D VOX editorial paper collage, one matte paper-color background, one torn charcoal base panel, "
    "black-and-white halftone cut-outs, crisp cream paper edges, tactile grain, short paper shadows, "
    "muted gold, deep navy and restrained vermilion accents"
)

REFERENCE_IMAGE_PROVIDER = "codex_builtin_imagegen"
VIDEO_PROVIDER = "google_gemini_omni_signed_in_chrome"

REFERENCE_CONTRACT = {
    "visual_mode": "flat_separable_collage",
    "major_group_range": [4, 6],
    "persistent_base_layer": True,
    "first_frame_policy": "assemble_to_reference",
    "motion_policy": "named_groups_appear_once",
    "final_hold_sec": 1.0,
}


def is_programmatic_shot(shot: dict[str, Any]) -> bool:
    motion = shot.get("motion") or {}
    return str(shot.get("production_route") or "") in {"shotcraft_remotion", "real_evidence_remotion"} or (
        isinstance(motion, dict) and bool(motion.get("shotcraft_card"))
    )


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def image_prompt(shot: dict[str, Any]) -> str:
    return (
        f"Create exactly one complete horizontal 16:9 reference frame for a documentary explainer. {STYLE}. "
        f"Visual thesis: {shot['visual_thesis']}. Composition: {shot['composition']}. "
        "Use only four to six major movable groups. Keep every group visually separate with generous gaps, simple bold silhouettes, "
        "front-facing orthographic placement and enough negative space for later captions. "
        "This is the final assembled object map that an image-to-video model must rebuild piece by piece. "
        "No photorealistic 3D, diorama, room, desk, miniature city, dense newspaper environment, cinematic depth, gradient or glow. "
        "No readable text, letters, numbers, logo, watermark, UI, border or split storyboard."
    )


def omni_prompt(shot: dict[str, Any]) -> str:
    in_place = shot.get("motion_mode") == "in_place"
    beats = shot.get("motion_beats") if in_place else shot.get("assembly_order")
    beats = beats or shot.get("assembly_order") or []
    order = "; ".join(f"{index + 1}. {item}" for index, item in enumerate(beats))
    if in_place:
        action = (
            "Use the provided image as the exact first frame, layout and palette reference. "
            "Keep every visible object present from the first frame to the last frame. Never deconstruct the image. "
            "Animate only these local in-place beats, without moving any group off-canvas or replacing it: "
            f"{order}."
        )
    else:
        action = (
            "Use the provided image as the exact target composition and palette reference. "
            "Start on the same matte background with only the torn base panel visible. Do not show the completed reference first. "
            "Make each named paper group appear exactly once in this order, and keep it visible after it arrives: "
            f"{order}."
        )
    return (
        "Create one 10-second flat editorial paper-collage stop-motion B-roll shot. "
        f"{action} Finish the motion by 9 seconds, then hold the completed reference composition motionless for the final second. "
        f"Preserve this exact style: {STYLE}. "
        "Use tactile 2D paper motion: slide, drop, hinge, unfold, stamp, arrow draw, dial turn or line bend. "
        "Keep the background visible and the camera completely locked. No zoom, pan, reframing, scene cut, whole-frame drift, fade, flash, dissolve, "
        "object disappearance after arrival, morphing, alternate composition, realistic 3D or new objects beyond the reference image. "
        "Keep every dial, certificate, report and label blank: no ticks, glyphs, signatures or fake markings. "
        "No readable text, letters, numbers, logos, watermark, UI or sound."
    )


def shot_status(reference: Path, clip: Path) -> str:
    if clip.exists():
        return "clip_ready"
    if reference.exists():
        return "ready_for_omni"
    return "pending_reference"


def build_packet(source: Path, output_dir: Path) -> Path:
    payload = read_json(source)
    shots = payload.get("shots") if isinstance(payload.get("shots"), list) else payload.get("scenes", [])
    if not shots:
        raise ValueError("input must contain a non-empty shots[] or scenes[] array")

    reference_dir = output_dir / "reference-images"
    prompt_dir = output_dir / "omni-prompts"
    clip_dir = output_dir / "omni-clips"
    for directory in (reference_dir, prompt_dir, clip_dir):
        directory.mkdir(parents=True, exist_ok=True)

    jobs = []
    for index, raw in enumerate(shots, 1):
        shot = dict(raw)
        if is_programmatic_shot(shot):
            continue
        shot_id = shot.get("id") or f"shot-{index:02d}"
        start = float(shot["start_sec"])
        end = float(shot["end_sec"])
        if end <= start:
            raise ValueError(f"{shot_id}: end_sec must be greater than start_sec")
        motion_beats = shot.get("motion_beats") or shot.get("assembly_order")
        if not motion_beats:
            raise ValueError(f"{shot_id}: motion_beats or assembly_order is required")

        reference = reference_dir / f"{shot_id}.png"
        clip = clip_dir / f"{shot_id}.mp4"
        image_text = shot.get("image_prompt") or image_prompt(shot)
        omni_text = shot.get("omni_prompt") or omni_prompt(shot)
        image_file = prompt_dir / f"{shot_id}.image.txt"
        omni_file = prompt_dir / f"{shot_id}.omni.txt"
        image_file.write_text(image_text + "\n", encoding="utf-8")
        omni_file.write_text(omni_text + "\n", encoding="utf-8")

        jobs.append(
            {
                **shot,
                "id": shot_id,
                "motion_beats": motion_beats,
                "timeline_duration_sec": round(end - start, 3),
                "generation_duration_sec": 10,
                "production_route": "gemini_video",
                "reference_contract": REFERENCE_CONTRACT,
                "reference_image_required": True,
                "reference_image": str(reference),
                "reference_image_provider": REFERENCE_IMAGE_PROVIDER,
                "image_prompt_file": str(image_file),
                "omni_prompt_file": str(omni_file),
                "clip_path": str(clip),
                "video_provider": VIDEO_PROVIDER,
                "status": shot_status(reference, clip),
            }
        )

    if not jobs:
        raise ValueError("no Gemini-routed shots; skip Omni packet for this scene plan")

    manifest = {
        "schema_version": "dasheng.video.omni_shot_manifest.v1",
        "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "provider": VIDEO_PROVIDER,
        "reference_image_provider": REFERENCE_IMAGE_PROVIDER,
        "video_provider": VIDEO_PROVIDER,
        "workflow": [
            "director_shot",
            "codex_builtin_imagegen_reference",
            "gemini_omni_browser_video",
            "download",
            "remotion_edit",
        ],
        "aspect_ratio": "16:9",
        "reference_contract": REFERENCE_CONTRACT,
        "jobs": jobs,
    }
    manifest_path = output_dir / "omni_shot_manifest.json"
    write_json(manifest_path, manifest)
    return manifest_path


def refresh(manifest_path: Path) -> None:
    manifest = read_json(manifest_path)
    for job in manifest.get("jobs", []):
        job["status"] = shot_status(Path(job["reference_image"]), Path(job["clip_path"]))
    manifest["updated_at"] = datetime.now().astimezone().isoformat(timespec="seconds")
    write_json(manifest_path, manifest)


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    build = sub.add_parser("build")
    build.add_argument("--shots", type=Path, required=True)
    build.add_argument("--output-dir", type=Path, required=True)
    update = sub.add_parser("refresh")
    update.add_argument("--manifest", type=Path, required=True)
    args = parser.parse_args()

    if args.command == "build":
        print(build_packet(args.shots.expanduser().resolve(), args.output_dir.expanduser().resolve()))
    else:
        refresh(args.manifest.expanduser().resolve())
        print(args.manifest.expanduser().resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
