#!/usr/bin/env python3
"""Build a per-scene rough-cut review page and contact sheet."""

from __future__ import annotations

import argparse
import html
import json
import subprocess
from datetime import datetime
from pathlib import Path
from urllib.parse import quote

from PIL import Image, ImageDraw, ImageFont


def file_uri(path: Path) -> str:
    return "file://" + quote(str(path.expanduser().resolve()))


def load_json(path: Path) -> dict:
    return json.loads(path.expanduser().read_text(encoding="utf-8"))


def extract_frame(video: Path, timestamp: float, output: Path) -> None:
    subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-ss",
            f"{timestamp:.3f}",
            "-i",
            str(video),
            "-frames:v",
            "1",
            "-vf",
            "scale=480:-1",
            str(output),
        ],
        check=True,
    )


def font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for candidate in (
        "/System/Library/Fonts/PingFang.ttc",
        "/System/Library/Fonts/STHeiti Medium.ttc",
        "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
    ):
        try:
            return ImageFont.truetype(candidate, size=size)
        except OSError:
            continue
    return ImageFont.load_default()


def build_contact_sheet(items: list[dict], output: Path, columns: int = 4) -> None:
    frame_width, frame_height, label_height = 480, 270, 58
    rows = (len(items) + columns - 1) // columns
    canvas = Image.new("RGB", (frame_width * columns, (frame_height + label_height) * rows), "#f3efe6")
    draw = ImageDraw.Draw(canvas)
    label_font = font(20)
    for index, item in enumerate(items):
        x = (index % columns) * frame_width
        y = (index // columns) * (frame_height + label_height)
        frame = Image.open(item["preview"]).convert("RGB")
        frame.thumbnail((frame_width, frame_height))
        canvas.paste(frame, (x + (frame_width - frame.width) // 2, y + (frame_height - frame.height) // 2))
        label = f"{item['scene_id']}  {item['start_sec']:.1f}s–{item['end_sec']:.1f}s"
        draw.rectangle((x, y + frame_height, x + frame_width, y + frame_height + label_height), fill="#13231f")
        draw.text((x + 16, y + frame_height + 16), label, fill="#f7f3ea", font=label_font)
    output.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(output, quality=90)


def build_review_page(
    *,
    title: str,
    video: Path,
    contact_sheet: Path,
    items: list[dict],
    qc: dict,
    output: Path,
) -> None:
    metrics = qc.get("metrics") or {}
    cards: list[str] = []
    for item in items:
        scene_id = html.escape(item["scene_id"])
        narration = html.escape(item.get("narration") or "")
        scene_title = html.escape(item.get("title") or scene_id)
        cards.append(
            f"""
            <article class="scene" data-scene="{scene_id}">
              <button class="preview" onclick="seekTo({item['start_sec']:.3f})" title="从本镜头开始播放">
                <img loading="lazy" src="{file_uri(Path(item['preview']))}" alt="{scene_title}">
                <span>{scene_id} · {item['start_sec']:.1f}s–{item['end_sec']:.1f}s</span>
              </button>
              <div class="body">
                <h3>{scene_title}</h3>
                <p>{narration}</p>
                <label>审核结果
                  <select class="decision"><option value="pending">待审核</option><option value="approved">通过</option><option value="revise">需修改</option></select>
                </label>
                <label>修改意见<textarea class="note" rows="3" placeholder="填写该镜头需要调整的内容"></textarea></label>
              </div>
            </article>
            """
        )

    qc_status = html.escape(str(qc.get("status") or "unknown"))
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        f"""<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{html.escape(title)} · 粗剪审核</title>
<style>
:root{{--paper:#f3efe6;--ink:#13231f;--red:#ad4b32;--blue:#337695;--teal:#118278;--line:#d9d0c1}}*{{box-sizing:border-box}}body{{margin:0;background:var(--paper);color:var(--ink);font-family:-apple-system,BlinkMacSystemFont,"PingFang SC",sans-serif}}header{{padding:28px 4vw 18px;border-bottom:1px solid var(--line)}}h1{{margin:0;font-size:30px}}header p{{margin:8px 0 0;color:#68716d}}.summary{{display:flex;gap:10px;flex-wrap:wrap;margin-top:16px}}.pill{{background:#fff;border:1px solid var(--line);border-radius:999px;padding:7px 11px;font-size:13px}}.pill.pass{{color:#fff;background:var(--teal);border-color:var(--teal)}}main{{padding:22px 4vw 56px}}.player{{display:grid;grid-template-columns:minmax(0,1.4fr) minmax(320px,.6fr);gap:20px;align-items:start}}video{{width:100%;background:#111;border-radius:16px;box-shadow:0 12px 32px #33261620}}.sheet{{width:100%;border-radius:16px;border:1px solid var(--line)}}.toolbar{{position:sticky;top:0;z-index:4;display:flex;gap:10px;align-items:center;padding:14px 0;background:#f3efe6ee;backdrop-filter:blur(10px)}}button{{font:inherit}}.action{{border:0;border-radius:10px;padding:10px 14px;background:var(--ink);color:#fff;cursor:pointer}}.action.primary{{background:var(--red)}}#saveState{{font-size:13px;color:#61706a}}.global-note{{width:100%;padding:12px;border:1px solid var(--line);border-radius:12px;background:#fff;resize:vertical}}.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(340px,1fr));gap:16px;margin-top:18px}}.scene{{background:#fff;border:1px solid var(--line);border-radius:16px;overflow:hidden}}.preview{{display:block;position:relative;width:100%;padding:0;border:0;background:#111;cursor:pointer}}.preview img{{display:block;width:100%;aspect-ratio:16/9;object-fit:cover}}.preview span{{position:absolute;left:10px;bottom:10px;padding:5px 8px;border-radius:8px;background:#10221edb;color:#fff;font-size:12px}}.body{{padding:15px}}h3{{margin:0 0 8px;font-size:18px}}.body p{{min-height:44px;margin:0 0 13px;color:#5d6763;line-height:1.55;font-size:14px}}label{{display:block;margin-top:10px;font-size:13px;color:#65706c}}select,textarea{{display:block;width:100%;margin-top:5px;border:1px solid var(--line);border-radius:9px;padding:9px;background:#fff;color:var(--ink)}}@media(max-width:900px){{.player{{grid-template-columns:1fr}}}}
</style></head><body><header><h1>{html.escape(title)}</h1><p>逐镜点击缩略图可跳转播放；审核意见可保存到本机并导出 JSON。</p><div class="summary"><span class="pill {qc_status}">QC {qc_status.upper()}</span><span class="pill">时长 {float(metrics.get('duration_sec') or 0):.1f} 秒</span><span class="pill">响度 {float((metrics.get('loudness') or {{}}).get('integrated_lufs') or 0):.2f} LUFS</span><span class="pill">视觉变化 {int(metrics.get('strong_visual_change_count') or 0)} 次</span><span class="pill">黑场 {int(metrics.get('dark_run_count') or 0)}</span></div></header><main><section class="player"><video id="video" controls preload="metadata" src="{file_uri(video)}"></video><a href="{file_uri(contact_sheet)}"><img class="sheet" src="{file_uri(contact_sheet)}" alt="逐镜接触表"></a></section><div class="toolbar"><button class="action primary" onclick="saveReview()">保存审核</button><button class="action" onclick="exportReview()">导出 JSON</button><span id="saveState">尚未保存</span></div><textarea id="globalNote" class="global-note" rows="3" placeholder="整片修改意见"></textarea><section class="grid">{''.join(cards)}</section></main>
<script>
const storageKey='newma-roughcut-review:{quote(str(video))}';
const video=document.getElementById('video');
function seekTo(sec){{video.currentTime=sec;video.play();window.scrollTo({{top:0,behavior:'smooth'}})}}
function collect(){{const scenes={{}};document.querySelectorAll('.scene').forEach(card=>{{scenes[card.dataset.scene]={{decision:card.querySelector('.decision').value,note:card.querySelector('.note').value}}}});return{{schema_version:'newma.video.roughcut_review.v1',video:{json.dumps(str(video), ensure_ascii=False)},saved_at:new Date().toISOString(),global_note:document.getElementById('globalNote').value,scenes}}}}
function apply(data){{if(!data)return;document.getElementById('globalNote').value=data.global_note||'';document.querySelectorAll('.scene').forEach(card=>{{const value=(data.scenes||{{}})[card.dataset.scene]||{{}};card.querySelector('.decision').value=value.decision||'pending';card.querySelector('.note').value=value.note||''}})}}
function saveReview(){{const data=collect();localStorage.setItem(storageKey,JSON.stringify(data));document.getElementById('saveState').textContent='已保存 '+new Date().toLocaleTimeString()}}
function exportReview(){{const blob=new Blob([JSON.stringify(collect(),null,2)],{{type:'application/json'}});const link=document.createElement('a');link.href=URL.createObjectURL(blob);link.download='roughcut_review_decision.json';link.click();URL.revokeObjectURL(link.href)}}
try{{apply(JSON.parse(localStorage.getItem(storageKey)))}}catch(e){{}}
</script></body></html>""",
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a per-scene rough-cut review page.")
    parser.add_argument("--video", required=True)
    parser.add_argument("--scene-plan", required=True)
    parser.add_argument("--qc-report", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--title", default="视频粗剪审核")
    args = parser.parse_args()

    video = Path(args.video).expanduser().resolve()
    plan = load_json(Path(args.scene_plan))
    qc = load_json(Path(args.qc_report))
    output_dir = Path(args.output_dir).expanduser().resolve()
    frames_dir = output_dir / "scene_frames"
    frames_dir.mkdir(parents=True, exist_ok=True)

    items: list[dict] = []
    for index, scene in enumerate(plan.get("scenes") or [], start=1):
        start = float(scene.get("start_sec") or 0)
        end = float(scene.get("end_sec") or start)
        timestamp = start + max(0.1, (end - start) * 0.65)
        preview = frames_dir / f"{index:02d}_{scene.get('id') or f'scene_{index:03d}'}.jpg"
        extract_frame(video, min(timestamp, max(start, end - 0.1)), preview)
        items.append(
            {
                "scene_id": str(scene.get("id") or f"scene_{index:03d}"),
                "title": str(scene.get("title") or ""),
                "narration": str(scene.get("narration") or ""),
                "start_sec": start,
                "end_sec": end,
                "preview": str(preview),
            }
        )

    contact_sheet = output_dir / "roughcut_contact_sheet.jpg"
    review_page = output_dir / "roughcut_review.html"
    manifest_path = output_dir / "roughcut_review_manifest.json"
    build_contact_sheet(items, contact_sheet)
    build_review_page(
        title=args.title,
        video=video,
        contact_sheet=contact_sheet,
        items=items,
        qc=qc,
        output=review_page,
    )
    manifest = {
        "schema_version": "newma.video.roughcut_review_manifest.v1",
        "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "video": str(video),
        "qc_report": str(Path(args.qc_report).expanduser().resolve()),
        "contact_sheet": str(contact_sheet),
        "review_page": str(review_page),
        "scene_count": len(items),
        "scenes": items,
    }
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": "ok", "review_page": str(review_page), "contact_sheet": str(contact_sheet), "scene_count": len(items)}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
