#!/usr/bin/env python3
"""Generate one VOX shot with the official Google Gen AI SDK."""

from __future__ import annotations

import argparse
import base64
import json
import os
import subprocess
import time
import urllib.request
from pathlib import Path
from typing import Any


def load_sdk() -> tuple[Any, Any]:
    try:
        from google import genai
        from google.genai import types
    except ImportError as exc:
        raise RuntimeError("google-genai is missing; install google-genai>=1.67.0") from exc
    return genai, types


def image_from_path(path: Path, types: Any) -> Any:
    mime = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".webp": "image/webp",
    }.get(path.suffix.lower())
    if not mime:
        raise ValueError(f"unsupported image type: {path.suffix}")
    return types.Image(image_bytes=path.read_bytes(), mime_type=mime)


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def normalize_video(source: Path, output: Path, final_duration: int, aspect_ratio: str) -> None:
    width, height = (1080, 1920) if aspect_ratio == "9:16" else (1920, 1080)
    output.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(source),
            "-vf",
            f"scale={width}:{height}:force_original_aspect_ratio=decrease,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,tpad=stop_mode=clone:stop_duration=12,fps=30",
            "-an",
            "-t",
            str(final_duration),
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            str(output),
        ],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def interaction_input(references: list[Path], prompt: str) -> list[dict[str, str]]:
    parts: list[dict[str, str]] = []
    for reference in references:
        mime = {
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".webp": "image/webp",
        }.get(reference.suffix.lower())
        if not mime:
            raise ValueError(f"unsupported image type: {reference.suffix}")
        parts.append(
            {
                "type": "image",
                "data": base64.b64encode(reference.read_bytes()).decode("ascii"),
                "mime_type": mime,
            }
        )
    parts.append({"type": "text", "text": prompt})
    return parts


def download_interaction_video(uri: str, output: Path, api_key: str) -> None:
    separator = "&" if "?" in uri else "?"
    request = urllib.request.Request(f"{uri}{separator}alt=media")
    request.add_header("x-goog-api-key", api_key)
    with urllib.request.urlopen(request, timeout=480) as response:
        output.parent.mkdir(parents=True, exist_ok=True)
        with output.open("wb") as handle:
            while chunk := response.read(1024 * 1024):
                handle.write(chunk)


def generate_omni(
    *,
    client: Any,
    prompt: str,
    references: list[Path],
    output: Path,
    model: str,
    duration: int,
    aspect_ratio: str,
    api_key: str,
) -> str:
    interaction = client.interactions.create(
        model=model,
        input=interaction_input(references, prompt),
        response_format={
            "type": "video",
            "aspect_ratio": aspect_ratio,
            "duration": f"{duration}s",
            "delivery": "uri",
        },
    )
    if interaction.status != "completed":
        raise RuntimeError(f"Gemini Omni interaction did not complete: {interaction.status}")
    videos = [item for item in (interaction.outputs or []) if getattr(item, "type", None) == "video"]
    if not videos or not videos[0].uri:
        raise RuntimeError("Gemini Omni returned no video URI")
    download_interaction_video(videos[0].uri, output, api_key)
    return interaction.id


def generate(
    *,
    prompt: str,
    reference: Path,
    output: Path,
    model: str,
    duration: int,
    aspect_ratio: str,
    resolution: str,
    poll_seconds: int,
    timeout_seconds: int,
    dry_run: bool,
    api_key: str | None = None,
    final_duration: int | None = None,
    first_frame: Path | None = None,
    last_frame: Path | None = None,
) -> dict[str, Any]:
    omni_model = "omni" in model.lower()
    if omni_model and (duration < 3 or duration > 10):
        raise ValueError("Gemini Omni duration must be between 3 and 10 seconds")
    if not omni_model and (duration < 4 or duration > 8):
        raise ValueError("official Veo duration must be between 4 and 8 seconds")
    source_frame = first_frame or reference
    target_frame = last_frame or (reference if first_frame else None)
    request = {
        "backend": "omni_interactions" if omni_model else "veo_generate_videos",
        "model": model,
        "reference": str(reference),
        "first_frame": str(source_frame),
        "last_frame": str(target_frame) if target_frame else None,
        "output": str(output),
        "duration_seconds": duration,
        "aspect_ratio": aspect_ratio,
        "resolution": resolution,
        "generate_audio": False,
        "final_duration_seconds": final_duration or duration,
    }
    write_json(output.with_suffix(".request.json"), request)
    if dry_run:
        return request

    api_key = api_key or os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY or GOOGLE_API_KEY is required")
    for path in [reference, source_frame, target_frame]:
        if path and not path.exists():
            raise FileNotFoundError(path)

    genai, types = load_sdk()
    client = genai.Client(api_key=api_key)
    output.parent.mkdir(parents=True, exist_ok=True)
    native_output = output.with_name(f"{output.stem}.native{output.suffix}") if final_duration and final_duration != duration else output
    if omni_model:
        operation_id = generate_omni(
            client=client,
            prompt=prompt,
            references=[source_frame] + ([target_frame] if target_frame else []),
            output=native_output,
            model=model,
            duration=duration,
            aspect_ratio=aspect_ratio,
            api_key=api_key,
        )
    else:
        operation = client.models.generate_videos(
            model=model,
            prompt=prompt,
            image=image_from_path(source_frame, types),
            config=types.GenerateVideosConfig(
                number_of_videos=1,
                duration_seconds=duration,
                aspect_ratio=aspect_ratio,
                resolution=resolution,
                generate_audio=False,
                last_frame=image_from_path(target_frame, types) if target_frame else None,
            ),
        )
        operation_id = operation.name
        deadline = time.monotonic() + timeout_seconds
        while not operation.done:
            if time.monotonic() >= deadline:
                raise TimeoutError(f"generation timed out: {operation_id}")
            time.sleep(poll_seconds)
            operation = client.operations.get(operation)
        if operation.error:
            raise RuntimeError(f"Gemini video generation failed: {operation.error}")
        if not operation.result or not operation.result.generated_videos:
            raise RuntimeError("Gemini returned no generated video")
        native_output.write_bytes(client.files.download(file=operation.result.generated_videos[0]))

    write_json(output.with_suffix(".operation.json"), {"name": operation_id})
    if native_output != output:
        normalize_video(native_output, output, final_duration or duration, aspect_ratio)
    result = {
        **request,
        "operation_id": operation_id,
        "bytes": output.stat().st_size,
        "status": "succeeded",
    }
    write_json(output.with_suffix(".result.json"), result)
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--prompt-file", type=Path, required=True)
    parser.add_argument("--reference", type=Path, required=True)
    parser.add_argument("--first-frame", type=Path)
    parser.add_argument("--last-frame", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--model", default="veo-3.1-generate-preview")
    parser.add_argument("--duration", type=int, default=8)
    parser.add_argument("--final-duration", type=int)
    parser.add_argument("--aspect-ratio", default="16:9", choices=["16:9", "9:16"])
    parser.add_argument("--resolution", default="720p")
    parser.add_argument("--poll-seconds", type=int, default=10)
    parser.add_argument("--timeout-seconds", type=int, default=1200)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    prompt = args.prompt_file.expanduser().resolve().read_text(encoding="utf-8").strip()
    result = generate(
        prompt=prompt,
        reference=args.reference.expanduser().resolve(),
        output=args.output.expanduser().resolve(),
        model=args.model,
        duration=args.duration,
        aspect_ratio=args.aspect_ratio,
        resolution=args.resolution,
        poll_seconds=args.poll_seconds,
        timeout_seconds=args.timeout_seconds,
        dry_run=args.dry_run,
        api_key=None,
        final_duration=args.final_duration,
        first_frame=args.first_frame.expanduser().resolve() if args.first_frame else None,
        last_frame=args.last_frame.expanduser().resolve() if args.last_frame else None,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
