"""Industry output prices from NBS, never substituted with national input prices."""
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

router = APIRouter(prefix="/api/industry-research/prices", tags=["industry-research"])
FIELDS = ("monthMom", "monthYoy", "yearToDateAverageYoy")
_cache: dict[str, tuple[float, dict]] = {}
_lock = asyncio.Lock()


def price_links(html: str, period: str) -> list[str]:
    year, month = map(int, period.split("-"))
    prefix = f"{year}年{month}月份工业生产者出厂价格"
    links = set()
    for a in BeautifulSoup(html, "html.parser").select("a[href]"):
        if not clean(a.get("title") or a.get_text()).startswith(prefix):
            continue
        url = urljoin(INDEX, a["href"])
        parts = urlsplit(url)
        if parts.scheme == "https" and parts.netloc == "www.stats.gov.cn" and re.fullmatch(r"/sj/zxfb/\d{6}/t\d{8}_\d+\.html", parts.path):
            links.add(url)
    return sorted(links)


def parse_prices(html: str, url: str, period: str, *, today: date | None = None) -> dict:
    today = today or date.today()
    year, month = map(int, period.split("-"))
    end = date(year, month, calendar.monthrange(year, month)[1])
    soup = BeautifulSoup(html, "html.parser")
    def meta(name):
        tag = soup.find("meta", attrs={"name": name})
        return tag.get("content", "") if tag else ""
    title, published = meta("ArticleTitle"), meta("PubDate")[:10].replace("/", "-")
    if not clean(title).startswith(f"{year}年{month}月份工业生产者出厂价格"):
        raise ValueError("价格报告期与所选财务报告期不一致")
    if not published or not end <= date.fromisoformat(published) <= today:
        raise ValueError("价格报告发布日期异常")
    metrics = {}
    for table in soup.find_all("table"):
        rows = [[clean(c.get_text()) for c in tr.find_all(["td", "th"], recursive=False)] for tr in table.find_all("tr")]
        if not rows or rows[0] != ["", "环比涨跌幅（%）", "同比涨跌幅（%）", f"1—{month}月同比涨跌幅（%）"]:
            continue
        industry_section = False
        for row in rows[1:]:
            if not row:
                continue
            if row[0] == "三、主要行业出厂价格":
                industry_section = True
                continue
            if not industry_section:
                continue
            if re.match(r"[一二三四五六七八九十]+、", row[0]):
                break
            if len(row) != 4 or not row[0]:
                continue
            item = {"name": row[0], **dict(zip(FIELDS, (number(v) for v in row[1:]))), "raw": dict(zip(FIELDS, row[1:]))}
            if row[0] in metrics and metrics[row[0]] != item:
                raise ValueError("价格表重复值冲突")
            metrics[row[0]] = item
    if not metrics:
        raise ValueError("未识别主要行业出厂价格原表，不用全国总量或购进价格替代")
    base_notes = []
    for p in soup.find_all("p"):
        text = clean(p.get_text())
        if len(text) < 600 and "PPI" in text and "基期" in text and text not in base_notes:
            base_notes.append(text)
    return {"title": title, "sourceUrl": url, "publisher": "国家统计局", "periodEnd": end.isoformat(),
            "monthlyPeriod": f"{year}年{month}月", "averagePeriod": f"{year}年1—{month}月平均", "publishedAt": published,
            "unit": "%", "metrics": list(metrics.values()), "baseNotes": base_notes,
            "freshness": "stale" if (today - date.fromisoformat(published)).days > 45 else "unknown",
            "limitations": ["当月环比、当月同比、年内平均同比是三个口径；年内平均同比不是年初至今累计涨幅，也不是单月价格水平。",
                            "行业出厂价格为工业生产者出售产品的价格指数变化，不是现货报价、长协合同价或上市公司实际售价。",
                            "PPI价格调查与行业财务、产品产量的样本及权重不同，不能直接相乘重构营收或相减归因利润。",
                            "不将全国购进价格当作某行业成本，不用出厂减购进价差冒充利润率。",
                            "仅按同名行业和同一统计期匹配，不自动映射申万或东财分类；网页可能修订，不是原始时点快照。"]}


async def collect_prices(client: httpx.AsyncClient, period: str) -> dict:
    # PPI is released ahead of profits; one more page covers the same four financial periods.
    pages = [INDEX, *(urljoin(INDEX, f"index_{i}.html") for i in range(1, 5))]
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
            links.update(price_links(listing, period))
    if not links:
        raise ValueError("最近五个官方列表页未找到所选期间的价格报告；未用最新月份替代")
    if len(links) > 1:
        raise ValueError("同一期间发现多份价格报告，需核验版本后使用")
    url = next(iter(links))
    result = parse_prices(await fetch(url), url, period)
    return {**result, "fetchedAt": datetime.now(timezone.utc).isoformat(), "cached": False,
            "discoveryErrors": errors, "discovery": "最近五个官方发布列表页；仅匹配所选统计期，不保证完整历史"}


@router.get("")
async def price_evidence(period: str = Query(pattern=r"^\d{4}-(0[1-9]|1[0-2])$"), refresh: bool = False) -> dict:
    async with _lock:
        if not refresh and period in _cache and time.monotonic() - _cache[period][0] < 900:
            return {**deepcopy(_cache[period][1]), "cached": True}
        try:
            async with httpx.AsyncClient(timeout=18, follow_redirects=False) as client:
                result = await collect_prices(client, period)
        except (httpx.HTTPError, ValueError) as exc:
            message = str(exc) if isinstance(exc, ValueError) else "价格原文暂时不可用，没有生成替代数据"
            raise HTTPException(status_code=502, detail=message) from exc
        _cache[period] = (time.monotonic(), result)
        while len(_cache) > 4:
            del _cache[next(iter(_cache))]
        return result
