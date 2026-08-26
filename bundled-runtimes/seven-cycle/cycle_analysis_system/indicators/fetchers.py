from __future__ import annotations

"""
Low-level fetchers for different data providers (Tushare Pro, AkShare, OpenBB).

All functions here return a pandas.Series indexed by Timestamp, with values in
their native units. Standardisation (YoY, MoM, returns, etc.) happens elsewhere.
"""

from dataclasses import dataclass
from functools import lru_cache
from typing import Optional
import os

import pandas as pd
import requests

from .indicator_registry import IndicatorSpec


@dataclass
class TSConfig:
    token: str
    timeout: int = 30


DEFAULT_OPENBB_BASE_URL = os.environ.get("OPENBB_BASE_URL", "http://127.0.0.1:6900")


def _empty_series() -> pd.Series:
    return pd.Series(dtype="float64")


def _to_month_end_index(values: pd.Series) -> pd.DatetimeIndex:
    dt = pd.to_datetime(values.astype(str), format="%Y%m", errors="coerce")
    dt = dt.dt.to_period("M").dt.to_timestamp("M")
    return pd.DatetimeIndex(dt)


def _to_date_index(values: pd.Series) -> pd.DatetimeIndex:
    s = values.astype(str).str.strip()
    if s.str.fullmatch(r"\d{8}", na=False).any():
        return pd.DatetimeIndex(pd.to_datetime(s, format="%Y%m%d", errors="coerce"))
    return pd.DatetimeIndex(pd.to_datetime(values, errors="coerce"))


def _to_quarter_start_month_end_index(values: pd.Series) -> pd.DatetimeIndex:
    """
    Convert Tushare 'YYYYQn' quarter strings to the month-end timestamp of the
    first month in that quarter (e.g., 2024Q3 -> 2024-07-31).
    """
    s = values.astype(str).str.strip()
    try:
        q = pd.PeriodIndex(s, freq="Q")
    except Exception:
        return pd.DatetimeIndex([])
    dt = q.asfreq("M", "start").to_timestamp("M")
    return pd.DatetimeIndex(dt)


def _ts_pro(cfg: TSConfig):
    import tushare as ts  # type: ignore

    token = cfg.token or os.environ.get("TUSHARE_TOKEN", "")
    if not token:
        raise RuntimeError("Tushare token missing; set TSConfig.token or TUSHARE_TOKEN.")
    ts.set_token(token)
    return ts.pro_api(timeout=cfg.timeout)


def _openbb_get(base_url: str, path: str, params: dict[str, object], timeout: int = 120) -> list[dict]:
    url = f"{base_url}{path}"
    r = requests.get(url, params=params, timeout=timeout)
    r.raise_for_status()
    return list(r.json().get("results", []) or [])


@lru_cache(maxsize=64)
def _ts_df_cached(token: str, timeout: int, api_name: str, params_items: tuple[tuple[str, str], ...]) -> pd.DataFrame:
    cfg = TSConfig(token=token, timeout=timeout)
    pro = _ts_pro(cfg)
    params = {k: v for k, v in params_items}
    df = getattr(pro, api_name)(**params)
    if df is None:
        return pd.DataFrame()
    return df.copy()


def _ts_df(cfg: TSConfig, api_name: str, **params) -> pd.DataFrame:
    params_items = tuple(sorted(((str(k), str(v)) for k, v in params.items())))
    token = cfg.token or os.environ.get("TUSHARE_TOKEN", "")
    return _ts_df_cached(token, cfg.timeout, api_name, params_items)


def fetch_from_tushare(ind: IndicatorSpec, cfg: TSConfig) -> pd.Series:
    if ind.backend == "cn_cpi":
        df = _ts_df(cfg, "cn_cpi", start_m="195101", end_m="202512")
        if df.empty:
            return _empty_series()
        idx = _to_month_end_index(df["month"])
        field = str(ind.params["field"])
        s = pd.to_numeric(df[field], errors="coerce")
        s.index = idx
        return s.sort_index()

    if ind.backend == "cn_ppi":
        df = _ts_df(cfg, "cn_ppi", start_m="196001", end_m="202512")
        if df.empty:
            return _empty_series()
        idx = _to_month_end_index(df["month"])
        field = str(ind.params["field"])
        s = pd.to_numeric(df[field], errors="coerce")
        s.index = idx
        return s.sort_index()

    if ind.backend == "cn_m":
        df = _ts_df(cfg, "cn_m", start_m="197801", end_m="202512")
        if df.empty:
            return _empty_series()
        idx = _to_month_end_index(df["month"])
        field = str(ind.params["field"])
        s = pd.to_numeric(df[field], errors="coerce")
        s.index = idx
        return s.sort_index()

    if ind.backend == "cn_pmi":
        df = _ts_df(cfg, "cn_pmi", start_m="200501", end_m="202512")
        if df.empty:
            return _empty_series()
        idx = _to_month_end_index(df["MONTH"])
        field = str(ind.params["field"])
        s = pd.to_numeric(df[field], errors="coerce")
        s.index = idx
        return s.sort_index()

    if ind.backend == "cn_gdp":
        df = _ts_df(cfg, "cn_gdp")
        if df.empty:
            return _empty_series()
        if "quarter" not in df.columns:
            return _empty_series()
        field = str(ind.params["field"])
        if field not in df.columns:
            return _empty_series()
        idx = _to_quarter_start_month_end_index(df["quarter"])
        s = pd.to_numeric(df[field], errors="coerce")
        s.index = idx
        return s.sort_index()

    if ind.backend == "shibor":
        df = _ts_df(cfg, "shibor", start_date="19900101")
        if df.empty:
            return _empty_series()
        idx = _to_date_index(df["date"])
        field = str(ind.params["field"])
        s = pd.to_numeric(df[field], errors="coerce")
        s.index = idx
        return s.sort_index()

    if ind.backend == "hibor":
        df = _ts_df(cfg, "hibor", start_date="19900101")
        if df.empty:
            return _empty_series()
        idx = _to_date_index(df["date"])
        field = str(ind.params["field"])
        s = pd.to_numeric(df[field], errors="coerce")
        s.index = idx
        return s.sort_index()

    if ind.backend == "index_daily":
        ts_code = str(ind.params["ts_code"])
        start_date = str(ind.params.get("start_date", "19900101"))
        field = str(ind.params.get("field", "close"))
        df = _ts_df(cfg, "index_daily", ts_code=ts_code, start_date=start_date)
        if df.empty:
            return _empty_series()
        idx = _to_date_index(df["trade_date"])
        s = pd.to_numeric(df[field], errors="coerce")
        s.index = idx
        return s.sort_index()

    if ind.backend == "index_dailybasic":
        ts_code = str(ind.params["ts_code"])
        start_date = str(ind.params.get("start_date", "20040101"))
        field = str(ind.params["field"])
        df = _ts_df(cfg, "index_dailybasic", ts_code=ts_code, start_date=start_date)
        if df.empty:
            return _empty_series()
        idx = _to_date_index(df["trade_date"])
        s = pd.to_numeric(df[field], errors="coerce")
        s.index = idx
        return s.sort_index()

    if ind.backend == "sw_daily":
        ts_code = str(ind.params["ts_code"])
        start_date = str(ind.params.get("start_date", "20120101"))
        end_date = str(ind.params.get("end_date", ""))
        field = str(ind.params.get("field", "close"))
        params = {"ts_code": ts_code, "start_date": start_date}
        if end_date:
            params["end_date"] = end_date
        df = _ts_df(cfg, "sw_daily", **params)
        if df.empty:
            return _empty_series()
        if "trade_date" not in df.columns or field not in df.columns:
            return _empty_series()
        idx = _to_date_index(df["trade_date"])
        s = pd.to_numeric(df[field], errors="coerce")
        s.index = idx
        return s.sort_index()

    if ind.backend == "ci_daily":
        ts_code = str(ind.params.get("ts_code", "")).strip()
        start_date = str(ind.params.get("start_date", "19900101"))
        end_date = str(ind.params.get("end_date", ""))
        field = str(ind.params.get("field", "close"))
        params = {"start_date": start_date}
        if ts_code:
            params["ts_code"] = ts_code
        if end_date:
            params["end_date"] = end_date
        df = _ts_df(cfg, "ci_daily", **params)
        if df.empty:
            return _empty_series()
        if "trade_date" not in df.columns or field not in df.columns:
            return _empty_series()
        idx = _to_date_index(df["trade_date"])
        s = pd.to_numeric(df[field], errors="coerce")
        s.index = idx
        return s.sort_index()

    if ind.backend == "fund_daily":
        ts_code = str(ind.params["ts_code"])
        start_date = str(ind.params.get("start_date", "19900101"))
        end_date = str(ind.params.get("end_date", ""))
        field = str(ind.params.get("field", "close"))
        params = {"ts_code": ts_code, "start_date": start_date}
        if end_date:
            params["end_date"] = end_date
        df = _ts_df(cfg, "fund_daily", **params)
        if df.empty:
            return _empty_series()
        if "trade_date" not in df.columns or field not in df.columns:
            return _empty_series()
        idx = _to_date_index(df["trade_date"])
        s = pd.to_numeric(df[field], errors="coerce")
        s.index = idx
        return s.sort_index()

    raise NotImplementedError(f"Tushare backend not implemented: {ind.backend}")


def fetch_from_openbb_price(ind: IndicatorSpec, base_url: str = DEFAULT_OPENBB_BASE_URL) -> pd.Series:
    symbol = str(ind.params["symbol"])
    start_date = str(ind.params.get("start_date", "1960-01-01"))
    end_date = str(ind.params.get("end_date", "2025-12-31"))
    price_field = str(ind.params.get("price_field", "adj_close"))
    try:
        data = _openbb_get(
            base_url,
            "/api/v1/index/price/historical",
            {"provider": "yfinance", "symbol": symbol, "start_date": start_date, "end_date": end_date},
            timeout=60,
        )
    except Exception:
        return _empty_series()
    if not data:
        return _empty_series()
    df = pd.DataFrame(data)
    if "date" not in df.columns:
        return _empty_series()
    df["date"] = pd.to_datetime(df["date"])
    col = price_field if price_field in df.columns else ("adj_close" if "adj_close" in df.columns else "close")
    s = pd.to_numeric(df[col], errors="coerce")
    s.index = pd.DatetimeIndex(df["date"])
    return s.sort_index()


@lru_cache(maxsize=32)
def _openbb_ff_portfolio_df(
    base_url: str,
    portfolio: str,
    frequency: str,
    start_date: str,
    end_date: str,
) -> pd.DataFrame:
    data = _openbb_get(
        base_url,
        "/api/v1/famafrench/us_portfolio_returns",
        {"portfolio": portfolio, "frequency": frequency, "start_date": start_date, "end_date": end_date},
        timeout=180,
    )
    if not data:
        return pd.DataFrame()
    df = pd.DataFrame(data)
    if not {"date", "portfolio", "value"}.issubset(df.columns):
        return pd.DataFrame()
    df["date"] = pd.to_datetime(df["date"]).dt.to_period("M").dt.to_timestamp("M")
    df["value"] = pd.to_numeric(df["value"], errors="coerce") / 100.0
    wide = df.pivot(index="date", columns="portfolio", values="value").sort_index()
    wide.columns = [str(c).strip() for c in wide.columns]
    return wide


def fetch_from_openbb_ff_portfolio_returns(ind: IndicatorSpec, base_url: str = DEFAULT_OPENBB_BASE_URL) -> pd.Series:
    portfolio = str(ind.params["portfolio"])
    portfolio_name = str(ind.params["portfolio_name"]).strip()
    frequency = str(ind.params.get("frequency", "monthly"))
    start_date = str(ind.params.get("start_date", "1960-01-01"))
    end_date = str(ind.params.get("end_date", "2024-12-31"))
    try:
        wide = _openbb_ff_portfolio_df(base_url, portfolio, frequency, start_date, end_date)
    except Exception:
        return _empty_series()
    if wide.empty or portfolio_name not in wide.columns:
        return _empty_series()
    return wide[portfolio_name].sort_index()


@lru_cache(maxsize=32)
def _openbb_ff_factors_df(
    base_url: str,
    region: str,
    factor: str,
    frequency: str,
    start_date: str,
    end_date: str,
) -> pd.DataFrame:
    data = _openbb_get(
        base_url,
        "/api/v1/famafrench/factors",
        {"region": region, "factor": factor, "frequency": frequency, "start_date": start_date, "end_date": end_date},
        timeout=180,
    )
    if not data:
        return pd.DataFrame()
    df = pd.DataFrame(data)
    if "date" not in df.columns:
        return pd.DataFrame()
    df["date"] = pd.to_datetime(df["date"]).dt.to_period("M").dt.to_timestamp("M")
    for c in df.columns:
        if c == "date":
            continue
        df[c] = pd.to_numeric(df[c], errors="coerce") / 100.0
    return df.set_index("date").sort_index()


def fetch_from_openbb_ff_factors(ind: IndicatorSpec, base_url: str = DEFAULT_OPENBB_BASE_URL) -> pd.Series:
    region = str(ind.params.get("region", "america"))
    factor = str(ind.params["factor"])
    field = str(ind.params["field"])
    frequency = str(ind.params.get("frequency", "monthly"))
    start_date = str(ind.params.get("start_date", "1960-01-01"))
    end_date = str(ind.params.get("end_date", "2024-12-31"))
    try:
        df = _openbb_ff_factors_df(base_url, region, factor, frequency, start_date, end_date)
    except Exception:
        return _empty_series()
    if df.empty or field not in df.columns:
        return _empty_series()
    return df[field].sort_index()


@lru_cache(maxsize=64)
def _openbb_oecd_series_cached(base_url: str, endpoint: str, params_items: tuple[tuple[str, str], ...]) -> pd.Series:
    params = {k: v for k, v in params_items}
    data = _openbb_get(base_url, f"/api/v1/economy/{endpoint}", params, timeout=120)
    if not data:
        return _empty_series()
    df = pd.DataFrame(data)
    if "date" not in df.columns or "value" not in df.columns:
        return _empty_series()
    dt = pd.to_datetime(df["date"]).dt.to_period("M").dt.to_timestamp("M")
    s = pd.to_numeric(df["value"], errors="coerce")
    s.index = pd.DatetimeIndex(dt)
    return s.sort_index()


def fetch_from_openbb_oecd_series(ind: IndicatorSpec, base_url: str = DEFAULT_OPENBB_BASE_URL) -> pd.Series:
    endpoint = str(ind.params["endpoint"])
    params = dict(ind.params.get("params", {}))
    params.setdefault("provider", "oecd")
    params.setdefault("start_date", "1960-01-01")
    params.setdefault("end_date", "2024-12-31")
    params_items = tuple(sorted(((str(k), str(v)) for k, v in params.items())))
    try:
        return _openbb_oecd_series_cached(base_url, endpoint, params_items)
    except Exception:
        return _empty_series()


@lru_cache(maxsize=128)
def _ak_df_cached(func_name: str) -> pd.DataFrame:
    import akshare as ak  # type: ignore

    f = getattr(ak, func_name, None)
    if not callable(f):
        return pd.DataFrame()
    try:
        df = f()
    except Exception:
        return pd.DataFrame()
    if df is None or not isinstance(df, pd.DataFrame):
        return pd.DataFrame()
    return df.copy()


def fetch_from_akshare(ind: IndicatorSpec) -> pd.Series:
    func_name = str(ind.params["func"])
    field = str(ind.params["field"])
    df = _ak_df_cached(func_name)
    if df.empty:
        return _empty_series()

    date_col = None
    for c in df.columns:
        if str(c) in {"date", "DATE", "month", "MONTH", "月份", "日期", "时间"}:
            date_col = str(c)
            break
    if date_col is None:
        date_col = str(df.columns[0])

    if field not in df.columns:
        return _empty_series()

    dt = pd.to_datetime(df[date_col], errors="coerce").dt.to_period("M").dt.to_timestamp("M")
    s = pd.to_numeric(df[field], errors="coerce")
    out = pd.Series(s.values, index=pd.DatetimeIndex(dt)).sort_index()
    out = out[~out.index.isna()]
    out = out.groupby(out.index).last().sort_index()
    return out


def fetch_raw_series(ind: IndicatorSpec, ts_cfg: Optional[TSConfig] = None) -> pd.Series:
    if ind.primary_source == "tushare":
        if ts_cfg is None:
            ts_cfg = TSConfig(token=os.environ.get("TUSHARE_TOKEN", ""))
        return fetch_from_tushare(ind, ts_cfg)

    if ind.primary_source == "openbb":
        if ind.backend == "index_price":
            return fetch_from_openbb_price(ind)
        if ind.backend == "ff_us_portfolio_returns":
            return fetch_from_openbb_ff_portfolio_returns(ind)
        if ind.backend == "ff_factors":
            return fetch_from_openbb_ff_factors(ind)
        if ind.backend == "oecd_series":
            return fetch_from_openbb_oecd_series(ind)
        raise NotImplementedError(f"OpenBB backend not implemented: {ind.backend}")

    if ind.primary_source == "akshare":
        return fetch_from_akshare(ind)

    raise NotImplementedError(f"Primary source not implemented: {ind.primary_source}")


def to_monthly_and_annual(s: pd.Series, value_type: str, base_freq: str) -> tuple[pd.Series, pd.Series]:
    """
    Convert a raw series to:
    - Monthly (month-end) series for 2000+ analysis
    - Annual (year-end) series for long-cycle analysis

    Notes:
    - Daily series are downsampled to month-end for level/price-like values.
    - Quarterly series are expanded to monthly via forward-fill, aligned to the
      first month of each quarter.
    """
    if s.empty:
        return s, s

    s = s.sort_index()

    base_freq = (base_freq or "M").upper()
    if base_freq == "Q":
        # Align to quarter's first-month month-end, then forward-fill to all months.
        q = s.index.to_period("Q")
        idx = q.asfreq("M", "start").to_timestamp("M")
        s = pd.Series(s.values, index=pd.DatetimeIndex(idx)).sort_index()
        s = s[~s.index.isna()].groupby(level=0).last().sort_index()
        m = s.resample("ME").ffill()
    elif value_type in {"price", "price_adj", "level", "index", "rate_level"}:
        m = s.resample("ME").last()
    else:
        m = s.copy()

    if value_type == "return":
        a = m.resample("YE-DEC").apply(
            lambda x: float((1.0 + x.dropna()).prod() - 1.0) if not x.dropna().empty else float("nan")
        )
    else:
        a = m.resample("YE-DEC").last()

    m.index = pd.DatetimeIndex(m.index).to_period("M").to_timestamp("M")
    a.index = pd.DatetimeIndex(a.index).to_period("Y-DEC").to_timestamp("Y-DEC")
    return m, a


def derive_yoy_mom(s: pd.Series, base_freq: str, value_type: str) -> dict[str, pd.Series]:
    s = s.sort_index()
    out: dict[str, pd.Series] = {}

    if base_freq == "M":
        if value_type == "rate_yoy":
            out["yoy"] = s
        elif value_type == "rate_mom":
            out["mom"] = s
        elif value_type == "rate_level":
            out["mom"] = s.diff()
            out["yoy"] = s.diff(12)
        elif value_type == "return":
            out["mom"] = s
            out["yoy"] = s.rolling(12).apply(
                lambda x: float((1.0 + x.dropna()).prod() - 1.0) if not x.dropna().empty else float("nan"),
                raw=False,
            )
        elif value_type in {"price", "price_adj", "level", "index"}:
            out["mom"] = s.pct_change()
            out["yoy"] = s.pct_change(12)
    elif base_freq == "A":
        if value_type == "rate_level":
            out["yoy"] = s.diff()
        elif value_type.startswith("rate"):
            out["yoy"] = s
        elif value_type == "return":
            out = {}
        else:
            out["yoy"] = s.pct_change()

    return out
