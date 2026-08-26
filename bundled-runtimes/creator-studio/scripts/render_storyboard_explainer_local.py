#!/usr/bin/env python3
from __future__ import annotations

import argparse
import html
import json
import math
import re
import shutil
import subprocess
import textwrap
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from bs4 import BeautifulSoup
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont


WIDTH = 1080
HEIGHT = 1920
FPS = 30
REMOVED_STATIC_RENDERER_MESSAGE = (
    "The local static storyboard preview renderer has been removed from production. "
    "Use scripts/render_html_anything_scene_pack_animated.py for live HTML animation recording."
)
BG = (9, 14, 25)
PANEL = (18, 28, 46)
PANEL_2 = (23, 37, 61)
RED = (218, 57, 57)
BLUE = (65, 132, 232)
GOLD = (229, 178, 82)
TEXT = (235, 240, 248)
MUTED = (143, 158, 180)


@dataclass
class AudioClip:
    path: Path
    duration: float


def run(cmd: list[str], *, capture: bool = False) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
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
            "default=nk=1:nw=1",
            str(path),
        ],
        capture=True,
    )
    return float(result.stdout.strip())


def load_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    candidates = [
        "/System/Library/Fonts/STHeiti Medium.ttc" if bold else "/System/Library/Fonts/STHeiti Light.ttc",
        "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
        "/System/Library/Fonts/Supplemental/Songti.ttc",
    ]
    for candidate in candidates:
        if Path(candidate).exists():
            return ImageFont.truetype(candidate, size=size)
    return ImageFont.load_default()


FONT_TITLE = load_font(58, bold=True)
FONT_SUBTITLE = load_font(38, bold=True)
FONT_BODY = load_font(32)
FONT_SMALL = load_font(24)
FONT_NUM = load_font(44, bold=True)


def clean_text(text: str) -> str:
    text = html.unescape(text)
    text = text.replace("。。", "。").replace("，。", "。")
    text = re.sub(r"\s+", " ", text)
    text = text.replace("——", "，")
    return text.strip(" 。")


def wrap_zh(text: str, width: int) -> list[str]:
    text = clean_text(text)
    lines: list[str] = []
    for para in re.split(r"[。；;]", text):
        para = para.strip()
        if not para:
            continue
        lines.extend(textwrap.wrap(para, width=width, break_long_words=True, replace_whitespace=False))
    return lines


def extract_tables(article_html: Path) -> list[list[list[str]]]:
    soup = BeautifulSoup(article_html.read_text(encoding="utf-8", errors="ignore"), "html.parser")
    tables: list[list[list[str]]] = []
    for table in soup.find_all("table"):
        rows = []
        for tr in table.find_all("tr"):
            cells = [clean_text(cell.get_text(" ", strip=True)) for cell in tr.find_all(["th", "td"])]
            if cells:
                rows.append(cells)
        if rows:
            tables.append(rows)
    return tables


def draw_rounded(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int], fill: tuple[int, int, int], outline=None, radius: int = 28) -> None:
    draw.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=2 if outline else 1)


def draw_text_lines(
    draw: ImageDraw.ImageDraw,
    xy: tuple[int, int],
    lines: list[str],
    font: ImageFont.FreeTypeFont,
    fill: tuple[int, int, int] = TEXT,
    line_gap: int = 14,
    max_lines: int | None = None,
) -> int:
    x, y = xy
    selected = lines[:max_lines] if max_lines else lines
    for line in selected:
        draw.text((x, y), line, font=font, fill=fill)
        y += font.size + line_gap
    return y


def draw_background(draw: ImageDraw.ImageDraw, scene_index: int, total: int) -> None:
    draw.rectangle((0, 0, WIDTH, HEIGHT), fill=BG)
    for i in range(12):
        x = -260 + i * 130 + scene_index * 7
        color = BLUE if i % 2 else RED
        rgba = tuple(max(0, min(255, c // 5)) for c in color)
        draw.line((x, 0, x + 520, HEIGHT), fill=rgba, width=2)
    progress_w = int((WIDTH - 96) * (scene_index / max(1, total)))
    draw.rectangle((48, 48, WIDTH - 48, 56), fill=(39, 52, 78))
    draw.rectangle((48, 48, 48 + progress_w, 56), fill=GOLD)
    draw.text((48, 78), "MARKET DOSSIER", font=FONT_SMALL, fill=MUTED)
    draw.text((WIDTH - 178, 78), f"{scene_index:02d}/{total:02d}", font=FONT_SMALL, fill=MUTED)


def draw_table_card(draw: ImageDraw.ImageDraw, table: list[list[str]], box: tuple[int, int, int, int]) -> None:
    x1, y1, x2, y2 = box
    draw_rounded(draw, box, PANEL_2, outline=(55, 75, 112), radius=24)
    draw.text((x1 + 28, y1 + 24), "关键数据", font=FONT_SUBTITLE, fill=GOLD)
    y = y1 + 92
    rows = table[:5]
    for idx, row in enumerate(rows):
        row_bg = (28, 44, 72) if idx % 2 else (21, 34, 56)
        draw.rounded_rectangle((x1 + 24, y, x2 - 24, y + 92), radius=16, fill=row_bg)
        label = row[0] if row else ""
        value = row[1] if len(row) > 1 else ""
        note = row[2] if len(row) > 2 else ""
        draw.text((x1 + 48, y + 16), label[:13], font=FONT_SMALL, fill=TEXT)
        draw.text((x2 - 330, y + 12), value[:12], font=FONT_NUM, fill=RED if "-" in value else BLUE)
        if note:
            draw.text((x1 + 48, y + 54), note[:28], font=FONT_SMALL, fill=MUTED)
        y += 104


def draw_bar_visual(draw: ImageDraw.ImageDraw, table: list[list[str]], box: tuple[int, int, int, int]) -> None:
    x1, y1, x2, y2 = box
    rows = table[:4]
    y = y1
    for idx, row in enumerate(rows):
        label = row[0][:11] if row else ""
        value = row[1] if len(row) > 1 else ""
        raw = re.search(r"-?\d+(?:\.\d+)?", value.replace(",", ""))
        number = abs(float(raw.group(0))) if raw else (idx + 2) * 7
        bar_w = int(min(x2 - x1 - 220, max(80, number / 12 * (x2 - x1 - 240))))
        color = RED if "-" in value else BLUE
        draw.text((x1, y), label, font=FONT_SMALL, fill=MUTED)
        draw.rounded_rectangle((x1, y + 40, x1 + bar_w, y + 74), radius=10, fill=color)
        draw.text((x1 + bar_w + 16, y + 32), value[:16], font=FONT_SMALL, fill=TEXT)
        y += 104


def render_scene_image(
    scene: dict[str, Any],
    index: int,
    total: int,
    table: list[list[str]] | None,
    output: Path,
) -> None:
    img = Image.new("RGB", (WIDTH, HEIGHT), BG)
    draw = ImageDraw.Draw(img)
    draw_background(draw, index, total)

    scene_type = scene.get("type")
    title = clean_text(str(scene.get("title") or ""))
    narration = clean_text(str(scene.get("narration") or ""))

    if scene_type == "hook":
        draw.text((64, 260), "非农之夜", font=FONT_SUBTITLE, fill=GOLD)
        draw_text_lines(draw, (64, 350), wrap_zh(title, 11), FONT_TITLE, fill=TEXT, line_gap=18, max_lines=4)
        draw.rectangle((64, 720, WIDTH - 64, 728), fill=RED)
        draw.text((64, 780), "三把刀同时落下：就业、利率、流动性", font=FONT_BODY, fill=MUTED)
    elif scene_type == "outro":
        draw.text((64, 350), "结论", font=FONT_SUBTITLE, fill=GOLD)
        draw_text_lines(draw, (64, 450), wrap_zh(narration, 14), FONT_TITLE, fill=TEXT, line_gap=20, max_lines=5)
        draw.text((64, 1420), "数据驱动，谨慎判断", font=FONT_BODY, fill=MUTED)
    else:
        draw.text((64, 150), f"第 {index - 1:02d} 章", font=FONT_SMALL, fill=GOLD)
        draw_text_lines(draw, (64, 205), wrap_zh(title, 13), FONT_SUBTITLE, fill=TEXT, line_gap=12, max_lines=3)
        draw_rounded(draw, (56, 390, WIDTH - 56, 770), PANEL, outline=(44, 66, 104), radius=28)
        lines = wrap_zh(narration, 26)
        draw_text_lines(draw, (92, 430), lines, FONT_BODY, fill=TEXT, line_gap=13, max_lines=7)
        if table:
            draw_table_card(draw, table, (56, 820, WIDTH - 56, 1385))
            draw_bar_visual(draw, table, (86, 1428, WIDTH - 86, 1820))
        else:
            draw_rounded(draw, (56, 840, WIDTH - 56, 1390), PANEL_2, outline=(55, 75, 112), radius=28)
            draw.text((92, 884), "逻辑链路", font=FONT_SUBTITLE, fill=GOLD)
            bullets = [
                "信号出现：价格剧烈波动",
                "原因拆解：就业、利率与流动性",
                "传导路径：美股到A股、港股和商品",
                "结论：少追涨，多看资金约束",
            ]
            y = 960
            for bullet in bullets:
                draw.ellipse((92, y + 9, 110, y + 27), fill=BLUE)
                draw.text((128, y), bullet, font=FONT_BODY, fill=TEXT)
                y += 82

    caption = wrap_zh(narration, 20)
    draw_rounded(draw, (54, 1628, WIDTH - 54, 1838), (7, 10, 18), outline=(40, 50, 70), radius=22)
    draw_text_lines(draw, (86, 1662), caption, FONT_BODY, fill=TEXT, line_gap=10, max_lines=4)
    img = img.filter(ImageFilter.UnsharpMask(radius=1.2, percent=110, threshold=3))
    enhancer = ImageEnhance.Contrast(img)
    img = enhancer.enhance(1.04)
    output.parent.mkdir(parents=True, exist_ok=True)
    img.save(output, quality=94)


def synthesize_audio(text: str, output: Path, voice: str, rate: int) -> AudioClip:
    output.parent.mkdir(parents=True, exist_ok=True)
    aiff = output.with_suffix(".aiff")
    run(["say", "-v", voice, "-r", str(rate), "-o", str(aiff), text])
    run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-i",
            str(aiff),
            "-ac",
            "1",
            "-ar",
            "44100",
            str(output),
        ]
    )
    aiff.unlink(missing_ok=True)
    return AudioClip(path=output, duration=ffprobe_duration(output))


def render_scene_video(image: Path, audio: Path, duration: float, output: Path) -> None:
    raise RuntimeError(REMOVED_STATIC_RENDERER_MESSAGE)


def format_srt_time(seconds: float) -> str:
    ms = int(round((seconds - math.floor(seconds)) * 1000))
    total = int(math.floor(seconds))
    if ms == 1000:
        total += 1
        ms = 0
    return f"{total // 3600:02d}:{(total % 3600) // 60:02d}:{total % 60:02d},{ms:03d}"


def write_srt(path: Path, scenes: list[dict[str, Any]], durations: list[float]) -> None:
    rows = []
    cursor = 0.0
    for idx, (scene, duration) in enumerate(zip(scenes, durations), 1):
        start = cursor
        end = cursor + duration
        cursor = end
        text = clean_text(str(scene.get("narration") or scene.get("title") or ""))
        rows.extend([str(idx), f"{format_srt_time(start)} --> {format_srt_time(end)}", text, ""])
    path.write_text("\n".join(rows), encoding="utf-8")


def concat_videos(videos: list[Path], output: Path) -> None:
    concat_file = output.parent / "concat.ffconcat"
    lines = ["ffconcat version 1.0"]
    for video in videos:
        escaped = str(video.resolve()).replace("'", "'\\''")
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
            "-c",
            "copy",
            str(output),
        ]
    )


def normalize_final_video(source: Path, output: Path) -> None:
    run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-i",
            str(source),
            "-c:v",
            "copy",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-af",
            "highpass=f=80,afftdn=nf=-25,dynaudnorm=f=150:g=15:p=0.95,loudnorm=I=-16:LRA=8:TP=-1.0,alimiter=limit=0.95",
            "-movflags",
            "+faststart",
            str(output),
        ]
    )


def write_manifest(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Render a vertical Newma explainer video from storyboard using local tools.")
    parser.add_argument("--storyboard", required=True)
    parser.add_argument("--article-html", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--voice", default="Tingting")
    parser.add_argument("--rate", type=int, default=215)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    raise SystemExit(REMOVED_STATIC_RENDERER_MESSAGE)
    if not shutil.which("say"):
        raise SystemExit("macOS say is required for local preview narration")
    if not shutil.which("ffmpeg"):
        raise SystemExit("ffmpeg is required")

    storyboard_path = Path(args.storyboard).expanduser().resolve()
    article_html = Path(args.article_html).expanduser().resolve()
    out_dir = Path(args.output_dir).expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    frames_dir = out_dir / "frames"
    audio_dir = out_dir / "audio"
    scenes_dir = out_dir / "scenes"

    storyboard = json.loads(storyboard_path.read_text(encoding="utf-8"))
    scenes = storyboard.get("scenes") or []
    tables = extract_tables(article_html)
    section_table_cursor = 0
    table_scene_cursor = 0
    videos: list[Path] = []
    durations: list[float] = []
    scene_reports: list[dict[str, Any]] = []

    for idx, scene in enumerate(scenes, 1):
        table = None
        if scene.get("type") == "table" and tables:
            table = tables[table_scene_cursor % len(tables)]
            table_scene_cursor += 1
        elif scene.get("type") == "section" and tables and idx <= 9:
            table = tables[section_table_cursor % len(tables)]
            section_table_cursor += 1

        frame = frames_dir / f"scene_{idx:03d}.jpg"
        wav = audio_dir / f"scene_{idx:03d}.wav"
        mp4 = scenes_dir / f"scene_{idx:03d}.mp4"
        render_scene_image(scene, idx, len(scenes), table, frame)
        clip = synthesize_audio(clean_text(str(scene.get("narration") or scene.get("title"))), wav, args.voice, args.rate)
        duration = max(clip.duration + 0.25, float(scene.get("duration_sec") or 5.0))
        render_scene_video(frame, wav, duration, mp4)
        videos.append(mp4)
        durations.append(duration)
        scene_reports.append(
            {
                "id": scene.get("id"),
                "title": scene.get("title"),
                "duration_sec": round(duration, 3),
                "table_used": table is not None,
                "frame": str(frame),
                "audio": str(wav),
                "video": str(mp4),
            }
        )

    final_raw = out_dir / f"{storyboard.get('title', 'explainer')}_巫师财经风格_竖版.raw.mp4"
    final_video = out_dir / f"{storyboard.get('title', 'explainer')}_巫师财经风格_竖版.mp4"
    concat_videos(videos, final_raw)
    normalize_final_video(final_raw, final_video)
    srt = out_dir / f"{storyboard.get('title', 'explainer')}_字幕.srt"
    write_srt(srt, scenes, durations)
    manifest = {
        "status": "rendered",
        "renderer": "dasheng_local_explainer",
        "style": "wushi_finance_like_vertical_documentary_preview",
        "source_article": str(article_html),
        "storyboard": str(storyboard_path),
        "final_video": str(final_video),
        "raw_video": str(final_raw),
        "subtitle_srt": str(srt),
        "duration_sec": round(sum(durations), 3),
        "scene_count": len(scenes),
        "table_count": len(tables),
        "scenes": scene_reports,
        "note": "Local preview narration uses macOS say. Replace with Coze/MiniMax for production voice.",
    }
    write_manifest(out_dir / "video_manifest.json", manifest)
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
