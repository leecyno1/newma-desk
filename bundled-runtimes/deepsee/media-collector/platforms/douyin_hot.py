#!/usr/bin/env python3
"""抖音热榜采集 — 纯Python实现，零依赖（替代node脚本，方便云部署）"""
import json, sys, argparse
from datetime import datetime, timezone, timedelta
from urllib.request import Request, urlopen
from urllib.error import URLError

TZ = timezone(timedelta(hours=8))
# 抖音公开热榜接口（与douyin.js一致）
API = "https://www.douyin.com/aweme/v1/hot/search/list/"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Referer": "https://www.douyin.com/",
    "Accept": "application/json",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}

def fetch(limit: int = 20) -> dict:
    try:
        req = Request(API, headers=HEADERS)
        resp = urlopen(req, timeout=10)
        data = json.loads(resp.read())
    except (URLError, json.JSONDecodeError) as e:
        return {"error": str(e), "platform": "douyin"}

    words = data.get("data", {}).get("word_list", [])
    items = []
    for i, w in enumerate(words[:limit]):
        word = w.get("word", "")
        items.append({
            "rank": i + 1,
            "title": word,
            "url": f"https://www.douyin.com/search/{word}",
            "heat": w.get("hot_value", 0),
            "description": "",
            "extra": {
                "label": w.get("label", ""),
                "type": w.get("type", ""),
                "position": w.get("position", 0),
            },
        })
    return {
        "platform": "douyin",
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
