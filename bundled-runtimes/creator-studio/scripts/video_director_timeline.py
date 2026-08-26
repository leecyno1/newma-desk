#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
import re
import subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from video_driver_rules import (
    audio_for_beat,
    classify_beat,
    load_driver_rules,
    score_driver,
    talking_head_shot_for_beat,
    transition_for_beat,
    weighted_driver_score,
)
from video_timeline_edl import alignment_report, build_keep_segments, read_json as read_edl_json, remap_interval

SRT_TIME_RE = re.compile(
    r"(?P<h>\d{2}):(?P<m>\d{2}):(?P<s>\d{2}),(?P<ms>\d{3})"
)
SENTENCE_END_RE = re.compile(r"[。！？!?；;]$")
DATA_RE = re.compile(r"[\d０-９]+|%|％|万亿|亿美元|人民币|指数|利率|IPO|Capex|GDP", re.I)
CAPTION_TOKEN_RE = re.compile(r"[A-Za-z]+(?:[-'][A-Za-z]+)*|\d+(?:\.\d+)?%?|.", re.S)
SOFT_BREAK_TOKENS = set("，。！？；：、,.!?;:")


@dataclass
class Caption:
    start: float
    end: float
    text: str

    @property
    def duration(self) -> float:
        return max(0.0, self.end - self.start)


def run_ffprobe_duration(path: Path) -> float | None:
    if not path.exists():
        return None
    proc = subprocess.run(
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
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if proc.returncode != 0:
        return None
    try:
        return float(proc.stdout.strip())
    except ValueError:
        return None


def parse_srt_time(value: str) -> float:
    match = SRT_TIME_RE.fullmatch(value.strip())
    if not match:
        raise ValueError(f"invalid SRT time: {value}")
    return (
        int(match.group("h")) * 3600
        + int(match.group("m")) * 60
        + int(match.group("s"))
        + int(match.group("ms")) / 1000
    )


def load_srt(path: Path) -> list[Caption]:
    blocks = re.split(r"\n\s*\n", path.read_text(encoding="utf-8").strip())
    captions: list[Caption] = []
    for block in blocks:
        lines = [line.strip() for line in block.splitlines() if line.strip()]
        if len(lines) < 2 or "-->" not in lines[1]:
            continue
        start_raw, end_raw = [item.strip() for item in lines[1].split("-->", 1)]
        text = "".join(lines[2:]).strip()
        if text:
            captions.append(Caption(parse_srt_time(start_raw), parse_srt_time(end_raw), text))
    return captions


def load_captions_json(path: Path) -> list[Caption]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError("captions JSON must be a list")
    captions = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        text = str(item.get("text") or "").strip()
        if not text:
            continue
        captions.append(Caption(float(item["start"]), float(item["end"]), text))
    return captions


def remap_captions_to_roughcut(
    captions: list[Caption],
    edl_path: Path,
) -> tuple[list[Caption], dict[str, Any]]:
    keep_segments = build_keep_segments(read_edl_json(edl_path))
    mapped_captions: list[Caption] = []
    dropped = 0
    clipped = 0
    for caption in captions:
        mapped = remap_interval(caption.start, caption.end, keep_segments)
        if mapped is None:
            dropped += 1
            continue
        if mapped.clipped:
            clipped += 1
        mapped_captions.append(Caption(mapped.start, mapped.end, caption.text))
    return mapped_captions, alignment_report(
        keep_segments,
        dropped_count=dropped,
        clipped_count=clipped,
        item_label="caption",
        edl_path=str(edl_path),
    )


def normalize_space(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def split_long_caption(caption: Caption, max_sec: float = 4.2) -> list[Caption]:
    if caption.duration <= max_sec:
        return [caption]
    part_count = max(2, math.ceil(caption.duration / max_sec))
    tokens = [token for token in CAPTION_TOKEN_RE.findall(caption.text) if token]
    if len(tokens) < part_count:
        return [caption]

    cuts = [0]
    for index in range(1, part_count):
        ideal = round(len(tokens) * index / part_count)
        lower = max(cuts[-1] + 1, ideal - 4)
        upper = min(len(tokens) - (part_count - index), ideal + 4)
        punctuation = [
            candidate
            for candidate in range(lower, upper + 1)
            if tokens[candidate - 1] in SOFT_BREAK_TOKENS
        ]
        cuts.append(min(punctuation, key=lambda value: abs(value - ideal)) if punctuation else ideal)
    cuts.append(len(tokens))

    parts: list[Caption] = []
    duration = caption.duration
    for index, (left, right) in enumerate(zip(cuts, cuts[1:])):
        text = normalize_space("".join(tokens[left:right]))
        if not text:
            continue
        start = caption.start + duration * (left / len(tokens))
        end = caption.start + duration * (right / len(tokens))
        parts.append(Caption(start=start, end=end, text=text))
    return parts or [caption]


def group_captions(captions: list[Caption], min_sec: float = 1.6, max_sec: float = 4.2) -> list[Caption]:
    expanded = [
        part
        for caption in captions
        for part in split_long_caption(caption, max_sec=max_sec)
    ]
    groups: list[Caption] = []
    buf: list[Caption] = []

    def flush() -> None:
        nonlocal buf
        if not buf:
            return
        groups.append(
            Caption(
                start=buf[0].start,
                end=buf[-1].end,
                text=normalize_space("".join(item.text for item in buf)),
            )
        )
        buf = []

    for caption in expanded:
        if not buf:
            buf.append(caption)
            continue
        projected = caption.end - buf[0].start
        current_text = "".join(item.text for item in buf)
        if projected > max_sec:
            flush()
        buf.append(caption)
        current_duration = buf[-1].end - buf[0].start
        current_text = "".join(item.text for item in buf)
        if current_duration >= min_sec and SENTENCE_END_RE.search(current_text):
            flush()
    flush()
    return coalesce_short_groups([item for item in groups if item.duration >= 0.25], min_sec=min(2.0, min_sec))


def coalesce_short_groups(groups: list[Caption], min_sec: float = 2.0) -> list[Caption]:
    if not groups:
        return []
    out: list[Caption] = []
    for group in groups:
        if out and group.duration < min_sec:
            prev = out.pop()
            out.append(Caption(prev.start, group.end, normalize_space(prev.text + group.text)))
        else:
            out.append(group)
    if len(out) >= 2 and out[-1].duration < min_sec:
        tail = out.pop()
        prev = out.pop()
        out.append(Caption(prev.start, tail.end, normalize_space(prev.text + tail.text)))
    return out


def has_data_signal(text: str) -> bool:
    return bool(DATA_RE.search(text))


def choose_shot(index: int, beat: Caption, seconds_since_anchor: float) -> str:
    beat_class = classify_beat(beat.text, index=index)
    scores = score_driver(
        beat.text,
        beat_class=beat_class,
        duration=beat.duration,
        seconds_since_speaker=seconds_since_anchor,
        index=index,
        lane="talking_head",
    )
    return talking_head_shot_for_beat(
        beat_class,
        scores,
        seconds_since_speaker=seconds_since_anchor,
        index=index,
    )


def camera_for_shot(shot: str, index: int) -> dict[str, float]:
    if shot in {"talking_head_full", "speaker_full", "speaker_anchor", "speaker_return"}:
        return {"scale": 1.0, "x": 0.0, "y": 0.0}
    if shot in {"talking_head_punch_in", "claim_closeup"}:
        return {"scale": 1.06 + (index % 2) * 0.02, "x": -0.02, "y": 0.0}
    if shot == "broll_with_pip":
        return {"scale": 1.0, "x": 0.0, "y": 0.0}
    return {"scale": 1.02, "x": 0.0, "y": 0.0}


def overlay_for_shot(shot: str, beat: Caption) -> dict[str, Any]:
    if shot in {"chart_or_data_card", "chart_card"}:
        return {
            "type": "real_data_chart_or_table",
            "required": True,
            "position": "right_top_safe_area",
            "source_hint": beat.text[:80],
        }
    if shot in {"document_or_news_zoom", "document_zoom"}:
        return {
            "type": "source_document_or_news_card",
            "required": True,
            "position": "right_side_safe_area",
            "source_hint": beat.text[:80],
        }
    if shot == "html_logic_overlay":
        return {
            "type": "logic_chain_overlay",
            "required": True,
            "position": "right_side_safe_area",
            "source_hint": beat.text[:80],
        }
    if shot == "broll_with_pip":
        return {
            "type": "broll_or_html_sticker",
            "required": True,
            "position": "main_area_with_speaker_pip",
            "source_hint": beat.text[:80],
        }
    return {
        "type": "outline_progress",
        "required": False,
        "position": "left_top_safe_area",
    }


def composition_for_shot(shot: str, beat_class: str, index: int) -> dict[str, str]:
    if shot in {"speaker_anchor", "speaker_return", "speaker_full", "talking_head_full"}:
        return {
            "speaker_state": "full",
            "material_state": "none",
            "pip_shape": "none",
        }
    if shot in {"claim_closeup", "talking_head_punch_in"}:
        return {
            "speaker_state": "speaker_punch_in",
            "material_state": "transparent_overlay",
            "pip_shape": "nested_card",
        }
    if shot in {"chart_card", "chart_or_data_card"}:
        return {
            "speaker_state": "circle_pip" if index % 2 else "rounded_rect_pip",
            "material_state": "chart_fullscreen",
            "pip_shape": "circle" if index % 2 else "rounded_rect",
        }
    if shot in {"document_zoom", "document_or_news_zoom"}:
        return {
            "speaker_state": "circle_pip",
            "material_state": "document_fullscreen",
            "pip_shape": "circle",
        }
    if shot == "html_logic_overlay":
        return {
            "speaker_state": "half_right" if index % 2 else "half_left",
            "material_state": "split_screen",
            "pip_shape": "rounded_rect",
        }
    if shot == "broll_with_pip":
        return {
            "speaker_state": "circle_pip",
            "material_state": "evidence_fullscreen",
            "pip_shape": "circle",
        }
    return {
        "speaker_state": "full",
        "material_state": "transparent_overlay",
        "pip_shape": "none",
    }


def diversify_composition_if_repeated(
    composition: dict[str, str],
    recent: list[tuple[str, str, str]],
    *,
    index: int,
) -> dict[str, str]:
    key = (
        composition["speaker_state"],
        composition["material_state"],
        composition["pip_shape"],
    )
    if len(recent) < 2 or recent[-1] != key or recent[-2] != key:
        return composition

    material_state = composition["material_state"]
    if material_state in {"chart_fullscreen", "document_fullscreen", "evidence_fullscreen"}:
        variants = [
            {"speaker_state": "hidden", "material_state": material_state, "pip_shape": "none"},
            {"speaker_state": "rounded_rect_pip", "material_state": material_state, "pip_shape": "rounded_rect"},
            {"speaker_state": "circle_pip", "material_state": material_state, "pip_shape": "circle"},
        ]
        filtered = [item for item in variants if (item["speaker_state"], item["material_state"], item["pip_shape"]) != key]
        return filtered[index % len(filtered)]

    if material_state == "transparent_overlay":
        variants = [
            {"speaker_state": "full", "material_state": "transparent_overlay", "pip_shape": "none"},
            {"speaker_state": "speaker_punch_in", "material_state": "transparent_overlay", "pip_shape": "nested_card"},
            {"speaker_state": "half_right", "material_state": "split_screen", "pip_shape": "rounded_rect"},
        ]
        filtered = [item for item in variants if (item["speaker_state"], item["material_state"], item["pip_shape"]) != key]
        return filtered[index % len(filtered)]

    if material_state == "split_screen":
        return {
            "speaker_state": "rounded_rect_pip" if index % 2 else "circle_pip",
            "material_state": "evidence_fullscreen",
            "pip_shape": "rounded_rect" if index % 2 else "circle",
        }
    return composition


def html_animation_for_shot(shot: str, beat_class: str) -> str:
    if shot in {"chart_card", "chart_or_data_card"}:
        return "axis_draw_then_series_reveal_with_key_annotation"
    if shot in {"document_zoom", "document_or_news_zoom"}:
        return "document_push_zoom_with_marker_circle_and_paragraph_highlight"
    if shot == "html_logic_overlay":
        return "flow_arrow_step_reveal_with_active_node_highlight"
    if shot == "broll_with_pip":
        return "evidence_card_fly_in_then_source_marker_or_callout"
    if beat_class == "chapter":
        return "chapter_hit_title_reveal_then_fast_exit"
    if beat_class == "recap":
        return "outline_recap_collapse_to_final_sentence"
    return "keyword_type_on_with_static_callout_and_opacity_settle"


def transition_pair_for_shot(shot: str, beat_class: str, duration: float) -> dict[str, str]:
    transition = transition_for_beat(beat_class, lane="talking_head", duration=duration)
    if shot in {"chart_card", "chart_or_data_card"}:
        return {"transition_in": "data_reveal", "transition_out": "speaker_return_cut"}
    if shot in {"document_zoom", "document_or_news_zoom"}:
        return {"transition_in": "push_zoom", "transition_out": "speaker_return_cut"}
    if shot == "broll_with_pip":
        return {"transition_in": "circle_morph", "transition_out": "hard_cut"}
    if shot == "html_logic_overlay":
        return {"transition_in": "wipe_card", "transition_out": "path_highlight"}
    return {"transition_in": transition, "transition_out": "hard_cut"}


def build_talking_head_timeline(
    captions: list[Caption],
    *,
    title: str,
    source_video: str | None = None,
    duration: float | None = None,
    roughcut_gate: str | None = None,
    timeline_alignment: dict[str, Any] | None = None,
) -> dict[str, Any]:
    rules = load_driver_rules()
    beats = group_captions(captions)
    duration = duration or (max((caption.end for caption in captions), default=0.0))
    segments: list[dict[str, Any]] = []
    last_anchor_at = 0.0
    last_evidence_at = 0.0
    recent_compositions: list[tuple[str, str, str]] = []
    for index, beat in enumerate(beats, 1):
        seconds_since_speaker = beat.start - last_anchor_at
        seconds_since_evidence = beat.start - last_evidence_at
        beat_class = classify_beat(beat.text, index=index)
        driver_scores = score_driver(
            beat.text,
            beat_class=beat_class,
            duration=beat.duration,
            seconds_since_speaker=seconds_since_speaker,
            seconds_since_evidence=seconds_since_evidence,
            index=index,
            lane="talking_head",
        )
        shot = talking_head_shot_for_beat(
            beat_class,
            driver_scores,
            seconds_since_speaker=seconds_since_speaker,
            index=index,
        )
        if shot in {"speaker_anchor", "speaker_full", "speaker_return", "claim_closeup", "talking_head_full", "talking_head_punch_in"}:
            last_anchor_at = beat.start
        if beat_class in {"evidence_data", "evidence_document"} or shot in {"chart_card", "document_zoom", "html_logic_overlay"}:
            last_evidence_at = beat.start
        composition = diversify_composition_if_repeated(
            composition_for_shot(shot, beat_class, index),
            recent_compositions,
            index=index,
        )
        recent_compositions.append((composition["speaker_state"], composition["material_state"], composition["pip_shape"]))
        recent_compositions = recent_compositions[-2:]
        transitions = transition_pair_for_shot(shot, beat_class, beat.duration)
        segments.append(
            {
                "id": f"beat_{index:03d}",
                "start": round(beat.start, 3),
                "end": round(beat.end, 3),
                "duration": round(beat.duration, 3),
                "caption": beat.text,
                "beat_class": beat_class,
                "driver_scores": driver_scores,
                "driver_score": weighted_driver_score(driver_scores, rules),
                "shot": shot,
                "speaker_state": composition["speaker_state"],
                "material_state": composition["material_state"],
                "pip_shape": composition["pip_shape"],
                "html_animation_behavior": html_animation_for_shot(shot, beat_class),
                "transition_in": transitions["transition_in"],
                "transition_out": transitions["transition_out"],
                "collision_policy": "Keep face, torso, and key data out of collision; reserve the lower safe area for downstream manual subtitles. Full evidence scenes may hide the speaker only for a bounded evidence run.",
                "qc_risk": "Requires roughcut gate approval and collision-safe evidence placement before final render.",
                "camera": camera_for_shot(shot, index),
                "overlay": overlay_for_shot(shot, beat),
                "subtitle": {
                    "mode": "off",
                    "reason": "Subtitles are added manually in the downstream finishing stage.",
                },
                "transition": transition_for_beat(beat_class, lane="talking_head", duration=beat.duration),
                "audio": audio_for_beat(beat_class),
            }
        )
    timeline = {
        "schema_version": "dasheng.talking_head_timeline.v1",
        "lane": "talking_head_video",
        "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "title": title,
        "source_video": source_video,
        "duration_sec": round(duration or 0.0, 3),
        "aspect": "16:9",
        "roughcut_gate": {
            "path": roughcut_gate,
            "status": "missing" if not roughcut_gate else "provided",
            "render_allowed": False if not roughcut_gate else None,
            "note": "Final render must verify roughcut_gate_report.render_allowed == true.",
        },
        "style_reference": {
            "target": "side-facing speaker plus evidence-first broll",
            "median_segment_sec": "2.5-4.0",
            "broll_or_evidence_ratio": "45%-65%",
            "speaker_return_interval_sec": "8-20",
        },
        "driver_rules_schema": rules.get("schema_version"),
        "director_state_machine": [
            "speaker_anchor",
            "claim_closeup",
            "evidence_fullscreen",
            "broll_with_pip",
            "document_zoom",
            "chart_card",
            "speaker_return",
        ],
        "safe_areas": {
            "speaker_crop": "bottom_half_or_side_anchor",
            "left_top": "outline_progress",
            "right_top": "charts_tables_documents",
            "bottom": "available_but_keep_clear_for_downstream_manual_subtitles",
        },
        "segments": segments,
        "qc_targets": {
            "audio_lufs": -16,
            "subtitles_in_director_render": "forbidden",
            "developer_labels_in_final": "forbidden",
            "fake_data_charts": "forbidden",
            "static_zoompan_only": "forbidden",
            "mechanical_fixed_pip": "forbidden",
            "roughcut_gate_before_render": "required",
        },
    }
    if timeline_alignment:
        timeline["timeline_alignment"] = timeline_alignment
    return timeline


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build a Newma talking-head director timeline.")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--captions-json")
    group.add_argument("--srt")
    parser.add_argument("--source-video")
    parser.add_argument("--duration", type=float)
    parser.add_argument("--title", default="未命名口播视频")
    parser.add_argument("--roughcut-gate", help="Path to approved roughcut_gate_report.json.")
    parser.add_argument("--roughcut-edl", help="Discrete keep-segment EDL from the rough-cut stage.")
    parser.add_argument("--output", required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.captions_json:
        captions = load_captions_json(Path(args.captions_json).expanduser().resolve())
    else:
        captions = load_srt(Path(args.srt).expanduser().resolve())
    timeline_alignment = None
    if args.roughcut_edl:
        captions, timeline_alignment = remap_captions_to_roughcut(
            captions,
            Path(args.roughcut_edl).expanduser().resolve(),
        )
    source_video = str(Path(args.source_video).expanduser().resolve()) if args.source_video else None
    duration = args.duration
    if duration is None and source_video:
        duration = run_ffprobe_duration(Path(source_video))
    if duration is None and timeline_alignment:
        duration = float(timeline_alignment["output_duration_sec"])
    timeline = build_talking_head_timeline(
        captions,
        title=args.title,
        source_video=source_video,
        duration=duration,
        roughcut_gate=str(Path(args.roughcut_gate).expanduser().resolve()) if args.roughcut_gate else None,
        timeline_alignment=timeline_alignment,
    )
    write_json(Path(args.output).expanduser().resolve(), timeline)
    print(json.dumps({"status": "ok", "output": str(Path(args.output).expanduser().resolve()), "segments": len(timeline["segments"])}, ensure_ascii=False))


if __name__ == "__main__":
    main()
