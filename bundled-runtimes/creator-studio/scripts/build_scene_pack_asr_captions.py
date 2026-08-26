#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

from align_video_subtitles_to_asr import (
    build_position_mapper,
    format_srt_time,
    load_asr_char_timeline,
    plain,
)


def split_caption_chunks(text: str, max_chars: int) -> list[str]:
    text = re.sub(r"\s+", " ", text).strip()
    sentences = [part.strip() for part in re.split(r"(?<=[。？！；])", text) if part.strip()]
    chunks: list[str] = []
    for sentence in sentences:
        if len(sentence) <= max_chars:
            chunks.append(sentence)
            continue
        parts = [part for part in re.split(r"(?<=[，、：])", sentence) if part]
        current = ""
        for part in parts:
            if current and len(current) + len(part) > max_chars:
                chunks.append(current.strip())
                current = part
            else:
                current += part
        if current:
            while len(current) > max_chars:
                chunks.append(current[:max_chars].strip())
                current = current[max_chars:]
            if current.strip():
                chunks.append(current.strip())
    return chunks or [text]


def write_srt(path: Path, cues: list[dict[str, Any]]) -> None:
    rows: list[str] = []
    for index, cue in enumerate(cues, 1):
        rows.extend(
            [
                str(index),
                f"{format_srt_time(float(cue['start']))} --> {format_srt_time(float(cue['end']))}",
                str(cue["text"]),
                "",
            ]
        )
    path.write_text("\n".join(rows).strip() + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Build short, ASR-aligned captions for an HTML scene-pack render.")
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--render-report", required=True)
    parser.add_argument("--asr-json", required=True)
    parser.add_argument("--output-json", required=True)
    parser.add_argument("--output-srt", required=True)
    parser.add_argument("--max-chars", type=int, default=28)
    parser.add_argument("--asr-time-scale", type=float, default=1.0)
    args = parser.parse_args()

    manifest = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
    render_report = json.loads(Path(args.render_report).read_text(encoding="utf-8"))
    manifest_by_id = {str(scene.get("id")): scene for scene in manifest.get("scenes", [])}

    chunks: list[dict[str, Any]] = []
    scene_windows: dict[str, tuple[float, float]] = {}
    cursor = 0.0
    for rendered in render_report.get("scenes", []):
        scene_id = str(rendered.get("id"))
        duration = float(rendered.get("duration_sec") or 0)
        scene_windows[scene_id] = (cursor, cursor + duration)
        source = manifest_by_id.get(scene_id, {})
        narration = str(source.get("narration") or source.get("title") or "").strip()
        for text in split_caption_chunks(narration, args.max_chars):
            normalized = plain(text)
            if normalized:
                chunks.append({"scene_id": scene_id, "text": text, "plain": normalized})
        cursor += duration

    asr_plain, asr_chars = load_asr_char_timeline(Path(args.asr_json))
    script_plain = "".join(chunk["plain"] for chunk in chunks)
    match_ratio, b_for_a = build_position_mapper(script_plain, asr_plain)

    def mapped_time(position: int, *, end: bool = False) -> float:
        position = max(0, min(position, len(script_plain) - 1))
        asr_position = max(0, min(b_for_a(position), len(asr_chars) - 1))
        return asr_chars[asr_position][2 if end else 1] * args.asr_time_scale

    cues: list[dict[str, Any]] = []
    script_cursor = 0
    for chunk in chunks:
        length = len(chunk["plain"])
        scene_start, scene_end = scene_windows[chunk["scene_id"]]
        start = max(scene_start, mapped_time(script_cursor))
        end = min(scene_end, mapped_time(script_cursor + length - 1, end=True))
        if cues and start < float(cues[-1]["end"]):
            start = float(cues[-1]["end"])
        if end <= start:
            end = min(scene_end, start + max(0.8, length / 6.0))
        cues.append(
            {
                "start": round(start, 3),
                "end": round(end, 3),
                "text": chunk["text"],
                "sceneId": chunk["scene_id"],
                "timingSource": "asr-aligned-to-script",
                "confidence": round(match_ratio, 4),
            }
        )
        script_cursor += length

    output_json = Path(args.output_json)
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(
        json.dumps(
            {
                "captions": cues,
                "timingSource": "asr-aligned-to-script",
                "alignmentScore": round(match_ratio, 4),
                "durationSec": round(cursor, 3),
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    output_srt = Path(args.output_srt)
    output_srt.parent.mkdir(parents=True, exist_ok=True)
    write_srt(output_srt, cues)
    print(json.dumps({"cues": len(cues), "alignmentScore": round(match_ratio, 4)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
