#!/usr/bin/env python3
"""NewsNow 热榜关键词过滤 — 从已有热榜中筛选含关键词的条目
覆盖 14 个中文源，用缓存加速"""
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

ALL_SOURCES = {
    "weibo": "微博热搜", "zhihu": "知乎热榜", "baidu": "百度热搜",
    "toutiao": "今日头条", "douyin": "抖音热榜", "thepaper": "澎湃新闻",
    "36kr": "36氪", "ithome": "IT之家", "v2ex": "V2EX", "juejin": "掘金",
    "hackernews": "Hacker News", "cls": "财联社", "wallstreetcn": "华尔街见闻",
    "xueqiu": "雪球热榜",
}


def fetch_source(source_id: str) -> list:
    """获取单个源的热榜"""
    try:
        req = Request(f"{API_BASE}?id={source_id}&count=30", headers=HEADERS)
        resp = urlopen(req, timeout=10)
        data = json.loads(resp.read())
        if data.get("status") in ("success", "cache"):
            return data.get("items", [])
    except Exception:
        pass
    return []


def keyword_match(item: dict, keyword: str) -> bool:
    title = item.get("title", "").lower()
    desc = item.get("extra", {}).get("desc", "").lower() if isinstance(item.get("extra"), dict) else ""
    kw = keyword.lower()
    # 支持空格分隔的多关键词（OR 逻辑）
    for k in kw.split():
        if k in title or k in desc:
            return True
    return False


def search(keyword: str, sources: list = None, limit: int = 20) -> dict:
    if sources is None:
        sources = list(ALL_SOURCES.keys())

    all_matches = []
    for src in sources:
        items = fetch_source(src)
        for item in items:
            if keyword_match(item, keyword):
                item["_source_id"] = src
                item["_source_name"] = ALL_SOURCES.get(src, src)
                all_matches.append(item)
        if len(sources) > 1:
            time.sleep(0.1)

    items = []
    for i, item in enumerate(all_matches[:limit]):
        extra = item.get("extra", {}) if isinstance(item.get("extra"), dict) else {}
        items.append({
            "rank": i + 1,
            "title": item.get("title", ""),
            "url": item.get("url", item.get("mobileUrl", "")),
            "heat": extra.get("hot", 0) if isinstance(extra, dict) else 0,
            "description": (extra.get("desc", "") if isinstance(extra, dict) else "")[:200],
            "extra": {
                "source_id": item.get("_source_id", ""),
                "source_name": item.get("_source_name", ""),
            },
        })

    return {
        "platform": "newsnow-filter",
        "keyword": keyword,
        "sources_scanned": len(sources),
        "fetched_at": datetime.now(TZ).isoformat(),
        "count": len(items),
        "items": items,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="NewsNow热榜关键词过滤")
    parser.add_argument("keyword", help="搜索关键词（支持空格分隔多词OR匹配）")
    parser.add_argument("--sources", "-s", default="weibo,zhihu,baidu,cls,wallstreetcn,36kr",
                        help="源列表，逗号分隔")
    parser.add_argument("--limit", "-n", type=int, default=20)
    parser.add_argument("--pretty", action="store_true")
    parser.add_argument("--list", action="store_true", help="列出可用源")
    args = parser.parse_args()

    if args.list:
        for sid, name in ALL_SOURCES.items():
            print(f"  {sid:15s} {name}")
        sys.exit(0)

    sources = [s.strip() for s in args.sources.split(",")]
    result = search(args.keyword, sources, args.limit)
    indent = 2 if args.pretty else None
    print(json.dumps(result, ensure_ascii=False, indent=indent))
    sys.exit(1 if "error" in result else 0)
