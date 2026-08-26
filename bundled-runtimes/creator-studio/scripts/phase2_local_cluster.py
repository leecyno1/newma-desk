#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import math
import os
import re
import urllib.request
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from path_config import get_stage_dir


CLUSTER_RULES = [
    {
        "id": "ai_tools_open_source",
        "name": "AI工具与开源效率",
        "keywords": [
            "ai",
            "人工智能",
            "开源",
            "github",
            "效率",
            "工具",
            "自动化",
            "编程",
            "模型",
            "文档",
            "视频生成",
        ],
    },
    {
        "id": "macro_policy_markets",
        "name": "宏观政策与市场波动",
        "keywords": [
            "加息",
            "降息",
            "通胀",
            "宏观",
            "美联储",
            "利率",
            "货币",
            "经济",
            "汇率",
            "债券",
            "国债",
        ],
    },
    {
        "id": "geopolitics_security",
        "name": "地缘政治与安全冲突",
        "keywords": [
            "战争",
            "冲突",
            "制裁",
            "军事",
            "中东",
            "乌克兰",
            "俄罗斯",
            "红海",
            "航运",
            "北约",
            "台海",
        ],
    },
    {
        "id": "finance_investment_asset",
        "name": "投资配置与资产定价",
        "keywords": [
            "黄金",
            "原油",
            "股市",
            "etf",
            "投资",
            "交易",
            "仓位",
            "配置",
            "风控",
            "估值",
            "白银",
        ],
    },
    {
        "id": "tech_industry_hardware",
        "name": "科技产业与硬件竞争",
        "keywords": [
            "芯片",
            "半导体",
            "手机",
            "英伟达",
            "苹果",
            "算力",
            "云",
            "机器人",
            "gpu",
            "终端",
        ],
    },
    {
        "id": "media_content_growth",
        "name": "内容运营与增长方法",
        "keywords": [
            "公众号",
            "自媒体",
            "选题",
            "爆款",
            "流量",
            "复盘",
            "写作",
            "发布",
            "转化",
            "账号",
        ],
    },
]

DEFAULT_CLUSTER = {"id": "other_general", "name": "其他泛资讯"}

SOURCE_WEIGHT = {
    "mediacrawler": 2.5,
    "trendradar_report": 2.0,
    "trendradar_excerpt": 2.2,
    "wemprss_article": 1.4,
}


@dataclass
class Record:
    record_id: str
    source: str
    platform: str
    title: str
    url: str
    author: str
    text: str
    signal: float
    raw: dict[str, Any]


def safe_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def to_int(value: Any) -> int:
    try:
        text = str(value or "").strip().replace(",", "")
        if text == "":
            return 0
        return int(float(text))
    except Exception:
        return 0


def normalize_text(parts: list[str]) -> str:
    text = " ".join([p for p in parts if p]).strip().lower()
    text = re.sub(r"\s+", " ", text)
    return text


def fetch_text_from_url(url: str, timeout: int = 8) -> str:
    try:
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 (compatible; Phase2LocalCluster/1.0)",
            },
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read().decode("utf-8", errors="ignore")
    except Exception:
        return ""


def extract_titles_from_html(html: str, max_count: int = 20) -> list[str]:
    if not html:
        return []
    cleaned = re.sub(r"(?is)<script.*?>.*?</script>", " ", html)
    cleaned = re.sub(r"(?is)<style.*?>.*?</style>", " ", cleaned)
    tags = re.findall(r"(?is)<(?:h1|h2|h3|a)[^>]*>(.*?)</(?:h1|h2|h3|a)>", cleaned)
    out: list[str] = []
    for t in tags:
        t = re.sub(r"(?is)<.*?>", "", t)
        t = re.sub(r"\s+", " ", t).strip()
        if len(t) < 8:
            continue
        if t in out:
            continue
        out.append(t)
        if len(out) >= max_count:
            break
    return out


def build_records(stage1_dir: Path) -> list[Record]:
    raw_dir = stage1_dir / "raw"
    mc_latest_path = raw_dir / "mediacrawler_latest.json"
    if mc_latest_path.exists():
        mc_latest_items = safe_json(mc_latest_path).get("items", [])
    else:
        mc_latest_items = []
        for platform in ["x", "wb", "xhs", "douyin", "bili"]:
            platform_path = raw_dir / f"mediacrawler_latest_{platform}.json"
            if platform_path.exists():
                payload = safe_json(platform_path)
                mc_latest_items.extend(payload.get("items", []))

    tr_reports = safe_json(raw_dir / "trendradar_reports.json")
    wx_service_path = raw_dir / "wemprss_service_articles.json"
    wx_articles_latest_path = raw_dir / "wemprss_articles_latest.json"
    if wx_service_path.exists():
        wx_articles = safe_json(wx_service_path)
    elif wx_articles_latest_path.exists():
        wx_articles = safe_json(wx_articles_latest_path)
    else:
        wx_articles = {"data": {"list": []}}

    records: list[Record] = []

    for item in mc_latest_items:
        liked = to_int(item.get("liked_count"))
        comment = to_int(item.get("comment_count"))
        share = to_int(item.get("share_count"))
        collect = to_int(item.get("collected_count"))
        weighted = liked + comment * 3 + share * 4 + collect * 2
        signal = math.log1p(max(weighted, 0))
        text = normalize_text(
            [
                item.get("title", ""),
                item.get("content", ""),
                item.get("tag_list", ""),
                item.get("source_task", ""),
            ]
        )
        records.append(
            Record(
                record_id=f"mc:{item.get('id')}",
                source="mediacrawler",
                platform=str(item.get("platform") or "unknown"),
                title=str(item.get("title") or ""),
                url=str(item.get("url") or ""),
                author=str(item.get("author_name") or ""),
                text=text,
                signal=signal,
                raw=item,
            )
        )

    for report in tr_reports[:25]:
        title = str(report.get("label") or "")
        rel = str(report.get("relpath") or "")
        url = (
            f"http://127.0.0.1:18080/output/{rel}"
            if rel
            else "http://127.0.0.1:18080/reports"
        )
        text = normalize_text([title, rel, str(report.get("date") or "")])
        records.append(
            Record(
                record_id=f"tr:{report.get('id')}",
                source="trendradar_report",
                platform="trendradar",
                title=title,
                url=url,
                author="TrendRadar",
                text=text,
                signal=0.9,
                raw=report,
            )
        )

    for report in tr_reports[:5]:
        rel = str(report.get("relpath") or "")
        if not rel:
            continue
        url = f"http://127.0.0.1:18080/output/{rel}"
        html = fetch_text_from_url(url)
        snippets = extract_titles_from_html(html, max_count=15)
        for idx, snippet in enumerate(snippets):
            records.append(
                Record(
                    record_id=f"tre:{report.get('id')}:{idx}",
                    source="trendradar_excerpt",
                    platform="trendradar",
                    title=snippet,
                    url=url,
                    author="TrendRadar",
                    text=normalize_text([snippet]),
                    signal=1.1,
                    raw={"report_id": report.get("id"), "snippet_index": idx},
                )
            )

    for item in (wx_articles.get("data") or {}).get("list", []):
        title = str(item.get("title") or "")
        text = normalize_text(
            [
                title,
                str(item.get("description") or ""),
                str(item.get("mp_name") or ""),
                str(item.get("source_platform") or ""),
            ]
        )
        records.append(
            Record(
                record_id=f"wx:{item.get('id')}",
                source="wemprss_article",
                platform=str(item.get("source_platform") or "unknown"),
                title=title,
                url=str(item.get("url") or ""),
                author=str(item.get("mp_name") or ""),
                text=text,
                signal=0.7,
                raw=item,
            )
        )

    return records


def cluster_record(record: Record) -> tuple[dict[str, str], dict[str, int]]:
    hit_map: dict[str, int] = {}
    keyword_hit_detail: dict[str, int] = {}
    text = record.text
    for rule in CLUSTER_RULES:
        count = 0
        for kw in rule["keywords"]:
            c = text.count(kw.lower())
            if c > 0:
                count += c
                keyword_hit_detail[kw] = keyword_hit_detail.get(kw, 0) + c
        hit_map[rule["id"]] = count

    best = max(hit_map.values()) if hit_map else 0
    if best <= 0:
        return DEFAULT_CLUSTER, keyword_hit_detail

    for rule in CLUSTER_RULES:
        if hit_map[rule["id"]] == best:
            return {"id": rule["id"], "name": rule["name"]}, keyword_hit_detail
    return DEFAULT_CLUSTER, keyword_hit_detail


def build_outputs(records: list[Record], output_dir: Path, run_id: str, stage1_dir: Path) -> None:
    cluster_items: dict[str, list[dict[str, Any]]] = defaultdict(list)
    cluster_keywords: dict[str, Counter] = defaultdict(Counter)

    for record in records:
        cluster, hit_detail = cluster_record(record)
        base = SOURCE_WEIGHT.get(record.source, 1.0)
        keyword_score = sum(hit_detail.values())
        heat = round(base + keyword_score * 1.8 + record.signal, 4)
        row = {
            "record_id": record.record_id,
            "cluster_id": cluster["id"],
            "cluster_name": cluster["name"],
            "source": record.source,
            "platform": record.platform,
            "title": record.title,
            "url": record.url,
            "author": record.author,
            "heat": heat,
            "keyword_hits": keyword_score,
            "signal": round(record.signal, 4),
            "raw": record.raw,
        }
        cluster_items[cluster["id"]].append(row)
        cluster_keywords[cluster["id"]].update(hit_detail)

    cluster_summary: list[dict[str, Any]] = []
    for cluster_id, items in cluster_items.items():
        cluster_name = items[0]["cluster_name"] if items else cluster_id
        platforms = sorted(list({i["platform"] for i in items}))
        sources = sorted(list({i["source"] for i in items}))
        avg_heat = sum(i["heat"] for i in items) / max(len(items), 1)
        composite = round(avg_heat * 0.45 + len(items) * 0.35 + len(platforms) * 1.2, 4)
        top_items = sorted(items, key=lambda x: x["heat"], reverse=True)[:5]
        top_keywords = [k for k, _ in cluster_keywords[cluster_id].most_common(8)]
        cluster_summary.append(
            {
                "cluster_id": cluster_id,
                "cluster_name": cluster_name,
                "count": len(items),
                "platforms": platforms,
                "sources": sources,
                "avg_heat": round(avg_heat, 4),
                "composite_heat": composite,
                "top_keywords": top_keywords,
                "top_items": top_items,
            }
        )

    cluster_summary.sort(key=lambda x: x["composite_heat"], reverse=True)

    ranked_clusters = sorted(
        cluster_summary,
        key=lambda x: (
            x["composite_heat"]
            * (0.25 if x["cluster_id"] == DEFAULT_CLUSTER["id"] else 1.0)
        ),
        reverse=True,
    )

    topic_index = []
    for idx, c in enumerate(ranked_clusters, start=1):
        topic_index.append(
            {
                "rank": idx,
                "topic_id": c["cluster_id"],
                "topic_name": c["cluster_name"],
                "composite_heat": c["composite_heat"],
                "count": c["count"],
                "platform_count": len(c["platforms"]),
                "source_count": len(c["sources"]),
                "top_keywords": c["top_keywords"][:5],
            }
        )

    editorial_briefs = []
    for c in ranked_clusters:
        evidence = [
            {
                "title": item["title"],
                "url": item["url"],
                "source": item["source"],
                "platform": item["platform"],
                "heat": item["heat"],
            }
            for item in c["top_items"][:3]
        ]
        top_keywords = c["top_keywords"][:3]
        editorial_briefs.append(
            {
                "topic_id": c["cluster_id"],
                "topic_name": c["cluster_name"],
                "thesis": f"{c['cluster_name']}在本轮采集中呈现稳定高频，具备连续创作价值。",
                "why_now": f"当前样本量 {c['count']}，覆盖平台 {len(c['platforms'])} 个，热度分 {c['composite_heat']}。",
                "audience_value": "可提供高频信息筛选与可执行决策建议。",
                "angles": [
                    f"从关键词 {k} 切入，做结构化拆解。" for k in top_keywords
                ],
                "evidence_items": evidence,
                "risk_notes": [
                    "避免仅凭单平台数据下结论。",
                    "注意剔除广告与引流链接噪音。",
                ],
                "next_actions": [
                    "阶段三按该母题输出 A/B/C 三个题目方向。",
                    "阶段四补采证据链中的原始正文与图表。",
                ],
            }
        )

    top_n = [t for t in topic_index if t["topic_id"] != DEFAULT_CLUSTER["id"]][:3]

    summary_json = {
        "run_id": run_id,
        "generated_at": datetime.now().isoformat(),
        "input_stage1_dir": str(stage1_dir),
        "stats": {
            "input_records": len(records),
            "cluster_count": len(cluster_summary),
            "topn_count": len(top_n),
        },
        "clusters": cluster_summary,
    }

    (output_dir / "phase2-clusters-summary.json").write_text(
        json.dumps(summary_json, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (output_dir / "phase2-topic-index.json").write_text(
        json.dumps(topic_index, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (output_dir / "phase2-editorial-briefs.json").write_text(
        json.dumps(editorial_briefs, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (output_dir / "phase2-topn-for-confirmation.json").write_text(
        json.dumps(top_n, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    md = []
    md.append(f"# 第二环节 Brief 库（run_id={run_id}）")
    md.append("")
    md.append("## TOP3 待确认")
    for t in top_n:
        md.append(
            f"- {t['rank']}. {t['topic_name']} | heat={t['composite_heat']} | count={t['count']} | 关键词={','.join(t['top_keywords'])}"
        )
    md.append("")
    for i, brief in enumerate(editorial_briefs, start=1):
        md.append(f"## {i}. {brief['topic_name']} ({brief['topic_id']})")
        md.append(f"- 核心判断：{brief['thesis']}")
        md.append(f"- Why now：{brief['why_now']}")
        md.append(f"- 用户价值：{brief['audience_value']}")
        md.append("- 切入角度：")
        for a in brief["angles"]:
            md.append(f"  - {a}")
        md.append("- 证据链：")
        for e in brief["evidence_items"]:
            md.append(f"  - [{e['source']}/{e['platform']}] {e['title']} ({e['url']})")
        md.append("- 风险：")
        for r in brief["risk_notes"]:
            md.append(f"  - {r}")
        md.append("- 下一步：")
        for n in brief["next_actions"]:
            md.append(f"  - {n}")
        md.append("")
    (output_dir / "phase2-brief-library.md").write_text("\n".join(md), encoding="utf-8")


def write_stage2_notes(output_dir: Path, run_id: str) -> None:
    summary = safe_json(output_dir / "phase2-clusters-summary.json")
    topic_index = safe_json(output_dir / "phase2-topic-index.json")
    topn = safe_json(output_dir / "phase2-topn-for-confirmation.json")

    draft = []
    draft.append(f"# 第二环节内容聚合与选题分析底稿（{run_id}）")
    draft.append("")
    draft.append("## 一、聚合概览")
    draft.append(
        f"- 输入记录数：{summary['stats']['input_records']}；聚类数：{summary['stats']['cluster_count']}。"
    )
    draft.append("- 本轮按主题关键词 + 平台信号做自动聚类。")
    draft.append("")
    draft.append("## 二、主题索引（按热度）")
    draft.append("| 排名 | 主题 | 热度 | 条目数 | 平台数 | 来源数 | 关键词 |")
    draft.append("| --- | --- | --- | --- | --- | --- | --- |")
    for t in topic_index:
        draft.append(
            f"| {t['rank']} | {t['topic_name']} | {t['composite_heat']} | {t['count']} | {t['platform_count']} | {t['source_count']} | {','.join(t['top_keywords'])} |"
        )
    draft.append("")
    draft.append("## 三、TOP3 待确认")
    for i, t in enumerate(topn, start=1):
        draft.append(
            f"- TOP{i}: {t['topic_name']}（heat={t['composite_heat']}，count={t['count']}）"
        )
    draft.append("")
    draft.append("## 四、下一阶段建议")
    draft.append("- 阶段三先围绕 TOP3 各产出 3 个选题角度。")
    draft.append("- 阶段四补抓 TOP3 的正文与数据证据，优先跨平台证据。")
    (output_dir / "02_内容聚合及选题分析_底稿.md").write_text(
        "\n".join(draft), encoding="utf-8"
    )

    report = []
    report.append(f"# 第二环节执行报告（{run_id}）")
    report.append("")
    report.append("## 1. 执行结论")
    report.append("- 已完成：内容聚合、主题聚类、热度排序、TopN 选题输出。")
    report.append(
        f"- 本轮输入 {summary['stats']['input_records']} 条记录，输出 {summary['stats']['cluster_count']} 个主题簇。"
    )
    report.append("")
    report.append("## 2. 输出文件")
    for p in [
        "phase2-clusters-summary.json",
        "phase2-topic-index.json",
        "phase2-editorial-briefs.json",
        "phase2-brief-library.md",
        "phase2-topn-for-confirmation.json",
        "02_内容聚合及选题分析_底稿.md",
        "02_内容聚合及选题分析_报告.md",
    ]:
        report.append(f"- `{p}`")
    report.append("")
    report.append("## 3. 风险说明")
    report.append("- 18080 当前主要是报告目录，正文证据还需要阶段四补抓。")
    report.append("- 8001 样本中含门户 RSS 内容，阶段三选题前需做来源白名单。")
    report.append("- 聚类采用关键词规则，可在后续改为向量聚类提升准确度。")
    (output_dir / "02_内容聚合及选题分析_报告.md").write_text(
        "\n".join(report), encoding="utf-8"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Local phase2 clustering for stage1 intake output")
    parser.add_argument("--stage1-dir", required=True, help="Path to stage1 output directory")
    parser.add_argument(
        "--output-root",
        default=None,
        help="Legacy output root (stage-level); default=~/Desktop/自媒体创作/<run_id>/02_选题",
    )
    args = parser.parse_args()

    stage1_dir = Path(args.stage1_dir).expanduser().resolve()
    run_id = stage1_dir.name
    if args.output_root:
        output_dir = Path(args.output_root).expanduser().resolve() / run_id
    else:
        output_dir = get_stage_dir("brief", run_id)
    output_dir.mkdir(parents=True, exist_ok=True)

    records = build_records(stage1_dir)
    if not records:
        raise RuntimeError("No records parsed from stage1 input.")

    build_outputs(records, output_dir, run_id, stage1_dir)
    write_stage2_notes(output_dir, run_id)

    manifest = {
        "run_id": run_id,
        "generated_at": datetime.now().isoformat(),
        "stage1_dir": str(stage1_dir),
        "output_dir": str(output_dir),
        "artifacts": [
            "phase2-clusters-summary.json",
            "phase2-topic-index.json",
            "phase2-editorial-briefs.json",
            "phase2-brief-library.md",
            "phase2-topn-for-confirmation.json",
            "02_内容聚合及选题分析_底稿.md",
            "02_内容聚合及选题分析_报告.md",
        ],
    }
    (output_dir / "phase2_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
