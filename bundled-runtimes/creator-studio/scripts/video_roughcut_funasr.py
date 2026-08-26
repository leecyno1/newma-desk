#!/usr/bin/env python3
from __future__ import annotations

import argparse
import difflib
import html
import json
import math
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


FILLER_RE = re.compile(r"[，。！？、,.!?；;：:\\s]")
SENTENCE_END_RE = re.compile(r"[。！？!?；;]")
PUNCT_RE = re.compile(r"[，。！？、,.!?；;：:\\s]")
TEXT_NOISE_RE = re.compile(r"(呃|嗯|啊|额|这个|那个|就是|然后|的话|呢|吧|对吧|知道吧|就是说)")
DEFAULT_HOTWORDS = "老虎 富途 纳指 美股 A股 港股 OpenAI SpaceX Anthropic Capex Mag7 IPO 黄金 原油"
AUDIO_ENHANCE_FILTER = (
    "highpass=f=80,"
    "lowpass=f=12000,"
    "afftdn=nf=-25,"
    "dynaudnorm=f=150:g=15:p=0.95,"
    "acompressor=threshold=-18dB:ratio=2.5:attack=5:release=80,"
    "loudnorm=I=-14:LRA=8:TP=-1.0,"
    "alimiter=limit=0.95"
)


@dataclass
class Segment:
    start: float
    end: float
    text: str
    source: str = "asr"

    @property
    def duration(self) -> float:
        return max(0.0, self.end - self.start)

    @property
    def center(self) -> float:
        return (self.start + self.end) / 2

    def as_dict(self) -> dict[str, Any]:
        return {
            "start": round(self.start, 3),
            "end": round(self.end, 3),
            "duration": round(self.duration, 3),
            "text": self.text,
            "source": self.source,
        }


def run(cmd: list[str], *, cwd: Path | None = None, capture: bool = False) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        cwd=str(cwd) if cwd else None,
        text=True,
        stdout=subprocess.PIPE if capture else None,
        stderr=subprocess.PIPE if capture else None,
        check=True,
    )


def ffprobe_duration(path: Path) -> float:
    result = run(
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
        capture=True,
    )
    return float((result.stdout or "0").strip() or 0)


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content.rstrip() + "\n", encoding="utf-8")


def extract_audio(video: Path, wav_path: Path) -> None:
    wav_path.parent.mkdir(parents=True, exist_ok=True)
    run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-i",
            str(video),
            "-vn",
            "-ac",
            "1",
            "-ar",
            "16000",
            str(wav_path),
        ]
    )


def transcribe_funasr(audio: Path, hotwords: str, device: str) -> tuple[list[Segment], dict[str, Any]]:
    try:
        from funasr import AutoModel
    except Exception as exc:  # pragma: no cover - depends on local media env
        raise RuntimeError("FunASR is not installed in the active Python environment") from exc

    model = AutoModel(
        model="paraformer-zh",
        vad_model="fsmn-vad",
        punc_model="ct-punc",
        device=device,
        disable_update=True,
    )
    result = model.generate(input=str(audio), batch_size_s=300, hotword=hotwords)
    payload = result[0] if isinstance(result, list) and result else result
    segments = parse_funasr_segments(payload)
    if not segments:
        text = str(payload.get("text") if isinstance(payload, dict) else payload).strip()
        duration = ffprobe_duration(audio)
        segments = [Segment(0, duration, text, "asr_no_timestamps")]
    return segments, {"engine": "funasr", "raw": payload}


def parse_funasr_segments(payload: Any) -> list[Segment]:
    if not isinstance(payload, dict):
        return []
    out: list[Segment] = []
    for item in payload.get("sentence_info") or []:
        if not isinstance(item, dict):
            continue
        start = float(item.get("start", 0)) / 1000
        end = float(item.get("end", 0)) / 1000
        text = str(item.get("text") or "").strip()
        if end > start and text:
            out.append(Segment(start, end, text, "sentence_info"))
    if out:
        return out

    timestamps = payload.get("timestamp") or []
    text = str(payload.get("text") or "").strip()
    if not timestamps or not text:
        return []
    aligned = align_text_to_timestamps(text, timestamps)
    return split_aligned_sentences(aligned) or [
        Segment(float(timestamps[0][0]) / 1000, float(timestamps[-1][1]) / 1000, text, "timestamp_blob")
    ]


def align_text_to_timestamps(text: str, timestamps: list[list[float]]) -> list[dict[str, Any]]:
    aligned: list[dict[str, Any]] = []
    ts_idx = 0
    last_start = float(timestamps[0][0]) / 1000 if timestamps else 0.0
    last_end = last_start
    for char in text:
        if PUNCT_RE.fullmatch(char):
            aligned.append({"char": char, "start": last_end, "end": last_end, "punct": True})
            continue
        if ts_idx >= len(timestamps):
            aligned.append({"char": char, "start": last_end, "end": last_end + 0.12, "punct": False})
            last_end += 0.12
            continue
        start, end = timestamps[ts_idx]
        ts_idx += 1
        last_start = float(start) / 1000
        last_end = float(end) / 1000
        aligned.append({"char": char, "start": last_start, "end": last_end, "punct": False})
    return aligned


def split_aligned_sentences(aligned: list[dict[str, Any]], max_chars: int = 42) -> list[Segment]:
    segments: list[Segment] = []
    buf: list[dict[str, Any]] = []

    def flush() -> None:
        nonlocal buf
        chars = [item["char"] for item in buf]
        text = "".join(chars).strip()
        timed = [item for item in buf if not item.get("punct")]
        if text and timed:
            segments.append(Segment(float(timed[0]["start"]), float(timed[-1]["end"]), text, "timestamp_sentence"))
        buf = []

    for item in aligned:
        buf.append(item)
        text_so_far = "".join(x["char"] for x in buf)
        if SENTENCE_END_RE.fullmatch(item["char"]) or len(PUNCT_RE.sub("", text_so_far)) >= max_chars:
            flush()
    if buf:
        flush()
    return [seg for seg in segments if seg.duration > 0.05]


def scale_funasr_payload_timebase(payload: Any, scale: float) -> Any:
    """Scale FunASR millisecond timestamps when model timebase drifts from media duration."""
    if isinstance(payload, list):
        if payload and all(
            isinstance(item, list)
            and len(item) == 2
            and all(isinstance(value, (int, float)) for value in item)
            for item in payload
        ):
            return [[round(float(start) * scale, 3), round(float(end) * scale, 3)] for start, end in payload]
        return [scale_funasr_payload_timebase(item, scale) for item in payload]
    if isinstance(payload, dict):
        out: dict[str, Any] = {}
        for key, value in payload.items():
            if key in {"start", "end"} and isinstance(value, (int, float)):
                out[key] = round(float(value) * scale, 3)
            else:
                out[key] = scale_funasr_payload_timebase(value, scale)
        return out
    return payload


def align_asr_timebase(
    segments: list[Segment],
    asr_payload: dict[str, Any],
    media_duration: float,
) -> tuple[list[Segment], dict[str, Any], dict[str, Any] | None]:
    if not segments or media_duration <= 0:
        return segments, asr_payload, None
    asr_end = max(seg.end for seg in segments)
    drift = asr_end - media_duration
    if abs(drift) < 1.0:
        return segments, asr_payload, None
    scale = media_duration / asr_end if asr_end else 1.0
    if not 0.92 <= scale <= 1.08:
        return segments, asr_payload, {
            "applied": False,
            "reason": "drift_outside_safe_scale_window",
            "asr_end_sec": round(asr_end, 3),
            "media_duration_sec": round(media_duration, 3),
            "drift_sec": round(drift, 3),
            "scale": round(scale, 6),
        }
    scaled_segments = [
        Segment(seg.start * scale, seg.end * scale, seg.text, seg.source)
        for seg in segments
    ]
    payload_copy = json.loads(json.dumps(asr_payload, ensure_ascii=False))
    if isinstance(payload_copy, dict) and "raw" in payload_copy:
        payload_copy["raw"] = scale_funasr_payload_timebase(payload_copy["raw"], scale)
    else:
        payload_copy = scale_funasr_payload_timebase(payload_copy, scale)
    correction = {
        "applied": True,
        "asr_end_sec": round(asr_end, 3),
        "media_duration_sec": round(media_duration, 3),
        "drift_sec": round(drift, 3),
        "scale": round(scale, 6),
    }
    return scaled_segments, payload_copy, correction


def silence_ranges(audio: Path, duration: float, threshold: str, min_silence: float, keep_padding: float) -> list[dict[str, Any]]:
    result = subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-nostats",
            "-i",
            str(audio),
            "-af",
            f"silencedetect=noise={threshold}:d={min_silence}",
            "-f",
            "null",
            "-",
        ],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    starts: list[float] = []
    ranges: list[dict[str, Any]] = []
    for line in (result.stderr or "").splitlines():
        m_start = re.search(r"silence_start: ([0-9.]+)", line)
        if m_start:
            starts.append(float(m_start.group(1)))
            continue
        m_end = re.search(r"silence_end: ([0-9.]+)", line)
        if m_end and starts:
            start = starts.pop(0)
            end = float(m_end.group(1))
            delete_start = min(max(0, start + keep_padding), duration)
            delete_end = max(min(duration, end - keep_padding), 0)
            if delete_end - delete_start >= 0.28:
                ranges.append(
                    {
                        "start": delete_start,
                        "end": delete_end,
                        "reason": "silence",
                        "confidence": 0.82,
                        "text": "",
                    }
                )
    return ranges


def normalize_text(text: str) -> str:
    compact = FILLER_RE.sub("", text)
    compact = TEXT_NOISE_RE.sub("", compact)
    return compact.strip()


def is_filler_only(text: str) -> bool:
    compact = FILLER_RE.sub("", text)
    stripped = TEXT_NOISE_RE.sub("", compact)
    return bool(compact) and len(stripped) <= 1 and len(compact) <= 10


def semantic_candidates(segments: list[Segment]) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    last_kept_norm = ""
    last_kept_text = ""
    for seg in segments:
        norm = normalize_text(seg.text)
        if is_filler_only(seg.text) and seg.duration <= 1.8:
            candidates.append(
                {
                    "start": seg.start,
                    "end": seg.end,
                    "reason": "filler_only_sentence",
                    "confidence": 0.9,
                    "text": seg.text,
                }
            )
            continue
        if norm and last_kept_norm:
            ratio = difflib.SequenceMatcher(None, norm, last_kept_norm).ratio()
            if ratio >= 0.82 and seg.duration <= 12:
                candidates.append(
                    {
                        "start": seg.start,
                        "end": seg.end,
                        "reason": "adjacent_repetition",
                        "confidence": round(ratio, 3),
                        "text": seg.text,
                        "compare_to": last_kept_text,
                    }
                )
                continue
        if norm:
            last_kept_norm = norm
            last_kept_text = seg.text
    return candidates


def merge_ranges(ranges: list[dict[str, Any]], duration: float, gap: float = 0.18) -> list[dict[str, Any]]:
    clean = [
        {
            **item,
            "start": max(0.0, min(duration, float(item["start"]))),
            "end": max(0.0, min(duration, float(item["end"]))),
        }
        for item in ranges
        if float(item.get("end", 0)) - float(item.get("start", 0)) >= 0.18
    ]
    clean.sort(key=lambda item: (item["start"], item["end"]))
    merged: list[dict[str, Any]] = []
    for item in clean:
        if not merged or item["start"] > merged[-1]["end"] + gap:
            merged.append({**item, "reasons": [item["reason"]]})
            continue
        prev = merged[-1]
        prev["end"] = max(prev["end"], item["end"])
        prev["confidence"] = max(float(prev.get("confidence", 0)), float(item.get("confidence", 0)))
        prev.setdefault("reasons", []).append(item["reason"])
        if item.get("text"):
            prev["text"] = (str(prev.get("text") or "") + " " + str(item.get("text"))).strip()
    return merged


def guard_unreliable_silence(
    candidates: list[dict[str, Any]],
    duration: float,
    max_silence_ratio: float,
) -> list[dict[str, Any]]:
    silence_removed = sum(
        float(item["end"]) - float(item["start"]) for item in candidates if item.get("reason") == "silence"
    )
    if duration > 0 and silence_removed / duration > max_silence_ratio:
        return [item for item in candidates if item.get("reason") != "silence"]
    return candidates


def complement_ranges(deletes: list[dict[str, Any]], duration: float, min_keep: float = 0.35) -> list[dict[str, float]]:
    keep: list[dict[str, float]] = []
    cursor = 0.0
    for item in deletes:
        start = float(item["start"])
        end = float(item["end"])
        if start - cursor >= min_keep:
            keep.append({"start": cursor, "end": start})
        cursor = max(cursor, end)
    if duration - cursor >= min_keep:
        keep.append({"start": cursor, "end": duration})
    return keep


def select_expression(keep_ranges: list[dict[str, float]]) -> str:
    if not keep_ranges:
        raise ValueError("At least one keep range is required")
    return "+".join(
        f"between(t\\,{float(keep['start']):.6f}\\,{float(keep['end']):.6f})"
        for keep in keep_ranges
    )


def timestamp_rebuild_expression(keep_ranges: list[dict[str, float]]) -> str:
    gap_terms = []
    for previous, current in zip(keep_ranges, keep_ranges[1:]):
        gap = max(0.0, float(current["start"]) - float(previous["end"]))
        if gap <= 0:
            continue
        gap_terms.append(f"gte(T\\,{float(current['start']):.6f})*{gap:.6f}")
    if not gap_terms:
        return "PTS-STARTPTS"
    return f"(PTS-STARTPTS)-({'+'.join(gap_terms)})/TB"


def render_concat(video: Path, keep_ranges: list[dict[str, float]], output: Path, work_dir: Path) -> None:
    expression = select_expression(keep_ranges)
    rebuilt_pts = timestamp_rebuild_expression(keep_ranges)
    filter_complex = (
        f"[0:v:0]select={expression},setpts={rebuilt_pts}[v];"
        f"[0:a:0]aselect={expression},asetpts={rebuilt_pts},"
        f"aresample=48000,{AUDIO_ENHANCE_FILTER}[a]"
    )
    write_json(
        work_dir / "render_timeline.json",
        {
            "method": "single_decode_select_and_timestamp_rebuild",
            "keep_ranges": keep_ranges,
            "expected_duration_sec": round(
                sum(float(keep["end"]) - float(keep["start"]) for keep in keep_ranges),
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
            str(video),
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
            "21",
            "-c:a",
            "aac",
            "-b:a",
            "160k",
            "-ar",
            "48000",
            "-movflags",
            "+faststart",
            str(output),
        ]
    )


def render_softsub_video(video: Path, srt: Path, output: Path) -> None:
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
            "-c:v",
            "copy",
            "-c:a",
            "copy",
            "-c:s",
            "mov_text",
            "-metadata:s:s:0",
            "language=chi",
            str(output),
        ]
    )


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


def format_srt_time(seconds: float) -> str:
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


def write_srt(path: Path, segments: list[Segment], deletes: list[dict[str, Any]]) -> None:
    rows: list[str] = []
    idx = 1
    last_end = 0.0
    for seg in segments:
        start = map_time(seg.start, deletes)
        end = map_time(seg.end, deletes)
        if start is None or end is None or end <= start:
            continue
        if start < last_end + 0.04:
            start = last_end + 0.04
        if end <= start:
            end = start + 0.65
        rows.extend([str(idx), f"{format_srt_time(start)} --> {format_srt_time(end)}", seg.text, ""])
        last_end = end
        idx += 1
    write_text(path, "\n".join(rows))


def render_loud_preview(source: Path, output: Path) -> None:
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
            "-map",
            "0:v:0",
            "-map",
            "0:a:0?",
            "-c:v",
            "copy",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-af",
            AUDIO_ENHANCE_FILTER,
            "-movflags",
            "+faststart",
            str(output),
        ]
    )


def candidate_kind(item: dict[str, Any]) -> str:
    reasons = item.get("reasons") or [item.get("reason", "")]
    if "silence" in reasons:
        return "silence"
    if "adjacent_repetition" in reasons:
        return "repetition"
    if "filler_only_sentence" in reasons:
        return "filler"
    return "semantic"


def default_candidate_enabled(item: dict[str, Any]) -> bool:
    kind = candidate_kind(item)
    confidence = float(item.get("confidence") or 0)
    if kind == "silence":
        return confidence >= 0.8
    if kind == "filler":
        return confidence >= 0.88
    if kind == "repetition":
        return confidence >= 0.9
    return False


def review_candidates(deletes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for idx, item in enumerate(deletes, 1):
        start = float(item["start"])
        end = float(item["end"])
        reasons = item.get("reasons") or [item.get("reason", "")]
        out.append(
            {
                "id": f"c{idx:03d}",
                "start": round(start, 3),
                "end": round(end, 3),
                "duration": round(max(0, end - start), 3),
                "reason": "+".join(str(reason) for reason in reasons if reason),
                "text": str(item.get("text") or ""),
                "default": default_candidate_enabled(item),
                "kind": candidate_kind(item),
                "confidence": round(float(item.get("confidence") or 0), 3),
            }
        )
    return out


def captions_json(segments: list[Segment]) -> list[dict[str, Any]]:
    return [
        {"start": round(seg.start, 3), "end": round(seg.end, 3), "text": seg.text}
        for seg in segments
        if seg.end > seg.start and seg.text.strip()
    ]


def render_review_page_html() -> str:
    return r'''<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <title>Newma Video Roughcut Review</title>
  <style>
    body { margin: 0; font-family: -apple-system, BlinkMacSystemFont, "PingFang SC", sans-serif; background: #f7f4ed; color: #172033; }
    header { position: sticky; top: 0; z-index: 3; background: #101827; color: white; padding: 14px 22px; display: flex; gap: 12px; align-items: center; }
    main { display: grid; grid-template-columns: 430px 1fr; gap: 18px; padding: 18px; }
    .video-wrap { position: relative; background: #111; border-radius: 14px; overflow: hidden; }
    video { width: 100%; display: block; background: #111; }
    .subtitle {
      position: absolute; left: 50%; bottom: 18px; transform: translateX(-50%);
      max-width: 88%; padding: 4px 8px; border-radius: 7px;
      background: rgba(0, 0, 0, 0.58); color: #fff; font-size: 13px;
      line-height: 1.35; text-align: center; text-shadow: 0 1px 2px #000;
      pointer-events: none; display: none;
    }
    .subtitle.show { display: block; }
    .card { background: white; border: 1px solid #e5ded2; border-radius: 14px; padding: 16px; box-shadow: 0 10px 26px #0001; }
    button { background: #1d4ed8; color: white; border: 0; border-radius: 9px; padding: 7px 11px; cursor: pointer; }
    button.secondary { background: #334155; }
    button.warn { background: #b45309; }
    table { width: 100%; border-collapse: collapse; font-size: 13px; }
    th, td { padding: 8px; border-bottom: 1px solid #eee; vertical-align: top; }
    th { position: sticky; top: 56px; background: #fbf8f1; }
    textarea { width: 100%; height: 150px; font-family: ui-monospace, Menlo, monospace; }
    .muted { color: #94a3b8; }
    .pill { display: inline-block; padding: 2px 8px; border-radius: 999px; background: #dbeafe; color: #1e40af; margin: 3px 4px 3px 0; }
    .status { white-space: pre-wrap; background: #0f172a; color: #d8e6ff; padding: 10px; border-radius: 10px; min-height: 46px; }
    .hint { color: #64748b; font-size: 13px; line-height: 1.55; }
    @media (max-width: 900px) { main { grid-template-columns: 1fr; } }
  </style>
</head>
<body>
  <header>
    <strong>Newma Video Roughcut Review</strong>
    <span class="muted">勾选只预览；保存才落盘；保存并重剪才生成新视频</span>
  </header>
  <main>
    <section class="card">
      <div class="video-wrap">
        <video id="video" controls src="0_source_loud_preview.mp4"></video>
        <div id="subtitle" class="subtitle show"></div>
      </div>
      <p>
        <span class="pill">FunASR 初检</span>
        <span class="pill">审核源已响度归一</span>
        <span class="pill">句段级候选</span>
        <span class="pill">保存后可 Agent 校对字幕</span>
      </p>
      <p>
        <label><input id="toggleSubtitle" type="checkbox" checked> 显示字幕</label>
        <label style="margin-left:12px;"><input id="livePreview" type="checkbox" checked> 实时预览删除效果</label>
        <label style="margin-left:12px;">字号
          <select id="subtitleSize">
            <option value="12">小</option>
            <option value="13" selected>默认小</option>
            <option value="15">中</option>
            <option value="17">大</option>
          </select>
        </label>
      </p>
      <p class="hint">审核建议：静音通常可保留默认；重复、口水句、疑似口误请结合上下文手动勾选。实时预览不会写文件。</p>
      <p>
        <button onclick="saveOnly()">保存审核</button>
        <button class="warn" onclick="saveAndRender()">保存并重剪</button>
        <button class="secondary" onclick="exportJson()">刷新 JSON</button>
      </p>
      <textarea id="jsonBox"></textarea>
      <h3>状态</h3>
      <div id="status" class="status">等待操作。点击“保存审核”会写入 3_delete_segments.reviewed.json；点击“保存并重剪”会生成 reviewed_output_loud.mp4 / reviewed_output_loud.srt / reviewed_output_loud_softsub.mp4 / proofread_agent_input.md。</div>
    </section>
    <section class="card">
      <table>
        <thead>
          <tr><th>剪</th><th>ID</th><th>时间</th><th>时长</th><th>默认</th><th>类型</th><th>原因</th><th>说明</th><th>播放</th></tr>
        </thead>
        <tbody id="rows"></tbody>
      </table>
    </section>
  </main>
  <script>
    let candidates = [];
    let captions = [];
    let captionIndex = 0;
    const video = document.getElementById("video");
    const rows = document.getElementById("rows");
    const statusBox = document.getElementById("status");
    const jsonBox = document.getElementById("jsonBox");
    const subtitle = document.getElementById("subtitle");
    const toggleSubtitle = document.getElementById("toggleSubtitle");
    const subtitleSize = document.getElementById("subtitleSize");
    const livePreview = document.getElementById("livePreview");
    let lastSkipAt = -1;

    function escapeHtml(text) {
      return String(text || "").replace(/[&<>"']/g, ch => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[ch]));
    }

    function setStatus(text) { statusBox.textContent = text; }

    function jump(time) {
      video.currentTime = Math.max(0, time - 1);
      video.play();
    }

    function updateSubtitle() {
      if (!toggleSubtitle.checked) {
        subtitle.classList.remove("show");
        return;
      }
      const t = video.currentTime;
      while (captionIndex > 0 && captions[captionIndex]?.start > t) captionIndex--;
      while (captionIndex < captions.length - 1 && captions[captionIndex]?.end < t) captionIndex++;
      const cue = captions[captionIndex];
      if (cue && cue.start <= t && cue.end >= t) {
        subtitle.textContent = cue.text;
        subtitle.classList.add("show");
      } else {
        subtitle.textContent = "";
        subtitle.classList.remove("show");
      }
    }

    function selectedSegments() {
      return [...document.querySelectorAll("tr[data-id]")].flatMap(row => {
        if (!row.querySelector("input").checked) return [];
        const item = candidates.find(c => c.id === row.dataset.id);
        return [{ id: item.id, start: item.start, end: item.end, reason: item.reason, kind: item.kind, text: item.text }];
      });
    }

    function mergedSelectedSegments() {
      const items = selectedSegments().sort((a, b) => a.start - b.start);
      const merged = [];
      for (const item of items) {
        if (!merged.length || item.start > merged[merged.length - 1].end + 0.05) {
          merged.push({ ...item });
        } else {
          merged[merged.length - 1].end = Math.max(merged[merged.length - 1].end, item.end);
          merged[merged.length - 1].reason = `${merged[merged.length - 1].reason}+${item.reason}`;
        }
      }
      return merged;
    }

    function skipDeletedSegmentIfNeeded() {
      if (!livePreview.checked || video.paused || video.seeking) return;
      const t = video.currentTime;
      const hit = mergedSelectedSegments().find(seg => t >= seg.start && t < seg.end);
      if (!hit) return;
      if (Math.abs(lastSkipAt - hit.end) < 0.2) return;
      lastSkipAt = hit.end;
      video.currentTime = Math.min(video.duration || hit.end, hit.end + 0.03);
    }

    function exportJson() {
      jsonBox.value = JSON.stringify(selectedSegments(), null, 2);
    }

    async function saveOnly() {
      exportJson();
      const response = await fetch("/save", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: jsonBox.value,
      });
      const result = await response.json();
      setStatus(JSON.stringify(result, null, 2));
    }

    async function saveAndRender() {
      exportJson();
      setStatus("正在保存并重剪，视频较长，请等待...");
      const response = await fetch("/render", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: jsonBox.value,
      });
      const result = await response.json();
      setStatus(JSON.stringify(result, null, 2));
    }

    async function init() {
      candidates = await fetch("2_candidates.json").then(r => r.json());
      captions = await fetch("0_source_review_captions.json").then(r => r.json());
      rows.innerHTML = candidates.map(item => `
        <tr data-id="${escapeHtml(item.id)}">
          <td><input type="checkbox" ${item.default ? "checked" : ""} onchange="exportJson()"></td>
          <td>${escapeHtml(item.id)}</td>
          <td>${Number(item.start).toFixed(2)}-${Number(item.end).toFixed(2)}</td>
          <td>${Number(item.duration).toFixed(2)}s</td>
          <td>${item.default ? "默认剪" : "仅审核"}</td>
          <td>${escapeHtml(item.kind)}</td>
          <td>${escapeHtml(item.reason)}</td>
          <td>${escapeHtml(item.text)}</td>
          <td><button onclick="jump(${Number(item.start)})">跳转</button></td>
        </tr>
      `).join("");
      video.addEventListener("timeupdate", updateSubtitle);
      video.addEventListener("timeupdate", skipDeletedSegmentIfNeeded);
      video.addEventListener("seeked", () => {
        captionIndex = 0;
        lastSkipAt = -1;
        updateSubtitle();
      });
      toggleSubtitle.addEventListener("change", updateSubtitle);
      subtitleSize.addEventListener("change", () => {
        subtitle.style.fontSize = `${subtitleSize.value}px`;
      });
      subtitle.style.fontSize = `${subtitleSize.value}px`;
      exportJson();
    }

    init().catch(error => setStatus(error.stack || error.message));
  </script>
</body>
</html>'''


def render_review_server_js() -> str:
    return r'''#!/usr/bin/env node
const http = require("node:http");
const fs = require("node:fs");
const path = require("node:path");
const { spawn } = require("node:child_process");

const baseDir = __dirname;
const port = Number(process.env.PORT || 8899);

const mime = {
  ".html": "text/html; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".json": "application/json; charset=utf-8",
  ".mp4": "video/mp4",
  ".srt": "text/plain; charset=utf-8",
  ".md": "text/markdown; charset=utf-8",
};

function send(res, status, body, type = "application/json; charset=utf-8") {
  res.writeHead(status, { "Content-Type": type });
  res.end(body);
}

function readBody(req) {
  return new Promise((resolve, reject) => {
    let data = "";
    req.on("data", chunk => {
      data += chunk;
      if (data.length > 5 * 1024 * 1024) {
        reject(new Error("body too large"));
        req.destroy();
      }
    });
    req.on("end", () => resolve(data));
    req.on("error", reject);
  });
}

function safePath(urlPath) {
  const decoded = decodeURIComponent(urlPath.split("?")[0]);
  const relative = decoded === "/" ? "3_review_live.html" : decoded.replace(/^\/+/, "");
  const full = path.resolve(baseDir, relative);
  if (!full.startsWith(baseDir)) return null;
  return full;
}

const server = http.createServer(async (req, res) => {
  try {
    if (req.method === "POST" && req.url === "/save") {
      const body = await readBody(req);
      const segments = JSON.parse(body);
      if (!Array.isArray(segments)) throw new Error("expected JSON array");
      const out = path.join(baseDir, "3_delete_segments.reviewed.json");
      fs.writeFileSync(out, JSON.stringify(segments, null, 2), "utf8");
      return send(res, 200, JSON.stringify({ ok: true, path: out, count: segments.length }));
    }

    if (req.method === "POST" && req.url === "/render") {
      const body = await readBody(req);
      const segments = JSON.parse(body);
      if (!Array.isArray(segments)) throw new Error("expected JSON array");
      const selectedPath = path.join(baseDir, "3_delete_segments.reviewed.json");
      fs.writeFileSync(selectedPath, JSON.stringify(segments, null, 2), "utf8");

      const child = spawn("python3", [path.join(baseDir, "render_review.py")], {
        cwd: baseDir,
        stdio: ["ignore", "pipe", "pipe"],
      });
      let stdout = "";
      let stderr = "";
      child.stdout.on("data", chunk => (stdout += chunk));
      child.stderr.on("data", chunk => (stderr += chunk));
      child.on("close", code => {
        if (code === 0) return send(res, 200, JSON.stringify({ ok: true, stdout }));
        send(res, 500, JSON.stringify({ ok: false, code, stdout, stderr }));
      });
      return;
    }

    if (req.method !== "GET" && req.method !== "HEAD") {
      return send(res, 405, JSON.stringify({ ok: false, error: "method not allowed" }));
    }

    const full = safePath(req.url);
    if (!full || !fs.existsSync(full) || fs.statSync(full).isDirectory()) {
      return send(res, 404, "not found", "text/plain; charset=utf-8");
    }
    const ext = path.extname(full).toLowerCase();
    const stat = fs.statSync(full);
    const type = mime[ext] || "application/octet-stream";
    const range = req.headers.range;
    if (range) {
      const match = range.match(/bytes=(\d*)-(\d*)/);
      if (match) {
        const start = match[1] ? Number(match[1]) : 0;
        const end = match[2] ? Number(match[2]) : stat.size - 1;
        const safeEnd = Math.min(end, stat.size - 1);
        const chunkSize = safeEnd - start + 1;
        res.writeHead(206, {
          "Content-Type": type,
          "Content-Length": chunkSize,
          "Content-Range": `bytes ${start}-${safeEnd}/${stat.size}`,
          "Accept-Ranges": "bytes",
        });
        if (req.method === "HEAD") return res.end();
        return fs.createReadStream(full, { start, end: safeEnd }).pipe(res);
      }
    }
    res.writeHead(200, {
      "Content-Type": type,
      "Content-Length": stat.size,
      "Accept-Ranges": "bytes",
    });
    if (req.method === "HEAD") return res.end();
    fs.createReadStream(full).pipe(res);
  } catch (error) {
    send(res, 500, JSON.stringify({ ok: false, error: error.message }));
  }
});

server.listen(port, () => {
  console.log(`Newma roughcut review server: http://localhost:${port}/`);
});
'''


def render_review_py(source: Path) -> str:
    source_json = json.dumps(str(source.resolve()), ensure_ascii=False)
    return f'''#!/usr/bin/env python3
import json
import math
import subprocess
from datetime import datetime
from pathlib import Path

BASE = Path(__file__).resolve().parent
SOURCE = Path({source_json})
SEGMENTS_JSON = BASE / "0_source_review_captions.json"
SELECTED_JSON = BASE / "3_delete_segments.reviewed.json"
DEFAULT_JSON = BASE / "3_delete_segments.json"
RAW_OUT = BASE / "reviewed_output_raw.mp4"
LOUD_OUT = BASE / "reviewed_output_loud.mp4"
SRT_OUT = BASE / "reviewed_output_loud.srt"
SOFTSUB_OUT = BASE / "reviewed_output_loud_softsub.mp4"
MANIFEST_OUT = BASE / "reviewed_render_manifest.json"
PROOFREAD_MD = BASE / "proofread_agent_input.md"
PROOFREAD_JSON = BASE / "proofread_agent_input.json"
AUDIO_ENHANCE_FILTER = (
    "highpass=f=80,"
    "lowpass=f=12000,"
    "afftdn=nf=-25,"
    "dynaudnorm=f=150:g=15:p=0.95,"
    "acompressor=threshold=-18dB:ratio=2.5:attack=5:release=80,"
    "loudnorm=I=-14:LRA=8:TP=-1.0,"
    "alimiter=limit=0.95"
)

BUFFER_SEC = 0.05


def run(cmd):
    subprocess.run(cmd, check=True)


def ffprobe_duration(path):
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=nk=1:nw=1", str(path)],
        check=True,
        text=True,
        capture_output=True,
    )
    return float(result.stdout.strip())


def load_deletes(duration):
    path = SELECTED_JSON if SELECTED_JSON.exists() else DEFAULT_JSON
    deletes = json.loads(path.read_text(encoding="utf-8"))
    ranges = []
    for item in deletes:
        start = max(0.0, float(item["start"]) - BUFFER_SEC)
        end = min(duration, float(item["end"]) + BUFFER_SEC)
        if end - start >= 0.18:
            ranges.append({{**item, "start": start, "end": end}})
    ranges.sort(key=lambda item: (item["start"], item["end"]))
    merged = []
    for item in ranges:
        if not merged or item["start"] > merged[-1]["end"] + 0.05:
            merged.append(dict(item))
        else:
            merged[-1]["end"] = max(merged[-1]["end"], item["end"])
            merged[-1]["reason"] = str(merged[-1].get("reason", "")) + "+" + str(item.get("reason", ""))
    return merged


def build_keeps(duration, deletes):
    keeps = []
    cursor = 0.0
    for item in deletes:
        start = float(item["start"])
        end = float(item["end"])
        if start > cursor:
            keeps.append({{"start": cursor, "end": start}})
        cursor = max(cursor, end)
    if cursor < duration:
        keeps.append({{"start": cursor, "end": duration}})
    return [item for item in keeps if item["end"] - item["start"] >= 0.25]


def render_video(keeps):
    concat_path = BASE / "reviewed_keep_ranges.ffconcat"
    escaped = str(SOURCE.resolve()).replace("'", "'\\\\''")
    lines = ["ffconcat version 1.0"]
    for keep in keeps:
        lines.extend([f"file '{{escaped}}'", f"inpoint {{keep['start']:.3f}}", f"outpoint {{keep['end']:.3f}}"])
    concat_path.write_text("\\n".join(lines) + "\\n", encoding="utf-8")
    run([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-safe", "0", "-f", "concat", "-i", str(concat_path),
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "21",
        "-c:a", "aac", "-b:a", "192k",
        "-af", AUDIO_ENHANCE_FILTER,
        "-movflags", "+faststart", str(LOUD_OUT),
    ])


def map_time(t, keeps):
    removed = 0.0
    for keep in keeps:
        start = float(keep["start"])
        end = float(keep["end"])
        if t < start:
            return None
        if start <= t <= end:
            return removed + (t - start)
        removed += end - start
    return None


def format_srt_time(seconds):
    ms = int(round((seconds - math.floor(seconds)) * 1000))
    total = int(math.floor(seconds))
    if ms == 1000:
        total += 1
        ms = 0
    h = total // 3600
    m = (total % 3600) // 60
    s = total % 60
    return f"{{h:02d}}:{{m:02d}}:{{s:02d}},{{ms:03d}}"


def write_srt(keeps):
    captions = json.loads(SEGMENTS_JSON.read_text(encoding="utf-8"))
    rows = []
    idx = 1
    last_end = 0.0
    for cue in captions:
        center = (float(cue["start"]) + float(cue["end"])) / 2
        mapped_center = map_time(center, keeps)
        if mapped_center is None:
            continue
        start = map_time(float(cue["start"]), keeps)
        end = map_time(float(cue["end"]), keeps)
        if start is None:
            start = max(0.0, mapped_center - min(1.2, (float(cue["end"]) - float(cue["start"])) / 2))
        if end is None or end <= start:
            end = start + max(0.65, min(4.2, float(cue["end"]) - float(cue["start"])))
        if start < last_end + 0.04:
            start = last_end + 0.04
        if end <= start:
            end = start + 0.65
        rows.extend([str(idx), f"{{format_srt_time(start)}} --> {{format_srt_time(end)}}", str(cue["text"]).strip(), ""])
        last_end = end
        idx += 1
    SRT_OUT.write_text("\\n".join(rows).rstrip() + "\\n", encoding="utf-8")


def mux_soft_subtitles():
    run([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-i", str(LOUD_OUT), "-i", str(SRT_OUT),
        "-map", "0:v", "-map", "0:a", "-map", "1:0",
        "-c:v", "copy", "-c:a", "copy", "-c:s", "mov_text",
        "-metadata:s:s:0", "language=chi", "-movflags", "+faststart", str(SOFTSUB_OUT),
    ])


def write_proofread_input(deletes, keeps):
    srt_text = SRT_OUT.read_text(encoding="utf-8") if SRT_OUT.exists() else ""
    payload = {{
        "task": "agent_subtitle_proofread",
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "source_video": str(SOURCE),
        "reviewed_video": str(LOUD_OUT),
        "reviewed_srt": str(SRT_OUT),
        "rules": [
            "只校对字幕文本，不重算时间轴",
            "修正错字、同音词、专名、断句和明显口水词",
            "保留每条 cue 的 start/end，除非用户明确要求重新切字幕",
            "输出 proofread.srt 和 text_edits.json",
        ],
        "delete_segments": deletes,
        "keep_segments": keeps,
        "srt": srt_text,
    }}
    PROOFREAD_JSON.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    PROOFREAD_MD.write_text(
        "# Agent 字幕语义校对输入包\\n\\n"
        "请基于下面 SRT 做中文口播字幕校对。默认不要改时间轴，只改字幕文本。\\n\\n"
        "重点：错字、同音词、专名、断句、口水词、语意连贯。\\n\\n"
        f"源视频：{{SOURCE}}\\n\\n审核后视频：{{LOUD_OUT}}\\n\\n审核后 SRT：{{SRT_OUT}}\\n\\n"
        "```srt\\n" + srt_text + "\\n```\\n",
        encoding="utf-8",
    )


def main():
    duration = ffprobe_duration(SOURCE)
    deletes = load_deletes(duration)
    keeps = build_keeps(duration, deletes)
    render_video(keeps)
    write_srt(keeps)
    mux_soft_subtitles()
    write_proofread_input(deletes, keeps)
    manifest = {{
        "status": "rendered",
        "delete_count": len(deletes),
        "output": str(LOUD_OUT),
        "softsub": str(SOFTSUB_OUT),
        "srt": str(SRT_OUT),
        "proofread_input": str(PROOFREAD_MD),
        "duration": ffprobe_duration(LOUD_OUT),
    }}
    MANIFEST_OUT.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
'''


def write_review_package(
    review_dir: Path,
    *,
    source: Path,
    segments: list[Segment],
    deletes: list[dict[str, Any]],
    manifest: dict[str, Any],
) -> dict[str, str]:
    review_dir.mkdir(parents=True, exist_ok=True)
    preview = review_dir / "0_source_loud_preview.mp4"
    render_loud_preview(source, preview)
    candidates = review_candidates(deletes)
    default_deletes = [
        {"id": item["id"], "start": item["start"], "end": item["end"], "reason": item["reason"], "kind": item["kind"], "text": item["text"]}
        for item in candidates
        if item["default"]
    ]
    write_json(review_dir / "0_source_review_captions.json", captions_json(segments))
    write_json(review_dir / "2_candidates.json", candidates)
    write_json(review_dir / "3_delete_segments.json", default_deletes)
    write_json(review_dir / "review_source_manifest.json", manifest)
    write_text(review_dir / "3_review_live.html", render_review_page_html())
    write_text(review_dir / "review_server.js", render_review_server_js())
    write_text(review_dir / "render_review.py", render_review_py(source))
    write_text(
        review_dir / "start_review.command",
        "#!/bin/zsh\ncd \"$(dirname \"$0\")\"\nPORT=${PORT:-8899} node review_server.js\n",
    )
    for script in ["review_server.js", "render_review.py", "start_review.command"]:
        (review_dir / script).chmod(0o755)
    return {
        "review_page": str((review_dir / "3_review_live.html").resolve()),
        "review_server": str((review_dir / "review_server.js").resolve()),
        "review_start_command": str((review_dir / "start_review.command").resolve()),
        "review_url": "http://localhost:8899/",
        "review_candidates": str((review_dir / "2_candidates.json").resolve()),
    }


def render_review_html(
    path: Path,
    *,
    source_video: Path,
    edited_video: Path,
    segments: list[Segment],
    deletes: list[dict[str, Any]],
    manifest: dict[str, Any],
) -> None:
    rows = "\n".join(
        "<tr>"
        f"<td>{idx}</td>"
        f"<td>{item['start']:.2f}-{item['end']:.2f}</td>"
        f"<td>{html.escape(', '.join(item.get('reasons') or [item.get('reason', '')]))}</td>"
        f"<td>{float(item.get('confidence', 0)):.2f}</td>"
        f"<td>{html.escape(str(item.get('text') or ''))}</td>"
        "</tr>"
        for idx, item in enumerate(deletes, 1)
    )
    transcript = "\n".join(
        f"<p><b>{seg.start:.2f}-{seg.end:.2f}</b> {html.escape(seg.text)}</p>" for seg in segments
    )
    content = f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>视频粗剪审核</title>
<style>
body{{margin:0;background:#f5f7fb;color:#132033;font-family:-apple-system,BlinkMacSystemFont,"PingFang SC","Helvetica Neue",Arial,sans-serif;}}
main{{max-width:1180px;margin:0 auto;padding:28px;}}
h1{{font-size:26px;margin:0 0 18px;}}
.grid{{display:grid;grid-template-columns:1fr 1fr;gap:18px;align-items:start;}}
.panel{{background:#fff;border:1px solid #dfe6f2;border-radius:8px;padding:16px;box-shadow:0 8px 24px rgba(20,37,63,.06);}}
video{{width:100%;background:#000;border-radius:6px;}}
table{{width:100%;border-collapse:collapse;font-size:13px;}}
th,td{{border-bottom:1px solid #e8edf5;padding:8px;vertical-align:top;text-align:left;}}
th{{color:#526174;background:#f7f9fc;position:sticky;top:0;}}
.scroll{{max-height:460px;overflow:auto;}}
.meta{{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin:16px 0;}}
.metric{{background:#fff;border:1px solid #dfe6f2;border-radius:8px;padding:12px;}}
.metric strong{{display:block;font-size:20px;color:#c51f2f;}}
p{{line-height:1.65;}}
@media(max-width:900px){{.grid,.meta{{grid-template-columns:1fr;}}main{{padding:16px;}}}}
</style>
</head>
<body>
<main>
  <h1>视频粗剪审核</h1>
  <div class="meta">
    <div class="metric"><span>原始时长</span><strong>{manifest['source_duration_sec']:.1f}s</strong></div>
    <div class="metric"><span>删除时长</span><strong>{manifest['removed_duration_sec']:.1f}s</strong></div>
    <div class="metric"><span>输出时长</span><strong>{manifest['edited_duration_sec']:.1f}s</strong></div>
    <div class="metric"><span>删除段数</span><strong>{len(deletes)}</strong></div>
  </div>
  <section class="grid">
    <div class="panel"><h2>原视频</h2><video controls src="{source_video.resolve().as_uri()}"></video></div>
    <div class="panel"><h2>粗剪后</h2><video controls src="{edited_video.resolve().as_uri()}"></video></div>
  </section>
  <section class="panel" style="margin-top:18px">
    <h2>删除段</h2>
    <div class="scroll"><table><thead><tr><th>#</th><th>时间</th><th>原因</th><th>置信</th><th>文本</th></tr></thead><tbody>{rows}</tbody></table></div>
  </section>
  <section class="panel" style="margin-top:18px">
    <h2>转录文本</h2>
    <div class="scroll">{transcript}</div>
  </section>
</main>
</body>
</html>"""
    write_text(path, content)


def build_manifest(
    *,
    source: Path,
    output: Path,
    review: Path,
    srt: Path,
    softsub: Path,
    candidates: Path,
    deletes: list[dict[str, Any]],
    source_duration: float,
    edited_duration: float,
    engine: str,
) -> dict[str, Any]:
    removed = sum(float(item["end"]) - float(item["start"]) for item in deletes)
    return {
        "stage": "video_roughcut",
        "status": "rendered",
        "engine": engine,
        "created_at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        "source_video": str(source.resolve()),
        "source_duration_sec": round(source_duration, 3),
        "edited_video": str(output.resolve()),
        "edited_duration_sec": round(edited_duration, 3),
        "removed_duration_sec": round(removed, 3),
        "delete_segment_count": len(deletes),
        "delete_segments": str(candidates.resolve()),
        "subtitle_srt": str(srt.resolve()),
        "softsub_video": str(softsub.resolve()),
        "review_html": str(review.resolve()),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Newma FunASR-based talking-head rough cut")
    parser.add_argument("--input-video", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--hotwords", default=DEFAULT_HOTWORDS)
    parser.add_argument("--device", default=os.getenv("FUNASR_DEVICE", "cpu"))
    parser.add_argument("--silence-threshold", default="-55dB")
    parser.add_argument("--min-silence", type=float, default=0.62)
    parser.add_argument("--silence-padding", type=float, default=0.16)
    parser.add_argument("--max-silence-remove-ratio", type=float, default=0.35)
    parser.add_argument("--mode", choices=["conservative", "balanced"], default="balanced")
    parser.add_argument(
        "--transcribe-only",
        action="store_true",
        help="Generate aligned ASR artifacts without rendering another video copy.",
    )
    args = parser.parse_args()

    source = Path(args.input_video).expanduser().resolve()
    out_dir = Path(args.output_dir).expanduser().resolve()
    work_dir = out_dir / "work"
    final_dir = out_dir / "final"
    review_dir = out_dir / "review"
    if not source.exists():
        raise SystemExit(f"input video not found: {source}")
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        raise SystemExit("ffmpeg/ffprobe is required")

    source_duration = ffprobe_duration(source)
    audio = work_dir / "source_16k.wav"
    extract_audio(source, audio)
    segments, asr_payload = transcribe_funasr(audio, args.hotwords, args.device)
    segments, asr_payload, timebase_correction = align_asr_timebase(segments, asr_payload, source_duration)
    write_json(work_dir / "funasr_raw.json", asr_payload)
    write_json(work_dir / "segments.json", [seg.as_dict() for seg in segments])

    if args.transcribe_only:
        srt = out_dir / f"{source.stem}_funasr_locked.srt"
        write_srt(srt, segments, [])
        manifest = {
            "stage": "video_transcription_lock",
            "status": "transcribed",
            "engine": "funasr_paraformer_zh_fsmn_vad_ct_punc",
            "created_at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
            "source_video": str(source.resolve()),
            "source_duration_sec": round(source_duration, 3),
            "segment_count": len(segments),
            "segments": str((work_dir / "segments.json").resolve()),
            "funasr_raw": str((work_dir / "funasr_raw.json").resolve()),
            "subtitle_srt": str(srt.resolve()),
            "asr_timebase_correction": timebase_correction,
        }
        write_json(out_dir / "transcription_manifest.json", manifest)
        print(json.dumps(manifest, ensure_ascii=False, indent=2))
        return

    silence = silence_ranges(audio, source_duration, args.silence_threshold, args.min_silence, args.silence_padding)
    semantic = semantic_candidates(segments)
    raw_candidates = guard_unreliable_silence(silence + semantic, source_duration, args.max_silence_remove_ratio)
    if args.mode == "conservative":
        raw_candidates = [item for item in raw_candidates if item["reason"] == "silence" or item["confidence"] >= 0.88]
    deletes = merge_ranges(raw_candidates, source_duration)
    keep = complement_ranges(deletes, source_duration)

    candidates_path = work_dir / "delete_segments.json"
    keep_path = work_dir / "keep_segments.json"
    write_json(candidates_path, deletes)
    write_json(keep_path, keep)

    edited = final_dir / f"{source.stem}_roughcut_funasr.mp4"
    render_concat(source, keep, edited, work_dir)
    srt = final_dir / f"{source.stem}_roughcut_funasr.srt"
    write_srt(srt, segments, deletes)
    softsub = final_dir / f"{source.stem}_roughcut_funasr_softsub.mp4"
    render_softsub_video(edited, srt, softsub)
    edited_duration = ffprobe_duration(edited)
    review = review_dir / "3_review_live.html"
    manifest = build_manifest(
        source=source,
        output=edited,
        review=review,
        srt=srt,
        softsub=softsub,
        candidates=candidates_path,
        deletes=deletes,
        source_duration=source_duration,
        edited_duration=edited_duration,
        engine="funasr_paraformer_zh_fsmn_vad_ct_punc",
    )
    manifest.update(
        {
            "review_mode": "interactive",
            "asr_timebase_correction": timebase_correction,
            "review_outputs": {
                "reviewed_video": str((review_dir / "reviewed_output_loud.mp4").resolve()),
                "reviewed_srt": str((review_dir / "reviewed_output_loud.srt").resolve()),
                "reviewed_softsub_video": str((review_dir / "reviewed_output_loud_softsub.mp4").resolve()),
                "proofread_agent_input": str((review_dir / "proofread_agent_input.md").resolve()),
            },
        }
    )
    manifest.update(
        write_review_package(
            review_dir,
            source=source,
            segments=segments,
            deletes=deletes,
            manifest=manifest,
        )
    )
    write_json(out_dir / "roughcut_manifest.json", manifest)
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
