#!/usr/bin/env python3
from __future__ import annotations

import argparse
import html
import json
from pathlib import Path


def text(value: object) -> str:
    return html.escape(str(value or ""))


def render(cards_path: Path, ranking_path: Path, output_path: Path) -> None:
    cards_payload = json.loads(cards_path.read_text(encoding="utf-8"))
    ranking_payload = json.loads(ranking_path.read_text(encoding="utf-8"))
    cards = cards_payload.get("topic_cards", [])
    ranks = {row["topic_id"]: row for row in ranking_payload.get("ranking", [])}
    rows: list[str] = []
    for card in sorted(cards, key=lambda item: ranks.get(item["topic_id"], {}).get("rank", 999)):
        rank = ranks.get(card["topic_id"], {})
        chain = "".join(f"<li>{text(item)}</li>" for item in card.get("logic_chain", []))
        evidence = "".join(f"<span>{text(item)}</span>" for item in card.get("evidence_needed", []))
        rows.append(
            f"""
            <article class="topic-card" data-tier="{text(rank.get('tier'))}" data-search="{text(card.get('title'))} {text(card.get('core_proposition'))}">
              <header><b>#{text(rank.get('rank'))}</b><span>{text(rank.get('tier'))} 级 · {text(card.get('score'))} 分</span><i>{text(card.get('topic_id'))}</i></header>
              <h2>{text(card.get('title'))}</h2>
              <p class="judgment">{text(card.get('one_line_judgment'))}</p>
              <section><strong>核心命题</strong><p>{text(card.get('core_proposition'))}</p></section>
              <section><strong>逻辑链</strong><ol>{chain}</ol></section>
              <section><strong>反方与边界</strong><p>{text(card.get('counterargument'))}</p></section>
              <section><strong>需要补的数据</strong><div class="tags">{evidence}</div></section>
              <footer><strong>读者收获</strong><p>{text(card.get('reader_payoff'))}</p></footer>
            </article>
            """
        )

    document = f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>选题分析与逻辑推演报告</title>
<style>
:root{{--bg:#f4f1e8;--paper:#fffdf7;--ink:#18251f;--muted:#6e786f;--line:#d9d6cb;--green:#0d6b50;--gold:#b17a28}}
*{{box-sizing:border-box}} body{{margin:0;background:var(--bg);color:var(--ink);font:14px/1.65 -apple-system,BlinkMacSystemFont,"PingFang SC",sans-serif}}
.page{{max-width:1180px;margin:auto;padding:42px 24px 80px}} .hero{{display:grid;grid-template-columns:1fr auto;gap:30px;align-items:end;border-bottom:2px solid var(--ink);padding-bottom:24px}}
.eyebrow{{font-size:11px;letter-spacing:.18em;color:var(--green);font-weight:800}} h1{{font-size:36px;line-height:1.12;margin:8px 0 12px}} .hero p{{margin:0;color:var(--muted);max-width:760px}}
.metric{{text-align:right}} .metric b{{display:block;font-size:48px;line-height:1;color:var(--green)}} .metric span{{font-size:12px;color:var(--muted)}}
.toolbar{{position:sticky;top:0;z-index:5;display:flex;gap:10px;align-items:center;margin:22px 0;padding:12px;background:rgba(244,241,232,.92);backdrop-filter:blur(10px);border:1px solid var(--line);border-radius:12px}}
.toolbar input{{flex:1;border:0;background:var(--paper);padding:10px 12px;border-radius:8px;outline:none}} .toolbar button{{border:1px solid var(--line);background:var(--paper);padding:9px 12px;border-radius:8px;cursor:pointer}} .toolbar button.active{{background:var(--ink);color:white}}
.grid{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:14px}} .topic-card{{background:var(--paper);border:1px solid var(--line);border-radius:14px;padding:20px;box-shadow:0 8px 28px rgba(30,40,34,.04)}}
.topic-card header{{display:flex;align-items:center;gap:9px;color:var(--muted);font-size:11px}} .topic-card header b{{display:grid;place-items:center;width:30px;height:30px;border-radius:50%;background:var(--ink);color:white}} .topic-card header i{{margin-left:auto;font-style:normal}}
.topic-card h2{{font-size:20px;line-height:1.35;margin:14px 0 8px}} .judgment{{font-size:15px;color:var(--green);font-weight:650;border-left:3px solid var(--green);padding-left:10px}}
.topic-card section{{border-top:1px solid var(--line);padding-top:10px;margin-top:10px}} .topic-card section>strong,.topic-card footer>strong{{font-size:11px;color:var(--gold);letter-spacing:.08em}} .topic-card p{{margin:4px 0}} ol{{margin:5px 0 0;padding-left:20px}} .tags{{display:flex;flex-wrap:wrap;gap:6px;margin-top:6px}} .tags span{{background:#eeece4;border-radius:999px;padding:3px 8px;font-size:11px}}
.topic-card footer{{margin-top:12px;padding:10px 12px;background:#f0f4ef;border-radius:9px}} .hidden{{display:none}}
@media(max-width:760px){{.grid{{grid-template-columns:1fr}} .hero{{grid-template-columns:1fr}} .metric{{text-align:left}} h1{{font-size:28px}}}}
</style></head>
<body><main class="page"><section class="hero"><div><span class="eyebrow">NEWMA · BRIEF / TOPIC ANALYSIS</span><h1>30 个衍生选题与逻辑推演</h1><p>从 Intake 的 10 个基础方向继续做论证、反驳和话题衍生。排序只是系统建议，下一节点可勾选 3—10 个进入详细 Brief。</p></div><div class="metric"><b>30</b><span>候选选题</span></div></section>
<div class="toolbar"><input id="search" placeholder="搜索标题或核心命题"><button class="active" data-tier="ALL">全部</button><button data-tier="S">S 级</button><button data-tier="A">A 级</button><button data-tier="B">B 级</button><button data-tier="C">C 级</button></div>
<section class="grid" id="grid">{''.join(rows)}</section></main>
<script>const cards=[...document.querySelectorAll('.topic-card')],q=document.querySelector('#search');let tier='ALL';function filter(){{const term=q.value.trim().toLowerCase();cards.forEach(c=>c.classList.toggle('hidden',!(tier==='ALL'||c.dataset.tier===tier)||!c.dataset.search.toLowerCase().includes(term)))}}q.addEventListener('input',filter);document.querySelectorAll('[data-tier]').forEach(b=>b.onclick=()=>{{document.querySelectorAll('[data-tier]').forEach(x=>x.classList.remove('active'));b.classList.add('active');tier=b.dataset.tier;filter()}});</script></body></html>"""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(document, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("cards", type=Path)
    parser.add_argument("ranking", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    render(args.cards.resolve(), args.ranking.resolve(), args.output.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
