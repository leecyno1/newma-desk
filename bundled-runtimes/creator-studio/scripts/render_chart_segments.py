#!/usr/bin/env python3
"""animated-chart HTML → 视频段渲染（Chrome Headless 逐帧截图 + FFmpeg 合成）。

用法：
    python scripts/render_chart_segments.py --html <animated_chart.html> --out <segment.mp4> [--seconds 6] [--fps 12]
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import tempfile
from pathlib import Path

CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"


def main() -> int:
    parser = argparse.ArgumentParser(description="Render animated chart HTML to video segment")
    parser.add_argument("--html", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--seconds", type=float, default=6.0)
    parser.add_argument("--fps", type=int, default=12)
    args = parser.parse_args()

    html = Path(args.html).resolve()
    out = Path(args.out).expanduser().resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    frames = int(args.seconds * args.fps)
    budget_ms = int(args.seconds * 1000)

    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        # Chrome Headless 逐帧截图（virtual-time 控制每帧时刻）
        for i in range(frames):
            t_ms = int(i * (1000 / args.fps))
            frame = tmp / f"frame_{i:04d}.png"
            subprocess.run(
                [CHROME, "--headless", "--disable-gpu", "--window-size=1080,1920",
                 "--user-data-dir=/tmp/chrome-headless-profile",
                 f"--screenshot={frame}", f"--virtual-time-budget={t_ms}",
                 f"file://{html}"],
                check=True, capture_output=True, timeout=60,
            )
        # FFmpeg 合成
        subprocess.run(
            ["ffmpeg", "-y", "-framerate", str(args.fps), "-i", str(tmp / "frame_%04d.png"),
             "-c:v", "libx264", "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(out)],
            check=True, capture_output=True,
        )
    print(f"渲染完成 → {out}（{frames} 帧 × {args.fps}fps = {args.seconds}s）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
