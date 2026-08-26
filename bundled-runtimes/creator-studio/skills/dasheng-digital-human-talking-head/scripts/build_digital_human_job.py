#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PROFILES: dict[str, dict[str, Any]] = {
    "animal_presenter": {"motion_style": "restrained", "camera_locked": True, "lip_sync": "audio_driven"},
    "calm_presenter": {"cfg_scale": 1.5, "animation_region": "all", "crop": True},
    "stable_lips": {"cfg_scale": 1.5, "animation_region": "lip", "crop": True},
    "expressive_presenter": {"cfg_scale": 2.1, "animation_region": "all", "crop": True},
}


def ffprobe_media(path: Path) -> dict[str, Any]:
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration:stream=codec_type,width,height,sample_rate,channels",
            "-of",
            "json",
            str(path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(result.stdout)


def image_dimensions(path: Path) -> tuple[int | None, int | None]:
    try:
        from PIL import Image

        with Image.open(path) as image:
            return image.size
    except Exception:
        return None, None


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def build_job(
    *,
    image: Path,
    audio: Path,
    output_dir: Path,
    consent: str,
    engine: str = "luma_dream_machine",
    profile: str = "animal_presenter",
    subtitle: Path | None = None,
    title: str = "",
    subject: str = "authorized_presenter",
    minimax_model: str = "speech-2.8-hd",
    minimax_voice: str = "tianxin_xiaoling",
    minimax_speed: float = 1.0,
    max_segment_sec: float = 35.0,
    status: str = "ready_for_short_sample",
) -> Path:
    if consent != "confirmed":
        raise ValueError("portrait consent is not confirmed")
    if engine not in {"luma_dream_machine", "joyvasa_liveportrait"}:
        raise ValueError(f"unsupported engine: {engine}")
    if profile not in PROFILES:
        raise ValueError(f"unsupported profile: {profile}")
    if not 8 <= max_segment_sec <= 45:
        raise ValueError("max_segment_sec must be between 8 and 45 seconds")
    image = image.expanduser().resolve()
    audio = audio.expanduser().resolve()
    subtitle = subtitle.expanduser().resolve() if subtitle else None
    for path, label in ((image, "image"), (audio, "audio")):
        if not path.is_file():
            raise FileNotFoundError(f"{label} not found: {path}")
    if subtitle and not subtitle.is_file():
        raise FileNotFoundError(f"subtitle not found: {subtitle}")
    if not shutil.which("ffprobe"):
        raise RuntimeError("ffprobe is required")

    output_dir = output_dir.expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    width, height = image_dimensions(image)
    audio_probe = ffprobe_media(audio)
    duration = float((audio_probe.get("format") or {}).get("duration") or 0)
    source_dir = output_dir / "source"
    segment_dir = output_dir / "avatar_segments"
    source_dir.mkdir(exist_ok=True)
    segment_dir.mkdir(exist_ok=True)
    image_copy = source_dir / f"portrait{image.suffix.lower()}"
    audio_copy = source_dir / f"minimax_audio{audio.suffix.lower()}"
    shutil.copy2(image, image_copy)
    shutil.copy2(audio, audio_copy)
    subtitle_copy = None
    if subtitle:
        subtitle_copy = source_dir / f"captions{subtitle.suffix.lower()}"
        shutil.copy2(subtitle, subtitle_copy)

    selected_profile = PROFILES[profile]
    segment_count = max(1, int((duration + max_segment_sec - 0.001) // max_segment_sec)) if duration else 1
    payload = {
        "schema_version": "dasheng.digital_human_job.v1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "title": title,
        "mode": "single_presenter",
        "presenter_source": {
            "kind": "digital_human",
            "engine": engine,
            "subject": subject,
            "consent": {"status": "confirmed", "scope": "this_production"},
            "disclosure_required": True,
        },
        "inputs": {
            "portrait": str(image_copy),
            "audio": str(audio_copy),
            "subtitle": str(subtitle_copy) if subtitle_copy else None,
            "portrait_width": width,
            "portrait_height": height,
            "audio_duration_sec": round(duration, 3),
        },
        "voice": {
            "provider": "minimax",
            "model": minimax_model,
            "voice_id": minimax_voice,
            "speed": minimax_speed,
            "master_audio": str(audio_copy),
            "mount_policy": "exactly_once_at_remotion_root",
        },
        "generation": {
            "profile": profile,
            **selected_profile,
            "short_sample_sec": 8,
            "max_segment_sec": max_segment_sec,
            "planned_segment_count": segment_count,
            "segment_policy": "prefer_srt_pause_else_fixed_duration",
            "preserve_master_audio_timing": True,
            "video_generation_provider": "luma" if engine == "luma_dream_machine" else "local",
            "api_video_generation": engine == "luma_dream_machine",
            "source_image_policy": "codex_imagegen_head_replacement" if engine == "luma_dream_machine" else "authorized_portrait",
        },
        "outputs": {
            "segment_dir": str(segment_dir),
            "presenter_video": str(output_dir / "digital_human_source.mp4"),
            "presenter_manifest": str(output_dir / "presenter_source_manifest.json"),
            "qc": str(output_dir / "digital_human_qc.json"),
        },
        "handoff": {
            "lane": "digital_human_video",
            "base_video": str(output_dir / "digital_human_source.mp4"),
            "human_audio": str(audio_copy),
            "subtitle": str(subtitle_copy) if subtitle_copy else None,
            "roughcut_policy": "skip_spoken_cleanup_use_generated_audio_as_locked_timeline",
            "director_skill": "dasheng-video-director",
        },
        "gates": {
            "consent": "pass",
            "short_sample_review": "pending",
            "digital_human_qc": "pending",
            "storyboard_review": "pending",
            "claim_evidence": "pending",
            "renderer_asset": "pending",
            "renderer_contract": "pending",
            "render_qc": "pending",
        },
    }
    job_path = output_dir / "digital_human_job.json"
    write_json(job_path, payload)
    write_json(
        output_dir / "presenter_source_manifest.json",
        {
            "schema_version": "dasheng.presenter_source_manifest.v1",
            "status": "planned",
            "kind": "digital_human",
            "engine": engine,
            "mode": "single_presenter",
            "portrait": str(image_copy),
            "master_audio": str(audio_copy),
            "video": str(output_dir / "digital_human_source.mp4"),
            "job": str(job_path),
            "consent": {"status": "confirmed", "scope": "this_production"},
            "presenter_video_audio_policy": "silent_visual_layer",
            "ai_disclosure_required": True,
        },
    )
    return job_path


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a governed digital-human generation job.")
    parser.add_argument("--image", required=True)
    parser.add_argument("--audio", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--consent", required=True, choices=["confirmed", "not_confirmed"])
    parser.add_argument("--engine", default="luma_dream_machine", choices=["luma_dream_machine", "joyvasa_liveportrait"])
    parser.add_argument("--profile", default="animal_presenter", choices=sorted(PROFILES))
    parser.add_argument("--subtitle")
    parser.add_argument("--title", default="")
    parser.add_argument("--subject", default="authorized_presenter")
    parser.add_argument("--minimax-model", default="speech-2.8-hd")
    parser.add_argument("--minimax-voice", default="tianxin_xiaoling")
    parser.add_argument("--minimax-speed", type=float, default=1.0)
    parser.add_argument("--max-segment-sec", type=float, default=35.0)
    parser.add_argument("--job-status", default="ready_for_short_sample")
    args = parser.parse_args()

    try:
        job_path = build_job(
            image=Path(args.image),
            audio=Path(args.audio),
            output_dir=Path(args.output_dir),
            consent=args.consent,
            engine=args.engine,
            profile=args.profile,
            subtitle=Path(args.subtitle) if args.subtitle else None,
            title=args.title,
            subject=args.subject,
            minimax_model=args.minimax_model,
            minimax_voice=args.minimax_voice,
            minimax_speed=args.minimax_speed,
            max_segment_sec=args.max_segment_sec,
            status=args.job_status,
        )
    except (ValueError, FileNotFoundError, RuntimeError) as exc:
        raise SystemExit(str(exc)) from exc
    print(str(job_path))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
