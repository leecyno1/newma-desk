#!/usr/bin/env python3
"""Lock captions and scene plans to a discrete rough-cut edit decision list."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class KeepSegment:
    old_start: float
    old_end: float
    new_start: float
    new_end: float


@dataclass(frozen=True)
class MappedInterval:
    start: float
    end: float
    kept_duration: float
    clipped: bool
    source_piece_count: int


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def build_keep_segments(payload: dict[str, Any]) -> list[KeepSegment]:
    raw_segments = payload.get("segments") or payload.get("keep_segments") or []
    keep_segments: list[KeepSegment] = []
    cursor = 0.0
    previous_end = -1.0
    for index, raw in enumerate(raw_segments, 1):
        old_start = float(raw.get("old_start", raw.get("start", 0.0)) or 0.0)
        old_end = float(raw.get("old_end", raw.get("end", old_start)) or old_start)
        if old_end <= old_start:
            raise ValueError(f"EDL segment {index} has non-positive duration")
        if old_start < previous_end:
            raise ValueError(f"EDL segment {index} overlaps or is out of order")
        duration = old_end - old_start
        keep_segments.append(KeepSegment(old_start, old_end, cursor, cursor + duration))
        cursor += duration
        previous_end = old_end
    if not keep_segments:
        raise ValueError("EDL contains no keep segments")
    return keep_segments


def remap_interval(start: float, end: float, keep_segments: list[KeepSegment]) -> MappedInterval | None:
    start = float(start)
    end = float(end)
    if end <= start:
        return None
    pieces: list[tuple[float, float]] = []
    kept_duration = 0.0
    for segment in keep_segments:
        overlap_start = max(start, segment.old_start)
        overlap_end = min(end, segment.old_end)
        if overlap_end <= overlap_start:
            continue
        mapped_start = segment.new_start + overlap_start - segment.old_start
        mapped_end = segment.new_start + overlap_end - segment.old_start
        pieces.append((mapped_start, mapped_end))
        kept_duration += overlap_end - overlap_start
    if not pieces:
        return None
    original_duration = end - start
    return MappedInterval(
        start=pieces[0][0],
        end=pieces[-1][1],
        kept_duration=kept_duration,
        clipped=kept_duration < original_duration - 0.001,
        source_piece_count=len(pieces),
    )


def alignment_report(
    keep_segments: list[KeepSegment],
    *,
    dropped_count: int,
    clipped_count: int,
    item_label: str,
    edl_path: str | None = None,
) -> dict[str, Any]:
    return {
        "schema_version": "dasheng.video.timeline_alignment.v1",
        "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "mode": "roughcut_edl",
        "edl_path": edl_path,
        "source_duration_sec": round(max(segment.old_end for segment in keep_segments), 3),
        "output_duration_sec": round(keep_segments[-1].new_end, 3),
        "kept_segment_count": len(keep_segments),
        f"dropped_{item_label}_count": dropped_count,
        f"clipped_{item_label}_count": clipped_count,
        "boundary_review_required": clipped_count > 0,
    }


def remap_scene_plan(
    plan: dict[str, Any],
    keep_segments: list[KeepSegment],
    *,
    edl_path: str | None = None,
    minimum_scene_duration: float = 0.35,
) -> dict[str, Any]:
    locked = dict(plan)
    scenes: list[dict[str, Any]] = []
    dropped = 0
    clipped = 0
    for scene in plan.get("scenes") or []:
        start = float(scene.get("start_sec", scene.get("start", 0.0)) or 0.0)
        end = float(scene.get("end_sec", scene.get("end", start)) or start)
        mapped = remap_interval(start, end, keep_segments)
        if mapped is None or mapped.end - mapped.start < minimum_scene_duration:
            dropped += 1
            continue
        item = dict(scene)
        item["start_sec"] = round(mapped.start, 3)
        item["end_sec"] = round(mapped.end, 3)
        item["duration_sec"] = round(mapped.end - mapped.start, 3)
        if mapped.clipped:
            clipped += 1
            item["timeline_boundary_review"] = {
                "reason": "scene_intersected_a_roughcut_boundary",
                "source_piece_count": mapped.source_piece_count,
            }
        scenes.append(item)
    locked["scenes"] = scenes
    output_duration = round(keep_segments[-1].new_end, 3)
    locked["duration_estimate_sec"] = output_duration
    if "duration_sec" in locked:
        locked["duration_sec"] = output_duration
    locked["timeline_alignment"] = alignment_report(
        keep_segments,
        dropped_count=dropped,
        clipped_count=clipped,
        item_label="scene",
        edl_path=edl_path,
    )
    return locked


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Map a talking-head scene plan through a discrete rough-cut EDL.")
    parser.add_argument("--scene-plan", required=True)
    parser.add_argument("--edl", required=True)
    parser.add_argument("--output", required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    scene_plan_path = Path(args.scene_plan).expanduser().resolve()
    edl_path = Path(args.edl).expanduser().resolve()
    output = Path(args.output).expanduser().resolve()
    keep_segments = build_keep_segments(read_json(edl_path))
    locked = remap_scene_plan(read_json(scene_plan_path), keep_segments, edl_path=str(edl_path))
    write_json(output, locked)
    print(
        json.dumps(
            {
                "status": "ok",
                "output": str(output),
                "scene_count": len(locked.get("scenes") or []),
                "timeline_alignment": locked["timeline_alignment"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
