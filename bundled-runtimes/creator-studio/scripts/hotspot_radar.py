#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from intake_collectors import (
    CollectedItem,
    CollectorRun,
    collect_public_fallback,
    collect_public_news_fallback,
    now_iso,
)


SOURCE_PROFILES = {
    "public_news/wallstreetcn-quick": {"role": "macro_finance_wire", "macro_bias": 0.35},
    "public_news/10jqka-stock": {"role": "market_industry_wire", "macro_bias": 0.22},
    "public_news/bloomberg-markets": {"role": "global_market_wire", "macro_bias": 0.32},
    "public/hn_frontpage": {"role": "tech_builder_hotlist", "macro_bias": 0.05},
    "public/wsj_world": {"role": "global_policy_wire", "macro_bias": 0.28},
    "public/zhihu_hot": {"role": "china_public_discussion", "macro_bias": 0.08},
    "public/toutiao_hot": {"role": "china_mass_hotlist", "macro_bias": 0.08},
    "public/weibo_hot": {"role": "china_mass_hotlist", "macro_bias": 0.06},
    "public/hupu_hot": {"role": "china_mass_hotlist", "macro_bias": 0.03},
    "public/douyin_hot": {"role": "china_mass_hotlist", "macro_bias": 0.04},
}

MACRO_POLICY_SIGNALS = (
    "央行",
    "利率",
    "降息",
    "加息",
    "通胀",
    "就业",
    "财政",
    "关税",
    "制裁",
    "汇率",
    "美元",
    "国债",
    "债券",
    "原油",
    "黄金",
    "白银",
    "地缘",
    "战争",
    "冲突",
    "选举",
    "政策",
    "监管",
    "fed",
    "federal reserve",
    "inflation",
    "tariff",
    "sanction",
    "treasury",
    "yield",
    "rate",
    "central bank",
    "election",
    "geopolitical",
)


def normalize_source_profile(source: str) -> dict[str, Any]:
    profile = SOURCE_PROFILES.get(source)
    if profile:
        return profile
    if source.startswith("public_news/"):
        return {"role": "public_news_wire", "macro_bias": 0.18}
    if source.startswith("public/"):
        return {"role": "public_hotlist", "macro_bias": 0.04}
    return {"role": "unknown_hotspot_source", "macro_bias": 0.0}


def macro_policy_score(item: CollectedItem) -> float:
    profile = normalize_source_profile(item.source)
    text = f"{item.title} {item.summary} {item.author_name} {item.raw.get('category', '')}".lower()
    signal_hits = sum(1 for signal in MACRO_POLICY_SIGNALS if signal.lower() in text)
    category = str(item.raw.get("category") or "").lower()
    category_bonus = 0.2 if category in {"macro", "market", "finance"} else 0.0
    score = float(profile.get("macro_bias") or 0.0) + min(signal_hits, 4) * 0.13 + category_bonus
    return round(min(1.0, score), 4)


def source_role(item: CollectedItem) -> str:
    return str(normalize_source_profile(item.source).get("role") or "unknown_hotspot_source")


def item_payload(item: CollectedItem) -> dict[str, Any]:
    payload = item.to_payload()
    payload["radar"] = {
        "capture_role": "hotspot_capture",
        "source_role": source_role(item),
        "macro_policy_score": macro_policy_score(item),
        "kept_by": "dynamic_capture_no_content_filter",
    }
    return payload


def item_with_radar(item: CollectedItem) -> CollectedItem:
    payload = item_payload(item)
    return CollectedItem(
        source=str(payload.get("source") or item.source),
        channel=str(payload.get("channel") or item.channel),
        title=str(payload.get("title") or item.title),
        url=str(payload.get("url") or item.url),
        author_name=str(payload.get("author_name") or item.author_name),
        created_at=str(payload.get("created_at") or item.created_at),
        summary=str(payload.get("summary") or item.summary),
        score=float(payload.get("score") or item.score or 0.0),
        raw={
            key: value
            for key, value in payload.items()
            if key not in {"source", "channel", "title", "url", "author_name", "created_at", "summary", "score"}
        },
    )


def task_payload(run: CollectorRun, task_name: str) -> dict[str, Any]:
    status = run.status.get(task_name, {})
    return {
        "status": status.get("status", "unknown"),
        "total": status.get("total", len(run.tasks.get(task_name, []))),
        "sources": status.get("sources", {}),
        "issues": status.get("issues", []),
        "error": status.get("error"),
    }


def build_hotspot_radar_result(public_news_run: CollectorRun, public_hot_run: CollectorRun) -> dict[str, Any]:
    items = [
        *[item_payload(item) for item in public_news_run.tasks.get("public_news", [])],
        *[item_payload(item) for item in public_hot_run.tasks.get("public_hot", [])],
    ]
    items.sort(
        key=lambda item: (
            float((item.get("radar") or {}).get("macro_policy_score") or 0.0),
            float(item.get("score") or 0.0),
        ),
        reverse=True,
    )
    source_roles: dict[str, int] = {}
    for item in items:
        role = str((item.get("radar") or {}).get("source_role") or "unknown")
        source_roles[role] = source_roles.get(role, 0) + 1
    return {
        "generated_at": now_iso(),
        "module": "hotspot_radar",
        "summary": {
            "capture_role": "hotspot_capture",
            "total_items": len(items),
            "macro_policy_candidates": sum(1 for item in items if float((item.get("radar") or {}).get("macro_policy_score") or 0.0) >= 0.45),
            "source_roles": source_roles,
            "content_policy": "preserve_dynamic_news; score macro/policy/geopolitics preference without dropping other items",
        },
        "sources": {
            "public_news": task_payload(public_news_run, "public_news"),
            "public_hot": task_payload(public_hot_run, "public_hot"),
        },
        "items": items,
    }


def merge_runs(public_news_run: CollectorRun, public_hot_run: CollectorRun, radar_payload: dict[str, Any]) -> CollectorRun:
    merged = CollectorRun()
    for name, run in (("public_news", public_news_run), ("public_hot", public_hot_run)):
        items = [item_with_radar(item) for item in run.tasks.get(name, [])]
        status = run.status.get(name, {"status": "ready" if items else "empty"})
        merged.add_task(name, items, status)
    merged.status = {**public_news_run.status, **public_hot_run.status, **merged.status}
    merged.status["hotspot_radar"] = {
        "status": "ready" if radar_payload.get("items") else "empty",
        "total": len(radar_payload.get("items") or []),
        "module": "hotspot_radar",
        "summary": radar_payload.get("summary", {}),
    }
    merged.artifacts = [*public_news_run.artifacts, *public_hot_run.artifacts, "raw/hotspot_radar.json"]
    return merged


def collect_hotspot_radar(raw_dir: Path) -> CollectorRun:
    raw_dir.mkdir(parents=True, exist_ok=True)
    public_news_run = collect_public_news_fallback(raw_dir)
    public_hot_run = collect_public_fallback(raw_dir)
    payload = build_hotspot_radar_result(public_news_run, public_hot_run)
    (raw_dir / "hotspot_radar.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return merge_runs(public_news_run, public_hot_run, payload)
