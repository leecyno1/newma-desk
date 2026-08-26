#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Compute last 20 years monthly returns (adj if available) for the same categories as the annual file.
- CN indices via akshare (index level monthly last -> pct_change)
- SW L1 industries via akshare
- Bonds via akshare indices
- Global via Stooq (Close is treated as adjusted proxy)
Output:
- Parquet: output/monthly_returns_20y.parquet (MultiIndex: category, asset x monthly series)
- Markdown summary with latest 24 months per category: output/monthly_returns_20y.md
"""
from __future__ import annotations

import os
import io
from typing import Dict, List, Tuple
import pandas as pd
import numpy as np
import requests
import datetime as dt

import akshare as ak
try:
    import yfinance as yf
except Exception:
    yf = None
try:
    from pandas_datareader import data as web
except Exception:
    web = None

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR = os.path.join(ROOT, "output")
os.makedirs(OUT_DIR, exist_ok=True)

TODAY = pd.Timestamp.today().normalize()
END = TODAY
START = END - pd.DateOffset(years=20) + pd.offsets.MonthEnd(0)

# Reuse the same mappings as annual script
CN_CORE = {
    "沪深300": "sh000300",
    "中证500": "sh000905",
    "中证1000": "sh000852",
}
CN_STYLE = {
    "红利指数(上证)": "sh000015",
    "全指成长": "sh000057",
    "创质量": "sz399269",
    "超大盘": "sh000043",
    "上证小盘": "sh000045",
    "中小盘(深证)": "sz399401",
    "中证A500": "sh000510",
    "创业板指": "sz399006",
    "创业板50": "sz399673",
    "科创50": "sh000688",
}
CN_BONDS = {
    "国债指数(上证)": "sh000012",
    "沪公司债": "sh000022",
    "深信用债": "sz399301",
    "深公司债": "sz399302",
    "企债指数(深证)": "sz399481",
    "国证转债": "sz399413",
    "上证转债": "sh000139",
    "深证转债": "sz399307",
    "深转交债": "sz399290",
}
GLOBAL = {
    "标普500(SPY)": "spy.us",
    "纳指100(QQQ)": "qqq.us",
    "罗素2000(IWM)": "iwm.us",
    "德国ETF(EWG)": "ewg.us",
    "印度ETF(INDA)": "inda.us",
    "英国富时100(^FTSE)": "^ukx",
    "法国CAC40(^FCHI)": "^cac",
}

CN_CORE_ETF = {
    "沪深300(ETF累计净值)": "510300",
    "中证500(ETF累计净值)": "510500",
    "中证1000(ETF累计净值)": "512100",
}
CN_STYLE_ETF = {
    "红利(ETF累计净值)": "510880",
    "创业板指(ETF累计净值)": "159915",
    "创业板50(ETF累计净值)": "159949",
    "科创50(ETF累计净值)": "588000",
}

# US sector ETFs (SPDR)
US_SECTOR_ETF = {
    "美股可选消费(XLY)": "XLY",
    "美股必选消费(XLP)": "XLP",
    "美股能源(XLE)": "XLE",
    "美股金融(XLF)": "XLF",
    "美股工业(XLI)": "XLI",
    "美股信息科技(XLK)": "XLK",
    "美股公用事业(XLU)": "XLU",
    "美股医疗保健(XLV)": "XLV",
    "美股原材料(XLB)": "XLB",
}

def fetch_ak_index_monthly(ts: str) -> pd.Series:
    df = ak.stock_zh_index_daily(symbol=ts)
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    s = df.set_index("date")["close"].sort_index().resample("ME").last()
    s = s.loc[(s.index >= START) & (s.index <= END)]
    return s.pct_change()

def fetch_cn_etf_acc_nav_monthly(code: str) -> pd.Series:
    """
    Eastmoney open fund info: indicator='累计净值走势' as total return proxy.
    """
    df = ak.fund_open_fund_info_em(symbol=code, indicator="累计净值走势")
    df["净值日期"] = pd.to_datetime(df["净值日期"], errors="coerce")
    s = df.set_index("净值日期")["累计净值"].sort_index().resample("ME").last()
    s = s.loc[(s.index >= START) & (s.index <= END)]
    return s.pct_change()

def stooq_monthly(symbol: str) -> pd.Series:
    url = f"https://stooq.com/q/d/l/?s={symbol}&i=m"
    r = requests.get(url, timeout=30)
    r.raise_for_status()
    df = pd.read_csv(io.StringIO(r.text))
    if "Date" not in df.columns or "Close" not in df.columns or df.empty:
        return pd.Series(dtype="float64")
    df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
    s = df.set_index("Date")["Close"].sort_index()
    s = s.loc[(s.index >= START) & (s.index <= END)]
    return s.pct_change()

def yf_monthly_adj(symbol: str) -> pd.Series:
    """
    Try Yahoo Finance monthly adjusted close returns.
    """
    if yf is None:
        return pd.Series(dtype="float64")
    try:
        df = yf.download(symbol, start=str(START.date()), end=str((END+pd.Timedelta(days=1)).date()), interval="1mo", auto_adjust=False, progress=False)
        if df.empty:
            return pd.Series(dtype="float64")
        # Prefer Adj Close if present
        if "Adj Close" in df.columns:
            s = df["Adj Close"]
        else:
            # fallback to Close
            s = df["Close"]
        s.index = pd.to_datetime(s.index)
        s = s.sort_index()
        s = s.loc[(s.index >= START) & (s.index <= END)]
        return s.pct_change()
    except Exception:
        return pd.Series(dtype="float64")

def openbb_base() -> str:
    return os.environ.get("OPENBB_BASE", "http://127.0.0.1:6900")

def openbb_fetch_daily(provider: str, kind: str, symbol: str, start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    """
    kind: 'etf', 'equity', 'index'
    Returns DataFrame with columns [date, close, dividend] if available.
    """
    import requests
    base = openbb_base().rstrip("/")
    if kind == "etf":
        path = "/api/v1/etf/historical"
    elif kind == "equity":
        path = "/api/v1/equity/price/historical"
    else:
        path = "/api/v1/index/price/historical"
    params = {
        "provider": provider,
        "symbol": symbol,
        "start_date": str(start.date()),
        "end_date": str(end.date()),
        "include_actions": "true",
        "interval": "1d",
    }
    r = requests.get(f"{base}{path}", params=params, timeout=30)
    r.raise_for_status()
    js = r.json()
    rows = js.get("results") or []
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    # normalize
    if "date" in df.columns:
        df["date"] = pd.to_datetime(df["date"], errors="coerce")
    if "close" not in df.columns and "adj_close" in df.columns:
        df["close"] = df["adj_close"]
    if "dividend" not in df.columns:
        df["dividend"] = 0.0
    return df.dropna(subset=["date", "close"]).sort_values("date")

def openbb_yf_monthly_tr(kind: str, symbol: str) -> pd.Series:
    """
    Compute monthly total return using daily close + dividend from OpenBB yfinance endpoint.
    TR_daily = (Close_t + Dividend_t) / Close_{t-1} - 1
    TR_month = prod(1+TR_daily) - 1
    """
    try:
        df = openbb_fetch_daily("yfinance", kind, symbol, START, END)
        if df.empty:
            return pd.Series(dtype="float64")
        df = df.set_index("date")[["close", "dividend"]].sort_index()
        # daily TR with reinvested dividends
        close = df["close"].astype(float)
        div = df["dividend"].astype(float).fillna(0.0)
        prev_close = close.shift(1)
        tr_daily = (close + div) / prev_close - 1.0
        tr_month = (1.0 + tr_daily).resample("ME").prod() - 1.0
        tr_month = tr_month.loc[(tr_month.index >= START) & (tr_month.index <= END)]
        return tr_month
    except Exception:
        return pd.Series(dtype="float64")


def build_category(mapping: Dict[str, str], fetcher) -> pd.DataFrame:
    rows = {}
    for name, code in mapping.items():
        try:
            ser = fetcher(code)
            rows[name] = ser
        except Exception:
            rows[name] = pd.Series(dtype="float64")
    return pd.DataFrame(rows)


def ff_17_industries_monthly() -> pd.DataFrame:
    """
    Fama-French 17 Industry Portfolios, monthly returns (%), treated as US行业组合。
    注意：目前Ken French站点此数据集仅提供近几年数据，可能不足20年。
    """
    if web is None:
        return pd.DataFrame()
    try:
        ff = web.DataReader("17_Industry_Portfolios", "famafrench")
        m = ff[0]  # monthly returns in percent
        # index is PeriodIndex; convert to month-end Timestamp
        m.index = m.index.to_timestamp("M")
        m = m.sort_index()
        m = m.loc[(m.index >= START) & (m.index <= END)]
        # convert % -> fraction
        return m / 100.0
    except Exception:
        return pd.DataFrame()

def sw_l1_monthly_map() -> Dict[str, str]:
    info = ak.sw_index_first_info()
    info["code"] = info["行业代码"].str.replace(".SI", "", regex=False)
    return dict(zip(info["行业名称"], info["code"]))

def fetch_sw_l1_monthly(sw_code: str) -> pd.Series:
    df = ak.index_hist_sw(symbol=sw_code, period="day")
    df["日期"] = pd.to_datetime(df["日期"], errors="coerce")
    s = df.set_index("日期")["收盘"].sort_index().resample("ME").last()
    s = s.loc[(s.index >= START) & (s.index <= END)]
    return s.pct_change()

def to_markdown(df: pd.DataFrame, title: str, months: int = 24) -> str:
    tail = df.tail(months).copy() * 100.0
    tail = tail.round(2)
    tail.index = [d.strftime("%Y-%m") for d in tail.index]
    # ensure simple string columns
    tail.columns = [str(c) for c in tail.columns]
    md = [f"### {title}", ""]
    md.append("| 月份 | " + " | ".join(tail.columns) + " |")
    md.append("| --- | " + " | ".join(["---"] * tail.shape[1]) + " |")
    for idx, row in tail.iterrows():
        md.append("| " + idx + " | " + " | ".join(row.astype(object).astype(str)) + " |")
    md.append("")
    return "\n".join(md)

def main():
    out = {}
    # CN core: prefer ETF累计净值（含分红），若失败再用指数点位
    cn_core_etf = build_category(CN_CORE_ETF, fetch_cn_etf_acc_nav_monthly)
    cn_core_idx = build_category(CN_CORE, fetch_ak_index_monthly)
    cn_core = cn_core_etf.combine_first(cn_core_idx)
    out[("A股宽基指数",)] = cn_core
    # CN style: mix ETF累计净值 for available + index fallback
    cn_style_etf = build_category(CN_STYLE_ETF, fetch_cn_etf_acc_nav_monthly)
    cn_style_idx = build_category(CN_STYLE, fetch_ak_index_monthly)
    cn_style = pd.concat([cn_style_etf, cn_style_idx], axis=1)
    out[("风格/规模指数",)] = cn_style
    # SW L1
    sw_map = sw_l1_monthly_map()
    sw_df = pd.DataFrame({k: fetch_sw_l1_monthly(v) for k, v in sw_map.items()})
    out[("申万一级行业",)] = sw_df
    # Bonds
    cn_bonds = build_category(CN_BONDS, fetch_ak_index_monthly)
    out[("各类债券指数",)] = cn_bonds
    # Global: prefer OpenBB yfinance (daily close+div -> monthly TR), fallback Yahoo monthly Adj Close, then Stooq
    glob_series = {}
    # Map display -> (kind, yf_symbol)
    yf_map = {
        "标普500(SPY)": ("etf", "SPY"),
        "纳指100(QQQ)": ("etf", "QQQ"),
        "罗素2000(IWM)": ("etf", "IWM"),
        "德国ETF(EWG)": ("etf", "EWG"),
        "印度ETF(INDA)": ("etf", "INDA"),
        "英国富时100(^FTSE)": ("index", "^FTSE"),
        "法国CAC40(^FCHI)": ("index", "^FCHI"),
    }
    for name, stooq_sym in GLOBAL.items():
        kind, yf_sym = yf_map.get(name, ("etf", None))
        s = pd.Series(dtype="float64")
        if yf_sym:
            s = openbb_yf_monthly_tr(kind, yf_sym)
        if s.empty and yf is not None and yf_sym:
            s = yf_monthly_adj(yf_sym)
        if s.empty:
            s = stooq_monthly(stooq_sym)
        glob_series[name] = s
    glob_df = pd.DataFrame(glob_series)
    out[("海外指数/ETF",)] = glob_df

    # US sector ETFs (total return via OpenBB yfinance, fallback yfinance Adj, then Stooq)
    us_sector_series = {}
    for name, sym in US_SECTOR_ETF.items():
        s = openbb_yf_monthly_tr("etf", sym)
        if s.empty and yf is not None:
            s = yf_monthly_adj(sym)
        if s.empty:
            # last fallback: Stooq ETF if ticker exists, otherwise skip
            stq_sym = f"{sym.lower()}.us"
            s = stooq_monthly(stq_sym)
        us_sector_series[name] = s
    us_sector_df = pd.DataFrame(us_sector_series)
    out[("美股行业ETF",)] = us_sector_df

    # Fama-French 17 Industry Portfolios (US industry composites)
    ff_df = ff_17_industries_monthly()
    if not ff_df.empty:
        out[("FF 17行业组合(US)",)] = ff_df

    # Save parquet (multi index columns)
    big = []
    for (cat,), df in out.items():
        df.columns = pd.MultiIndex.from_product([[cat], df.columns])
        big.append(df)
    big_df = pd.concat(big, axis=1).sort_index()
    big_df.to_parquet(os.path.join(OUT_DIR, "monthly_returns_20y.parquet"))

    # MD summary (tail 24 months per category)
    sections = []
    for (cat,), df in out.items():
        sections.append(to_markdown(df, f"{cat} 月度回报（最近24个月, %）", months=24))
    with open(os.path.join(OUT_DIR, "monthly_returns_20y.md"), "w", encoding="utf-8") as f:
        f.write("# 20年间月度回报（复权/指数增长率）\n\n")
        f.write("> 优先口径：A股采用ETF累计净值（含分红再投资）为基准；海外ETF优先Yahoo Adj Close，失败时退回Stooq；其余为指数点位月末变动。\n\n")
        f.write("\n\n".join(sections))
    print("Wrote output/monthly_returns_20y.parquet and monthly_returns_20y.md")

if __name__ == "__main__":
    main()
