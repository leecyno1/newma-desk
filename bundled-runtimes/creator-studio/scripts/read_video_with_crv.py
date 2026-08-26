#!/usr/bin/env python3
"""Read a video locally with claude-real-video and keep outputs outside repo."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from path_config import get_output_root


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CRV_ROOT = Path(
    os.environ.get("CLAUDE_REAL_VIDEO_ROOT", str(PROJECT_ROOT / "vendor/reserved/video/claude-real-video"))
).expanduser()


def safe_slug(value: str, max_len: int = 48) -> str:
    stem = Path(value).stem if not value.startswith(("http://", "https://")) else value.rstrip("/").split("/")[-1]
    cleaned = re.sub(r"[^0-9A-Za-z\u4e00-\u9fff._-]+", "_", stem).strip("._-")
    return (cleaned or "video")[:max_len]


def default_output_dir(source: str) -> Path:
    stamp = datetime.now().astimezone().strftime("%Y%m%d_%H%M%S")
    return get_output_root("video_training") / "_video_reading" / f"{stamp}_{safe_slug(source)}"


def media_python() -> Path:
    candidate = PROJECT_ROOT / ".venv_media" / "bin" / "python"
    return candidate if candidate.exists() else Path(sys.executable)


def run(cmd: list[str], *, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env, check=False)


def inspect_outputs(out_dir: Path) -> dict[str, Any]:
    frames_dir = out_dir / "frames"
    grids_dir = out_dir / "grids"
    return {
        "out_dir": str(out_dir),
        "manifest": str(out_dir / "MANIFEST.txt") if (out_dir / "MANIFEST.txt").exists() else None,
        "transcript": str(out_dir / "transcript.txt") if (out_dir / "transcript.txt").exists() else None,
        "audio": str(out_dir / "audio.m4a") if (out_dir / "audio.m4a").exists() else None,
        "report_html": str(out_dir / "report.html") if (out_dir / "report.html").exists() else None,
        "source_video": str(out_dir / "source.mp4") if (out_dir / "source.mp4").exists() else None,
        "frames_dir": str(frames_dir) if frames_dir.exists() else None,
        "frame_count": len(list(frames_dir.glob("*.jpg"))) if frames_dir.exists() else 0,
        "grids_dir": str(grids_dir) if grids_dir.exists() else None,
        "grid_count": len(list(grids_dir.glob("*.jpg"))) if grids_dir.exists() else 0,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Use local claude-real-video to extract keyframes, grids, transcript, and manifest.")
    parser.add_argument("source", help="Local video path or authorized video URL.")
    parser.add_argument("--output-dir", default="", help="Default: ~/Desktop/自媒体创作/00_范式学习/视频训练/_video_reading/<timestamp>_<slug>.")
    parser.add_argument("--crv-root", default=str(DEFAULT_CRV_ROOT), help="Local claude-real-video checkout.")
    parser.add_argument("--why", default="分析视频内容、剪辑节奏、构图、转场和可复用风格 DNA")
    parser.add_argument("--scene", type=float, default=0.30)
    parser.add_argument("--fps-floor", type=float, default=1.0)
    parser.add_argument("--max-frames", type=int, default=150)
    parser.add_argument("--dedup-threshold", type=float, default=8.0)
    parser.add_argument("--dedup-window", type=int, default=4)
    parser.add_argument("--lang", default="zh")
    parser.add_argument("--cookies", default="")
    parser.add_argument("--transcribe", action="store_true", help="Enable Whisper transcription. Default skips it unless subtitles already exist.")
    parser.add_argument("--keep-audio", action="store_true")
    parser.add_argument("--report", action="store_true")
    parser.add_argument("--no-grid", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    crv_root = Path(args.crv_root).expanduser().resolve()
    if not (crv_root / "src" / "claude_real_video").exists():
        raise SystemExit(f"claude-real-video not found: {crv_root}")

    out_dir = Path(args.output_dir).expanduser().resolve() if args.output_dir else default_output_dir(args.source)
    out_dir.mkdir(parents=True, exist_ok=True)

    env = os.environ.copy()
    env["PYTHONPATH"] = f"{crv_root / 'src'}{os.pathsep}{env.get('PYTHONPATH', '')}".rstrip(os.pathsep)

    cmd = [
        str(media_python()),
        "-m",
        "claude_real_video",
        args.source,
        "-o",
        str(out_dir),
        "--scene",
        str(args.scene),
        "--fps-floor",
        str(args.fps_floor),
        "--max-frames",
        str(args.max_frames),
        "--dedup-threshold",
        str(args.dedup_threshold),
        "--dedup-window",
        str(args.dedup_window),
        "--lang",
        args.lang,
        "--why",
        args.why,
    ]
    if not args.transcribe:
        cmd.append("--no-transcribe")
    if not args.no_grid:
        cmd.append("--grid")
    if args.keep_audio:
        cmd.append("--keep-audio")
    if args.report:
        cmd.append("--report")
    if args.cookies:
        cmd.extend(["--cookies", str(Path(args.cookies).expanduser().resolve())])

    proc = run(cmd, env=env)
    status = "ok" if proc.returncode == 0 else "error"
    result = {
        "schema_version": "dasheng.video_reading_crv.v1",
        "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "status": status,
        "source": args.source,
        "crv_root": str(crv_root),
        "command": cmd,
        "stdout": proc.stdout[-4000:],
        "stderr": proc.stderr[-4000:],
        "outputs": inspect_outputs(out_dir),
        "notes": [
            "Generated outputs stay outside the repo under the creator desktop folder.",
            "Default mode skips Whisper; enable --transcribe only when local Whisper is installed and needed.",
        ],
    }
    manifest = out_dir / "dasheng_video_reading_manifest.json"
    result["dasheng_manifest"] = str(manifest)
    manifest.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return proc.returncode


if __name__ == "__main__":
    raise SystemExit(main())
