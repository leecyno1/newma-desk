#!/usr/bin/env python3
"""B站热门采集 — 零认证，公开API"""
import json, sys, argparse
from datetime import datetime, timezone, timedelta
from urllib.request import Request, urlopen
from urllib.error import URLError

TZ = timezone(timedelta(hours=8))
API = "https://api.bilibili.com/x/web-interface/popular"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    "Referer": "https://www.bilibili.com",
}

def fetch(limit: int = 20) -> dict:
    try:
        req = Request(f"{API}?ps={limit}", headers=HEADERS)
        resp = urlopen(req, timeout=10)
        data = json.loads(resp.read())
    except (URLError, json.JSONDecodeError) as e:
        return {"error": str(e), "platform": "bilibili"}

    if data.get("code") != 0:
        return {"error": data.get("message", "unknown"), "platform": "bilibili"}

    items = []
    for i, v in enumerate(data["data"]["list"]):
        items.append({
            "rank": i + 1,
            "title": v["title"],
            "url": f"https://www.bilibili.com/video/{v.get('bvid', '')}",
            "heat": v.get("stat", {}).get("view", 0),
            "description": v.get("desc", "")[:200],
            "extra": {
                "author": v.get("owner", {}).get("name", ""),
                "danmaku": v.get("stat", {}).get("danmaku", 0),
                "reply": v.get("stat", {}).get("reply", 0),
                "favorite": v.get("stat", {}).get("favorite", 0),
                "duration": v.get("duration", 0),
            },
        })
    return {
        "platform": "bilibili",
        "fetched_at": datetime.now(TZ).isoformat(),
        "count": len(items),
        "items": items,
    }

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", "-n", type=int, default=20)
    parser.add_argument("--pretty", action="store_true")
    args = parser.parse_args()
    result = fetch(args.limit)
    indent = 2 if args.pretty else None
    print(json.dumps(result, ensure_ascii=False, indent=indent))
    sys.exit(1 if "error" in result else 0)
