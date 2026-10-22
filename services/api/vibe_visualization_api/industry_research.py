"""Industry fundamentals from NBS publications, separate from market taxonomies."""
from __future__ import annotations

import asyncio
import calendar
import math
import re
import time
from copy import deepcopy
from datetime import date, datetime, timezone
from urllib.parse import urljoin, urlsplit

import httpx
from bs4 import BeautifulSoup
from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/api/industry-research", tags=["industry-research"])
INDEX = "https://www.stats.gov.cn/sj/zxfb/"
_cache: tuple[float, dict] | None = None
_lock = asyncio.Lock()
_history_cache: tuple[float, dict] | None = None
_history_lock = asyncio.Lock()
FIELDS = ("revenue", "revenueYoy", "cost", "costYoy", "profit", "profitYoy")
LIMITS = [
    "口径为国家统计局规模以上工业企业行业分类，包含非上市企业；不是申万或东财行业成分。",
    "营收、成本、利润是年初至报告月累计值，同比沿用官方可比口径；不通过相邻累计差额推算单月。",
    "营收增长同时受销量、价格和统计样本影响，不能单独等同需求增长；利润增长可能受低基数影响。",
    "利润率=利润总额/营业收入，不是毛利率、净利率或ROE；成本率不包含全部期间费用。",
    "历史对照为累计同比变化，不是单月增速或拐点确认；行业订单、库存、产能、价格、估值及上市公司暴露仍待补证。",
    "银行、证券及多数服务行业不在此工业调查范围；电子制造业大类不能代表半导体子行业。",
]


def clean(value: str) -> str:
    return re.sub(r"\s+", "", value).replace("－", "-").replace("−", "-")


def number(value: str) -> float | None:
    text = clean(value).replace(",", "")
    if not re.fullmatch(r"[+-]?\d+(?:\.\d+)?", text):
        return None
    result = float(text)
    return result if math.isfinite(result) else None


def quadrant(revenue: float | None, profit: float | None) -> str:
    if revenue is None or profit is None:
        return "unknown"
    if revenue == 0 or profit == 0:
        return "boundary"
    return ("expansion" if profit > 0 else "pressure") if revenue > 0 else ("repair" if profit > 0 else "contraction")


def publication_links(html: str) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")
    result = []
    for a in soup.select("a[href]"):
        title = clean(a.get("title") or a.get_text())
        if not re.match(r"\d{4}年(?:1[—-]\d{1,2}月份)?全国规模以上工业企业利润", title):
            continue
        url = urljoin(INDEX, a["href"])
        parts = urlsplit(url)
        if parts.scheme == "https" and parts.netloc == "www.stats.gov.cn" and re.fullmatch(r"/sj/zxfb/\d{6}/t\d{8}_\d+\.html", parts.path):
            if url not in result:
                result.append(url)
    return result


def parse_operations(soup: BeautifulSoup, month: int) -> dict:
    """Read the economic-efficiency table, never attribute group data to an industry."""
    columns = {"inventoryDays": ("产成品存货周转天数", "（天）"),
               "receivableDays": ("应收账款平均回收期", "（天）"),
               "debtRatio": ("资产负债率", "（%）"),
               "expensePer100Revenue": ("每百元营业收入中的费用", "（元）")}
    groups = {"总计", "采矿业", "制造业", "电力、热力、燃气及水生产和供应业"}
    result = {}
    for table in soup.find_all("table"):
        cells = [[clean(c.get_text()) for c in tr.find_all(["td", "th"], recursive=False)] for tr in table.find_all("tr")]
        if len(cells) < 4 or cells[0][0:1] != ["分组"] or "产成品存货周转天数" not in cells[0]:
            continue
        indexes = {}
        for key, (label, unit) in columns.items():
            if label not in cells[0]:
                return {"status": "unavailable", "rows": [], "reason": "经营质量表缺少必需列"}
            index = cells[0].index(label)
            # The second and third header rows omit the spanning group column.
            if len(cells[2]) != len(cells[0]) - 1 or cells[2][index - 1] != unit:
                return {"status": "unavailable", "rows": [], "reason": "经营质量表单位未识别"}
            indexes[key] = index
        for cell in cells[3:]:
            if len(cell) != len(cells[0]):
                continue
            name = cell[0].removeprefix("其中：")
            if name not in groups:
                continue
            item = {"name": name, **{key: number(cell[index]) for key, index in indexes.items()},
                    "raw": {key: cell[index] for key, index in indexes.items()}}
            if name in result and result[name] != item:
                return {"status": "unavailable", "rows": [], "reason": "经营质量表重复值冲突"}
            result[name] = item
    if "总计" in result:
        # Only the national, current-month narrative publishes year-on-year days.
        paragraphs = {clean(p.get_text()) for p in soup.find_all("p") if not p.find("p") and not p.find("table")}
        for key, label in [("inventoryDays", "产成品存货周转天数"), ("receivableDays", "应收账款平均回收期")]:
            observations = set()
            for paragraph in paragraphs:
                if not paragraph.startswith(f"{month}月末，规模以上工业企业"):
                    continue
                match = re.search(label + r"为([\d.]+)天，同比(增加|减少)([\d.]+)天", paragraph)
                if match and number(match[1]) == result["总计"][key]:
                    value = number(match[3])
                    if value is not None:
                        observations.add(value * (1 if match[2] == "增加" else -1))
            result["总计"][key + "YoyChange"] = observations.pop() if len(observations) == 1 else None
    return {"status": "ready" if len(result) == 4 else "partial" if result else "unavailable",
            "rows": list(result.values()), "reason": "" if len(result) == 4 else "全国或三大门类指标未完整取得"}


def parse_publication(html: str, url: str, *, today: date | None = None) -> dict:
    today = today or date.today()
    soup = BeautifulSoup(html, "html.parser")
    def meta(name):
        tag = soup.find("meta", attrs={"name": name})
        return tag.get("content", "") if tag else ""
    title = meta("ArticleTitle")
    period = re.match(r"(\d{4})年(?:1[—-](\d{1,2})月份)?全国规模以上工业企业利润", clean(title))
    published = meta("PubDate")[:10].replace("/", "-")
    if not period or not published:
        raise ValueError("官方报告期或发布日期未识别，未生成行业判断")
    year, month = int(period.group(1)), int(period.group(2) or 12)
    end = date(year, month, calendar.monthrange(year, month)[1])
    published_date = date.fromisoformat(published)
    if end > published_date or published_date > today:
        raise ValueError("报告期或发布日期异常，未使用未来信息")
    rows: dict[str, dict] = {}
    total = None
    for table in soup.find_all("table"):
        cells = [[clean(c.get_text()) for c in tr.find_all(["td", "th"], recursive=False)] for tr in table.find_all("tr")]
        # NBS repeats the same table in desktop/mobile markup. Match semantics,
        # not table position, and reject inconsistent duplicate observations.
        if not cells or cells[0] != ["行业", "营业收入", "营业成本", "利润总额"]:
            continue
        header = "".join("".join(row) for row in cells[:3])
        if "亿元" not in header or "同比增长" not in header or "%" not in header:
            raise ValueError("行业表单位或同比列未识别")
        for cell in cells[1:]:
            if len(cell) != 7 or not cell[0]:
                continue
            values = dict(zip(FIELDS, (number(v) for v in cell[1:])))
            if all(v is None for v in values.values()):
                raise ValueError("行业行无法识别为数值，未静默跳过")
            revenue, profit, cost = values["revenue"], values["profit"], values["cost"]
            item = {"name": cell[0], **values, "raw": dict(zip(FIELDS, cell[1:])),
                    "profitMargin": round(profit / revenue * 100, 4) if revenue and revenue > 0 and profit is not None else None,
                    "costRatio": round(cost / revenue * 100, 4) if revenue and revenue > 0 and cost is not None else None,
                    "quadrant": quadrant(values["revenueYoy"], values["profitYoy"])}
            if cell[0] == "总计":
                if total and total != item:
                    raise ValueError("总计重复值冲突")
                total = item
            else:
                if cell[0] in rows and rows[cell[0]] != item:
                    raise ValueError("同一行业重复值冲突")
                rows[cell[0]] = item
    if not rows or total is None:
        raise ValueError("未识别分行业原始表，未以新闻摘要替代")
    return {"title": title, "sourceUrl": url, "publisher": "国家统计局", "publishedAt": published,
            "period": f"{year}年1—{month}月", "periodEnd": end.isoformat(), "unit": "亿元 / %",
            "taxonomy": "国家统计局规模以上工业企业行业分类", "rows": list(rows.values()), "total": total,
            "operations": {**parse_operations(soup, month), "scope": "全国及工业三大门类，不是41个细分行业",
                           "periodEnd": end.isoformat(), "sourceUrl": url, "publishedAt": published,
                           "boundary": "周转天数和回收期采用官方平均存量计算值，不以期末余额重算。费用为累计每百元营收费用；其余指标为报告月末官方口径。不同门类经营模式不同，不按天数高低排名，不据此推断具体行业现金流或投资评级。"},
            "coverage": {"industries": len(rows), "comparable": sum(r["quadrant"] != "unknown" for r in rows.values()),
                         "expectedIndustries": 41}, "limitations": LIMITS,
            "freshness": "stale" if (today - published_date).days > 45 else "unknown"}


async def collect(client: httpx.AsyncClient) -> dict:
    pages = [INDEX, *(urljoin(INDEX, f"index_{i}.html") for i in range(1, 4))]
    visited = []
    # Releases are listed newest first. Stop at the first matching page, but
    # never skip a failed newer page and present an older report as current.
    for page in pages:
        listing = await client.get(page)
        listing.raise_for_status()
        visited.append(page)
        links = publication_links(listing.text)
        if links:
            break
    else:
        raise ValueError("最近四个发布列表页中未发现工业利润报告，请查看统计局原文；未扫描完整历史档案")
    # The date in the official document path selects the newest discovered release.
    url = max(links, key=lambda value: urlsplit(value).path)
    response = await client.get(url)
    response.raise_for_status()
    result = parse_publication(response.text, url)
    return {"schemaVersion": "newma-desk.industry-prosperity.v1", **result,
            "fetchedAt": datetime.now(timezone.utc).isoformat(),
            "discovery": f"按发布时间顺序检查国家统计局最近发布列表前{len(visited)}页，采用首个匹配页的最新报告；最多检查4页，不保证完整历史",
            "discoveryPages": visited, "cached": False}


async def collect_history(client: httpx.AsyncClient) -> dict:
    pages = [INDEX, *(urljoin(INDEX, f"index_{i}.html") for i in range(1, 4))]
    errors = []

    async def fetch(url):
        response = await client.get(url)
        response.raise_for_status()
        return response.text

    listings = await asyncio.gather(*(fetch(url) for url in pages), return_exceptions=True)
    links = set()
    for url, listing in zip(pages, listings):
        if isinstance(listing, Exception):
            errors.append({"sourceUrl": url, "reason": "发布列表读取失败"})
        else:
            links.update(publication_links(listing))
    urls = sorted(links, key=lambda value: urlsplit(value).path, reverse=True)[:4]
    documents = await asyncio.gather(*(fetch(url) for url in urls), return_exceptions=True)
    publications = []
    fetched_at = datetime.now(timezone.utc).isoformat()
    for url, document in zip(urls, documents):
        try:
            if isinstance(document, Exception):
                raise ValueError("报告原文读取失败")
            result = parse_publication(document, url)
            publications.append({"schemaVersion": "newma-desk.industry-prosperity.v1", **result,
                                 "fetchedAt": fetched_at, "cached": False,
                                 "discovery": "最近四个发布列表页中的历史报告；本次读取，不是原始时点快照"})
        except ValueError as exc:
            errors.append({"sourceUrl": url, "reason": str(exc)})
    if not publications:
        raise ValueError("最近四个列表页未取得可解析的历史报告，请重试或查看统计局原文")
    publications.sort(key=lambda item: (item["periodEnd"], item["publishedAt"], item["sourceUrl"]), reverse=True)
    return {"publications": publications, "errors": errors, "status": "partial" if errors else "complete",
            "fetchedAt": fetched_at, "cached": False, "discoveryPages": pages,
            "scope": "最近四个发布列表页，最多四份报告；不保证连续或完整历史。网页可能修订，不可用于无前视回测。"}


@router.get("/history")
async def industry_history(refresh: bool = False) -> dict:
    global _history_cache
    async with _history_lock:
        if not refresh and _history_cache and time.monotonic() - _history_cache[0] < 900:
            result = deepcopy(_history_cache[1])
            result["cached"] = True
            for publication in result["publications"]:
                publication["cached"] = True
            return result
        try:
            async with httpx.AsyncClient(timeout=18, follow_redirects=False) as client:
                result = await collect_history(client)
        except (httpx.HTTPError, ValueError) as exc:
            message = str(exc) if isinstance(exc, ValueError) else "历史原文暂时不可用，没有生成替代数据"
            raise HTTPException(status_code=502, detail=message) from exc
        _history_cache = (time.monotonic(), result)
        return result


@router.get("")
async def industry_dashboard(refresh: bool = False) -> dict:
    global _cache
    async with _lock:
        if not refresh and _cache and time.monotonic() - _cache[0] < 900:
            return {**deepcopy(_cache[1]), "cached": True}
        try:
            async with httpx.AsyncClient(timeout=18, follow_redirects=False) as client:
                result = await collect(client)
        except (httpx.HTTPError, ValueError) as exc:
            # A failed refresh never substitutes a cached snapshot as current evidence.
            message = str(exc) if isinstance(exc, ValueError) else "统计局原文暂时不可用，请重试；没有生成替代数据"
            raise HTTPException(status_code=502, detail=message) from exc
        _cache = (time.monotonic(), result)
        return result
