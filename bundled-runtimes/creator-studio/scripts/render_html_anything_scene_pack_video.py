#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

from video_tts_pronunciation import normalize_tts_text

DEFAULT_MMX_VOICE = "tianxin_xiaoling"
DEFAULT_MMX_MODEL = "speech-2.8-hd"
DEFAULT_MMX_SPEED = 1.2

REMOVED_STATIC_RENDERER_MESSAGE = (
    "The legacy screenshot/zoompan renderer has been removed. "
    "Use scripts/render_html_anything_scene_pack_animated.py so HTML/GSAP/Lottie scenes are recorded as real animation."
)

EVIDENCE_PARTS = {"data_chart", "financial_chart", "data_table", "article_image", "news_or_document", "source_citation"}
FORBIDDEN_VISIBLE_TERMS = [
    "content_part:",
    "template_id:",
    "template:",
    "slot:",
    "position:",
    "workflow:",
    "developer:",
    "data-director-policy",
    "data-motion-policy",
]


class RenderError(RuntimeError):
    pass


def run(cmd: list[str]) -> None:
    proc = subprocess.run(cmd, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    if proc.returncode != 0:
        raise RenderError(proc.stderr or proc.stdout or "command failed")


def run_capture(cmd: list[str]) -> str:
    proc = subprocess.run(cmd, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    if proc.returncode != 0:
        raise RenderError(proc.stderr or proc.stdout or "command failed")
    return proc.stdout.strip()


def run_capture_combined(cmd: list[str]) -> str:
    proc = subprocess.run(cmd, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    if proc.returncode != 0:
        raise RenderError(proc.stderr or proc.stdout or "command failed")
    return "\n".join(part for part in [proc.stdout.strip(), proc.stderr.strip()] if part)


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def ffprobe_duration(path: Path) -> float:
    output = run_capture(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=nk=1:nw=1",
            str(path),
        ]
    )
    return float(output)


def ffmpeg_mean_volume(path: Path) -> float | None:
    try:
        output = run_capture_combined(
            [
                "ffmpeg",
                "-hide_banner",
                "-nostats",
                "-i",
                str(path),
                "-af",
                "volumedetect",
                "-f",
                "null",
                "-",
            ]
        )
    except RenderError:
        return None
    match = re.search(r"mean_volume:\s*(-?\d+(?:\.\d+)?)\s*dB", output)
    return float(match.group(1)) if match else None


def visible_text_from_html(path: Path) -> str:
    text = path.read_text(encoding="utf-8", errors="ignore")
    text = re.sub(r"<!--.*?-->", " ", text, flags=re.S)
    text = re.sub(r"<script\b.*?</script>", " ", text, flags=re.S | re.I)
    text = re.sub(r"<style\b.*?</style>", " ", text, flags=re.S | re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def scene_has_real_evidence(scene: dict[str, Any]) -> bool:
    part = str(scene.get("content_part") or "")
    if part not in EVIDENCE_PARTS and not str(scene.get("beat_class") or "").startswith("evidence"):
        return True
    variables = scene.get("variables") or {}
    if variables.get("table") or variables.get("rows") or variables.get("src") or variables.get("metrics"):
        return True
    text = " ".join(str(scene.get(key) or "") for key in ["title", "narration"])
    return bool(re.search(r"\d|%|万亿|亿美元|bp|IPO|VIX|纳指|美债|半导体|比特币", text, re.I))


def build_qc_report(
    manifest: dict[str, Any],
    *,
    output_dir: Path,
    silent_result: dict[str, Any],
    voice_result: dict[str, Any] | None,
) -> dict[str, Any]:
    scenes = manifest.get("scenes") or []
    failures: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []

    last_evidence_end = 0.0
    evidence_seen = False
    for scene in scenes:
        scene_id = scene.get("id")
        start = float(scene.get("start_sec") or 0)
        end = float(scene.get("end_sec") or start + float(scene.get("duration_sec") or 0))
        duration = float(scene.get("duration_sec") or max(0.0, end - start))
        part = str(scene.get("content_part") or "")
        beat = str(scene.get("beat_class") or "")
        motion = scene.get("motion_policy") or {}
        is_evidence = part in EVIDENCE_PARTS or beat.startswith("evidence")

        if is_evidence:
            evidence_seen = True
            if start - last_evidence_end > 40:
                failures.append(
                    {
                        "code": "evidence_gap_too_long",
                        "scene_id": scene_id,
                        "gap_sec": round(start - last_evidence_end, 3),
                        "message": "无真人科普线超过 40 秒没有证据/数据/资料画面。",
                    }
                )
            last_evidence_end = end
            if not scene_has_real_evidence(scene):
                failures.append(
                    {
                        "code": "evidence_without_real_data",
                        "scene_id": scene_id,
                        "content_part": part,
                        "message": "证据场景缺少来自文章表格、图片或明确数字的支撑。",
                    }
                )

        if duration > 12 and not motion:
            failures.append(
                {
                    "code": "long_scene_without_motion",
                    "scene_id": scene_id,
                    "duration_sec": round(duration, 3),
                    "message": "超过 12 秒的场景没有声明运动策略。",
                }
            )

        html_path = Path(str(scene.get("html") or ""))
        if html_path.exists():
            visible_text = visible_text_from_html(html_path).lower()
            for term in FORBIDDEN_VISIBLE_TERMS:
                if term.lower() in visible_text:
                    failures.append(
                        {
                            "code": "visible_workflow_label",
                            "scene_id": scene_id,
                            "term": term,
                            "message": "最终画面可见开发/流程标签。",
                        }
                    )
                    break

    transition_cards = [scene for scene in scenes if str(scene.get("content_part") or "") == "transition"]
    if len(transition_cards) > max(2, len(scenes) // 12):
        warnings.append(
            {
                "code": "too_many_standalone_transition_cards",
                "transition_count": len(transition_cards),
                "scene_count": len(scenes),
                "message": "独立转场卡偏多，建议改为场景间运动/声音转场，减少黑底空卡。",
            }
        )

    if not evidence_seen:
        warnings.append({"code": "no_evidence_scene", "message": "时间线没有识别到证据/数据/资料场景。"})

    audio_report = None
    final_video = Path((voice_result or silent_result).get("final_video") or silent_result.get("final_video"))
    if final_video.exists():
        try:
            measured_duration = ffprobe_duration(final_video)
        except RenderError:
            measured_duration = None
        mean_volume = ffmpeg_mean_volume(final_video) if voice_result else None
        audio_report = {
            "video": str(final_video.resolve()),
            "duration_sec": round(measured_duration, 3) if measured_duration is not None else None,
            "mean_volume_db": mean_volume,
            "target_lufs": -16 if voice_result else None,
        }
        if voice_result and mean_volume is not None and mean_volume < -28:
            warnings.append(
                {
                    "code": "voice_mean_volume_low",
                    "mean_volume_db": mean_volume,
                    "message": "音频平均音量偏低，建议检查 TTS 源或响度标准化。",
                }
            )
    if voice_result:
        planned_duration = float(silent_result.get("duration_sec") or 0)
        voiced_duration = float(voice_result.get("duration_sec") or (audio_report or {}).get("duration_sec") or 0)
        if planned_duration > 0 and voiced_duration / planned_duration > 1.25:
            warnings.append(
                {
                    "code": "voiceover_stretches_visual_timeline",
                    "planned_duration_sec": round(planned_duration, 3),
                    "voiceover_duration_sec": round(voiced_duration, 3),
                    "ratio": round(voiced_duration / planned_duration, 3),
                    "message": "逐场景 TTS 明显拉长视觉时间线，建议改为整段旁白主时间轴或提高语速并压缩长段。",
                }
            )

    report = {
        "schema_version": "dasheng.video_qc_report.v1",
        "status": "pass" if not failures else "fail",
        "scene_count": len(scenes),
        "failure_count": len(failures),
        "warning_count": len(warnings),
        "checks": {
            "visible_workflow_labels": "fail_on_visible_text",
            "fake_or_unsourced_evidence": "fail",
            "explainer_evidence_gap_sec": 40,
            "long_static_scene_sec": 12,
            "audio_volume": "warn_if_mean_volume_below_-28db",
            "voiceover_timeline_ratio": "warn_if_voiceover_exceeds_visual_by_25_percent",
            "static_screenshot_renderer": "forbidden",
        },
        "audio": audio_report,
        "failures": failures,
        "warnings": warnings,
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "video_qc_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report


def build_mmx_speech_command(
    text_file: Path,
    output: Path,
    *,
    model: str,
    voice: str,
    speed: float,
    language: str,
) -> list[str]:
    cmd = ["mmx"]
    base_url = os.environ.get("MMX_BASE_URL")
    if base_url:
        cmd.extend(["--base-url", base_url])
    cmd.extend(
        [
            "speech",
            "synthesize",
            "--text-file",
            str(text_file),
            "--out",
            str(output),
            "--model",
            model,
            "--voice",
            voice,
            "--speed",
            f"{speed:g}",
            "--format",
            "wav",
            "--sample-rate",
            "44100",
            "--channels",
            "1",
            "--language",
            language,
            "--quiet",
            "--non-interactive",
        ]
    )
    return cmd


def canonicalize_wav(source: Path, output: Path) -> None:
    run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-i",
            str(source),
            "-ac",
            "1",
            "-ar",
            "44100",
            str(output),
        ]
    )


def synthesize_audio_with_mmx(
    text: str,
    output: Path,
    *,
    model: str,
    voice: str,
    speed: float,
    language: str,
) -> float:
    if not shutil.which("mmx"):
        raise RenderError("MiniMax CLI `mmx` is required for production voiceover.")
    output.parent.mkdir(parents=True, exist_ok=True)
    text_file = output.with_suffix(".txt")
    raw = output.with_name(f"{output.stem}.mmx.raw.wav")
    text_file.write_text(text.strip() or "。", encoding="utf-8")
    run(build_mmx_speech_command(text_file, raw, model=model, voice=voice, speed=speed, language=language))
    canonicalize_wav(raw, output)
    raw.unlink(missing_ok=True)
    return ffprobe_duration(output)


def synthesize_audio_with_say(text: str, output: Path, *, voice: str, rate: int) -> float:
    if not shutil.which("say"):
        raise RenderError("macOS say is required for fallback preview voiceover.")
    output.parent.mkdir(parents=True, exist_ok=True)
    aiff = output.with_suffix(".aiff")
    run(["say", "-v", voice, "-r", str(rate), "-o", str(aiff), text])
    canonicalize_wav(aiff, output)
    aiff.unlink(missing_ok=True)
    return ffprobe_duration(output)


def synthesize_audio(
    text: str,
    output: Path,
    *,
    provider: str,
    voice: str,
    rate: int,
    mmx_model: str,
    mmx_speed: float,
    mmx_language: str,
) -> float:
    if provider == "mmx":
        return synthesize_audio_with_mmx(
            text,
            output,
            model=mmx_model,
            voice=voice,
            speed=mmx_speed,
            language=mmx_language,
        )
    if provider == "say":
        return synthesize_audio_with_say(text, output, voice=voice, rate=rate)
    raise RenderError(f"Unsupported voice provider: {provider}")


def scene_narration(scene: dict[str, Any]) -> str:
    explicit = str(scene.get("narration_tts") or "").strip()
    if explicit:
        return explicit
    return normalize_tts_text(str(scene.get("narration") or scene.get("title") or "").strip())


def combined_narration_text(scenes: list[dict[str, Any]]) -> str:
    lines: list[str] = []
    for scene in scenes:
        text = scene_narration(scene)
        if not text:
            continue
        if text[-1] not in "。！？!?":
            text += "。"
        lines.append(text)
    return "\n".join(lines).strip() or "。"


def allocate_voice_durations(scenes: list[dict[str, Any]], total_duration: float, *, min_sec: float = 1.2) -> list[float]:
    if not scenes:
        return []
    weights = [max(6, len(scene_narration(scene))) for scene in scenes]
    total_weight = sum(weights) or len(scenes)
    raw = [total_duration * weight / total_weight for weight in weights]
    durations = [max(min_sec, item) for item in raw]
    overflow = sum(durations) - total_duration
    if overflow > 0:
        adjustable = [idx for idx, item in enumerate(durations) if item > min_sec]
        while overflow > 0.001 and adjustable:
            share = overflow / len(adjustable)
            next_adjustable = []
            for idx in adjustable:
                reduce_by = min(share, durations[idx] - min_sec)
                durations[idx] -= reduce_by
                overflow -= reduce_by
                if durations[idx] > min_sec + 0.001:
                    next_adjustable.append(idx)
            if len(next_adjustable) == len(adjustable):
                break
            adjustable = next_adjustable
    rounded = [round(max(0.4, item), 3) for item in durations]
    rounded[-1] = round(max(0.4, rounded[-1] + (round(total_duration, 3) - sum(rounded))), 3)
    return rounded


def format_srt_time(seconds: float) -> str:
    ms = int(round((seconds - math.floor(seconds)) * 1000))
    total = int(math.floor(seconds))
    if ms == 1000:
        total += 1
        ms = 0
    return f"{total // 3600:02d}:{(total % 3600) // 60:02d}:{total % 60:02d},{ms:03d}"


def render_pack(*_: Any, **__: Any) -> dict[str, Any]:
    raise RenderError(REMOVED_STATIC_RENDERER_MESSAGE)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Removed static renderer compatibility shim.")
    parser.add_argument("--manifest")
    parser.add_argument("--output-dir")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--with-voice", action="store_true")
    parser.add_argument("--voice-mode")
    parser.add_argument("--voice-provider")
    parser.add_argument("--voice")
    parser.add_argument("--rate", type=int)
    parser.add_argument("--mmx-model")
    parser.add_argument("--mmx-speed", type=float)
    parser.add_argument("--mmx-language")
    return parser.parse_args()


def main() -> None:
    parse_args()
    raise SystemExit(REMOVED_STATIC_RENDERER_MESSAGE)


if __name__ == "__main__":
    main()
