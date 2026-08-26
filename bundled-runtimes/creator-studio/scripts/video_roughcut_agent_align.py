#!/usr/bin/env python3
from __future__ import annotations

import argparse
import difflib
import json
import math
import re
import subprocess
from pathlib import Path
from typing import Any


AUDIO_ENHANCE_FILTER = (
    "highpass=f=80,"
    "lowpass=f=12000,"
    "afftdn=nf=-25,"
    "dynaudnorm=f=150:g=15:p=0.95,"
    "acompressor=threshold=-18dB:ratio=2.5:attack=5:release=80,"
    "loudnorm=I=-14:LRA=8:TP=-1.0,"
    "alimiter=limit=0.95"
)
FILLER_PATTERN = re.compile(r"(呃+|嗯+|啊+|额+|这个|那个|一个|就是|其实|然后|的话|呢|吧|对吧|知道吧)")


def run(cmd: list[str], *, capture: bool = False) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        text=True,
        stdout=subprocess.PIPE if capture else None,
        stderr=subprocess.PIPE if capture else None,
        check=True,
    )


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def ffprobe_duration(path: Path) -> float:
    result = run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=nk=1:nw=1",
            str(path),
        ],
        capture=True,
    )
    return float(result.stdout.strip())


def format_ts(seconds: float) -> str:
    seconds = max(0.0, seconds)
    ms = int(round((seconds - math.floor(seconds)) * 1000))
    total = int(math.floor(seconds))
    if ms == 1000:
        total += 1
        ms = 0
    h = total // 3600
    m = (total % 3600) // 60
    s = total % 60
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def load_segments(path: Path) -> list[dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    out = []
    for idx, item in enumerate(data, 1):
        out.append(
            {
                "id": idx,
                "start": float(item["start"]),
                "end": float(item["end"]),
                "text": str(item.get("text") or ""),
            }
        )
    return out


def load_funasr_timeline(path: Path | None) -> list[dict[str, Any]]:
    if not path:
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    raw = payload.get("raw", payload) if isinstance(payload, dict) else payload
    if not isinstance(raw, dict):
        return []
    text = str(raw.get("text") or "")
    timestamps = raw.get("timestamp") or []
    timeline = []
    ts_idx = 0
    last_end = 0.0
    for char in text:
        if re.fullmatch(r"[，。！？、,.!?；;：:\s]", char):
            timeline.append({"char": char, "start": last_end, "end": last_end, "punct": True})
            continue
        if ts_idx >= len(timestamps):
            continue
        start, end = timestamps[ts_idx]
        ts_idx += 1
        last_end = float(end) / 1000
        timeline.append({"char": char, "start": float(start) / 1000, "end": last_end, "punct": False})
    return timeline


def compact_text(text: str) -> str:
    return "".join(ch for ch in text if ch.strip())


def diff_delete_ranges(segment: dict[str, Any], edited_text: str) -> list[dict[str, Any]]:
    original = compact_text(segment["text"])
    edited = compact_text(edited_text)
    if not original or not edited or original == edited:
        return []
    matcher = difflib.SequenceMatcher(a=original, b=edited, autojunk=False)
    ranges = []
    total_chars = max(1, len(original))
    duration = max(0.001, segment["end"] - segment["start"])
    for tag, i1, i2, _j1, _j2 in matcher.get_opcodes():
        if tag != "delete":
            continue
        start = segment["start"] + duration * (i1 / total_chars)
        end = segment["start"] + duration * (i2 / total_chars)
        if end - start >= 0.16:
            ranges.append(
                {
                    "start": round(start, 3),
                    "end": round(end, 3),
                    "reason": "agent_text_alignment_delete",
                    "text": original[i1:i2],
                    "segment_id": segment["id"],
                    "default": True,
                }
            )
    return ranges


def timeline_text(timeline: list[dict[str, Any]]) -> str:
    return "".join(item["char"] for item in timeline if not item.get("punct"))


def find_timeline_window(timeline: list[dict[str, Any]], segment: dict[str, Any]) -> list[dict[str, Any]]:
    start = float(segment["start"])
    end = float(segment["end"])
    return [
        item
        for item in timeline
        if not item.get("punct") and item["end"] >= start - 0.05 and item["start"] <= end + 0.05
    ]


def timeline_diff_delete_ranges(
    segment: dict[str, Any],
    edited_text: str,
    timeline: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    window = find_timeline_window(timeline, segment)
    original = timeline_text(window)
    edited = compact_text(edited_text)
    if not original or not edited or original == edited:
        return []
    matcher = difflib.SequenceMatcher(a=original, b=edited, autojunk=False)
    ranges = []
    for tag, i1, i2, _j1, _j2 in matcher.get_opcodes():
        if tag != "delete" or i2 <= i1 or i2 > len(window):
            continue
        start = float(window[i1]["start"])
        end = float(window[i2 - 1]["end"])
        if end - start >= 0.08:
            ranges.append(
                {
                    "start": round(start, 3),
                    "end": round(end, 3),
                    "reason": "agent_timeline_text_delete",
                    "text": original[i1:i2],
                    "segment_id": segment["id"],
                    "default": True,
                }
            )
    return ranges


def filler_delete_ranges(segments: list[dict[str, Any]], timeline: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not timeline:
        return []
    ranges = []
    for seg in segments:
        window = find_timeline_window(timeline, seg)
        text = timeline_text(window)
        if not text:
            continue
        for match in FILLER_PATTERN.finditer(text):
            # Avoid deleting every discourse marker blindly; only short standalone filler runs.
            start_idx, end_idx = match.span()
            token = match.group(0)
            if token in {"一个", "其实"} and len(text) > 14:
                continue
            if end_idx > len(window) or start_idx >= len(window):
                continue
            start = float(window[start_idx]["start"])
            end = float(window[end_idx - 1]["end"])
            if 0.08 <= end - start <= 1.2:
                ranges.append(
                    {
                        "start": round(start, 3),
                        "end": round(end, 3),
                        "reason": "filler_word_timeline",
                        "text": token,
                        "segment_id": seg["id"],
                        "default": False,
                    }
                )
    return ranges


def merge_ranges(ranges: list[dict[str, Any]], duration: float, gap: float = 0.08) -> list[dict[str, Any]]:
    clean = []
    for item in ranges:
        start = max(0.0, min(duration, float(item["start"])))
        end = max(0.0, min(duration, float(item["end"])))
        if end - start >= 0.16:
            clean.append({**item, "start": start, "end": end})
    clean.sort(key=lambda item: (item["start"], item["end"]))
    merged: list[dict[str, Any]] = []
    for item in clean:
        if not merged or item["start"] > merged[-1]["end"] + gap:
            merged.append(dict(item))
            continue
        merged[-1]["end"] = max(merged[-1]["end"], item["end"])
        merged[-1]["reason"] = "+".join(
            x
            for x in [str(merged[-1].get("reason") or ""), str(item.get("reason") or "")]
            if x
        )
        if item.get("text"):
            merged[-1]["text"] = (str(merged[-1].get("text") or "") + " " + str(item["text"])).strip()
    return merged


def build_deletes(
    segments: list[dict[str, Any]],
    plan: dict[str, Any],
    duration: float,
    timeline: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    by_id = {int(seg["id"]): seg for seg in segments}
    ranges: list[dict[str, Any]] = []
    for item in plan.get("delete_ranges") or []:
        if item.get("default", True) is not False:
            ranges.append({**item, "default": item.get("default", True)})
    if plan.get("delete_filler_words"):
        ranges.extend(filler_delete_ranges(segments, timeline))
    for edit in plan.get("segments") or []:
        seg_id = int(edit.get("id") or edit.get("segment_id") or 0)
        seg = by_id.get(seg_id)
        if not seg:
            continue
        action = str(edit.get("action") or "keep")
        if action == "drop":
            ranges.append(
                {
                    "start": seg["start"],
                    "end": seg["end"],
                    "reason": edit.get("reason", "agent_drop_segment"),
                    "text": seg["text"],
                    "segment_id": seg_id,
                    "default": True,
                }
            )
        elif action in {"rewrite", "keep"} and edit.get("edited_text") and edit.get("cut_text_diff"):
            if timeline:
                ranges.extend(timeline_diff_delete_ranges(seg, str(edit["edited_text"]), timeline))
            else:
                ranges.extend(diff_delete_ranges(seg, str(edit["edited_text"])))
    return merge_ranges(ranges, duration)


def build_keeps(deletes: list[dict[str, Any]], duration: float) -> list[dict[str, float]]:
    keeps = []
    cursor = 0.0
    for item in deletes:
        start = float(item["start"])
        end = float(item["end"])
        if start > cursor:
            keeps.append({"start": cursor, "end": start})
        cursor = max(cursor, end)
    if cursor < duration:
        keeps.append({"start": cursor, "end": duration})
    return [item for item in keeps if item["end"] - item["start"] >= 0.25]


def map_time(t: float, deletes: list[dict[str, Any]]) -> float | None:
    removed = 0.0
    for item in deletes:
        start = float(item["start"])
        end = float(item["end"])
        if t >= end:
            removed += end - start
            continue
        if start <= t < end:
            return None
        break
    return max(0.0, t - removed)


def select_expression(keeps: list[dict[str, float]]) -> str:
    if not keeps:
        raise ValueError("At least one keep range is required")
    return "+".join(
        f"between(t\\,{float(keep['start']):.6f}\\,{float(keep['end']):.6f})"
        for keep in keeps
    )


def timestamp_rebuild_expression(keeps: list[dict[str, float]]) -> str:
    gap_terms = []
    for previous, current in zip(keeps, keeps[1:]):
        gap = max(0.0, float(current["start"]) - float(previous["end"]))
        if gap <= 0:
            continue
        gap_terms.append(f"gte(T\\,{float(current['start']):.6f})*{gap:.6f}")
    if not gap_terms:
        return "PTS-STARTPTS"
    return f"(PTS-STARTPTS)-({'+'.join(gap_terms)})/TB"


def render_video(source: Path, keeps: list[dict[str, float]], output: Path, work_dir: Path) -> None:
    # Repeated concat-demuxer in/out points on AAC sources can accumulate decoder
    # priming samples. Select once from the original streams and rebuild both
    # timelines so the consolidated rough cut stays sample-accurate.
    expression = select_expression(keeps)
    rebuilt_pts = timestamp_rebuild_expression(keeps)
    filter_complex = (
        f"[0:v:0]select={expression},setpts={rebuilt_pts}[v];"
        f"[0:a:0]aselect={expression},asetpts={rebuilt_pts},"
        f"aresample=48000,{AUDIO_ENHANCE_FILTER}[a]"
    )
    write_json(
        work_dir / "agent_render_timeline.json",
        {
            "method": "single_decode_select_and_timestamp_rebuild",
            "keep_ranges": keeps,
            "expected_duration_sec": round(
                sum(float(keep["end"]) - float(keep["start"]) for keep in keeps),
                3,
            ),
        },
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-i",
            str(source),
            "-filter_complex",
            filter_complex,
            "-map",
            "[v]",
            "-map",
            "[a]",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "20",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-ar",
            "48000",
            "-movflags",
            "+faststart",
            str(output),
        ]
    )


def plan_text_for_segment(plan: dict[str, Any], seg: dict[str, Any]) -> str:
    for edit in plan.get("segments") or []:
        seg_id = int(edit.get("id") or edit.get("segment_id") or 0)
        if seg_id == seg["id"] and edit.get("edited_text"):
            return str(edit["edited_text"]).strip()
    return seg["text"].strip()


def write_srt(path: Path, segments: list[dict[str, Any]], deletes: list[dict[str, Any]], plan: dict[str, Any]) -> None:
    rows = []
    idx = 1
    last_end = 0.0
    for seg in segments:
        center = (seg["start"] + seg["end"]) / 2
        if any(float(item["start"]) <= center < float(item["end"]) for item in deletes):
            continue
        start = map_time(seg["start"], deletes)
        end = map_time(seg["end"], deletes)
        if start is None or end is None or end <= start:
            continue
        if start < last_end + 0.04:
            start = last_end + 0.04
        if end <= start:
            end = start + 0.65
        text = plan_text_for_segment(plan, seg)
        if not text:
            continue
        rows.extend([str(idx), f"{format_ts(start)} --> {format_ts(end)}", text, ""])
        last_end = end
        idx += 1
    path.write_text("\n".join(rows).rstrip() + "\n", encoding="utf-8")


def mux_softsub(video: Path, srt: Path, output: Path) -> None:
    run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-i",
            str(video),
            "-i",
            str(srt),
            "-map",
            "0:v",
            "-map",
            "0:a",
            "-map",
            "1:0",
            "-c:v",
            "copy",
            "-c:a",
            "copy",
            "-c:s",
            "mov_text",
            "-metadata:s:s:0",
            "language=chi",
            "-movflags",
            "+faststart",
            str(output),
        ]
    )


def write_agent_input(path: Path, segments: list[dict[str, Any]]) -> None:
    lines = [
        "# Agent 口播稿整理输入",
        "",
        "请按原口播顺序整理，不要重构文章。可以删除重复试讲、口水句、明显口误；可以修正字幕文字。",
        "输出 JSON：`segments` 数组，每项包含 `id`、`action`（keep/drop/rewrite）、`edited_text`、`reason`。",
        "默认 `edited_text` 只用于字幕文本校正，不剪视频。",
        "只有明确设置 `cut_text_diff: true` 的分段，才会按整理稿差异反推删除视频。",
        "如果希望脚本尝试删字级口水词，可加 `delete_filler_words: true`，但仍建议人工复核。",
        "",
    ]
    for seg in segments:
        lines.append(f"{seg['id']:03d} {seg['start']:.3f}-{seg['end']:.3f} {seg['text']}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Render rough cut from Agent-cleaned transcript alignment")
    parser.add_argument("--source-video", required=True)
    parser.add_argument("--segments-json", required=True)
    parser.add_argument("--agent-plan")
    parser.add_argument("--funasr-raw")
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()

    source = Path(args.source_video).expanduser().resolve()
    segments_path = Path(args.segments_json).expanduser().resolve()
    out_dir = Path(args.output_dir).expanduser().resolve()
    work_dir = out_dir / "work"
    final_dir = out_dir / "final"
    segments = load_segments(segments_path)
    timeline = load_funasr_timeline(Path(args.funasr_raw).expanduser().resolve() if args.funasr_raw else None)
    duration = ffprobe_duration(source)

    if not args.agent_plan:
        write_agent_input(out_dir / "agent_refine_input.md", segments)
        write_json(
            out_dir / "agent_refine_plan.template.json",
            {"delete_filler_words": False, "segments": [], "delete_ranges": []},
        )
        print(json.dumps({"status": "needs_agent_plan", "agent_input": str(out_dir / "agent_refine_input.md")}, ensure_ascii=False, indent=2))
        return

    plan_path = Path(args.agent_plan).expanduser().resolve()
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    deletes = build_deletes(segments, plan, duration, timeline)
    keeps = build_keeps(deletes, duration)
    write_json(work_dir / "agent_delete_segments.json", deletes)
    write_json(work_dir / "agent_keep_segments.json", keeps)

    video_out = final_dir / f"{source.stem}_agent_refined.mp4"
    srt_out = final_dir / f"{source.stem}_agent_refined.srt"
    softsub_out = final_dir / f"{source.stem}_agent_refined_softsub.mp4"
    render_video(source, keeps, video_out, work_dir)
    write_srt(srt_out, segments, deletes, plan)
    mux_softsub(video_out, srt_out, softsub_out)
    manifest = {
        "status": "rendered",
        "source_video": str(source),
        "source_duration_sec": round(duration, 3),
        "agent_plan": str(plan_path),
        "delete_count": len(deletes),
        "timeline_char_count": len(timeline),
        "removed_duration_sec": round(sum(float(item["end"]) - float(item["start"]) for item in deletes), 3),
        "video": str(video_out),
        "srt": str(srt_out),
        "softsub_video": str(softsub_out),
        "duration_sec": round(ffprobe_duration(video_out), 3),
        "audio_filter": AUDIO_ENHANCE_FILTER,
    }
    write_json(out_dir / "agent_refined_manifest.json", manifest)
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
