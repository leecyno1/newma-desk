#!/usr/bin/env python3
"""Google Trends 每日趋势 — RSS 方式，零依赖"""
import json, sys, argparse, re
from datetime import datetime, timezone, timedelta
from urllib.request import Request, urlopen
from urllib.error import URLError
import xml.etree.ElementTree as ET

TZ = timezone(timedelta(hours=8))
RSS_URL = "https://trends.google.com/trending/rss"
NS = "https://trends.google.com/trending/rss"

REGIONS = {
    "us": "US", "cn": "CN", "jp": "JP", "gb": "GB",
    "kr": "KR", "de": "DE", "fr": "FR", "global": "US",
}

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; Hermes-Collector/1.0)"}


def parse_traffic(val: str) -> int:
    """Parse traffic like '100K+' or '200+' to integer"""
    val = val.replace("+", "").replace(",", "").strip()
    m = re.match(r"(\d+\.?\d*)\s*([KMB]?)", val, re.IGNORECASE)
    if not m:
        return 0
    n = float(m.group(1))
    unit = m.group(2).upper()
    if unit == "M":
        n *= 1000000
    elif unit == "K":
        n *= 1000
    return int(n)


def fetch(region: str = "us", limit: int = 20) -> dict:
    geo = REGIONS.get(region, region.upper())
    url = f"{RSS_URL}?geo={geo}"

    try:
        req = Request(url, headers=HEADERS)
        resp = urlopen(req, timeout=15)
        xml_data = resp.read()
    except URLError as e:
        return {"error": f"RSS 请求失败: {e}", "platform": "google-trends"}

    try:
        root = ET.fromstring(xml_data)
    except ET.ParseError as e:
        return {"error": f"XML 解析失败: {e}", "platform": "google-trends"}

    items = []
    for i, item_el in enumerate(root.findall(".//item")):
        if i >= limit:
            break

        title_el = item_el.find("title")
        traffic_el = item_el.find(f"{{{NS}}}approx_traffic")
        pic_el = item_el.find(f"{{{NS}}}picture")

        title = title_el.text if title_el is not None else ""
        traffic_raw = traffic_el.text if traffic_el is not None else ""
        traffic = parse_traffic(traffic_raw)

        # 提取第一个 news item 作为描述和链接
        news_items = item_el.findall(f"{{{NS}}}news_item")
        description = ""
        ext_url = ""
        news_source = ""
        if news_items:
            first = news_items[0]
            nt = first.find(f"{{{NS}}}news_item_title")
            nu = first.find(f"{{{NS}}}news_item_url")
            ns = first.find(f"{{{NS}}}news_item_source")
            if nt is not None:
                description = (nt.text or "")[:200]
            if nu is not None:
                ext_url = nu.text or ""
            if ns is not None:
                news_source = ns.text or ""

        items.append({
            "rank": i + 1,
            "title": title,
            "url": ext_url or f"https://trends.google.com/trends/explore?q={title}&geo={geo}",
            "heat": traffic,
            "description": description,
            "extra": {
                "traffic_raw": traffic_raw,
                "source": news_source,
                "geo": geo,
            },
        })

    if not items:
        return {"error": f"RSS 无数据 (geo={geo})", "platform": "google-trends"}

    return {
        "platform": f"google-trends/{region}",
        "fetched_at": datetime.now(TZ).isoformat(),
        "count": len(items),
        "items": items,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--region", "-r", default="us",
                        choices=list(REGIONS.keys()))
    parser.add_argument("--limit", "-n", type=int, default=20)
    parser.add_argument("--pretty", action="store_true")
    args = parser.parse_args()
    result = fetch(args.region, args.limit)
    indent = 2 if args.pretty else None
    print(json.dumps(result, ensure_ascii=False, indent=indent))
    sys.exit(1 if "error" in result else 0)
