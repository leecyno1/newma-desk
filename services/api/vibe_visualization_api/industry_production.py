"""NBS production evidence, aligned to a requested financial reporting month."""
from __future__ import annotations

import asyncio
import calendar
import time
from copy import deepcopy
from datetime import date, datetime, timezone
from urllib.parse import urljoin, urlsplit
import re

import httpx
from bs4 import BeautifulSoup
from fastapi import APIRouter, HTTPException, Query

from .industry_research import INDEX, clean, number

router = APIRouter(prefix="/api/industry-research/production", tags=["industry-research"])
PRODUCTS = {"原煤（万吨）": ("原煤", "万吨"), "集成电路（亿块）": ("集成电路", "亿块"),
            "微型计算机设备（万台）": ("微型计算机设备", "万台"), "移动通信手持机（万台）": ("移动通信手持机", "万台")}
FIELDS = ("monthValue", "monthYoy", "cumulativeValue", "cumulativeYoy")
_cache: dict[str, tuple[float, dict]] = {}
_lock = asyncio.Lock()


def production_links(html: str, period: str) -> list[str]:
    year, month = map(int, period.split("-"))
    prefix = f"{year}年{month}月份规模以上工业增加值"
    result = set()
    for a in BeautifulSoup(html, "html.parser").select("a[href]"):
        if not clean(a.get("title") or a.get_text()).startswith(prefix):
            continue
        url = urljoin(INDEX, a["href"])
        parts = urlsplit(url)
        if parts.scheme == "https" and parts.netloc == "www.stats.gov.cn" and re.fullmatch(r"/sj/zxfb/\d{6}/t\d{8}_\d+\.html", parts.path):
            result.add(url)
    return sorted(result)


def parse_production(html: str, url: str, period: str, *, today: date | None = None) -> dict:
    today = today or date.today()
    year, month = map(int, period.split("-"))
    end = date(year, month, calendar.monthrange(year, month)[1])
    soup = BeautifulSoup(html, "html.parser")
    def meta(name):
        tag = soup.find("meta", attrs={"name": name})
        return tag.get("content", "") if tag else ""
    title, published = meta("ArticleTitle"), meta("PubDate")[:10].replace("/", "-")
    if not clean(title).startswith(f"{year}年{month}月份规模以上工业增加值"):
        raise ValueError("生产报告期与所选财务报告期不一致")
    if not published or not end <= date.fromisoformat(published) <= today:
        raise ValueError("生产报告发布日期异常")
    metrics = {}
    sales = None
    for table in soup.find_all("table"):
        rows = [[clean(c.get_text()) for c in tr.find_all(["td", "th"], recursive=False)] for tr in table.find_all("tr")]
        if len(rows) < 2 or rows[0] != ["指标", f"{month}月", f"1—{month}月"]:
            continue
        if rows[1] != ["绝对量", "同比增长（%）", "绝对量", "同比增长（%）"]:
            raise ValueError("生产表的当月/累计同比列未识别")
        section = None
        for row in rows[2:]:
            if not row:
                continue
            if len(row) == 5 and row[0] == "产品销售率（%）":
                def pp(value):
                    return number(value.removesuffix("（百分点）")) if value.endswith("（百分点）") else None
                item = {"scope": "全国规模以上工业", "monthRate": number(row[1]), "monthYoyPp": pp(row[2]),
                        "cumulativeRate": number(row[3]), "cumulativeYoyPp": pp(row[4]),
                        "raw": dict(zip(("monthRate", "monthYoyPp", "cumulativeRate", "cumulativeYoyPp"), row[1:]))}
                if sales is not None and sales != item:
                    raise ValueError("产品销售率重复值冲突")
                sales = item
                continue
            if row[0] in ("主要行业增加值", "规模以上工业主要产品产量"):
                section = "valueAdded" if row[0] == "主要行业增加值" else "product"
                continue
            if len(row) != 5 or not section:
                continue
            if section == "product" and row[0] not in PRODUCTS:
                continue
            name, unit = PRODUCTS[row[0]] if section == "product" else (row[0], None)
            values = dict(zip(FIELDS, (number(v) for v in row[1:])))
            item = {"name": name, "kind": section, "unit": unit, **values, "raw": dict(zip(FIELDS, row[1:]))}
            key = (section, name)
            if key in metrics and metrics[key] != item:
                raise ValueError("生产表重复值冲突")
            metrics[key] = item
    if not metrics:
        raise ValueError("未识别生产原表，不以新闻叙述替代数据")
    return {"title": title, "sourceUrl": url, "publisher": "国家统计局", "periodEnd": end.isoformat(),
            "monthlyPeriod": f"{year}年{month}月", "cumulativePeriod": f"{year}年1—{month}月", "publishedAt": published,
            "metrics": list(metrics.values()), "nationalSales": sales, "freshness": "stale" if (today - date.fromisoformat(published)).days > 45 else "unknown",
            "limitations": ["增加值同比为扣除价格因素的实际增长率；财务营收和利润为名义金额，不能直接相减推算价格。",
                            "产品产量是规上工业实物生产量，不是销量、订单或终端需求；不同产品单位不同，不可相加。",
                            "行业财务、行业增加值与产品产量的企业样本及覆盖不保证一致；产品只是相关验证证据，不代表行业全部业务。",
                            "当月同比来自官方原表，不由累计值差分；同比沿用官方可比口径，企业范围仍可能调整。",
                            "产品销售率为销售产值/工业总产值，只是全国产销衔接背景，不是终端销量或当前行业订单。",
                            "价格与季度产能请另查看对应证据；细分行业库存与订单仍待补证。网页可能修订，不是原始时点快照。"]}


async def collect_production(client: httpx.AsyncClient, period: str) -> dict:
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
            links.update(production_links(listing, period))
    if not links:
        raise ValueError("最近四个官方列表页未找到所选期间的生产报告；未用其他月份替代")
    if len(links) > 1:
        raise ValueError("同一期间发现多份生产报告，需核验版本后使用")
    url = next(iter(links))
    result = parse_production(await fetch(url), url, period)
    return {**result, "fetchedAt": datetime.now(timezone.utc).isoformat(), "cached": False,
            "discoveryErrors": errors, "discovery": "最近四个官方发布列表页；按所选统计期匹配，不保证完整历史"}


@router.get("")
async def production_evidence(period: str = Query(pattern=r"^\d{4}-(0[1-9]|1[0-2])$"), refresh: bool = False) -> dict:
    async with _lock:
        if not refresh and period in _cache and time.monotonic() - _cache[period][0] < 900:
            return {**deepcopy(_cache[period][1]), "cached": True}
        try:
            async with httpx.AsyncClient(timeout=18, follow_redirects=False) as client:
                result = await collect_production(client, period)
        except (httpx.HTTPError, ValueError) as exc:
            message = str(exc) if isinstance(exc, ValueError) else "生产原文暂时不可用，没有生成替代数据"
            raise HTTPException(status_code=502, detail=message) from exc
        _cache[period] = (time.monotonic(), result)
        while len(_cache) > 4:
            del _cache[next(iter(_cache))]
        return result
