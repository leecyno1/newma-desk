---
name: dasheng-ffmpeg-toolkit
description: Use when a video or audio file must be probed, clipped, transcoded, normalized, have audio extracted, or receive an image watermark through repeatable guarded FFmpeg commands.
---

# Newma FFmpeg Toolkit

## Role

Provide a small safe wrapper around common FFmpeg engineering operations. Use this for deterministic media handling; use the director, B-roll, or caption skills for creative decisions.

## Quick Start

```bash
python3 skills/dasheng-ffmpeg-toolkit/scripts/ffmpeg_toolkit.py probe --input /absolute/input.mp4
python3 skills/dasheng-ffmpeg-toolkit/scripts/ffmpeg_toolkit.py clip --input /absolute/input.mp4 --output /absolute/output.mp4 --start 4.2 --duration 12
python3 skills/dasheng-ffmpeg-toolkit/scripts/ffmpeg_toolkit.py transcode --input /absolute/input.mov --output /absolute/output.mp4
python3 skills/dasheng-ffmpeg-toolkit/scripts/ffmpeg_toolkit.py extract-audio --input /absolute/input.mp4 --output /absolute/audio.wav
python3 skills/dasheng-ffmpeg-toolkit/scripts/ffmpeg_toolkit.py watermark --input /absolute/input.mp4 --watermark-image /absolute/logo.png --output /absolute/output.mp4
```

Add `--dry-run` to any mutating command to print the exact argument list without executing it. Existing outputs are refused unless `--overwrite` is explicit.

## Workflow

1. Run `probe` and record duration, streams, frame size, codec, and frame rate.
2. Choose the least lossy operation that satisfies the downstream contract.
3. Use an absolute output path under `~/Desktop/自媒体创作/<run_id>/` for production work.
4. Execute the wrapper; never assemble a shell command from untrusted filenames.
5. Probe the result and run the repository's `video_render_qc.py` for final masters.

See [references/operations.md](references/operations.md) for operation defaults and limitations.

## Hard Rules

- Never write outputs into `skills/`, `.codex/skills/`, or `openclaw-skill-exports/`.
- Never overwrite an existing output implicitly.
- Watermarks use an image overlay so the command does not depend on host font discovery.
- The wrapper is not a substitute for subtitle proofreading, director review, or final QC.
