#!/usr/bin/env python3
"""微博关键词搜索 — 移动端公开接口，零认证
使用 curl 处理 gzip 压缩，urllib 在部分环境有编码问题"""
import json, sys, subprocess, argparse, urllib.parse
from datetime import datetime, timezone, timedelta

TZ = timezone(timedelta(hours=8))
API = "https://m.weibo.cn/api/container/getIndex"
HEADERS = [
    "-H", "User-Agent: Mozilla/5.0 (iPhone; CPU iPhone OS 15_0 like Mac OS X) AppleWebKit/605.1.15",
]

def search(keyword: str, limit: int = 20) -> dict:
    containerid = f"100103type%3D1%26q%3D{urllib.parse.quote(keyword)}"
    url = f"{API}?containerid={containerid}&page=1"

    try:
        r = subprocess.run(
            ["curl", "-s", "--compressed", "-m", "15", url] + HEADERS,
            capture_output=True, text=True, timeout=20)
        if r.returncode != 0 or not r.stdout.strip():
            return {"error": f"curl failed", "platform": "weibo-search"}
        data = json.loads(r.stdout)
    except (json.JSONDecodeError, Exception) as e:
        return {"error": str(e), "platform": "weibo-search"}

    if data.get("ok") != 1:
        return {"error": data.get("msg", "API error"), "platform": "weibo-search"}

    cards = data.get("data", {}).get("cards", [])
    items = []
    rank = 0
    for card in cards:
        mblog = card.get("mblog")
        if not mblog:
            continue
        rank += 1
        if rank > limit:
            break
        text = mblog.get("text", "")
        # 简单清理HTML标签
        import re
        text_clean = re.sub(r"<[^>]+>", "", text).replace("\n", " ")[:200]
        items.append({
            "rank": rank,
            "title": text_clean[:100],
            "url": f"https://m.weibo.cn/detail/{mblog.get('id', '')}",
            "heat": mblog.get("attitudes_count", 0),  # 点赞数
            "description": text_clean,
            "extra": {
                "author": mblog.get("user", {}).get("screen_name", ""),
                "likes": mblog.get("attitudes_count", 0),
                "comments": mblog.get("comments_count", 0),
                "reposts": mblog.get("reposts_count", 0),
                "created_at": mblog.get("created_at", ""),
            },
        })

    return {
        "platform": "weibo-search",
        "keyword": keyword,
        "fetched_at": datetime.now(TZ).isoformat(),
        "count": len(items),
        "items": items,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="微博关键词搜索")
    parser.add_argument("keyword", help="搜索关键词")
    parser.add_argument("--limit", "-n", type=int, default=20)
    parser.add_argument("--pretty", action="store_true")
    args = parser.parse_args()
    result = search(args.keyword, args.limit)
    indent = 2 if args.pretty else None
    print(json.dumps(result, ensure_ascii=False, indent=indent))
    sys.exit(1 if "error" in result else 0)
