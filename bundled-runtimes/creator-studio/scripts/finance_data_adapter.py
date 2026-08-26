#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import re
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib import parse as urllib_parse
from urllib import request as urllib_request


UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
EASTMONEY_KLINE_URL = "https://push2his.eastmoney.com/api/qt/stock/kline/get"
BAIDU_KLINE_URL = "https://finance.pae.baidu.com/selfselect/getstockquotation"
TENCENT_QUOTE_URL = "https://qt.gtimg.cn/q="
FMP_ECONOMIC_CALENDAR_URL = "https://financialmodelingprep.com/stable/economics-calendar"
YAHOO_CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"
EASTMONEY_DATACENTER_URL = "https://datacenter-web.eastmoney.com/api/data/v1/get"
EM_MIN_INTERVAL = 1.0
_EM_LAST_CALL = [0.0]
DEFAULT_CACHE_TTL_SECONDS = 60 * 60 * 12
EASTMONEY_MACRO_PRESETS = {
    "china_cpi": {
        "report_name": "RPT_ECONOMY_CPI",
        "field": "NATIONAL_SAME",
        "label": "CPI同比",
        "unit": "%",
        "source_url": "https://data.eastmoney.com/cjsj/cpi.html",
    },
    "china_pmi": {
        "report_name": "RPT_ECONOMY_PMI",
        "field": "MAKE_INDEX",
        "label": "制造业PMI",
        "unit": "%",
        "source_url": "https://data.eastmoney.com/cjsj/pmi.html",
    },
    "china_gdp": {
        "report_name": "RPT_ECONOMY_GDP",
        "field": "SUM_SAME",
        "label": "GDP同比",
        "unit": "%",
        "source_url": "https://data.eastmoney.com/cjsj/gdp.html",
    },
    "china_money_supply": {
        "report_name": "RPT_ECONOMY_CURRENCY_SUPPLY",
        "field": "BASIC_CURRENCY_SAME",
        "label": "货币供应同比",
        "unit": "%",
        "source_url": "https://data.eastmoney.com/cjsj/hbgyl.html",
    },
    "china_rmb_loan": {
        "report_name": "RPT_ECONOMY_RMB_LOAN",
        "field": "RMB_LOAN_ACCUMULATE",
        "label": "人民币贷款累计新增",
        "unit": "亿元",
        "source_url": "https://data.eastmoney.com/cjsj/xzdk.html",
    },
    "china_house_price": {
        "report_name": "RPT_ECONOMY_HOUSE_PRICE",
        "field": "FIRST_COMHOUSE_SAME",
        "label": "新建商品住宅价格同比涨跌幅",
        "unit": "%",
        "transform": "delta_from_100",
        "source_url": "https://data.eastmoney.com/cjsj/newhouse.html",
        "default_cities": ["北京", "上海", "广州", "深圳"],
    },
}


def read_json(path: Path) -> Any:
    return json.loads(path.expanduser().resolve().read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def finance_cache_dir() -> Path:
    configured = os.environ.get("DASHENG_FINANCE_CACHE_DIR")
    if configured:
        return Path(configured).expanduser().resolve()
    return Path(__file__).resolve().parents[1] / ".cache" / "finance_data"


def cache_key(payload: Any) -> str:
    text = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def read_cache(namespace: str, key: str, *, max_age_seconds: int | None = DEFAULT_CACHE_TTL_SECONDS) -> tuple[Any | None, bool]:
    path = finance_cache_dir() / namespace / f"{key}.json"
    if not path.exists():
        return None, False
    try:
        wrapper = json.loads(path.read_text(encoding="utf-8"))
        created_at = float(wrapper.get("created_at") or 0)
        payload = wrapper.get("payload")
    except Exception:
        return None, False
    is_stale = bool(max_age_seconds is not None and time.time() - created_at > max_age_seconds)
    if is_stale:
        return None, True
    return payload, False


def read_stale_cache(namespace: str, key: str) -> Any | None:
    path = finance_cache_dir() / namespace / f"{key}.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8")).get("payload")
    except Exception:
        return None


def write_cache(namespace: str, key: str, payload: Any) -> None:
    path = finance_cache_dir() / namespace / f"{key}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"created_at": time.time(), "payload": payload}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def normalize_code(value: str) -> str:
    text = str(value or "").strip().lower()
    text = re.sub(r"^(sh|sz|bj)", "", text)
    text = re.sub(r"\.(sh|sz|bj)$", "", text)
    text = re.sub(r"[^0-9]", "", text)
    if not re.fullmatch(r"\d{6}", text):
        raise ValueError(f"股票/指数代码格式错误：{value}")
    return text


def infer_prefix(code: str, *, market: str | None = None, as_index: bool = False) -> str:
    if market:
        return market.lower()
    if as_index and code.startswith("399"):
        return "sz"
    if as_index:
        return "sh"
    if code.startswith(("6", "9")):
        return "sh"
    if code.startswith("8"):
        return "bj"
    return "sz"


def eastmoney_market_id(prefix: str) -> int:
    return 1 if prefix == "sh" else 0


def secid_for(symbol: dict[str, Any] | str) -> tuple[str, str, str]:
    if isinstance(symbol, str):
        code = normalize_code(symbol)
        prefix = infer_prefix(code)
        return f"{eastmoney_market_id(prefix)}.{code}", code, prefix
    if symbol.get("secid"):
        secid = str(symbol["secid"])
        code = normalize_code(secid.split(".", 1)[-1])
        prefix = symbol.get("market") or ("sh" if secid.startswith("1.") else "sz")
        return secid, code, str(prefix).lower()
    code = normalize_code(str(symbol.get("code") or symbol.get("symbol") or ""))
    prefix = infer_prefix(code, market=symbol.get("market"), as_index=bool(symbol.get("as_index")))
    return f"{eastmoney_market_id(prefix)}.{code}", code, prefix


def is_yfinance_symbol(symbol: Any) -> bool:
    if isinstance(symbol, dict):
        if symbol.get("ticker") or symbol.get("yf") or symbol.get("yfinance"):
            return True
        raw = str(symbol.get("code") or symbol.get("symbol") or "")
    else:
        raw = str(symbol or "")
    raw = raw.strip()
    return not bool(re.fullmatch(r"(sh|sz|bj)?\d{6}(\.(sh|sz|bj))?", raw.lower()))


def _urlopen_json(url: str, params: dict[str, str] | None = None, *, timeout: int = 15) -> Any:
    if params:
        url = url + "?" + urllib_parse.urlencode(params)
    req = urllib_request.Request(url, headers={"User-Agent": UA, "Referer": "https://quote.eastmoney.com/"})
    with urllib_request.urlopen(req, timeout=timeout) as response:
        text = response.read().decode("utf-8", errors="replace")
    return json.loads(text)


def em_get_json(url: str, params: dict[str, str] | None = None, *, timeout: int = 15) -> Any:
    wait = EM_MIN_INTERVAL - (time.time() - _EM_LAST_CALL[0])
    if wait > 0:
        time.sleep(wait + random.uniform(0.1, 0.4))
    try:
        return _urlopen_json(url, params=params, timeout=timeout)
    finally:
        _EM_LAST_CALL[0] = time.time()


def fetch_eastmoney_kline(
    symbol: dict[str, Any] | str,
    *,
    start_date: str,
    end_date: str,
    period: str = "daily",
    adjust: str = "qfq",
) -> dict[str, Any]:
    secid, code, prefix = secid_for(symbol)
    klt_map = {"daily": "101", "weekly": "102", "monthly": "103"}
    fqt_map = {"none": "0", "qfq": "1", "hfq": "2"}
    params = {
        "secid": secid,
        "klt": klt_map.get(period, period),
        "fqt": fqt_map.get(adjust, adjust),
        "beg": re.sub(r"[^0-9]", "", start_date),
        "end": re.sub(r"[^0-9]", "", end_date),
        "fields1": "f1,f2,f3,f4,f5,f6",
        "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61",
    }
    payload = em_get_json(EASTMONEY_KLINE_URL, params=params)
    data = payload.get("data") or {}
    rows = []
    for line in data.get("klines") or []:
        parts = line.split(",")
        if len(parts) < 11:
            continue
        rows.append(
            {
                "date": parts[0],
                "open": _float(parts[1]),
                "close": _float(parts[2]),
                "high": _float(parts[3]),
                "low": _float(parts[4]),
                "volume": _float(parts[5]),
                "amount": _float(parts[6]),
                "amplitude_pct": _float(parts[7]),
                "change_pct": _float(parts[8]),
                "change": _float(parts[9]),
                "turnover_pct": _float(parts[10]),
            }
        )
    return {
        "code": code,
        "prefix": prefix,
        "secid": secid,
        "name": data.get("name") or code,
        "source": "eastmoney_push2his_kline",
        "rows": rows,
    }


def fetch_baidu_kline(
    symbol: dict[str, Any] | str,
    *,
    start_date: str,
    end_date: str,
    period: str = "daily",
) -> dict[str, Any]:
    _, code, prefix = secid_for(symbol)
    ktype_map = {"daily": "1", "weekly": "2", "monthly": "3"}
    params = {
        "all": "1",
        "isIndex": "true" if isinstance(symbol, dict) and symbol.get("as_index") else "false",
        "isBk": "false",
        "isBlock": "false",
        "isFutures": "false",
        "isStock": "false" if isinstance(symbol, dict) and symbol.get("as_index") else "true",
        "newFormat": "1",
        "group": "quotation_kline_ab",
        "finClientType": "pc",
        "code": code,
        "ktype": ktype_map.get(period, "1"),
    }
    url = BAIDU_KLINE_URL + "?" + urllib_parse.urlencode(params)
    req = urllib_request.Request(
        url,
        headers={
            "User-Agent": UA,
            "Accept": "application/vnd.finance-web.v1+json",
            "Origin": "https://gushitong.baidu.com",
            "Referer": "https://gushitong.baidu.com/",
        },
    )
    with urllib_request.urlopen(req, timeout=15) as response:
        payload = json.loads(response.read().decode("utf-8", errors="replace"))
    market_data = ((payload.get("Result") or {}).get("newMarketData") or {})
    keys = market_data.get("keys") or []
    rows = []
    start = re.sub(r"[^0-9]", "", start_date)
    end = re.sub(r"[^0-9]", "", end_date)
    for raw in str(market_data.get("marketData") or "").split(";"):
        if not raw.strip():
            continue
        values = raw.split(",")
        item = {key: values[index] if index < len(values) else None for index, key in enumerate(keys)}
        date = str(item.get("time") or "")
        compact = date.replace("-", "")
        if start and compact < start:
            continue
        if end and compact > end:
            continue
        rows.append(
            {
                "date": date,
                "open": _float(item.get("open")),
                "close": _float(item.get("close")),
                "high": _float(item.get("high")),
                "low": _float(item.get("low")),
                "volume": _float(item.get("volume")),
                "amount": _float(item.get("amount")),
                "change_pct": _float(str(item.get("ratio") or "").replace("%", "")),
                "change": _float(item.get("increase")),
                "turnover_pct": _float(str(item.get("turnoverratio") or "").replace("%", "")),
                "ma5": _float(item.get("ma5avgprice")),
                "ma10": _float(item.get("ma10avgprice")),
                "ma20": _float(item.get("ma20avgprice")),
            }
        )
    return {"code": code, "prefix": prefix, "secid": f"baidu.{code}", "name": code, "source": "baidu_gushitong_kline", "rows": rows}


def fetch_kline(
    symbol: dict[str, Any] | str,
    *,
    start_date: str,
    end_date: str,
    period: str = "daily",
    adjust: str = "qfq",
) -> dict[str, Any]:
    try:
        data = fetch_eastmoney_kline(symbol, start_date=start_date, end_date=end_date, period=period, adjust=adjust)
        if data.get("rows"):
            return data
    except Exception:
        pass
    return fetch_baidu_kline(symbol, start_date=start_date, end_date=end_date, period=period)


def fetch_yfinance_history(
    symbol: dict[str, Any] | str,
    *,
    start_date: str,
    end_date: str,
    interval: str = "1d",
) -> dict[str, Any]:
    try:
        import yfinance as yf
    except ImportError as exc:
        raise RuntimeError("yfinance 未安装，无法获取全球金融市场数据") from exc
    ticker = str(symbol.get("ticker") or symbol.get("yf") or symbol.get("symbol") or symbol.get("code")) if isinstance(symbol, dict) else str(symbol)
    df = yf.download(
        ticker,
        start=_date_dash(start_date),
        end=_date_dash(end_date),
        interval=interval,
        auto_adjust=False,
        progress=False,
        threads=False,
    )
    if df is None or df.empty:
        return {"code": ticker, "name": ticker, "source": "yfinance", "rows": []}
    if hasattr(df.columns, "nlevels") and getattr(df.columns, "nlevels", 1) > 1:
        df.columns = [col[0] for col in df.columns]
    rows = []
    for idx, row in df.reset_index().iterrows():
        date_value = row.get("Date") or row.get("Datetime")
        date = getattr(date_value, "strftime", lambda fmt: str(date_value))("%Y-%m-%d")
        rows.append(
            {
                "date": date,
                "open": _float(row.get("Open")),
                "close": _float(row.get("Close")),
                "high": _float(row.get("High")),
                "low": _float(row.get("Low")),
                "volume": _float(row.get("Volume")),
            }
        )
    return {"code": ticker, "name": ticker, "source": "yfinance", "rows": rows}


def _date_epoch_seconds(value: str, *, end_exclusive: bool = False) -> int:
    text = _date_dash(value)
    dt = datetime.strptime(text, "%Y-%m-%d")
    if end_exclusive:
        dt = dt + timedelta(days=1)
    return int(dt.replace(tzinfo=timezone.utc).timestamp())


def fetch_yahoo_chart_history(
    symbol: dict[str, Any] | str,
    *,
    start_date: str,
    end_date: str,
    interval: str = "1d",
    retries: int = 2,
) -> dict[str, Any]:
    ticker = str(symbol.get("ticker") or symbol.get("yf") or symbol.get("symbol") or symbol.get("code")) if isinstance(symbol, dict) else str(symbol)
    ticker = ticker.strip()
    params = {
        "period1": str(_date_epoch_seconds(start_date)),
        "period2": str(_date_epoch_seconds(end_date, end_exclusive=True)),
        "interval": interval,
        "events": "history",
        "includeAdjustedClose": "true",
    }
    key = cache_key({"endpoint": "yahoo_chart", "ticker": ticker, "params": params})
    cached, _ = read_cache("yahoo_chart", key)
    if cached:
        return cached

    url = YAHOO_CHART_URL.format(ticker=urllib_parse.quote(ticker, safe=""))
    last_error: Exception | None = None
    for attempt in range(max(1, retries + 1)):
        try:
            payload = _urlopen_json(url, params=params, timeout=20)
            result = ((payload.get("chart") or {}).get("result") or [None])[0]
            if not result:
                error = (payload.get("chart") or {}).get("error")
                raise RuntimeError(f"Yahoo Finance 返回空结果：{error}")
            meta = result.get("meta") or {}
            timestamps = result.get("timestamp") or []
            indicators = result.get("indicators") or {}
            quote = (indicators.get("quote") or [{}])[0]
            adjclose = ((indicators.get("adjclose") or [{}])[0]).get("adjclose") or []
            rows = []
            for index, ts in enumerate(timestamps):
                close_value = _list_get(quote.get("close"), index)
                rows.append(
                    {
                        "date": datetime.fromtimestamp(int(ts), tz=timezone.utc).strftime("%Y-%m-%d"),
                        "open": _float(_list_get(quote.get("open"), index)),
                        "close": _float(close_value),
                        "adjclose": _float(_list_get(adjclose, index)) if adjclose else _float(close_value),
                        "high": _float(_list_get(quote.get("high"), index)),
                        "low": _float(_list_get(quote.get("low"), index)),
                        "volume": _float(_list_get(quote.get("volume"), index)),
                    }
                )
            rows = [row for row in rows if row.get("close") is not None or row.get("adjclose") is not None]
            if not rows:
                raise RuntimeError("Yahoo Finance 返回空行情序列")
            result_payload = {
                "code": ticker,
                "name": meta.get("shortName") or meta.get("longName") or meta.get("symbol") or ticker,
                "source": "yahoo_chart_api",
                "rows": rows,
            }
            write_cache("yahoo_chart", key, result_payload)
            return result_payload
        except Exception as exc:
            last_error = exc
            if attempt < retries:
                time.sleep(0.8 * (attempt + 1) + random.uniform(0.1, 0.5))

    stale = read_stale_cache("yahoo_chart", key)
    if stale:
        stale = dict(stale)
        stale["source"] = "yahoo_chart_cache_stale"
        stale["warning"] = f"Yahoo Finance 实时请求失败，使用本地旧缓存：{last_error}"
        return stale
    raise RuntimeError(f"Yahoo Finance 直连接口失败：{last_error}")


def fetch_global_market_history(
    symbol: dict[str, Any] | str,
    *,
    start_date: str,
    end_date: str,
    interval: str = "1d",
) -> dict[str, Any]:
    direct_error: Exception | None = None
    try:
        return fetch_yahoo_chart_history(symbol, start_date=start_date, end_date=end_date, interval=interval)
    except Exception as exc:
        direct_error = exc
    try:
        data = fetch_yfinance_history(symbol, start_date=start_date, end_date=end_date, interval=interval)
        if data.get("rows"):
            return data
    except Exception as exc:
        raise RuntimeError(f"全球市场数据获取失败：Yahoo={direct_error}; yfinance={exc}") from exc
    raise RuntimeError(f"全球市场数据获取失败：Yahoo={direct_error}; yfinance 返回空序列")


def _date_dash(value: str) -> str:
    text = re.sub(r"[^0-9]", "", str(value or ""))
    if len(text) == 8:
        return f"{text[:4]}-{text[4:6]}-{text[6:8]}"
    return str(value)


def _float(value: Any) -> float | None:
    try:
        if value in {"", None, "-"}:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _list_get(values: Any, index: int) -> Any:
    if not isinstance(values, list) or index >= len(values):
        return None
    return values[index]


def fetch_tencent_quotes(symbols: list[str | dict[str, Any]]) -> dict[str, dict[str, Any]]:
    prefixed = []
    for symbol in symbols:
        _, code, prefix = secid_for(symbol)
        prefixed.append(f"{prefix}{code}")
    req = urllib_request.Request(TENCENT_QUOTE_URL + ",".join(prefixed), headers={"User-Agent": UA})
    with urllib_request.urlopen(req, timeout=10) as response:
        data = response.read().decode("gbk", errors="replace")
    result: dict[str, dict[str, Any]] = {}
    for line in data.strip().split(";"):
        if not line.strip() or "=" not in line or '"' not in line:
            continue
        key = line.split("=")[0].split("_")[-1]
        values = line.split('"')[1].split("~")
        if len(values) < 53:
            continue
        code = key[2:]
        result[code] = {
            "name": values[1],
            "price": _float(values[3]),
            "last_close": _float(values[4]),
            "open": _float(values[5]),
            "change_amt": _float(values[31]),
            "change_pct": _float(values[32]),
            "high": _float(values[33]),
            "low": _float(values[34]),
            "amount_wan": _float(values[37]),
            "turnover_pct": _float(values[38]),
            "pe_ttm": _float(values[39]),
            "amplitude_pct": _float(values[43]),
            "mcap_yi": _float(values[44]),
            "float_mcap_yi": _float(values[45]),
            "pb": _float(values[46]),
            "limit_up": _float(values[47]),
            "limit_down": _float(values[48]),
            "vol_ratio": _float(values[49]),
            "pe_static": _float(values[52]),
            "source": "tencent_quote",
        }
    return result


def fetch_eastmoney_macro_report(report_name: str, *, page_size: int = 1000) -> list[dict[str, Any]]:
    params = {
        "reportName": report_name,
        "columns": "ALL",
        "pageNumber": "1",
        "pageSize": str(page_size),
        "sortColumns": "REPORT_DATE",
        "sortTypes": "-1",
        "source": "WEB",
        "client": "WEB",
    }
    payload = _urlopen_json(EASTMONEY_DATACENTER_URL, params=params, timeout=20)
    return ((payload.get("result") or {}).get("data") or []) if isinstance(payload, dict) else []


def default_end_date() -> str:
    return datetime.now().strftime("%Y%m%d")


def default_start_date(days: int = 365) -> str:
    return (datetime.now() - timedelta(days=days)).strftime("%Y%m%d")


def normalize_series(rows: list[dict[str, Any]], field: str) -> list[float | None]:
    values = [row.get(field) for row in rows]
    first = next((value for value in values if isinstance(value, (int, float)) and value), None)
    if not first:
        return values
    return [round(float(value) / float(first) * 100, 2) if isinstance(value, (int, float)) else None for value in values]


def _transform_values(values: list[float | None], transform: str = "none") -> list[float | None]:
    transform = str(transform or "none").lower()
    if transform in {"delta_from_100", "subtract_100", "index_yoy_to_pct"}:
        return [round(float(value) - 100.0, 4) if isinstance(value, (int, float)) else None for value in values]
    return values


def build_eastmoney_macro_chart_spec(request: dict[str, Any]) -> dict[str, Any] | None:
    preset_key = str(request.get("preset") or request.get("indicator") or request.get("metric_id") or "").strip()
    preset = EASTMONEY_MACRO_PRESETS.get(preset_key, {})
    report_name = str(request.get("report_name") or preset.get("report_name") or "").strip()
    if not report_name:
        raise ValueError("中国宏观/地产数据请求缺少 preset 或 report_name")
    field = str(request.get("field") or preset.get("field") or "").strip()
    if not field:
        raise ValueError("中国宏观/地产数据请求缺少 field")
    title = request.get("title") or preset.get("label") or "中国宏观数据"
    unit = str(request.get("unit") or preset.get("unit") or field)
    start_date = request.get("start_date")
    end_date = request.get("end_date")
    rows = fetch_eastmoney_macro_report(report_name, page_size=int(request.get("page_size") or 2000))
    rows = [_macro_row_with_date(row) for row in rows]
    rows = [row for row in rows if row.get("date")]
    rows = _filter_rows_by_date(rows, start_date=start_date, end_date=end_date)
    source_url = str(request.get("source_url") or preset.get("source_url") or "https://data.eastmoney.com/cjsj/")
    source_name = "东方财富数据中心（宏观）"
    transform = str(request.get("transform") or preset.get("transform") or "none")
    if report_name == "RPT_ECONOMY_HOUSE_PRICE" or str(request.get("kind") or "").lower() in {"china_house_price", "china_real_estate"}:
        spec = _build_city_macro_chart_spec(request, rows, field=field, title=str(title), unit=unit, source_name=source_name, source_url=source_url, preset=preset, transform=transform)
    else:
        label = str(request.get("label") or preset.get("label") or field)
        points = sorted(
            [{"date": row["date"], "value": _float(row.get(field))} for row in rows if _float(row.get(field)) is not None],
            key=lambda item: item["date"],
        )
        if not points:
            return None
        values = [item["value"] for item in points]
        values = _transform_values(values, transform)
        if request.get("normalize"):
            values = normalize_series([{"value": value} for value in values], "value")
        spec = _macro_spec(
            request,
            title=str(title),
            labels=[item["date"] for item in points],
            datasets=[
                {
                    "label": f"{label}{'（起点=100）' if request.get('normalize') else ''}",
                    "data": values,
                    "borderColor": "#1a6fb5",
                    "backgroundColor": "rgba(26,111,181,.10)",
                    "tension": 0.25,
                    "fill": False,
                    "spanGaps": True,
                }
            ],
            field=field,
            unit=unit,
            source_name=source_name,
            source_url=source_url,
            source_key=report_name,
            row_count=len(rows),
            transform=transform,
        )
    return spec


def build_kline_chart_spec(request: dict[str, Any]) -> dict[str, Any] | None:
    symbols = request.get("symbols") or request.get("codes") or request.get("code") or request.get("symbol")
    if isinstance(symbols, (str, dict)):
        symbols = [symbols]
    if not isinstance(symbols, list) or not symbols:
        return None
    start_date = request.get("start_date") or default_start_date(int(request.get("days") or 365))
    end_date = request.get("end_date") or default_end_date()
    field = str(request.get("field") or "close")
    normalize = bool(request.get("normalize"))
    data_source = str(request.get("data_source") or request.get("source_provider") or "").lower()
    series_payloads = []
    for symbol in symbols:
        if data_source == "yfinance" or is_yfinance_symbol(symbol):
            series_payloads.append(fetch_global_market_history(symbol, start_date=start_date, end_date=end_date, interval=str(request.get("interval") or "1d")))
        else:
            series_payloads.append(fetch_kline(symbol, start_date=start_date, end_date=end_date, period=str(request.get("period") or "daily"), adjust=str(request.get("adjust") or "qfq")))
    series_payloads = [item for item in series_payloads if item.get("rows")]
    if not series_payloads:
        return None
    labels = [row["date"] for row in series_payloads[0]["rows"]]
    palette = request.get("colors") or ["#1a6fb5", "#c41230", "#667085", "#0f766e", "#9333ea"]
    datasets = []
    for index, payload in enumerate(series_payloads):
        rows = payload["rows"]
        values = normalize_series(rows, field) if normalize else [row.get(field) for row in rows]
        if len(rows) != len(labels):
            by_date = {row["date"]: row.get(field) for row in rows}
            values = [by_date.get(label) for label in labels]
            if normalize:
                values = normalize_series([{"v": value} for value in values], "v")
        label = _symbol_label(symbols[index], payload)
        datasets.append(
            {
                "label": f"{label}{'（起点=100）' if normalize else ''}",
                "data": values,
                "borderColor": palette[index % len(palette)],
                "backgroundColor": "rgba(26,111,181,.10)" if index == 0 else "rgba(196,18,48,.10)",
                "tension": 0.25,
                "fill": False,
                "spanGaps": True,
            }
        )
    title = request.get("title") or "市场价格走势"
    request_id = str(request.get("id") or _chart_id(title))
    unit = str(request.get("unit") or ("指数化" if normalize else field))
    source_key = str(series_payloads[0].get("source") or "")
    source_name = _source_label(source_key)
    source_url = request.get("source_url") or _source_url(source_key)
    spec = {
        "id": request_id,
        "title": title,
        "type": "line",
        "labels": labels,
        "datasets": datasets,
        "caption": request.get("caption") or f"字段：{field}；单位/口径：{unit}；区间：{start_date} 至 {end_date}；数据源：{source_name}。",
        "source": request.get("source") or source_name,
        "source_url": source_url,
        "meta": {
            "request_id": request_id,
            "claim_id": request.get("claim_id"),
            "section_id": request.get("section_id"),
            "metric_id": request.get("metric_id") or request.get("metric"),
            "usage_type": request.get("usage_type") or "chart",
            "field": field,
            "unit": unit,
            "frequency": request.get("frequency") or request.get("period") or "daily",
            "date_range": {"start_date": str(start_date), "end_date": str(end_date)},
            "symbols": [_symbol_label(symbol, series_payloads[index]) for index, symbol in enumerate(symbols[: len(series_payloads)])],
            "provenance": _build_provenance(source_key, source_name, source_url, series_payloads),
            "data_quality": _build_series_quality(datasets, labels, series_payloads),
        },
        "options": {"scales": {"y": {"title": {"display": True, "text": unit}}}},
    }
    _attach_binding_fields(spec, request)
    return spec


def _macro_row_with_date(row: dict[str, Any]) -> dict[str, Any]:
    next_row = dict(row)
    raw_date = str(row.get("REPORT_DATE") or row.get("date") or "")
    if raw_date:
        next_row["date"] = raw_date[:10]
    elif row.get("TIME"):
        next_row["date"] = str(row.get("TIME"))
    return next_row


def _filter_rows_by_date(rows: list[dict[str, Any]], *, start_date: Any = None, end_date: Any = None) -> list[dict[str, Any]]:
    start = re.sub(r"[^0-9]", "", str(start_date or ""))
    end = re.sub(r"[^0-9]", "", str(end_date or ""))
    result = []
    for row in rows:
        compact = re.sub(r"[^0-9]", "", str(row.get("date") or ""))[:8]
        if start and compact and compact < start:
            continue
        if end and compact and compact > end:
            continue
        result.append(row)
    return result


def _build_city_macro_chart_spec(
    request: dict[str, Any],
    rows: list[dict[str, Any]],
    *,
    field: str,
    title: str,
    unit: str,
    source_name: str,
    source_url: str,
    preset: dict[str, Any],
    transform: str,
) -> dict[str, Any] | None:
    raw_cities = request.get("cities") or request.get("city") or request.get("entities") or preset.get("default_cities") or []
    if isinstance(raw_cities, (str, dict)):
        raw_cities = [raw_cities]
    cities = []
    for item in raw_cities:
        if isinstance(item, dict):
            city = str(item.get("city") or item.get("name") or item.get("label") or "").strip()
            label = str(item.get("label") or city).strip()
        else:
            city = str(item).strip()
            label = city
        if city:
            cities.append({"city": city, "label": label})
    if not cities:
        return None
    dates = sorted({row["date"] for row in rows if row.get("CITY") in {item["city"] for item in cities} and _float(row.get(field)) is not None})
    if not dates:
        return None
    palette = request.get("colors") or ["#1a6fb5", "#c41230", "#667085", "#0f766e", "#9333ea"]
    datasets = []
    for index, item in enumerate(cities):
        by_date = {row["date"]: _float(row.get(field)) for row in rows if row.get("CITY") == item["city"]}
        values = [by_date.get(date) for date in dates]
        values = _transform_values(values, transform)
        if request.get("normalize"):
            values = normalize_series([{"value": value} for value in values], "value")
        datasets.append(
            {
                "label": f"{item['label']}{'（起点=100）' if request.get('normalize') else ''}",
                "data": values,
                "borderColor": palette[index % len(palette)],
                "backgroundColor": "rgba(26,111,181,.10)" if index == 0 else "rgba(196,18,48,.10)",
                "tension": 0.25,
                "fill": False,
                "spanGaps": True,
            }
        )
    return _macro_spec(
        request,
        title=title,
        labels=dates,
        datasets=datasets,
        field=field,
        unit=unit,
        source_name=source_name,
        source_url=source_url,
        source_key="RPT_ECONOMY_HOUSE_PRICE",
        row_count=len(rows),
        transform=transform,
    )


def _macro_spec(
    request: dict[str, Any],
    *,
    title: str,
    labels: list[str],
    datasets: list[dict[str, Any]],
    field: str,
    unit: str,
    source_name: str,
    source_url: str,
    source_key: str,
    row_count: int,
    transform: str = "none",
) -> dict[str, Any]:
    request_id = str(request.get("id") or _chart_id(title))
    spec = {
        "id": request_id,
        "title": title,
        "type": "line",
        "labels": labels,
        "datasets": datasets,
        "caption": request.get("caption") or f"字段：{field}；单位/口径：{unit}；数据源：{source_name}。",
        "source": request.get("source") or source_name,
        "source_url": source_url,
        "meta": {
            "request_id": request_id,
            "claim_id": request.get("claim_id"),
            "section_id": request.get("section_id"),
            "metric_id": request.get("metric_id") or request.get("metric") or request.get("preset") or request.get("indicator"),
            "usage_type": request.get("usage_type") or "chart",
            "field": field,
            "transform": transform,
            "unit": unit,
            "frequency": request.get("frequency") or "monthly",
            "date_range": {"start_date": str(request.get("start_date") or ""), "end_date": str(request.get("end_date") or "")},
            "provenance": {
                "source_key": source_key,
                "source": source_name,
                "source_url": source_url,
                "fetched_at": datetime.now().astimezone().isoformat(),
                "cache_status": "live",
                "raw_row_count": row_count,
            },
            "data_quality": _build_series_quality(datasets, labels, [{"source": source_key}]),
        },
        "options": {"scales": {"y": {"title": {"display": True, "text": unit}}}},
    }
    _attach_binding_fields(spec, request)
    return spec


def _source_label(source: str) -> str:
    if source == "yahoo_chart_api":
        return "Yahoo Finance Chart API"
    if source == "yahoo_chart_cache_stale":
        return "Yahoo Finance 本地缓存"
    if source == "yfinance":
        return "Yahoo Finance / yfinance"
    if source == "baidu_gushitong_kline":
        return "百度股市通 K线"
    return "东方财富 push2his K线"


def _source_url(source: str) -> str:
    if source in {"yfinance", "yahoo_chart_api", "yahoo_chart_cache_stale"}:
        return "https://finance.yahoo.com/"
    if source == "baidu_gushitong_kline":
        return "https://gushitong.baidu.com/"
    return "https://quote.eastmoney.com/"


def fetch_fmp_economic_calendar(from_date: str, to_date: str, api_key: str | None = None) -> list[dict[str, Any]]:
    key = api_key or os.environ.get("FMP_API_KEY")
    if not key:
        raise RuntimeError("缺少 FMP_API_KEY，无法获取经济日历")
    params = {"from": _date_dash(from_date), "to": _date_dash(to_date), "apikey": key}
    payload = _urlopen_json(FMP_ECONOMIC_CALENDAR_URL, params=params, timeout=20)
    return payload if isinstance(payload, list) else []


def build_economic_calendar_chart_spec(request: dict[str, Any]) -> dict[str, Any] | None:
    from_date = request.get("from_date") or request.get("start_date") or datetime.now().strftime("%Y-%m-%d")
    to_date = request.get("to_date") or request.get("end_date") or (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d")
    events = fetch_fmp_economic_calendar(str(from_date), str(to_date), api_key=request.get("api_key"))
    countries = set(request.get("countries") or [])
    if countries:
        events = [item for item in events if str(item.get("country") or "").upper() in {c.upper() for c in countries}]
    if not events:
        return None
    counts = {"High": 0, "Medium": 0, "Low": 0, "Other": 0}
    for event in events:
        impact = str(event.get("impact") or "Other")
        counts[impact if impact in counts else "Other"] += 1
    request_id = str(request.get("id") or "economic-calendar-impact")
    source_url = "https://financialmodelingprep.com/"
    spec = {
        "id": request_id,
        "title": request.get("title") or "经济数据发布日历：按影响等级统计",
        "type": "bar",
        "labels": list(counts.keys()),
        "datasets": [{"label": "事件数量", "data": list(counts.values()), "backgroundColor": ["#c41230", "#1a6fb5", "#667085", "#d7dce5"]}],
        "caption": request.get("caption") or f"区间：{_date_dash(str(from_date))} 至 {_date_dash(str(to_date))}；事件明细来自 FMP Economic Calendar。",
        "source": "FMP Economic Calendar",
        "source_url": source_url,
        "meta": {
            "request_id": request_id,
            "claim_id": request.get("claim_id"),
            "section_id": request.get("section_id"),
            "metric_id": request.get("metric_id") or request.get("metric") or "economic_calendar",
            "usage_type": request.get("usage_type") or "chart",
            "unit": "事件数量",
            "frequency": "event",
            "date_range": {"start_date": _date_dash(str(from_date)), "end_date": _date_dash(str(to_date))},
            "events": events[:50],
            "event_count": len(events),
            "provenance": {
                "source_key": "fmp_economic_calendar",
                "source": "FMP Economic Calendar",
                "source_url": source_url,
                "fetched_at": datetime.now().astimezone().isoformat(),
                "cache_status": "live",
            },
            "data_quality": {
                "status": "pass",
                "point_count": len(events),
                "missing_points": 0,
                "warnings": [],
            },
        },
        "options": {"scales": {"y": {"beginAtZero": True, "title": {"display": True, "text": "事件数量"}}}},
    }
    _attach_binding_fields(spec, request)
    return spec


def _symbol_label(symbol: Any, payload: dict[str, Any]) -> str:
    if isinstance(symbol, dict):
        return str(symbol.get("label") or symbol.get("name") or payload.get("name") or payload.get("code"))
    return str(payload.get("name") or payload.get("code") or symbol)


def _chart_id(title: str) -> str:
    value = re.sub(r"[^0-9A-Za-z\u4e00-\u9fa5_-]+", "-", str(title)).strip("-").lower()
    return value or "finance-chart"


def _attach_binding_fields(spec: dict[str, Any], request: dict[str, Any]) -> None:
    for key in ("claim_id", "section_id", "metric_id", "usage_type"):
        value = request.get(key)
        if value:
            spec[key] = value


def _build_provenance(source_key: str, source_name: str, source_url: str, series_payloads: list[dict[str, Any]]) -> dict[str, Any]:
    cache_status = "stale_cache" if any(item.get("source") == "yahoo_chart_cache_stale" for item in series_payloads) else "live"
    warnings = [str(item.get("warning")) for item in series_payloads if item.get("warning")]
    return {
        "source_key": source_key,
        "source": source_name,
        "source_url": source_url,
        "fetched_at": datetime.now().astimezone().isoformat(),
        "cache_status": cache_status,
        "warnings": warnings,
    }


def _build_series_quality(datasets: list[dict[str, Any]], labels: list[str], series_payloads: list[dict[str, Any]]) -> dict[str, Any]:
    point_count = len(labels)
    missing_points = 0
    for dataset in datasets:
        missing_points += sum(1 for value in dataset.get("data") or [] if value is None)
    warnings = []
    if missing_points:
        warnings.append(f"存在 {missing_points} 个缺失数据点")
    if any(item.get("source") == "yahoo_chart_cache_stale" for item in series_payloads):
        warnings.append("使用了本地旧缓存")
    return {
        "status": "warning" if warnings else "pass",
        "point_count": point_count,
        "missing_points": missing_points,
        "warnings": warnings,
    }


def _request_id(request: dict[str, Any], index: int) -> str:
    return str(request.get("id") or request.get("title") or f"finance_request_{index}")


def build_finance_chart_specs_with_report(requests: list[dict[str, Any]] | None) -> dict[str, Any]:
    specs = []
    failures = []
    requests = requests or []
    for index, request in enumerate(requests, start=1):
        if not isinstance(request, dict):
            failures.append({"request_id": f"finance_request_{index}", "reason": "请求不是对象"})
            continue
        kind = str(request.get("kind") or request.get("type") or "kline").lower()
        if kind in {"kline", "price", "timeseries", "stock_kline", "index_kline", "global_market", "market", "commodity", "fx", "crypto", "yield"}:
            try:
                spec = build_kline_chart_spec(request)
            except Exception as exc:
                spec = None
                failures.append({"request_id": _request_id(request, index), "kind": kind, "reason": str(exc)})
            if spec:
                specs.append(spec)
            elif not any(item.get("request_id") == _request_id(request, index) for item in failures):
                failures.append({"request_id": _request_id(request, index), "kind": kind, "reason": "行情接口返回空序列"})
        elif kind in {"china_macro", "eastmoney_macro", "china_real_estate", "china_house_price"}:
            try:
                spec = build_eastmoney_macro_chart_spec(request)
            except Exception as exc:
                spec = None
                failures.append({"request_id": _request_id(request, index), "kind": kind, "reason": str(exc)})
            if spec:
                specs.append(spec)
            elif not any(item.get("request_id") == _request_id(request, index) for item in failures):
                failures.append({"request_id": _request_id(request, index), "kind": kind, "reason": "宏观/地产接口返回空序列"})
        elif kind in {"economic_calendar", "economics_calendar", "macro_calendar"}:
            try:
                spec = build_economic_calendar_chart_spec(request)
            except Exception as exc:
                spec = None
                failures.append({"request_id": _request_id(request, index), "kind": kind, "reason": str(exc)})
            if spec:
                specs.append(spec)
            elif not any(item.get("request_id") == _request_id(request, index) for item in failures):
                failures.append({"request_id": _request_id(request, index), "kind": kind, "reason": "经济日历返回空结果"})
        else:
            failures.append({"request_id": _request_id(request, index), "kind": kind, "reason": "不支持的金融数据请求类型"})
    validation = build_validation_report(requests, specs, failures)
    return {"chart_specs": specs, "failures": failures, "validation_report": validation}


def build_finance_chart_specs(requests: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    return list(build_finance_chart_specs_with_report(requests).get("chart_specs") or [])


def build_validation_report(requests: list[Any], specs: list[dict[str, Any]], failures: list[dict[str, Any]]) -> dict[str, Any]:
    warnings = []
    for spec in specs:
        quality = ((spec.get("meta") or {}).get("data_quality") or {})
        for warning in quality.get("warnings") or []:
            warnings.append({"request_id": spec.get("id"), "reason": warning})
    return {
        "requested_count": len(requests),
        "generated_count": len(specs),
        "failure_count": len(failures),
        "warning_count": len(warnings),
        "status": "fail" if failures else ("warning" if warnings else "pass"),
        "warnings": warnings,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Build finance data chart specs for Newma Draft")
    sub = parser.add_subparsers(dest="command", required=True)
    chart_parser = sub.add_parser("chart-specs")
    chart_parser.add_argument("--requests-file", required=True)
    chart_parser.add_argument("--output")
    chart_parser.add_argument("--report", action="store_true", help="输出 chart_specs 与失败明细，而不是仅输出图表数组")
    quote_parser = sub.add_parser("quote")
    quote_parser.add_argument("symbols", nargs="+")
    args = parser.parse_args()
    if args.command == "chart-specs":
        payload = read_json(Path(args.requests_file))
        requests_payload = (
            payload.get("finance_chart_requests")
            or payload.get("market_data_requests")
            or payload.get("data_requests")
            if isinstance(payload, dict)
            else payload
        )
        report = build_finance_chart_specs_with_report(requests_payload)
        output_payload = report if args.report else report.get("chart_specs", [])
        if args.output:
            write_json(Path(args.output), output_payload)
        print(json.dumps(output_payload, ensure_ascii=False, indent=2))
    elif args.command == "quote":
        print(json.dumps(fetch_tencent_quotes(args.symbols), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
