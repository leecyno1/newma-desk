#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = PROJECT_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from render_html_anything_scene_pack_video import DEFAULT_MMX_MODEL  # noqa: E402
from render_html_anything_scene_pack_video import DEFAULT_MMX_SPEED  # noqa: E402
from render_html_anything_scene_pack_video import DEFAULT_MMX_VOICE  # noqa: E402
from render_html_anything_scene_pack_video import build_qc_report  # noqa: E402
from render_html_anything_scene_pack_video import synthesize_audio  # noqa: E402
from video_audio_timing import capped_scene_duration  # noqa: E402
from video_audio_timing import semantic_tail_allowance  # noqa: E402
from video_tts_pronunciation import normalize_tts_text  # noqa: E402

WIDTH = 1080
HEIGHT = 1920
FPS = 30

MOTION_INJECTION_CSS = """
html, body { background: #07090d !important; }
.frame::before {
  content: "";
  position: absolute;
  inset: -20%;
  pointer-events: none;
  background:
    radial-gradient(circle at 24% 18%, rgba(216,170,85,.10), transparent 24%),
    linear-gradient(115deg, transparent 0%, rgba(255,255,255,.055) 48%, transparent 58%);
  mix-blend-mode: screen;
  animation: dashengAmbientSweep 8s ease-in-out infinite;
}
.motion-accent { animation: dashengPulseOrbit 5.2s ease-in-out infinite !important; }
.blob { animation-name: dashengBlobDrift !important; animation-duration: 8s !important; }
.bar rect, rect.bar { transform-box: fill-box; transform-origin: left center; animation: dashengBarGrow 1.25s cubic-bezier(.2,.8,.2,1) both; }
.lines path, path.line, path.curve {
  stroke-dasharray: 18 10;
  animation: dashengLineMarch 2.8s linear infinite;
}
tr, li, .card, .paper, .note, .metric, .stat, .tile {
  will-change: transform, opacity;
}
@keyframes dashengAmbientSweep {
  0%,100% { transform: translate3d(-3%, -2%, 0) rotate(-2deg); opacity: .42; }
  50% { transform: translate3d(4%, 3%, 0) rotate(2deg); opacity: .72; }
}
@keyframes dashengPulseOrbit {
  0%,100% { transform: translate3d(0,0,0) scale(1); filter: brightness(1); }
  50% { transform: translate3d(-10px,12px,0) scale(1.045); filter: brightness(1.22); }
}
@keyframes dashengBlobDrift {
  0%,100% { transform: translate3d(0,0,0) scale(1); }
  50% { transform: translate3d(28px,-18px,0) scale(1.045); }
}
@keyframes dashengBarGrow {
  from { transform: scaleX(.04); opacity: .35; }
  to { transform: scaleX(1); opacity: 1; }
}
@keyframes dashengLineMarch {
  to { stroke-dashoffset: -56; }
}
"""

RESTART_MOTION_JS = """
() => {
  document.body.style.opacity = '1';
  const animations = document.getAnimations({subtree: true});
  for (const animation of animations) {
    try {
      animation.cancel();
      animation.play();
    } catch (error) {}
  }
  if (window.gsap && window.gsap.globalTimeline) {
    try {
      window.gsap.globalTimeline.clear(false);
      if (typeof window.initScene === 'function') window.initScene();
      window.gsap.globalTimeline.restart(true, false);
    } catch (error) {
      try { window.gsap.globalTimeline.restart(true, false); } catch (innerError) {}
    }
  } else if (typeof window.initScene === 'function') {
    try { window.initScene(); } catch (error) {}
  }
  if (window.lottie && typeof window.lottie.getRegisteredAnimations === 'function') {
    try {
      for (const item of window.lottie.getRegisteredAnimations()) {
        item.goToAndPlay(0, true);
      }
    } catch (error) {}
  }
  window.dispatchEvent(new Event('dasheng-render-start'));
}
"""


class AnimatedRenderError(RuntimeError):
    pass


def run(cmd: list[str]) -> None:
    proc = subprocess.run(cmd, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    if proc.returncode != 0:
        raise AnimatedRenderError(proc.stderr or proc.stdout or "command failed")


def run_capture(cmd: list[str]) -> str:
    proc = subprocess.run(cmd, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    if proc.returncode != 0:
        raise AnimatedRenderError(proc.stderr or proc.stdout or "command failed")
    return proc.stdout.strip()


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def ffprobe_duration(path: Path) -> float:
    out = run_capture(
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
    return float(out)


def trailing_silence_duration(path: Path, *, threshold_db: int = -42, minimum_sec: float = 0.20) -> float:
    total = ffprobe_duration(path)
    proc = subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-nostats",
            "-i",
            str(path),
            "-af",
            f"silencedetect=noise={threshold_db}dB:d={minimum_sec:g}",
            "-f",
            "null",
            "-",
        ],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    matches = re.findall(r"silence_end:\s*([0-9.]+)\s*\|\s*silence_duration:\s*([0-9.]+)", proc.stderr)
    if not matches:
        return 0.0
    end, duration = map(float, matches[-1])
    return duration if end >= total - 0.08 else 0.0


def find_chrome() -> str | None:
    candidates = [
        os.environ.get("CHROME_EXECUTABLE"),
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "/Applications/Chromium.app/Contents/MacOS/Chromium",
        shutil.which("google-chrome"),
        shutil.which("chromium"),
        shutil.which("chromium-browser"),
    ]
    for item in candidates:
        if item and Path(item).exists():
            return str(item)
    return None


def file_url(path: Path) -> str:
    return path.expanduser().resolve().as_uri()


def scene_audio_plan(
    scenes: list[dict[str, Any]],
    *,
    voice_dir: Path | None,
    reuse_render_report: Path | None,
) -> list[dict[str, Any]]:
    report_by_id: dict[str, dict[str, Any]] = {}
    if reuse_render_report and reuse_render_report.exists():
        report = load_json(reuse_render_report)
        for item in (report.get("voiceover") or {}).get("scenes") or []:
            if item.get("id"):
                report_by_id[str(item["id"])] = item

    plan: list[dict[str, Any]] = []
    for idx, scene in enumerate(scenes, 1):
        report_item = report_by_id.get(str(scene.get("id") or ""))
        audio_path: Path | None = None
        duration = float(scene.get("duration_sec") or 4)
        if report_item:
            duration = float(report_item.get("duration_sec") or duration)
            if report_item.get("audio"):
                audio_path = Path(str(report_item["audio"])).expanduser().resolve()
        if voice_dir:
            candidate = voice_dir / f"{idx:03d}.wav"
            if candidate.exists():
                audio_path = candidate.resolve()
        if audio_path and audio_path.exists() and not report_item:
            source_duration = ffprobe_duration(audio_path)
            trailing_silence = trailing_silence_duration(audio_path)
            duration = max(
                capped_scene_duration(
                    scene,
                    audio_duration=source_duration,
                    trailing_silence=trailing_silence,
                ),
                1.2,
            )
        else:
            source_duration = None
            trailing_silence = None
        plan.append(
            {
                "index": idx,
                "scene_id": scene.get("id") or f"scene_{idx:03d}",
                "duration_sec": round(max(0.6, duration), 3),
                "audio": str(audio_path) if audio_path and audio_path.exists() else None,
                "source_audio_duration_sec": round(source_duration, 3) if source_duration is not None else None,
                "trailing_silence_sec": round(trailing_silence, 3) if trailing_silence is not None else None,
            }
        )
    return plan


def convert_recording_to_mp4(webm: Path, output: Path, *, trim_start: float, duration: float, fps: int) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-ss",
            f"{max(0.0, trim_start):.3f}",
            "-i",
            str(webm),
            "-t",
            f"{duration:.3f}",
            "-vf",
            f"fps={fps},scale={WIDTH}:{HEIGHT}:flags=lanczos,format=yuv420p",
            "-an",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "19",
            "-movflags",
            "+faststart",
            str(output),
        ]
    )


def record_scene(
    browser: Any,
    scene: dict[str, Any],
    output: Path,
    raw_dir: Path,
    *,
    duration: float,
    fps: int,
    inject_motion_css: bool,
) -> dict[str, Any]:
    raw_dir.mkdir(parents=True, exist_ok=True)
    context = browser.new_context(
        viewport={"width": WIDTH, "height": HEIGHT},
        record_video_dir=str(raw_dir),
        record_video_size={"width": WIDTH, "height": HEIGHT},
        device_scale_factor=1,
        reduced_motion="no-preference",
    )
    page = context.new_page()
    video = page.video
    started = time.monotonic()
    html_path = Path(str(scene["html"])).expanduser().resolve()
    try:
        page.goto(file_url(html_path), wait_until="load", timeout=45_000)
    except PlaywrightTimeoutError:
        page.goto(file_url(html_path), wait_until="domcontentloaded", timeout=45_000)
    if inject_motion_css:
        page.add_style_tag(content=MOTION_INJECTION_CSS)
    page.evaluate(RESTART_MOTION_JS)
    restart_at = time.monotonic()
    page.wait_for_timeout(int((duration + 0.45) * 1000))
    page.close()
    context.close()
    if video is None:
        raise AnimatedRenderError(f"Playwright did not produce a video for {html_path}")
    webm = Path(video.path()).resolve()
    # Browser recordings can contain one pre-style paint frame. Skip it so
    # concatenation never flashes a flat white/black frame between scenes.
    trim_start = max(0.0, restart_at - started + 0.08)
    convert_recording_to_mp4(webm, output, trim_start=trim_start, duration=duration, fps=fps)
    return {
        "html": str(html_path),
        "raw_recording": str(webm),
        "trim_start_sec": round(trim_start, 3),
        "duration_sec": round(duration, 3),
        "video": str(output.resolve()),
    }


def make_video_concat_file(videos: list[Path], output: Path) -> None:
    lines = ["ffconcat version 1.0"]
    for video in videos:
        escaped = str(video.resolve()).replace("'", "'\\''")
        lines.append(f"file '{escaped}'")
    output.write_text("\n".join(lines) + "\n", encoding="utf-8")


def concat_videos(videos: list[Path], output: Path) -> None:
    concat_file = output.parent / "video_concat.ffconcat"
    make_video_concat_file(videos, concat_file)
    run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-safe",
            "0",
            "-f",
            "concat",
            "-i",
            str(concat_file),
            "-c",
            "copy",
            str(output),
        ]
    )


def align_video_duration(video: Path, duration: float) -> None:
    actual = ffprobe_duration(video)
    drift = duration - actual
    if abs(drift) <= 0.04:
        return
    aligned = video.with_name(f"{video.stem}.duration_aligned{video.suffix}")
    vf = f"tpad=stop_mode=clone:stop_duration={max(0.0, drift + 0.06):.3f}"
    run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-i",
            str(video),
            "-vf",
            vf,
            "-t",
            f"{duration:.3f}",
            "-c:v",
            "libx264",
            "-preset",
            "medium",
            "-crf",
            "18",
            "-an",
            str(aligned),
        ]
    )
    aligned.replace(video)


def pad_audio_to_duration(source: Path, output: Path, duration: float) -> None:
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
            "-af",
            "apad",
            "-t",
            f"{duration:.3f}",
            "-ac",
            "1",
            "-ar",
            "44100",
            str(output),
        ]
    )


def concat_audio(files: list[Path], output: Path) -> None:
    concat_file = output.parent / "audio_concat.ffconcat"
    lines = ["ffconcat version 1.0"]
    for audio in files:
        escaped = str(audio.resolve()).replace("'", "'\\''")
        lines.append(f"file '{escaped}'")
    concat_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
    run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-safe",
            "0",
            "-f",
            "concat",
            "-i",
            str(concat_file),
            "-c:a",
            "pcm_s16le",
            str(output),
        ]
    )


def mux_video_audio(video: Path, audio: Path, output: Path) -> None:
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
            str(audio),
            "-map",
            "0:v:0",
            "-map",
            "1:a:0",
            "-c:v",
            "copy",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-shortest",
            "-movflags",
            "+faststart",
            str(output),
        ]
    )


def bgm_volume_filter(
    chapter_windows: list[tuple[float, float]] | None = None,
    recap_windows: list[tuple[float, float]] | None = None,
) -> str:
    def active(windows: list[tuple[float, float]]) -> str:
        return "+".join(f"between(t,{start:.3f},{end:.3f})" for start, end in windows) or "0"

    chapter_expr = active(chapter_windows or [])
    recap_expr = active(recap_windows or [])
    return f"volume='if(gt({chapter_expr},0),0.120,if(gt({recap_expr},0),0.105,0.075))'"


def mix_bgm(
    voice: Path,
    bgm: Path,
    output: Path,
    *,
    duration: float,
    chapter_windows: list[tuple[float, float]] | None = None,
    recap_windows: list[tuple[float, float]] | None = None,
) -> None:
    run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-i",
            str(voice),
            "-stream_loop",
            "-1",
            "-i",
            str(bgm),
            "-filter_complex",
            (
                f"[1:a]{bgm_volume_filter(chapter_windows, recap_windows)},atrim=0:{duration:.3f},asetpts=N/SR/TB[bgm];"
                "[0:a]volume=1.0[voice];"
                "[voice][bgm]amix=inputs=2:duration=first:dropout_transition=2,"
                "loudnorm=I=-16:LRA=8:TP=-1.0[mix]"
            ),
            "-map",
            "[mix]",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            str(output),
        ]
    )


def extract_mid_still(video: Path, output: Path, *, duration: float) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-ss",
            f"{max(0.1, duration * 0.52):.3f}",
            "-i",
            str(video),
            "-frames:v",
            "1",
            str(output),
        ]
    )


def make_contact_sheet(scenes: list[dict[str, Any]], still_dir: Path, output: Path, cols: int = 4) -> None:
    if WIDTH > HEIGHT:
        thumb_w, thumb_h, label_h = 384, 216, 64
        cols = 4
    else:
        thumb_w, thumb_h, label_h = 270, 480, 72
    rows = (len(scenes) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * thumb_w, rows * (thumb_h + label_h)), (13, 17, 24))
    draw = ImageDraw.Draw(sheet)
    try:
        font = ImageFont.truetype("/System/Library/Fonts/STHeiti Medium.ttc", 18)
        small = ImageFont.truetype("/System/Library/Fonts/STHeiti Light.ttc", 14)
    except Exception:
        font = ImageFont.load_default()
        small = ImageFont.load_default()
    for idx, scene in enumerate(scenes, 1):
        still = still_dir / f"{idx:03d}.jpg"
        if not still.exists():
            continue
        x = ((idx - 1) % cols) * thumb_w
        y = ((idx - 1) // cols) * (thumb_h + label_h)
        thumb = Image.open(still).convert("RGB").resize((thumb_w, thumb_h))
        sheet.paste(thumb, (x, y))
        draw.rectangle((x, y + thumb_h, x + thumb_w, y + thumb_h + label_h), fill=(23, 29, 40))
        draw.text((x + 10, y + thumb_h + 8), f"{idx:02d} {scene.get('content_part')}", fill=(245, 242, 233), font=font)
        draw.text((x + 10, y + thumb_h + 36), str(scene.get("template_id")), fill=(216, 170, 85), font=small)
    output.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(output, quality=92)


def wrap_text(text: str, font: ImageFont.FreeTypeFont, max_width: int) -> list[str]:
    clean = re.sub(r"\s+", " ", text).strip()
    lines: list[str] = []
    current = ""
    for char in clean:
        candidate = current + char
        if font.getlength(candidate) <= max_width or not current:
            current = candidate
        else:
            lines.append(current)
            current = char
    if current:
        lines.append(current)
    return lines[:2]


def load_captions(path: Path) -> list[dict[str, Any]]:
    data = load_json(path)
    return data.get("captions") or data.get("cues") or []


def burn_subtitles(video: Path, captions_json: Path, output: Path) -> None:
    captions = load_captions(captions_json)
    cap = cv2.VideoCapture(str(video))
    if not cap.isOpened():
        raise AnimatedRenderError(f"Cannot open video for subtitles: {video}")
    fps = cap.get(cv2.CAP_PROP_FPS) or FPS
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or WIDTH)
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or HEIGHT)
    output.parent.mkdir(parents=True, exist_ok=True)
    writer = cv2.VideoWriter(str(output), cv2.VideoWriter_fourcc(*"mp4v"), fps, (width, height))
    font_size = 48 if width > height else 42
    try:
        font = ImageFont.truetype("/System/Library/Fonts/STHeiti Medium.ttc", font_size)
    except Exception:
        font = ImageFont.load_default()
    caption_idx = 0
    frame_idx = 0
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        t = frame_idx / fps
        while caption_idx + 1 < len(captions) and float(captions[caption_idx].get("end", 0)) < t:
            caption_idx += 1
        active = captions[caption_idx] if caption_idx < len(captions) else None
        if active and float(active.get("start", 0)) <= t <= float(active.get("end", 0)):
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            image = Image.fromarray(rgb)
            overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
            draw = ImageDraw.Draw(overlay)
            text_width = min(1320, int(width * 0.72))
            lines = wrap_text(str(active.get("text") or ""), font, text_width)
            line_h = font_size + 16
            box_h = 42 + line_h * len(lines)
            box_w = min(width - 160, text_width + 100)
            x = (width - box_w) // 2
            bottom_margin = 90 if width > height else 250
            y = height - bottom_margin - box_h
            draw.rounded_rectangle((x, y, x + box_w, y + box_h), radius=24, fill=(5, 7, 10, 176))
            for i, line in enumerate(lines):
                tw = font.getlength(line)
                tx = int((width - tw) / 2)
                ty = y + 22 + i * line_h
                draw.text((tx, ty), line, font=font, fill=(248, 245, 235, 255), stroke_width=2, stroke_fill=(0, 0, 0, 210))
            image = Image.alpha_composite(image.convert("RGBA"), overlay).convert("RGB")
            frame = cv2.cvtColor(np.array(image), cv2.COLOR_RGB2BGR)
        writer.write(frame)
        frame_idx += 1
    cap.release()
    writer.release()


def render_pack(
    manifest_path: Path,
    output_dir: Path,
    *,
    reuse_render_report: Path | None,
    voice_dir: Path | None,
    bgm: Path | None,
    captions_json: Path | None,
    limit: int | None,
    fps: int,
    skip_subtitles: bool,
    with_voice: bool,
    voice_provider: str,
    voice: str,
    rate: int,
    mmx_model: str,
    mmx_speed: float,
    mmx_language: str,
    inject_motion_css: bool,
    use_bundled_chromium: bool,
) -> dict[str, Any]:
    manifest = load_json(manifest_path)
    global WIDTH, HEIGHT
    WIDTH = int(manifest.get("width") or WIDTH)
    HEIGHT = int(manifest.get("height") or HEIGHT)
    scenes = manifest.get("scenes") or []
    if limit:
        scenes = scenes[:limit]
        manifest = {**manifest, "scenes": scenes, "scene_count": len(scenes)}
    output_dir.mkdir(parents=True, exist_ok=True)
    animated_dir = output_dir / "animated_segments"
    raw_recording_dir = output_dir / "raw_browser_recordings"
    still_dir = output_dir / "animated_mid_stills"
    audio_plan = scene_audio_plan(scenes, voice_dir=voice_dir, reuse_render_report=reuse_render_report)
    if with_voice:
        audio_dir = output_dir / "voice_audio"
        for idx, (scene, plan_item) in enumerate(zip(scenes, audio_plan), 1):
            if plan_item.get("audio"):
                continue
            wav = audio_dir / f"{idx:03d}.wav"
            text = str(scene.get("narration_tts") or "").strip()
            if not text:
                text = normalize_tts_text(str(scene.get("narration") or scene.get("title") or "").strip())
            text = text or "。"
            audio_duration = synthesize_audio(
                text,
                wav,
                provider=voice_provider,
                voice=voice,
                rate=rate,
                mmx_model=mmx_model,
                mmx_speed=mmx_speed,
                mmx_language=mmx_language,
            )
            plan_item["audio"] = str(wav.resolve())
            plan_item["duration_sec"] = round(
                max(
                    audio_duration + semantic_tail_allowance(scene),
                    float(scene.get("minimum_duration_sec") or 0),
                    1.2,
                ),
                3,
            )

    chrome = None if use_bundled_chromium else find_chrome()
    segment_videos: list[Path] = []
    scene_reports: list[dict[str, Any]] = []
    with sync_playwright() as p:
        launch_kwargs = {"headless": True}
        if chrome:
            launch_kwargs["executable_path"] = chrome
        browser = p.chromium.launch(**launch_kwargs)
        try:
            for idx, (scene, plan_item) in enumerate(zip(scenes, audio_plan), 1):
                duration = float(plan_item["duration_sec"])
                segment = animated_dir / f"{idx:03d}.mp4"
                record_report = record_scene(
                    browser,
                    scene,
                    segment,
                    raw_recording_dir / f"{idx:03d}",
                    duration=duration,
                    fps=fps,
                    inject_motion_css=inject_motion_css,
                )
                extract_mid_still(segment, still_dir / f"{idx:03d}.jpg", duration=duration)
                segment_videos.append(segment)
                scene_reports.append(
                    {
                        "id": scene.get("id"),
                        "index": idx,
                        "content_part": scene.get("content_part"),
                        "beat_class": scene.get("beat_class"),
                        "director_state": scene.get("director_state"),
                        "template_id": scene.get("template_id"),
                        "transition_to_next": scene.get("transition_to_next"),
                        "duration_sec": round(duration, 3),
                        "audio": plan_item.get("audio"),
                        **record_report,
                    }
                )
        finally:
            browser.close()

    total_duration = round(sum(float(item["duration_sec"]) for item in scene_reports), 3)
    visual_video = output_dir / "animated_visual_timeline_silent.mp4"
    concat_videos(segment_videos, visual_video)
    align_video_duration(visual_video, total_duration)
    contact_sheet = output_dir / "animated_contact_sheet.jpg"
    make_contact_sheet(scenes, still_dir, contact_sheet)

    voice_result = None
    final_voice_video = None
    audio_files = [Path(str(item["audio"])) for item in scene_reports if item.get("audio")]
    if len(audio_files) == len(scene_reports):
        padded_dir = output_dir / "voice_audio_padded"
        padded_files: list[Path] = []
        for idx, item in enumerate(scene_reports, 1):
            padded = padded_dir / f"{idx:03d}.wav"
            pad_audio_to_duration(Path(str(item["audio"])), padded, float(item["duration_sec"]))
            padded_files.append(padded)
        voiceover = output_dir / "voiceover_scene_concat.wav"
        concat_audio(padded_files, voiceover)
        final_voice_video = output_dir / "animated_talking_video_tts.mp4"
        mux_video_audio(visual_video, voiceover, final_voice_video)
        mixed_audio = voiceover
        if bgm and bgm.exists():
            mixed_audio = output_dir / "mixed_voice_bgm.m4a"
            chapter_windows = [
                (float(scene.get("start_sec") or 0), float(scene.get("end_sec") or 0))
                for scene in scenes
                if scene.get("beat_class") == "chapter"
            ]
            recap_windows = [
                (float(scene.get("start_sec") or 0), float(scene.get("end_sec") or 0))
                for scene in scenes
                if scene.get("beat_class") == "recap"
            ]
            mix_bgm(
                voiceover,
                bgm,
                mixed_audio,
                duration=total_duration,
                chapter_windows=chapter_windows,
                recap_windows=recap_windows,
            )
        video_for_audio = visual_video
        if captions_json and captions_json.exists() and not skip_subtitles:
            subtitled_noaudio = output_dir / "animated_subtitled_video_noaudio.mp4"
            burn_subtitles(visual_video, captions_json, subtitled_noaudio)
            video_for_audio = subtitled_noaudio
        orientation = "horizontal" if WIDTH > HEIGHT else "vertical"
        caption_suffix = "subtitled" if captions_json and captions_json.exists() and not skip_subtitles else "no_subtitles"
        final_delivery = output_dir / f"final_explainer_{orientation}_animated_bgm_{caption_suffix}.mp4"
        mux_video_audio(video_for_audio, mixed_audio, final_delivery)
        voice_result = {
            "mode": "reuse_per_scene_audio",
            "duration_sec": total_duration,
            "voiceover_audio": str(voiceover.resolve()),
            "mixed_audio": str(mixed_audio.resolve()),
            "final_video": str(final_delivery.resolve()),
            "raw_video": str(final_voice_video.resolve()),
            "scenes": scene_reports,
        }

    silent_result = {
        "duration_sec": total_duration,
        "final_video": str(visual_video.resolve()),
        "scenes": scene_reports,
    }
    qc_report = build_qc_report(manifest, output_dir=output_dir, silent_result=silent_result, voice_result=voice_result)
    result = {
        "schema_version": "dasheng.html_anything_scene_pack_animated_render.v1",
        "status": "ok",
        "source_manifest": str(manifest_path.resolve()),
        "render_mode": "live_html_animation_recording",
        "static_screenshot_renderer": "forbidden",
        "generic_motion_injection": "enabled" if inject_motion_css else "disabled",
        "scene_count": len(scenes),
        "fps": fps,
        "duration_sec": total_duration,
        "animated_segments_dir": str(animated_dir.resolve()),
        "raw_recordings_dir": str(raw_recording_dir.resolve()),
        "contact_sheet": str(contact_sheet.resolve()),
        "silent_video": str(visual_video.resolve()),
        "voiceover": voice_result,
        "qc_report": str((output_dir / "video_qc_report.json").resolve()),
        "qc_status": qc_report["status"],
        "scenes": scene_reports,
    }
    (output_dir / "animated_render_report.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Record HTML scene-pack animations as real video, not static screenshots.")
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--reuse-render-report", help="Previous render_report.json with per-scene audio paths and durations.")
    parser.add_argument("--voice-dir", help="Directory containing 001.wav, 002.wav ... for per-scene narration.")
    parser.add_argument("--bgm", help="Optional background music file.")
    parser.add_argument("--captions-json", help="Optional full timed captions JSON for burned subtitles.")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--fps", type=int, default=FPS)
    parser.add_argument("--skip-subtitles", action="store_true")
    parser.add_argument("--with-voice", action="store_true", help="Generate missing per-scene narration audio before rendering.")
    parser.add_argument("--voice-provider", choices=["mmx", "say"], default="mmx")
    parser.add_argument("--voice", default=DEFAULT_MMX_VOICE)
    parser.add_argument("--rate", type=int, default=215)
    parser.add_argument("--mmx-model", default=DEFAULT_MMX_MODEL)
    parser.add_argument("--mmx-speed", type=float, default=DEFAULT_MMX_SPEED)
    parser.add_argument("--mmx-language", default="Chinese")
    parser.add_argument(
        "--disable-motion-injection",
        action="store_true",
        help="Record only the scene-authored motion; do not inject the generic ambient sweep CSS.",
    )
    parser.add_argument(
        "--use-bundled-chromium",
        action="store_true",
        help="Use Playwright's bundled Chromium instead of the system Chrome executable.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    result = render_pack(
        Path(args.manifest).expanduser().resolve(),
        Path(args.output_dir).expanduser().resolve(),
        reuse_render_report=Path(args.reuse_render_report).expanduser().resolve() if args.reuse_render_report else None,
        voice_dir=Path(args.voice_dir).expanduser().resolve() if args.voice_dir else None,
        bgm=Path(args.bgm).expanduser().resolve() if args.bgm else None,
        captions_json=Path(args.captions_json).expanduser().resolve() if args.captions_json else None,
        limit=args.limit,
        fps=args.fps,
        skip_subtitles=args.skip_subtitles,
        with_voice=args.with_voice,
        voice_provider=args.voice_provider,
        voice=args.voice,
        rate=args.rate,
        mmx_model=args.mmx_model,
        mmx_speed=args.mmx_speed,
        mmx_language=args.mmx_language,
        inject_motion_css=not args.disable_motion_injection,
        use_bundled_chromium=args.use_bundled_chromium,
    )
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
