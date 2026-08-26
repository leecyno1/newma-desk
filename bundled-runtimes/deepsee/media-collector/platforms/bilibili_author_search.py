#!/usr/bin/env python3
"""B站作者搜索 — 按作者名检索视频，输出统一 collector JSON。"""
from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.parse
from datetime import datetime, timezone, timedelta
from urllib.request import Request, urlopen
from urllib.error import URLError

TZ = timezone(timedelta(hours=8))
API = "https://api.bilibili.com/x/web-interface/search/type"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    "Referer": "https://www.bilibili.com",
}


def _clean(s: str) -> str:
    return re.sub(r"<[^>]+>", "", str(s or "")).strip()


def search_author(author: str, limit: int = 20, order: str = "pubdate") -> dict:
    # B站没有稳定免认证的“按作者精确拉视频”统一接口；轻量方案用作者名搜索视频，
    # 再优先保留 author 字段命中的结果，未命中时保留搜索结果避免作者名变体导致空集。
    params = urllib.parse.urlencode({
        "keyword": author,
        "search_type": "video",
        "order": order,
        "page": 1,
    })
    try:
        req = Request(f"{API}?{params}", headers=HEADERS)
        data = json.loads(urlopen(req, timeout=10).read())
    except (URLError, TimeoutError, json.JSONDecodeError) as e:
        return {"error": str(e), "platform": "bilibili-author", "author_query": author, "count": 0, "items": []}

    if data.get("code") != 0:
        return {"error": data.get("message", "unknown"), "platform": "bilibili-author", "author_query": author, "count": 0, "items": []}

    raw = data.get("data", {}).get("result", []) or []
    exact = []
    fuzzy = []
    for v in raw:
        item_author = _clean(v.get("author", ""))
        bucket = exact if (author in item_author or item_author in author) else fuzzy
        bucket.append(v)
    chosen = (exact + fuzzy)[:limit]

    items = []
    for i, v in enumerate(chosen):
        item_author = _clean(v.get("author", ""))
        title = _clean(v.get("title", ""))
        bvid = v.get("bvid", "")
        items.append({
            "rank": i + 1,
            "title": title,
            "url": f"https://www.bilibili.com/video/{bvid}" if bvid else "",
            "heat": v.get("play", 0) or 0,
            "description": _clean(v.get("description", ""))[:240],
            "extra": {
                "author": item_author,
                "author_query": author,
                "views": v.get("play", 0) or 0,
                "danmaku": v.get("video_review", 0) or 0,
                "favorites": v.get("favorites", 0) or 0,
                "duration": v.get("duration", ""),
                "pubdate": v.get("pubdate", 0) or 0,
                "match": "exact" if v in exact else "fuzzy",
            },
        })

    return {
        "platform": "bilibili-author",
        "author_query": author,
        "keyword": author,
        "search_type": "author",
        "order": order,
        "fetched_at": datetime.now(TZ).isoformat(),
        "count": len(items),
        "items": items,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="B站作者搜索")
    parser.add_argument("author", help="作者/博主名称")
    parser.add_argument("--limit", "-n", type=int, default=20)
    parser.add_argument("--order", "-o", default="pubdate", choices=["totalrank", "click", "pubdate", "dm"])
    parser.add_argument("--pretty", action="store_true")
    args = parser.parse_args()
    result = search_author(args.author, args.limit, args.order)
    print(json.dumps(result, ensure_ascii=False, indent=2 if args.pretty else None))
    sys.exit(1 if result.get("error") else 0)
