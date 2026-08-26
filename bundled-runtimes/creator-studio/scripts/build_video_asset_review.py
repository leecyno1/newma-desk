#!/usr/bin/env python3
"""Build a concise browser review page for registered video assets."""

from __future__ import annotations

import argparse
import html
import json
from pathlib import Path
from urllib.parse import quote


def file_uri(path: str) -> str:
    return "file://" + quote(str(Path(path).expanduser().resolve()))


def build_page(manifest: dict, output: Path) -> None:
    cards: list[str] = []
    for asset in manifest.get("assets") or []:
        local_path = str(asset.get("local_path") or asset.get("path") or "")
        source_url = str(asset.get("source_url") or "")
        scenes = "、".join(asset.get("scene_usage") or asset.get("scene_ids") or []) or "素材池备用"
        media = ""
        if local_path and Path(local_path).suffix.lower() in {".mp4", ".mov", ".webm"}:
            media = f'<video controls muted preload="metadata" src="{file_uri(local_path)}"></video>'
        elif local_path:
            media = f'<img loading="lazy" src="{file_uri(local_path)}" alt="{html.escape(str(asset.get("title") or "素材"))}">'
        source_link = f'<a href="{html.escape(source_url)}">打开来源</a>' if source_url else '<span>来源链接待补</span>'
        cards.append(
            f"""
            <article class="card">
              {media}
              <div class="body">
                <div class="top"><b>{html.escape(str(asset.get('id') or ''))}</b><span>{html.escape(str(asset.get('evidence_role') or 'context'))}</span></div>
                <h2>{html.escape(str(asset.get('title') or '未命名素材'))}</h2>
                <p>{html.escape(str(asset.get('publisher') or ''))} · {html.escape(str(asset.get('source_title') or ''))}</p>
                <dl><dt>使用镜头</dt><dd>{html.escape(scenes)}</dd><dt>本地片段</dt><dd>{html.escape(str(asset.get('local_time_range') or ''))}</dd><dt>版权复核</dt><dd>{html.escape(str(asset.get('rights_review_status') or 'pending'))}</dd></dl>
                <div class="links">{source_link}<a href="{file_uri(local_path)}">打开本地文件</a></div>
              </div>
            </article>
            """
        )
    title = html.escape(str(manifest.get("project") or "视频素材审核"))
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        f"""<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{title} · 素材审核</title>
<style>
:root{{--paper:#f5f1e8;--ink:#171918;--red:#a84a32;--blue:#2f6f8f;--line:#d8d0c2}}*{{box-sizing:border-box}}body{{margin:0;background:var(--paper);color:var(--ink);font-family:-apple-system,BlinkMacSystemFont,"PingFang SC",sans-serif}}header{{padding:32px 4vw 22px;border-bottom:1px solid var(--line)}}h1{{margin:0;font-size:30px}}header p{{margin:10px 0 0;color:#666}}main{{display:grid;grid-template-columns:repeat(auto-fit,minmax(360px,1fr));gap:18px;padding:24px 4vw 48px}}.card{{background:#fff;border:1px solid var(--line);border-radius:18px;overflow:hidden;box-shadow:0 10px 28px #33261610}}video,img{{display:block;width:100%;aspect-ratio:16/9;object-fit:cover;background:#111}}.body{{padding:18px}}.top{{display:flex;justify-content:space-between;color:var(--blue);font-size:13px}}.top span{{padding:3px 8px;border-radius:99px;background:#edf4f7}}h2{{font-size:20px;margin:10px 0 6px}}p{{color:#666;font-size:14px;line-height:1.5}}dl{{display:grid;grid-template-columns:76px 1fr;gap:7px 10px;font-size:13px}}dt{{color:#888}}dd{{margin:0}}.links{{display:flex;gap:10px;margin-top:14px}}a{{color:#fff;background:var(--ink);text-decoration:none;padding:8px 12px;border-radius:9px;font-size:13px}}.links a:first-child{{background:var(--red)}}
</style></head><body><header><h1>{title}</h1><p>{html.escape(str(manifest.get('evidence_policy') or ''))}</p></header><main>{''.join(cards)}</main></body></html>""",
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    manifest = json.loads(Path(args.manifest).expanduser().read_text(encoding="utf-8"))
    build_page(manifest, Path(args.output).expanduser().resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
