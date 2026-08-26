#!/usr/bin/env python3
"""Extract per-template preview frames from a template showcase video."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path


def safe_id(value: str) -> str:
    return re.sub(r"[^0-9A-Za-z_.-]+", "_", value).strip("_") or "template"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Extract template preview images from TemplateShowcase video.")
    parser.add_argument("--template-data", required=True, help="template_showcase_data.json")
    parser.add_argument("--video", required=True, help="template_showcase_silent.mp4 or equivalent")
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--scale", default="360:-1")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    data = json.loads(Path(args.template_data).expanduser().read_text(encoding="utf-8"))
    video = Path(args.video).expanduser().resolve()
    output_dir = Path(args.output_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    cursor = 0.0
    outputs = []
    for item in data.get("templates", []):
        duration = float(item.get("durationSec") or 3.8)
        timestamp = cursor + duration * 0.5
        template_id = str(item.get("id") or f"template_{len(outputs) + 1:03d}")
        out = output_dir / f"{safe_id(template_id)}.jpg"
        subprocess.run(
            [
                "ffmpeg",
                "-hide_banner",
                "-loglevel",
                "error",
                "-y",
                "-ss",
                f"{timestamp:.3f}",
                "-i",
                str(video),
                "-frames:v",
                "1",
                "-vf",
                f"scale={args.scale}",
                str(out),
            ],
            check=True,
        )
        outputs.append({"template_id": template_id, "timestamp": round(timestamp, 3), "preview": str(out)})
        cursor += duration

    manifest = {
        "schema_version": "dasheng.template_preview_frames.v1",
        "source_video": str(video),
        "source_template_data": str(Path(args.template_data).expanduser().resolve()),
        "output_dir": str(output_dir),
        "count": len(outputs),
        "previews": outputs,
    }
    (output_dir / "template_preview_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": "ok", "count": len(outputs), "outputDir": str(output_dir)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
