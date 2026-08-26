from __future__ import annotations

"""
Tushare-based data loader for Huatai-style cycle analysis.

Design goals
------------
- Use Tushare as the *single* source of truth for China-related assets/macros
- Provide clean monthly panels suitable for both the Huatai replication
  and the existing deep-cycle framework
- Keep the interface simple and explicit; avoid hidden global state
"""

import os
from dataclasses import dataclass
from typing import List, Optional, Dict

import pandas as pd


@dataclass
class TSConfig:
    """Lightweight Tushare configuration."""

    token: str
    timeout: int = 30


def _init_ts_pro(cfg: TSConfig):
    """Initialise and return a Tushare pro client."""
    # Import inside function so that other parts of the project do not require tushare
    import tushare as ts  # type: ignore

    # Prefer explicit token from cfg, fall back to env if empty
    token = cfg.token or os.environ.get("TUSHARE_TOKEN", "")
    if not token:
        raise RuntimeError("Tushare token is empty – set TSConfig.token or TUSHARE_TOKEN.")

    ts.set_token(token)
    pro = ts.pro_api(timeout=cfg.timeout)
    return pro


def get_index_daily(
    cfg: TSConfig,
    ts_code: str,
    start_date: str = "19900101",
    end_date: Optional[str] = None,
) -> pd.DataFrame:
    """
    Fetch daily index data from Tushare pro.index_daily.

    Args:
        cfg: TSConfig with token.
        ts_code: e.g. '000001.SH', '399001.SZ', '000300.SH'.
        start_date: YYYYMMDD, inclusive.
        end_date: YYYYMMDD, inclusive; defaults to today.
    """
    pro = _init_ts_pro(cfg)
    params: Dict[str, str] = {"ts_code": ts_code, "start_date": start_date}
    if end_date:
        params["end_date"] = end_date

    df = pro.index_daily(**params)
    if df.empty:
        return df

    df["trade_date"] = pd.to_datetime(df["trade_date"])
    df = df.sort_values("trade_date").set_index("trade_date")
    return df


def index_daily_to_monthly_return(df_daily: pd.DataFrame) -> pd.Series:
    """
    Convert daily index data to monthly simple returns based on close price.

    This is a *price* return (no dividends). For many China indices that is
    already the standard; later we can extend this to use total-return proxies
    when available.
    """
    if df_daily.empty:
        return pd.Series(dtype="float64")

    # Resample to month-end close
    close = df_daily["close"].resample("ME").last()
    ret = close.pct_change().dropna()
    ret.name = "ret_m"
    return ret


def get_index_monthly_return(
    cfg: TSConfig,
    ts_code: str,
    start_date: str = "19900101",
    end_date: Optional[str] = None,
) -> pd.Series:
    """
    Convenience wrapper: daily index → monthly return series.
    """
    df_daily = get_index_daily(cfg, ts_code=ts_code, start_date=start_date, end_date=end_date)
    return index_daily_to_monthly_return(df_daily)


def get_macro_monthly(
    cfg: TSConfig,
    indicator: str,
    start_date: str = "19900101",
    end_date: Optional[str] = None,
) -> pd.Series:
    """
    Fetch a macro indicator as a monthly series.

    This is intentionally slim for now – we only support a small set of
    commonly used indicators and can extend gradually as we formalise the
    Huatai spec.

    Supported indicator keys (to be extended):
        - 'cpi_yoy': 居民消费价格指数同比
        - 'ppi_yoy': 工业生产者出厂价格指数同比

    Returns:
        pd.Series indexed by month-end Timestamp.
    """
    pro = _init_ts_pro(cfg)

    if indicator == "cpi_yoy":
        df = pro.cn_cpi(start_m=start_date, end_m=end_date)
        if df.empty:
            return pd.Series(dtype="float64")
        df["month"] = pd.to_datetime(df["month"].astype(str), format="%Y%m", errors="coerce")
        # 使用全国总指数同比（nt_yoy）作为代表
        s = df.set_index("month")["nt_yoy"]
    elif indicator == "ppi_yoy":
        df = pro.cn_ppi(start_m=start_date, end_m=end_date)
        if df.empty:
            return pd.Series(dtype="float64")
        df["month"] = pd.to_datetime(df["month"].astype(str), format="%Y%m", errors="coerce")
        s = df.set_index("month")["ppi_yoy"]
    else:
        raise ValueError(f"Unsupported macro indicator key: {indicator}")

    # Align to month-end index for consistency with financial returns
    s.index = s.index.to_period("M").to_timestamp("M")
    s.name = indicator
    return s.sort_index()


def get_index_coverage(
    cfg: TSConfig,
    ts_codes: List[str],
    start_date: str = "19900101",
) -> pd.DataFrame:
    """
    Quick coverage check for a list of indices.

    Returns a small DataFrame with first/last available dates and row counts.
    """
    records = []
    for code in ts_codes:
        df = get_index_daily(cfg, code, start_date=start_date)
        if df.empty:
            records.append({"ts_code": code, "rows": 0, "start": None, "end": None})
        else:
            records.append(
                {
                    "ts_code": code,
                    "rows": int(df.shape[0]),
                    "start": df.index.min(),
                    "end": df.index.max(),
                }
            )
    return pd.DataFrame.from_records(records)
