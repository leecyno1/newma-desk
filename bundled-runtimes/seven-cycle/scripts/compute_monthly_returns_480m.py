#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Compute last 480 months (~40y) monthly returns (prefer total return) for major categories.
Outputs:
- Parquet: output/monthly_returns_480m.parquet
- Markdown preview (first/last 12 months per category): output/monthly_returns_480m.md
"""
from __future__ import annotations

import os
import io
from typing import Dict
import pandas as pd
import numpy as np
import requests

import akshare as ak
try:
    import yfinance as yf
except Exception:
    yf = None

# Reuse helpers by importing from 20y script if present
from compute_monthly_returns_20y import (
    CN_CORE, CN_STYLE, CN_BONDS, GLOBAL,
    CN_CORE_ETF, CN_STYLE_ETF,
    fetch_ak_index_monthly, fetch_cn_etf_acc_nav_monthly,
    stooq_monthly, yf_monthly_adj,
    sw_l1_monthly_map, fetch_sw_l1_monthly,
    openbb_yf_monthly_tr,
)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR = os.path.join(ROOT, "output")
os.makedirs(OUT_DIR, exist_ok=True)

TODAY = pd.Timestamp.today().normalize()
END = TODAY
START = END - pd.DateOffset(months=480) + pd.offsets.MonthEnd(0)

def build_category(mapping: Dict[str, str], fetcher) -> pd.DataFrame:
    rows = {}
    for name, code in mapping.items():
        try:
            ser = fetcher(code)
            rows[name] = ser
        except Exception:
            rows[name] = pd.Series(dtype="float64")
    return pd.DataFrame(rows)

def to_markdown_tail(df: pd.DataFrame, title: str) -> str:
    # show head 12 and tail 12 for sanity
    head = (df.head(12) * 100.0).round(2)
    head.index = [d.strftime("%Y-%m") for d in head.index]
    tail = (df.tail(12) * 100.0).round(2)
    tail.index = [d.strftime("%Y-%m") for d in tail.index]
    head.columns = [str(c) for c in head.columns]
    tail.columns = [str(c) for c in tail.columns]
    def tbl(block: pd.DataFrame) -> str:
        md = []
        md.append("| 月份 | " + " | ".join(block.columns) + " |")
        md.append("| --- | " + " | ".join(["---"] * block.shape[1]) + " |")
        for idx, row in block.iterrows():
            md.append("| " + idx + " | " + " | ".join(row.astype(object).astype(str)) + " |")
        return "\n".join(md)
    return f"### {title}\n\n(前12个月)\n\n{tbl(head)}\n\n(后12个月)\n\n{tbl(tail)}\n"

def main():
    out = {}
    # A股宽基：ETF累计净值优先 + 指数点位补充
    cn_core_etf = build_category(CN_CORE_ETF, fetch_cn_etf_acc_nav_monthly)
    cn_core_idx = build_category(CN_CORE, fetch_ak_index_monthly)
    cn_core = cn_core_etf.combine_first(cn_core_idx)
    out[("A股宽基指数",)] = cn_core
    # 风格：ETF累计净值优先 + 指数点位
    cn_style_etf = build_category(CN_STYLE_ETF, fetch_cn_etf_acc_nav_monthly)
    cn_style_idx = build_category(CN_STYLE, fetch_ak_index_monthly)
    cn_style = pd.concat([cn_style_etf, cn_style_idx], axis=1)
    out[("风格/规模指数",)] = cn_style
    # 申万一级
    sw_map = sw_l1_monthly_map()
    sw_df = pd.DataFrame({k: fetch_sw_l1_monthly(v) for k, v in sw_map.items()})
    out[("申万一级行业",)] = sw_df
    # 债券
    cn_bonds = build_category(CN_BONDS, fetch_ak_index_monthly)
    out[("各类债券指数",)] = cn_bonds
    # 海外：优先OpenBB yfinance（日频含分红构造TR）-> yfinance月Adj -> Stooq
    yf_map = {
        "标普500(SPY)": ("etf", "SPY"),
        "纳指100(QQQ)": ("etf", "QQQ"),
        "罗素2000(IWM)": ("etf", "IWM"),
        "德国ETF(EWG)": ("etf", "EWG"),
        "印度ETF(INDA)": ("etf", "INDA"),
        "英国富时100(^FTSE)": ("index", "^FTSE"),
        "法国CAC40(^FCHI)": ("index", "^FCHI"),
    }
    glob_series = {}
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

    # Merge and save
    big = []
    for (cat,), df in out.items():
        # trim to 480-month window explicitly
        df = df.loc[(df.index >= START) & (df.index <= END)]
        df.columns = pd.MultiIndex.from_product([[cat], df.columns])
        big.append(df)
    big_df = pd.concat(big, axis=1).sort_index()
    big_df.to_parquet(os.path.join(OUT_DIR, "monthly_returns_480m.parquet"))

    # MD preview
    sections = []
    for (cat,), df in out.items():
        df = df.loc[(df.index >= START) & (df.index <= END)]
        sections.append(to_markdown_tail(df, f"{cat} 月度回报（%）"))
    with open(os.path.join(OUT_DIR, "monthly_returns_480m.md"), "w", encoding="utf-8") as f:
        f.write("# 480个月月度回报（复权/指数增长率）\n\n")
        f.write("> 口径：A股优先ETF累计净值，海外优先OpenBB yfinance(含分红)；其余为指数点位。\n\n")
        f.write("\n\n".join(sections))
    print("Wrote output/monthly_returns_480m.parquet and monthly_returns_480m.md")

if __name__ == "__main__":
    main()

