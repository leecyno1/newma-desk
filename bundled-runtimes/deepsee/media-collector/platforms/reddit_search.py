#!/usr/bin/env python3
"""Reddit关键词搜索 — 零认证，公开JSON API"""
import json, sys, argparse, urllib.parse
from datetime import datetime, timezone, timedelta
from urllib.request import Request, urlopen
from urllib.error import URLError

TZ = timezone(timedelta(hours=8))
API = "https://www.reddit.com"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; Hermes-Collector/1.0; +https://github.com)"}


def search(keyword: str, subreddit: str = "all", limit: int = 20, sort: str = "relevance") -> dict:
    if subreddit == "all":
        url = f"{API}/search.json?q={urllib.parse.quote(keyword)}&limit={min(limit, 100)}&sort={sort}&raw_json=1"
    else:
        url = f"{API}/r/{subreddit}/search.json?q={urllib.parse.quote(keyword)}&limit={min(limit, 100)}&sort={sort}&restrict_sr=on&raw_json=1"

    try:
        req = Request(url, headers=HEADERS)
        resp = urlopen(req, timeout=15)
        data = json.loads(resp.read())
    except (URLError, json.JSONDecodeError) as e:
        # Fallback to curl
        try:
            r = __import__("subprocess").run(
                ["curl", "-s", "-m", "15", "-H", f"User-Agent: {HEADERS['User-Agent']}", url],
                capture_output=True, text=True, timeout=20)
            data = json.loads(r.stdout)
        except Exception as e2:
            return {"error": f"urllib: {e}, curl: {e2}", "platform": "reddit-search"}

    posts = data.get("data", {}).get("children", [])
    items = []
    for i, child in enumerate(posts[:limit]):
        p = child.get("data", {})
        items.append({
            "rank": i + 1,
            "title": p.get("title", ""),
            "url": f"https://reddit.com{p.get('permalink', '')}",
            "heat": p.get("score", 0),
            "description": (p.get("selftext", "") or "")[:300],
            "extra": {
                "subreddit": p.get("subreddit", ""),
                "author": p.get("author", ""),
                "comments": p.get("num_comments", 0),
                "ratio": p.get("upvote_ratio", 0),
            },
        })
    return {
        "platform": f"reddit-search{'/r/'+subreddit if subreddit != 'all' else ''}",
        "keyword": keyword,
        "sort": sort,
        "fetched_at": datetime.now(TZ).isoformat(),
        "count": len(items),
        "items": items,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Reddit关键词搜索")
    parser.add_argument("keyword", help="搜索关键词")
    parser.add_argument("--subreddit", "-r", default="all")
    parser.add_argument("--limit", "-n", type=int, default=20)
    parser.add_argument("--sort", "-s", default="relevance",
                        choices=["relevance", "hot", "top", "new", "comments"])
    parser.add_argument("--pretty", action="store_true")
    args = parser.parse_args()
    result = search(args.keyword, args.subreddit, args.limit, args.sort)
    indent = 2 if args.pretty else None
    print(json.dumps(result, ensure_ascii=False, indent=indent))
    sys.exit(1 if "error" in result else 0)
