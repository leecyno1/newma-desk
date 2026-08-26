#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from runtime_paths import digital_human_runtime_root


os.environ.setdefault("PYTORCH_ENABLE_MPS_FALLBACK", "1")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
os.environ.setdefault("HF_HUB_ENABLE_HF_TRANSFER", "0")


def run(command: list[str]) -> None:
    subprocess.run(command, check=True)


def ffprobe_duration(path: Path) -> float:
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=nk=1:nw=1", str(path)],
        check=True,
        capture_output=True,
        text=True,
    )
    return float(result.stdout.strip() or 0)


@dataclass(frozen=True)
class Segment:
    index: int
    start_sec: float
    end_sec: float
    source: str

    @property
    def duration_sec(self) -> float:
        return self.end_sec - self.start_sec


def parse_srt_timestamp(value: str) -> float:
    hours, minutes, rest = value.strip().replace(".", ",").split(":")
    seconds, millis = rest.split(",")
    return int(hours) * 3600 + int(minutes) * 60 + int(seconds) + int(millis) / 1000


def parse_srt_cues(path: Path) -> list[tuple[float, float]]:
    cues: list[tuple[float, float]] = []
    for block in path.read_text(encoding="utf-8", errors="ignore").replace("\r\n", "\n").split("\n\n"):
        timing = next((line.strip() for line in block.splitlines() if "-->" in line), "")
        if not timing:
            continue
        try:
            start, end = (parse_srt_timestamp(item) for item in timing.split("-->", 1))
        except (ValueError, TypeError):
            continue
        if end > start:
            cues.append((start, end))
    return sorted(cues)


def subtitle_cut_points(path: Path | None, total_duration: float) -> list[float]:
    if not path or not path.is_file() or path.suffix.lower() != ".srt":
        return []
    points: list[float] = []
    cues = parse_srt_cues(path)
    for index, (_, end) in enumerate(cues[:-1]):
        next_start = cues[index + 1][0]
        point = end + max(0.0, next_start - end) / 2
        if 0 < point < total_duration:
            points.append(point)
    return points


def build_segments(
    total_duration: float,
    max_segment_sec: float,
    subtitle: Path | None = None,
    min_segment_sec: float = 8.0,
) -> list[Segment]:
    if total_duration <= 0:
        return []
    if max_segment_sec <= 0:
        raise ValueError("max_segment_sec must be positive")
    candidates = subtitle_cut_points(subtitle, total_duration)
    segments: list[Segment] = []
    start = 0.0
    while total_duration - start > max_segment_sec:
        lower = start + min_segment_sec
        upper = min(start + max_segment_sec, total_duration)
        eligible = [point for point in candidates if lower <= point <= upper]
        if eligible:
            end = eligible[-1]
            source = "subtitle_pause"
        else:
            end = upper
            source = "fixed_duration"
        segments.append(Segment(len(segments) + 1, round(start, 3), round(end, 3), source))
        start = end
    if total_duration - start > 0.001:
        segments.append(Segment(len(segments) + 1, round(start, 3), round(total_duration, 3), "tail"))
    return segments


def normalize_audio(source: Path, output: Path, start: float | None = None, duration: float | None = None) -> None:
    command = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y"]
    if start is not None:
        command.extend(["-ss", f"{start:.3f}"])
    command.extend(["-i", str(source)])
    if duration is not None:
        command.extend(["-t", f"{duration:.3f}"])
    command.extend(["-ar", "16000", "-ac", "1", str(output)])
    run(command)


def strip_audio(source: Path, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-i",
            str(source),
            "-map",
            "0:v:0",
            "-an",
            "-c:v",
            "copy",
            "-movflags",
            "+faststart",
            str(output),
        ]
    )


def concat_video_segments(segments: list[Path], output: Path, target_duration: float) -> None:
    if not segments:
        raise ValueError("no rendered segments to concatenate")
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", suffix=".ffconcat", encoding="utf-8", delete=False) as handle:
        list_path = Path(handle.name)
        handle.write("ffconcat version 1.0\n")
        for segment in segments:
            escaped = str(segment).replace("'", "'\\''")
            handle.write(f"file '{escaped}'\n")
    try:
        run(
            [
                "ffmpeg",
                "-hide_banner",
                "-loglevel",
                "error",
                "-y",
                "-f",
                "concat",
                "-safe",
                "0",
                "-i",
                str(list_path),
                "-map",
                "0:v:0",
                "-an",
                "-vf",
                f"tpad=stop_mode=clone:stop_duration={target_duration:.3f}",
                "-t",
                f"{target_duration:.3f}",
                "-c:v",
                "libx264",
                "-crf",
                "16",
                "-preset",
                "medium",
                "-pix_fmt",
                "yuv420p",
                "-movflags",
                "+faststart",
                str(output),
            ]
        )
    finally:
        list_path.unlink(missing_ok=True)


def install_torch_load_shim() -> None:
    import torch

    original = torch.load

    def load(*args: Any, **kwargs: Any) -> Any:
        kwargs.setdefault("weights_only", False)
        loaded = original(*args, **kwargs)
        if isinstance(loaded, dict) and isinstance(loaded.get("args"), argparse.Namespace):
            loaded["args"].device = "mps" if torch.backends.mps.is_available() else "cpu"
        return loaded

    torch.load = load


def resolve_runtime() -> tuple[Path, Path]:
    root = digital_human_runtime_root()
    return root, root / "JoyVASA"


def render_one(repo: Path, image: Path, audio: Path, output_dir: Path, cfg_scale: float, animation_region: str, crop: bool) -> Path:
    sys.path.insert(0, str(repo))
    os.chdir(repo)
    install_torch_load_shim()
    from src.config.argument_config import ArgumentConfig
    from src.config.crop_config import CropConfig
    from src.config.inference_config import InferenceConfig
    from src.live_portrait_wmg_pipeline import LivePortraitPipeline

    def partial_fields(target: type, kwargs: dict[str, Any]) -> Any:
        return target(**{key: value for key, value in kwargs.items() if hasattr(target, key)})

    args = ArgumentConfig()
    args.animation_mode = "human"
    args.reference = str(image)
    args.audio = str(audio)
    args.output_dir = str(output_dir)
    args.cfg_scale = cfg_scale
    args.animation_region = animation_region
    args.flag_force_cpu = False
    if crop:
        args.flag_do_crop = True
        args.flag_pasteback = True
        args.flag_stitching = True
    inference_cfg = partial_fields(InferenceConfig, args.__dict__)
    crop_cfg = partial_fields(CropConfig, args.__dict__)
    produced = LivePortraitPipeline(inference_cfg=inference_cfg, crop_cfg=crop_cfg).execute(args)
    if not produced or not Path(produced).is_file():
        raise RuntimeError("JoyVASA did not produce a video")
    return Path(produced).resolve()


def remux(source: Path, master_audio: Path, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-i",
            str(source),
            "-i",
            str(master_audio),
            "-map",
            "0:v:0",
            "-map",
            "1:a:0",
            "-c:v",
            "copy",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-shortest",
            "-movflags",
            "+faststart",
            str(output),
        ]
    )


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Render a governed JoyVASA digital-human job locally.")
    parser.add_argument("--job", required=True)
    parser.add_argument("--sample-only", action="store_true", help="Render only the first short sample.")
    args = parser.parse_args()

    job_path = Path(args.job).expanduser().resolve()
    job = json.loads(job_path.read_text(encoding="utf-8"))
    if (job.get("presenter_source") or {}).get("consent", {}).get("status") != "confirmed":
        raise SystemExit("portrait consent is not confirmed")
    if job.get("generation", {}).get("api_video_generation") is not False:
        raise SystemExit("job does not explicitly disable video generation APIs")

    runtime_root, repo = resolve_runtime()
    if not repo.is_dir():
        raise SystemExit(f"JoyVASA runtime missing: {repo}; run setup_joyvasa_macos.sh")
    image = Path(job["inputs"]["portrait"]).expanduser().resolve()
    audio = Path(job["inputs"]["audio"]).expanduser().resolve()
    output = Path(job["outputs"]["presenter_video"]).expanduser().resolve()
    segment_dir = Path(job["outputs"]["segment_dir"]).expanduser().resolve()
    segment_dir.mkdir(parents=True, exist_ok=True)
    cfg_scale = float(job["generation"]["cfg_scale"])
    animation_region = str(job["generation"]["animation_region"])
    crop = bool(job["generation"].get("crop", True))

    with tempfile.TemporaryDirectory(prefix="dasheng-digital-human-") as temp:
        temp_dir = Path(temp)
        if args.sample_only:
            sample_duration = min(float(job["generation"].get("short_sample_sec") or 8), ffprobe_duration(audio))
            sample_audio = temp_dir / "sample.wav"
            normalize_audio(audio, sample_audio, 0, sample_duration)
            raw = render_one(repo, image, sample_audio, temp_dir / "render", cfg_scale, animation_region, crop)
            sample_output = segment_dir / "sample_review.mp4"
            remux(raw, sample_audio, sample_output)
            print(str(sample_output))
            return 0

        subtitle_value = job["inputs"].get("subtitle")
        subtitle = Path(subtitle_value).expanduser().resolve() if subtitle_value else None
        total_duration = ffprobe_duration(audio)
        max_segment_sec = float(job["generation"].get("max_segment_sec") or 35)
        plan = build_segments(total_duration, max_segment_sec, subtitle)
        if not plan:
            raise SystemExit("master audio is empty")

        rendered_segments: list[Path] = []
        segment_rows: list[dict[str, Any]] = []
        for segment in plan:
            segment_audio = temp_dir / f"audio_{segment.index:03d}.wav"
            normalize_audio(audio, segment_audio, segment.start_sec, segment.duration_sec)
            raw = render_one(
                repo,
                image,
                segment_audio,
                temp_dir / f"render_{segment.index:03d}",
                cfg_scale,
                animation_region,
                crop,
            )
            segment_output = segment_dir / f"segment_{segment.index:03d}.mp4"
            strip_audio(raw, segment_output)
            rendered_segments.append(segment_output)
            segment_rows.append(
                {
                    "index": segment.index,
                    "start_sec": segment.start_sec,
                    "end_sec": segment.end_sec,
                    "duration_sec": round(segment.duration_sec, 3),
                    "cut_source": segment.source,
                    "video": str(segment_output),
                }
            )
        concat_video_segments(rendered_segments, output, total_duration)
        write_json(
            segment_dir / "segment_manifest.json",
            {
                "schema_version": "dasheng.digital_human_segments.v1",
                "master_audio": str(audio),
                "max_segment_sec": max_segment_sec,
                "segments": segment_rows,
                "presenter_video_audio_policy": "silent_visual_layer",
            },
        )

    manifest_path = Path(job["outputs"]["presenter_manifest"]).expanduser().resolve()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.is_file() else {}
    manifest.update(
        {
            "schema_version": "dasheng.presenter_source_manifest.v1",
            "status": "generated_pending_qc",
            "kind": "digital_human",
            "engine": "joyvasa_liveportrait",
            "video": str(output),
            "master_audio": str(audio),
            "duration_sec": round(ffprobe_duration(output), 3),
            "segment_manifest": str(segment_dir / "segment_manifest.json"),
            "presenter_video_audio_policy": "silent_visual_layer",
            "runtime_root": str(runtime_root),
            "ai_disclosure_required": True,
        }
    )
    write_json(manifest_path, manifest)
    print(str(output))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
