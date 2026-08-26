#!/usr/bin/env python3
"""微博热搜采集 — 零认证，公开AJAX接口"""
import json, sys, argparse
from datetime import datetime, timezone, timedelta
from urllib.request import Request, urlopen
from urllib.error import URLError

TZ = timezone(timedelta(hours=8))
API = "https://weibo.com/ajax/side/hotSearch"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    "Referer": "https://weibo.com",
}

def fetch(limit: int = 20) -> dict:
    try:
        req = Request(API, headers=HEADERS)
        resp = urlopen(req, timeout=10)
        data = json.loads(resp.read())
    except (URLError, json.JSONDecodeError) as e:
        return {"error": str(e), "platform": "weibo"}

    raw = data.get("data", {}).get("realtime", [])
    items = []
    for i, v in enumerate(raw[:limit]):
        word = v.get("word", "")
        items.append({
            "rank": i + 1,
            "title": word,
            "url": f"https://s.weibo.com/weibo?q={word}",
            "heat": v.get("num", 0),
            "description": v.get("word_scheme", ""),
            "extra": {
                "label": v.get("label_name", ""),
                "category": v.get("category", ""),
                "emoji": v.get("emoji", ""),
            },
        })
    return {
        "platform": "weibo",
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
