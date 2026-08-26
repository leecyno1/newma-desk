#!/usr/bin/env python3
"""Extract first/middle/last frames and basic health signals for one VOX clip."""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path
from typing import Any


def run(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)


def probe(video: Path) -> dict[str, Any]:
    proc = run(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=width,height,r_frame_rate:format=duration",
            "-of",
            "json",
            str(video),
        ]
    )
    if proc.returncode:
        raise RuntimeError(proc.stderr.strip() or "ffprobe failed")
    return json.loads(proc.stdout)


def frame(video: Path, timestamp: float, output: Path) -> None:
    proc = run(
        [
            "ffmpeg",
            "-y",
            "-ss",
            f"{timestamp:.3f}",
            "-i",
            str(video),
            "-frames:v",
            "1",
            "-vf",
            "scale=960:-2",
            str(output),
        ]
    )
    if proc.returncode:
        raise RuntimeError(proc.stderr.strip() or "frame extraction failed")


def black_runs(video: Path) -> list[str]:
    proc = run(
        [
            "ffmpeg",
            "-hide_banner",
            "-nostats",
            "-i",
            str(video),
            "-vf",
            "blackdetect=d=0.15:pix_th=0.05:pic_th=0.98",
            "-an",
            "-f",
            "null",
            "-",
        ]
    )
    return [line.strip() for line in proc.stderr.splitlines() if "black_start:" in line]


def build(video: Path, output_dir: Path) -> Path:
    info = probe(video)
    duration = float(info["format"]["duration"])
    output_dir.mkdir(parents=True, exist_ok=True)
    times = {
        "first": min(0.08, duration / 10),
        "middle": duration / 2,
        "last": max(0.0, duration - 0.08),
    }
    frames: dict[str, str] = {}
    for label, timestamp in times.items():
        path = output_dir / f"{label}.jpg"
        frame(video, timestamp, path)
        frames[label] = str(path)
    report = {
        "video": str(video),
        "duration_sec": round(duration, 3),
        "stream": info.get("streams", [{}])[0],
        "frames": frames,
        "black_runs": black_runs(video),
        "status": "review_required",
    }
    report_path = output_dir / "shot_qc.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report_path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--video", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    print(build(args.video.expanduser().resolve(), args.output_dir.expanduser().resolve()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
