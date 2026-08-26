"""资讯雷达数据层 —— 移植自 investment-news。

抓 12 赛道 108 个公开 RSS 源 → 合规过滤（赌/预测市场/加密/色情）+ 最近 N 天
+ 按赛道分组、时间倒序。纯标准库 + 线程池，零 key、零个股字段。

AI「今日要点」不在此模块——复用 Vibe-Research 的可插拔 AI 层（前端调 /api/chat，
把某赛道资讯打包给用户自己的模型提炼）。本模块只出客观资讯。
"""

from __future__ import annotations

import json
import os
import re
import time
import urllib.request
import xml.etree.ElementTree as ET
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime
from threading import get_ident, Lock, Thread

from newsindustry import classify_industries
from newsmonitor import build_news_monitor
from newstranslate import apply_chinese_titles

HERE = os.path.dirname(os.path.abspath(__file__))
MONITOR_SCHEMA_VERSION = 10
SOURCES_FILE = os.path.join(HERE, "news_sources.json")
CACHE_DIR = os.path.join(HERE, ".cache")
CACHE_FILE = os.path.join(CACHE_DIR, "radar.json")
AUTO_REFRESH_MINUTES = max(5, int(os.environ.get("NEWS_RADAR_AUTO_REFRESH_MINUTES", "15")))

_REFRESH_LOCK = Lock()
_TOPIC_INDEX_LOCK = Lock()
_TOPIC_INDEX_KEY = ""
_TOPIC_INDEX: list[dict] = []

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
BEIJING = timezone(timedelta(hours=8))


def _strip_html(s: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", s or "")).strip()


def _local(tag: str) -> str:
    return tag.split("}")[-1]


def _parse_dt(s: str):
    if not s:
        return None
    try:
        dt = parsedate_to_datetime(s)
    except Exception:
        try:
            dt = datetime.fromisoformat(s.strip().replace("Z", "+00:00"))
        except Exception:
            return None
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _fetch_source(src: dict, per: int, cutoff, redline: list[str]):
    """抓单个 RSS 源，并保留可展示的失败原因。"""
    started = time.monotonic()
    try:
        req = urllib.request.Request(src["url"], headers={
            "User-Agent": UA,
            "Accept": "application/rss+xml,application/atom+xml,application/xml,text/xml,*/*",
        })
        with urllib.request.urlopen(req, timeout=14) as r:
            raw = r.read()
        root = ET.fromstring(raw)
        out = []
        for n in [e for e in root.iter() if _local(e.tag) in ("item", "entry")]:
            if len(out) >= per:
                break
            d = {
                "title": "", "url": "", "time": "", "ts": 0,
                "summary": "", "source": src["name"],
                "source_url": src["url"], "source_industry_key": src["hint"],
                "industry_key": src["hint"],
            }
            rawtime = ""
            for c in n:
                t = _local(c.tag)
                if t == "title" and not d["title"]:
                    d["title"] = (c.text or "").strip()
                elif t == "link" and not d["url"]:
                    d["url"] = c.get("href") or (c.text or "").strip()
                elif t in ("pubDate", "published", "updated", "date") and not rawtime:
                    rawtime = (c.text or "").strip()
                elif t in ("description", "summary", "content") and not d["summary"]:
                    d["summary"] = _strip_html(c.text or "")[:160]
            if not d["title"]:
                continue
            blob = (d["title"] + " " + d["summary"]).lower()
            if any(k in blob for k in redline):  # 合规红线过滤
                continue
            dt = _parse_dt(rawtime)
            if dt is not None:
                if cutoff and dt < cutoff:
                    continue
                d["time"] = dt.astimezone(BEIJING).strftime("%m-%d %H:%M")
                d["ts"] = int(dt.timestamp())
            else:
                d["time"] = "—"
            out.append(d)
        return {
            "items": out,
            "error": None,
            "elapsed_ms": round((time.monotonic() - started) * 1000),
        }
    except Exception as exc:
        return {
            "items": None,
            "error": f"{type(exc).__name__}: {str(exc)[:160]}",
            "elapsed_ms": round((time.monotonic() - started) * 1000),
        }


def _read_cache_file() -> dict | None:
    try:
        with open(CACHE_FILE, encoding="utf-8") as handle:
            return json.load(handle)
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def _write_cache_file(data: dict) -> None:
    os.makedirs(CACHE_DIR, exist_ok=True)
    temporary = f"{CACHE_FILE}.{os.getpid()}.{get_ident()}.tmp"
    with open(temporary, "w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False)
    os.replace(temporary, CACHE_FILE)


def _fetch_radar_unlocked() -> dict:
    """抓全部源，返回 12 赛道数据并落盘缓存。"""
    cfg = json.load(open(SOURCES_FILE, encoding="utf-8"))
    days = cfg.get("fetch", {}).get("recent_days", 7)
    per = cfg.get("fetch", {}).get("per_source", 6)
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    redline = [k.lower() for k in cfg.get("redline_keywords", [])]

    previous = _read_cache_file() or {}
    previous_items: dict[str, list[dict]] = {}
    for industry in previous.get("industries") or []:
        for item in industry.get("items") or []:
            key = str(item.get("source_url") or item.get("source") or "")
            if key:
                previous_items.setdefault(key, []).append(item)
    previous_health = {
        str(item.get("url") or item.get("name") or ""): item
        for item in (previous.get("stats") or {}).get("source_health") or []
    }

    byhint: dict[str, list] = {}
    for s in cfg["sources"]:
        byhint.setdefault(s["hint"], []).append(s)

    industries, tasks = [], []
    for i, ind in enumerate(cfg["industries"]):
        pool = byhint.get(ind["key"], [])
        industries.append({"key": ind["key"], "name": ind["name"], "accent": ind["accent"], "total": len(pool), "items": []})
        for s in pool:
            tasks.append((i, s))

    with ThreadPoolExecutor(max_workers=40) as ex:
        results = list(ex.map(lambda t: (t[0], t[1], _fetch_source(t[1], per, cutoff, redline)), tasks))

    failed = 0
    stale = 0
    source_health = []
    checked_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    cutoff_timestamp = int(cutoff.timestamp())
    for idx, source, result in results:
        items = result["items"]
        prior = previous_health.get(source["url"]) or previous_health.get(source["name"]) or {}
        if items is None:
            failed += 1
            cached = [
                dict(item) for item in previous_items.get(source["url"], previous_items.get(source["name"], []))
                if not item.get("ts") or int(item.get("ts") or 0) >= cutoff_timestamp
            ]
            if cached:
                stale += 1
                for item in cached:
                    item["source_industry_key"] = source["hint"]
                industries[idx]["items"].extend(cached)
            source_health.append({
                "name": source["name"],
                "url": source["url"],
                "industry_key": source["hint"],
                "status": "stale" if cached else "failed",
                "item_count": len(cached),
                "fresh_item_count": 0,
                "error": result["error"],
                "elapsed_ms": result["elapsed_ms"],
                "checked_at": checked_at,
                "last_success_at": prior.get("last_success_at") or (previous.get("generated_at_iso") if cached else None),
            })
            continue
        industries[idx]["items"].extend(items)
        source_health.append({
            "name": source["name"],
            "url": source["url"],
            "industry_key": source["hint"],
            "status": "healthy",
            "item_count": len(items),
            "fresh_item_count": len(items),
            "error": None,
            "elapsed_ms": result["elapsed_ms"],
            "checked_at": checked_at,
            "last_success_at": checked_at,
        })
    classification_stats = classify_industries(industries)
    apply_chinese_titles(industries, translate_missing=True)
    full_monitor = build_news_monitor(industries, max_topics=10_000)
    topic_index = full_monitor.get("topics") or []
    monitor = {**full_monitor, "topics": topic_index[:80]}

    data = {
        "generated_at": datetime.now(BEIJING).strftime("%Y-%m-%d %H:%M"),
        "generated_at_iso": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "recent_days": days,
        "industries": industries,
        "stats": {
            "industries": len(cfg["industries"]),
            "total_sources": len(cfg["sources"]),
            "healthy_sources": len(cfg["sources"]) - failed,
            "failed_sources": failed,
            "stale_sources": stale,
            "unavailable_sources": failed - stale,
            "source_health": source_health,
            **classification_stats,
        },
        "monitor": monitor,
        "_topic_index": topic_index,
        "monitor_schema_version": MONITOR_SCHEMA_VERSION,
    }
    _write_cache_file(data)
    global _TOPIC_INDEX_KEY, _TOPIC_INDEX
    with _TOPIC_INDEX_LOCK:
        _TOPIC_INDEX_KEY = ""
        _TOPIC_INDEX = []
    return data


def fetch_radar() -> dict:
    with _REFRESH_LOCK:
        return _fetch_radar_unlocked()


def _refresh_in_background() -> None:
    try:
        _fetch_radar_unlocked()
    finally:
        _REFRESH_LOCK.release()


def trigger_background_refresh() -> bool:
    if not _REFRESH_LOCK.acquire(blocking=False):
        return False
    Thread(target=_refresh_in_background, name="news-radar-refresh", daemon=True).start()
    return True


def load_cache():
    data = _read_cache_file()
    if data is None:
        return None
    translated = apply_chinese_titles(data.get("industries") or [], translate_missing=False)
    schema_changed = data.get("monitor_schema_version") != MONITOR_SCHEMA_VERSION
    needs_classification = schema_changed or any(
        "source_industry_key" not in item
        for industry in data.get("industries") or []
        for item in industry.get("items") or []
    )
    classification_stats = classify_industries(data.get("industries") or []) if needs_classification else None
    if translated or needs_classification or not data.get("_topic_index"):
        full_monitor = build_news_monitor(data.get("industries") or [], max_topics=10_000)
        topic_index = full_monitor.get("topics") or []
        data["monitor"] = {**full_monitor, "topics": topic_index[:80]}
        data["_topic_index"] = topic_index
        data["monitor_schema_version"] = MONITOR_SCHEMA_VERSION
        if classification_stats:
            data.setdefault("stats", {}).update(classification_stats)
        _write_cache_file(data)
    stats = data.setdefault("stats", {})
    total = int(stats.get("total_sources") or 0)
    failed = int(stats.get("failed_sources") or 0)
    stats.setdefault("healthy_sources", max(0, total - failed))
    stats.setdefault("stale_sources", 0)
    stats.setdefault("unavailable_sources", failed)
    stats.setdefault("source_health", [])
    return data


def skeleton() -> dict:
    """无缓存时返回赛道骨架（空 items），前端提示点刷新。"""
    cfg = json.load(open(SOURCES_FILE, encoding="utf-8"))
    byhint: dict[str, int] = {}
    for s in cfg["sources"]:
        byhint[s["hint"]] = byhint.get(s["hint"], 0) + 1
    return {
        "generated_at": None,
        "generated_at_iso": None,
        "recent_days": cfg.get("fetch", {}).get("recent_days", 7),
        "industries": [{"key": i["key"], "name": i["name"], "accent": i["accent"], "total": byhint.get(i["key"], 0), "items": []} for i in cfg["industries"]],
        "stats": {
            "industries": len(cfg["industries"]),
            "total_sources": len(cfg["sources"]),
            "healthy_sources": 0,
            "failed_sources": 0,
            "stale_sources": 0,
            "unavailable_sources": 0,
            "source_health": [],
        },
        "monitor": build_news_monitor([]),
        "monitor_schema_version": MONITOR_SCHEMA_VERSION,
    }


def _generated_at(data: dict) -> datetime | None:
    value = data.get("generated_at_iso") or data.get("generated_at")
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=BEIJING)


def _is_stale(data: dict) -> bool:
    generated = _generated_at(data)
    return generated is None or datetime.now(timezone.utc) - generated.astimezone(timezone.utc) >= timedelta(minutes=AUTO_REFRESH_MINUTES)


def _with_refresh_state(data: dict) -> dict:
    output = dict(data)
    output.pop("_topic_index", None)
    output["refresh"] = {
        "refreshing": _REFRESH_LOCK.locked(),
        "stale": _is_stale(data),
        "interval_minutes": AUTO_REFRESH_MINUTES,
    }
    return output


def get_radar(force: bool = False) -> dict:
    if force:
        return _with_refresh_state(fetch_radar())
    data = load_cache() or skeleton()
    if _is_stale(data):
        trigger_background_refresh()
    return _with_refresh_state(data)


def _all_topics(data: dict) -> list[dict]:
    global _TOPIC_INDEX_KEY, _TOPIC_INDEX
    key = str(data.get("generated_at_iso") or data.get("generated_at") or "empty")
    with _TOPIC_INDEX_LOCK:
        if _TOPIC_INDEX_KEY != key:
            stored = data.get("_topic_index")
            if isinstance(stored, list) and stored:
                _TOPIC_INDEX = stored
            else:
                monitor = build_news_monitor(data.get("industries") or [], max_topics=10_000)
                _TOPIC_INDEX = monitor.get("topics") or []
            _TOPIC_INDEX_KEY = key
        return list(_TOPIC_INDEX)


def query_topics(
    *,
    query: str = "",
    industry: str = "all",
    signal: str = "all",
    sort: str = "attention",
    offset: int = 0,
    limit: int = 80,
) -> dict:
    data = load_cache() or skeleton()
    topics = _all_topics(data)
    industry_counts = Counter(topic.get("industry_key") or "other" for topic in topics)
    needle = query.casefold().strip()

    def matches(topic: dict) -> bool:
        if industry != "all" and topic.get("industry_key") != industry:
            return False
        if signal == "rising" and topic.get("velocity_state") not in {"new", "rising"}:
            return False
        if signal == "risk" and topic.get("signal") not in {"risk", "mixed"}:
            return False
        if signal == "opportunity" and topic.get("signal") not in {"opportunity", "mixed"}:
            return False
        if signal == "verify" and topic.get("verification_status") == "常规报道":
            return False
        if not needle:
            return True
        values = [
            topic.get("label"), topic.get("headline"), topic.get("summary"),
            topic.get("industry_name"), *(topic.get("sources") or []), *(topic.get("keywords") or []),
        ]
        for item in topic.get("items") or []:
            values.extend((item.get("zh"), item.get("title"), item.get("summary")))
        return needle in " ".join(str(value or "") for value in values).casefold()

    filtered = [topic for topic in topics if matches(topic)]
    if sort == "latest":
        filtered.sort(key=lambda topic: topic.get("latest_at") or "", reverse=True)
    else:
        filtered.sort(key=lambda topic: (topic.get("attention_score") or 0, topic.get("heat_score") or 0), reverse=True)
    start = max(0, offset)
    end = start + max(1, min(limit, 160))
    return {
        "items": filtered[start:end],
        "total": len(filtered),
        "offset": start,
        "limit": end - start,
        "industry_counts": dict(industry_counts),
        "generated_at_iso": data.get("generated_at_iso"),
    }
