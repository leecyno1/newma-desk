"""Quarterly NBS capacity utilization; never relabel quarters as monthly data."""
from __future__ import annotations

import asyncio
import calendar
import re
import time
from copy import deepcopy
from datetime import date, datetime, timezone
from urllib.parse import urljoin, urlsplit

import httpx
from bs4 import BeautifulSoup
from fastapi import APIRouter, HTTPException, Query

from .industry_research import INDEX, clean, number

router = APIRouter(prefix="/api/industry-research/capacity", tags=["industry-research"])
FIELDS = ("quarterRate", "quarterYoyPp", "yearToDateRate", "yearToDateYoyPp")
QUARTERS = {3: "一季度", 6: "二季度", 9: "三季度", 12: "四季度"}
CUMULATIVE = {3: "一季度", 6: "上半年", 9: "前三季度", 12: "全年"}
GROUPS = {"工业", "采矿业", "制造业", "电力、热力、燃气及水生产和供应业"}
_cache: dict[str, tuple[float, dict]] = {}
_lock = asyncio.Lock()


def capacity_links(html: str, period: str) -> list[str]:
    year, month = map(int, period.split("-"))
    title_prefix = f"{year}年{QUARTERS[month]}全国规模以上工业产能利用率"
    urls = set()
    for a in BeautifulSoup(html, "html.parser").select("a[href]"):
        if not clean(a.get("title") or a.get_text()).startswith(title_prefix):
            continue
        url = urljoin(INDEX, a["href"])
        parts = urlsplit(url)
        if parts.scheme == "https" and parts.netloc == "www.stats.gov.cn" and re.fullmatch(r"/sj/zxfb/\d{6}/t\d{8}_\d+\.html", parts.path):
            urls.add(url)
    return sorted(urls)


def parse_capacity(html: str, url: str, period: str, *, today: date | None = None) -> dict:
    year, month = map(int, period.split("-"))
    quarter, cumulative = QUARTERS[month], CUMULATIVE[month]
    end = date(year, month, calendar.monthrange(year, month)[1])
    soup = BeautifulSoup(html, "html.parser")
    def meta(name):
        tag = soup.find("meta", attrs={"name": name})
        return tag.get("content", "") if tag else ""
    title, published = meta("ArticleTitle"), meta("PubDate")[:10].replace("/", "-")
    if not clean(title).startswith(f"{year}年{quarter}全国规模以上工业产能利用率"):
        raise ValueError("产能报告季度不一致，未使用其他季度替代")
    if not published or not end <= date.fromisoformat(published) <= (today or date.today()):
        raise ValueError("产能报告发布日期异常")
    metrics = {}
    for table in soup.find_all("table"):
        rows = [[clean(c.get_text()) for c in tr.find_all(["td", "th"], recursive=False)] for tr in table.find_all("tr")]
        if len(rows) < 3 or rows[0] != ["行业", quarter, cumulative]:
            continue
        if rows[1] != ["产能利用率（%）", "比上年同期增减（百分点）"] * 2:
            raise ValueError("产能利用率与同比百分点列未识别")
        for row in rows[2:]:
            if len(row) != 5:
                continue
            name = row[0].removeprefix("其中：")
            values = dict(zip(FIELDS, (number(v) for v in row[1:])))
            item = {"name": name, "scope": "group" if name in GROUPS else "industry", **values,
                    "raw": dict(zip(FIELDS, row[1:]))}
            if name in metrics and metrics[name] != item:
                raise ValueError("产能原表重复值冲突")
            metrics[name] = item
    if not metrics or not any(row["scope"] == "industry" for row in metrics.values()):
        raise ValueError("未识别分行业产能利用率原表")
    return {"title": title, "sourceUrl": url, "publisher": "国家统计局", "publishedAt": published,
            "periodEnd": end.isoformat(), "quarterPeriod": f"{year}年{quarter}", "yearToDatePeriod": f"{year}年{cumulative}",
            "metrics": list(metrics.values()), "coverage": sum(row["scope"] == "industry" for row in metrics.values()),
            "limitations": ["产能利用率是实际产出与生产能力的比率，不是订单、销量或盈利增速。",
                            "季度与年内累计利用率分别沿用官方值；同比变化单位为百分点，不是百分比增长率。",
                            "利用率变化可能来自需求、产能增减或检修，不能单独判定需求复苏或产能过剩。",
                            "不同产业生产工艺与正常利用水平不同，不按利用率高低跨行业评级。未列行业不以全国或门类替代。",
                            "季度证据不可外推为后续月份；原文为现时读取，可能修订，不是原始时点回测数据。"]}


async def collect_capacity(client: httpx.AsyncClient, period: str) -> dict:
    pages = [INDEX, *(urljoin(INDEX, f"index_{i}.html") for i in range(1, 4))]
    async def fetch(url):
        response = await client.get(url)
        response.raise_for_status()
        return response.text
    listings = await asyncio.gather(*(fetch(url) for url in pages), return_exceptions=True)
    links, errors = set(), []
    for url, listing in zip(pages, listings):
        if isinstance(listing, Exception):
            errors.append({"sourceUrl": url, "reason": "发布列表读取失败"})
        else:
            links.update(capacity_links(listing, period))
    if len(links) != 1:
        raise ValueError("最近四个官方列表页未找到唯一匹配的季度产能报告；未使用其他季度替代")
    url = next(iter(links))
    result = parse_capacity(await fetch(url), url, period)
    return {**result, "fetchedAt": datetime.now(timezone.utc).isoformat(), "cached": False,
            "discoveryErrors": errors, "discovery": "最近四个官方发布列表页；不保证完整季度历史"}


@router.get("")
async def capacity_evidence(period: str = Query(pattern=r"^\d{4}-(03|06|09|12)$"), refresh: bool = False) -> dict:
    async with _lock:
        if not refresh and period in _cache and time.monotonic() - _cache[period][0] < 900:
            return {**deepcopy(_cache[period][1]), "cached": True}
        try:
            async with httpx.AsyncClient(timeout=18, follow_redirects=False) as client:
                result = await collect_capacity(client, period)
        except (httpx.HTTPError, ValueError) as exc:
            message = str(exc) if isinstance(exc, ValueError) else "产能原文暂时不可用，没有生成替代数据"
            raise HTTPException(status_code=502, detail=message) from exc
        _cache[period] = (time.monotonic(), result)
        while len(_cache) > 4:
            del _cache[next(iter(_cache))]
        return result
