from __future__ import annotations

import importlib
import importlib.util
import json
import threading
from datetime import datetime, timedelta
from typing import Any

import requests
from sqlalchemy.orm import Session

from ..config import settings
from ..models import SyncState


# These providers pull in pandas/numpy and materially increase API startup RSS.
# Detect availability without importing them; load only when a fallback is used.
HAS_AKSHARE = importlib.util.find_spec("akshare") is not None
HAS_TUSHARE = importlib.util.find_spec("tushare") is not None
ak: Any | None = None
ts: Any | None = None
_OPTIONAL_IMPORT_LOCK = threading.Lock()


def _load_akshare() -> Any | None:
    global ak, HAS_AKSHARE
    if ak is not None:
        return ak
    if not HAS_AKSHARE:
        return None
    with _OPTIONAL_IMPORT_LOCK:
        if ak is not None:
            return ak
        try:
            ak = importlib.import_module("akshare")
        except Exception:
            HAS_AKSHARE = False
            ak = None
    return ak


def _load_tushare() -> Any | None:
    global ts, HAS_TUSHARE
    if ts is not None:
        return ts
    if not HAS_TUSHARE:
        return None
    with _OPTIONAL_IMPORT_LOCK:
        if ts is not None:
            return ts
        try:
            ts = importlib.import_module("tushare")
        except Exception:
            HAS_TUSHARE = False
            ts = None
    return ts


MARKET_DATA_CONFIG_KEY = "market_data_config"
MASKED_SECRET_VALUE = "*** 已配置 ***"
DEFAULT_BENCHMARK_CODE = "sh000300"
PROVIDER_PREFERENCES = {
    "a_stock_first",
    "tushare_first",
    "akshare_first",
    "a_stock_only",
    "tushare_only",
    "akshare_only",
}
STOCK_PREFIX_TO_EXCHANGE = {
    "600": "SH",
    "601": "SH",
    "603": "SH",
    "605": "SH",
    "688": "SH",
    "689": "SH",
    "900": "SH",
    "000": "SZ",
    "001": "SZ",
    "002": "SZ",
    "003": "SZ",
    "200": "SZ",
    "300": "SZ",
    "301": "SZ",
    "302": "SZ",
    "430": "BJ",
    "830": "BJ",
    "831": "BJ",
    "832": "BJ",
    "833": "BJ",
    "835": "BJ",
    "836": "BJ",
    "837": "BJ",
    "838": "BJ",
    "839": "BJ",
    "870": "BJ",
    "871": "BJ",
    "872": "BJ",
    "873": "BJ",
    "874": "BJ",
    "875": "BJ",
    "876": "BJ",
    "877": "BJ",
    "878": "BJ",
    "879": "BJ",
    "920": "BJ",
}
ETF_PREFIX_TO_EXCHANGE = {
    "159": "SZ",
    "160": "SZ",
    "161": "SZ",
    "162": "SZ",
    "163": "SZ",
    "164": "SZ",
    "165": "SZ",
    "166": "SZ",
    "167": "SZ",
    "168": "SZ",
    "500": "SH",
    "501": "SH",
    "502": "SH",
    "503": "SH",
    "505": "SH",
    "506": "SH",
    "508": "SH",
    "510": "SH",
    "511": "SH",
    "512": "SH",
    "513": "SH",
    "515": "SH",
    "516": "SH",
    "517": "SH",
    "518": "SH",
    "519": "SH",
    "520": "SH",
    "560": "SH",
    "561": "SH",
    "562": "SH",
    "563": "SH",
    "588": "SH",
}
INDEX_PREFIX_TO_EXCHANGE = {
    "000": "SH",
    "880": "SH",
    "881": "SH",
    "882": "SH",
    "883": "SH",
    "884": "SH",
    "885": "SH",
    "886": "SH",
    "887": "SH",
    "888": "SH",
    "399": "SZ",
}

_TUSHARE_LOCK = threading.Lock()
_TUSHARE_CLIENT: Any | None = None
_TUSHARE_TOKEN_CACHE = ""
_LOOKUP_CACHE_LOCK = threading.Lock()
_ASSET_LOOKUP_CACHE: dict[str, list[dict[str, Any]]] = {}

CURATED_ASSET_ALIASES: list[dict[str, Any]] = [
    {"asset_type": "index", "asset_code": "sh000300", "asset_name": "沪深300", "aliases": ["沪深300", "hs300"]},
    {"asset_type": "index", "asset_code": "sh000001", "asset_name": "上证指数", "aliases": ["上证指数", "上证综指", "大盘"]},
    {"asset_type": "index", "asset_code": "sz399006", "asset_name": "创业板指", "aliases": ["创业板", "创业板指"]},
    {"asset_type": "index", "asset_code": "sh000905", "asset_name": "中证500", "aliases": ["中证500"]},
    {"asset_type": "index", "asset_code": "sh000688", "asset_name": "科创50", "aliases": ["科创50"]},
    {"asset_type": "index", "asset_code": "sh000852", "asset_name": "中证1000", "aliases": ["中证1000"]},
    {"asset_type": "stock", "asset_code": "601899", "asset_name": "紫金矿业", "aliases": ["紫金矿业"]},
    {"asset_type": "stock", "asset_code": "600519", "asset_name": "贵州茅台", "aliases": ["贵州茅台", "茅台"]},
    {"asset_type": "stock", "asset_code": "000858", "asset_name": "五粮液", "aliases": ["五粮液"]},
    {"asset_type": "stock", "asset_code": "600036", "asset_name": "招商银行", "aliases": ["招商银行", "招行"]},
    {"asset_type": "stock", "asset_code": "601318", "asset_name": "中国平安", "aliases": ["中国平安", "平安"]},
    {"asset_type": "stock", "asset_code": "300750", "asset_name": "宁德时代", "aliases": ["宁德时代"]},
    {"asset_type": "stock", "asset_code": "600309", "asset_name": "万华化学", "aliases": ["万华化学"]},
    {"asset_type": "stock", "asset_code": "600941", "asset_name": "中国移动", "aliases": ["中国移动"]},
    {"asset_type": "stock", "asset_code": "601919", "asset_name": "中远海控", "aliases": ["中远海控"]},
    {"asset_type": "stock", "asset_code": "000333", "asset_name": "美的集团", "aliases": ["美的集团"]},
    {"asset_type": "etf", "asset_code": "512480", "asset_name": "半导体ETF", "aliases": ["半导体ETF", "芯片ETF"]},
    {"asset_type": "etf", "asset_code": "515980", "asset_name": "人工智能ETF", "aliases": ["人工智能ETF", "AIETF"]},
    {"asset_type": "etf", "asset_code": "512690", "asset_name": "酒ETF", "aliases": ["酒ETF", "白酒ETF"]},
    {"asset_type": "fund", "asset_code": "161725", "asset_name": "招商中证白酒指数", "aliases": ["招商白酒", "白酒基金"]},
]


def _default_market_data_config() -> dict[str, Any]:
    token = str(getattr(settings, "TUSHARE_TOKEN", "") or "").strip()
    return {
        "provider_preference": "a_stock_first",
        "enable_a_stock_direct": True,
        "enable_tushare": bool(token),
        "enable_tushare_lookup": False,
        "enable_akshare": True,
        "tushare_token": token,
        "default_benchmark": DEFAULT_BENCHMARK_CODE,
    }


def _read_sync_state_json(db: Session, key: str) -> dict[str, Any]:
    row = db.get(SyncState, key)
    if not row or not row.value:
        return {}
    try:
        payload = json.loads(row.value)
        return payload if isinstance(payload, dict) else {}
    except Exception:
        return {}


def _write_sync_state_json(db: Session, key: str, payload: dict[str, Any]) -> None:
    row = db.get(SyncState, key)
    if not row:
        row = SyncState(key=key, value=json.dumps(payload, ensure_ascii=False))
    else:
        row.value = json.dumps(payload, ensure_ascii=False)
    db.add(row)


def normalize_market_data_config(payload: dict[str, Any] | None, *, existing: dict[str, Any] | None = None) -> dict[str, Any]:
    merged = {**_default_market_data_config(), **(existing or {}), **(payload or {})}
    preference = str(merged.get("provider_preference") or "").strip().lower()
    if preference not in PROVIDER_PREFERENCES:
        preference = _default_market_data_config()["provider_preference"]

    token = str(merged.get("tushare_token") or "").strip()
    enable_a_stock_direct = bool(merged.get("enable_a_stock_direct", True))
    enable_tushare = bool(merged.get("enable_tushare", bool(token)))
    enable_tushare_lookup = bool(merged.get("enable_tushare_lookup", False))
    enable_akshare = bool(merged.get("enable_akshare", True))
    benchmark = str(merged.get("default_benchmark") or DEFAULT_BENCHMARK_CODE).strip() or DEFAULT_BENCHMARK_CODE
    return {
        "provider_preference": preference,
        "enable_a_stock_direct": enable_a_stock_direct,
        "enable_tushare": enable_tushare,
        "enable_tushare_lookup": enable_tushare_lookup,
        "enable_akshare": enable_akshare,
        "tushare_token": token,
        "default_benchmark": benchmark,
    }


def load_market_data_config(db: Session | None = None) -> dict[str, Any]:
    stored = _read_sync_state_json(db, MARKET_DATA_CONFIG_KEY) if db is not None else {}
    return normalize_market_data_config(stored)


def sanitize_market_data_config_for_ui(config: dict[str, Any] | None) -> dict[str, Any]:
    cfg = normalize_market_data_config(config or {})
    token = str(cfg.get("tushare_token") or "").strip()
    return {
        "provider_preference": cfg["provider_preference"],
        "enable_a_stock_direct": bool(cfg["enable_a_stock_direct"]),
        "enable_tushare": bool(cfg["enable_tushare"]),
        "enable_tushare_lookup": bool(cfg["enable_tushare_lookup"]),
        "enable_akshare": bool(cfg["enable_akshare"]),
        "default_benchmark": cfg["default_benchmark"],
        "has_tushare_token": bool(token),
        "tushare_token": "",
        "providers": {
            "a_stock_direct_installed": True,
            "akshare_installed": HAS_AKSHARE,
            "tushare_installed": HAS_TUSHARE,
        },
    }


def save_market_data_config(db: Session, payload: dict[str, Any]) -> dict[str, Any]:
    current = load_market_data_config(db)
    incoming = dict(payload or {})
    token_present = "tushare_token" in incoming
    raw_token = str(incoming.get("tushare_token") or "").strip() if token_present else None
    if token_present and raw_token == MASKED_SECRET_VALUE:
        incoming["tushare_token"] = current.get("tushare_token", "")
    normalized = normalize_market_data_config(incoming, existing=current)
    _write_sync_state_json(db, MARKET_DATA_CONFIG_KEY, normalized)
    db.commit()
    return normalize_market_data_config(normalized)


def market_data_provider_order(config: dict[str, Any] | None = None) -> list[str]:
    cfg = normalize_market_data_config(config or {})
    preference = cfg["provider_preference"]
    if preference == "a_stock_only":
        order = ["a_stock_direct"]
    elif preference == "tushare_only":
        order = ["tushare"]
    elif preference == "akshare_only":
        order = ["akshare"]
    elif preference == "a_stock_first":
        order = ["a_stock_direct", "tushare", "akshare"]
    elif preference == "akshare_first":
        order = ["akshare", "tushare", "a_stock_direct"]
    else:
        order = ["tushare", "akshare", "a_stock_direct"]

    out: list[str] = []
    for provider in order:
        if provider == "a_stock_direct":
            if cfg.get("enable_a_stock_direct", True):
                out.append(provider)
        elif provider == "tushare":
            if cfg.get("enable_tushare") and str(cfg.get("tushare_token") or "").strip() and HAS_TUSHARE:
                out.append(provider)
        elif provider == "akshare":
            if cfg.get("enable_akshare") and HAS_AKSHARE:
                out.append(provider)
    return out


def _detect_exchange_from_prefix(code: str, mapping: dict[str, str], default: str | None = None) -> str | None:
    short = str(code or "").strip()
    for prefix, exchange in mapping.items():
        if short.startswith(prefix):
            return exchange
    return default


def _guess_stock_exchange(code: str) -> str | None:
    return _detect_exchange_from_prefix(code, STOCK_PREFIX_TO_EXCHANGE)


def _guess_etf_exchange(code: str) -> str | None:
    return _detect_exchange_from_prefix(code, ETF_PREFIX_TO_EXCHANGE, default="SZ" if str(code).startswith("1") else "SH")


def _guess_index_exchange(code: str) -> str | None:
    return _detect_exchange_from_prefix(code, INDEX_PREFIX_TO_EXCHANGE, default="SH")


def _extract_digits(value: str | None) -> str:
    return "".join(ch for ch in str(value or "") if ch.isdigit())


def normalize_asset_identity(asset_type: str, asset_code: str | None) -> dict[str, Any]:
    raw_type = str(asset_type or "").strip().lower() or "stock"
    raw_code = str(asset_code or "").strip()
    lower_code = raw_code.lower()
    digits = _extract_digits(raw_code)

    if lower_code.startswith(("sh", "sz", "bj")) and len(lower_code) >= 8:
        exchange = lower_code[:2].upper()
        digits = lower_code[2:8]
    elif "." in raw_code:
        left, right = raw_code.split(".", 1)
        digits = _extract_digits(left)
        exchange = right.upper()
    else:
        exchange = None

    asset_kind = raw_type
    if asset_kind == "industry":
        asset_kind = "etf"
    if asset_kind not in {"stock", "index", "etf", "fund"}:
        asset_kind = "stock"

    if asset_kind == "index":
        exchange = exchange or _guess_index_exchange(digits)
    elif asset_kind in {"etf", "fund"}:
        exchange = exchange or _guess_etf_exchange(digits)
    else:
        exchange = exchange or _guess_stock_exchange(digits)

    ts_code = f"{digits}.{exchange}" if digits and exchange else None
    prefixed = f"{exchange.lower()}{digits}" if digits and exchange in {"SH", "SZ"} else digits
    return {
        "asset_type": asset_kind,
        "raw_code": raw_code,
        "digits": digits,
        "exchange": exchange,
        "ts_code": ts_code,
        "prefixed_code": prefixed,
        "is_fund_like": asset_kind in {"etf", "fund"},
    }


def _records_from_df(df: Any) -> list[dict[str, Any]]:
    if df is None:
        return []
    try:
        cols = {str(c).lower(): c for c in df.columns}
        date_col = None
        close_col = None
        for key in ("date", "日期", "trade_date", "净值日期"):
            if key in cols:
                date_col = cols[key]
                break
        for key in ("close", "收盘", "收盘价", "close_price", "单位净值", "累计净值"):
            if key in cols:
                close_col = cols[key]
                break
        if not date_col or not close_col:
            return []

        out: list[dict[str, Any]] = []
        for _, row in df.iterrows():
            raw_date = row[date_col]
            if hasattr(raw_date, "strftime"):
                dt = raw_date.strftime("%Y-%m-%d")
            else:
                raw_text = str(raw_date).strip()
                if len(raw_text) == 8 and raw_text.isdigit():
                    dt = f"{raw_text[0:4]}-{raw_text[4:6]}-{raw_text[6:8]}"
                else:
                    dt = raw_text[:10]
            try:
                close = float(row[close_col])
            except Exception:
                continue
            out.append({"date": dt, "close": close})
        out.sort(key=lambda item: str(item.get("date") or ""))
        return out
    except Exception:
        return []


def _clip_records(records: list[dict[str, Any]], start_date: datetime, end_date: datetime) -> list[dict[str, Any]]:
    start_s = start_date.strftime("%Y-%m-%d")
    end_s = end_date.strftime("%Y-%m-%d")
    return [item for item in records if start_s <= str(item.get("date") or "") <= end_s]


def _get_tushare_client(token: str) -> Any | None:
    global _TUSHARE_CLIENT, _TUSHARE_TOKEN_CACHE
    if not token or not HAS_TUSHARE:
        return None
    ts_module = _load_tushare()
    if ts_module is None:
        return None
    with _TUSHARE_LOCK:
        if _TUSHARE_CLIENT is not None and _TUSHARE_TOKEN_CACHE == token:
            return _TUSHARE_CLIENT
        try:
            ts_module.set_token(token)
            _TUSHARE_CLIENT = ts_module.pro_api(token, timeout=8)
            _TUSHARE_TOKEN_CACHE = token
        except Exception:
            _TUSHARE_CLIENT = None
            _TUSHARE_TOKEN_CACHE = ""
        return _TUSHARE_CLIENT


def _lookup_cache_key(config: dict[str, Any]) -> str:
    token = str(config.get("tushare_token") or "").strip()
    return f"{int(bool(token and config.get('enable_tushare_lookup')))}:{token[:12]}"


def _build_lookup_entry(asset_type: str, asset_code: str, asset_name: str, aliases: list[str] | None = None) -> dict[str, Any]:
    alias_list = [str(item).strip() for item in (aliases or []) if str(item).strip()]
    if asset_name and asset_name not in alias_list:
        alias_list.insert(0, asset_name)
    cleaned = []
    seen = set()
    for alias in alias_list:
        if len(alias) < 2 or alias in seen:
            continue
        seen.add(alias)
        cleaned.append(alias)
    return {
        "asset_type": asset_type,
        "asset_code": asset_code,
        "asset_name": asset_name,
        "aliases": cleaned,
    }


def _fetch_tushare_lookup_entries(config: dict[str, Any]) -> list[dict[str, Any]]:
    token = str(config.get("tushare_token") or "").strip()
    client = _get_tushare_client(token)
    if client is None:
        return []

    entries: list[dict[str, Any]] = []
    try:
        df = client.stock_basic(exchange="", list_status="L", fields="ts_code,symbol,name")
        if df is not None and len(df) > 0:
            for _, row in df.iterrows():
                ts_code = str(row.get("ts_code") or "").strip()
                symbol = str(row.get("symbol") or "").strip()
                name = str(row.get("name") or "").strip()
                if not ts_code or not name or len(name) < 3:
                    continue
                entries.append(_build_lookup_entry("stock", symbol or ts_code.split(".")[0], name, [name]))
    except Exception:
        pass

    for market, asset_type in (("E", "etf"), ("O", "fund")):
        try:
            df = client.fund_basic(market=market)
            if df is None or len(df) == 0:
                continue
            columns = {str(c).lower(): c for c in df.columns}
            code_col = columns.get("ts_code") or columns.get("symbol")
            name_col = columns.get("name")
            if not code_col or not name_col:
                continue
            for _, row in df.iterrows():
                ts_code = str(row[code_col] or "").strip()
                name = str(row[name_col] or "").strip()
                if not ts_code or not name or len(name) < 3:
                    continue
                asset_code = ts_code.split(".")[0]
                aliases = [name]
                if asset_type == "etf" and "ETF" not in name.upper():
                    aliases.append(f"{name}ETF")
                entries.append(_build_lookup_entry(asset_type, asset_code, name, aliases))
        except Exception:
            continue
    return entries


def load_asset_lookup_entries(config: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    cfg = normalize_market_data_config(config or {})
    key = _lookup_cache_key(cfg)
    with _LOOKUP_CACHE_LOCK:
        cached = _ASSET_LOOKUP_CACHE.get(key)
        if cached is not None:
            return cached

    entries = [dict(item) for item in CURATED_ASSET_ALIASES]
    if cfg.get("enable_tushare_lookup") and str(cfg.get("tushare_token") or "").strip() and HAS_TUSHARE:
        dynamic = _fetch_tushare_lookup_entries(cfg)
        if dynamic:
            dedup: dict[tuple[str, str], dict[str, Any]] = {}
            for item in entries + dynamic:
                key = (str(item.get("asset_type") or ""), str(item.get("asset_code") or ""))
                existing = dedup.get(key)
                if not existing:
                    dedup[key] = {
                        **item,
                        "aliases": list(item.get("aliases") or []),
                    }
                    continue
                aliases = list(existing.get("aliases") or [])
                aliases.extend(item.get("aliases") or [])
                dedup[key] = {
                    **existing,
                    **item,
                    "asset_name": str(existing.get("asset_name") or item.get("asset_name") or ""),
                    "aliases": list(dict.fromkeys([str(alias).strip() for alias in aliases if str(alias).strip()])),
                }
            entries = list(dedup.values())

    with _LOOKUP_CACHE_LOCK:
        _ASSET_LOOKUP_CACHE[key] = entries
    return entries


def search_asset_in_text(text: str, config: dict[str, Any] | None = None) -> dict[str, Any] | None:
    raw_text = str(text or "").strip()
    if len(raw_text) < 2:
        return None
    entries = load_asset_lookup_entries(config)
    candidates: list[tuple[int, int, dict[str, Any]]] = []
    for item in entries:
        asset_type = str(item.get("asset_type") or "")
        for alias in item.get("aliases") or []:
            alias_text = str(alias or "").strip()
            if len(alias_text) < 2:
                continue
            if alias_text not in raw_text:
                continue
            score = len(alias_text) * 10
            if asset_type == "stock":
                score += 14
            elif asset_type in {"etf", "fund"}:
                score += 12
            elif asset_type == "index":
                score += 2
            if "ETF" in alias_text.upper() or "基金" in alias_text:
                score += 3
            candidates.append((score, len(alias_text), item))
    if not candidates:
        return None
    candidates.sort(key=lambda row: (row[0], row[1]), reverse=True)
    chosen = candidates[0][2]
    return {
        "asset_type": str(chosen.get("asset_type") or ""),
        "asset_code": str(chosen.get("asset_code") or ""),
        "asset_name": str(chosen.get("asset_name") or ""),
    }


def _fetch_tushare_series(normalized: dict[str, Any], start_date: datetime, end_date: datetime, config: dict[str, Any]) -> list[dict[str, Any]]:
    token = str(config.get("tushare_token") or "").strip()
    client = _get_tushare_client(token)
    if client is None:
        return []
    ts_code = normalized.get("ts_code")
    if not ts_code:
        return []
    start_s = start_date.strftime("%Y%m%d")
    end_s = end_date.strftime("%Y%m%d")
    asset_type = normalized.get("asset_type")

    try_specs: list[tuple[str, dict[str, Any]]] = []
    if asset_type == "index":
        try_specs = [
            ("index_daily", {"ts_code": ts_code, "start_date": start_s, "end_date": end_s, "fields": "trade_date,close"}),
        ]
    elif asset_type in {"etf", "fund"}:
        try_specs = [
            ("fund_daily", {"ts_code": ts_code, "start_date": start_s, "end_date": end_s, "fields": "trade_date,close"}),
        ]
    else:
        try_specs = [
            ("daily", {"ts_code": ts_code, "start_date": start_s, "end_date": end_s, "fields": "trade_date,close"}),
            ("fund_daily", {"ts_code": ts_code, "start_date": start_s, "end_date": end_s, "fields": "trade_date,close"}),
        ]

    for func_name, kwargs in try_specs:
        try:
            fn = getattr(client, func_name, None)
            if not fn:
                continue
            df = fn(**kwargs)
            records = _records_from_df(df)
            if records:
                return _clip_records(records, start_date, end_date)
        except Exception:
            continue
    return []


def _fetch_akshare_open_fund(symbol: str, start_date: datetime, end_date: datetime) -> list[dict[str, Any]]:
    if not HAS_AKSHARE:
        return []
    ak_module = _load_akshare()
    if ak_module is None:
        return []
    fn = getattr(ak_module, "fund_open_fund_info_em", None)
    if not fn:
        return []
    for indicator in ("单位净值走势", "累计净值走势"):
        try:
            df = fn(symbol=symbol, indicator=indicator)
            records = _records_from_df(df)
            if records:
                return _clip_records(records, start_date, end_date)
        except Exception:
            continue
    return []


def _fetch_akshare_series(normalized: dict[str, Any], start_date: datetime, end_date: datetime) -> list[dict[str, Any]]:
    if not HAS_AKSHARE:
        return []
    ak_module = _load_akshare()
    if ak_module is None:
        return []

    digits = str(normalized.get("digits") or "").strip()
    prefixed = str(normalized.get("prefixed_code") or "").strip()
    asset_type = str(normalized.get("asset_type") or "stock")
    start_s = start_date.strftime("%Y%m%d")
    end_s = end_date.strftime("%Y%m%d")

    try_specs: list[tuple[str, dict[str, Any]]] = []
    if asset_type == "index":
        try_specs = [
            ("index_zh_a_hist", {"symbol": prefixed or digits, "period": "daily", "start_date": start_s, "end_date": end_s}),
            ("stock_zh_index_daily_em", {"symbol": prefixed or digits}),
            ("stock_zh_index_daily", {"symbol": prefixed or digits}),
        ]
    else:
        try_specs = [
            ("stock_zh_a_hist", {"symbol": digits, "period": "daily", "start_date": start_s, "end_date": end_s, "adjust": "qfq"}),
            ("stock_zh_a_hist", {"symbol": digits, "period": "daily", "start_date": start_s, "end_date": end_s, "adjust": ""}),
            ("fund_etf_hist_em", {"symbol": digits, "period": "daily", "start_date": start_s, "end_date": end_s, "adjust": "qfq"}),
            ("fund_etf_hist_em", {"symbol": digits, "period": "daily", "start_date": start_s, "end_date": end_s, "adjust": ""}),
        ]

    for func_name, kwargs in try_specs:
        try:
            fn = getattr(ak_module, func_name, None)
            if not fn:
                continue
            df = fn(**kwargs)
            records = _records_from_df(df)
            if records:
                return _clip_records(records, start_date, end_date)
        except Exception:
            continue

    if asset_type in {"fund", "etf"}:
        return _fetch_akshare_open_fund(digits, start_date, end_date)
    return []


def _tencent_symbol(normalized: dict[str, Any]) -> str:
    digits = str(normalized.get("digits") or "").strip()
    exchange = str(normalized.get("exchange") or "").strip().upper()
    if not digits or exchange not in {"SH", "SZ", "BJ"}:
        return ""
    return f"{exchange.lower()}{digits}"


def _records_from_tencent_kline_payload(payload: dict[str, Any], symbol: str) -> list[dict[str, Any]]:
    data = payload.get("data") or {}
    block = data.get(symbol) or data.get(symbol.lower()) or data.get(symbol.upper()) or {}
    if not isinstance(block, dict):
        return []
    rows = block.get("qfqday") or block.get("day") or block.get("hfqday") or []
    out: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, (list, tuple)) or len(row) < 3:
            continue
        dt = str(row[0] or "").strip()[:10]
        try:
            close = float(row[2])
        except Exception:
            continue
        if dt:
            out.append({"date": dt, "close": close})
    out.sort(key=lambda item: str(item.get("date") or ""))
    return out


def _fetch_a_stock_direct_series(normalized: dict[str, Any], start_date: datetime, end_date: datetime) -> list[dict[str, Any]]:
    """Fetch daily A-share/index/ETF K-line data from Tencent's public endpoint.

    This embeds the lightweight no-key route recommended by the a-stock-data skill.
    It is intentionally narrow: contact scoring only needs date/close series.
    """
    symbol = _tencent_symbol(normalized)
    if not symbol:
        return []
    asset_type = str(normalized.get("asset_type") or "stock")
    natural_days = max(10, (end_date.date() - start_date.date()).days + 45)
    limit = min(max(natural_days, 90), 1600)
    endpoint = "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get"
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Referer": "https://gu.qq.com/",
    }
    adjust_candidates = [""] if asset_type == "index" else ["qfq", ""]
    for adjust in adjust_candidates:
        try:
            params = {"param": f"{symbol},day,,,{limit},{adjust}"}
            resp = requests.get(endpoint, params=params, headers=headers, timeout=10)
            if resp.status_code != 200:
                continue
            data = resp.json()
            if int(data.get("code", -1)) != 0:
                continue
            records = _records_from_tencent_kline_payload(data, symbol)
            clipped = _clip_records(records, start_date - timedelta(days=3), end_date + timedelta(days=3))
            if clipped:
                return clipped
        except Exception:
            continue
    return []


def fetch_market_series(
    asset_type: str,
    asset_code: str | None,
    start_date: datetime,
    end_date: datetime,
    *,
    config: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    if not asset_code:
        return []
    cfg = normalize_market_data_config(config or {})
    normalized = normalize_asset_identity(asset_type, asset_code)
    if not normalized.get("digits"):
        return []

    for provider in market_data_provider_order(cfg):
        if provider == "a_stock_direct":
            records = _fetch_a_stock_direct_series(normalized, start_date, end_date)
        elif provider == "tushare":
            records = _fetch_tushare_series(normalized, start_date, end_date, cfg)
        else:
            records = _fetch_akshare_series(normalized, start_date, end_date)
        if records:
            return records
    return []


def market_provider_health(config: dict[str, Any] | None = None) -> dict[str, Any]:
    cfg = normalize_market_data_config(config or {})
    token = str(cfg.get("tushare_token") or "").strip()
    return {
        "provider_preference": cfg["provider_preference"],
        "providers": {
            "a_stock_direct": {
                "enabled": bool(cfg.get("enable_a_stock_direct", True)),
                "installed": True,
                "source": "A Stock Data / Tencent public K-line",
            },
            "akshare": {
                "enabled": bool(cfg.get("enable_akshare")),
                "installed": HAS_AKSHARE,
            },
            "tushare": {
                "enabled": bool(cfg.get("enable_tushare")),
                "installed": HAS_TUSHARE,
                "has_token": bool(token),
                "lookup_enabled": bool(cfg.get("enable_tushare_lookup")),
            },
        },
        "effective_order": market_data_provider_order(cfg),
    }
