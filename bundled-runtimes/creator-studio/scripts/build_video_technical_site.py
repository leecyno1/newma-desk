#!/usr/bin/env python3
"""Build a self-contained technical registry site for the video director stack."""

from __future__ import annotations

import argparse
import html
import json
from pathlib import Path
from typing import Any

from video_director_tool_router import (
    DEFAULT_DIRECTOR_REGISTRY,
    DEFAULT_PROJECT_REGISTRY,
    DEFAULT_TOOL_REGISTRY,
    build_stage_routes,
    director_profile_for_lane,
    load_director_registry,
    load_unified_registry,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = PROJECT_ROOT / "docs" / "technical" / "video-technical-stack-registry.html"
DEFAULT_CREATOR_CANDIDATES = PROJECT_ROOT / "configs" / "workflow" / "creator_technology_candidates.json"


def esc(value: Any) -> str:
    return html.escape(str(value or ""))


def badges(values: list[str]) -> str:
    return "".join(f'<span class="badge">{esc(value)}</span>' for value in values)


def entry_location(entry: dict[str, Any]) -> str:
    return str(entry.get("path") or entry.get("root") or entry.get("local_path") or entry.get("command") or entry.get("endpoint") or "")


def table_rows(entries: list[dict[str, Any]]) -> str:
    rows = []
    for entry in entries:
        search = " ".join(
            [
                str(entry.get("name") or ""),
                str(entry.get("kind") or ""),
                str(entry.get("status") or ""),
                " ".join(entry.get("capabilities") or []),
                " ".join(entry.get("route_stages") or []),
            ]
        ).lower()
        rows.append(
            f'''<tr data-search="{esc(search)}" data-kind="{esc(entry.get('kind'))}">
  <td><strong>{esc(entry.get('name'))}</strong><div class="muted">{esc(entry.get('scope') or entry.get('execution_mode'))}</div></td>
  <td>{esc(entry.get('kind'))}</td>
  <td>{esc(entry.get('tier'))}</td>
  <td><code>{esc(entry.get('status'))}</code></td>
  <td>{badges(entry.get('capabilities') or [])}</td>
  <td>{badges(entry.get('route_stages') or entry.get('lanes') or [])}</td>
  <td class="location">{esc(entry_location(entry))}</td>
</tr>'''
        )
    return "\n".join(rows)


def candidate_rows(entries: list[dict[str, Any]]) -> str:
    rows = []
    for entry in entries:
        search = " ".join(
            [
                str(entry.get("name") or ""),
                str(entry.get("category") or ""),
                str(entry.get("availability") or ""),
                " ".join(entry.get("capabilities") or []),
                " ".join(entry.get("route_stages") or []),
                " ".join(entry.get("dependencies") or []),
                " ".join(entry.get("blockers") or []),
            ]
        ).lower()
        repo = str(entry.get("repo") or "")
        repo_link = f'<a href="{esc(repo)}">upstream</a>' if repo else "—"
        rows.append(
            f'''<tr data-search="{esc(search)}" data-kind="candidate">
  <td><strong>{esc(entry.get('name'))}</strong><div class="muted">{esc(entry.get('category'))}</div></td>
  <td><strong>{esc(entry.get('score'))}</strong>/100<div class="muted">{esc(entry.get('stars'))} stars</div></td>
  <td><code>{esc(entry.get('availability'))}</code><div class="muted">{esc(entry.get('execution_mode'))}</div></td>
  <td>{badges(entry.get('route_stages') or [])}</td>
  <td>{badges(entry.get('capabilities') or [])}</td>
  <td>{badges(entry.get('dependencies') or [])}</td>
  <td>{badges(entry.get('blockers') or [])}</td>
  <td>{esc(entry.get('recommendation'))}<div class="muted">{repo_link}</div></td>
</tr>'''
        )
    return "\n".join(rows)


def stage_cards(registry: dict[str, Any], lane: str, director_registry: dict[str, Any]) -> str:
    cards = []
    director = director_profile_for_lane(director_registry, lane)
    cards.append(
        f'''<article class="route-card">
  <h3>{esc(director.get('name'))}</h3>
  <p><b>流水线编号</b> {esc(director.get('order'))}</p>
  <p><b>状态</b> {esc(director.get('status'))}</p>
  <p><b>Pipeline</b> {esc(director.get('pipeline_id'))}</p>
  <p><b>核心工具</b> {esc(', '.join(director.get('core_tools') or []))}</p>
</article>'''
    )
    for stage, route in build_stage_routes(registry, lane=lane, director_profile=director).items():
        primary = ", ".join(item["name"] for item in route["primary_stack"]) or "未解析"
        fallback = ", ".join(item["name"] for item in route["fallback_stack"][:6]) or "—"
        unresolved = ", ".join(route["unresolved_capabilities"]) or "—"
        blocked = ", ".join(route.get("blocked_capabilities") or []) or "—"
        cards.append(
            f'''<article class="route-card">
  <h3>{esc(stage)}</h3>
  <p><b>主路由</b> {esc(primary)}</p>
  <p><b>后备</b> {esc(fallback)}</p>
  <p><b>受阻能力</b> {esc(blocked)}</p>
  <p><b>未解析能力</b> {esc(unresolved)}</p>
</article>'''
        )
    return "\n".join(cards)


def load_creator_candidates(path: Path = DEFAULT_CREATOR_CANDIDATES) -> dict[str, Any]:
    if not path.exists():
        return {"candidates": [], "selection_policy": {}}
    return json.loads(path.read_text(encoding="utf-8"))


def build_html(
    registry: dict[str, Any],
    creator_candidates: dict[str, Any] | None = None,
    director_registry: dict[str, Any] | None = None,
) -> str:
    creator_candidates = creator_candidates or load_creator_candidates()
    director_registry = director_registry or load_director_registry()
    candidate_entries = creator_candidates.get("candidates") or []
    entries = [*registry["tools"], *registry["skills"], *registry["projects"], *registry["reserve_candidates"]]
    return f'''<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>视频导演技术注册站</title>
<style>
:root{{--bg:#f3f0e8;--ink:#171717;--muted:#6e6b63;--card:#fffdf8;--line:#d8d2c5;--accent:#143cff;--good:#0a7a45}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--ink);font:15px/1.55 -apple-system,BlinkMacSystemFont,"PingFang SC",sans-serif}}
header{{padding:48px clamp(22px,5vw,76px) 30px;border-bottom:1px solid var(--line);background:linear-gradient(120deg,#fffdf8,#e8ecff)}}
h1{{font-size:clamp(34px,6vw,72px);line-height:.96;letter-spacing:-.055em;margin:0 0 18px;max-width:900px}}header p{{max-width:780px;color:var(--muted);font-size:17px}}
.stats{{display:flex;gap:12px;flex-wrap:wrap;margin-top:24px}}.stat{{background:#fff;border:1px solid var(--line);padding:12px 16px;min-width:130px}}.stat b{{font-size:27px;display:block}}
main{{padding:30px clamp(18px,4vw,64px) 80px}}h2{{font-size:27px;margin:38px 0 16px}}.routes{{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:12px}}
.route-card{{background:var(--card);border:1px solid var(--line);padding:18px}}.route-card h3{{margin:0 0 12px;color:var(--accent)}}.route-card p{{margin:8px 0}}
.toolbar{{position:sticky;top:0;z-index:2;background:rgba(243,240,232,.94);backdrop-filter:blur(14px);padding:12px 0;display:flex;gap:8px;flex-wrap:wrap}}
input,select{{background:#fff;border:1px solid var(--line);padding:11px 13px;font:inherit}}input{{min-width:min(460px,100%)}}
.table-wrap{{overflow:auto;border:1px solid var(--line);background:var(--card)}}table{{border-collapse:collapse;width:100%;min-width:1200px}}th,td{{padding:12px;border-bottom:1px solid var(--line);vertical-align:top;text-align:left}}th{{background:#ece8de;position:sticky;top:59px}}
.badge{{display:inline-block;border:1px solid #c8c4ba;background:#fff;padding:2px 7px;margin:1px 3px 3px 0;font-size:12px}}code{{color:var(--good)}}.muted,.location{{color:var(--muted);font-size:12px}}tr[hidden]{{display:none}}
</style>
</head>
<body>
<header>
  <h1>视频导演技术注册站</h1>
  <p>导演在分镜、素材、渲染、字幕、质检和发布阶段使用的统一项目、Skill 与工具索引。GPT、Kimi、Gemini、Seedance/即梦/Seedream 与 MiniMax 等官方模型能力可以保留并按凭据状态路由；额外第三方网站服务、桌面 App、登录、实验和参考项目不会自动进入生产主路由。</p>
  <div class="stats"><div class="stat"><b>{len(director_registry.get('directors') or [])}</b>导演</div><div class="stat"><b>{len(registry['tools'])}</b>工具</div><div class="stat"><b>{len(registry['skills'])}</b>Skills</div><div class="stat"><b>{len(registry['projects'])}</b>项目</div><div class="stat"><b>{len(registry['reserve_candidates'])}</b>待晋级储备</div><div class="stat"><b>{len(candidate_entries)}</b>高分创作候选</div><div class="stat"><b>{len(registry['rejected_projects'])}</b>剔除项</div></div>
</header>
<main>
  <h2>真人口播路由</h2><div class="routes">{stage_cards(registry,'talking_head_video',director_registry)}</div>
  <h2>VOX 调查解释路由</h2><div class="routes">{stage_cards(registry,'vox_explainer_video',director_registry)}</div>
  <h2>无头口播 / HTML 科普路由</h2><div class="routes">{stage_cards(registry,'explainer_html_video',director_registry)}</div>
  <h2>AI 数字人口播 / 双人访谈路由</h2><div class="routes">{stage_cards(registry,'digital_human_video',director_registry)}</div>
  <h2>电影短剧路由（Deferred）</h2><div class="routes">{stage_cards(registry,'cinematic_short_drama_video',director_registry)}</div>
  <h2>广告宣传片路由</h2><div class="routes">{stage_cards(registry,'commercial_promo_video',director_registry)}</div>
  <h2>高分自媒体创作备选</h2>
  <p class="muted">来自 Boutique Skills 评分与人工复核，最低分 {esc((creator_candidates.get('selection_policy') or {}).get('minimum_score'))}/100。这里仅供导演发现和安排适配；候选不会自动进入生产主路由。</p>
  <div class="table-wrap"><table><thead><tr><th>项目</th><th>评分</th><th>可用性</th><th>主链环节</th><th>能力</th><th>依赖</th><th>阻断项</th><th>建议</th></tr></thead><tbody>{candidate_rows(candidate_entries)}</tbody></table></div>
  <h2>完整登记表</h2>
  <div class="toolbar"><input id="q" placeholder="搜索工具、能力、状态、依赖或路径"><select id="kind"><option value="">全部类型</option><option>candidate</option><option>tool</option><option>skill</option><option>project</option><option>reserve</option></select></div>
  <div class="table-wrap"><table><thead><tr><th>名称</th><th>类型</th><th>级别</th><th>状态</th><th>能力</th><th>阶段/线路</th><th>入口</th></tr></thead><tbody>{table_rows(entries)}</tbody></table></div>
</main>
<script>
const q=document.querySelector('#q'),kind=document.querySelector('#kind'),rows=[...document.querySelectorAll('tbody tr')];
function filter(){{const needle=q.value.trim().toLowerCase(),k=kind.value;for(const row of rows)row.hidden=(needle&&!row.dataset.search.includes(needle))||(k&&row.dataset.kind!==k)}}
q.addEventListener('input',filter);kind.addEventListener('change',filter);
</script>
</body></html>'''


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build the Newma video technical registry HTML site.")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--tool-registry", default=str(DEFAULT_TOOL_REGISTRY))
    parser.add_argument("--project-registry", default=str(DEFAULT_PROJECT_REGISTRY))
    parser.add_argument("--director-registry", default=str(DEFAULT_DIRECTOR_REGISTRY))
    parser.add_argument("--creator-candidates", default=str(DEFAULT_CREATOR_CANDIDATES))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    registry = load_unified_registry(Path(args.tool_registry).expanduser().resolve(), Path(args.project_registry).expanduser().resolve())
    director_registry = load_director_registry(Path(args.director_registry).expanduser().resolve())
    creator_candidates = load_creator_candidates(Path(args.creator_candidates).expanduser().resolve())
    output = Path(args.output).expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(build_html(registry, creator_candidates, director_registry), encoding="utf-8")
    print(json.dumps({"status":"ok","output":str(output),"directors":len(director_registry.get('directors') or []),"tools":len(registry['tools']),"skills":len(registry['skills']),"projects":len(registry['projects']),"reserve_candidates":len(registry['reserve_candidates']),"creator_candidates":len(creator_candidates.get('candidates') or [])}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
