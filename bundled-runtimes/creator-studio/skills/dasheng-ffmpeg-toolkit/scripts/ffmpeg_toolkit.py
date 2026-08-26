#!/usr/bin/env python3
"""Guarded wrappers for common FFmpeg operations used by Newma video skills."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path


FORBIDDEN_OUTPUT_PARTS = (
    ("skills",),
    (".codex", "skills"),
    ("openclaw-skill-exports",),
)


def existing_input(value: str) -> Path:
    path = Path(value).expanduser().resolve()
    if not path.is_file():
        raise argparse.ArgumentTypeError(f"input file does not exist: {path}")
    return path


def output_path(value: str) -> Path:
    path = Path(value).expanduser().resolve()
    parts = path.parts
    for forbidden in FORBIDDEN_OUTPUT_PARTS:
        width = len(forbidden)
        if any(tuple(parts[i : i + width]) == forbidden for i in range(len(parts) - width + 1)):
            raise argparse.ArgumentTypeError(f"output is inside a forbidden root: {path}")
    return path


def require_binary(name: str) -> str:
    found = shutil.which(name)
    if not found:
        raise SystemExit(f"required binary not found: {name}")
    return found


def prepare_output(path: Path, overwrite: bool, dry_run: bool) -> None:
    if path.exists() and not overwrite:
        raise SystemExit(f"output exists; pass --overwrite to replace it: {path}")
    if not dry_run:
        path.parent.mkdir(parents=True, exist_ok=True)


def run_command(command: list[str], dry_run: bool = False) -> int:
    if dry_run:
        print(json.dumps(command, ensure_ascii=False))
        return 0
    completed = subprocess.run(command, check=False)
    return completed.returncode


def base_ffmpeg(args: argparse.Namespace) -> list[str]:
    command = [require_binary("ffmpeg"), "-hide_banner", "-nostdin"]
    command.append("-y" if args.overwrite else "-n")
    return command


def cmd_probe(args: argparse.Namespace) -> int:
    command = [
        require_binary("ffprobe"), "-v", "error", "-show_streams", "-show_format",
        "-of", "json", str(args.input),
    ]
    completed = subprocess.run(command, check=False, capture_output=True, text=True)
    if completed.stdout:
        print(completed.stdout.rstrip())
    if completed.stderr:
        print(completed.stderr.rstrip(), file=sys.stderr)
    return completed.returncode


def cmd_transcode(args: argparse.Namespace) -> int:
    if not 0 <= args.crf <= 51:
        raise SystemExit("--crf must be between 0 and 51")
    prepare_output(args.output, args.overwrite, args.dry_run)
    command = base_ffmpeg(args) + [
        "-i", str(args.input), "-map", "0:v:0", "-map", "0:a?",
        "-c:v", "libx264", "-preset", args.preset, "-crf", str(args.crf),
        "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k",
        "-movflags", "+faststart", str(args.output),
    ]
    return run_command(command, args.dry_run)


def cmd_clip(args: argparse.Namespace) -> int:
    if args.start < 0:
        raise SystemExit("--start must be non-negative")
    if args.duration is not None and args.duration <= 0:
        raise SystemExit("--duration must be positive")
    if args.end is not None and args.end <= args.start:
        raise SystemExit("--end must be greater than --start")
    prepare_output(args.output, args.overwrite, args.dry_run)
    command = base_ffmpeg(args) + ["-i", str(args.input), "-ss", str(args.start)]
    if args.duration is not None:
        command += ["-t", str(args.duration)]
    elif args.end is not None:
        command += ["-t", str(args.end - args.start)]
    command += [
        "-map", "0:v:0", "-map", "0:a?", "-c:v", "libx264", "-crf", "18",
        "-preset", "medium", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k",
        "-movflags", "+faststart", str(args.output),
    ]
    return run_command(command, args.dry_run)


def cmd_extract_audio(args: argparse.Namespace) -> int:
    prepare_output(args.output, args.overwrite, args.dry_run)
    suffix = args.output.suffix.lower()
    codec = {".wav": ["pcm_s16le"], ".mp3": ["libmp3lame", "-b:a", "192k"], ".m4a": ["aac", "-b:a", "192k"]}.get(suffix)
    if codec is None:
        raise SystemExit("audio output must end in .wav, .mp3, or .m4a")
    command = base_ffmpeg(args) + ["-i", str(args.input), "-vn", "-c:a", *codec, str(args.output)]
    return run_command(command, args.dry_run)


def cmd_watermark(args: argparse.Namespace) -> int:
    if not 0 < args.scale <= 1:
        raise SystemExit("--scale must be greater than 0 and at most 1")
    if args.margin < 0:
        raise SystemExit("--margin must be non-negative")
    prepare_output(args.output, args.overwrite, args.dry_run)
    command = base_ffmpeg(args) + [
        "-i", str(args.input), "-i", str(args.watermark_image),
        "-filter_complex", f"[1:v]scale=iw*{args.scale}:ih*{args.scale}[wm];[0:v][wm]overlay=W-w-{args.margin}:H-h-{args.margin}",
        "-map", "0:a?", "-c:v", "libx264", "-crf", "18", "-preset", "medium",
        "-pix_fmt", "yuv420p", "-c:a", "copy", "-movflags", "+faststart", str(args.output),
    ]
    return run_command(command, args.dry_run)


def add_output_flags(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--input", required=True, type=existing_input)
    parser.add_argument("--output", required=True, type=output_path)
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--dry-run", action="store_true")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    probe = subparsers.add_parser("probe")
    probe.add_argument("--input", required=True, type=existing_input)
    probe.set_defaults(func=cmd_probe)

    transcode = subparsers.add_parser("transcode")
    add_output_flags(transcode)
    transcode.add_argument("--crf", type=int, default=18)
    transcode.add_argument("--preset", default="medium")
    transcode.set_defaults(func=cmd_transcode)

    clip = subparsers.add_parser("clip")
    add_output_flags(clip)
    clip.add_argument("--start", type=float, default=0.0)
    clip_group = clip.add_mutually_exclusive_group(required=True)
    clip_group.add_argument("--duration", type=float)
    clip_group.add_argument("--end", type=float)
    clip.set_defaults(func=cmd_clip)

    audio = subparsers.add_parser("extract-audio")
    add_output_flags(audio)
    audio.set_defaults(func=cmd_extract_audio)

    watermark = subparsers.add_parser("watermark")
    add_output_flags(watermark)
    watermark.add_argument("--watermark-image", required=True, type=existing_input)
    watermark.add_argument("--scale", type=float, default=0.2)
    watermark.add_argument("--margin", type=int, default=32)
    watermark.set_defaults(func=cmd_watermark)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
