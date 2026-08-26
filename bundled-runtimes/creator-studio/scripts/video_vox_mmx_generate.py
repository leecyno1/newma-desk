#!/usr/bin/env python3
"""Generate approved VOX Image2 shots through MiniMax CLI."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from pathlib import Path
from typing import Any


DEFAULT_BASE_URL = "https://api.minimaxi.com"
DEFAULT_MODEL = "MiniMax-Hailuo-2.3-Fast"


class GenerationError(RuntimeError):
    pass


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def normalize_base_url(value: str) -> str:
    base_url = value.rstrip("/")
    return base_url[:-3] if base_url.endswith("/v1") else base_url


def require_approved_review(review: dict[str, Any]) -> None:
    if review.get("decision") != "approved" or review.get("render_allowed") is not True:
        raise GenerationError("Crop storyboard review must be approved before image-to-video generation.")


def run(command: list[str]) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(command, check=False, text=True, capture_output=True)
    if result.returncode:
        message = (result.stderr or result.stdout).strip()
        raise GenerationError(message or f"Command failed: {command[0]}")
    return result


def preflight(base_url: str) -> None:
    if not shutil.which("mmx"):
        raise GenerationError("MiniMax CLI `mmx` is not installed.")
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        raise GenerationError("ffmpeg and ffprobe are required.")
    run([
        "mmx",
        "--base-url",
        base_url,
        "quota",
        "show",
        "--output",
        "json",
        "--no-color",
        "--non-interactive",
    ])


def probe_duration(path: Path) -> float:
    result = run([
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        str(path),
    ])
    return float(result.stdout.strip())


def generate_command(*, base_url: str, model: str, image: Path, prompt: str, output: Path) -> list[str]:
    return [
        "mmx",
        "--base-url",
        base_url,
        "video",
        "generate",
        "--model",
        model,
        "--image",
        str(image),
        "--prompt",
        prompt,
        "--download",
        str(output),
        "--output",
        "json",
        "--no-color",
        "--non-interactive",
    ]


def normalize_video(raw: Path, output: Path, requested_duration: float) -> float:
    raw_duration = probe_duration(raw)
    usable_duration = max(0.5, min(requested_duration, raw_duration - 0.25))
    output.parent.mkdir(parents=True, exist_ok=True)
    run([
        "ffmpeg",
        "-y",
        "-loglevel",
        "error",
        "-ss",
        "0.10",
        "-i",
        str(raw),
        "-t",
        f"{usable_duration:.3f}",
        "-vf",
        "scale=1920:1080:flags=lanczos,fps=30,format=yuv420p",
        "-an",
        "-c:v",
        "libx264",
        "-preset",
        "medium",
        "-crf",
        "18",
        "-movflags",
        "+faststart",
        str(output),
    ])
    return usable_duration


def generate_jobs(
    manifest: dict[str, Any],
    *,
    base_url: str,
    model: str,
    aspect: str,
    resume: bool,
) -> dict[str, Any]:
    completed = 0
    skipped = 0
    for job in manifest.get("jobs") or []:
        image_value = (job.get("crop_outputs") or {}).get(aspect)
        if not image_value:
            raise GenerationError(f"{job.get('shot_id')}: missing approved {aspect} crop.")
        image = Path(image_value).expanduser().resolve()
        if not image.exists():
            raise GenerationError(f"{job.get('shot_id')}: crop does not exist: {image}")
        output = Path(job["video_output"]).expanduser().resolve()
        if resume and output.exists():
            job["status"] = "video_ready"
            skipped += 1
            continue
        raw = output.with_name(f"{output.stem}.mmx_raw.mp4")
        raw.parent.mkdir(parents=True, exist_ok=True)
        run(generate_command(
            base_url=base_url,
            model=model,
            image=image,
            prompt=str(job.get("video_prompt") or ""),
            output=raw,
        ))
        used_duration = normalize_video(raw, output, float(job.get("duration_sec") or 4.0))
        job["video_generation"] = {
            "provider": "mmx_cli",
            "model": model,
            "base_url": base_url,
            "input_crop": str(image),
            "raw_output": str(raw),
            "normalized_output": str(output),
            "used_duration_sec": round(used_duration, 3),
            "review_points": [0.05, 0.5, 0.95],
        }
        job["status"] = "video_qc_pending"
        completed += 1
    manifest["video_generation_summary"] = {
        "provider": "mmx_cli",
        "model": model,
        "base_url": base_url,
        "completed": completed,
        "skipped": skipped,
        "next_gate": "opening_middle_ending_frame_review",
    }
    return manifest


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate approved VOX Image2 shots with MiniMax CLI.")
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--review", required=True)
    parser.add_argument("--aspect", default="16:9", choices=["16:9", "1:1", "9:16"])
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--resume", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    manifest_path = Path(args.manifest).expanduser().resolve()
    review = read_json(Path(args.review).expanduser().resolve())
    require_approved_review(review)
    base_url = normalize_base_url(args.base_url)
    preflight(base_url)
    manifest = generate_jobs(
        read_json(manifest_path),
        base_url=base_url,
        model=args.model,
        aspect=args.aspect,
        resume=args.resume,
    )
    write_json(manifest_path, manifest)
    print(json.dumps(manifest["video_generation_summary"], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
