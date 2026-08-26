#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path
from typing import Any


def ffprobe(path: Path) -> dict[str, Any]:
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration:stream=codec_type,codec_name,width,height,r_frame_rate,sample_rate,channels",
            "-of",
            "json",
            str(path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(result.stdout)


def duration(payload: dict[str, Any]) -> float:
    return float((payload.get("format") or {}).get("duration") or 0)


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit generated digital-human media before director handoff.")
    parser.add_argument("--job", required=True)
    parser.add_argument("--video")
    parser.add_argument("--output")
    args = parser.parse_args()

    job_path = Path(args.job).expanduser().resolve()
    job = json.loads(job_path.read_text(encoding="utf-8"))
    video = Path(args.video or job["outputs"]["presenter_video"]).expanduser().resolve()
    audio = Path(job["inputs"]["audio"]).expanduser().resolve()
    output = Path(args.output or job["outputs"]["qc"]).expanduser().resolve()
    failures: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []

    if (job.get("presenter_source") or {}).get("consent", {}).get("status") != "confirmed":
        failures.append({"code": "consent_missing", "message": "肖像授权未确认。"})
    if not video.is_file():
        failures.append({"code": "video_missing", "message": f"数字人视频不存在：{video}"})
    if not audio.is_file():
        failures.append({"code": "audio_missing", "message": f"MiniMax 主音频不存在：{audio}"})

    video_probe = ffprobe(video) if video.is_file() else {}
    audio_probe = ffprobe(audio) if audio.is_file() else {}
    video_duration = duration(video_probe)
    audio_duration = duration(audio_probe)
    drift = abs(video_duration - audio_duration)
    if video_duration and audio_duration and drift > 0.25:
        failures.append(
            {
                "code": "audio_video_duration_drift",
                "message": "数字人视频与 MiniMax 主音频时长漂移超过 0.25 秒。",
                "drift_sec": round(drift, 3),
            }
        )
    video_streams = [row for row in video_probe.get("streams") or [] if row.get("codec_type") == "video"]
    audio_streams = [row for row in video_probe.get("streams") or [] if row.get("codec_type") == "audio"]
    if video.is_file() and not video_streams:
        failures.append({"code": "missing_video_stream", "message": "输出没有视频流。"})
    expected_audio_policy = str(job.get("voice", {}).get("mount_policy") or "")
    if expected_audio_policy == "exactly_once_at_remotion_root" and audio_streams:
        failures.append(
            {
                "code": "presenter_video_contains_audio",
                "message": "数字人源视频必须是无声视觉层，避免与 Remotion 根节点的 MiniMax 主音频双挂。",
            }
        )
    if video.is_file() and not audio_streams:
        warnings.append({"code": "silent_presenter_video", "message": "数字人源视频为无声视觉层；Remotion 需在根节点挂载原 MiniMax 音频一次。"})

    report = {
        "schema_version": "dasheng.digital_human_qc.v1",
        "status": "pass" if not failures else "fail",
        "job": str(job_path),
        "video": str(video),
        "master_audio": str(audio),
        "video_duration_sec": round(video_duration, 3),
        "audio_duration_sec": round(audio_duration, 3),
        "duration_drift_sec": round(drift, 3),
        "failures": failures,
        "warnings": warnings,
        "manual_review_required": [
            "身份是否稳定",
            "口型是否与中文音节同步",
            "牙齿、舌头、眼睛是否出现明显伪影",
            "头动是否自然且不过度",
            "背景和画面四角是否稳定",
            "是否已标注 AI 数字人",
        ],
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(str(output))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
