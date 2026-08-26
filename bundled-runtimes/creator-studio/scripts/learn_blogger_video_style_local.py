#!/usr/bin/env python3
"""Learn video style DNA locally through claude-real-video outputs.

This replaces the old native-video-upload path. No reference video is uploaded
to a model provider in this stage.
"""

from __future__ import annotations

import argparse
import json
import statistics
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from path_config import get_output_root


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_DIR = str(get_output_root("video_training"))
VIDEO_EXTS = {".mp4", ".mov", ".webm", ".mkv", ".avi", ".mpeg", ".mpg", ".wmv", ".3gp"}


class LocalStyleLearnError(RuntimeError):
    pass


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def run(cmd: list[str], check: bool = True) -> subprocess.CompletedProcess[str]:
    proc = subprocess.run(cmd, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    if check and proc.returncode != 0:
        raise LocalStyleLearnError(proc.stderr or proc.stdout or f"command failed: {cmd}")
    return proc


def discover_videos(video_dir: Path) -> list[Path]:
    return sorted(path for path in video_dir.iterdir() if path.is_file() and path.suffix.lower() in VIDEO_EXTS)


def ffprobe_metadata(video_path: Path) -> dict[str, Any]:
    proc = run(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=width,height,r_frame_rate:format=duration",
            "-of",
            "json",
            str(video_path),
        ]
    )
    payload = json.loads(proc.stdout)
    stream = (payload.get("streams") or [{}])[0]
    fmt = payload.get("format") or {}
    return {
        "filename": video_path.name,
        "path": str(video_path),
        "duration_sec": round(float(fmt.get("duration") or 0.0), 3),
        "width": int(stream.get("width") or 0),
        "height": int(stream.get("height") or 0),
        "fps": round(parse_fps(str(stream.get("r_frame_rate") or "0/1")), 2),
    }


def parse_fps(value: str) -> float:
    if "/" in value:
        num, den = value.split("/", 1)
        try:
            return float(num) / float(den)
        except (ValueError, ZeroDivisionError):
            return 0.0
    try:
        return float(value)
    except ValueError:
        return 0.0


def write_json(path: Path, payload: Any) -> None:
    ensure_dir(path.parent)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def run_crv(video: Path, output_dir: Path, args: argparse.Namespace) -> dict[str, Any]:
    cmd = [
        sys.executable,
        str(ROOT / "scripts" / "read_video_with_crv.py"),
        str(video),
        "--output-dir",
        str(output_dir),
        "--why",
        f"学习 {args.blogger_name or args.style_id} 的剪辑节奏、镜头构图、证据画面、转场和风格 DNA",
        "--max-frames",
        str(args.max_frames),
        "--fps-floor",
        str(args.fps_floor),
        "--scene",
        str(args.scene),
        "--dedup-threshold",
        str(args.dedup_threshold),
    ]
    if args.report:
        cmd.append("--report")
    if args.transcribe:
        cmd.append("--transcribe")
    proc = run(cmd)
    result = json.loads(proc.stdout)
    manifest_path = Path(result["dasheng_manifest"])
    return json.loads(manifest_path.read_text(encoding="utf-8"))


def analyze_video(video: Path, run_dir: Path, args: argparse.Namespace) -> dict[str, Any]:
    meta = ffprobe_metadata(video)
    crv_dir = ensure_dir(run_dir / "crv" / video.stem)
    crv_manifest = run_crv(video, crv_dir, args)
    outputs = crv_manifest.get("outputs") or {}
    frame_count = int(outputs.get("frame_count") or 0)
    duration = float(meta.get("duration_sec") or 0.0)
    cuts_per_min = round(frame_count / duration * 60.0, 2) if duration else 0.0
    aspect = f"{meta['width']}x{meta['height']}"
    analysis = {
        "schema_version": "dasheng.local_video_style_analysis.v1",
        "analyzed_at": now_iso(),
        "video_metadata": meta,
        "local_reading": {
            "provider": "claude-real-video",
            "manifest": crv_manifest.get("dasheng_manifest"),
            "crv_out_dir": outputs.get("out_dir"),
            "llm_manifest": outputs.get("manifest"),
            "frames_dir": outputs.get("frames_dir"),
            "frame_count": frame_count,
            "grids_dir": outputs.get("grids_dir"),
            "grid_count": outputs.get("grid_count"),
            "transcript": outputs.get("transcript"),
            "report_html": outputs.get("report_html"),
        },
        "per_video_style_dna": {
            "aspect_ratio": "9:16" if meta["height"] > meta["width"] else "16:9" if meta["width"] > meta["height"] else "1:1",
            "resolution": aspect,
            "pacing": {
                "keyframes_kept": frame_count,
                "keyframes_per_minute": cuts_per_min,
                "duration_sec": duration,
            },
            "evidence_style": "derive_from_manifest_and_contact_sheets",
            "motion_style": {
                "framework": "unknown_from_local_keyframes",
                "animation_signature": "requires downstream manifest/contact-sheet analysis",
            },
            "talking_head_policy": {
                "blank_placeholder": True,
                "notes": "Reference creator footage is style-only; user footage replaces it in production.",
            },
        },
        "notes": "本地读片结果，不上传视频。后续 Agent 读取 MANIFEST/contact sheets 继续抽风格细节。",
    }
    output = ensure_dir(run_dir / "per_video" / video.stem) / "analysis.json"
    write_json(output, analysis)
    return analysis


def aggregate_profile(args: argparse.Namespace, analyses: list[dict[str, Any]]) -> dict[str, Any]:
    durations = [float((a.get("video_metadata") or {}).get("duration_sec") or 0.0) for a in analyses]
    keyframes_per_min = [
        float(((a.get("per_video_style_dna") or {}).get("pacing") or {}).get("keyframes_per_minute") or 0.0)
        for a in analyses
    ]
    source_videos = [
        {
            **(a.get("video_metadata") or {}),
            "analyzed_at": a.get("analyzed_at"),
            "crv_manifest": ((a.get("local_reading") or {}).get("manifest")),
            "llm_manifest": ((a.get("local_reading") or {}).get("llm_manifest")),
            "grids_dir": ((a.get("local_reading") or {}).get("grids_dir")),
        }
        for a in analyses
    ]
    return {
        "schema_version": "dasheng.blogger_style_dna.v1",
        "style_id": args.style_id,
        "blogger_name": args.blogger_name,
        "blogger_platform": args.blogger_platform,
        "source_count": len(analyses),
        "source_videos": source_videos,
        "generated_at": now_iso(),
        "analysis_provider": "claude-real-video-local",
        "visual_dna": {
            "aspect_ratio": most_common([((a.get("per_video_style_dna") or {}).get("aspect_ratio") or "") for a in analyses]),
            "resolution": most_common([((a.get("per_video_style_dna") or {}).get("resolution") or "") for a in analyses]),
            "color_palette": {"dominant": [], "background": "", "accent": "", "text": "", "mood": "pending_contact_sheet_review"},
            "typography": {"title_style": "", "body_style": "", "number_style": "", "hierarchy": "", "chinese_english_mix": ""},
            "composition_patterns": ["pending_agent_review_of_crv_contact_sheets"],
            "visual_signature": "local keyframe/contact-sheet profile; refine after Agent review",
        },
        "editing_dna": {
            "pacing": {
                "avg_duration_sec": round(statistics.mean(durations), 2) if durations else 0.0,
                "avg_keyframes_per_minute": round(statistics.mean(keyframes_per_min), 2) if keyframes_per_min else 0.0,
                "min_keyframes_per_minute": round(min(keyframes_per_min), 2) if keyframes_per_min else 0.0,
                "max_keyframes_per_minute": round(max(keyframes_per_min), 2) if keyframes_per_min else 0.0,
            },
            "transitions": {"primary": "pending_contact_sheet_review", "signature": ""},
            "motion_style": {"framework": "unknown_local_reading", "animation_signature": ""},
            "audio_mood": {"bgm_genre": "", "bgm_energy": "", "sfx_density": "", "voice_style": ""},
            "hook_pattern": "",
            "outro_pattern": "",
            "evidence_style": "pending_manifest_review",
            "talking_head_policy": {"presence": True, "blank_placeholder": True, "notes": "Style-only; user footage replaces creator footage."},
            "b_roll_density": "pending_contact_sheet_review",
        },
        "template_preferences": {},
        "beat_class_distribution": {},
        "reference_prompt": "优先参考本地 CRV contact sheets 与 MANIFEST，总结剪辑节奏、构图状态、证据密度与转场签名。",
        "notes": "Local-only first-pass style profile. Reference videos are not uploaded in this stage.",
    }


def most_common(values: list[str]) -> str:
    filtered = [value for value in values if value]
    if not filtered:
        return ""
    return max(set(filtered), key=filtered.count)


def render_markdown(profile: dict[str, Any]) -> str:
    pacing = (profile.get("editing_dna") or {}).get("pacing") or {}
    lines = [
        f"# 视频风格 DNA：{profile.get('blogger_name') or profile.get('style_id')}",
        "",
        f"- style_id: `{profile.get('style_id')}`",
        f"- 分析方式: `{profile.get('analysis_provider')}`",
        f"- 样本数: {profile.get('source_count')}",
        f"- 平均关键帧/分钟: {pacing.get('avg_keyframes_per_minute')}",
        "",
        "## 本地读片产物",
        "",
    ]
    for item in profile.get("source_videos") or []:
        lines.append(f"- `{item.get('filename')}`：manifest `{item.get('llm_manifest')}`，grids `{item.get('grids_dir')}`")
    lines.extend(
        [
            "",
            "## 后续处理",
            "",
            "- 读取 `MANIFEST.txt` 和 `grids/*.jpg`，继续抽取构图、转场、证据画面与节奏 DNA。",
            "- 不上传参考视频，不复制创作者素材到生产成片。",
        ]
    )
    return "\n".join(lines) + "\n"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Learn blogger video style locally via claude-real-video.")
    parser.add_argument("--video-dir", required=True, help="包含目标博主视频的目录")
    parser.add_argument("--style-id", required=True, help="风格唯一标识")
    parser.add_argument("--blogger-name", default="", help="博主名称")
    parser.add_argument("--blogger-platform", default="", help="平台，如 bilibili/抖音/视频号")
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR, help="输出根目录")
    parser.add_argument("--max-frames", type=int, default=150)
    parser.add_argument("--fps-floor", type=float, default=1.0)
    parser.add_argument("--scene", type=float, default=0.30)
    parser.add_argument("--dedup-threshold", type=float, default=8.0)
    parser.add_argument("--report", action="store_true")
    parser.add_argument("--transcribe", action="store_true")
    parser.add_argument("--skip-aggregate", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    video_dir = Path(args.video_dir).expanduser().resolve()
    if not video_dir.is_dir():
        raise LocalStyleLearnError(f"视频目录不存在: {video_dir}")
    videos = discover_videos(video_dir)
    if not videos:
        raise LocalStyleLearnError(f"目录下未找到视频文件: {video_dir}")

    run_dir = ensure_dir(Path(args.output_dir).expanduser().resolve() / args.style_id)
    analyses = [analyze_video(video, run_dir, args) for video in videos]
    profile_path = None
    md_path = None
    if not args.skip_aggregate:
        profile = aggregate_profile(args, analyses)
        profile_path = run_dir / "style_profile.json"
        md_path = run_dir / "style_profile.md"
        write_json(profile_path, profile)
        md_path.write_text(render_markdown(profile), encoding="utf-8")

    manifest = {
        "schema_version": "dasheng.video_style_training_manifest.v1",
        "stage": "video-style-training",
        "status": "completed_per_video_only" if args.skip_aggregate else "completed",
        "style_id": args.style_id,
        "blogger_name": args.blogger_name,
        "blogger_platform": args.blogger_platform,
        "analysis_provider": "claude-real-video-local",
        "source_video_dir": str(video_dir),
        "source_count": len(videos),
        "source_videos": [str(path) for path in videos],
        "output_dir": str(run_dir),
        "per_video_dir": str(run_dir / "per_video"),
        "crv_dir": str(run_dir / "crv"),
        "skip_aggregate": bool(args.skip_aggregate),
        "artifacts": {
            "style_profile_json": str(profile_path) if profile_path else None,
            "style_profile_md": str(md_path) if md_path else None,
            "per_video_analysis": [str(run_dir / "per_video" / video.stem / "analysis.json") for video in videos],
            "crv_manifests": [
                str((a.get("local_reading") or {}).get("manifest") or "")
                for a in analyses
            ],
        },
        "quality_rules": {
            "no_generated_media_in_repo": True,
            "source_videos_referenced_not_copied": True,
            "no_model_video_upload": True,
        },
        "generated_at": now_iso(),
    }
    manifest_path = run_dir / "training_manifest.json"
    write_json(manifest_path, manifest)
    print(json.dumps({"status": "ok", "output_dir": str(run_dir), "manifest": str(manifest_path)}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
