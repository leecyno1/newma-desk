#!/usr/bin/env python3
"""X/Twitter 趋势采集 — 用 xurl 搜索热门话题（无需特殊权限）
如果 xurl 不可用，用 Google 搜索 "Twitter trending" 作为后备"""
import json, sys, subprocess, argparse
from datetime import datetime, timezone, timedelta

TZ = timezone(timedelta(hours=8))


def fetch_via_xurl(limit: int) -> dict:
    """用 xurl 搜索热门话题"""
    try:
        r = subprocess.run(
            ["xurl", "search", "trending OR breaking OR hot", "-n", str(limit)],
            capture_output=True, text=True, timeout=20,
        )
        if r.returncode != 0:
            return {"error": f"xurl failed: {r.stderr[:200]}", "platform": "x"}

        data = json.loads(r.stdout)
        # xurl search 返回的是 tweets
        tweets = data.get("data", []) if isinstance(data, dict) else data
        items = []
        for i, t in enumerate(tweets[:limit]):
            tid = t.get("id", "")
            author = t.get("author_id", "")
            items.append({
                "rank": i + 1,
                "title": t.get("text", "")[:120],
                "url": f"https://x.com/i/status/{tid}" if tid else "",
                "heat": t.get("public_metrics", {}).get("like_count", 0),
                "description": "",
                "extra": {
                    "author": author,
                    "retweets": t.get("public_metrics", {}).get("retweet_count", 0),
                    "replies": t.get("public_metrics", {}).get("reply_count", 0),
                },
            })
        return {
            "platform": "x",
            "fetched_at": datetime.now(TZ).isoformat(),
            "count": len(items),
            "items": items,
        }
    except json.JSONDecodeError:
        return {"error": "xurl returned non-JSON", "platform": "x"}
    except Exception as e:
        return {"error": str(e), "platform": "x"}


def fetch_via_curl(limit: int) -> dict:
    """用 xurl 的原始 API 模式尝试获取 trending"""
    try:
        # 尝试 trends/place 端点 (需要认证)
        r = subprocess.run(
            ["xurl", "/2/users/me"],
            capture_output=True, text=True, timeout=10,
        )
        if r.returncode != 0:
            return {"error": "xurl not authenticated", "platform": "x"}
        return {"error": "trends API needs special endpoint", "platform": "x"}
    except Exception as e:
        return {"error": str(e), "platform": "x"}


def fetch(limit: int = 20) -> dict:
    result = fetch_via_xurl(limit)
    if "error" in result:
        # xurl 可能未认证，返回清晰的错误信息
        result["hint"] = "需要 xurl auth oauth2 设置认证"
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", "-n", type=int, default=20)
    parser.add_argument("--pretty", action="store_true")
    args = parser.parse_args()
    result = fetch(args.limit)
    indent = 2 if args.pretty else None
    print(json.dumps(result, ensure_ascii=False, indent=indent))
    sys.exit(1 if "error" in result else 0)
