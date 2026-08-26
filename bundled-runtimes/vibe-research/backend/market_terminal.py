"""Unified market-terminal data contract for VibeDesk.

The terminal intentionally exposes one normalized contract across A shares,
Hong Kong stocks and US stocks.  Source routing follows the bundled
``a-stock-data`` and ``global-stock-data`` skills:

* A-share quote/order book: Tencent; OHLCV: Tencent daily/minute K-line first,
  mootdx as a fallback.
* US/HK quote: the existing global-stock-data router in :mod:`gstock`.
* US OHLCV: Sina daily K-line first, authenticated Yahoo as fallback.
* HK OHLCV: Tencent daily K-line first, authenticated Yahoo as fallback.

All functions return objective market data only.  The UI and Agent receive the
same normalized symbol, quote and bar fields, so changing chart engines does
not change the VibeDesk protocol.
"""

from __future__ import annotations

import json
import re
import socket
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from typing import Any
from zoneinfo import ZoneInfo

import requests

import astock
import gstock
import security_master


SEARCH_URL = "https://searchapi.eastmoney.com/api/suggest/get"
SEARCH_TOKEN = "D43BF722C8E33BDC906FB84D85E326E8"
FUND_SUGGEST_URL = "https://fundsuggest.eastmoney.com/FundSearch/api/FundSearchAPI.ashx"
TENCENT_SEARCH_URL = "https://smartbox.gtimg.cn/s3/"
TENCENT_KLINE_URL = "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get"
TENCENT_HK_KLINE_URL = "https://web.ifzq.gtimg.cn/appstock/app/kline/kline"
TENCENT_MINUTE_KLINE_URL = "https://ifzq.gtimg.cn/appstock/app/kline/mkline"
TENCENT_DAY_MINUTE_URL = "https://web.ifzq.gtimg.cn/appstock/app/day/query"
EASTMONEY_KLINE_URL = "https://push2his.eastmoney.com/api/qt/stock/kline/get"
SINA_US_KLINE_URL = "https://stock.finance.sina.com.cn/usstock/api/jsonp.php/var/US_MinKService.getDailyK"
SINA_US_MINUTE_URL = "https://stock.finance.sina.com.cn/usstock/api/jsonp.php/var/US_MinKService.getMinK"
SINA_CN_KLINE_URL = "https://money.finance.sina.com.cn/quotes_service/api/json_v2.php/CN_MarketData.getKLineData"
YAHOO_CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
YAHOO_CRUMB_URLS = (
    "https://query1.finance.yahoo.com/v1/test/getcrumb",
    "https://query2.finance.yahoo.com/v1/test/getcrumb",
)

_SUPPORTED_MKT = {0, 1, 105, 106, 107, 116, 150}
_CN_ETF_CODE = re.compile(r"^(?:159\d{3}|5(?:1\d|2[0-3]|6[0-3]|88)\d{3})$")
_TDX_SERVERS = (
    ("119.97.185.59", 7709),
    ("124.70.133.119", 7709),
    ("116.205.183.150", 7709),
    ("123.60.73.44", 7709),
    ("116.205.163.254", 7709),
)
_tdx_client_cache: list[Any | None] = [None]
_yahoo_session_cache: list[Any | None] = [None]
_CHINA_TIMEZONE = ZoneInfo("Asia/Shanghai")
_NEW_YORK_TIMEZONE = ZoneInfo("America/New_York")
_SCAN_CACHE: dict[tuple[str, str, str, int], tuple[float, dict[str, Any]]] = {}
_FUND_PROFILE_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}

_SCAN_MARKETS = {
    "CN": "m:0 t:6,m:0 t:80,m:1 t:2,m:1 t:23,m:0 t:81 s:2048",
    "HK": "m:116+t:3,m:116+t:4,m:116+t:1,m:116+t:2",
    "US": "m:105,m:106,m:107",
}
_SCAN_SORT_FIELDS = {
    "changePct": "f3",
    "amount": "f6",
    "turnoverPct": "f8",
    "pe": "f9",
    "volumeRatio": "f10",
    "marketCap": "f20",
    "pb": "f23",
}


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _float(value: Any) -> float | None:
    try:
        if value in (None, "", "-"):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _asset_type(security_type: str, *, name: str = "", code: str = "", mkt_num: int | None = None) -> str:
    value = f"{security_type} {name}".casefold()
    if mkt_num == 150:
        return "fund"
    if "etf联接" in value or "etf连接" in value:
        return "fund"
    if "etf" in value or "交易型开放式" in value or _CN_ETF_CODE.fullmatch(code):
        return "etf"
    if "指数" in security_type or "index" in value:
        return "index"
    if "基金" in security_type or "fund" in value:
        return "fund"
    return "stock"


def _search_row(row: dict[str, Any]) -> dict[str, Any] | None:
    try:
        mkt_num = int(row.get("MktNum"))
    except (TypeError, ValueError):
        return None
    if mkt_num not in _SUPPORTED_MKT:
        return None
    code = str(row.get("Code") or "").strip().upper()
    if not code:
        return None
    security_type = str(row.get("SecurityTypeName") or "")
    if mkt_num == 150:
        market, exchange, currency, timezone = "CN", "OTC", "CNY", "Asia/Shanghai"
    elif mkt_num == 116:
        market, exchange, currency, timezone = "HK", "HKEX", "HKD", "Asia/Hong_Kong"
    elif mkt_num in {105, 106, 107}:
        market = "US"
        exchange = {105: "NASDAQ", 106: "NYSE", 107: "US"}[mkt_num]
        currency, timezone = "USD", "America/New_York"
    else:
        market = "CN"
        if "京" in security_type:
            exchange = "BJ"
        else:
            exchange = "SH" if mkt_num == 1 else "SZ"
        currency, timezone = "CNY", "Asia/Shanghai"
    return {
        "symbol": code,
        "name": str(row.get("Name") or code),
        "market": market,
        "exchange": exchange,
        "currency": currency,
        "timezone": timezone,
        "assetType": _asset_type(security_type, name=str(row.get("Name") or code), code=code, mkt_num=mkt_num),
        "securityType": security_type,
        "quoteId": str(row.get("QuoteID") or f"{mkt_num}.{code}"),
        "source": "eastmoney-search",
    }


def _tencent_search_symbols(query: str, *, limit: int, market: str) -> list[dict[str, Any]]:
    try:
        response = requests.get(
            TENCENT_SEARCH_URL,
            params={"q": query, "t": "all"},
            headers={"User-Agent": astock.UA, "Referer": "https://gu.qq.com/"},
            timeout=10,
        )
        response.raise_for_status()
        match = re.search(r'v_hint="(.*)"', response.text)
        content = json.loads(f'"{match.group(1)}"') if match else ""
    except (requests.RequestException, ValueError, json.JSONDecodeError):
        return []
    items: list[dict[str, Any]] = []
    for raw in content.split("^"):
        fields = raw.split("~")
        if len(fields) < 3:
            continue
        prefix, code, name = fields[:3]
        if prefix in {"sh", "sz", "bj"}:
            market_id = "CN"
            exchange = prefix.upper()
            currency, timezone = "CNY", "Asia/Shanghai"
        elif prefix == "hk":
            market_id, exchange = "HK", "HKEX"
            code = code.zfill(5)
            currency, timezone = "HKD", "Asia/Hong_Kong"
        elif prefix == "us":
            market_id, exchange = "US", "US"
            code = code.split(".", 1)[0].upper()
            currency, timezone = "USD", "America/New_York"
        else:
            continue
        if market in {"CN", "HK", "US"} and market_id != market:
            continue
        security_type = fields[4] if len(fields) > 4 else ""
        items.append({
            "symbol": code,
            "name": name or code,
            "market": market_id,
            "exchange": exchange,
            "currency": currency,
            "timezone": timezone,
            "assetType": _asset_type(security_type, name=name, code=code),
            "securityType": security_type,
            "quoteId": f"{market_id}:{code}",
            "source": "tencent-search",
        })
        if len(items) >= limit:
            break
    return items


def _fund_search_symbols(query: str, *, limit: int) -> list[dict[str, Any]]:
    """Search Eastmoney funds by code, Chinese name or pinyin abbreviation."""
    try:
        response = astock.em_get(
            FUND_SUGGEST_URL,
            params={"m": 1, "key": query},
            headers={"User-Agent": astock.UA, "Referer": "https://fund.eastmoney.com/"},
            timeout=10,
        )
        response.raise_for_status()
        rows = response.json().get("Datas") or []
    except (requests.RequestException, ValueError):
        return []

    items: list[dict[str, Any]] = []
    for row in rows:
        if str(row.get("CATEGORY") or "") != "700" and str(row.get("CATEGORYDESC") or "").strip() != "基金":
            continue
        base = row.get("FundBaseInfo") or {}
        code = str(row.get("CODE") or base.get("FCODE") or "").strip()
        if not re.fullmatch(r"\d{6}", code):
            continue
        name = str(row.get("NAME") or base.get("SHORTNAME") or code).strip()
        security_type = str(base.get("FTYPE") or row.get("CATEGORYDESC") or "开放式基金")
        asset_type = "etf" if _CN_ETF_CODE.fullmatch(code) else "fund"
        if asset_type == "etf":
            exchange = "SH" if code.startswith("5") else "SZ"
            quote_id = f"{1 if exchange == 'SH' else 0}.{code}"
        else:
            exchange = "OTC"
            quote_id = f"150.{code}"
        items.append({
            "symbol": code,
            "name": name,
            "market": "CN",
            "exchange": exchange,
            "currency": "CNY",
            "timezone": "Asia/Shanghai",
            "assetType": asset_type,
            "securityType": security_type,
            "quoteId": quote_id,
            "source": "eastmoney-fund-search",
        })
        if len(items) >= limit:
            break
    return items


def search_symbols(query: str, *, limit: int = 12, market: str = "ALL") -> dict[str, Any]:
    """Search CN/HK/US securities and normalize market identity."""
    clean = query.strip()
    if not clean:
        return {"items": [], "asOf": _now_iso(), "source": "eastmoney-search"}
    selected_market = market.strip().upper()
    local_items = security_master.search(clean, limit=limit)
    if selected_market == "CN":
        normalized = local_items
    elif selected_market == "ALL":
        normalized = local_items
    else:
        normalized = []
    params = {
        "input": clean,
        "type": 14,
        "token": SEARCH_TOKEN,
        "count": max(limit * 2, 20),
        "cb": "callback",
        "_": int(datetime.now(UTC).timestamp() * 1000),
    }
    payload: dict[str, Any] = {}
    # SearchAPI sometimes reuses an incompatible JSONP cookie on the shared
    # Eastmoney session.  A short-lived session keeps symbol search isolated;
    # direct access remains preferred and the user's proxy is a fallback.
    for direct in (True, False):
        try:
            session = requests.Session()
            session.trust_env = not direct
            response = session.get(
                SEARCH_URL,
                params=params,
                headers={"User-Agent": astock.UA, "Referer": "https://quote.eastmoney.com/"},
                timeout=10,
            )
            response.raise_for_status()
            text = response.text.strip()
            if not text.startswith("{"):
                start, end = text.find("("), text.rfind(")")
                if start >= 0 and end > start:
                    text = text[start + 1:end]
            payload = json.loads(text)
            if "QuotationCodeTable" in payload:
                break
        except (requests.RequestException, ValueError):
            continue
    rows = ((payload.get("QuotationCodeTable") or {}).get("Data") or [])
    normalized.extend(item for row in rows if (item := _search_row(row)) is not None)
    if selected_market in {"CN", "HK", "US"}:
        normalized = [item for item in normalized if item["market"] == selected_market]
    has_primary_results = bool(normalized)
    normalized.extend(_tencent_search_symbols(clean, limit=limit, market=selected_market))
    should_search_funds = selected_market == "CN" or (
        selected_market == "ALL"
        and (not has_primary_results or bool(re.search(r"[\u4e00-\u9fff]", clean)) or bool(re.fullmatch(r"\d{6}", clean)))
    )
    if should_search_funds:
        normalized.extend(_fund_search_symbols(clean, limit=limit))

    exact = clean.upper()
    normalized.sort(key=lambda item: (item["symbol"] != exact, item["name"] != clean))
    items: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for item in normalized:
        key = (item["market"], item["symbol"])
        if key in seen:
            continue
        seen.add(key)
        items.append(item)
        if len(items) >= limit:
            break
    return {
        "items": items,
        "asOf": _now_iso(),
        "source": "eastmoney-search",
    }


def _split_symbol(value: str) -> tuple[str, str]:
    clean = value.strip().upper()
    if ":" in clean:
        market, symbol = clean.split(":", 1)
        if market in {"CN", "HK", "US"} and symbol:
            return market, symbol
    if clean.endswith(".HK"):
        return "HK", clean[:-3].zfill(5)
    if clean.endswith(".US"):
        return "US", clean[:-3]
    if re.fullmatch(r"\d{6}", clean):
        return "CN", clean
    if re.fullmatch(r"\d{1,5}", clean):
        return "HK", clean.zfill(5)
    return "US", clean


def _quote_identity(market: str, symbol: str, name: str = "") -> dict[str, Any]:
    if market == "CN":
        exchange = "SH" if astock.get_prefix(symbol) == "sh" else ("BJ" if astock.get_prefix(symbol) == "bj" else "SZ")
        currency, timezone = "CNY", "Asia/Shanghai"
    elif market == "HK":
        exchange, currency, timezone = "HKEX", "HKD", "Asia/Hong_Kong"
    else:
        exchange, currency, timezone = "US", "USD", "America/New_York"
    return {
        "symbol": symbol,
        "name": name or symbol,
        "market": market,
        "exchange": exchange,
        "currency": currency,
        "timezone": timezone,
    }


def _cn_quote(symbol: str, raw: dict[str, Any]) -> dict[str, Any]:
    identity = _quote_identity("CN", symbol, str(raw.get("name") or symbol))
    return {
        **identity,
        "price": raw.get("price"),
        "change": raw.get("change_amt"),
        "changePct": raw.get("change_pct"),
        "prevClose": raw.get("last_close"),
        "open": raw.get("open"),
        "high": raw.get("high"),
        "low": raw.get("low"),
        "volume": raw.get("volume"),
        "amount": (raw.get("amount_wan") or 0) * 10_000,
        "turnoverPct": raw.get("turnover_pct"),
        "marketCap": (raw.get("mcap_yi") or 0) * 100_000_000,
        "floatMarketCap": (raw.get("float_mcap_yi") or 0) * 100_000_000,
        "pe": raw.get("pe_ttm"),
        "pb": raw.get("pb"),
        "amplitudePct": raw.get("amplitude_pct"),
        "volumeRatio": raw.get("vol_ratio"),
        "limitUp": raw.get("limit_up"),
        "limitDown": raw.get("limit_down"),
        "orderBook": {
            "bids": raw.get("bids") or [],
            "asks": raw.get("asks") or [],
        },
        "trades": [],
        "source": "tencent",
        "sources": ["tencent"],
        "asOf": _now_iso(),
    }


def _global_quote(market: str, symbol: str, raw: dict[str, Any]) -> dict[str, Any]:
    quote = raw.get("quote") or {}
    price = quote.get("price")
    prev_close = quote.get("prev_close")
    change = None
    if isinstance(price, (int, float)) and isinstance(prev_close, (int, float)):
        change = price - prev_close
    identity = _quote_identity(market, symbol, str(raw.get("name") or symbol))
    if raw.get("market") and market == "US":
        identity["exchange"] = raw["market"]
    return {
        **identity,
        "price": price,
        "change": change,
        "changePct": quote.get("change_pct"),
        "prevClose": prev_close,
        "open": quote.get("open"),
        "high": quote.get("high"),
        "low": quote.get("low"),
        "volume": quote.get("volume"),
        "amount": quote.get("amount"),
        "turnoverPct": quote.get("turnover_rate"),
        "marketCap": quote.get("mcap"),
        "floatMarketCap": None,
        "pe": quote.get("pe"),
        "pb": quote.get("pb"),
        "amplitudePct": None,
        "volumeRatio": None,
        "limitUp": None,
        "limitDown": None,
        "orderBook": {"bids": [], "asks": []},
        "trades": [],
        "source": quote.get("source") or "global-stock-data",
        "sources": quote.get("sources") or raw.get("data_sources") or [],
        "asOf": _now_iso(),
    }


def _fund_profile(symbol: str) -> dict[str, Any]:
    hit = _FUND_PROFILE_CACHE.get(symbol)
    if hit and time.time() - hit[0] < 21_600:
        return hit[1]
    response = astock.em_get(
        FUND_SUGGEST_URL,
        params={"m": 1, "key": symbol},
        headers={"User-Agent": astock.UA, "Referer": "https://fund.eastmoney.com/"},
        timeout=10,
    )
    response.raise_for_status()
    row = next(
        (item for item in response.json().get("Datas") or [] if str(item.get("CODE") or "") == symbol),
        {},
    )
    base = row.get("FundBaseInfo") or {}
    profile = {
        "name": str(row.get("NAME") or base.get("SHORTNAME") or symbol),
        "fundType": str(base.get("FTYPE") or ""),
        "fundCompany": str(base.get("JJGS") or ""),
        "fundManager": str(base.get("JJJL") or ""),
        "minimumPurchase": _float(base.get("MINSG")),
    }
    _FUND_PROFILE_CACHE[symbol] = (time.time(), profile)
    return profile


def _fund_quote(symbol: str) -> dict[str, Any]:
    rows = astock.fund_nav_history(symbol, limit=2)
    if not rows or rows[0].get("unitNav") is None:
        return {}
    try:
        profile = _fund_profile(symbol)
    except Exception:  # noqa: BLE001 - NAV remains usable when profile metadata is unavailable
        profile = {}
    latest = rows[0]
    previous = rows[1] if len(rows) > 1 else {}
    price = float(latest["unitNav"])
    prev_close = previous.get("unitNav")
    change = price - float(prev_close) if prev_close is not None else None
    change_pct = latest.get("changePct")
    if change_pct is None and prev_close:
        change_pct = change / float(prev_close) * 100
    return {
        **_quote_identity("CN", symbol, str(profile.get("name") or symbol)),
        "exchange": "OTC",
        "assetType": "fund",
        "securityType": profile.get("fundType") or "开放式基金",
        "fundType": profile.get("fundType") or "",
        "fundCompany": profile.get("fundCompany") or "",
        "fundManager": profile.get("fundManager") or "",
        "minimumPurchase": profile.get("minimumPurchase"),
        "navDate": latest.get("date") or "",
        "cumulativeNav": latest.get("cumulativeNav"),
        "subscribeStatus": latest.get("subscribeStatus") or "",
        "redeemStatus": latest.get("redeemStatus") or "",
        "price": price,
        "change": change,
        "changePct": change_pct,
        "prevClose": prev_close,
        "open": price,
        "high": price,
        "low": price,
        "volume": None,
        "amount": None,
        "turnoverPct": None,
        "marketCap": None,
        "floatMarketCap": None,
        "pe": None,
        "pb": None,
        "amplitudePct": None,
        "volumeRatio": None,
        "limitUp": None,
        "limitDown": None,
        "orderBook": {"bids": [], "asks": []},
        "trades": [],
        "source": "eastmoney-fund-nav",
        "sources": ["eastmoney-fund-nav"] + (["eastmoney-fund-search"] if profile else []),
        "asOf": _now_iso(),
    }


def get_quotes(symbols: str) -> dict[str, Any]:
    """Return normalized quotes for ``MARKET:SYMBOL`` comma-separated inputs."""
    requested = [_split_symbol(item) for item in symbols.split(",") if item.strip()]
    cn_symbols = [symbol for market, symbol in requested if market == "CN"]
    cn_quotes = astock.tencent_quote(cn_symbols) if cn_symbols else {}
    global_requested = [(market, symbol) for market, symbol in requested if market != "CN"]

    def load_global(item: tuple[str, str]) -> tuple[tuple[str, str], dict[str, Any] | None]:
        market, symbol = item
        # The watchlist path values latency over full fundamentals.  It still
        # follows the global-stock-data primary/fallback order, while the
        # single-symbol endpoint keeps the complete Eastmoney enrichment.
        if market == "HK":
            quote = gstock._safe_quote(lambda: gstock._hk_quote_tencent(symbol))
            if not quote:
                quote = gstock._safe_quote(lambda: gstock._hk_quote_sina(symbol))
        else:
            quote = gstock._safe_quote(lambda: gstock._us_quote_sina(symbol))
            if not quote:
                quote = gstock._safe_quote(lambda: gstock._us_quote_tencent(symbol))
        raw = {
            "name": quote.get("name") or symbol,
            "market": market,
            "quote": {**quote, "sources": [quote.get("source")] if quote.get("source") else []},
        } if quote else None
        return item, _global_quote(market, symbol, raw) if raw else None

    global_quotes: dict[tuple[str, str], dict[str, Any]] = {}
    if global_requested:
        with ThreadPoolExecutor(max_workers=min(len(global_requested), 6)) as pool:
            for key, value in pool.map(load_global, global_requested):
                if value:
                    global_quotes[key] = value
    items: list[dict[str, Any]] = []
    for market, symbol in requested:
        if market == "CN":
            raw = cn_quotes.get(symbol)
            if raw:
                items.append(_cn_quote(symbol, raw))
            continue
        quote = global_quotes.get((market, symbol))
        if quote:
            items.append(quote)
    return {"items": items, "asOf": _now_iso()}


def get_quote(symbol: str, *, market: str = "", asset_type: str = "stock") -> dict[str, Any]:
    market_id, code = _split_symbol(f"{market}:{symbol}" if market else symbol)
    if asset_type == "fund":
        return _fund_quote(code)
    quotes = get_quotes(f"{market_id}:{code}")
    return {**quotes["items"][0], "assetType": asset_type} if quotes["items"] else {}


def scan_market_quotes(
    market: str,
    *,
    sort: str = "amount",
    order: str = "desc",
    limit: int = 100,
) -> dict[str, Any]:
    """Return a broad, normalized A/H/US scan universe without per-symbol calls."""
    market_id = market.strip().upper()
    if market_id not in _SCAN_MARKETS:
        raise ValueError("扫描市场必须是 CN、HK 或 US")
    if sort not in _SCAN_SORT_FIELDS:
        raise ValueError("不支持的扫描排序字段")
    if order not in {"asc", "desc"}:
        raise ValueError("扫描排序方向必须是 asc 或 desc")
    limit = min(max(int(limit), 20), 200)
    cache_key = (market_id, sort, order, limit)
    cached = _SCAN_CACHE.get(cache_key)
    if cached and time.time() - cached[0] < 20:
        return cached[1]

    params = {
        "pn": 1,
        "pz": limit,
        "po": 1 if order == "desc" else 0,
        "np": 1,
        "fltt": 2,
        "invt": 2,
        "fid": _SCAN_SORT_FIELDS[sort],
        "fs": _SCAN_MARKETS[market_id],
        "fields": "f2,f3,f4,f5,f6,f8,f9,f10,f12,f13,f14,f15,f16,f17,f18,f20,f21,f23,f100",
    }
    rows: list[dict[str, Any]] = []
    source = "eastmoney-delay"
    for host in ("push2delay.eastmoney.com", "push2.eastmoney.com"):
        try:
            response = astock.em_get(
                f"https://{host}/api/qt/clist/get",
                params=params,
                headers={"User-Agent": astock.UA, "Referer": "https://quote.eastmoney.com/"},
                timeout=10,
            )
            payload = response.json()
            raw_rows = (payload.get("data") or {}).get("diff") or []
            rows = list(raw_rows.values()) if isinstance(raw_rows, dict) else raw_rows
            if rows:
                source = "eastmoney-delay" if host.startswith("push2delay") else "eastmoney"
                break
        except Exception:  # noqa: BLE001 - next host is the explicit fallback
            continue

    items = []
    for row in rows:
        symbol = str(row.get("f12") or "").strip().upper()
        if not symbol:
            continue
        identity = _quote_identity(market_id, symbol, str(row.get("f14") or symbol))
        if market_id == "US":
            identity["exchange"] = {105: "NASDAQ", 106: "NYSE", 107: "US"}.get(row.get("f13"), "US")
        items.append({
            **identity,
            "price": _float(row.get("f2")),
            "change": _float(row.get("f4")),
            "changePct": _float(row.get("f3")),
            "prevClose": _float(row.get("f18")),
            "open": _float(row.get("f17")),
            "high": _float(row.get("f15")),
            "low": _float(row.get("f16")),
            "volume": _float(row.get("f5")),
            "amount": _float(row.get("f6")),
            "turnoverPct": _float(row.get("f8")),
            "marketCap": _float(row.get("f20")),
            "floatMarketCap": _float(row.get("f21")),
            "pe": _float(row.get("f9")),
            "pb": _float(row.get("f23")),
            "volumeRatio": _float(row.get("f10")),
            "industry": str(row.get("f100") or ""),
            "source": source,
            "sources": [source],
            "asOf": _now_iso(),
        })
    result = {
        "items": items,
        "market": market_id,
        "sort": sort,
        "order": order,
        "source": source,
        "asOf": _now_iso(),
        "coverage": {"requested": limit, "returned": len(items)},
    }
    _SCAN_CACHE[cache_key] = (time.time(), result)
    return result


def _parse_tencent_rows(rows: list[Any]) -> list[dict[str, Any]]:
    bars: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, (list, tuple)) or len(row) < 6:
            continue
        try:
            raw_timestamp = str(row[0]).strip()
            if re.fullmatch(r"\d{12}", raw_timestamp):
                parsed_timestamp = datetime.strptime(raw_timestamp, "%Y%m%d%H%M")
            elif re.fullmatch(r"\d{8}", raw_timestamp):
                parsed_timestamp = datetime.strptime(raw_timestamp, "%Y%m%d")
            else:
                parsed_timestamp = datetime.fromisoformat(raw_timestamp)
            if parsed_timestamp.tzinfo is None:
                parsed_timestamp = parsed_timestamp.replace(tzinfo=_CHINA_TIMEZONE)
            timestamp = int(parsed_timestamp.timestamp() * 1000)
            bars.append({
                "timestamp": timestamp,
                "open": float(row[1]),
                "close": float(row[2]),
                "high": float(row[3]),
                "low": float(row[4]),
                "volume": float(row[5]),
                "turnover": float(row[6]) if len(row) > 6 and _float(row[6]) is not None else 0,
            })
        except (TypeError, ValueError):
            continue
    return sorted(bars, key=lambda item: item["timestamp"])


def _tencent_ohlcv(symbol: str, timeframe: str, limit: int, adjust: str) -> list[dict[str, Any]]:
    period = {"1d": "day", "1w": "week", "1M": "month"}.get(timeframe)
    if period is None:
        return []
    prefixed = f"{astock.get_prefix(symbol)}{symbol}"
    adjustment = adjust if adjust in {"qfq", "hfq"} else ""
    response = requests.get(
        TENCENT_KLINE_URL,
        params={"param": f"{prefixed},{period},,,{limit},{adjustment}"},
        headers={"User-Agent": astock.UA, "Referer": "https://gu.qq.com/"},
        timeout=12,
    )
    response.raise_for_status()
    payload = response.json()
    if int(payload.get("code", -1)) != 0:
        return []
    block = (payload.get("data") or {}).get(prefixed) or {}
    rows = block.get(f"{adjustment}{period}") or block.get(period) or []
    return _parse_tencent_rows(rows)[-limit:]


def _eastmoney_ohlcv(symbol: str, timeframe: str, limit: int, adjust: str) -> list[dict[str, Any]]:
    """Fetch CN daily/weekly/monthly bars when the Tencent endpoint is unavailable."""
    klt = {"1d": "101", "1w": "102", "1M": "103"}.get(timeframe)
    if klt is None:
        return []
    prefix = astock.get_prefix(symbol)
    market = "1" if prefix == "sh" else "0"
    fqt = {"none": 0, "qfq": 1, "hfq": 2}.get(adjust, 0)
    response = requests.get(
        EASTMONEY_KLINE_URL,
        params={
            "secid": f"{market}.{symbol}",
            "klt": klt,
            "fqt": fqt,
            "beg": "0",
            "end": "20500000",
            "lmt": limit,
            "fields1": "f1,f2,f3,f4,f5,f6",
            "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61",
        },
        headers={"User-Agent": astock.UA, "Referer": "https://quote.eastmoney.com/"},
        timeout=12,
    )
    response.raise_for_status()
    payload = response.json()
    if int(payload.get("rc", -1)) != 0:
        return []
    rows = ((payload.get("data") or {}).get("klines") or [])
    bars: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, str):
            continue
        fields = row.split(",")
        if len(fields) < 7:
            continue
        try:
            parsed_timestamp = datetime.fromisoformat(fields[0]).replace(tzinfo=_CHINA_TIMEZONE)
            bars.append({
                "timestamp": int(parsed_timestamp.timestamp() * 1000),
                "open": float(fields[1]),
                "close": float(fields[2]),
                "high": float(fields[3]),
                "low": float(fields[4]),
                "volume": float(fields[5]),
                "turnover": float(fields[6]),
            })
        except (TypeError, ValueError):
            continue
    return sorted(bars, key=lambda item: item["timestamp"])[-limit:]


def _sina_cn_ohlcv(symbol: str, timeframe: str, limit: int) -> list[dict[str, Any]]:
    """Fetch unadjusted CN bars from Sina as a low-latency public fallback."""
    scale = {"1d": 240, "1w": 1200, "1M": 7200}.get(timeframe)
    if scale is None:
        return []
    prefixed = f"{astock.get_prefix(symbol)}{symbol}"
    response = requests.get(
        SINA_CN_KLINE_URL,
        params={"symbol": prefixed, "scale": scale, "ma": "no", "datalen": limit},
        headers={"User-Agent": astock.UA, "Referer": "https://finance.sina.com.cn/"},
        timeout=12,
    )
    response.raise_for_status()
    rows = response.json()
    if not isinstance(rows, list):
        return []
    bars: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        try:
            parsed_timestamp = datetime.fromisoformat(str(row["day"])).replace(tzinfo=_CHINA_TIMEZONE)
            bars.append({
                "timestamp": int(parsed_timestamp.timestamp() * 1000),
                "open": float(row["open"]),
                "close": float(row["close"]),
                "high": float(row["high"]),
                "low": float(row["low"]),
                "volume": float(row.get("volume") or 0),
                "turnover": 0,
            })
        except (KeyError, TypeError, ValueError):
            continue
    return sorted(bars, key=lambda item: item["timestamp"])[-limit:]


def _tencent_intraday_ohlcv(symbol: str, timeframe: str, limit: int) -> list[dict[str, Any]]:
    period = {"1m": "m1", "5m": "m5", "15m": "m15", "30m": "m30", "60m": "m60"}.get(timeframe)
    if period is None:
        return []
    prefixed = f"{astock.get_prefix(symbol)}{symbol}"
    response = requests.get(
        TENCENT_MINUTE_KLINE_URL,
        params={"param": f"{prefixed},{period},,{limit}"},
        headers={"User-Agent": astock.UA, "Referer": "https://gu.qq.com/"},
        timeout=12,
    )
    response.raise_for_status()
    payload = response.json()
    if int(payload.get("code", -1)) != 0:
        return []
    block = (payload.get("data") or {}).get(prefixed) or {}
    return _parse_tencent_rows(block.get(period) or [])[-limit:]


def _probe(ip: str, port: int, timeout: float = 0.8) -> bool:
    try:
        with socket.create_connection((ip, port), timeout=timeout):
            return True
    except OSError:
        return False


def _tdx_client():
    if _tdx_client_cache[0] is not None:
        return _tdx_client_cache[0]
    try:
        from mootdx.quotes import Quotes
    except ImportError as error:
        raise astock.DependencyMissing("mootdx 未安装：pip install mootdx") from error
    for server in _TDX_SERVERS:
        if not _probe(*server):
            continue
        try:
            _tdx_client_cache[0] = Quotes.factory(market="std", server=server)
            return _tdx_client_cache[0]
        except Exception:
            continue
    try:
        _tdx_client_cache[0] = Quotes.factory(market="std", bestip=True)
    except Exception as error:
        raise RuntimeError("所有 mootdx 行情服务器均不可达") from error
    return _tdx_client_cache[0]


def _mootdx_ohlcv(symbol: str, timeframe: str, limit: int) -> list[dict[str, Any]]:
    frequency = {"1m": 8, "5m": 0, "15m": 1, "30m": 2, "60m": 3, "1d": 9, "1w": 5, "1M": 6}.get(timeframe)
    if frequency is None:
        return []
    frame = _tdx_client().bars(symbol=symbol, frequency=frequency, offset=limit)
    if frame is None or getattr(frame, "empty", True):
        return []
    bars: list[dict[str, Any]] = []
    for row in frame.to_dict("records"):
        timestamp_value = row.get("datetime") or row.get("date")
        try:
            timestamp = int(datetime.fromisoformat(str(timestamp_value)).replace(tzinfo=UTC).timestamp() * 1000)
            bars.append({
                "timestamp": timestamp,
                "open": float(row.get("open")),
                "close": float(row.get("close")),
                "high": float(row.get("high")),
                "low": float(row.get("low")),
                "volume": float(row.get("vol") or row.get("volume") or 0),
                "turnover": float(row.get("amount") or 0),
            })
        except (TypeError, ValueError):
            continue
    return sorted(bars, key=lambda item: item["timestamp"])[-limit:]


def _yahoo_symbol(market: str, symbol: str) -> str:
    if market != "HK":
        return symbol.upper()
    digits = str(int(symbol)) if symbol.isdigit() else symbol
    return f"{digits.zfill(4)}.HK"


def _sina_us_daily_ohlcv(symbol: str, limit: int) -> list[dict[str, Any]]:
    response = requests.get(
        SINA_US_KLINE_URL,
        params={"symbol": symbol.upper(), "num": limit},
        headers={"User-Agent": astock.UA, "Referer": "https://finance.sina.com.cn/"},
        timeout=15,
    )
    response.raise_for_status()
    match = re.search(r"\((\[.*\])\)", response.text, re.DOTALL)
    if not match:
        return []
    rows = json.loads(match.group(1))
    bars: list[dict[str, Any]] = []
    for row in rows:
        try:
            timestamp = int(
                datetime.fromisoformat(str(row.get("d"))).replace(tzinfo=_NEW_YORK_TIMEZONE).timestamp() * 1000
            )
            bars.append({
                "timestamp": timestamp,
                "open": float(row.get("o")),
                "close": float(row.get("c")),
                "high": float(row.get("h")),
                "low": float(row.get("l")),
                "volume": float(row.get("v") or 0),
                "turnover": float(row.get("a") or 0),
            })
        except (AttributeError, TypeError, ValueError):
            continue
    return sorted(bars, key=lambda item: item["timestamp"])[-limit:]


def _sina_us_intraday_ohlcv(symbol: str, timeframe: str, limit: int) -> list[dict[str, Any]]:
    minutes = {"1m": 1, "5m": 5, "15m": 15, "30m": 30, "60m": 60}.get(timeframe)
    if minutes is None:
        return []
    response = requests.get(
        SINA_US_MINUTE_URL,
        params={"symbol": symbol.upper(), "type": minutes},
        headers={"User-Agent": astock.UA, "Referer": "https://finance.sina.com.cn/"},
        timeout=15,
    )
    response.raise_for_status()
    match = re.search(r"\((\[.*\])\)", response.text, re.DOTALL)
    if not match:
        return []
    rows = json.loads(match.group(1))
    bars: list[dict[str, Any]] = []
    for row in rows:
        try:
            timestamp = int(
                datetime.fromisoformat(str(row.get("d"))).replace(tzinfo=_NEW_YORK_TIMEZONE).timestamp() * 1000
            )
            bars.append({
                "timestamp": timestamp,
                "open": float(row.get("o")),
                "close": float(row.get("c")),
                "high": float(row.get("h")),
                "low": float(row.get("l")),
                "volume": float(row.get("v") or 0),
                "turnover": float(row.get("a") or 0),
            })
        except (AttributeError, TypeError, ValueError):
            continue
    return sorted(bars, key=lambda item: item["timestamp"])[-limit:]


def _aggregate_ohlcv(bars: list[dict[str, Any]], bucket_key) -> list[dict[str, Any]]:
    grouped: dict[Any, dict[str, Any]] = {}
    for bar in sorted(bars, key=lambda item: item["timestamp"]):
        key = bucket_key(bar)
        current = grouped.get(key)
        if current is None:
            grouped[key] = dict(bar)
            continue
        current["close"] = bar["close"]
        current["high"] = max(current["high"], bar["high"])
        current["low"] = min(current["low"], bar["low"])
        current["volume"] += bar.get("volume") or 0
        current["turnover"] += bar.get("turnover") or 0
    return list(grouped.values())


def _tencent_hk_ohlcv(symbol: str, timeframe: str, limit: int) -> list[dict[str, Any]]:
    period = {"1d": "day", "1w": "week", "1M": "month"}.get(timeframe)
    if period is None:
        return []
    prefixed = f"hk{symbol.zfill(5)}"
    response = requests.get(
        TENCENT_HK_KLINE_URL,
        params={"param": f"{prefixed},{period},,,{limit},"},
        headers={"User-Agent": astock.UA, "Referer": f"https://gu.qq.com/{prefixed}/gp"},
        timeout=12,
    )
    response.raise_for_status()
    payload = response.json()
    if int(payload.get("code", -1)) != 0:
        return []
    block = (payload.get("data") or {}).get(prefixed) or {}
    rows = block.get(period) or []
    return _parse_tencent_rows(rows)[-limit:]


def _tencent_hk_intraday_ohlcv(symbol: str, timeframe: str, limit: int) -> list[dict[str, Any]]:
    minutes = {"1m": 1, "5m": 5, "15m": 15, "30m": 30, "60m": 60}.get(timeframe)
    if minutes is None:
        return []
    prefixed = f"hk{symbol.zfill(5)}"
    response = requests.get(
        TENCENT_DAY_MINUTE_URL,
        params={"code": prefixed},
        headers={"User-Agent": astock.UA, "Referer": "https://gu.qq.com/"},
        timeout=12,
    )
    response.raise_for_status()
    payload = response.json()
    if int(payload.get("code", -1)) != 0:
        return []
    days = ((payload.get("data") or {}).get(prefixed) or {}).get("data") or []
    bars: list[dict[str, Any]] = []
    for day in days:
        date_value = str(day.get("date") or "")
        previous_volume = 0.0
        previous_turnover = 0.0
        for raw in day.get("data") or []:
            fields = str(raw).split()
            if len(fields) < 4:
                continue
            try:
                parsed = datetime.strptime(f"{date_value}{fields[0]}", "%Y%m%d%H%M").replace(tzinfo=_CHINA_TIMEZONE)
                price = float(fields[1])
                cumulative_volume = float(fields[2])
                cumulative_turnover = float(fields[3])
                bars.append({
                    "timestamp": int(parsed.timestamp() * 1000),
                    "open": price,
                    "close": price,
                    "high": price,
                    "low": price,
                    "volume": max(cumulative_volume - previous_volume, 0),
                    "turnover": max(cumulative_turnover - previous_turnover, 0),
                })
                previous_volume = cumulative_volume
                previous_turnover = cumulative_turnover
            except (TypeError, ValueError):
                continue
    if minutes > 1:
        bars = _aggregate_ohlcv(bars, lambda bar: bar["timestamp"] // (minutes * 60_000))
    return sorted(bars, key=lambda item: item["timestamp"])[-limit:]


def _yahoo_session() -> tuple[requests.Session, str]:
    cached = _yahoo_session_cache[0]
    if cached is not None:
        return cached
    session = requests.Session()
    session.headers.update({
        "User-Agent": astock.UA,
        "Accept": "application/json,text/plain,*/*",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": "https://finance.yahoo.com/",
    })
    try:
        session.get("https://fc.yahoo.com", timeout=10)
    except requests.RequestException:
        pass
    crumb = ""
    for url in YAHOO_CRUMB_URLS:
        try:
            response = session.get(url, timeout=10)
            value = response.text.strip()
            if response.ok and value and "<" not in value:
                crumb = value
                break
        except requests.RequestException:
            continue
    cached = (session, crumb)
    _yahoo_session_cache[0] = cached
    return cached


def _yahoo_ohlcv(market: str, symbol: str, timeframe: str, limit: int) -> list[dict[str, Any]]:
    interval = {"1m": "1m", "5m": "5m", "15m": "15m", "30m": "30m", "60m": "60m", "1d": "1d", "1w": "1wk", "1M": "1mo"}.get(timeframe)
    if interval is None:
        return []
    range_ = {"1m": "7d", "5m": "1mo", "15m": "1mo", "30m": "1mo", "60m": "3mo", "1d": "2y", "1w": "5y", "1M": "max"}[timeframe]
    response = None
    for _ in range(2):
        session, crumb = _yahoo_session()
        params = {
            "interval": interval,
            "range": range_,
            "includePrePost": "false",
            "events": "div,splits",
        }
        if crumb:
            params["crumb"] = crumb
        response = session.get(
            YAHOO_CHART_URL.format(symbol=_yahoo_symbol(market, symbol)),
            params=params,
            timeout=15,
        )
        if response.status_code not in {401, 403}:
            break
        _yahoo_session_cache[0] = None
    assert response is not None
    response.raise_for_status()
    result = (response.json().get("chart") or {}).get("result") or []
    if not result:
        return []
    chart = result[0]
    timestamps = chart.get("timestamp") or []
    quote = ((chart.get("indicators") or {}).get("quote") or [{}])[0]
    bars: list[dict[str, Any]] = []
    for index, seconds in enumerate(timestamps):
        values = {key: (quote.get(key) or []) for key in ("open", "close", "high", "low", "volume")}
        try:
            open_, close, high, low = (values[key][index] for key in ("open", "close", "high", "low"))
            if any(value is None for value in (open_, close, high, low)):
                continue
            bars.append({
                "timestamp": int(seconds) * 1000,
                "open": float(open_),
                "close": float(close),
                "high": float(high),
                "low": float(low),
                "volume": float(values["volume"][index] or 0),
                "turnover": 0,
            })
        except (IndexError, TypeError, ValueError):
            continue
    return bars[-limit:]


def _fund_nav_ohlcv(symbol: str, limit: int) -> list[dict[str, Any]]:
    bars: list[dict[str, Any]] = []
    for row in astock.fund_nav_history(symbol, limit=limit):
        nav = row.get("unitNav")
        if nav is None:
            continue
        try:
            timestamp = int(
                datetime.fromisoformat(str(row.get("date"))).replace(tzinfo=_CHINA_TIMEZONE).timestamp() * 1000
            )
        except (TypeError, ValueError):
            continue
        bars.append({
            "timestamp": timestamp,
            "open": float(nav),
            "close": float(nav),
            "high": float(nav),
            "low": float(nav),
            "volume": 0,
            "turnover": 0,
            "cumulativeNav": row.get("cumulativeNav"),
            "changePct": row.get("changePct"),
            "navEvent": row.get("navEvent") or "",
        })
    return sorted(bars, key=lambda item: item["timestamp"])[-limit:]


def get_ohlcv(
    symbol: str,
    *,
    market: str = "",
    timeframe: str = "1d",
    limit: int = 320,
    adjust: str = "qfq",
    asset_type: str = "stock",
) -> dict[str, Any]:
    """Load normalized OHLCV bars for the terminal chart."""
    market_id, code = _split_symbol(f"{market}:{symbol}" if market else symbol)
    limit = min(max(int(limit), 40), 800)
    effective_adjust = "none" if asset_type == "fund" else (adjust if market_id == "CN" else "none")
    if asset_type == "fund":
        bars = _fund_nav_ohlcv(code, limit) if market_id == "CN" and timeframe == "1d" else []
        source = "eastmoney-fund-nav"
    elif market_id == "CN":
        if timeframe in {"1m", "5m", "15m", "30m", "60m"}:
            bars = _tencent_intraday_ohlcv(code, timeframe, limit)
            source = "tencent-minute"
        else:
            try:
                bars = _tencent_ohlcv(code, timeframe, limit, adjust)
            except (requests.RequestException, ValueError):
                bars = []
            source = "tencent"
            if not bars:
                try:
                    bars = _eastmoney_ohlcv(code, timeframe, limit, adjust)
                except (requests.RequestException, ValueError):
                    bars = []
                source = "eastmoney"
            if not bars:
                try:
                    bars = _sina_cn_ohlcv(code, timeframe, limit)
                except (requests.RequestException, ValueError):
                    bars = []
                if bars:
                    effective_adjust = "none"
                    source = "sina-unadjusted"
            if not bars and adjust != "none":
                try:
                    bars = _eastmoney_ohlcv(code, timeframe, limit, "none")
                except (requests.RequestException, ValueError):
                    bars = []
                if bars:
                    effective_adjust = "none"
                    source = "eastmoney-unadjusted"
        if not bars:
            bars = _mootdx_ohlcv(code, timeframe, limit)
            source = "mootdx"
            effective_adjust = "none"
    else:
        bars = []
        source = ""
        try:
            if market_id == "US" and timeframe == "1d":
                bars = _sina_us_daily_ohlcv(code, limit)
                source = "sina"
            elif market_id == "US" and timeframe in {"1w", "1M"}:
                daily_limit = limit * (6 if timeframe == "1w" else 24) + 40
                daily_bars = _sina_us_daily_ohlcv(code, daily_limit)
                if timeframe == "1w":
                    bars = _aggregate_ohlcv(
                        daily_bars,
                        lambda bar: datetime.fromtimestamp(bar["timestamp"] / 1000, _NEW_YORK_TIMEZONE).isocalendar()[:2],
                    )[-limit:]
                else:
                    bars = _aggregate_ohlcv(
                        daily_bars,
                        lambda bar: (
                            datetime.fromtimestamp(bar["timestamp"] / 1000, _NEW_YORK_TIMEZONE).year,
                            datetime.fromtimestamp(bar["timestamp"] / 1000, _NEW_YORK_TIMEZONE).month,
                        ),
                    )[-limit:]
                source = "sina"
            elif market_id == "US":
                bars = _sina_us_intraday_ohlcv(code, timeframe, limit)
                source = "sina"
            elif market_id == "HK" and timeframe in {"1d", "1w", "1M"}:
                bars = _tencent_hk_ohlcv(code, timeframe, limit)
                source = "tencent"
            elif market_id == "HK":
                bars = _tencent_hk_intraday_ohlcv(code, timeframe, limit)
                source = "tencent-minute"
        except (requests.RequestException, ValueError):
            bars = []
        if not bars:
            bars = _yahoo_ohlcv(market_id, code, timeframe, limit)
            source = "yahoo"
    if not bars:
        raise RuntimeError(f"{market_id}:{code} {timeframe} 暂无可用行情")
    return {
        "symbol": code,
        "market": market_id,
        "timeframe": timeframe,
        "adjust": effective_adjust,
        "items": bars,
        "source": source,
        "asOf": _now_iso(),
        "hasMore": len(bars) >= limit,
    }
