#!/usr/bin/env python3
from __future__ import annotations

import argparse
import html
import json
from pathlib import Path
from typing import Any


CHANNEL_LABELS = {
    "bilibili_video": "B站",
    "wechat_channels_video": "视频号",
    "xiaohongshu_video": "小红书",
    "douyin_video": "抖音",
}


def read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("发布 manifest 必须是 JSON 对象")
    return payload


def file_uri(value: Any) -> str:
    if not value:
        return ""
    path = Path(str(value)).expanduser()
    return path.resolve().as_uri() if path.exists() else ""


def esc(value: Any) -> str:
    return html.escape(str(value or ""), quote=True)


def render_card(pack: dict[str, Any], index: int) -> str:
    metadata = pack.get("publish_metadata") if isinstance(pack.get("publish_metadata"), dict) else {}
    channel = str(pack.get("channel") or "")
    label = CHANNEL_LABELS.get(channel, channel)
    title = metadata.get("title") or pack.get("title") or ""
    summary = metadata.get("summary") or ""
    tags = " ".join(f"#{item}" for item in metadata.get("tags") or [])
    cover = str(metadata.get("cover") or "")
    cover_uri = file_uri(cover)
    video = str((pack.get("artifact_hint") or {}).get("video") or "")
    platform_notes = metadata.get("platform_notes") if isinstance(metadata.get("platform_notes"), dict) else {}
    cover_status = platform_notes.get("cover_status") or "待检查"
    aspect_value = platform_notes.get("aspect_decision") or "horizontal_direct"
    if aspect_value == "pending_user_review":
        aspect_value = "horizontal_direct"
    image = (
        f'<img src="{esc(cover_uri)}" alt="{esc(label)}封面">'
        if cover_uri
        else '<div class="missing">封面文件缺失</div>'
    )
    return f"""
    <article class="channel-card" data-index="{index}" data-channel="{esc(channel)}">
      <div class="card-head">
        <label class="channel-toggle"><input class="enabled" type="checkbox" checked> <strong>{esc(label)}</strong></label>
        <span class="status">{esc(cover_status)}</span>
      </div>
      <div class="cover">{image}</div>
      <label>发布标题<input class="title" value="{esc(title)}"></label>
      <label>发布文案<textarea class="summary" rows="7">{esc(summary)}</textarea></label>
      <label>标签<input class="tags" value="{esc(tags)}"></label>
      <div class="two-col">
        <label>账号 / IP<input class="account" value="{esc(pack.get('account_slot') or 'slot-1')}"></label>
        <label>画面适配
          <select class="aspect">
            <option value="horizontal_direct"{' selected' if aspect_value == 'horizontal_direct' else ''}>16:9 横屏直发</option>
            <option value="crop_vertical"{' selected' if aspect_value == 'crop_vertical' else ''}>裁切为竖屏</option>
            <option value="rebuild_vertical"{' selected' if aspect_value == 'rebuild_vertical' else ''}>重做竖屏版</option>
          </select>
        </label>
      </div>
      <label>封面处理
        <select class="cover-action">
          <option value="keep">使用当前封面</option>
          <option value="generate_3x4">生成 3:4 封面</option>
          <option value="generate_9x16">生成 9:16 封面</option>
          <option value="replace">人工替换</option>
        </select>
      </label>
      <label>审核备注<textarea class="notes" rows="3" placeholder="需要修改的标题、封面、竖版适配或发布时间"></textarea></label>
      <div class="paths">
        <div>封面：{esc(cover)}</div>
        <div>视频：{esc(video)}</div>
      </div>
    </article>"""


def build_html(manifest: dict[str, Any], source: Path) -> str:
    packs = manifest.get("channel_packs") or []
    video = ""
    if packs:
        video = str((packs[0].get("artifact_hint") or {}).get("video") or "")
    cards = "\n".join(render_card(pack, index) for index, pack in enumerate(packs))
    payload = json.dumps(manifest, ensure_ascii=False).replace("</", "<\\/")
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>发布包装审核｜黄仁勋与阿里 AI 融资</title>
<style>
:root{{--bg:#f3f4f6;--panel:#fff;--ink:#14171a;--muted:#6b7280;--line:#d8dde5;--blue:#1667d9;--green:#16845b;}}
*{{box-sizing:border-box}} body{{margin:0;background:var(--bg);color:var(--ink);font:15px/1.55 -apple-system,BlinkMacSystemFont,"PingFang SC","Microsoft YaHei",sans-serif}}
.top{{position:sticky;top:0;z-index:10;display:flex;align-items:center;gap:14px;padding:14px 24px;background:rgba(255,255,255,.94);border-bottom:1px solid var(--line);backdrop-filter:blur(12px)}}
.top h1{{font-size:18px;margin:0}} .top .meta{{color:var(--muted);font-size:13px}} .actions{{margin-left:auto;display:flex;gap:10px;align-items:center}}
button{{border:1px solid var(--line);background:#fff;border-radius:8px;padding:9px 14px;cursor:pointer}} button.primary{{background:var(--blue);border-color:var(--blue);color:#fff}} #saveState{{color:var(--muted);font-size:13px}}
main{{max-width:1460px;margin:auto;padding:22px}} .summary-bar{{display:grid;grid-template-columns:1.3fr 1fr;gap:18px;margin-bottom:20px}}
.panel,.channel-card{{background:var(--panel);border:1px solid var(--line);border-radius:14px;box-shadow:0 6px 22px rgba(18,31,53,.05)}} .panel{{padding:18px}}
.panel h2{{font-size:17px;margin:0 0 12px}} video{{width:100%;max-height:420px;background:#111;border-radius:10px}} .gate{{display:grid;grid-template-columns:repeat(3,1fr);gap:10px}}
.metric{{padding:14px;border-radius:10px;background:#f7f9fc}} .metric b{{display:block;font-size:23px}} .metric span{{color:var(--muted);font-size:12px}}
.hint{{margin-top:12px;color:var(--muted)}} .cards{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:18px}}
.channel-card{{padding:17px}} .card-head{{display:flex;justify-content:space-between;align-items:center;margin-bottom:13px}} .channel-toggle strong{{font-size:18px}} .status{{padding:3px 8px;border-radius:999px;background:#edf5ff;color:var(--blue);font-size:12px}}
.cover{{height:250px;background:#15191f;border-radius:10px;display:flex;align-items:center;justify-content:center;overflow:hidden;margin-bottom:13px}} .cover img{{width:100%;height:100%;object-fit:contain}} .missing{{color:#fff}}
label{{display:block;color:#4b5563;font-size:13px;margin-top:11px}} input,textarea,select{{display:block;width:100%;margin-top:5px;border:1px solid var(--line);border-radius:8px;padding:9px 10px;background:#fff;color:var(--ink);font:inherit}} textarea{{resize:vertical}} .two-col{{display:grid;grid-template-columns:1fr 1fr;gap:12px}}
.paths{{margin-top:12px;padding-top:10px;border-top:1px dashed var(--line);color:var(--muted);font-size:11px;word-break:break-all}} .approved{{color:var(--green)!important}}
@media(max-width:900px){{.summary-bar,.cards{{grid-template-columns:1fr}} .actions{{flex-wrap:wrap}}}}
</style>
</head>
<body>
<header class="top">
  <div><h1>渠道包装与账号路由审核</h1><div class="meta">黄仁勋撬动 5000 亿美元，阿里配售 800 亿港元</div></div>
  <div class="actions"><span id="saveState">尚未保存</span><button id="save">保存修改</button><button id="export">导出审核决定</button><button id="approve" class="primary">四平台包装通过</button></div>
</header>
<main>
  <section class="summary-bar">
    <div class="panel"><h2>终版成片</h2><video controls preload="metadata" src="{esc(file_uri(video))}"></video></div>
    <div class="panel"><h2>本节点交付</h2><div class="gate"><div class="metric"><b>{len(packs)}</b><span>渠道包</span></div><div class="metric"><b id="enabledCount">{len(packs)}</b><span>选中平台</span></div><div class="metric"><b id="verticalCount">0</b><span>需竖版适配</span></div></div><p class="hint">本页审核标题、文案、封面、账号和画面比例。通过后再进入发布预检，不会直接上传。</p></div>
  </section>
  <section class="cards">{cards}</section>
</main>
<script>
const SOURCE = {json.dumps(str(source), ensure_ascii=False)};
const MANIFEST = {payload};
const STORAGE_KEY = 'newma_publish_review:' + SOURCE;
function collect(status='changes_requested'){{
  const channels=[...document.querySelectorAll('.channel-card')].map((card)=>{{
    const index=Number(card.dataset.index); const pack=MANIFEST.channel_packs[index]||{{}};
    return {{task_id:pack.task_id,channel:card.dataset.channel,enabled:card.querySelector('.enabled').checked,title:card.querySelector('.title').value.trim(),summary:card.querySelector('.summary').value.trim(),tags:card.querySelector('.tags').value.trim().split(/\\s+/).map(x=>x.replace(/^#/, '')).filter(Boolean),account_slot:card.querySelector('.account').value.trim(),aspect_decision:card.querySelector('.aspect').value,cover_action:card.querySelector('.cover-action').value,notes:card.querySelector('.notes').value.trim()}};
  }});
  return {{schema_version:'newma.publish_review_decision.v1',source_publish_manifest:SOURCE,status,created_at:new Date().toISOString(),channels}};
}}
function refresh(){{const cards=[...document.querySelectorAll('.channel-card')];document.querySelector('#enabledCount').textContent=cards.filter(x=>x.querySelector('.enabled').checked).length;document.querySelector('#verticalCount').textContent=cards.filter(x=>x.querySelector('.aspect').value!=='horizontal_direct').length;}}
function save(status='changes_requested'){{const payload=collect(status);localStorage.setItem(STORAGE_KEY,JSON.stringify(payload));const state=document.querySelector('#saveState');state.textContent=status==='approved' ? '已通过并保存' : '已保存 '+new Date().toLocaleTimeString();state.className=status==='approved'?'approved':'';return payload;}}
function apply(payload){{const map=new Map((payload.channels||[]).map(x=>[x.task_id,x]));document.querySelectorAll('.channel-card').forEach((card)=>{{const pack=MANIFEST.channel_packs[Number(card.dataset.index)]||{{}};const row=map.get(pack.task_id);if(!row)return;card.querySelector('.enabled').checked=row.enabled!==false;for(const key of ['title','summary','account_slot','aspect_decision','cover_action','notes']){{const selector={{account_slot:'.account',aspect_decision:'.aspect',cover_action:'.cover-action'}}[key]||'.'+key;const el=card.querySelector(selector);if(el&&row[key]!=null)el.value=row[key];}}if(Array.isArray(row.tags))card.querySelector('.tags').value=row.tags.map(x=>'#'+x).join(' ');}});refresh();}}
function download(payload){{const blob=new Blob([JSON.stringify(payload,null,2)+'\\n'],{{type:'application/json'}});const a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download='publish_review_decision.json';a.click();URL.revokeObjectURL(a.href);}}
document.querySelector('#save').onclick=()=>save();document.querySelector('#export').onclick=()=>download(save());document.querySelector('#approve').onclick=()=>{{const payload=save('approved');download(payload);}};document.addEventListener('input',()=>{{document.querySelector('#saveState').textContent='有未保存修改';refresh();}});document.addEventListener('change',refresh);
try{{const cached=localStorage.getItem(STORAGE_KEY);if(cached)apply(JSON.parse(cached));}}catch(error){{console.warn(error)}} refresh();
</script>
</body></html>"""


def main() -> None:
    parser = argparse.ArgumentParser(description="生成 Newma 发布包装审核页")
    parser.add_argument("--publish-manifest", required=True)
    parser.add_argument("--output")
    args = parser.parse_args()
    source = Path(args.publish_manifest).expanduser().resolve()
    output = Path(args.output).expanduser().resolve() if args.output else source.parent / "publish_review.html"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(build_html(read_json(source), source), encoding="utf-8")
    print(output)


if __name__ == "__main__":
    main()
