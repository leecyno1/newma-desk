#!/usr/bin/env python3
"""B站关键词搜索 — 按综合热度排序"""
import json, sys, argparse, urllib.parse
from datetime import datetime, timezone, timedelta
from urllib.request import Request, urlopen
from urllib.error import URLError

TZ = timezone(timedelta(hours=8))
API = "https://api.bilibili.com/x/web-interface/search/type"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    "Referer": "https://www.bilibili.com",
}

def search(keyword: str, limit: int = 20, order: str = "totalrank") -> dict:
    """totalrank=综合排序, click=最多播放, pubdate=最新"""
    params = urllib.parse.urlencode({
        "keyword": keyword,
        "search_type": "video",
        "order": order,
        "page": 1,
    })
    try:
        req = Request(f"{API}?{params}", headers=HEADERS)
        resp = urlopen(req, timeout=10)
        data = json.loads(resp.read())
    except (URLError, json.JSONDecodeError) as e:
        return {"error": str(e), "platform": "bilibili-search"}

    if data.get("code") != 0:
        return {"error": data.get("message", "unknown"), "platform": "bilibili-search"}

    raw = data.get("data", {}).get("result", [])
    items = []
    import re as _re
    for i, v in enumerate(raw[:limit]):
        title = _re.sub(r"<[^>]+>", "", v.get("title", ""))
        items.append({
            "rank": i + 1,
            "title": title,
            "url": f"https://www.bilibili.com/video/{v.get('bvid', '')}",
            "heat": v.get("play", 0),  # 播放量作为热度
            "description": v.get("description", "")[:200],
            "extra": {
                "author": v.get("author", ""),
                "views": v.get("play", 0),
                "danmaku": v.get("video_review", 0),
                "favorites": v.get("favorites", 0),
                "duration": v.get("duration", ""),
                "pubdate": v.get("pubdate", 0),
            },
        })
    return {
        "platform": "bilibili-search",
        "keyword": keyword,
        "order": order,
        "fetched_at": datetime.now(TZ).isoformat(),
        "count": len(items),
        "items": items,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="B站关键词搜索")
    parser.add_argument("keyword", help="搜索关键词")
    parser.add_argument("--limit", "-n", type=int, default=20)
    parser.add_argument("--order", "-o", default="totalrank",
                        choices=["totalrank", "click", "pubdate", "dm"])
    parser.add_argument("--pretty", action="store_true")
    args = parser.parse_args()
    result = search(args.keyword, args.limit, args.order)
    indent = 2 if args.pretty else None
    print(json.dumps(result, ensure_ascii=False, indent=indent))
    sys.exit(1 if "error" in result else 0)
