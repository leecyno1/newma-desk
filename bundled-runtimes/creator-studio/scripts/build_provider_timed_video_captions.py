#!/usr/bin/env python3
"""Build an audio-driven storyboard and display captions from per-scene TTS files."""

from __future__ import annotations

import argparse
import copy
import json
import re
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any

from video_tts_pronunciation import normalize_tts_text


SRT_BLOCK = re.compile(
    r"(?:^|\n)(\d+)\s*\n"
    r"(\d{2}:\d{2}:\d{2},\d{3})\s+-->\s+(\d{2}:\d{2}:\d{2},\d{3})\s*\n"
    r"(.*?)(?=\n\s*\n|\Z)",
    re.S,
)


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def srt_seconds(value: str) -> float:
    hour, minute, tail = value.split(":")
    second, millisecond = tail.split(",")
    return int(hour) * 3600 + int(minute) * 60 + int(second) + int(millisecond) / 1000


def format_srt_time(seconds: float) -> str:
    milliseconds = max(0, int(round(seconds * 1000)))
    hour, remainder = divmod(milliseconds, 3_600_000)
    minute, remainder = divmod(remainder, 60_000)
    second, millisecond = divmod(remainder, 1000)
    return f"{hour:02d}:{minute:02d}:{second:02d},{millisecond:03d}"


def parse_srt(path: Path) -> list[dict[str, Any]]:
    text = path.read_text(encoding="utf-8-sig").strip()
    return [
        {
            "start_sec": srt_seconds(start),
            "end_sec": srt_seconds(end),
            "provider_text": re.sub(r"\s+", " ", body).strip(),
        }
        for _index, start, end, body in SRT_BLOCK.findall(text)
    ]


def audio_duration(path: Path) -> float:
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return float(result.stdout.strip())


def scene_tail(scene: dict[str, Any]) -> float:
    content_part = str(scene.get("content_part") or "")
    if content_part == "closing_outro":
        return 0.60
    if content_part == "chapter_divider":
        return 0.50
    if content_part in {"data_table", "financial_chart", "news_or_document"}:
        return 0.45
    return 0.35


def clauses(text: str) -> list[str]:
    parts = [item.strip() for item in re.split(r"(?<=[。！？!?;；])", text) if item.strip()]
    return parts or [text.strip()]


def expand_clauses(parts: list[str], target: int) -> list[str]:
    expanded = list(parts)
    while len(expanded) < target:
        index = max(range(len(expanded)), key=lambda item: len(expanded[item]))
        source = expanded[index]
        candidates = [item.strip() for item in re.split(r"(?<=[，,])", source) if item.strip()]
        if len(candidates) < 2:
            midpoint = max(1, len(source) // 2)
            candidates = [source[:midpoint].strip(), source[midpoint:].strip()]
        expanded[index:index + 1] = [item for item in candidates if item]
    return expanded


def fit_display_text(text: str, provider_cues: list[dict[str, Any]]) -> list[str]:
    target = max(1, len(provider_cues))
    parts = expand_clauses(clauses(text), target)
    if len(parts) == target:
        return parts
    if target == 1:
        return ["".join(parts)]

    durations = [max(0.08, cue["end_sec"] - cue["start_sec"]) for cue in provider_cues]
    total_duration = sum(durations)
    total_chars = sum(len(item) for item in parts) or 1
    groups: list[str] = []
    cursor = 0
    consumed_chars = 0
    for index, duration in enumerate(durations):
        remaining_groups = target - index
        if remaining_groups == 1:
            groups.append("".join(parts[cursor:]))
            break
        target_chars = total_chars * sum(durations[: index + 1]) / total_duration
        group: list[str] = []
        while cursor < len(parts) - (remaining_groups - 1):
            group.append(parts[cursor])
            consumed_chars += len(parts[cursor])
            cursor += 1
            if consumed_chars >= target_chars:
                break
        groups.append("".join(group))
    return groups


def write_srt(path: Path, cues: list[dict[str, Any]]) -> None:
    rows: list[str] = []
    for index, cue in enumerate(cues, 1):
        rows.extend(
            [
                str(index),
                f"{format_srt_time(cue['start_sec'])} --> {format_srt_time(cue['end_sec'])}",
                str(cue["text"]),
                "",
            ]
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(rows).strip() + "\n", encoding="utf-8")


def build_master_audio(rows: list[dict[str, Any]], output: Path) -> None:
    command = ["ffmpeg", "-y", "-loglevel", "error"]
    filters: list[str] = []
    concat_inputs: list[str] = []
    for index, row in enumerate(rows):
        command.extend(["-i", str(row["audio_path"])])
        filters.append(f"[{index}:a]apad=pad_dur={float(row['tail_sec']):.3f}[a{index}]")
        concat_inputs.append(f"[a{index}]")
    filters.append(f"{''.join(concat_inputs)}concat=n={len(rows)}:v=0:a=1[outa]")
    output.parent.mkdir(parents=True, exist_ok=True)
    command.extend(
        [
            "-filter_complex",
            ";".join(filters),
            "-map",
            "[outa]",
            "-ar",
            "32000",
            "-ac",
            "1",
            "-c:a",
            "pcm_s16le",
            str(output),
        ]
    )
    subprocess.run(command, check=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--storyboard", required=True)
    parser.add_argument("--audio-dir", required=True)
    parser.add_argument("--output-storyboard", required=True)
    parser.add_argument("--output-captions-json", required=True)
    parser.add_argument("--output-captions-srt", required=True)
    parser.add_argument("--output-timing-manifest", required=True)
    parser.add_argument("--output-master-audio", default="")
    parser.add_argument("--provider", default="minimax_cli")
    parser.add_argument("--model", default="speech-02-hd")
    parser.add_argument("--voice", default="tianxin_xiaoling")
    parser.add_argument("--speed", type=float, default=1.1)
    args = parser.parse_args()

    storyboard_path = Path(args.storyboard).expanduser().resolve()
    audio_dir = Path(args.audio_dir).expanduser().resolve()
    storyboard = read_json(storyboard_path)
    timed = copy.deepcopy(storyboard)
    global_cues: list[dict[str, Any]] = []
    timing_rows: list[dict[str, Any]] = []
    cursor = 0.0

    for index, scene in enumerate(timed.get("scenes") or [], 1):
        scene_id = str(scene.get("id") or scene.get("scene_id") or f"scene_{index:03d}")
        wav = audio_dir / f"{scene_id}.wav"
        source_srt = audio_dir / f"{scene_id}.srt"
        if not wav.exists() or not source_srt.exists():
            raise FileNotFoundError(f"Missing provider audio/SRT for {scene_id}")

        voice_duration = audio_duration(wav)
        provider_cues = parse_srt(source_srt)
        display_texts = fit_display_text(str(scene.get("narration") or scene.get("title") or ""), provider_cues)
        tail = scene_tail(scene)
        scene_start = cursor
        scene_end = scene_start + voice_duration + tail
        local_cues: list[dict[str, Any]] = []
        for cue_index, (provider_cue, display_text) in enumerate(zip(provider_cues, display_texts), 1):
            local_start = min(voice_duration, provider_cue["start_sec"])
            local_end = min(voice_duration, max(local_start + 0.08, provider_cue["end_sec"]))
            cue = {
                "id": f"{scene_id}_caption_{cue_index:02d}",
                "scene_id": scene_id,
                "text": display_text,
                "start_sec": round(scene_start + local_start, 3),
                "end_sec": round(scene_start + local_end, 3),
                "local_start_sec": round(local_start, 3),
                "local_end_sec": round(local_end, 3),
                "timing_source": "minimax_provider_srt",
            }
            local_cues.append(cue)
            global_cues.append(cue)

        scene.update(
            {
                "start_sec": round(scene_start, 3),
                "end_sec": round(scene_end, 3),
                "duration_sec": round(scene_end - scene_start, 3),
                "narration_tts": normalize_tts_text(str(scene.get("narration") or "")),
                "voice_audio": str(wav),
                "provider_subtitles": str(source_srt),
                "caption_cues": local_cues,
                "audio_tail_sec": tail,
            }
        )
        timing_rows.append(
            {
                "scene_id": scene_id,
                "audio_path": str(wav),
                "provider_srt": str(source_srt),
                "voice_duration_sec": round(voice_duration, 3),
                "tail_sec": tail,
                "scene_duration_sec": round(scene_end - scene_start, 3),
                "caption_count": len(local_cues),
            }
        )
        cursor = scene_end

    timed["duration_estimate_sec"] = round(cursor, 3)
    timed["status"] = "audio_timed"
    timed["timeline_alignment"] = {
        "schema_version": "dasheng.video.timeline_alignment.v1",
        "mode": "audio_driven_per_scene",
        "source_storyboard": str(storyboard_path),
        "input_duration_sec": storyboard.get("duration_estimate_sec"),
        "output_duration_sec": round(cursor, 3),
        "global_scale": False,
        "subtitle_timing_source": "minimax_provider_srt",
    }
    timed["voice"] = {
        **(timed.get("voice") if isinstance(timed.get("voice"), dict) else {}),
        "provider": args.provider,
        "model": args.model,
        "voice": args.voice,
        "speed": args.speed,
        "sample_rate": 32000,
    }

    write_json(Path(args.output_storyboard).expanduser().resolve(), timed)
    write_json(Path(args.output_captions_json).expanduser().resolve(), {"cues": global_cues})
    write_srt(Path(args.output_captions_srt).expanduser().resolve(), global_cues)
    master_audio = Path(args.output_master_audio).expanduser().resolve() if args.output_master_audio else None
    if master_audio:
        build_master_audio(timing_rows, master_audio)
    write_json(
        Path(args.output_timing_manifest).expanduser().resolve(),
        {
            "schema_version": "dasheng.video.voice_timing_manifest.v1",
            "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
            "provider": args.provider,
            "model": args.model,
            "voice": args.voice,
            "speed": args.speed,
            "scene_count": len(timing_rows),
            "total_duration_sec": round(cursor, 3),
            "subtitle_timing_source": "minimax_provider_srt",
            "master_audio": str(master_audio) if master_audio else "",
            "scenes": timing_rows,
        },
    )
    print(json.dumps({"scene_count": len(timing_rows), "duration_sec": round(cursor, 3), "caption_count": len(global_cues)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
