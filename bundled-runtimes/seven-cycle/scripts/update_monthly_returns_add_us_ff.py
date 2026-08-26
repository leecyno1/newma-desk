#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Post-process monthly_returns_20y.parquet to add:
- 美股行业ETF (SPDR sector ETFs, 月度回报，近似总回报 via Stooq)
- FF 17行业组合(US) (Fama-French 17 Industry Portfolios, 月度回报，可能不足20年)

Then overwrites monthly_returns_20y.parquet so downstream HTML渲染可直接使用。
"""
from __future__ import annotations

import os
import io
from typing import Dict

import numpy as np
import pandas as pd
import requests

try:
    from pandas_datareader import data as web
except Exception:
    web = None

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR = os.path.join(ROOT, "output")

US_SECTOR_ETF = {
    "美股可选消费(XLY)": "xly.us",
    "美股必选消费(XLP)": "xlp.us",
    "美股能源(XLE)": "xle.us",
    "美股金融(XLF)": "xlf.us",
    "美股工业(XLI)": "xli.us",
    "美股信息科技(XLK)": "xlk.us",
    "美股公用事业(XLU)": "xlu.us",
    "美股医疗保健(XLV)": "xlv.us",
    "美股原材料(XLB)": "xlb.us",
}


def stooq_monthly(symbol: str, start: pd.Timestamp, end: pd.Timestamp) -> pd.Series:
    url = f"https://stooq.com/q/d/l/?s={symbol}&i=m"
    r = requests.get(url, timeout=30)
    r.raise_for_status()
    df = pd.read_csv(io.StringIO(r.text))
    if "Date" not in df.columns or "Close" not in df.columns or df.empty:
        return pd.Series(dtype="float64")
    df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
    s = df.set_index("Date")["Close"].sort_index()
    s = s.loc[(s.index >= start) & (s.index <= end)]
    return s.pct_change()


def ff_17_industries_monthly(start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    if web is None:
        return pd.DataFrame()
    try:
        ff = web.DataReader("17_Industry_Portfolios", "famafrench")
        m = ff[0]  # monthly returns in percent
        m.index = m.index.to_timestamp("M")
        m = m.sort_index()
        m = m.loc[(m.index >= start) & (m.index <= end)]
        return m / 100.0
    except Exception:
        return pd.DataFrame()


def main():
    # Update 480m file
    src480 = os.path.join(OUT_DIR, "monthly_returns_480m.parquet")
    if not os.path.exists(src480):
        raise SystemExit("monthly_returns_480m.parquet 不存在，请先运行 scripts/compute_monthly_returns_480m.py")
    df480 = pd.read_parquet(src480)
    s_start, s_end = df480.index.min(), df480.index.max()

    us_sector_series_480 = {}
    for name, sym in US_SECTOR_ETF.items():
        us_sector_series_480[name] = stooq_monthly(sym, s_start, s_end)
    us480 = pd.DataFrame(us_sector_series_480).reindex(df480.index)
    ff480 = ff_17_industries_monthly(s_start, s_end).reindex(df480.index)

    big480 = df480.copy()
    # drop old versions if already present to avoid duplicates
    if isinstance(big480.columns, pd.MultiIndex):
        mask = big480.columns.get_level_values(0).isin(["美股行业ETF", "FF 17行业组合(US)"])
        big480 = big480.loc[:, ~mask]

    if not us480.empty:
        us480.columns = pd.MultiIndex.from_product([["美股行业ETF"], us480.columns])
        big480 = pd.concat([big480, us480], axis=1)
    if not ff480.empty:
        ff480.columns = pd.MultiIndex.from_product([["FF 17行业组合(US)"], ff480.columns])
        big480 = pd.concat([big480, ff480], axis=1)

    big480 = big480.sort_index(axis=1)
    big480.to_parquet(src480)
    print("Updated", src480, "with 美股行业ETF and FF 17行业组合(US)")


if __name__ == "__main__":
    main()
