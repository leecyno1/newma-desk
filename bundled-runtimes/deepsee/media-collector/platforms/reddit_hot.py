#!/usr/bin/env python3
"""Reddit热门采集 — 零认证，公开JSON API
如果urllib被封（部分环境），自动fallback到curl"""
import json, sys, subprocess, argparse
from datetime import datetime, timezone, timedelta

TZ = timezone(timedelta(hours=8))
HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; Hermes-Collector/1.0; +https://github.com)",
}


def fetch_via_urllib(subreddit: str, limit: int) -> dict:
    from urllib.request import Request, urlopen
    from urllib.error import URLError
    url = f"https://www.reddit.com/r/{subreddit}/hot.json?limit={min(limit, 100)}&raw_json=1"
    req = Request(url, headers=HEADERS)
    resp = urlopen(req, timeout=15)
    return json.loads(resp.read())


def fetch_via_curl(subreddit: str, limit: int) -> dict:
    url = f"https://www.reddit.com/r/{subreddit}/hot.json?limit={min(limit, 100)}&raw_json=1"
    r = subprocess.run(
        ["curl", "-s", "-m", "15", "-H", f"User-Agent: {HEADERS['User-Agent']}", url],
        capture_output=True, text=True, timeout=20,
    )
    if r.returncode != 0 or not r.stdout.strip():
        raise Exception(f"curl failed: {r.stderr or 'empty response'}")
    return json.loads(r.stdout)


def fetch(subreddit: str = "all", limit: int = 20) -> dict:
    raw = None
    for method, fn in [("urllib", fetch_via_urllib), ("curl", fetch_via_curl)]:
        try:
            raw = fn(subreddit, limit)
            break
        except Exception:
            continue

    if raw is None:
        return {"error": "所有请求方式均失败 (urllib + curl)", "platform": "reddit"}

    posts = raw.get("data", {}).get("children", [])
    items = []
    for i, child in enumerate(posts):
        p = child.get("data", {})
        items.append(
            {
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
                    "flair": p.get("link_flair_text", ""),
                },
            }
        )
    return {
        "platform": f"reddit/r/{subreddit}",
        "fetched_at": datetime.now(TZ).isoformat(),
        "count": len(items),
        "items": items,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--subreddit", "-r", default="all")
    parser.add_argument("--limit", "-n", type=int, default=20)
    parser.add_argument("--pretty", action="store_true")
    args = parser.parse_args()
    result = fetch(args.subreddit, args.limit)
    indent = 2 if args.pretty else None
    print(json.dumps(result, ensure_ascii=False, indent=indent))
    sys.exit(1 if "error" in result else 0)
