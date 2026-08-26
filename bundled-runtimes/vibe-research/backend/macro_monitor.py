"""Lightweight macro monitor for the integrated Research domain.

The adapter normalizes public macro series and upcoming economic events.  It
does not make allocation calls, persist data, start workers, or own model
configuration.  Optional keyed sources degrade to public read-only fallbacks.
"""

from __future__ import annotations

import calendar
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
import json
import math
import os
import re
import threading
import time
from typing import Any, Callable
from urllib.parse import urlencode
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
        "name": "中国 GDP 同比",
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
        "source": "eastmoney-us-macro",
        "sourceLabel": "东方财富美国宏观数据",
        "sourceUrl": "https://data.eastmoney.com/cjsj/foreign_0_12.html",
    },
)

_TUSHARE_SERIES: tuple[dict[str, str], ...] = (
    {"id": "cn-pmi", "api": "cn_pmi", "periodKey": "MONTH", "valueKey": "PMI010000", "frequency": "month", "updateKey": "UPDATE_TIME"},
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


def _normalize_tushare_series(
    indicator_config: dict[str, Any],
    series_config: dict[str, str],
    rows: list[dict[str, Any]],
    today: date,
) -> dict[str, Any] | None:
    normalized: list[dict[str, Any]] = []
    for row in rows:
        period = _tushare_period(row.get(series_config["periodKey"]), series_config["frequency"])
        value = _number(row.get(series_config["valueKey"]))
        if period is None or value is None:
            continue
        update_date = _date(row.get(series_config.get("updateKey", ""))) if series_config.get("updateKey") else None
        normalized.append({"period": period[0], "periodDate": period[1], "referenceDate": update_date or period[1], "releaseDate": update_date, "value": value})
    if not normalized:
        return None
    normalized.sort(key=lambda item: item["periodDate"])
    latest = normalized[-1]
    previous = normalized[-2]["value"] if len(normalized) > 1 else None
    change = latest["value"] - previous if previous is not None else None
    freshness = _freshness(latest["referenceDate"], today, int(indicator_config["maxAgeDays"]))
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
        "source": {"id": f"tushare-{series_config['api']}", "label": "Tushare Pro 宏观序列", "url": _TUSHARE_SOURCE_URL},
        "evidenceId": f"macro:{indicator_config['id']}:tushare:{latest['period']}",
        "asOf": latest["releaseDate"].isoformat() if latest["releaseDate"] else latest["period"],
        "freshness": freshness,
        "confidence": _confidence(freshness),
        "history": [{"period": item["period"], "value": item["value"]} for item in normalized[-12:]],
    }


def _metric_number(value: Any) -> float | None:
    if isinstance(value, str):
        value = value.strip().replace(",", "").removesuffix("%")
    return _number(value)


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
        localized = explicit is None and str(row.get("country") or "") == series_config["country"]
        actual = explicit if explicit is not None else (_metric_number(row.get("pre_value")) if localized else None)
        if actual is None:
            continue
        candidate = {
            "releaseDate": release,
            "value": actual,
            "previous": _metric_number(row.get("pre_value")) if explicit is not None else None,
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
        return {}, [], "unsupported"
    configs = {item["id"]: item for item in _INDICATORS}
    indicators: dict[str, dict[str, Any]] = {}
    errors: list[str] = []
    for series in _TUSHARE_SERIES:
        try:
            if series["frequency"] == "quarter":
                params = {"start_q": f"{today.year - 3}Q1", "end_q": f"{today.year}Q{((today.month - 1) // 3) + 1}"}
            else:
                params = {"start_m": f"{today.year - 2}01", "end_m": f"{today.year}{today.month:02d}"}
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
        if actual is None:
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
        and (value := _number(row.get("LPR1Y"))) is not None
    ]
    if not normalized:
        return None
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
    errors: list[str] = []
    gaps: list[dict[str, str]] = []

    def fetch(config: dict[str, Any]) -> tuple[dict[str, Any], Any | None, Exception | None]:
        try:
            frame = _cached(
                f"macro-indicator:{config['function']}",
                6 * 3600,
                lambda function=config["function"]: astock.akshare_parallel_call(function),
            )
            return config, frame, None
        except Exception as exc:  # noqa: BLE001
            return config, None, exc

    with ThreadPoolExecutor(max_workers=5) as pool:
        tushare_future = pool.submit(_load_tushare_indicators, today)
        results = list(pool.map(fetch, _INDICATORS))
        tushare_indicators, tushare_errors, tushare_status = tushare_future.result()

    for indicator_id, indicator in tushare_indicators.items():
        candidates[indicator_id].append(indicator)
    errors.extend(f"tushare {error}" for error in tushare_errors)

    for config, frame, error in results:
        if error:
            errors.append(f"akshare {config['id']}: {error}")
            continue
        try:
            rows = _records(frame)
            if config.get("kind") == "lpr":
                indicator = _normalize_lpr_indicator(config, rows, today)
            elif config.get("kind") == "usa":
                indicator = _normalize_usa_indicator(config, rows, today)
            else:
                indicator = _normalize_standard_indicator(config, rows, today)
            if indicator:
                candidates[config["id"]].append(indicator)
        except Exception as exc:  # noqa: BLE001 - normalization status is part of the contract
            errors.append(f"akshare {config['id']}: {exc}")

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
                1 if str(item.get("source", {}).get("id", "")).startswith("tushare-") else 0,
            ),
        )
        indicators.append(selected)

    generated_at = datetime.now(timezone.utc).isoformat()
    status = "ok" if len(indicators) == len(_INDICATORS) else ("partial" if indicators else "unavailable")
    fresh_count = sum(item["freshness"].get("status") == "fresh" for item in indicators)
    source = {
        "id": "public-macro-aggregators",
        "label": "Tushare Pro 优先 · AkShare 降级",
        "status": status,
        "count": len(indicators),
        "asOf": generated_at,
        "coverage": {
            "regions": sorted({item["region"] for item in indicators}),
            "fresh": fresh_count,
            "stale": len(indicators) - fresh_count,
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
) -> dict[str, Any] | None:
    if not rows:
        return None
    latest = rows[-1]
    previous = rows[-2]["value"] if len(rows) > 1 else None
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
        "period": latest["period"].isoformat(),
        "asOf": latest["period"].isoformat(),
        "source": {"id": source_id, "label": source_label, "url": source_url},
        "freshness": freshness,
        "history": [{"period": row["period"].isoformat(), "value": round(row["value"], 4)} for row in rows[-30:]],
    }


def _liquidity_forecast(indicators: list[dict[str, Any]], horizon_days: int = 5) -> dict[str, Any]:
    """Small, explainable baseline: recent linear trend, not a trading model."""
    forecasts: list[dict[str, Any]] = []
    for item in indicators:
        values = [float(row["value"]) for row in item.get("history", []) if _number(row.get("value")) is not None]
        if len(values) < 3:
            continue
        sample = values[-6:]
        slope = (sample[-1] - sample[0]) / max(len(sample) - 1, 1)
        forecast = sample[-1] + slope * horizon_days
        if abs(slope) < max(abs(sample[-1]) * 0.001, 0.0001):
            direction = "flat"
        else:
            direction = "higher" if slope > 0 else "lower"
        forecasts.append({
            "id": item["id"],
            "name": item["name"],
            "direction": direction,
            "latest": round(sample[-1], 4),
            "forecast": round(forecast, 4),
            "slope": round(slope, 6),
        })
    supportive = sum(1 for item in indicators if item.get("change") is not None and ((item.get("effect") == "supportive" and item["change"] > 0) or (item.get("effect") == "supportive_inverse" and item["change"] < 0)))
    restrictive = sum(1 for item in indicators if item.get("change") is not None and ((item.get("effect") == "restrictive" and item["change"] > 0) or (item.get("effect") == "restrictive_inverse" and item["change"] < 0)))
    signal = "supportive" if supportive > restrictive else ("restrictive" if restrictive > supportive else "mixed")
    return {
        "horizonDays": horizon_days,
        "signal": signal,
        "direction": "higher" if supportive > restrictive else ("lower" if restrictive > supportive else "mixed"),
        "confidence": round(min(0.85, 0.35 + len(forecasts) * 0.06), 2),
        "method": "近 6 个观测的线性趋势外推，仅作监测基线",
        "items": forecasts,
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

    source_url = "https://www.pbc.gov.cn/"
    quantity: list[dict[str, Any]] = []
    price: list[dict[str, Any]] = []
    transmission: list[dict[str, Any]] = []

    shibor = frames.get("macro_china_shibor_all")
    for key, item_id, label in (("O/N-定价", "cn-shibor-on", "SHIBOR 隔夜"), ("1W-定价", "cn-shibor-1w", "SHIBOR 1 周"), ("3M-定价", "cn-shibor-3m", "SHIBOR 3 个月")):
        item = _liquidity_item(
            item_id=item_id, name=label, unit="%", rows=_series_rows(shibor, "日期", key), today=today,
            source_id="shibor", source_label="中国外汇交易中心 SHIBOR", source_url="https://www.shibor.org/", max_age_days=5, effect="restrictive",
        )
        if item: price.append(item)

    money = frames.get("macro_china_money_supply")
    m2_rows = _series_rows(money, "月份", "货币和准货币(M2)-同比增长")
    m1_rows = _series_rows(money, "月份", "货币(M1)-同比增长")
    for item_id, label, rows, effect in (
        ("cn-m2-yoy", "M2 同比", m2_rows, "supportive"),
        ("cn-m1-yoy", "M1 同比", m1_rows, "supportive"),
    ):
        item = _liquidity_item(item_id=item_id, name=label, unit="%", rows=rows, today=today, source_id="pbc-money-supply", source_label="人民银行货币供应量", source_url=source_url, max_age_days=55, effect=effect)
        if item: quantity.append(item)
    if m2_rows and m1_rows:
        m1_by_period = {row["period"]: row["value"] for row in m1_rows}
        spread_rows = [{"period": row["period"], "value": row["value"] - m1_by_period[row["period"]]} for row in m2_rows if row["period"] in m1_by_period]
        item = _liquidity_item(item_id="cn-m2-m1-spread", name="M2-M1 增速差", unit="百分点", rows=spread_rows, today=today, source_id="pbc-money-supply", source_label="人民银行货币供应量", source_url=source_url, max_age_days=55, effect="supportive")
        if item: quantity.append(item)

    credit = _series_rows(frames.get("macro_china_new_financial_credit"), "月份", "当月")
    item = _liquidity_item(item_id="cn-new-social-financing", name="新增社融", unit="亿元", rows=credit, today=today, source_id="pbc-social-financing", source_label="人民银行社会融资规模", source_url=source_url, max_age_days=55, effect="supportive")
    if item: quantity.append(item)

    margin_frames = [_series_rows(frames.get(name), "日期", "融资融券余额") for name in ("macro_china_market_margin_sh", "macro_china_market_margin_sz")]
    margin_by_date: dict[date, float] = {}
    for rows in margin_frames:
        for row in rows: margin_by_date[row["period"]] = margin_by_date.get(row["period"], 0) + row["value"] / 100_000_000
    item = _liquidity_item(item_id="cn-margin-balance", name="全市场两融余额", unit="亿元", rows=[{"period": period, "value": value} for period, value in sorted(margin_by_date.items())], today=today, source_id="margin-exchanges", source_label="沪深交易所两融", source_url="https://www.sse.com.cn/market/othersdata/margin/", max_age_days=5, effect="supportive")
    if item: transmission.append(item)

    financing = _series_rows(frames.get("macro_stock_finance"), "月份", "募集资金")
    item = _liquidity_item(item_id="cn-equity-financing", name="股票市场融资额", unit="亿元", rows=financing, today=today, source_id="csrc-equity-financing", source_label="A 股再融资与 IPO", source_url="https://www.csrc.gov.cn/", max_age_days=55, effect="restrictive")
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
        "forecast": _liquidity_forecast(all_indicators),
        "coverage": {"available": len(all_indicators), "total": 9, "asOf": max((item["asOf"] for item in all_indicators), default=None)},
        "source": "AkShare · 人民银行 / SHIBOR / 沪深交易所",
        "note": "数量、价格和市场传导分开统计；预测为近 6 个观测的趋势基线，不替代正式预测模型。",
    }


def _importance(value: Any) -> str:
    text = str(value or "").strip().lower()
    if text in {"high", "3"}:
        return "high"
    if text in {"medium", "2"}:
        return "medium"
    return "low"


def _calendar_event(row: dict[str, Any], source_id: str, source_label: str, source_url: str, today: date) -> dict[str, Any] | None:
    release_date = _date(row.get("日期") or str(row.get("date") or "")[:10])
    if not release_date:
        return None
    raw_time = str(row.get("时间") or str(row.get("date") or "")[11:19] or "").strip()
    region = str(row.get("地区") or row.get("country") or "Unknown").strip()[:40]
    title = str(row.get("事件") or row.get("event") or "").strip()[:240]
    if not title:
        return None
    actual = _number(row.get("公布") if "公布" in row else row.get("actual"))
    forecast = _number(row.get("预期") if "预期" in row else row.get("estimate"))
    previous = _number(row.get("前值") if "前值" in row else row.get("previous"))
    importance = _importance(row.get("重要性") if "重要性" in row else row.get("impact"))
    event_id = f"{source_id}:{release_date.isoformat()}:{raw_time}:{region}:{title}"
    return {
        "id": event_id[:500],
        "date": release_date.isoformat(),
        "time": raw_time[:12] or None,
        "region": region,
        "currency": str(row.get("currency") or "").strip()[:12] or None,
        "title": title,
        "importance": importance,
        "status": "released" if actual is not None and release_date <= today else "scheduled",
        "actual": actual,
        "forecast": forecast,
        "previous": previous,
        "source": {"id": source_id, "label": source_label, "url": source_url},
        "evidenceId": f"macro-calendar:{source_id}:{release_date.isoformat()}:{title}"[:500],
        "asOf": datetime.now(timezone.utc).isoformat(),
    }


def _fmp_events(today: date, days: int, api_key: str) -> list[dict[str, Any]]:
    end = today + timedelta(days=days)
    query = urlencode({"from": today.isoformat(), "to": end.isoformat(), "apikey": api_key})
    request = Request(
        f"https://financialmodelingprep.com/api/v3/economic_calendar?{query}",
        headers={"Accept": "application/json", "User-Agent": "Newma-Desk/0.1"},
    )
    with urlopen(request, timeout=8) as response:  # noqa: S310 - fixed HTTPS origin
        payload = json.load(response)
    if not isinstance(payload, list):
        raise ValueError("FMP economic calendar returned an invalid payload")
    return payload


def _load_calendar(today: date, days: int) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, str]]]:
    events: list[dict[str, Any]] = []
    sources: list[dict[str, Any]] = []
    gaps: list[dict[str, str]] = []
    api_key = os.environ.get("FMP_API_KEY", "").strip()
    generated_at = datetime.now(timezone.utc).isoformat()

    if api_key:
        try:
            rows = _cached(
                f"fmp-economic-calendar:{today.isoformat()}:{days}",
                3600,
                lambda: _fmp_events(today, days, api_key),
            )
            events = [
                event
                for row in rows
                if (event := _calendar_event(
                    row,
                    "fmp-economic-calendar",
                    "Financial Modeling Prep Economic Calendar",
                    "https://financialmodelingprep.com/developer/docs/economic-calendar-api",
                    today,
                ))
            ]
            sources.append({
                "id": "fmp-economic-calendar",
                "label": "FMP 经济日历",
                "status": "ok" if events else "empty",
                "count": len(events),
                "asOf": generated_at,
                "coverage": {"start": today.isoformat(), "end": (today + timedelta(days=days)).isoformat()},
            })
            return events, sources, gaps
        except Exception as exc:  # noqa: BLE001
            sources.append({
                "id": "fmp-economic-calendar",
                "label": "FMP 经济日历",
                "status": "unavailable",
                "count": 0,
                "asOf": generated_at,
                "error": str(exc)[:600],
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
            for row in _records(frame):
                event = _calendar_event(
                    row,
                    "baidu-economic-calendar",
                    "百度股市通经济日历",
                    "https://finance.baidu.com/calendar",
                    today,
                )
                if event and event["importance"] != "low":
                    events.append(event)
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
        "coverage": {
            "start": today.isoformat(),
            "end": (today + timedelta(days=fallback_days)).isoformat(),
        },
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
    by_id = {item["id"]: item for item in indicators}
    pmi = by_id.get("cn-pmi")
    gdp = by_id.get("cn-gdp-yoy")
    growth_votes: list[int] = []
    growth_evidence: list[str] = []
    if pmi:
        growth_votes.append(1 if pmi["value"] >= 50 else -1)
        growth_evidence.append(pmi["evidenceId"])
    if gdp and gdp.get("previous") is not None:
        growth_votes.append(1 if gdp["value"] > gdp["previous"] else (-1 if gdp["value"] < gdp["previous"] else 0))
        growth_evidence.append(gdp["evidenceId"])
    growth_score = sum(growth_votes)
    growth_signal = "positive" if growth_score > 0 else ("negative" if growth_score < 0 else ("mixed" if growth_votes else "unknown"))
    growth_summary = (
        f"PMI {pmi['value']:.1f}" if pmi else "PMI 缺失"
    ) + (f"；GDP 同比 {gdp['value']:.1f}%" if gdp else "；GDP 缺失")

    price_rows = [by_id[item] for item in ("cn-cpi-yoy", "cn-ppi-yoy") if item in by_id]
    price_deltas = [item["change"] for item in price_rows if item.get("change") is not None]
    price_average = sum(price_deltas) / len(price_deltas) if price_deltas else None
    price_signal = "positive" if price_average is not None and price_average > 0.2 else (
        "negative" if price_average is not None and price_average < -0.2 else ("neutral" if price_average is not None else "unknown")
    )
    price_summary = "；".join(f"{item['name']} {item['value']:.1f}%" for item in price_rows) or "通胀数据缺失"

    liquidity_votes: list[int] = []
    liquidity_evidence: list[str] = []
    m2 = by_id.get("cn-m2-yoy")
    lpr = by_id.get("cn-lpr-1y")
    if m2 and m2.get("change") is not None:
        liquidity_votes.append(1 if m2["change"] > 0 else (-1 if m2["change"] < 0 else 0))
        liquidity_evidence.append(m2["evidenceId"])
    if lpr and lpr.get("change") is not None:
        liquidity_votes.append(1 if lpr["change"] < 0 else (-1 if lpr["change"] > 0 else 0))
        liquidity_evidence.append(lpr["evidenceId"])
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
    evidence_ids = [item["evidenceId"] for item in indicators]
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
            "rationale": f"{fresh_count}/{len(_INDICATORS)} 项核心指标处于合理更新窗口；聚合数据仍需回到原发布机构复核",
        },
        "transmission": transmission,
        "scenarios": scenarios,
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
    return {
        "schemaVersion": SCHEMA_VERSION,
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "horizon": {
            "start": current.isoformat(),
            "end": (current + timedelta(days=horizon_days)).isoformat(),
            "days": horizon_days,
        },
        "regime": _build_regime(indicators),
        "liquidity": liquidity,
        "indicators": indicators,
        "events": events,
        "sources": [indicator_source, *calendar_sources],
        "gaps": [*indicator_gaps, *calendar_gaps, {
            "capability": "official-primary-source-verification",
            "reason": "aggregated_series_require_primary_source_confirmation",
        }],
        "disclaimer": "宏观数据和事件日期可能修订；本页面只提供研究证据与监测线索，不构成资产配置或买卖建议。",
    }
