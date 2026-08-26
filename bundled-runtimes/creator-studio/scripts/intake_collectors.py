#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import re
import time
import hashlib
from copy import deepcopy
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from email.utils import parsedate_to_datetime
from difflib import SequenceMatcher
from html import unescape
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlparse
from xml.etree import ElementTree as ET

import requests


DEFAULT_LOCAL_BASE = "http://127.0.0.1:8001"
DEFAULT_CHAT_DAYS = 0
DEFAULT_LOCAL_LIMIT = 120
DEFAULT_FALLBACK_LIMIT = 80
REQUEST_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0 Safari/537.36"
)

LOOPBACK_HTTP_SESSION = requests.Session()
LOOPBACK_HTTP_SESSION.trust_env = False

PUBLIC_RSS_SOURCES = {
    "reddit_local_llama": "https://www.reddit.com/r/LocalLLaMA/.rss",
    "reddit_openai": "https://www.reddit.com/r/OpenAI/.rss",
    "reddit_claudeai": "https://www.reddit.com/r/ClaudeAI/.rss",
    "reddit_singularity": "https://www.reddit.com/r/singularity/.rss",
    "hn_frontpage": "https://hnrss.org/frontpage",
    "sina_finance": "https://rss.sina.com.cn/roll/finance/hot_roll.xml",
    "wsj_world": "https://feeds.a.dj.com/rss/RSSWorldNews.xml",
}

PUBLIC_JSON_SOURCES = {
    "zhihu_hot": "https://api.zhihu.com/topstory/hot-list?limit=50",
    "toutiao_hot": "https://www.toutiao.com/hot-event/hot-board/?origin=toutiao_pc",
}

PUBLIC_HTML_SOURCES = {
    "weibo_hot": ("https://hotflashnews.com/platform/weibo", "微博热搜", "jsonld"),
    "hupu_hot": ("https://m.hupu.com/hot", "虎扑热榜", "next_data"),
    "douyin_hot": ("https://hotflashnews.com/platform/douyin", "抖音热榜", "jsonld"),
}

PUBLIC_NEWS_SOURCES = {
    "wallstreetcn-quick": ("华尔街见闻", "https://api.wallstreetcn.com/apiv1/content/lives", "cn", "finance"),
    "10jqka-stock": ("同花顺", "https://news.10jqka.com.cn/tapp/news/push/stock/", "cn", "finance"),
    "bloomberg-markets": ("彭博市场", "https://feeds.bloomberg.com/markets/news.rss", "global", "finance"),
}

KEYWORD_HINTS = (
    "新闻",
    "公众号",
    "自媒体",
    "会议",
    "投研",
    "交流",
    "财经",
    "市场",
    "基金",
    "券商",
    "固收",
    "债券",
    "国债",
    "期货",
    "股票",
    "财报",
    "路演",
    "AI",
    "agent",
    "OpenAI",
    "Claude",
    "半导体",
    "黄金",
    "白银",
    "原油",
    "美联储",
    "降息",
    "关税",
    "政策",
)

POSITIVE_TERMS = ("上涨", "增长", "突破", "回暖", "创新高", "利好", "扩张", "beat", "surge", "rise", "gain", "growth", "record")
NEGATIVE_TERMS = ("下跌", "下降", "风险", "承压", "亏损", "裁员", "调查", "制裁", "危机", "miss", "fall", "drop", "risk", "loss", "cut")
RISK_TERMS = ("监管", "制裁", "调查", "违约", "亏损", "裁员", "风险", "下跌", "crackdown", "probe", "default", "lawsuit")
OPPORTUNITY_TERMS = ("AI", "人工智能", "算力", "芯片", "新能源", "机器人", "出海", "增长", "突破", "record", "growth")


@dataclass
class CollectedItem:
    source: str
    channel: str
    title: str
    url: str
    author_name: str = ""
    created_at: str = ""
    summary: str = ""
    score: float = 0.0
    raw: dict[str, Any] = field(default_factory=dict)

    def to_payload(self) -> dict[str, Any]:
        payload = asdict(self)
        raw = payload.pop("raw", {}) or {}
        return {**raw, **payload}


@dataclass
class CollectorRun:
    tasks: dict[str, list[CollectedItem]] = field(default_factory=dict)
    status: dict[str, dict[str, Any]] = field(default_factory=dict)
    artifacts: list[str] = field(default_factory=list)

    def add_task(self, name: str, items: list[CollectedItem], status: dict[str, Any]) -> None:
        self.tasks[name] = items
        self.status[name] = {"total": len(items), **status}


def env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except Exception:
        return default


def clean_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def strip_tags(value: str) -> str:
    return clean_text(re.sub(r"<[^>]+>", "", unescape(value)))


def heat_to_float(value: Any) -> float:
    if value is None:
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    text = clean_text(value).replace(",", "")
    if not text:
        return 0.0
    match = re.search(r"[-+]?\d+(?:\.\d+)?", text)
    if not match:
        return 0.0
    number = float(match.group(0))
    if "亿" in text:
        number *= 100_000_000
    elif "万" in text:
        number *= 10_000
    return number


def news_item_id(source_id: str, title: str, url: str) -> str:
    digest = hashlib.sha1(f"{source_id}|{url}|{title}".encode("utf-8", "ignore")).hexdigest()[:16]
    return f"{source_id}:{digest}"


def news_tone(title: str) -> str:
    lower = title.lower()
    if any(term.lower() in lower or term in title for term in NEGATIVE_TERMS):
        return "negative"
    if any(term.lower() in lower or term in title for term in POSITIVE_TERMS):
        return "positive"
    return "neutral"


def news_category(title: str, default: str = "finance") -> str:
    lower = title.lower()
    if any(term in title for term in ("AI", "人工智能", "芯片", "算力", "机器人")) or any(term in lower for term in ("ai", "chip", "nvidia", "semiconductor")):
        return "technology"
    if any(term in title for term in ("央行", "利率", "通胀", "汇率", "GDP", "就业")) or any(term in lower for term in ("fed", "inflation", "rate", "gdp")):
        return "macro"
    if any(term in title for term in ("A股", "港股", "美股", "债券", "期货")) or any(term in lower for term in ("stocks", "market", "shares")):
        return "market"
    return default


def news_cluster_key(title: str) -> str:
    text = clean_text(title).lower()
    text = re.sub(r"[\d\.]+[%％]?", "", text)
    words = re.findall(r"[A-Za-z][A-Za-z0-9+.-]{2,}|[\u4e00-\u9fff]{2,6}", text)
    return "|".join(words[:4]) or text[:18]


def news_heat_score(item: dict[str, Any], *, duplicate_count: int = 1, source_count: int = 1) -> float:
    now_ms = int(time.time() * 1000)
    pub_ts = int(item.get("pub_ts") or 0)
    age_hours = max(0.0, (now_ms - pub_ts) / 3_600_000) if pub_ts else 24.0
    recency = max(0.0, 36.0 - age_hours) / 36.0 * 42.0
    source_id = str(item.get("source_id") or "")
    source_weight = {
        "wallstreetcn-quick": 18,
        "10jqka-stock": 16,
        "bloomberg-markets": 17,
    }.get(source_id, 10)
    title = str(item.get("title_original") or item.get("title") or "")
    lower = title.lower()
    signal = 0
    if any(term.lower() in lower or term in title for term in RISK_TERMS):
        signal += 10
    if any(term.lower() in lower or term in title for term in OPPORTUNITY_TERMS):
        signal += 8
    if re.search(r"\d+(?:\.\d+)?\s*%|涨停|跌停|创新高|新高|暴涨|暴跌|surge|plunge|soar|slump", title, re.I):
        signal += 8
    resonance = min(22, max(0, duplicate_count - 1) * 7 + max(0, source_count - 1) * 5)
    return round(max(0.0, min(100.0, recency + source_weight + signal + resonance)), 1)


def clip(value: Any, limit: int = 96) -> str:
    text = clean_text(value)
    return text if len(text) <= limit else text[: limit - 1] + "…"


def now_iso() -> str:
    return datetime.now().astimezone().isoformat()


def since_iso(days: int) -> str:
    return (datetime.now().astimezone() - timedelta(days=days)).isoformat()


def to_iso(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(value).astimezone().isoformat()
        except Exception:
            return ""
    text = clean_text(value)
    if not text:
        return ""
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).astimezone().isoformat()
    except Exception:
        pass
    try:
        return parsedate_to_datetime(text).astimezone().isoformat()
    except Exception:
        return text


def safe_get_json(url: str, *, timeout: int = 12, params: dict[str, Any] | None = None) -> Any:
    hostname = (urlparse(url).hostname or "").lower()
    client = LOOPBACK_HTTP_SESSION if hostname in {"127.0.0.1", "localhost", "::1"} else requests
    response = client.get(
        url,
        params=params,
        timeout=timeout,
        headers={"User-Agent": REQUEST_USER_AGENT, "Accept": "application/json,text/html,*/*", "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.7"},
    )
    response.raise_for_status()
    return response.json()


def safe_get_text(url: str, *, timeout: int = 12) -> str:
    hostname = (urlparse(url).hostname or "").lower()
    client = LOOPBACK_HTTP_SESSION if hostname in {"127.0.0.1", "localhost", "::1"} else requests
    response = client.get(
        url,
        timeout=timeout,
        headers={"User-Agent": REQUEST_USER_AGENT, "Accept": "application/rss+xml,application/xml,text/html,*/*", "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.7"},
    )
    response.raise_for_status()
    return response.text


def local_url(base: str, path: str, **params: Any) -> str:
    query = "&".join(f"{quote(str(k))}={quote(str(v))}" for k, v in params.items() if v not in (None, ""))
    return f"{base.rstrip('/')}{path}" + (f"?{query}" if query else "")


def looks_relevant(text: str) -> bool:
    lowered = text.lower()
    return any(keyword.lower() in lowered for keyword in KEYWORD_HINTS)


def message_contents(meta: dict[str, Any]) -> dict[str, Any]:
    contents = meta.get("contents")
    return contents if isinstance(contents, dict) else {}


def is_priority_local_message(row: dict[str, Any], meta: dict[str, Any], contents: dict[str, Any], text: str) -> bool:
    msg_type = clean_text(row.get("type")).lower()
    source = clean_text(meta.get("source")).lower()
    ids = " ".join(
        clean_text(value)
        for value in [
            row.get("chat_id"),
            row.get("sender_id"),
            contents.get("sourceusername"),
            contents.get("username"),
            contents.get("userName"),
        ]
    )
    if msg_type == "link" and clean_text(contents.get("url")):
        return True
    if source == "wechat_gateway":
        return True
    if any(part.startswith("gh_") for part in ids.split()):
        return True
    return looks_relevant(text)


def message_to_item(row: dict[str, Any], local_base: str) -> CollectedItem | None:
    content = clean_text(row.get("content_text") or "")
    derived = row.get("derived") if isinstance(row.get("derived"), dict) else {}
    meta = row.get("meta") if isinstance(row.get("meta"), dict) else {}
    contents = message_contents(meta)
    display_title = clean_text(
        meta.get("display_title")
        or contents.get("title")
        or derived.get("display_summary")
        or ""
    )
    if not display_title and content.lstrip().startswith("<"):
        return None
    title = display_title or clip(content, 80)
    if not title or len(title) < 4:
        return None
    summary_parts = [
        clean_text(derived.get("key_info") or derived.get("summary") or ""),
        clean_text(contents.get("desc") or contents.get("description") or ""),
        clean_text(row.get("talker_name") or row.get("chat_id") or ""),
        clean_text(contents.get("sourcedisplayname") or row.get("sender_name") or row.get("sender_id") or ""),
    ]
    summary = "｜".join(part for part in summary_parts if part)
    if not is_priority_local_message(row, meta, contents, f"{title} {summary} {content}"):
        return None
    msg_id = row.get("id")
    url = clean_text(contents.get("url") or row.get("media_url") or "")
    if not url:
        url = f"dasheng-local://messages/{msg_id}" if msg_id else local_base
    return CollectedItem(
        source="local_chat/messages",
        channel="local_chat",
        title=title,
        url=url,
        author_name=clean_text(contents.get("sourcedisplayname") or row.get("talker_name") or row.get("sender_name") or "本地聊天"),
        created_at=to_iso(row.get("timestamp")),
        summary=summary or clip(content, 120),
        score=heat_to_float(row.get("importance_score")),
        raw={
            "message_id": msg_id,
            "chat_id": row.get("chat_id"),
            "type": row.get("type"),
            "sender_id": row.get("sender_id"),
            "talker_name": row.get("talker_name"),
        },
    )


def news_to_item(row: dict[str, Any], local_base: str) -> CollectedItem | None:
    title = clean_text(row.get("title") or row.get("name") or "")
    if not title:
        return None
    url = clean_text(row.get("url") or row.get("link") or "")
    item_id = row.get("id")
    if not url and item_id:
        url = f"dasheng-local://news/{item_id}"
    if not url:
        url = local_base
    return CollectedItem(
        source="local_news/8001",
        channel="local_news",
        title=title,
        url=url,
        author_name=clean_text(row.get("source_name") or row.get("source_id") or "8001新闻流"),
        created_at=to_iso(row.get("pub_ts") or row.get("created_at") or row.get("time")),
        summary=clean_text(row.get("summary") or row.get("desc") or "本地新闻流"),
        score=heat_to_float(row.get("score") or row.get("hot_score")),
        raw=row,
    )


def mp_article_to_item(row: dict[str, Any], local_base: str) -> CollectedItem | None:
    title = clean_text(row.get("title") or "")
    if not title:
        return None
    item_id = clean_text(row.get("id") or row.get("message_id") or "")
    url = clean_text(row.get("url") or "")
    if not url and item_id:
        url = f"dasheng-local://mp/{quote(item_id)}"
    if not url:
        url = f"{local_base}/api/mp/articles"
    return CollectedItem(
        source="local_mp/8001",
        channel="wechat",
        title=title,
        url=url,
        author_name=clean_text(row.get("channel_name") or row.get("mp_name") or "公众号"),
        created_at=to_iso(row.get("publish_time") or row.get("created_at") or row.get("time")),
        summary=clean_text(row.get("summary") or row.get("description") or row.get("content") or title),
        score=heat_to_float(
            row.get("heat")
            or row.get("read_count")
            or row.get("recommend_count")
            or row.get("like_count")
        ),
        raw=row,
    )


def media_item_to_item(row: dict[str, Any], local_base: str) -> CollectedItem | None:
    title = clean_text(row.get("title") or row.get("description") or "")
    if not title:
        return None
    item_id = clean_text(row.get("id") or "")
    url = clean_text(row.get("url") or row.get("link") or "")
    if not url and item_id:
        url = f"dasheng-local://media/{quote(item_id)}"
    if not url:
        url = f"{local_base}/api/media/items"
    stats = row.get("stats") if isinstance(row.get("stats"), dict) else {}
    platform = clean_text(row.get("platform") or stats.get("source_name") or "self_media")
    return CollectedItem(
        source=f"local_media/{platform or '8001'}",
        channel="content_research",
        title=title,
        url=url,
        author_name=clean_text(row.get("author") or row.get("nickname") or platform or "自媒体"),
        created_at=to_iso(row.get("time") or row.get("created_at") or row.get("publish_time")),
        summary=clean_text(row.get("summary") or row.get("description") or title),
        score=heat_to_float(
            row.get("heat")
            or stats.get("heat")
            or stats.get("like")
            or stats.get("collect")
            or stats.get("share")
        ),
        raw=row,
    )


def normalize_news_title(value: str) -> str:
    return re.sub(r"[^a-z0-9\u4e00-\u9fff]+", "", clean_text(value).lower())


def canonical_news_url(value: str) -> str:
    url = clean_text(value)
    if not url.startswith(("http://", "https://")):
        return ""
    return url.split("#", 1)[0].split("?", 1)[0].rstrip("/")


def news_source_identity(item: CollectedItem) -> str:
    source_id = clean_text(item.raw.get("source_id") or "")
    item_id = clean_text(item.raw.get("id") or "")
    return f"{source_id}:{item_id}" if source_id and item_id else ""


def news_items_match(left: CollectedItem, right: CollectedItem) -> bool:
    left_identity = news_source_identity(left)
    right_identity = news_source_identity(right)
    if left_identity and left_identity == right_identity:
        return True

    left_url = canonical_news_url(left.url)
    right_url = canonical_news_url(right.url)
    if left_url and left_url == right_url:
        return True

    left_title = normalize_news_title(left.title)
    right_title = normalize_news_title(right.title)
    if not left_title or not right_title:
        return False
    if left_title == right_title:
        return True

    shorter, longer = sorted((left_title, right_title), key=len)
    if len(shorter) < 24:
        return False
    if shorter in longer and len(shorter) / max(len(longer), 1) >= 0.82:
        return True
    return SequenceMatcher(None, left_title, right_title).ratio() >= 0.93


def news_item_quality(item: CollectedItem) -> tuple[float, float, int, int]:
    return (
        1.0 if canonical_news_url(item.url) else 0.0,
        float(item.score or 0.0),
        1 if item.created_at else 0,
        len(clean_text(item.summary)),
    )


def news_source_ref(item: CollectedItem) -> dict[str, Any]:
    return {
        "source": item.source,
        "source_id": clean_text(item.raw.get("source_id") or ""),
        "item_id": clean_text(item.raw.get("id") or ""),
        "title": item.title,
        "url": item.url,
        "author_name": item.author_name,
        "created_at": item.created_at,
        "score": item.score,
    }


def merge_news_items(*groups: list[CollectedItem]) -> list[CollectedItem]:
    candidates = [item for group in groups for item in group]
    candidates.sort(key=news_item_quality, reverse=True)
    merged: list[CollectedItem] = []

    for candidate in candidates:
        existing = next((item for item in merged if news_items_match(item, candidate)), None)
        if existing is None:
            cloned = deepcopy(candidate)
            cloned.channel = "news"
            cloned.raw = {
                **cloned.raw,
                "merged_sources": [news_source_ref(candidate)],
                "merged_count": 1,
                "merged_channel": "news",
            }
            merged.append(cloned)
            continue

        refs = existing.raw.setdefault("merged_sources", [])
        ref = news_source_ref(candidate)
        ref_key = (ref["source"], ref["item_id"], ref["url"])
        if ref_key not in {(row.get("source"), row.get("item_id"), row.get("url")) for row in refs}:
            refs.append(ref)
        existing.raw["merged_count"] = len(refs)
        existing.score = max(float(existing.score or 0.0), float(candidate.score or 0.0))
        if not existing.created_at and candidate.created_at:
            existing.created_at = candidate.created_at
        if len(clean_text(candidate.summary)) > len(clean_text(existing.summary)):
            existing.summary = candidate.summary

    return merged


def collect_local_service(raw_dir: Path) -> CollectorRun:
    base = os.getenv("DASHENG_LOCAL_CHAT_INTAKE_BASE", DEFAULT_LOCAL_BASE).rstrip("/")
    days = env_int("DASHENG_LOCAL_CHAT_DAYS", DEFAULT_CHAT_DAYS)
    limit = env_int("DASHENG_LOCAL_CHAT_LIMIT", DEFAULT_LOCAL_LIMIT)
    mp_limit = env_int("DASHENG_LOCAL_MP_LIMIT", 200)
    media_limit = env_int("DASHENG_LOCAL_MEDIA_LIMIT", 300)
    run = CollectorRun()

    try:
        health = safe_get_json(f"{base}/api/health", timeout=5)
        (raw_dir / "local_chat_health.json").write_text(json.dumps(health, ensure_ascii=False, indent=2), encoding="utf-8")
        run.artifacts.append("raw/local_chat_health.json")
    except Exception as exc:
        run.status["local_health"] = {"status": "error", "base": base, "error": str(exc)}
        return run

    try:
        chats = safe_get_json(f"{base}/api/chats", timeout=8)
        (raw_dir / "local_chats.json").write_text(json.dumps(chats, ensure_ascii=False, indent=2), encoding="utf-8")
        run.artifacts.append("raw/local_chats.json")
    except Exception as exc:
        chats = []
        run.status["local_chats"] = {"status": "error", "base": base, "error": str(exc)}

    try:
        message_params = {
            "size": limit,
            "fast": "true",
            "include_meta": "true",
            "include_mp_messages": "false",
            "content_max_chars": 1200,
            "direction": "in",
        }
        if days > 0:
            message_params["time_from"] = since_iso(days)
        messages = safe_get_json(
            f"{base}/api/messages",
            timeout=25,
            params=message_params,
        )
        (raw_dir / "local_messages.json").write_text(json.dumps(messages, ensure_ascii=False, indent=2), encoding="utf-8")
        rows = messages.get("items") if isinstance(messages, dict) else []
        items = [item for row in rows or [] if isinstance(row, dict) for item in [message_to_item(row, base)] if item]
        run.add_task(
            "local_chat",
            items[:limit],
            {"status": "ready", "base": base, "chats_total": len(chats) if isinstance(chats, list) else 0},
        )
        run.artifacts.append("raw/local_messages.json")
    except Exception as exc:
        run.add_task("local_chat", [], {"status": "error", "base": base, "error": str(exc)})

    try:
        mp_articles = safe_get_json(
            f"{base}/api/mp/articles",
            timeout=30,
            params={"limit": mp_limit, "offset": 0, "filter_spam": "true"},
        )
        (raw_dir / "local_mp_articles.json").write_text(
            json.dumps(mp_articles, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        rows = mp_articles.get("items") if isinstance(mp_articles, dict) else []
        items = [
            item
            for row in rows or []
            if isinstance(row, dict)
            for item in [mp_article_to_item(row, base)]
            if item
        ]
        run.add_task(
            "wechat",
            items[:mp_limit],
            {
                "status": "ready" if items else "empty",
                "base": base,
                "endpoint": "/api/mp/articles",
                "upstream": mp_articles.get("source", {}) if isinstance(mp_articles, dict) else {},
            },
        )
        run.artifacts.append("raw/local_mp_articles.json")
    except Exception as exc:
        run.add_task("wechat", [], {"status": "error", "base": base, "error": str(exc)})

    try:
        media_items = safe_get_json(
            f"{base}/api/media/items",
            timeout=45,
            params={"limit": media_limit, "filter_noise": "true"},
        )
        (raw_dir / "local_media_items.json").write_text(
            json.dumps(media_items, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        rows = media_items.get("items") if isinstance(media_items, dict) else []
        items = [
            item
            for row in rows or []
            if isinstance(row, dict)
            for item in [media_item_to_item(row, base)]
            if item
        ]
        run.add_task(
            "content_research",
            items[:media_limit],
            {
                "status": "ready" if items else "empty",
                "base": base,
                "endpoint": "/api/media/items",
                "upstream": media_items.get("source", {}) if isinstance(media_items, dict) else {},
            },
        )
        run.artifacts.append("raw/local_media_items.json")
    except Exception as exc:
        run.add_task("content_research", [], {"status": "error", "base": base, "error": str(exc)})

    try:
        news = safe_get_json(f"{base}/api/newsfeed/items", timeout=25, params={"limit": limit})
        (raw_dir / "local_newsfeed.json").write_text(json.dumps(news, ensure_ascii=False, indent=2), encoding="utf-8")
        rows = news.get("items") if isinstance(news, dict) else []
        items = [item for row in rows or [] if isinstance(row, dict) for item in [news_to_item(row, base)] if item]
        run.add_task("local_news", items[:limit], {"status": "ready", "base": base})
        run.artifacts.append("raw/local_newsfeed.json")
    except Exception as exc:
        run.add_task("local_news", [], {"status": "error", "base": base, "error": str(exc)})

    return run


def parse_atom_or_rss(xml_text: str, source_name: str, channel: str, limit: int) -> list[CollectedItem]:
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return []
    items: list[CollectedItem] = []
    atom_ns = {"atom": "http://www.w3.org/2005/Atom"}
    for entry in root.findall("atom:entry", atom_ns):
        title = clean_text(entry.findtext("atom:title", default="", namespaces=atom_ns))
        link = ""
        for node in entry.findall("atom:link", atom_ns):
            link = clean_text(node.attrib.get("href", ""))
            if link:
                break
        created = clean_text(entry.findtext("atom:updated", default="", namespaces=atom_ns))
        author = clean_text(entry.findtext("atom:author/atom:name", default="", namespaces=atom_ns))
        if title and link:
            items.append(CollectedItem(source=f"public/{source_name}", channel=channel, title=title, url=link, author_name=author or source_name, created_at=to_iso(created), summary=f"{source_name} RSS"))
        if len(items) >= limit:
            return items
    for entry in root.findall(".//item"):
        title = clean_text(entry.findtext("title", default=""))
        link = clean_text(entry.findtext("link", default=""))
        created = clean_text(entry.findtext("pubDate", default=""))
        if title and link:
            items.append(CollectedItem(source=f"public/{source_name}", channel=channel, title=title, url=link, author_name=source_name, created_at=to_iso(created), summary=f"{source_name} RSS"))
        if len(items) >= limit:
            break
    return items


def zhihu_public_url(target: dict[str, Any]) -> str:
    question_id = target.get("id")
    if question_id:
        return f"https://www.zhihu.com/question/{question_id}"
    url = clean_text(target.get("url") or target.get("link"))
    match = re.search(r"/questions/(\d+)", url)
    if match:
        return f"https://www.zhihu.com/question/{match.group(1)}"
    return url


def parse_tophub_html(html_text: str, source_name: str, label: str, limit: int) -> list[CollectedItem]:
    items: list[CollectedItem] = []
    for row in re.findall(r"<tr\b[^>]*>(.*?)</tr>", html_text, flags=re.S | re.I):
        link_match = re.search(r'<a\b[^>]*href="([^"]+)"[^>]*>(.*?)</a>', row, flags=re.S | re.I)
        if not link_match:
            continue
        title = strip_tags(link_match.group(2))
        url = clean_text(unescape(link_match.group(1)))
        score_match = re.search(r'<td\b[^>]*class="ws"[^>]*>(.*?)</td>', row, flags=re.S | re.I)
        score = heat_to_float(strip_tags(score_match.group(1)) if score_match else 0)
        if title and url:
            items.append(
                CollectedItem(
                    source=f"public/{source_name}",
                    channel="public_hot",
                    title=title,
                    url=url,
                    author_name=label,
                    created_at=now_iso(),
                    summary=f"{label}公开热榜",
                    score=score,
                )
            )
        if len(items) >= limit:
            break
    return items


def parse_jsonld_hot_html(html_text: str, source_name: str, label: str, limit: int) -> list[CollectedItem]:
    items: list[CollectedItem] = []
    scripts = re.findall(r'<script\b[^>]*type="application/ld\+json"[^>]*>(.*?)</script>', html_text, flags=re.S | re.I)
    for script in scripts:
        try:
            payload = json.loads(unescape(script).strip())
        except Exception:
            continue
        entity = payload.get("mainEntity") if isinstance(payload, dict) else {}
        rows = entity.get("itemListElement") if isinstance(entity, dict) else []
        if not isinstance(rows, list):
            continue
        for row in rows[:limit]:
            if not isinstance(row, dict):
                continue
            title = clean_text(row.get("name"))
            url = clean_text(row.get("url"))
            position = heat_to_float(row.get("position"))
            if title and url:
                items.append(
                    CollectedItem(
                        source=f"public/{source_name}",
                        channel="public_hot",
                        title=title,
                        url=url,
                        author_name=label,
                        created_at=now_iso(),
                        summary=f"{label}公开热榜",
                        score=max(1.0, limit - position + 1.0) if position else 0.0,
                        raw=row,
                    )
                )
        if items:
            break
    return items


def parse_next_data_hot_html(html_text: str, source_name: str, label: str, limit: int) -> list[CollectedItem]:
    match = re.search(r'<script\b[^>]*id="__NEXT_DATA__"[^>]*>(.*?)</script>', html_text, flags=re.S | re.I)
    if not match:
        return []
    try:
        payload = json.loads(unescape(match.group(1)).strip())
    except Exception:
        return []
    rows = (((payload.get("props") or {}).get("pageProps") or {}).get("res") or [])
    if not isinstance(rows, list):
        return []
    items: list[CollectedItem] = []
    for row in rows[:limit]:
        if not isinstance(row, dict):
            continue
        title = clean_text(row.get("tagName") or row.get("title") or row.get("name"))
        tag_id = clean_text(row.get("tagId"))
        url = f"https://m.hupu.com/hot/{tag_id}" if tag_id else "https://m.hupu.com/hot"
        if title:
            items.append(
                CollectedItem(
                    source=f"public/{source_name}",
                    channel="public_hot",
                    title=title,
                    url=url,
                    author_name=label,
                    created_at=now_iso(),
                    summary=f"{label}公开热榜",
                    score=heat_to_float(row.get("heat")),
                    raw=row,
                )
            )
    return items


def parse_html_hot_items(html_text: str, source_name: str, label: str, parser: str, limit: int) -> list[CollectedItem]:
    if parser == "jsonld":
        return parse_jsonld_hot_html(html_text, source_name, label, limit)
    if parser == "next_data":
        return parse_next_data_hot_html(html_text, source_name, label, limit)
    return parse_tophub_html(html_text, source_name, label, limit)


def fetch_wallstreetcn_news(limit: int) -> list[dict[str, Any]]:
    name, url, region, default_category = PUBLIC_NEWS_SOURCES["wallstreetcn-quick"]
    payload = safe_get_json(url, timeout=10, params={"channel": "global", "limit": max(limit, 50)})
    rows: list[dict[str, Any]] = []
    for live in ((payload.get("data") or {}).get("items") or [])[:limit]:
        if not isinstance(live, dict):
            continue
        content = strip_tags(str(live.get("content") or ""))
        if not content:
            continue
        title = clip(content, 180)
        raw_ts = live.get("display_time") or live.get("created_at") or live.get("updated_at") or 0
        pub_ts = heat_to_float(raw_ts)
        if pub_ts and pub_ts < 10_000_000_000:
            pub_ts *= 1000
        article = live.get("article") if isinstance(live.get("article"), dict) else {}
        item_url = clean_text(article.get("uri") or article.get("resource") or "")
        category = news_category(title, default_category)
        tone = news_tone(title)
        rows.append(
            {
                "id": str(live.get("id") or news_item_id("wallstreetcn-quick", title, item_url)),
                "source_id": "wallstreetcn-quick",
                "source_name": name,
                "title": title,
                "url": item_url,
                "pub_ts": int(pub_ts or time.time() * 1000),
                "region": region,
                "category": category,
                "summary": content,
                "derived": {"key_info": title[:160], "category": category, "tone": tone, "summary_origin": "public_news_fallback"},
                "raw": live,
            }
        )
    return rows


def fetch_10jqka_news(limit: int) -> list[dict[str, Any]]:
    name, url, region, default_category = PUBLIC_NEWS_SOURCES["10jqka-stock"]
    payload = safe_get_json(url, timeout=10, params={"page": 1, "tag": "", "track": "website", "pagesize": max(limit, 50)})
    rows: list[dict[str, Any]] = []
    for item in (((payload.get("data") or {}).get("list")) or [])[:limit]:
        if not isinstance(item, dict):
            continue
        title = strip_tags(str(item.get("title") or item.get("digest") or ""))
        if not title:
            continue
        digest = strip_tags(str(item.get("digest") or ""))
        item_url = clean_text(item.get("url") or item.get("link") or "")
        raw_ts = item.get("ctime") or item.get("time") or item.get("rtime") or 0
        pub_ts = heat_to_float(raw_ts)
        if pub_ts and pub_ts < 10_000_000_000:
            pub_ts *= 1000
        category = news_category(title, default_category)
        tone = news_tone(title)
        rows.append(
            {
                "id": str(item.get("id") or item.get("seq") or news_item_id("10jqka-stock", title, item_url)),
                "source_id": "10jqka-stock",
                "source_name": name,
                "title": title,
                "url": item_url,
                "pub_ts": int(pub_ts or time.time() * 1000),
                "region": region,
                "category": category,
                "summary": digest,
                "derived": {"key_info": title[:160], "category": category, "tone": tone, "summary_origin": "public_news_fallback"},
                "raw": item,
            }
        )
    return rows


def fetch_rss_news(source_id: str, limit: int) -> list[dict[str, Any]]:
    name, url, region, default_category = PUBLIC_NEWS_SOURCES[source_id]
    xml_text = safe_get_text(url, timeout=10)
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return []
    rows: list[dict[str, Any]] = []

    def append_item(title: str, item_url: str, pub: str, summary: str = "") -> None:
        title = strip_tags(title)
        item_url = clean_text(item_url)
        if not title or not item_url:
            return
        parsed_dt = parse_datetime_text(pub)
        pub_ts = int(parsed_dt.timestamp() * 1000) if parsed_dt else int(time.time() * 1000)
        category = news_category(title, default_category)
        tone = news_tone(title)
        rows.append(
            {
                "id": news_item_id(source_id, title, item_url),
                "source_id": source_id,
                "source_name": name,
                "title": title,
                "url": item_url,
                "pub_ts": pub_ts,
                "region": region,
                "category": category,
                "summary": strip_tags(summary),
                "derived": {"key_info": title[:160], "category": category, "tone": tone, "summary_origin": "public_news_fallback"},
            }
        )

    for item in root.findall(".//item"):
        append_item(
            item.findtext("title", default=""),
            item.findtext("link", default=""),
            item.findtext("pubDate", default=""),
            item.findtext("description", default=""),
        )
        if len(rows) >= limit:
            break
    atom_ns = {"atom": "http://www.w3.org/2005/Atom"}
    for entry in root.findall("atom:entry", atom_ns):
        link = ""
        for node in entry.findall("atom:link", atom_ns):
            link = clean_text(node.attrib.get("href", ""))
            if link:
                break
        append_item(
            entry.findtext("atom:title", default="", namespaces=atom_ns),
            link,
            entry.findtext("atom:updated", default="", namespaces=atom_ns) or entry.findtext("atom:published", default="", namespaces=atom_ns),
            entry.findtext("atom:summary", default="", namespaces=atom_ns),
        )
        if len(rows) >= limit:
            break
    return rows[:limit]


def parse_datetime_text(value: Any) -> datetime | None:
    text = clean_text(value)
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).astimezone()
    except Exception:
        pass
    try:
        return parsedate_to_datetime(text).astimezone()
    except Exception:
        return None


def fetch_public_news_rows(per_source_limit: int) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    source_status: dict[str, Any] = {}
    fetchers = {
        "wallstreetcn-quick": fetch_wallstreetcn_news,
        "10jqka-stock": fetch_10jqka_news,
        "bloomberg-markets": lambda limit: fetch_rss_news("bloomberg-markets", limit),
    }
    for source_id, fetcher in fetchers.items():
        try:
            parsed = fetcher(per_source_limit)
            rows.extend(parsed)
            source_status[source_id] = {"status": "ready", "total": len(parsed)}
        except Exception as exc:
            source_status[source_id] = {"status": "error", "error": str(exc)}
    return rows, source_status


def public_news_items(rows: list[dict[str, Any]], total_limit: int) -> list[CollectedItem]:
    cluster_counts: dict[str, int] = {}
    cluster_sources: dict[str, set[str]] = {}
    for row in rows:
        key = news_cluster_key(str(row.get("title") or ""))
        cluster_counts[key] = cluster_counts.get(key, 0) + 1
        cluster_sources.setdefault(key, set()).add(str(row.get("source_id") or ""))

    deduped: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in rows:
        key = clean_text(row.get("url")) or clean_text(row.get("id")) or clean_text(row.get("title"))
        if not key or key in seen:
            continue
        seen.add(key)
        cluster = news_cluster_key(str(row.get("title") or ""))
        row["heat_cluster"] = cluster
        row["heat_score"] = news_heat_score(
            row,
            duplicate_count=cluster_counts.get(cluster, 1),
            source_count=len(cluster_sources.get(cluster, set())),
        )
        deduped.append(row)

    deduped.sort(key=lambda item: (float(item.get("heat_score") or 0), int(item.get("pub_ts") or 0)), reverse=True)
    items: list[CollectedItem] = []
    for row in deduped[:total_limit]:
        derived = row.get("derived") if isinstance(row.get("derived"), dict) else {}
        tone = clean_text(derived.get("tone") or "neutral")
        category = clean_text(row.get("category") or derived.get("category") or "finance")
        items.append(
            CollectedItem(
                source=f"public_news/{row.get('source_id') or 'unknown'}",
                channel="public_news",
                title=clean_text(row.get("title")),
                url=clean_text(row.get("url") or f"dasheng-public-news://{row.get('id')}"),
                author_name=clean_text(row.get("source_name") or "公开新闻兜底"),
                created_at=to_iso((int(row.get("pub_ts") or 0) / 1000) if row.get("pub_ts") else None),
                summary=clean_text(row.get("summary") or derived.get("key_info") or f"{category}/{tone}"),
                score=heat_to_float(row.get("heat_score")),
                raw={**row, "tone": tone, "category": category},
            )
        )
    return items


def collect_public_news_fallback(raw_dir: Path) -> CollectorRun:
    per_source_limit = env_int("DASHENG_PUBLIC_NEWS_PER_SOURCE", 50)
    total_limit = env_int("DASHENG_PUBLIC_NEWS_LIMIT", DEFAULT_FALLBACK_LIMIT)
    run = CollectorRun()
    rows, source_status = fetch_public_news_rows(per_source_limit)
    items = public_news_items(rows, total_limit)
    payload = {
        "generated_at": now_iso(),
        "sources": source_status,
        "items": [item.to_payload() for item in items],
    }
    (raw_dir / "public_news_fallback_items.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    run.artifacts.append("raw/public_news_fallback_items.json")
    run.add_task("public_news", items, {"status": "ready" if items else "empty", "sources": source_status})
    return run


def json_hot_items(payload: Any, source_name: str, limit: int) -> list[CollectedItem]:
    rows: list[Any] = []
    if source_name == "weibo_hot" and isinstance(payload, dict):
        rows = ((payload.get("data") or {}).get("realtime") or [])[:limit]
        return [
            CollectedItem(
                source="public/weibo_hot",
                channel="public_hot",
                title=clean_text(row.get("word") or row.get("note")),
                url="https://s.weibo.com/weibo?q=" + quote(clean_text(row.get("word") or row.get("note"))),
                author_name="微博热搜",
                created_at=now_iso(),
                summary="微博公开热搜",
                score=heat_to_float(row.get("num") or row.get("raw_hot")),
                raw=row,
            )
            for row in rows
            if isinstance(row, dict) and clean_text(row.get("word") or row.get("note"))
        ]
    if source_name == "zhihu_hot" and isinstance(payload, dict):
        rows = (payload.get("data") or [])[:limit]
        out = []
        for row in rows:
            target = row.get("target") if isinstance(row, dict) else {}
            if not isinstance(target, dict):
                continue
            title = clean_text(target.get("title"))
            url = zhihu_public_url(target)
            if title and url:
                out.append(CollectedItem(source="public/zhihu_hot", channel="public_hot", title=title, url=url, author_name="知乎热榜", created_at=now_iso(), summary="知乎公开热榜", score=heat_to_float(row.get("detail_text")), raw=row))
        return out
    if source_name == "toutiao_hot" and isinstance(payload, dict):
        rows = (payload.get("data") or [])[:limit]
        return [
            CollectedItem(
                source="public/toutiao_hot",
                channel="public_hot",
                title=clean_text(row.get("Title") or row.get("title")),
                url=clean_text(row.get("Url") or row.get("url") or "https://www.toutiao.com/"),
                author_name="头条热榜",
                created_at=now_iso(),
                summary="头条公开热榜",
                score=heat_to_float(row.get("HotValue") or row.get("hotValue")),
                raw=row,
            )
            for row in rows
            if isinstance(row, dict) and clean_text(row.get("Title") or row.get("title"))
        ]
    return []


def collect_public_fallback(raw_dir: Path) -> CollectorRun:
    per_source_limit = env_int("DASHENG_PUBLIC_FALLBACK_PER_SOURCE", 12)
    total_limit = env_int("DASHENG_PUBLIC_FALLBACK_LIMIT", DEFAULT_FALLBACK_LIMIT)
    run = CollectorRun()
    items: list[CollectedItem] = []
    source_status: dict[str, Any] = {}

    for name, url in PUBLIC_RSS_SOURCES.items():
        try:
            xml_text = safe_get_text(url, timeout=10)
            parsed = parse_atom_or_rss(xml_text, name, "public_hot", per_source_limit)
            items.extend(parsed)
            source_status[name] = {"status": "ready", "total": len(parsed)}
        except Exception as exc:
            source_status[name] = {"status": "error", "error": str(exc)}

    for name, url in PUBLIC_JSON_SOURCES.items():
        try:
            payload = safe_get_json(url, timeout=10)
            parsed = json_hot_items(payload, name, per_source_limit)
            items.extend(parsed)
            source_status[name] = {"status": "ready", "total": len(parsed)}
        except Exception as exc:
            source_status[name] = {"status": "error", "error": str(exc)}

    for name, (url, label, parser) in PUBLIC_HTML_SOURCES.items():
        try:
            html_text = safe_get_text(url, timeout=10)
            parsed = parse_html_hot_items(html_text, name, label, parser, per_source_limit)
            items.extend(parsed)
            source_status[name] = {"status": "ready", "total": len(parsed)}
        except Exception as exc:
            source_status[name] = {"status": "error", "error": str(exc)}

    payload = {
        "generated_at": now_iso(),
        "sources": source_status,
        "items": [item.to_payload() for item in items[:total_limit]],
    }
    (raw_dir / "public_fallback_items.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    run.artifacts.append("raw/public_fallback_items.json")
    run.add_task("public_hot", items[:total_limit], {"status": "ready" if items else "empty", "sources": source_status})
    return run


def collect_simple_intake(raw_dir: Path) -> CollectorRun:
    raw_dir.mkdir(parents=True, exist_ok=True)
    local_run = collect_local_service(raw_dir)
    from hotspot_radar import collect_hotspot_radar

    hotspot_run = collect_hotspot_radar(raw_dir)
    merged = CollectorRun()
    for name, items in {**local_run.tasks, **hotspot_run.tasks}.items():
        status = local_run.status.get(name) or hotspot_run.status.get(name) or {"status": "ready"}
        merged.add_task(name, items, status)
    merged.status = {**local_run.status, **hotspot_run.status, **merged.status}
    merged.artifacts = [*local_run.artifacts, *hotspot_run.artifacts]
    return merged
