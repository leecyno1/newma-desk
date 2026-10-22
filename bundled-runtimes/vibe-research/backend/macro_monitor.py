"""Lightweight macro monitor for the integrated Research domain.

The adapter normalizes public macro series and upcoming economic events.  It
does not make allocation calls, persist data, start workers, or own model
configuration.  Optional keyed sources degrade to public read-only fallbacks.
"""

from __future__ import annotations

import calendar
import csv
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
from io import StringIO
import json
import math
import os
import re
import threading
import time
from typing import Any, Callable
from urllib.parse import urlencode
import urllib.request as http_request
from urllib.request import Request, urlopen

import astock


SCHEMA_VERSION = "newma-desk.macro-monitor.v1"
_CACHE: dict[str, tuple[float, Any]] = {}
_CACHE_LOCK = threading.RLock()


def _cached(key: str, ttl: int, fetch: Callable[[], Any]) -> Any:
    with _CACHE_LOCK:
        hit = _CACHE.get(key)
        if hit and time.time() - hit[0] < ttl:
            return hit[1]
    value = fetch()
    with _CACHE_LOCK:
        _CACHE[key] = (time.time(), value)
    return value


def _number(value: Any) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def _date(value: Any) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value or "").strip()[:10].replace("/", "-")
    try:
        return date.fromisoformat(text)
    except ValueError:
        return None


def _period_date(value: Any) -> date | None:
    """Parse both ISO dates and the Chinese month labels used by macro feeds."""
    parsed = _date(value)
    if parsed:
        return parsed
    text = str(value or "").strip()
    match = re.search(r"(\d{4})\D{0,4}(\d{1,2})", text)
    if not match:
        return None
    try:
        return date(int(match.group(1)), int(match.group(2)), 1)
    except ValueError:
        return None


def _freshness(release_date: date | None, today: date, max_age_days: int) -> dict[str, Any]:
    if not release_date:
        return {"status": "unknown"}
    age_days = max((today - release_date).days, 0)
    return {
        "status": "fresh" if age_days <= max_age_days else "stale",
        "ageDays": age_days,
    }


def _confidence(freshness: dict[str, Any], source_kind: str = "aggregator") -> dict[str, Any]:
    fresh = freshness.get("status") == "fresh"
    return {
        "level": "medium" if fresh else "low",
        "score": 0.72 if fresh and source_kind == "aggregator" else 0.5,
        "rationale": (
            "公开聚合数据且发布时间仍在合理更新窗口内；关键结论应回到原发布机构复核"
            if fresh
            else "数据发布时间偏旧或未知；仅适合识别研究方向，不应作为实时宏观判断"
        ),
    }


_INDICATORS: tuple[dict[str, Any], ...] = (
    {
        "id": "cn-pmi",
        "name": "中国官方制造业 PMI",
        "region": "CN",
        "category": "growth",
        "unit": "index",
        "function": "macro_china_pmi_yearly",
        "maxAgeDays": 50,
        "source": "jin10-macro",
        "sourceLabel": "金十宏观数据聚合",
        "sourceUrl": "https://datacenter.jin10.com/reportType/dc_chinese_manufacturing_pmi",
    },
    {
        "id": "cn-gdp-yoy",
        "name": "中国 GDP 单季同比",
        "region": "CN",
        "category": "growth",
        "unit": "%",
        "function": "macro_china_gdp_yearly",
        "maxAgeDays": 140,
        "source": "jin10-macro",
        "sourceLabel": "金十宏观数据聚合",
        "sourceUrl": "https://datacenter.jin10.com/reportType/dc_chinese_gdp_yoy",
    },
    {
        "id": "cn-cpi-yoy",
        "name": "中国 CPI 同比",
        "region": "CN",
        "category": "inflation",
        "unit": "%",
        "function": "macro_china_cpi_yearly",
        "maxAgeDays": 50,
        "source": "jin10-macro",
        "sourceLabel": "金十宏观数据聚合",
        "sourceUrl": "https://datacenter.jin10.com/reportType/dc_chinese_cpi_yoy",
    },
    {
        "id": "cn-ppi-yoy",
        "name": "中国 PPI 同比",
        "region": "CN",
        "category": "inflation",
        "unit": "%",
        "function": "macro_china_ppi_yearly",
        "maxAgeDays": 50,
        "source": "jin10-macro",
        "sourceLabel": "金十宏观数据聚合",
        "sourceUrl": "https://datacenter.jin10.com/reportType/dc_chinese_ppi_yoy",
    },
    {
      "id": "cn-m2-yoy",
        "name": "中国 M2 同比",
        "region": "CN",
        "category": "liquidity",
        "unit": "%",
        "function": "macro_china_m2_yearly",
        "maxAgeDays": 55,
        "source": "jin10-macro",
        "sourceLabel": "金十宏观数据聚合",
      "sourceUrl": "https://datacenter.jin10.com/reportType/dc_chinese_m2_money_supply_yoy",
    },
    {
        "id": "cn-industrial-production-yoy",
        "name": "中国规模以上工业增加值",
        "region": "CN",
        "category": "growth",
        "unit": "%",
        "function": "macro_china_industrial_production_yoy",
        "maxAgeDays": 55,
        "source": "jin10-macro",
        "sourceLabel": "金十工业增加值",
        "sourceUrl": "https://datacenter.jin10.com/reportType/dc_chinese_industrial_production_yoy",
    },
    {
        "id": "cn-exports-yoy",
        "name": "中国出口同比",
        "region": "CN",
        "category": "trade",
        "unit": "%",
        "function": "macro_china_exports_yoy",
        "maxAgeDays": 55,
        "source": "jin10-macro",
        "sourceLabel": "金十贸易数据",
        "sourceUrl": "https://datacenter.jin10.com/reportType/dc_chinese_exports_yoy",
    },
    {
        "id": "cn-lpr-1y",
        "name": "中国 1 年期 LPR",
        "region": "CN",
        "category": "liquidity",
        "unit": "%",
        "function": "macro_china_lpr",
        "maxAgeDays": 45,
        "source": "eastmoney-lpr",
        "sourceLabel": "东方财富 LPR 数据",
        "sourceUrl": "https://data.eastmoney.com/cjsj/globalRateLPR.html",
        "kind": "lpr",
    },
    {
        "id": "us-cpi-yoy",
        "name": "美国 CPI 同比",
        "region": "US",
        "category": "inflation",
        "unit": "%",
        "function": "macro_usa_cpi_yoy",
        "maxAgeDays": 50,
        "source": "eastmoney-us-macro",
        "sourceLabel": "东方财富美国宏观数据",
        "sourceUrl": "https://data.eastmoney.com/cjsj/foreign_0_12.html",
        "kind": "usa",
    },
    {
        "id": "us-unemployment-rate",
        "name": "美国失业率",
        "region": "US",
        "category": "labour",
        "unit": "%",
        "function": "macro_usa_unemployment_rate",
        "maxAgeDays": 50,
        "source": "jin10-macro",
        "sourceLabel": "金十美国失业率数据聚合",
        "sourceUrl": "https://datacenter.jin10.com/reportType/dc_usa_unemployment_rate",
    },
)

_TUSHARE_SERIES: tuple[dict[str, str], ...] = (
    # cn_pmi has no default columns; request the documented statistical fields.
    {"id": "cn-pmi", "api": "cn_pmi", "periodKey": "month", "valueKey": "pmi010000", "frequency": "month", "fields": "month,pmi010000"},
    {"id": "cn-gdp-yoy", "api": "cn_gdp", "periodKey": "quarter", "valueKey": "gdp_yoy", "frequency": "quarter"},
    {"id": "cn-cpi-yoy", "api": "cn_cpi", "periodKey": "month", "valueKey": "nt_yoy", "frequency": "month"},
    {"id": "cn-ppi-yoy", "api": "cn_ppi", "periodKey": "month", "valueKey": "ppi_yoy", "frequency": "month"},
    {"id": "cn-m2-yoy", "api": "cn_m", "periodKey": "month", "valueKey": "m2_yoy", "frequency": "month"},
)

_TUSHARE_CALENDAR_SERIES: tuple[dict[str, Any], ...] = (
    {
        "id": "cn-industrial-production-yoy",
        "queryKey": "CNY",
        "country": "中国",
        "currency": "CNY",
        "contains": ("中国规模以上工业增加值年率",),
        "excludes": ("年初至今",),
    },
    {
        "id": "cn-exports-yoy",
        "queryKey": "CNY",
        "country": "中国",
        "currency": "CNY",
        "contains": ("中国出口年率", "美元计价"),
        "excludes": (),
    },
    {
        "id": "us-unemployment-rate",
        "queryKey": "US",
        "country": "美国",
        "currency": "USD",
        "contains": ("美国失业率",),
        "excludes": ("U6",),
    },
)

_TUSHARE_SOURCE_URL = "https://tushare.pro/document/2"

# These monthly fields match the existing metrics (not YTD or forecast values).
# GDP is deliberately absent: RPT_ECONOMY_GDP.SUM_SAME is cumulative growth,
# whereas the legacy Jin10 series is single-quarter growth.
_EASTMONEY_SERIES = {
    "cn-pmi": ("RPT_ECONOMY_PMI", "MAKE_INDEX", "pmi"),
    "cn-cpi-yoy": ("RPT_ECONOMY_CPI", "NATIONAL_SAME", "cpi"),
    "cn-ppi-yoy": ("RPT_ECONOMY_PPI", "BASE_SAME", "ppi"),
    "cn-m2-yoy": ("RPT_ECONOMY_CURRENCY_SUPPLY", "BASIC_CURRENCY_SAME", "hbgyl"),
    "cn-industrial-production-yoy": ("RPT_ECONOMY_INDUS_GROW", "BASE_SAME", "gyzjz"),
    "cn-exports-yoy": ("RPT_ECONOMY_CUSTOMS", "EXIT_BASE_SAME", "hgjck"),
}


def _records(frame: Any) -> list[dict[str, Any]]:
    if frame is None or getattr(frame, "empty", True):
        return []
    return frame.to_dict("records")


def _tushare_client() -> Any | None:
    token = os.environ.get("TUSHARE_TOKEN", "").strip()
    if not token:
        return None
    try:
        import tushare as ts
    except ImportError:
        return None
    return ts.pro_api(token)


def _tushare_period(value: Any, frequency: str) -> tuple[str, date] | None:
    text = str(value or "").strip()
    if frequency == "quarter":
        match = re.fullmatch(r"(\d{4})Q([1-4])", text, re.IGNORECASE)
        if not match:
            return None
        year, quarter = int(match.group(1)), int(match.group(2))
        month = quarter * 3
        return f"{year}Q{quarter}", date(year, month, calendar.monthrange(year, month)[1])
    digits = re.sub(r"\D", "", text)
    if len(digits) < 6:
        return None
    year, month = int(digits[:4]), int(digits[4:6])
    if month < 1 or month > 12:
        return None
    return f"{year:04d}-{month:02d}", date(year, month, calendar.monthrange(year, month)[1])


def _normalize_period_series(
    indicator_config: dict[str, Any],
    series_config: dict[str, str],
    rows: list[dict[str, Any]],
    today: date,
    *,
    source: dict[str, Any],
) -> dict[str, Any] | None:
    normalized: list[dict[str, Any]] = []
    for row in rows:
        fields = {key.lower(): value for key, value in row.items()}
        period = _tushare_period(fields.get(series_config["periodKey"].lower()), series_config["frequency"])
        value = _number(fields.get(series_config["valueKey"].lower()))
        if period is None or value is None or period[1] > today:
            continue
        update_date = _date(fields.get(series_config["updateKey"].lower())) if series_config.get("updateKey") else None
        normalized.append({"period": period[0], "periodDate": period[1], "releaseDate": update_date, "value": value})
    if not normalized:
        return None
    normalized.sort(key=lambda item: item["periodDate"])
    latest = normalized[-1]
    previous = normalized[-2]["value"] if len(normalized) > 1 else None
    change = latest["value"] - previous if previous is not None else None
    # A recent database update must not make an old statistical period fresh.
    freshness = _freshness(latest["periodDate"], today, int(indicator_config["maxAgeDays"]))
    return {
        "id": indicator_config["id"],
        "name": indicator_config["name"],
        "region": indicator_config["region"],
        "category": indicator_config["category"],
        "unit": indicator_config["unit"],
        "period": latest["period"],
        "releaseDate": latest["releaseDate"].isoformat() if latest["releaseDate"] else None,
        "dateBasis": "source-update" if latest["releaseDate"] else "period",
        "value": latest["value"],
        "forecast": None,
        "previous": previous,
        "change": change,
        "direction": "higher" if change is not None and change > 0 else ("lower" if change is not None and change < 0 else "flat"),
        "source": source,
        "evidenceId": f"macro:{indicator_config['id']}:{source['id'].split('-')[0]}:{latest['period']}",
        "asOf": latest["releaseDate"].isoformat() if latest["releaseDate"] else latest["period"],
        "freshness": freshness,
        "confidence": {
            **_confidence(freshness),
            "rationale": "新鲜度按统计期判断；数据库更新不等于统计发布日期，关键结论仍需官方发布复核。",
        },
        "history": [{"period": item["period"], "value": item["value"]} for item in normalized[-12:]],
    }


def _normalize_tushare_series(indicator_config, series_config, rows, today):
    # cn_gdp.gdp_yoy is cumulative growth, unlike Jin10's single-quarter rate.
    # Keep the distinction visible and derive changes within the same series.
    if indicator_config["id"] == "cn-gdp-yoy":
        indicator_config = {**indicator_config, "name": "中国 GDP 累计同比"}
    return _normalize_period_series(indicator_config, series_config, rows, today, source={
        "id": f"tushare-{series_config['api']}", "label": "Tushare Pro 宏观序列", "url": _TUSHARE_SOURCE_URL,
    })


def _eastmoney_indicator(config: dict[str, Any], today: date) -> dict[str, Any] | None:
    report, field, page = _EASTMONEY_SERIES[config["id"]]

    def fetch():
        response = astock.em_get("https://datacenter-web.eastmoney.com/api/data/v1/get", params={
            "reportName": report, "columns": f"REPORT_DATE,TIME,{field}",
            "sortColumns": "REPORT_DATE", "sortTypes": "-1", "pageSize": "18", "pageNumber": "1",
        }, timeout=10)
        response.raise_for_status()
        payload = response.json()
        if not payload.get("success"):
            raise ValueError("东方财富宏观序列暂不可用")
        return (payload.get("result") or {}).get("data") or []

    rows = _cached(f"macro-eastmoney:{report}", 3600, fetch)
    return _normalize_period_series(config, {
        "periodKey": "REPORT_DATE", "valueKey": field, "frequency": "month",
    }, rows, today, source={
        "id": f"eastmoney-{report.lower()}", "label": "东方财富宏观统计聚合",
        "url": f"https://data.eastmoney.com/cjsj/{page}.html", "dataset": report, "field": field,
    })


def _metric_number(value: Any) -> float | None:
    if isinstance(value, str):
        value = value.strip().replace(",", "").removesuffix("%")
    return _number(value)


def _open_public_request(request: Request, *, timeout: int):
    proxies = http_request.getproxies()
    system_proxies = getattr(http_request, "getproxies_macosx_sysconf", None)
    # On macOS, NO_PROXY alone makes urllib skip the system proxy entirely.
    # Restore that default only when no explicit proxy is configured; retain
    # Desk's localhost bypass and never change the global opener or environment.
    if system_proxies and proxies and set(proxies) == {"no"}:
        proxies = {**system_proxies(), **proxies}
        return http_request.build_opener(http_request.ProxyHandler(proxies)).open(request, timeout=timeout)
    return urlopen(request, timeout=timeout)


def _normalize_unemployment(config, rows, today, source):
    indicator = _normalize_period_series(
        {**config, "name": "美国失业率（U-3，季调）"},
        {"periodKey": "month", "valueKey": "value", "frequency": "month"},
        rows, today,
        source={**source, "seasonalAdjustment": "seasonally-adjusted", "population": "16岁及以上平民劳动力"},
    )
    if indicator:
        indicator["revisionStatus"] = "not-tracked"
        fresh = indicator["freshness"]["status"] == "fresh"
        indicator["confidence"] = {
            "level": "high" if fresh else "low", "score": 0.9 if fresh else 0.5,
            "rationale": "BLS 官方 U-3 月度统计，可能由 FRED 转发；新鲜度按统计月份判断。未提供发布日期，不推算发布日期；历史值可能修订。",
        }
    return indicator


def _bls_unemployment_indicator(config: dict[str, Any], today: date) -> dict[str, Any] | None:
    """BLS household survey: U-3, age 16+, monthly, seasonally adjusted."""
    series_id = "LNS14000000"

    def fetch():
        request = Request(
            "https://api.bls.gov/publicAPI/v2/timeseries/data/",
            data=json.dumps({
                "seriesid": [series_id], "startyear": str(today.year - 1), "endyear": str(today.year),
            }).encode(),
            headers={"Content-Type": "application/json", "User-Agent": "Newma-Desk/1.0"},
        )
        with _open_public_request(request, timeout=10) as response:
            payload = json.load(response)
        if payload.get("status") != "REQUEST_SUCCEEDED":
            raise ValueError("BLS 官方失业率接口暂不可用或已达查询限额")
        return next((series.get("data", []) for series in payload.get("Results", {}).get("series", [])
                     if series.get("seriesID") == series_id), [])

    # Unregistered BLS access has a daily request limit; one shared 6-hour cache
    # serves all calendar ranges and limits each request to two calendar years.
    rows = _cached(f"macro-bls:{series_id}:{today.year}", 6 * 3600, fetch)
    monthly_rows = [
        {"month": f"{row.get('year')}{row['period'][1:]}", "value": row.get("value")}
        for row in rows if re.fullmatch(r"M(0[1-9]|1[0-2])", str(row.get("period", "")))
    ]
    return _normalize_unemployment(config, monthly_rows, today, {
        "id": "bls-unemployment", "label": "美国劳工统计局 BLS",
        "url": f"https://data.bls.gov/timeseries/{series_id}", "seriesId": series_id,
        "fallbackReason": "Tushare 未返回有效期内的实际值，使用 BLS 官方 U-3 季调月度序列。",
    })


def _fred_unemployment_indicator(config: dict[str, Any], today: date) -> dict[str, Any] | None:
    """FRED UNRATE republishes BLS LNS14000000 (not the non-seasonal UNRATENSA)."""
    start = date(today.year - 1, 1, 1)

    def fetch():
        query = urlencode({"id": "UNRATE", "cosd": start.isoformat(), "coed": today.isoformat()})
        request = Request(f"https://fred.stlouisfed.org/graph/fredgraph.csv?{query}",
                          headers={"Accept": "text/csv", "User-Agent": "Newma-Desk/1.0"})
        with _open_public_request(request, timeout=10) as response:
            reader = csv.DictReader(StringIO(response.read().decode("utf-8-sig")))
        if not reader.fieldnames or not {"observation_date", "UNRATE"}.issubset(reader.fieldnames):
            raise ValueError("FRED 未返回 UNRATE 月度数据，不能将错误页当成观测值")
        rows = []
        for row in reader:
            period = _date(row["observation_date"])
            value = _number(row["UNRATE"])
            if period and start <= period <= today and value is not None:
                rows.append({"month": period.strftime("%Y%m"), "value": value})
        if not rows:
            raise ValueError("FRED UNRATE 未返回有效月度观测")
        return rows

    rows = _cached(f"macro-fred:UNRATE:{today.year}", 6 * 3600, fetch)
    return _normalize_unemployment(config, rows, today, {
        "id": "fred-unemployment", "label": "FRED · BLS 失业率",
        "url": "https://fred.stlouisfed.org/series/UNRATE", "seriesId": "UNRATE",
        "originalSource": "美国劳工统计局 BLS", "originalSeriesId": "LNS14000000",
        "fallbackReason": "Tushare 与 BLS 直连均未取得有效期内的数据，使用 FRED 转发的同口径 U-3 季调月度序列；不是独立调查。",
    })


def _fred_cpi_indicator(config: dict[str, Any], today: date) -> dict[str, Any] | None:
    """BLS all-items CPI-U, not seasonally adjusted; derive 12-month change."""
    series_id = "CPIAUCNS"
    start = date(today.year - 2, 1, 1)

    def fetch():
        query = urlencode({"id": series_id, "cosd": start.isoformat(), "coed": today.isoformat()})
        request = Request(f"https://fred.stlouisfed.org/graph/fredgraph.csv?{query}",
                          headers={"Accept": "text/csv", "User-Agent": "Newma-Desk/1.0"})
        with _open_public_request(request, timeout=10) as response:
            reader = csv.DictReader(StringIO(response.read().decode("utf-8-sig")))
        if not reader.fieldnames or not {"observation_date", series_id}.issubset(reader.fieldnames):
            raise ValueError("FRED 未返回 CPIAUCNS 月度指数，不能将错误页当成观测值")
        levels = {}
        for row in reader:
            period = _date(row["observation_date"])
            value = _number(row[series_id])
            if period and start <= period <= today and value is not None and value > 0:
                levels[(period.year, period.month)] = value
        if not levels:
            raise ValueError("FRED CPIAUCNS 未返回有效月度观测")
        return levels

    levels = _cached(f"macro-fred:{series_id}:{today.year}", 6 * 3600, fetch)
    rates = []
    for (year, month), current in sorted(levels.items()):
        prior = levels.get((year - 1, month))
        if prior is None or prior <= 0:
            continue
        rates.append({"month": f"{year:04d}{month:02d}", "value": round((current / prior - 1) * 100, 1)})
    indicator = _normalize_period_series(
        {**config, "name": "美国 CPI 同比（CPI-U，未经季调）"},
        {"periodKey": "month", "valueKey": "value", "frequency": "month"},
        rates, today,
        source={
            "id": "fred-cpi", "label": "FRED · BLS CPI-U", "url": "https://fred.stlouisfed.org/series/CPIAUCNS",
            "seriesId": series_id, "originalSource": "美国劳工统计局 BLS", "originalSeriesId": "CUUR0000SA0",
            "seasonalAdjustment": "not-seasonally-adjusted",
            "calculation": "同月指数比上年同月指数减 1，四舍五入至 0.1 个百分点",
            "fallbackReason": "使用 FRED 转发的 BLS CPI-U 全项目未经季调指数计算同比；不是独立调查。",
        },
    )
    if indicator:
        history = indicator["history"]
        if len(history) > 1:
            latest_month = date.fromisoformat(history[-1]["period"] + "-01")
            previous_month = date.fromisoformat(history[-2]["period"] + "-01")
            if (latest_month.year * 12 + latest_month.month) - (previous_month.year * 12 + previous_month.month) != 1:
                indicator.update(previous=None, change=None, direction="flat")
        indicator["revisionStatus"] = "not-tracked"
        indicator["confidence"] = {
            **_confidence(indicator["freshness"]),
            "rationale": "FRED 转发 BLS 官方指数；同比由同月指数计算。发布日期和历史修订版本未由此公开 CSV 提供，不得推算。",
        }
    return indicator


def _normalize_tushare_calendar_series(
    indicator_config: dict[str, Any],
    series_config: dict[str, Any],
    rows: list[dict[str, Any]],
    today: date,
) -> dict[str, Any] | None:
    by_release: dict[date, dict[str, Any]] = {}
    for row in rows:
        title = str(row.get("event") or "")
        if not all(part in title for part in series_config["contains"]):
            continue
        if any(part in title for part in series_config["excludes"]):
            continue
        release = _date(row.get("date"))
        if release is None or release > today:
            continue
        explicit = _metric_number(row.get("value"))
        # pre_value is the previous observation, never the current actual.
        if explicit is None:
            continue
        candidate = {
            "releaseDate": release,
            "value": explicit,
            "previous": _metric_number(row.get("pre_value")),
            "forecast": _metric_number(row.get("fore_value")),
            "explicit": explicit is not None,
        }
        current = by_release.get(release)
        if current is None or (candidate["explicit"] and not current["explicit"]):
            by_release[release] = candidate
    normalized = [by_release[key] for key in sorted(by_release)]
    if not normalized:
        return None
    latest = normalized[-1]
    previous = latest["previous"]
    if previous is None and len(normalized) > 1:
        previous = normalized[-2]["value"]
    change = latest["value"] - previous if previous is not None else None
    freshness = _freshness(latest["releaseDate"], today, int(indicator_config["maxAgeDays"]))
    release_text = latest["releaseDate"].isoformat()
    return {
        "id": indicator_config["id"],
        "name": indicator_config["name"],
        "region": indicator_config["region"],
        "category": indicator_config["category"],
        "unit": indicator_config["unit"],
        "period": release_text,
        "releaseDate": release_text,
        "dateBasis": "release",
        "value": latest["value"],
        "forecast": latest["forecast"],
        "previous": previous,
        "change": change,
        "direction": "higher" if change is not None and change > 0 else ("lower" if change is not None and change < 0 else "flat"),
        "source": {"id": "tushare-eco-cal", "label": "Tushare Pro 经济日历", "url": _TUSHARE_SOURCE_URL},
        "evidenceId": f"macro:{indicator_config['id']}:tushare:{release_text}",
        "asOf": release_text,
        "freshness": freshness,
        "confidence": _confidence(freshness),
        "history": [{"period": item["releaseDate"].isoformat(), "value": item["value"]} for item in normalized[-12:]],
    }


def _month_windows(today: date) -> list[tuple[date, date]]:
    current_start = today.replace(day=1)
    previous_end = current_start - timedelta(days=1)
    return [(previous_end.replace(day=1), previous_end), (current_start, today)]


def _first_two_fridays(month_start: date) -> list[date]:
    offset = (calendar.FRIDAY - month_start.weekday()) % 7
    first = month_start + timedelta(days=offset)
    return [first, first + timedelta(days=7)]


def _load_tushare_indicators(today: date) -> tuple[dict[str, dict[str, Any]], list[str], str]:
    client = _tushare_client()
    if client is None:
        reason = "未配置 TUSHARE_TOKEN" if not os.environ.get("TUSHARE_TOKEN", "").strip() else "未安装 Tushare SDK"
        return {}, [reason], "unsupported"
    configs = {item["id"]: item for item in _INDICATORS}
    indicators: dict[str, dict[str, Any]] = {}
    errors: list[str] = []
    for series in _TUSHARE_SERIES:
        try:
            if series["frequency"] == "quarter":
                params = {"start_q": f"{today.year - 3}Q1", "end_q": f"{today.year}Q{((today.month - 1) // 3) + 1}"}
            else:
                params = {"start_m": f"{today.year - 2}01", "end_m": f"{today.year}{today.month:02d}"}
            if series.get("fields"):
                params["fields"] = series["fields"]
            frame = _cached(
                f"tushare:{series['api']}:{params}",
                6 * 3600,
                lambda api=series["api"], params=params: client.query(api, **params),
            )
            indicator = _normalize_tushare_series(configs[series["id"]], series, _records(frame), today)
            if indicator:
                indicators[series["id"]] = indicator
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{series['id']}: {exc}")

    calendar_rows: dict[str, list[dict[str, Any]]] = {"CNY": [], "US": []}
    for start, end in _month_windows(today):
        try:
            frame = _cached(
                f"tushare:eco-cal:CNY:{start}:{end}",
                6 * 3600,
                lambda start=start, end=end: client.query(
                    "eco_cal", start_date=start.strftime("%Y%m%d"), end_date=end.strftime("%Y%m%d"), currency="CNY"
                ),
            )
            calendar_rows["CNY"].extend(_records(frame))
        except Exception as exc:  # noqa: BLE001
            errors.append(f"eco-cal-CNY: {exc}")
            break
    for month_start, _ in _month_windows(today):
        for release_day in _first_two_fridays(month_start):
            if release_day > today:
                continue
            try:
                frame = _cached(
                    f"tushare:eco-cal:US:{release_day}",
                    6 * 3600,
                    lambda release_day=release_day: client.query(
                        "eco_cal", start_date=release_day.strftime("%Y%m%d"), end_date=release_day.strftime("%Y%m%d"), currency="USD"
                    ),
                )
                calendar_rows["US"].extend(_records(frame))
            except Exception as exc:  # noqa: BLE001
                errors.append(f"eco-cal-US: {exc}")
                break
    for series in _TUSHARE_CALENDAR_SERIES:
        indicator = _normalize_tushare_calendar_series(
            configs[series["id"]], series, calendar_rows[series["queryKey"]], today
        )
        if indicator:
            indicators[series["id"]] = indicator
    return indicators, errors, "ok" if indicators else "unavailable"


def _normalize_standard_indicator(config: dict[str, Any], rows: list[dict[str, Any]], today: date) -> dict[str, Any] | None:
    normalized: list[dict[str, Any]] = []
    next_release: date | None = None
    for row in rows:
        release = _date(row.get("日期") or row.get("发布日期") or row.get("时间"))
        actual = _number(row.get("今值") if "今值" in row else row.get("现值"))
        if release is None or release > today or actual is None:
            if release and release >= today and (next_release is None or release < next_release):
                next_release = release
            continue
        normalized.append({
            "period": release.isoformat() if release else str(row.get("日期") or ""),
            "releaseDate": release,
            "value": actual,
            "forecast": _number(row.get("预测值")),
            "previous": _number(row.get("前值")),
        })
    if not normalized:
        return None
    normalized.sort(key=lambda item: item["releaseDate"])
    latest = normalized[-1]
    release_date = latest["releaseDate"]
    freshness = _freshness(release_date, today, int(config["maxAgeDays"]))
    previous = latest["previous"]
    change = latest["value"] - previous if previous is not None else None
    return {
        "id": config["id"],
        "name": config["name"],
        "region": config["region"],
        "category": config["category"],
        "unit": config["unit"],
        "period": latest["period"],
        "releaseDate": release_date.isoformat() if release_date else None,
        **({"nextReleaseDate": next_release.isoformat()} if next_release else {}),
        "value": latest["value"],
        "forecast": latest["forecast"],
        "previous": previous,
        "change": change,
        "direction": "higher" if change and change > 0 else ("lower" if change and change < 0 else "flat"),
        "source": {
            "id": config["source"],
            "label": config["sourceLabel"],
            "url": config["sourceUrl"],
        },
        "evidenceId": f"macro:{config['id']}:{latest['period']}",
        "asOf": release_date.isoformat() if release_date else latest["period"],
        "freshness": freshness,
        "confidence": _confidence(freshness),
        "history": [
            {"period": row["period"], "value": row["value"]}
            for row in normalized[-12:]
        ],
    }


def _normalize_lpr_indicator(config: dict[str, Any], rows: list[dict[str, Any]], today: date) -> dict[str, Any] | None:
    normalized = [
        {
            "period": release.isoformat(),
            "releaseDate": release,
            "value": value,
        }
        for row in rows
        if (release := _date(row.get("TRADE_DATE")))
        and release <= today
        and (value := _number(row.get("LPR1Y"))) is not None
    ]
    if not normalized:
        return None
    normalized.sort(key=lambda item: item["releaseDate"])
    latest = normalized[-1]
    previous_value = normalized[-2]["value"] if len(normalized) > 1 else None
    freshness = _freshness(latest["releaseDate"], today, int(config["maxAgeDays"]))
    change = latest["value"] - previous_value if previous_value is not None else None
    return {
        "id": config["id"],
        "name": config["name"],
        "region": config["region"],
        "category": config["category"],
        "unit": config["unit"],
        "period": latest["period"],
        "releaseDate": latest["period"],
        "value": latest["value"],
        "forecast": None,
        "previous": previous_value,
        "change": change,
        "direction": "higher" if change and change > 0 else ("lower" if change and change < 0 else "flat"),
        "source": {
            "id": config["source"],
            "label": config["sourceLabel"],
            "url": config["sourceUrl"],
        },
        "evidenceId": f"macro:{config['id']}:{latest['period']}",
        "asOf": latest["period"],
        "freshness": freshness,
        "confidence": _confidence(freshness),
        "history": [
            {"period": row["period"], "value": row["value"]}
            for row in normalized[-12:]
        ],
    }


def _normalize_usa_indicator(config: dict[str, Any], rows: list[dict[str, Any]], today: date) -> dict[str, Any] | None:
    converted = [
        {
            "日期": row.get("发布日期") or row.get("时间"),
            "今值": row.get("现值"),
            "预测值": None,
            "前值": row.get("前值"),
        }
        for row in rows
    ]
    return _normalize_standard_indicator(config, converted, today)


def _load_indicators(today: date) -> tuple[list[dict[str, Any]], dict[str, Any], list[dict[str, str]]]:
    candidates: dict[str, list[dict[str, Any]]] = {config["id"]: [] for config in _INDICATORS}
    gaps: list[dict[str, str]] = []
    tushare_indicators, tushare_errors, tushare_status = _load_tushare_indicators(today)
    errors = [f"tushare {error}" for error in tushare_errors]
    for indicator_id, indicator in tushare_indicators.items():
        candidates[indicator_id].append(indicator)

    def fetch(config: dict[str, Any]):
        choices = candidates[config["id"]]
        source_errors = []
        if config["id"] == "us-cpi-yoy":
            try:
                indicator = _fred_cpi_indicator(config, today)
                if indicator:
                    choices.append(indicator)
                    if indicator["freshness"]["status"] == "fresh":
                        return source_errors
            except Exception as exc:  # noqa: BLE001 - retain the available aggregator when FRED fails
                source_errors.append(f"fred {config['id']}: {exc}")
        if config["id"] == "us-unemployment-rate" and any(item["freshness"]["status"] == "fresh" for item in choices):
            try:
                indicator = _fred_unemployment_indicator(config, today)
                if indicator:
                    choices.append(indicator)
                    if indicator["freshness"]["status"] == "fresh":
                        return source_errors
            except Exception as exc:  # noqa: BLE001 - retain the available aggregator when FRED fails
                source_errors.append(f"fred {config['id']}: {exc}")
        if any(item["freshness"]["status"] == "fresh" for item in choices):
            return source_errors
        if config["id"] == "us-unemployment-rate":
            for provider, adapter in (("bls", _bls_unemployment_indicator), ("fred", _fred_unemployment_indicator)):
                try:
                    indicator = adapter(config, today)
                    if indicator:
                        choices.append(indicator)
                        if indicator["freshness"]["status"] == "fresh":
                            return source_errors
                except Exception as exc:  # noqa: BLE001 - retain the legacy fallback
                    source_errors.append(f"{provider} {config['id']}: {exc}")
        if config["id"] in _EASTMONEY_SERIES:
            try:
                indicator = _eastmoney_indicator(config, today)
                if indicator:
                    choices.append(indicator)
                    if indicator["freshness"]["status"] == "fresh":
                        return source_errors
            except Exception as exc:  # noqa: BLE001 - retain the legacy fallback
                source_errors.append(f"eastmoney {config['id']}: {exc}")
        try:
            frame = _cached(
                f"macro-indicator:{config['function']}",
                6 * 3600,
                lambda function=config["function"]: astock.akshare_parallel_call(function),
            )
            rows = _records(frame)
            if config.get("kind") == "lpr":
                indicator = _normalize_lpr_indicator(config, rows, today)
            elif config.get("kind") == "usa":
                indicator = _normalize_usa_indicator(config, rows, today)
            else:
                indicator = _normalize_standard_indicator(config, rows, today)
            if indicator:
                choices.append(indicator)
        except Exception as exc:  # noqa: BLE001 - normalization status is part of the contract
            source_errors.append(f"akshare {config['id']}: {exc}")
        return source_errors

    with ThreadPoolExecutor(max_workers=5) as pool:
        for source_errors in pool.map(fetch, _INDICATORS):
            errors.extend(source_errors)

    freshness_rank = {"fresh": 2, "unknown": 1, "stale": 0}
    indicators: list[dict[str, Any]] = []
    for config in _INDICATORS:
        choices = candidates[config["id"]]
        if not choices:
            gaps.append({"capability": config["id"], "reason": "source_unavailable"})
            continue
        selected = max(
            choices,
            key=lambda item: (
                freshness_rank.get(item.get("freshness", {}).get("status"), -1),
                2 if str(item.get("source", {}).get("id", "")).startswith("bls-") else
                1 if str(item.get("source", {}).get("id", "")).startswith("fred-") else 0,
                -item.get("freshness", {}).get("ageDays", 10_000),
                1 if str(item.get("source", {}).get("id", "")).startswith("tushare-") else 0,
            ),
        )
        if not selected["source"]["id"].startswith("tushare-"):
            selected["source"].setdefault("fallbackReason", "Tushare 未返回有效期内的同口径数据，使用公开来源并保留原始数据期。")
        indicators.append(selected)
        if selected["freshness"]["status"] != "fresh":
            gaps.append({"capability": config["id"], "reason": f"{config['name']}最新可用记录为 {selected['period']}，仅供历史参考"})

    generated_at = datetime.now(timezone.utc).isoformat()
    fresh_count = sum(item["freshness"].get("status") == "fresh" for item in indicators)
    status = "ok" if fresh_count == len(_INDICATORS) else ("partial" if indicators else "unavailable")
    source = {
        "id": "public-macro-aggregators",
        "label": "美国 BLS/FRED 统计 · 中国 Tushare/公开源聚合",
        "status": status,
        "count": len(indicators),
        "asOf": generated_at,
        "coverage": {
            "regions": sorted({item["region"] for item in indicators}),
            "fresh": fresh_count,
            "stale": sum(item["freshness"].get("status") == "stale" for item in indicators),
            "unknown": sum(item["freshness"].get("status") == "unknown" for item in indicators),
            "officialDirect": sum(item["source"]["id"].startswith("bls-") for item in indicators),
            "officialRedistributed": sum(item["source"]["id"].startswith("fred-") for item in indicators),
            "aggregated": sum(not item["source"]["id"].startswith(("bls-", "fred-")) for item in indicators),
            "tushare": tushare_status,
        },
        **({"error": "; ".join(errors)[:600]} if errors else {}),
    }
    return indicators, source, gaps


_LIQUIDITY_FUNCTIONS = (
    "macro_china_shibor_all",
    "macro_china_money_supply",
    "macro_china_new_financial_credit",
    "macro_china_market_margin_sh",
    "macro_china_market_margin_sz",
    "macro_stock_finance",
)


def _series_rows(frame: Any, date_key: str, value_key: str, *, scale: float = 1.0) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row in _records(frame):
        period = _period_date(row.get(date_key))
        value = _number(row.get(value_key))
        if period is None or value is None:
            continue
        rows.append({"period": period, "value": value * scale})
    return sorted(rows, key=lambda item: item["period"])


def _liquidity_item(
    *,
    item_id: str,
    name: str,
    unit: str,
    rows: list[dict[str, Any]],
    today: date,
    source_id: str,
    source_label: str,
    source_url: str,
    max_age_days: int,
    effect: str,
    frequency: str = "day",
) -> dict[str, Any] | None:
    if frequency == "month":
        rows = [{**row, "period": row["period"].replace(day=calendar.monthrange(row["period"].year, row["period"].month)[1])} for row in rows]
    # Source frames may include future calendar rows or duplicate periods. Neither
    # is an observed value that can enter today's assessment. Monthly values
    # are comparable only after their statistical period has ended.
    cutoff = today - timedelta(days=1) if frequency == "month" else today
    observed = sorted({row["period"]: row for row in rows if row["period"] <= cutoff}.values(), key=lambda row: row["period"])
    if not observed:
        return None
    latest = observed[-1]
    previous = observed[-2]["value"] if len(observed) > 1 else None
    change = latest["value"] - previous if previous is not None else None
    freshness = _freshness(latest["period"], today, max_age_days)
    return {
        "id": item_id,
        "name": name,
        "unit": unit,
        "value": round(latest["value"], 4),
        "previous": round(previous, 4) if previous is not None else None,
        "change": round(change, 4) if change is not None else None,
        "direction": "higher" if change is not None and change > 0 else ("lower" if change is not None and change < 0 else "flat"),
        "effect": effect,
        "period": latest["period"].strftime("%Y-%m") if frequency == "month" else latest["period"].isoformat(),
        "periodEnd": latest["period"].isoformat(),
        "frequency": frequency,
        "dateBasis": "period-end" if frequency == "month" else "observation-date",
        "asOf": latest["period"].isoformat(),
        "source": {"id": source_id, "label": source_label, "url": source_url},
        "freshness": freshness,
        "history": [{"period": row["period"].strftime("%Y-%m") if frequency == "month" else row["period"].isoformat(), "value": round(row["value"], 4)} for row in observed[-30:]],
    }


def _liquidity_assessment(indicators: list[dict[str, Any]]) -> dict[str, Any]:
    """Observed marginal evidence only; no mixed-frequency level forecast."""
    comparable = {"cn-m2-yoy", "cn-m1-yoy", "cn-shibor-on", "cn-shibor-1w", "cn-shibor-3m"}
    items = []
    supportive = restrictive = 0
    for item in indicators:
        if item["id"] not in comparable or item["freshness"]["status"] != "fresh" or item.get("change") is None:
            continue
        change = item["change"]
        effect = item["effect"]
        vote = "flat" if change == 0 else (
            "supportive" if (effect == "supportive" and change > 0) or (effect == "restrictive" and change < 0)
            else "restrictive"
        )
        supportive += vote == "supportive"
        restrictive += vote == "restrictive"
        items.append({"id": item["id"], "name": item["name"], "period": item["period"], "change": change, "unit": item["unit"], "vote": vote})
    has_quantity = any(item["id"] in {"cn-m1-yoy", "cn-m2-yoy"} for item in items)
    has_price = any(item["id"].startswith("cn-shibor-") for item in items)
    return {
        "signal": ("supportive" if supportive > restrictive else ("restrictive" if restrictive > supportive else "mixed")) if has_quantity and has_price else "mixed",
        "complete": has_quantity and has_price,
        "supportiveCount": supportive,
        "restrictiveCount": restrictive,
        "observedCount": len(items),
        "method": "仅比较有效期内的 M1/M2 同比与 SHIBOR 各自前一观测；货币数量和资金价格任一维度缺失时只报分化/证据不足。月频和日频不外推、不合成预测值。新增社融、融资额受季节性影响，两融与 M2-M1 差仅作旁证。",
        "items": items,
    }


def _load_liquidity(today: date) -> dict[str, Any]:
    frames: dict[str, Any] = {}

    def fetch(function_name: str) -> tuple[str, Any | None]:
        try:
            return function_name, _cached(
                f"liquidity:{function_name}",
                6 * 3600,
                lambda: astock.akshare_parallel_call(function_name),
            )
        except Exception:
            return function_name, None

    with ThreadPoolExecutor(max_workers=4) as pool:
        for function_name, frame in pool.map(fetch, _LIQUIDITY_FUNCTIONS):
            frames[function_name] = frame

    source_url = "https://data.eastmoney.com/cjsj/hbgyl.html"
    quantity: list[dict[str, Any]] = []
    price: list[dict[str, Any]] = []
    transmission: list[dict[str, Any]] = []

    shibor = frames.get("macro_china_shibor_all")
    for key, item_id, label in (("O/N-定价", "cn-shibor-on", "SHIBOR 隔夜"), ("1W-定价", "cn-shibor-1w", "SHIBOR 1 周"), ("3M-定价", "cn-shibor-3m", "SHIBOR 3 个月")):
        item = _liquidity_item(
            item_id=item_id, name=label, unit="%", rows=_series_rows(shibor, "日期", key), today=today,
            source_id="shibor", source_label="金十聚合 · SHIBOR", source_url="https://datacenter.jin10.com/reportType/dc_shibor", max_age_days=5, effect="restrictive",
        )
        if item: price.append(item)

    money = frames.get("macro_china_money_supply")
    m2_rows = _series_rows(money, "月份", "货币和准货币(M2)-同比增长")
    m1_rows = _series_rows(money, "月份", "货币(M1)-同比增长")
    for item_id, label, rows, effect in (
        ("cn-m2-yoy", "M2 同比", m2_rows, "supportive"),
        ("cn-m1-yoy", "M1 同比", m1_rows, "supportive"),
    ):
        item = _liquidity_item(item_id=item_id, name=label, unit="%", rows=rows, today=today, source_id="pbc-money-supply", source_label="东方财富聚合 · 货币供应量", source_url=source_url, max_age_days=55, effect=effect, frequency="month")
        if item: quantity.append(item)
    if m2_rows and m1_rows:
        m1_by_period = {row["period"]: row["value"] for row in m1_rows}
        spread_rows = [{"period": row["period"], "value": row["value"] - m1_by_period[row["period"]]} for row in m2_rows if row["period"] in m1_by_period]
        item = _liquidity_item(item_id="cn-m2-m1-spread", name="M2-M1 增速差", unit="百分点", rows=spread_rows, today=today, source_id="pbc-money-supply", source_label="东方财富聚合 · 货币供应量", source_url=source_url, max_age_days=55, effect="supportive", frequency="month")
        if item: quantity.append(item)

    credit = _series_rows(frames.get("macro_china_new_financial_credit"), "月份", "当月")
    item = _liquidity_item(item_id="cn-new-rmb-loans", name="新增人民币贷款", unit="亿元", rows=credit, today=today, source_id="pbc-rmb-loans", source_label="东方财富聚合 · 人民币信贷（非社融总量）", source_url="https://data.eastmoney.com/cjsj/xzxd.html", max_age_days=55, effect="supportive", frequency="month")
    if item: quantity.append(item)

    margin_frames = [_series_rows(frames.get(name), "日期", "融资融券余额") for name in ("macro_china_market_margin_sh", "macro_china_market_margin_sz")]
    margin_maps = [{row["period"]: row["value"] for row in rows} for rows in margin_frames]
    # A one-exchange observation is not a whole-market balance.
    common_dates = set(margin_maps[0]) & set(margin_maps[1])
    margin_by_date = {period: (margin_maps[0][period] + margin_maps[1][period]) / 100_000_000 for period in common_dates}
    item = _liquidity_item(item_id="cn-margin-balance", name="全市场两融余额", unit="亿元", rows=[{"period": period, "value": value} for period, value in sorted(margin_by_date.items())], today=today, source_id="margin-exchanges", source_label="金十聚合 · 沪深两融合计", source_url="https://datacenter.jin10.com/", max_age_days=5, effect="supportive")
    if item: transmission.append(item)

    financing = _series_rows(frames.get("macro_stock_finance"), "月份", "募集资金")
    item = _liquidity_item(item_id="cn-equity-financing", name="股票市场融资额", unit="亿元", rows=financing, today=today, source_id="csrc-equity-financing", source_label="同花顺聚合 · 股票市场融资", source_url="https://data.10jqka.com.cn/macro/finance/", max_age_days=55, effect="restrictive", frequency="month")
    if item: transmission.append(item)

    groups = [
        {"id": "quantity", "label": "货币与信用数量", "indicators": quantity},
        {"id": "price", "label": "资金价格", "indicators": price},
        {"id": "transmission", "label": "市场传导", "indicators": transmission},
    ]
    all_indicators = quantity + price + transmission
    return {
        "groups": groups,
        "indicators": all_indicators,
        "assessment": _liquidity_assessment(all_indicators),
        "coverage": {"available": len(all_indicators), "total": 9, "asOf": max((item["asOf"] for item in all_indicators), default=None)},
        "source": "AkShare 接入 · 东方财富 / 金十 / 同花顺聚合数据",
        "note": "月度序列仅比较已结束月份，月末为统计截止日而非已核验发布日期；日度序列保留观测日期。各序列比较各自前一有效观测，不代表统一时点或已核验原始公告。仅展示边际变化，不提供未经回测的短期预测。",
    }


def _importance(value: Any) -> str:
    text = str(value or "").strip().lower()
    if text in {"high", "3", "3.0"}:
        return "high"
    if text in {"medium", "2", "2.0"}:
        return "medium"
    return "low" if text in {"low", "1", "1.0"} else "unknown"


_CALENDAR_COUNTRIES = {
    "CN": "中国", "US": "美国", "EU": "欧元区", "DE": "德国", "FR": "法国",
    "IT": "意大利", "ES": "西班牙", "GB": "英国", "JP": "日本", "CA": "加拿大",
    "AU": "澳大利亚", "NZ": "新西兰", "CH": "瑞士", "KR": "韩国", "ZA": "南非",
    "HK": "中国香港", "MO": "中国澳门", "TW": "中国台湾", "BR": "巴西", "ID": "印度尼西亚",
    "IN": "印度", "IL": "以色列", "MX": "墨西哥", "SG": "新加坡", "NO": "挪威",
    "SE": "瑞典", "DK": "丹麦", "FI": "芬兰", "NL": "荷兰", "BE": "比利时", "AT": "奥地利",
    "IE": "爱尔兰", "PT": "葡萄牙", "PL": "波兰", "RU": "俄罗斯", "TR": "土耳其",
    "TH": "泰国", "MY": "马来西亚", "PH": "菲律宾",
}
_CALENDAR_REGION_ALIASES = {
    **{name: code for code, name in _CALENDAR_COUNTRIES.items()},
    "中国内地": "CN", "中国大陆": "CN", "香港": "HK", "澳门": "MO", "台湾": "TW",
    "印尼": "ID", "新西蘭": "NZ", "美联储": "US", "欧洲央行": "EU", "欧洲中央银行": "EU",
    "澳洲联储": "AU", "外国投资者对日本": "JP",
}
_CALENDAR_ENGLISH_REGIONS = {
    "united states": "US", "united kingdom": "GB", "china": "CN", "hong kong": "HK",
    "taiwan": "TW", "euro zone": "EU", "euro area": "EU", "eurozone": "EU", "japan": "JP",
    "canada": "CA", "australia": "AU", "new zealand": "NZ", "germany": "DE", "france": "FR",
}
_CALENDAR_EUROPE = {"EU", "DE", "FR", "IT", "ES", "GB", "CH", "NO", "SE", "DK", "FI", "NL", "BE", "AT", "IE", "PT", "PL", "RU", "TR"}


def _calendar_text(value):
    text = str(value).strip() if value is not None else ""
    return "" if text.lower() in {"none", "nan", "nat", "null", "-", "--", "—"} else text


def _calendar_region_code(value):
    if value.upper() in _CALENDAR_COUNTRIES:
        return value.upper()
    return _CALENDAR_REGION_ALIASES.get(value) or _CALENDAR_ENGLISH_REGIONS.get(value.lower())


def _calendar_region(row: dict[str, Any], title: str) -> dict[str, Any]:
    reported = next((_calendar_text(row.get(key)) for key in ("国家", "country", "地区") if _calendar_text(row.get(key))), "")
    source_code = _calendar_region_code(reported)
    title_code = next((code for name, code in sorted(_CALENDAR_REGION_ALIASES.items(), key=lambda item: len(item[0]), reverse=True)
                       if title.startswith(name)), None)
    basis = {"kind": "unknown", "reportedRegion": _CALENDAR_COUNTRIES.get(source_code),
             "titleRegion": _CALENDAR_COUNTRIES.get(title_code), "reason": "缺少明确地区；币种不能单独确认经济统计地区"}
    code = title_code or source_code
    if title.startswith(("石油输出国组织", "国际能源署", "国际货币基金组织", "世界银行")):
        code = "GLOBAL"
        basis.update(kind="title", reason="国际组织的跨国报告，不按来源币种归入单一国家")
    elif title_code and source_code and title_code != source_code:
        # The title can be corrupted too (e.g. the same Israel headline is
        # attached to several countries). Do not silently pick either claim.
        code = None
        basis.update(kind="conflict", reason="标题与来源地区不一致，保留双方口径，等待核验")
    elif source_code:
        basis.update(kind="source", reason="采用来源地区" if not title_code else "标题与来源地区一致")
    elif title_code:
        basis.update(kind="title", reason="来源地区未能识别，按标题明确地区归类")
    region = _CALENDAR_COUNTRIES.get(code, "跨国/国际组织" if code == "GLOBAL" else "地区待核验" if basis["kind"] == "conflict" else "地区未注明")
    group = "UNKNOWN" if not code else "EU" if code in _CALENDAR_EUROPE else code if code in {"CN", "HK", "MO", "TW", "US"} else "OTHER"
    return {"region": region, "regionCode": code, "regionGroup": group, "regionBasis": basis,
            "reportedCountry": reported[:80]}


def _calendar_time(raw_date, raw_time, release_date):
    clock = raw_time or (raw_date[11:] if len(raw_date) > 10 else "")
    basis = {"kind": "date-only", "timeZone": None, "timestamp": None,
             "note": "来源未提供可解析时刻，不代表午夜"}
    if re.fullmatch(r"\d{1,2}:\d{2}(?::\d{2})?(?:Z|[+-]\d{2}:\d{2})?", clock):
        try:
            hour, rest = clock.split(":", 1)
            parsed = datetime.fromisoformat(f"{release_date.isoformat()}T{int(hour):02d}:{rest}")
            if raw_time and len(raw_date) > 10:
                dated_time = datetime.fromisoformat(raw_date)
                if parsed.tzinfo is None and dated_time.tzinfo and parsed.time() == dated_time.time():
                    parsed = parsed.replace(tzinfo=dated_time.tzinfo)
        except ValueError:
            return None, basis
        display = parsed.strftime("%H:%M:%S" if parsed.second else "%H:%M")
        if parsed.tzinfo is not None:
            offset = parsed.strftime("%z")
            zone = f"UTC{offset[:3]}:{offset[3:]}"
            basis.update(kind="explicit-offset", timeZone=zone, timestamp=parsed.isoformat(timespec="seconds"),
                         note=f"采用来源显式偏移 {zone}，未转换为浏览器本地时间")
        else:
            basis.update(kind="unconfirmed", note="来源时刻，时区未注明；不能据此跨时区比较或判断事件已到期")
        return display, basis
    return None, basis


def _calendar_value(value: Any) -> tuple[float | None, str | None]:
    text = str(value).strip() if value is not None else ""
    if text.lower() in {"", "none", "nan", "null", "-", "--", "—"}:
        return None, None
    return _metric_number(value), text[:80]


_CALENDAR_IMPORTANCE_RULES = (
    ("policy-rate", "high", r"(?:美联储|欧洲央行|英国央行|日本央行|加拿大央行|澳洲联储|瑞士央行)?(?:利率决议|货币政策声明)|(?:中国央行)?贷款市场报价利率(?:\(LPR\))?", "央行政策利率或政策声明，建议优先关注"),
    ("inflation", "high", r"(?:核心|季调后|未季调|全国|调和)*(?:CPI|PCE|居民消费价格指数\(CPI\)|消费者物价指数\(CPI\)|个人消费支出物价指数\(PCE\))(?:年率|月率|指数)?", "全国性消费通胀指标，建议优先关注"),
    ("gdp", "high", r"(?:GDP|国内生产总值\(GDP\))(?:年率|季率|年化季率|季率年化|同比|增长率)(?:初值|修正值|终值)?", "全国性经济增长发布，建议优先关注"),
    ("employment", "high", r"(?:季调后)?(?:非农就业人口(?:变动)?|非农就业人数(?:变动)?|失业率)", "就业与失业率发布，建议优先关注"),
    ("pmi", "medium", r"(?:官方|财新|Markit|S&PGlobal|日经/Markit)?(?:制造业|服务业|综合)(?:PMI|采购经理人指数\(PMI\))(?:初值|终值)?", "景气调查，建议结合实际经济数据跟踪"),
    ("activity", "medium", r"(?:核心|季调后)?(?:零售销售|工业产出|规模以上工业增加值)(?:年率|月率|同比)|(?:核心)?PPI(?:年率|月率)|初请失业金人数", "生产、消费或周度就业指标，建议常规跟踪"),
)


def _calendar_importance(title, region, source_value):
    importance = _importance(source_value)
    if importance != "unknown":
        return importance, {"kind": "source", "reason": "沿用日历来源评级", "sourceValue": str(source_value)}
    # This is a Desk attention heuristic, not a rating from the data provider.
    # Only a small set of national releases is covered; all others stay unknown.
    if region in {"中国", "美国", "欧元区", "英国", "日本", "加拿大", "澳大利亚", "瑞士"}:
        name = re.sub(r"\s+", "", title).replace("（", "(").replace("）", ")").replace("％", "%")
        if name.startswith(region) and not name.startswith(f"{region}央行"):
            name = name[len(region):]
        name = re.sub(r"\((?:%|年度|月度|季度|同比|月度环比|[一二三四五六七八九十\d]+月|第[一二三四]季度)\)", "", name)
        for rule_id, level, pattern, reason in _CALENDAR_IMPORTANCE_RULES:
            if re.fullmatch(pattern, name, re.IGNORECASE):
                return level, {"kind": "rule", "ruleId": rule_id, "version": "1", "reason": reason}
    return "unknown", {"kind": "unknown", "reason": "来源未提供评级，且未命中 Desk 关注规则"}


def _calendar_event(row: dict[str, Any], source_id: str, source_label: str, source_url: str, today: date) -> dict[str, Any] | None:
    raw_date = _calendar_text(row.get("日期")) or _calendar_text(row.get("date"))
    release_date = _date(raw_date[:10])
    if not release_date:
        return None
    raw_time = _calendar_text(row.get("时间")) or _calendar_text(row.get("time"))
    clock, time_basis = _calendar_time(raw_date, raw_time, release_date)
    title = str(row.get("事件") or row.get("event") or "").strip()[:240]
    if not title:
        return None
    location = _calendar_region(row, title)
    region = location["region"]
    actual, actual_text = _calendar_value(row.get("公布") if "公布" in row else row.get("actual", row.get("value")))
    forecast, forecast_text = _calendar_value(row.get("预期") if "预期" in row else row.get("estimate", row.get("fore_value")))
    previous, previous_text = _calendar_value(row.get("前值") if "前值" in row else row.get("previous", row.get("pre_value")))
    if release_date > today:
        actual, actual_text = None, None
    importance, importance_basis = _calendar_importance(
        title, region, row.get("重要性") if "重要性" in row else row.get("impact"))
    currency = str(row.get("currency") or "").strip()[:12] or None
    region_identity = f"{region}:{location['reportedCountry']}" if location["regionGroup"] == "UNKNOWN" else region
    event_id = f"{source_id}:{release_date.isoformat()}:{clock or raw_time}:{time_basis['timeZone'] or ''}:{region_identity}:{currency or ''}:{title}"
    return {
        "id": event_id[:500],
        "date": release_date.isoformat(),
        "time": clock,
        "timeBasis": time_basis,
        "region": region,
        "regionCode": location["regionCode"],
        "regionGroup": location["regionGroup"],
        "regionBasis": location["regionBasis"],
        "currency": currency,
        "title": title,
        "importance": importance,
        "importanceBasis": importance_basis,
        "status": "released" if actual_text is not None else "scheduled",
        "actual": actual,
        "forecast": forecast,
        "previous": previous,
        "actualText": actual_text,
        "forecastText": forecast_text,
        "previousText": previous_text,
        "source": {"id": source_id, "label": source_label, "url": source_url,
                   "reportedCountry": location["reportedCountry"], "reportedRegion": _calendar_text(row.get("地区"))[:80],
                   "reportedDate": raw_date[:80], "reportedTime": raw_time[:80]},
        "evidenceId": f"macro-calendar:{event_id}"[:500],
        "asOf": datetime.now(timezone.utc).isoformat(),
    }


def _fmp_events(today: date, days: int, api_key: str) -> list[dict[str, Any]]:
    end = today + timedelta(days=days)
    query = urlencode({"from": today.isoformat(), "to": end.isoformat(), "apikey": api_key})
    request = Request(
        f"https://financialmodelingprep.com/api/v3/economic_calendar?{query}",
        headers={"Accept": "application/json", "User-Agent": "Newma-Desk/0.1"},
    )
    with _open_public_request(request, timeout=8) as response:  # noqa: S310 - fixed HTTPS origin
        payload = json.load(response)
    if not isinstance(payload, list):
        raise ValueError("FMP economic calendar returned an invalid payload")
    return payload


def _tushare_events(client: Any, today: date, days: int) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    previous_page = None
    # eco_cal enforces a 100-row page even when a larger limit is requested.
    for offset in range(0, 5000, 100):
        page = _records(client.query(
            "eco_cal", start_date=today.strftime("%Y%m%d"),
            end_date=(today + timedelta(days=days)).strftime("%Y%m%d"),
            limit=100, offset=offset,
        ))
        if page and page == previous_page:
            raise ValueError("Tushare 经济日历分页未推进，不能确认完整查询结果")
        rows.extend(page)
        if len(page) < 100:
            return rows
        previous_page = page
    raise ValueError("Tushare 经济日历超过本次查询上限，不能确认完整查询结果")


def _calendar_title_key(title):
    name = re.sub(r"\s+", "", title).replace("（", "(").replace("）", ")").replace("％", "%")
    # Only an explicit rate permits an omitted percent marker. Never strip
    # periods, money/quantity units, core/headline or revision qualifiers.
    if re.search(r"利率|年率|月率|失业率|比重|同比|环比", name):
        name = name.replace("(%)", "")
    return name.casefold()


def _calendar_value_key(text, title):
    value = text.replace(",", "").replace("％", "%").strip()
    if re.fullmatch(r"[+-]?\d+(?:\.\d+)?%?", value):
        unit = "%" if value.endswith("%") or re.search(r"利率|年率|月率|失业率|比重|同比|环比|\(%\)|（%）", title) else ""
        return (_metric_number(value), unit)
    return value


def _merge_calendar_records(records):
    # Pick one whole record: do not silently splice forecasts/actuals from
    # different variants into a synthetic release.
    selected = max(records, key=lambda item: (
        item["actualText"] is not None,
        sum(item[f"{field}Text"] is not None for field in ("actual", "forecast", "previous")),
        "%" in item["title"] or "％" in item["title"],
        item["title"],
    ))
    result = {**selected, "recordCount": len(records), "conflictFields": []}
    if len(records) == 1:
        return result
    result["records"] = records
    for field in ("actual", "forecast", "previous"):
        values = {_calendar_value_key(item[f"{field}Text"], item["title"]) for item in records if item[f"{field}Text"] is not None}
        if len(values) > 1:
            result["conflictFields"].append(field)
    source_ratings = {item["importance"] for item in records if item["importanceBasis"]["kind"] == "source"}
    if len(source_ratings) > 1:
        result["conflictFields"].append("importance")
        result["importance"] = "unknown"
        result["importanceBasis"] = {"kind": "unknown", "reason": "原始记录的来源评级冲突，请核验"}
    elif source_ratings:
        rated = next(item for item in records if item["importanceBasis"]["kind"] == "source")
        result["importance"], result["importanceBasis"] = rated["importance"], rated["importanceBasis"]
    return result


def _calendar_rows(rows, source_id, source_label, source_url, today, days):
    end = today + timedelta(days=days)
    groups = {}
    for row in rows:
        event = _calendar_event(row, source_id, source_label, source_url, today)
        if event and today.isoformat() <= event["date"] <= end.isoformat():
            title_key = _calendar_title_key(event["title"]) if event["time"] else event["title"]
            key = (event["date"], event["time"] or event["source"]["reportedTime"], event["timeBasis"]["timeZone"],
                   event["region"], event["source"]["reportedCountry"] if event["regionGroup"] == "UNKNOWN" else None,
                   event["currency"], title_key)
            groups.setdefault(key, []).append(event)
    return sorted((_merge_calendar_records(records) for records in groups.values()),
                  key=lambda item: (item["date"], item.get("time") or "", item["title"]))


def _calendar_coverage(today, days, queried_dates, events, source_id):
    requested = {(today + timedelta(days=offset)).isoformat() for offset in range(days + 1)}
    queried = set(queried_dates) & requested
    event_dates = {event["date"] for event in events}
    missing = sorted(requested - queried)
    return {
        "sourceId": source_id, "start": today.isoformat(), "end": (today + timedelta(days=days)).isoformat(),
        "requestedDays": len(requested), "queriedDays": len(queried), "eventDays": len(event_dates),
        "status": "queried" if not missing else "partial" if queried else "unavailable",
        "missingDates": missing, "emptyDates": sorted(queried - event_dates),
        "note": "覆盖表示已查询来源日程，不保证收录全部事件；空日期不等于没有事件。日期和时刻沿用来源；未注明时区的记录不可直接跨时区比较。",
    }


def _load_calendar(today: date, days: int) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, str]]]:
    events: list[dict[str, Any]] = []
    sources: list[dict[str, Any]] = []
    gaps: list[dict[str, str]] = []
    api_key = os.environ.get("FMP_API_KEY", "").strip()
    generated_at = datetime.now(timezone.utc).isoformat()
    all_dates = [(today + timedelta(days=offset)).isoformat() for offset in range(days + 1)]
    client = _tushare_client()
    if client is not None:
        try:
            rows = _cached(f"tushare-economic-calendar:{today}:{days}", 3600, lambda: _tushare_events(client, today, days))
            events = _calendar_rows(rows, "tushare-economic-calendar", "Tushare Pro 经济日历", "https://tushare.pro/document/2?doc_id=233", today, days)
            sources.append({
                "id": "tushare-economic-calendar", "label": "Tushare Pro 经济日历",
                "status": "ok" if events else "empty", "count": len(events), "asOf": generated_at,
                "coverage": _calendar_coverage(today, days, all_dates, events, "tushare-economic-calendar"),
            })
            return events, sources, gaps
        except Exception as exc:  # noqa: BLE001 - use the optional or public source
            sources.append({"id": "tushare-economic-calendar", "label": "Tushare Pro 经济日历",
                            "status": "unavailable", "count": 0, "asOf": generated_at, "error": str(exc)[:600]})
    else:
        sources.append({"id": "tushare-economic-calendar", "label": "Tushare Pro 经济日历",
                        "status": "unsupported", "count": 0, "asOf": generated_at,
                        "error": "Tushare 经济日历未配置或 SDK 不可用，尝试备用源"})

    if api_key:
        try:
            rows = _cached(
                f"fmp-economic-calendar:{today.isoformat()}:{days}",
                3600,
                lambda: _fmp_events(today, days, api_key),
            )
            events = _calendar_rows(rows, "fmp-economic-calendar", "Financial Modeling Prep Economic Calendar",
                                   "https://financialmodelingprep.com/developer/docs/economic-calendar-api", today, days)
            sources.append({
                "id": "fmp-economic-calendar",
                "label": "FMP 经济日历",
                "status": "ok" if events else "empty",
                "count": len(events),
                "asOf": generated_at,
                "coverage": _calendar_coverage(today, days, all_dates, events, "fmp-economic-calendar"),
            })
            return events, sources, gaps
        except Exception as exc:  # noqa: BLE001
            sources.append({
                "id": "fmp-economic-calendar",
                "label": "FMP 经济日历",
                "status": "unavailable",
                "count": 0,
                "asOf": generated_at,
                "error": str(exc).replace(api_key, "[redacted]")[:600],
            })
            gaps.append({"capability": "fmp-economic-calendar", "reason": "source_unavailable"})
    else:
        sources.append({
            "id": "fmp-economic-calendar",
            "label": "FMP 经济日历",
            "status": "unsupported",
            "count": 0,
            "asOf": generated_at,
            "error": "FMP_API_KEY 未配置，已使用公开日历降级源",
        })

    fallback_days = min(days, 14)
    errors: list[str] = []
    queried_dates: list[str] = []
    targets = [today + timedelta(days=offset) for offset in range(fallback_days + 1)]
    for target in targets:
        try:
            frame = _cached(
                f"baidu-economic-calendar:{target.isoformat()}",
                3600,
                lambda target=target: astock.akshare_parallel_call(
                    "news_economic_baidu",
                    date=target.strftime("%Y%m%d"),
                ),
            )
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{target.isoformat()}: {exc}")
            continue
        try:
            # Do not remove low-importance events before the user's filter runs.
            day_events = _calendar_rows(_records(frame), "baidu-economic-calendar", "百度股市通经济日历",
                                        "https://finance.baidu.com/calendar", today, days)
            events.extend(event for event in day_events if event["date"] == target.isoformat())
            queried_dates.append(target.isoformat())
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{target.isoformat()}: {exc}")

    unique = {event["id"]: event for event in events}
    events = sorted(unique.values(), key=lambda item: (item["date"], item.get("time") or "", item["title"]))
    status = "ok" if events and not errors else ("partial" if events else ("unavailable" if errors else "empty"))
    sources.append({
        "id": "baidu-economic-calendar",
        "label": "百度股市通经济日历",
        "status": status,
        "count": len(events),
        "asOf": generated_at,
        "coverage": _calendar_coverage(today, days, queried_dates, events, "baidu-economic-calendar"),
        **({"error": "; ".join(errors)[:600]} if errors else {}),
    })
    if days > fallback_days:
        gaps.append({
            "capability": "economic-calendar-horizon",
            "reason": "public_fallback_capped_at_14_days",
        })
    if not api_key:
        gaps.append({
            "capability": "primary-global-economic-calendar",
            "reason": "optional_fmp_provider_not_configured",
        })
    if errors:
        gaps.append({
            "capability": "economic-calendar-date-coverage",
            "reason": "partial_source_unavailable",
        })
    if errors and not events:
        gaps.append({"capability": "economic-calendar", "reason": "fallback_unavailable"})
    return events, sources, gaps


def _signal(label: str, signal: str, summary: str, evidence_ids: list[str]) -> dict[str, Any]:
    return {"label": label, "signal": signal, "summary": summary, "evidenceIds": evidence_ids}


def _build_regime(indicators: list[dict[str, Any]]) -> dict[str, Any]:
    by_id = {item["id"]: item for item in indicators if item["freshness"]["status"] == "fresh"}
    pmi = by_id.get("cn-pmi")
    gdp = by_id.get("cn-gdp-yoy")
    growth_votes: list[int] = []
    growth_evidence: list[str] = []
    if pmi:
        growth_evidence.append(pmi["evidenceId"])
    if gdp:
        growth_evidence.append(gdp["evidenceId"])
    if pmi and gdp and gdp.get("previous") is not None:
        growth_votes.append(1 if pmi["value"] >= 50 else -1)
        growth_votes.append(1 if gdp["value"] > gdp["previous"] else (-1 if gdp["value"] < gdp["previous"] else 0))
    growth_score = sum(growth_votes)
    growth_signal = "positive" if growth_score > 0 else ("negative" if growth_score < 0 else ("mixed" if growth_votes else "unknown"))
    growth_summary = (
        f"PMI {pmi['value']:.1f}" if pmi else "PMI 缺失或已陈旧"
    ) + (f"；{gdp['name']} {gdp['value']:.1f}%" if gdp else "；GDP 缺失或已陈旧")

    price_rows = [by_id[item] for item in ("cn-cpi-yoy", "cn-ppi-yoy") if item in by_id]
    price_deltas = [item["change"] for item in price_rows if item.get("change") is not None]
    price_average = sum(price_deltas) / 2 if len(price_deltas) == 2 else None
    price_signal = "positive" if price_average is not None and price_average > 0.2 else (
        "negative" if price_average is not None and price_average < -0.2 else ("neutral" if price_average is not None else "unknown")
    )
    price_summary = "；".join(f"{item['name']} {item['value']:.1f}%" for item in price_rows) or "通胀数据缺失或已陈旧"

    liquidity_votes: list[int] = []
    liquidity_evidence: list[str] = []
    m2 = by_id.get("cn-m2-yoy")
    lpr = by_id.get("cn-lpr-1y")
    if m2:
        liquidity_evidence.append(m2["evidenceId"])
    if lpr:
        liquidity_evidence.append(lpr["evidenceId"])
    if m2 and lpr and m2.get("change") is not None and lpr.get("change") is not None:
        liquidity_votes.append(1 if m2["change"] > 0 else (-1 if m2["change"] < 0 else 0))
        liquidity_votes.append(1 if lpr["change"] < 0 else (-1 if lpr["change"] > 0 else 0))
    liquidity_score = sum(liquidity_votes)
    liquidity_signal = "positive" if liquidity_score > 0 else (
        "negative" if liquidity_score < 0 else ("neutral" if liquidity_votes else "unknown")
    )
    liquidity_summary = (
        f"M2 同比 {m2['value']:.1f}%" if m2 else "M2 缺失"
    ) + (f"；1 年期 LPR {lpr['value']:.2f}%" if lpr else "；LPR 缺失")

    fresh_count = sum(item["freshness"].get("status") == "fresh" for item in indicators)
    confidence_score = min(fresh_count / max(len(_INDICATORS), 1), 1)
    signals = [growth_signal, price_signal, liquidity_signal]
    if growth_signal == "positive" and price_signal in {"neutral", "positive"} and liquidity_signal == "positive":
        regime_label = "复苏扩张"
        regime_summary = "增长边际改善，价格压力可控，流动性对经济活动形成支持。"
    elif growth_signal == "negative" and price_signal == "negative":
        regime_label = "衰减压力"
        regime_summary = "增长和价格同步走弱，需关注需求收缩与盈利下修的叠加风险。"
    elif growth_signal == "negative" and price_signal == "positive":
        regime_label = "滞胀观察"
        regime_summary = "增长偏弱而价格仍有韧性，政策空间与风险资产估值都更敏感。"
    elif liquidity_signal == "positive" and growth_signal != "negative":
        regime_label = "流动性支撑"
        regime_summary = "流动性边际改善，但仍需等待增长数据确认传导是否有效。"
    else:
        regime_label = "过渡混合"
        regime_summary = "增长、价格和流动性信号尚未形成一致方向，适合提高观察频率。"
    if not by_id:
        regime_label = "数据不足，暂不判定"
        regime_summary = "核心指标均已陈旧或缺失，历史记录不参与当前宏观状态判断。"
    elif "unknown" in signals:
        regime_label = "关键证据不足，暂不判定"
        missing_dimensions = [label for label, signal in zip(("增长", "价格", "流动性"), signals) if signal == "unknown"]
        regime_summary = f"{', '.join(missing_dimensions)}缺少成对且可比的有效观测；已有单项数据仅作线索，不形成完整宏观状态。"
    core_ids = {"cn-pmi", "cn-gdp-yoy", "cn-cpi-yoy", "cn-ppi-yoy", "cn-m2-yoy", "cn-lpr-1y"}
    evidence_ids = [item["evidenceId"] for item in by_id.values() if item["id"] in core_ids]
    transmission = [
        {
            "id": "growth-profit",
            "title": "增长 → 盈利",
            "signal": growth_signal,
            "summary": "增长指标改善通常先影响周期行业订单，再传导到企业收入与盈利预期。",
            "assets": ["可选消费", "工业", "中小盘"],
            "evidenceIds": growth_evidence,
        },
        {
            "id": "price-policy",
            "title": "价格 → 政策",
            "signal": price_signal,
            "summary": "CPI/PPI 的方向决定政策约束，价格回落与需求走弱同时出现时需警惕通缩压力。",
            "assets": ["利率", "成长股", "大宗商品"],
            "evidenceIds": [item["evidenceId"] for item in price_rows],
        },
        {
            "id": "liquidity-valuation",
            "title": "流动性 → 估值",
            "signal": liquidity_signal,
            "summary": "M2 与 LPR 的边际变化反映信用扩张和贴现率方向，需结合市场成交与风险偏好验证。",
            "assets": ["权益估值", "信用", "房地产"],
            "evidenceIds": liquidity_evidence,
        },
    ]
    scenarios = [
        {
            "id": "base",
            "label": "基准",
            "probability": "观察",
            "summary": regime_summary,
            "triggers": ["核心指标按当前频率继续更新", "未来高重要性事件不出现显著偏离"],
            "evidenceIds": evidence_ids[:8],
        },
        {
            "id": "upside",
            "label": "改善",
            "probability": "条件成立",
            "summary": "PMI 保持扩张、M2 边际回升且价格压力稳定，增长预期可能继续修复。",
            "triggers": ["PMI > 50", "M2 同比继续回升", "LPR 保持稳定或下行"],
            "evidenceIds": growth_evidence + liquidity_evidence,
        },
        {
            "id": "downside",
            "label": "走弱",
            "probability": "风险路径",
            "summary": "PMI 跌破荣枯线、增长与价格同步走弱，需求和盈利预期可能下修。",
            "triggers": ["PMI < 50", "CPI/PPI 继续下行", "流动性指标转弱"],
            "evidenceIds": evidence_ids,
        },
    ]
    return {
        "overall": {
            "label": regime_label,
            "summary": regime_summary,
            "signals": signals,
            "evidenceIds": evidence_ids,
        },
        "growth": _signal("增长", growth_signal, growth_summary, growth_evidence),
        "inflation": _signal(
            "价格",
            price_signal,
            price_summary,
            [item["evidenceId"] for item in price_rows],
        ),
        "liquidity": _signal("流动性", liquidity_signal, liquidity_summary, liquidity_evidence),
        "confidence": {
            "level": "high" if confidence_score >= 0.75 else ("medium" if confidence_score >= 0.45 else "low"),
            "score": round(confidence_score, 4),
            "rationale": f"{fresh_count}/{len(_INDICATORS)} 项核心指标处于合理更新窗口；这是数据时效覆盖率，不是判断正确的概率。聚合数据仍需回到原发布机构复核",
        },
        "transmission": transmission,
        "scenarios": scenarios,
    }


def _decision_review(regime: dict[str, Any], events: list[dict[str, Any]], gaps: list[dict[str, Any]]) -> dict[str, Any]:
    """Traceable research adoption, not a position or return recommendation."""
    dimensions = [(key, regime[key]) for key in ("growth", "inflation", "liquidity")]
    supported = [dim for _key, dim in dimensions if dim["signal"] != "unknown" and dim["evidenceIds"]]
    missing = [dim["label"] for _key, dim in dimensions if dim["signal"] == "unknown" or not dim["evidenceIds"]]
    coverage = regime["confidence"]["score"]
    can_review = len(supported) == 3 and coverage >= 0.75
    evidence = [{"dimension": dim["label"], "signal": dim["signal"], "summary": dim["summary"], "evidenceIds": dim["evidenceIds"]} for dim in supported]
    counter = []
    if regime["growth"]["signal"] == "positive" and regime["liquidity"]["signal"] == "negative":
        counter.append("增长信号偏强，但流动性边际偏弱；需确认增长能否持续。")
    if regime["growth"]["signal"] == "negative" and regime["liquidity"]["signal"] == "positive":
        counter.append("流动性改善尚未传导至增长，不能仅凭宽松信号判断复苏。")
    if regime["inflation"]["signal"] == "positive" and regime["growth"]["signal"] == "negative":
        counter.append("价格上行与增长偏弱并存，需区分供给冲击和需求改善。")
    signals = [dim["signal"] for dim in supported]
    if len(set(signals)) > 1 or "mixed" in signals:
        counter.append("核心维度方向不一致，不能把单一改善信号直接推成资产上涨结论。")
    relevant_events = [event for event in events if event["status"] == "scheduled" and event.get("regionGroup") in {"CN", "US"} and not event.get("conflictFields")]
    review_events = [event for event in relevant_events if event["importance"] == "high"][:3]
    if not review_events:
        review_events = [event for event in relevant_events if event["importance"] == "medium"][:3]
    if not review_events:
        review_events = relevant_events[:3]
    checks = [f"补齐{', '.join(missing)}的有效观测" ] if missing else []
    if any(gap["capability"] == "official-primary-source-verification" for gap in gaps):
        checks.append("关键序列需回到统计机构或央行原文复核；当前聚合源不能视为官方确认")
    if any(gap["capability"].startswith("economic-calendar") or gap["capability"] == "primary-global-economic-calendar" for gap in gaps):
        checks.append("经济日历存在来源或日期覆盖缺口，事件时间与评级不能视为完整")
    return {
        "adoption": "可采纳为待核验研究假设" if can_review else "暂缓采纳，先补证",
        "thesis": regime["overall"]["label"] + "：" + regime["overall"]["summary"],
        "scope": "当前状态仅由中国 PMI、GDP、CPI、PPI、M2 与 LPR 形成；美国指标是跨市场旁证。用于安排复核与跨模块研究，不直接推出仓位、资产涨跌或交易指令。",
        "supportingEvidence": evidence,
        "counterEvidence": counter,
        "checks": checks,
        "nextReviewEvents": [{"id": event["id"], "date": event["date"], "title": event["title"], "importance": event["importance"], "ratingBasis": (event.get("importanceBasis") or {}).get("kind", "unknown"), "evidenceId": event["evidenceId"]} for event in review_events],
    }


def build_macro_monitor(days: int = 7, today: date | None = None) -> dict[str, Any]:
    current = today or date.today()
    horizon_days = min(max(int(days), 1), 30)
    with ThreadPoolExecutor(max_workers=2) as pool:
        indicator_future = pool.submit(_load_indicators, current)
        calendar_future = pool.submit(_load_calendar, current, horizon_days)
        liquidity_future = pool.submit(_load_liquidity, current)
        indicators, indicator_source, indicator_gaps = indicator_future.result()
        events, calendar_sources, calendar_gaps = calendar_future.result()
        liquidity = liquidity_future.result()
    regime = _build_regime(indicators)
    gaps = [*indicator_gaps, *calendar_gaps, {
        "capability": "official-primary-source-verification",
        "reason": "aggregated_series_require_primary_source_confirmation",
    }]
    return {
        "schemaVersion": SCHEMA_VERSION,
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "horizon": {
            "start": current.isoformat(),
            "end": (current + timedelta(days=horizon_days)).isoformat(),
            "days": horizon_days,
        },
        "regime": regime,
        "decisionReview": _decision_review(regime, events, gaps),
        "liquidity": liquidity,
        "indicators": indicators,
        "events": events,
        "calendarCoverage": calendar_sources[-1].get("coverage") if calendar_sources else None,
        "sources": [indicator_source, *calendar_sources],
        "gaps": gaps,
        "disclaimer": "宏观数据和事件日期可能修订；本页面只提供研究证据与监测线索，不构成资产配置或买卖建议。",
    }
