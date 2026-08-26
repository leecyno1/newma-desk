#!/usr/bin/env python3
"""NewsNow 热榜聚合采集 — 一口覆盖 14 个中文源
基于 alphaear-news 的 newsnow.busiyi.world API
来源: https://github.com/RKiding/Awesome-finance-skills
"""
import json, sys, argparse, os, time
from datetime import datetime, timezone, timedelta
from urllib.request import Request, urlopen
from urllib.error import URLError

TZ = timezone(timedelta(hours=8))
API_BASE = "https://newsnow.busiyi.world/api/s"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
}

# 全部可用源及其分类
ALL_SOURCES = {
    # 社交/通用
    "weibo":       {"name": "微博热搜",   "cat": "social"},
    "zhihu":       {"name": "知乎热榜",   "cat": "social"},
    "baidu":       {"name": "百度热搜",   "cat": "social"},
    "toutiao":     {"name": "今日头条",   "cat": "social"},
    "douyin":      {"name": "抖音热榜",   "cat": "social"},
    "thepaper":    {"name": "澎湃新闻",   "cat": "news"},
    # 科技
    "36kr":        {"name": "36氪",       "cat": "tech"},
    "ithome":      {"name": "IT之家",     "cat": "tech"},
    "v2ex":        {"name": "V2EX",       "cat": "tech"},
    "juejin":      {"name": "掘金",       "cat": "tech"},
    "hackernews":  {"name": "Hacker News","cat": "tech"},
    # 金融
    "cls":         {"name": "财联社",     "cat": "finance"},
    "wallstreetcn":{"name": "华尔街见闻", "cat": "finance"},
    "xueqiu":      {"name": "雪球热榜",   "cat": "finance"},
}

# 默认采集的源
DEFAULT_SOURCES = ["weibo", "zhihu", "baidu", "douyin", "36kr", "cls", "wallstreetcn"]

# ── 缓存 ──
CACHE_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".cache")
CACHE_TTL = 300  # 5 分钟


def _cache_path(source_id: str) -> str:
    return os.path.join(CACHE_DIR, f"newsnow_{source_id}.json")


def _read_cache(source_id: str):
    path = _cache_path(source_id)
    if not os.path.exists(path):
        return None
    try:
        with open(path) as f:
            data = json.load(f)
        age = time.time() - data.get("_ts", 0)
        if age < CACHE_TTL:
            return data.get("_data")
        return data.get("_data")  # 过期也返回，供 fallback
    except Exception:
        return None


def _write_cache(source_id: str, data: dict):
    os.makedirs(CACHE_DIR, exist_ok=True)
    with open(_cache_path(source_id), "w") as f:
        json.dump({"_ts": time.time(), "_data": data}, f, ensure_ascii=False)


def fetch_source(source_id: str, limit: int = 20) -> dict:
    """Fetch hot items for a single source from NewsNow API."""
    cached = _read_cache(source_id)

    # 缓存有效直接返回
    if cached:
        path = _cache_path(source_id)
        if os.path.exists(path):
            with open(path) as f:
                age = time.time() - json.load(f).get("_ts", 0)
            if age < CACHE_TTL:
                # 截断到 limit
                result = dict(cached)
                result["items"] = cached["items"][:limit]
                result["count"] = len(result["items"])
                return result

    # API 请求
    info = ALL_SOURCES.get(source_id, {"name": source_id, "cat": "other"})
    try:
        req = Request(f"{API_BASE}?id={source_id}&count={min(limit, 30)}", headers=HEADERS)
        resp = urlopen(req, timeout=10)
        data = json.loads(resp.read())
    except Exception as e:
        # 请求失败，用过期缓存兜底
        if cached:
            result = dict(cached)
            result["items"] = cached["items"][:limit]
            result["count"] = len(result["items"])
            result["_stale"] = True
            return result
        return {"error": str(e), "platform": f"newsnow/{source_id}"}

    if data.get("status") not in ("success", "cache"):
        return {"error": f"API status={data.get('status')}", "platform": f"newsnow/{source_id}"}

    items = []
    raw_items = data.get("items", [])
    for i, item in enumerate(raw_items[:limit]):
        extra = item.get("extra", {})
        info_copy = dict(item.get("info", {}))
        items.append({
            "rank": i + 1,
            "title": item.get("title", ""),
            "url": item.get("url", item.get("mobileUrl", "")),
            "heat": extra.get("hot", extra.get("heat", 0)),
            "description": extra.get("desc", "")[:200],
            "extra": {
                "source_id": source_id,
                "source_name": info["name"],
                "category": info["cat"],
            },
        })

    result = {
        "platform": f"newsnow/{source_id}",
        "source_name": info["name"],
        "category": info["cat"],
        "fetched_at": datetime.now(TZ).isoformat(),
        "count": len(items),
        "items": items,
    }

    _write_cache(source_id, result)
    return result


def fetch_multi(sources: list, limit: int = 20) -> list:
    """Fetch multiple sources, return list of per-source results."""
    results = []
    for src in sources:
        r = fetch_source(src, limit)
        results.append(r)
        if len(sources) > 1:
            time.sleep(0.1)  # 避免并发压 API
    return results


def main():
    parser = argparse.ArgumentParser(description="NewsNow 热榜聚合采集")
    parser.add_argument("--source", "-s", default=None,
                        help="单个源ID，不指定则采集默认源列表")
    parser.add_argument("--limit", "-n", type=int, default=20)
    parser.add_argument("--pretty", action="store_true")
    parser.add_argument("--list", action="store_true", help="列出所有可用源")
    args = parser.parse_args()

    if args.list:
        for sid, info in ALL_SOURCES.items():
            print(f"  {sid:15s} {info['name']:10s} [{info['cat']}]")
        return

    if args.source:
        result = fetch_source(args.source, args.limit)
        indent = 2 if args.pretty else None
        print(json.dumps(result, ensure_ascii=False, indent=indent))
        sys.exit(1 if "error" in result else 0)
    else:
        # 默认采集多个源
        results = fetch_multi(DEFAULT_SOURCES, args.limit)
        indent = 2 if args.pretty else None
        print(json.dumps(results, ensure_ascii=False, indent=indent))
        has_error = any("error" in r for r in results)
        sys.exit(1 if has_error else 0)


if __name__ == "__main__":
    main()
