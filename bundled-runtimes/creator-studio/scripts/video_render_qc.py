#!/usr/bin/env python3
"""Render-level QC for talking-head and explainer videos."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any

import cv2
import numpy as np


BLACK_RE = re.compile(
    r"black_start:(?P<start>[\d.]+)\s+black_end:(?P<end>[\d.]+)\s+black_duration:(?P<duration>[\d.]+)"
)
PTS_RE = re.compile(r"pts_time:(?P<time>[\d.]+)")
YAVG_RE = re.compile(r"lavfi\.signalstats\.YAVG=(?P<value>[\d.]+)")
YMIN_RE = re.compile(r"lavfi\.signalstats\.YMIN=(?P<value>[\d.]+)")
YMAX_RE = re.compile(r"lavfi\.signalstats\.YMAX=(?P<value>[\d.]+)")
SHOWINFO_TIME_RE = re.compile(r"\[Parsed_showinfo_[^\]]+\].*?pts_time:(?P<time>[\d.]+)")


def run(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def probe_video(path: Path) -> dict[str, Any]:
    proc = run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "stream=index,codec_type,codec_name,width,height,duration:format=duration,size,bit_rate",
            "-of",
            "json",
            str(path),
        ]
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or "ffprobe failed")
    return json.loads(proc.stdout)


def detect_dark_runs(path: Path, *, minimum_duration: float = 0.18) -> list[dict[str, float]]:
    proc = run(
        [
            "ffmpeg",
            "-hide_banner",
            "-nostats",
            "-i",
            str(path),
            "-vf",
            f"blackdetect=d={minimum_duration}:pix_th=0.05:pic_th=0.98",
            "-an",
            "-f",
            "null",
            "-",
        ]
    )
    return [
        {
            "start": float(match.group("start")),
            "end": float(match.group("end")),
            "duration": float(match.group("duration")),
        }
        for match in BLACK_RE.finditer(proc.stderr)
    ]


def sample_frame_stats(path: Path, *, fps: int = 8) -> list[dict[str, float]]:
    proc = run(
        [
            "ffmpeg",
            "-hide_banner",
            "-nostats",
            "-i",
            str(path),
            "-vf",
            f"fps={fps},scale=64:36,signalstats,metadata=print",
            "-an",
            "-f",
            "null",
            "-",
        ]
    )
    samples: list[dict[str, float]] = []
    current: dict[str, float] = {}
    for line in proc.stderr.splitlines():
        pts_match = PTS_RE.search(line)
        if pts_match:
            if {"time", "yavg", "ymin", "ymax"} <= current.keys():
                samples.append(current)
            current = {"time": float(pts_match.group("time"))}
            continue
        value_match = YAVG_RE.search(line)
        if value_match and current:
            current["yavg"] = float(value_match.group("value"))
            continue
        min_match = YMIN_RE.search(line)
        if min_match and current:
            current["ymin"] = float(min_match.group("value"))
            continue
        max_match = YMAX_RE.search(line)
        if max_match and current:
            current["ymax"] = float(max_match.group("value"))
    if {"time", "yavg", "ymin", "ymax"} <= current.keys():
        samples.append(current)
    return samples


def sample_luma(path: Path, *, fps: int = 8) -> list[tuple[float, float]]:
    return [(item["time"], item["yavg"]) for item in sample_frame_stats(path, fps=fps)]


def find_luma_pulses(
    samples: list[tuple[float, float]],
    *,
    low_ceiling: float = 24.0,
    recovery_samples: int = 4,
) -> list[dict[str, float]]:
    pulses: list[dict[str, float]] = []
    last_pulse_at = -10.0
    for index in range(1, max(1, len(samples) - recovery_samples)):
        time, value = samples[index]
        if time - last_pulse_at < 0.5 or value > low_ceiling:
            continue
        previous = samples[index - 1][1]
        future = samples[index + 1 : index + 1 + recovery_samples]
        if not future:
            continue
        recovered_time, recovered_value = max(future, key=lambda item: item[1])
        if previous - value < 4.0 or recovered_value - value < 4.0:
            continue
        if recovered_value <= 0 or value / recovered_value >= 0.85:
            continue
        pulses.append(
            {
                "start": round(time, 3),
                "recovered_at": round(recovered_time, 3),
                "start_luma": round(value, 3),
                "recovered_luma": round(recovered_value, 3),
            }
        )
        last_pulse_at = time
    return pulses


def find_flat_frame_pulses(
    samples: list[dict[str, float]],
    *,
    flat_range_ceiling: float = 3.0,
    neighbor_range_floor: float = 24.0,
) -> list[dict[str, float]]:
    pulses: list[dict[str, float]] = []
    for index in range(1, len(samples) - 1):
        current = samples[index]
        previous = samples[index - 1]
        following = samples[index + 1]
        current_range = current["ymax"] - current["ymin"]
        previous_range = previous["ymax"] - previous["ymin"]
        following_range = following["ymax"] - following["ymin"]
        if current_range > flat_range_ceiling:
            continue
        if previous_range < neighbor_range_floor or following_range < neighbor_range_floor:
            continue
        pulses.append(
            {
                "time": round(current["time"], 3),
                "luma": round(current.get("yavg", (current["ymin"] + current["ymax"]) / 2), 3),
                "range": round(current_range, 3),
                "previous_range": round(previous_range, 3),
                "following_range": round(following_range, 3),
            }
        )
    return pulses


def detect_strong_visual_changes(path: Path, *, threshold: float = 0.22) -> list[float]:
    proc = run(
        [
            "ffmpeg",
            "-hide_banner",
            "-nostats",
            "-i",
            str(path),
            "-vf",
            f"select='gt(scene,{threshold})',showinfo",
            "-an",
            "-f",
            "null",
            "-",
        ]
    )
    return [float(match.group("time")) for match in SHOWINFO_TIME_RE.finditer(proc.stderr)]


def detect_motion_changes(
    path: Path,
    *,
    sample_interval_sec: float = 0.5,
    mean_difference_threshold: float = 8.0,
    minimum_gap_sec: float = 0.75,
) -> list[float]:
    """Count gradual HTML animation beats that FFmpeg scene cuts miss.

    Scene-cut detection is intentionally strict, but animated cards, chart
    reveals, and focus-stage dissolves often happen over several frames. This
    sampler measures the actual rendered pixel delta at a coarse resolution.
    """
    capture = cv2.VideoCapture(str(path))
    if not capture.isOpened():
        return []
    fps = float(capture.get(cv2.CAP_PROP_FPS) or 30.0)
    sample_step = max(1, int(round(fps * sample_interval_sec)))
    previous: np.ndarray | None = None
    changes: list[float] = []
    frame_index = 0
    last_change = -minimum_gap_sec
    while True:
        ok, frame = capture.read()
        if not ok:
            break
        if frame_index % sample_step == 0:
            gray = cv2.cvtColor(cv2.resize(frame, (160, 90)), cv2.COLOR_BGR2GRAY)
            if previous is not None:
                difference = float(np.mean(cv2.absdiff(gray, previous)))
                timestamp = frame_index / fps
                if difference >= mean_difference_threshold and timestamp - last_change >= minimum_gap_sec:
                    changes.append(timestamp)
                    last_change = timestamp
            previous = gray
        frame_index += 1
    capture.release()
    return changes


def merge_change_times(*groups: list[float], minimum_gap_sec: float = 0.35) -> list[float]:
    merged: list[float] = []
    for value in sorted(value for group in groups for value in group):
        if not merged or value - merged[-1] >= minimum_gap_sec:
            merged.append(value)
    return merged


def evaluate_visual_change_density(
    *,
    duration_sec: float,
    change_times: list[float],
    minimum_per_minute: float,
) -> dict[str, Any]:
    changes_per_minute = len(change_times) * 60 / duration_sec if duration_sec > 0 else 0.0
    return {
        "status": "pass" if changes_per_minute >= minimum_per_minute else "fail",
        "change_count": len(change_times),
        "changes_per_minute": round(changes_per_minute, 2),
        "minimum_per_minute": minimum_per_minute,
        "change_times": [round(value, 3) for value in change_times[:100]],
    }


def measure_loudness(path: Path) -> dict[str, float] | None:
    proc = run(
        [
            "ffmpeg",
            "-hide_banner",
            "-nostats",
            "-i",
            str(path),
            "-af",
            "loudnorm=I=-16:LRA=11:TP=-1.5:print_format=json",
            "-f",
            "null",
            "-",
        ]
    )
    matches = list(re.finditer(r"\{\s*\"input_i\".*?\}", proc.stderr, re.S))
    if not matches:
        return None
    payload = json.loads(matches[-1].group(0))
    return {
        "integrated_lufs": float(payload["input_i"]),
        "true_peak_db": float(payload["input_tp"]),
        "loudness_range_lu": float(payload["input_lra"]),
    }


def scene_plan_duration(plan: dict[str, Any]) -> float:
    scenes = plan.get("scenes") or plan.get("segments") or []
    explicit_end = max(
        (
            float(scene.get("end_sec", scene.get("end", 0.0)) or 0.0)
            for scene in scenes
        ),
        default=0.0,
    )
    if explicit_end > 0:
        return explicit_end
    return sum(float(scene.get("duration_sec", scene.get("duration", 0.0)) or 0.0) for scene in scenes)


def audit_video(
    video: Path,
    *,
    scene_plan: dict[str, Any] | None = None,
    check_loudness: bool = True,
    target_lufs: float = -16.0,
    loudness_tolerance: float = 1.5,
) -> dict[str, Any]:
    probe = probe_video(video)
    streams = probe.get("streams") or []
    video_streams = [stream for stream in streams if stream.get("codec_type") == "video"]
    audio_streams = [stream for stream in streams if stream.get("codec_type") == "audio"]
    duration = float((probe.get("format") or {}).get("duration") or 0.0)
    dark_runs = detect_dark_runs(video)
    frame_stats = sample_frame_stats(video)
    luma_pulses = find_luma_pulses([(item["time"], item["yavg"]) for item in frame_stats])
    flat_frame_pulses = find_flat_frame_pulses(frame_stats)
    lane = str((scene_plan or {}).get("lane") or "")
    rhythm_policy = (scene_plan or {}).get("visual_rhythm_policy") or {}
    minimum_visual_changes = float(
        rhythm_policy.get("minimum_strong_visual_changes_per_minute")
        or (12.0 if lane in {"talking_head_video", "digital_human_video"} else 8.0)
    )
    maximum_visual_changes = rhythm_policy.get("maximum_strong_visual_changes_per_minute")
    maximum_visual_changes = float(maximum_visual_changes) if maximum_visual_changes is not None else None
    hard_cut_times = detect_strong_visual_changes(video) if duration >= 10 else []
    motion_change_times = detect_motion_changes(video) if duration >= 10 else []
    strong_change_times = merge_change_times(hard_cut_times, motion_change_times)
    visual_change_density = evaluate_visual_change_density(
        duration_sec=duration,
        change_times=strong_change_times,
        minimum_per_minute=minimum_visual_changes,
    )
    loudness = measure_loudness(video) if check_loudness and audio_streams else None
    failures: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []

    if not video_streams:
        failures.append({"code": "video_stream_missing", "message": "终片没有视频流。"})
    if not audio_streams:
        failures.append({"code": "audio_stream_missing", "message": "终片没有音频流。"})
    if dark_runs:
        failures.append(
            {
                "code": "dark_frame_run",
                "message": "检测到持续暗场/黑场，可能来自场景渐入空窗或错误转场。",
                "runs": dark_runs[:20],
                "total_duration_sec": round(sum(item["duration"] for item in dark_runs), 3),
            }
        )
    if len(luma_pulses) >= 3:
        failures.append(
            {
                "code": "dark_entry_pulses",
                "message": "检测到反复的低亮度入场脉冲，通常来自素材层先变暗、卡片随后渐入。",
                "events": luma_pulses[:30],
                "count": len(luma_pulses),
            }
        )
    elif luma_pulses:
        warnings.append(
            {
                "code": "dark_entry_pulse_warning",
                "message": "检测到少量低亮度入场脉冲，请人工确认是否为有意的章节黑场。",
                "events": luma_pulses,
            }
        )
    if flat_frame_pulses:
        failures.append(
            {
                "code": "flat_transition_frames",
                "message": "检测到夹在正常画面之间的纯色/近纯色空白帧，通常来自非重叠淡入淡出。",
                "events": flat_frame_pulses[:30],
                "count": len(flat_frame_pulses),
            }
        )
    if duration >= 10 and visual_change_density["status"] == "fail":
        failures.append(
            {
                "code": "visual_change_density_too_low",
                "message": "有效强视觉变化密度过低，成片仍可能呈现为模板幻灯片。",
                **visual_change_density,
            }
        )
    if (
        duration >= 10
        and maximum_visual_changes is not None
        and visual_change_density["changes_per_minute"] > maximum_visual_changes
    ):
        failures.append(
            {
                "code": "visual_change_density_too_high",
                "message": "有效视觉变化密度超过导演上限，可能存在短分镜反复切换并破坏核心场景的问题。",
                **visual_change_density,
                "maximum_per_minute": maximum_visual_changes,
            }
        )

    plan_duration = None
    if scene_plan is not None:
        plan_duration = scene_plan_duration(scene_plan)
        drift = abs(plan_duration - duration)
        if drift > 0.25:
            failures.append(
                {
                    "code": "timeline_duration_drift",
                    "message": "分镜时间轴与最终视频时长不一致。",
                    "scene_plan_duration_sec": round(plan_duration, 3),
                    "video_duration_sec": round(duration, 3),
                    "drift_sec": round(drift, 3),
                }
            )
        alignment = scene_plan.get("timeline_alignment") or {}
        if alignment.get("mode") == "global_scale":
            failures.append(
                {
                    "code": "global_time_scale_after_roughcut",
                    "message": "最终渲染仍在使用全局时间缩放，未锁定离散粗剪 EDL。",
                }
            )

    if loudness is not None and abs(loudness["integrated_lufs"] - target_lufs) > loudness_tolerance:
        failures.append(
            {
                "code": "voice_loudness_out_of_range",
                "message": "成片综合响度偏离目标范围。",
                "actual_lufs": loudness["integrated_lufs"],
                "target_lufs": target_lufs,
                "tolerance_lu": loudness_tolerance,
            }
        )

    return {
        "schema_version": "dasheng.video.render_qc.v1",
        "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "status": "pass" if not failures else "fail",
        "video": str(video),
        "metrics": {
            "duration_sec": round(duration, 3),
            "scene_plan_duration_sec": round(plan_duration, 3) if plan_duration is not None else None,
            "video_stream_count": len(video_streams),
            "audio_stream_count": len(audio_streams),
            "dark_run_count": len(dark_runs),
            "dark_run_total_sec": round(sum(item["duration"] for item in dark_runs), 3),
            "dark_entry_pulse_count": len(luma_pulses),
            "flat_transition_frame_count": len(flat_frame_pulses),
        "strong_visual_change_count": visual_change_density["change_count"],
        "hard_cut_count": len(hard_cut_times),
        "motion_change_count": len(motion_change_times),
            "strong_visual_changes_per_minute": visual_change_density["changes_per_minute"],
            "minimum_strong_visual_changes_per_minute": minimum_visual_changes,
            "loudness": loudness,
        },
        "probe": probe,
        "failures": failures,
        "warnings": warnings,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run render-level QC on a generated video.")
    parser.add_argument("--video", required=True)
    parser.add_argument("--scene-plan", default="")
    parser.add_argument("--output", default="")
    parser.add_argument("--skip-loudness", action="store_true")
    parser.add_argument("--target-lufs", type=float, default=-16.0)
    parser.add_argument("--loudness-tolerance", type=float, default=1.5)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    video = Path(args.video).expanduser().resolve()
    plan = read_json(Path(args.scene_plan).expanduser().resolve()) if args.scene_plan else None
    report = audit_video(
        video,
        scene_plan=plan,
        check_loudness=not args.skip_loudness,
        target_lufs=args.target_lufs,
        loudness_tolerance=args.loudness_tolerance,
    )
    if args.output:
        write_json(Path(args.output).expanduser().resolve(), report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
