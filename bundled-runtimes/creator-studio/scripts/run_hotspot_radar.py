#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path

from hotspot_radar import collect_hotspot_radar
from path_config import get_output_root


def default_output_dir() -> Path:
    run_id = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    return get_output_root("hotspot") / run_id


def run_hotspot_radar(output_dir: Path) -> dict:
    output_dir.mkdir(parents=True, exist_ok=True)
    raw_dir = output_dir / "raw"
    run = collect_hotspot_radar(raw_dir)
    radar_raw = raw_dir / "hotspot_radar.json"
    radar_public = output_dir / "hotspot_radar.json"
    if radar_raw.exists():
        radar_public.write_text(radar_raw.read_text(encoding="utf-8"), encoding="utf-8")
    manifest_path = output_dir / "hotspot_radar_manifest.json"
    manifest = {
        "generated_at": datetime.now().astimezone().isoformat(),
        "module": "hotspot_radar",
        "output_dir": str(output_dir.resolve()),
        "raw_dir": str(raw_dir.resolve()),
        "status": run.status.get("hotspot_radar", {}).get("status", "unknown"),
        "total": run.status.get("hotspot_radar", {}).get("total", 0),
        "channel_tasks": dict(run.status),
        "artifacts": [
            str(radar_public.resolve()),
            str(manifest_path.resolve()),
            *[str((output_dir / artifact).resolve()) for artifact in run.artifacts],
        ],
    }
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run standalone Newma hotspot radar capture")
    parser.add_argument("--output-dir", help="Output directory. Defaults to ~/Desktop/自媒体创作/00_热点捕捉/<timestamp>.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    output_dir = Path(args.output_dir).expanduser().resolve() if args.output_dir else default_output_dir()
    manifest = run_hotspot_radar(output_dir)
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
