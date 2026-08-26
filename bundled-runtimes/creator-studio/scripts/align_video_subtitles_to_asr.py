#!/usr/bin/env python3
"""Backfill Remotion scene captions with ASR timings while keeping script text.

This is for Newma video review/final renders where TTS has real pauses that
make text-length subtitle timing drift. The ASR transcript supplies timestamps;
the existing voiceover/script captions remain the display text.
"""

from __future__ import annotations

import argparse
import difflib
import json
import re
from pathlib import Path
from typing import Any


def to_simplified(text: str) -> str:
    try:
        import opencc  # type: ignore

        return opencc.OpenCC("t2s").convert(text)
    except Exception:
        return text


def plain(text: str) -> str:
    text = to_simplified(text).replace("—", "-").replace("–", "-")
    return "".join(re.findall(r"[\u4e00-\u9fffA-Za-z0-9%]+", text))


def format_srt_time(sec: float) -> str:
    ms = int(round(sec * 1000))
    h, rem = divmod(ms, 3_600_000)
    m, rem = divmod(rem, 60_000)
    s, milli = divmod(rem, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{milli:03d}"


def load_asr_char_timeline(asr_json: Path) -> tuple[str, list[tuple[str, float, float]]]:
    data = json.loads(asr_json.read_text(encoding="utf-8"))
    chars: list[tuple[str, float, float]] = []
    for segment in data.get("segments", []):
        segment_plain = plain(str(segment.get("text", "")))
        if not segment_plain:
            continue
        start = float(segment["start"])
        end = float(segment["end"])
        length = len(segment_plain)
        for idx, ch in enumerate(segment_plain):
            chars.append(
                (
                    ch,
                    start + (end - start) * idx / length,
                    start + (end - start) * (idx + 1) / length,
                )
            )
    return "".join(ch for ch, _, _ in chars), chars


def collect_script_chunks(video_data: dict[str, Any]) -> list[dict[str, Any]]:
    chunks: list[dict[str, Any]] = []
    for scene in video_data["scenes"]:
        for caption in scene.get("captions", []):
            text = str(caption["text"]).strip()
            if text:
                chunks.append({"scene": int(scene["index"]), "text": text, "plain": plain(text)})
    return chunks


def build_position_mapper(script_plain: str, asr_plain: str) -> tuple[float, Any]:
    matcher = difflib.SequenceMatcher(a=script_plain, b=asr_plain, autojunk=False)
    map_a_to_b: dict[int, int] = {}
    for tag, i1, i2, j1, _j2 in matcher.get_opcodes():
        if tag == "equal":
            for offset in range(i2 - i1):
                map_a_to_b[i1 + offset] = j1 + offset
    mapped_positions = sorted(map_a_to_b)

    def b_for_a(pos: int) -> int:
        if pos in map_a_to_b:
            return map_a_to_b[pos]
        if not mapped_positions:
            return int(pos * len(asr_plain) / max(1, len(script_plain)))
        import bisect

        idx = bisect.bisect_left(mapped_positions, pos)
        if idx == 0:
            return max(0, map_a_to_b[mapped_positions[0]] - (mapped_positions[0] - pos))
        if idx == len(mapped_positions):
            return min(len(asr_plain) - 1, map_a_to_b[mapped_positions[-1]] + (pos - mapped_positions[-1]))
        a0, a1 = mapped_positions[idx - 1], mapped_positions[idx]
        b0, b1 = map_a_to_b[a0], map_a_to_b[a1]
        ratio = (pos - a0) / max(1, a1 - a0)
        return round(b0 + (b1 - b0) * ratio)

    return matcher.ratio(), b_for_a


def build_aligned_cues(video_data: dict[str, Any], asr_json: Path) -> tuple[list[dict[str, Any]], float]:
    asr_plain, asr_chars = load_asr_char_timeline(asr_json)
    chunks = collect_script_chunks(video_data)
    script_plain = "".join(chunk["plain"] for chunk in chunks)
    match_ratio, b_for_a = build_position_mapper(script_plain, asr_plain)

    def time_for_script_pos(pos: int, *, end: bool = False) -> float:
        pos = max(0, min(pos, len(script_plain) - 1))
        b_pos = max(0, min(b_for_a(pos), len(asr_chars) - 1))
        return asr_chars[b_pos][2 if end else 1]

    cues: list[dict[str, Any]] = []
    cursor = 0
    for chunk in chunks:
        plain_len = len(chunk["plain"])
        if plain_len == 0:
            continue
        start = time_for_script_pos(cursor)
        end = time_for_script_pos(cursor + plain_len - 1, end=True)
        if cues and start < cues[-1]["endSec"] - 0.03:
            start = cues[-1]["endSec"]
        if end <= start:
            end = start + max(0.5, plain_len / 8.0)
        cues.append(
            {
                "scene": int(chunk["scene"]),
                "text": chunk["text"],
                "startSec": round(start, 3),
                "endSec": round(end, 3),
            }
        )
        cursor += plain_len

    for idx, cue in enumerate(cues):
        if idx + 1 < len(cues):
            next_start = cues[idx + 1]["startSec"]
            if cue["endSec"] > next_start:
                cue["endSec"] = round(max(cue["startSec"] + 0.08, next_start - 0.02), 3)
        if cue["endSec"] - cue["startSec"] < 0.45:
            cue["endSec"] = round(cue["startSec"] + 0.45, 3)
    return cues, match_ratio


def write_srt(path: Path, cues: list[dict[str, Any]]) -> None:
    rows: list[str] = []
    for idx, cue in enumerate(cues, 1):
        rows.extend(
            [
                str(idx),
                f"{format_srt_time(float(cue['startSec']))} --> {format_srt_time(float(cue['endSec']))}",
                str(cue["text"]),
                "",
            ]
        )
    path.write_text("\n".join(rows).strip() + "\n", encoding="utf-8")


def apply_scene_captions(video_data: dict[str, Any], cues: list[dict[str, Any]], speed: float, match_ratio: float) -> None:
    scene_starts: dict[int, float] = {}
    cursor = 0.0
    for scene in video_data["scenes"]:
        scene_starts[int(scene["index"])] = cursor
        scene["captions"] = []
        cursor += float(scene["durationSec"])

    scenes_by_index = {int(scene["index"]): scene for scene in video_data["scenes"]}
    for cue in cues:
        scene = scenes_by_index.get(int(cue["scene"]))
        if scene is None:
            continue
        scene_start = scene_starts[int(cue["scene"])]
        start_ms = round((float(cue["startSec"]) * speed - scene_start) * 1000)
        end_ms = round((float(cue["endSec"]) * speed - scene_start) * 1000)
        duration_ms = round(float(scene["durationSec"]) * 1000)
        start_ms = max(0, min(start_ms, duration_ms - 1))
        end_ms = max(start_ms + 80, min(end_ms, duration_ms))
        scene["captions"].append(
            {
                "text": cue["text"],
                "startMs": start_ms,
                "endMs": end_ms,
                "timestampMs": start_ms,
                "confidence": round(match_ratio, 3),
                "timingSource": "asr-aligned-to-script",
            }
        )

    for scene in video_data["scenes"]:
        if scene["captions"]:
            scene["caption"] = scene["captions"][0]["text"]
    video_data["subtitleTimingSource"] = "asr-aligned-to-script"
    video_data["subtitleAlignmentScore"] = round(match_ratio, 4)


def main() -> int:
    parser = argparse.ArgumentParser(description="Align Newma Remotion subtitles to ASR timing.")
    parser.add_argument("--project-dir", required=True, help="Remotion project directory containing data/strict_video_data.json")
    parser.add_argument("--asr-json", required=True, help="Whisper-style JSON with segments/start/end/text")
    parser.add_argument("--speed", type=float, default=1.2, help="Final speed multiplier used after Remotion render")
    parser.add_argument("--write", action="store_true", help="Update strict_video_data.json with aligned local scene captions")
    args = parser.parse_args()

    project_dir = Path(args.project_dir)
    data_path = project_dir / "data" / "strict_video_data.json"
    video_data = json.loads(data_path.read_text(encoding="utf-8"))
    cues, match_ratio = build_aligned_cues(video_data, Path(args.asr_json))

    out_dir = project_dir / "render" / "asr_captions"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "captions_asr_aligned_script.json").write_text(
        json.dumps(cues, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    write_srt(out_dir / "captions_asr_aligned_script.srt", cues)
    (project_dir / "captions_full_1p2x.json").write_text(
        json.dumps(cues, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    write_srt(project_dir / "captions_full_1p2x.srt", cues)

    if args.write:
        apply_scene_captions(video_data, cues, args.speed, match_ratio)
        data_path.write_text(json.dumps(video_data, ensure_ascii=False, indent=2), encoding="utf-8")

    print(json.dumps({"cues": len(cues), "matchRatio": round(match_ratio, 4), "wroteData": args.write}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
