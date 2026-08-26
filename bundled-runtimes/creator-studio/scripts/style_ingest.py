#!/usr/bin/env python3
"""Ingest scraped article index and generate style analysis artifacts.

Example:
python3 scripts/style_ingest.py \
  --index data/wechat_scrapes/2026-02-24_210208/index.json \
  --project 2026-02-25_热点复盘 \
  --tag wechat \
  --author "表舅是养基大户"
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
from pathlib import Path
from statistics import mean


def split_paragraphs(text: str) -> list[str]:
    return [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]


def analyze_text(text: str) -> dict:
    paras = split_paragraphs(text)
    short_para_ratio = 0.0
    if paras:
        short_para_ratio = sum(1 for p in paras if len(p) <= 40) / len(paras)

    heading_lines = sum(1 for ln in text.splitlines() if re.match(r"^(#|\d{2}$|\d[\)）]|[一二三四五六七八九十]、)", ln.strip()))
    bullet_lines = sum(1 for ln in text.splitlines() if ln.strip().startswith("- "))

    return {
        "chars": len(text),
        "paragraphs": len(paras),
        "short_para_ratio": round(short_para_ratio, 4),
        "questions": text.count("?") + text.count("？"),
        "exclaims": text.count("!") + text.count("！"),
        "digits": sum(ch.isdigit() for ch in text),
        "digit_ratio": round(sum(ch.isdigit() for ch in text) / max(1, len(text)), 4),
        "heading_lines": heading_lines,
        "bullet_lines": bullet_lines,
        "has_cta": int(("求赞" in text) or ("在看" in text) or ("评论" in text)),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--index", required=True, help="path to scrape index.json")
    parser.add_argument("--project", required=True, help="project name")
    parser.add_argument("--tag", default="wechat")
    parser.add_argument("--author", default="")
    args = parser.parse_args()

    index_path = Path(args.index)
    if not index_path.exists():
        raise FileNotFoundError(f"index not found: {index_path}")

    items = json.loads(index_path.read_text(encoding="utf-8"))
    if not isinstance(items, list) or not items:
        raise ValueError("index.json has no entries")

    now = dt.datetime.now()
    run_id = now.strftime("%Y%m%d_%H%M%S")

    per_article = []
    for item in items:
        text_path = Path(item.get("text_path", ""))
        if not text_path.is_absolute():
            text_path = Path.cwd() / text_path

        text = text_path.read_text(encoding="utf-8", errors="ignore") if text_path.exists() else ""
        stats = analyze_text(text)
        record = {
            "ingest_time": now.isoformat(timespec="seconds"),
            "project": args.project,
            "tag": args.tag,
            "author": item.get("author") or args.author,
            "title": item.get("title", ""),
            "url": item.get("url", ""),
            "slug": item.get("slug", ""),
            "images": item.get("images", 0),
            **stats,
        }
        per_article.append(record)

    agg = {
        "articles": len(per_article),
        "avg_chars": round(mean(r["chars"] for r in per_article), 1),
        "avg_images": round(mean(r["images"] for r in per_article), 2),
        "avg_short_para_ratio": round(mean(r["short_para_ratio"] for r in per_article), 4),
        "avg_digit_ratio": round(mean(r["digit_ratio"] for r in per_article), 4),
        "avg_questions": round(mean(r["questions"] for r in per_article), 2),
        "cta_ratio": round(mean(r["has_cta"] for r in per_article), 2),
    }

    engine_dir = Path("引擎") / "01_调性分析引擎"
    engine_dir.mkdir(parents=True, exist_ok=True)
    registry = engine_dir / "style_registry.jsonl"
    with registry.open("a", encoding="utf-8") as f:
        for r in per_article:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    run_file = engine_dir / "analysis_runs" / f"{run_id}_{args.project.replace(' ', '_')}.md"
    run_file.parent.mkdir(parents=True, exist_ok=True)
    titles = "\n".join(f"- {r['title']}" for r in per_article)
    run_file.write_text(
        (
            f"# 调性增量分析：{args.project}\n\n"
            f"- 时间：{now.strftime('%Y-%m-%d %H:%M:%S')}\n"
            f"- 样本数：{agg['articles']}\n"
            f"- 来源：`{index_path}`\n\n"
            "## 样本标题\n"
            f"{titles}\n\n"
            "## 聚合指标\n"
            f"- 平均字数：{agg['avg_chars']}\n"
            f"- 平均配图：{agg['avg_images']}\n"
            f"- 短段落占比：{agg['avg_short_para_ratio']}\n"
            f"- 数字字符占比：{agg['avg_digit_ratio']}\n"
            f"- 平均疑问句：{agg['avg_questions']}\n"
            f"- CTA覆盖率：{agg['cta_ratio']}\n\n"
            "## 新增迭代建议\n"
            "- [新增] 把本批样本中的高频标题结构写入知识库。\n"
            "- [校验] 对比历史批次，确认情绪强度是否影响完读率。\n"
            "- [执行] 在下一篇选题中同时产出 A/B/C 三版并复盘。\n"
        ),
        encoding="utf-8",
    )

    print(f"Ingested {len(per_article)} articles")
    print(f"Registry updated: {registry}")
    print(f"Analysis report: {run_file}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
