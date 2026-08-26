#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Compute 2014-2024 annual returns for a curated set of indices/assets.
Data sources:
- A股指数、申万一级行业、国债/公司债/转债等: akshare (Sina endpoints)
- 海外指数/ETF: Stooq CSV endpoints (to avoid yfinance rate limits)
- 黄金: 上海黄金交易所基准价
- 豆粕: 大商所豆粕主力连续 M0 (Sina)

Output: writes Markdown tables to ./output/annual_returns_2014_2024.md
"""
from __future__ import annotations

import os
import sys
import io
import time
import math
import json
import textwrap
from typing import Dict, List, Tuple, Optional
from datetime import datetime, date

import pandas as pd

# Third-party libs (installed in local venv ideally)
try:
    import akshare as ak
except Exception as e:
    print("ERROR: akshare not available. Please install inside your venv: pip install akshare")
    raise

OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "output")
os.makedirs(OUTPUT_DIR, exist_ok=True)

START_YEAR = 2004
END_YEAR = 2024
YEARS = list(range(START_YEAR, END_YEAR + 1))

# Helper: compute annual returns from a daily close series
def compute_annual_returns_from_df(df: pd.DataFrame, date_col: str, close_col: str) -> pd.Series:
    """
    Given a daily timeseries DataFrame with columns [date_col, close_col],
    compute annual returns for START_YEAR..END_YEAR based on last trading day close per year.
    """
    if df.empty:
        return pd.Series(index=YEARS, dtype="float64")
    # Normalize date
    s = df[[date_col, close_col]].copy()
    s[date_col] = pd.to_datetime(s[date_col], errors="coerce")
    s = s.dropna(subset=[date_col, close_col])
    s = s.sort_values(date_col)
    # Year-end closes
    s["year"] = s[date_col].dt.year
    year_end = s.groupby("year")[close_col].last()
    # Compute pct change YoY
    pct = year_end.pct_change()
    # Filter target window and reindex with all years
    out = pct.loc[START_YEAR:END_YEAR].reindex(YEARS)
    return out


# ---------- Fetchers ----------

def fetch_cn_index_daily(code: str) -> pd.DataFrame:
    """
    Fetch A-share index daily using ak.stock_zh_index_daily
    code examples: 'sh000300', 'sh000905', 'sh000852', 'sh000015', 'sh000057', 'sz399269', etc.
    Returns columns: [date, open, high, low, close, volume]
    """
    df = ak.stock_zh_index_daily(symbol=code)
    # Normalize column names
    df = df.rename(columns={"date": "日期", "close": "收盘"})
    return df


def fetch_sw_l1_daily(sw_code: str) -> pd.DataFrame:
    """
    Fetch Shenwan L1 industry daily history via ak.index_hist_sw
    sw_code examples: '801010', '801050', etc.
    Returns columns (中文): ['代码','日期','收盘','开盘','最高','最低','成交量','成交额']
    """
    df = ak.index_hist_sw(symbol=sw_code, period="day")
    return df


def fetch_gold_sge_benchmark() -> pd.DataFrame:
    """
    上海黄金交易所基准价，返回列: ['交易时间','晚盘价','早盘价']
    We'll use the '晚盘价' if available, else '早盘价' for the day-end proxy.
    """
    df = ak.spot_golden_benchmark_sge()
    df = df.rename(columns={"交易时间": "日期"})
    # Make a single close column preferring the evening fixing
    df["收盘"] = pd.to_numeric(df.get("晚盘价"), errors="coerce")
    # Fall back to morning price if evening is NaN
    df["收盘"] = df["收盘"].fillna(pd.to_numeric(df.get("早盘价"), errors="coerce"))
    df = df.dropna(subset=["日期", "收盘"])
    return df[["日期", "收盘"]]


def fetch_soymeal_main_continuous() -> pd.DataFrame:
    """
    豆粕主力连续 M0 日线 (Sina)
    Returns columns: ['date','open','high','low','close','volume','hold','settle']
    """
    df = ak.futures_zh_daily_sina(symbol="M0")
    df = df.rename(columns={"date": "日期", "close": "收盘"})
    return df


def fetch_csindex_daily(cs_symbol: str, start_date: str = "20040101", end_date: str = "20241231") -> pd.DataFrame:
    """
    Fetch CSI (中证) index daily via csindex API when only CSI website has the series.
    Returns columns with ['日期','收盘'].
    """
    df = ak.stock_zh_index_hist_csindex(symbol=cs_symbol, start_date=start_date, end_date=end_date)
    df = df.rename(columns={"收盘": "收盘", "日期": "日期"})
    return df[["日期", "收盘"]]


def fetch_stooq_csv(symbol: str) -> pd.DataFrame:
    """
    Fetch CSV from Stooq:
      https://stooq.com/q/d/l/?s=<symbol>&i=d
    Examples:
      'spy.us', 'qqq.us', 'ewg.us', 'inda.us', '^nkx', '^dax'
    Returns columns: Date,Open,High,Low,Close,Volume
    """
    import requests
    url = f"https://stooq.com/q/d/l/?s={symbol}&i=d"
    r = requests.get(url, timeout=30)
    r.raise_for_status()
    data = r.text
    df = pd.read_csv(io.StringIO(data))
    df = df.rename(columns={"Date": "日期", "Close": "收盘"})
    return df


# ---------- Asset Sets ----------

CN_CORE_INDICES: Dict[str, str] = {
    "沪深300": "sh000300",
    "中证500": "sh000905",
    "中证1000": "sh000852",
}

CN_STYLE_INDICES: Dict[str, str] = {
    "红利指数(上证)": "sh000015",
    "全指成长": "sh000057",
    "创质量": "sz399269",       # 质量风格可用的一个代表性指数（创业板质量）
    "超大盘": "sh000043",
    "上证小盘": "sh000045",
    "中小盘(深证)": "sz399401",
    "中证A500": "sh000510",
    "创业板指": "sz399006",
    "创业板50": "sz399673",
    "科创50": "sh000688",
}

CN_BOND_INDICES: Dict[str, str] = {
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

# Shenwan Level 1 industries
def get_sw_l1_map() -> Dict[str, str]:
    info = ak.sw_index_first_info()
    # Columns: ['行业代码','行业名称', ...], industry code has '.SI' suffix
    info = info.copy()
    info["code"] = info["行业代码"].str.replace(".SI", "", regex=False)
    mapping = dict(zip(info["行业名称"], info["code"]))
    return mapping


GLOBAL_ASSETS_STOOQ: Dict[str, str] = {
    # ETFs
    "标普500(SPY.US)": "spy.us",
    "纳指100(QQQ.US)": "qqq.us",
    "德国ETF(EWG.US)": "ewg.us",
    "印度ETF(INDA.US)": "inda.us",
    "罗素2000(IWM.US)": "iwm.us",
    "越南ETF(VNM.US)": "vnm.us",
    # Indices
    "日经225(^NKX)": "^nkx",
    "法国CAC40(^CAC)": "^cac",
    "英国富时100(^UKX)": "^ukx",
    # "德国DAX(^DAX)": "^dax",  # optional, we already include EWG
}

# Commodities proxies
COMMODITIES: Dict[str, str] = {
    # 黄金 via SGE (handled separately)
    # 有色 via 申万有色金属
    # 豆粕 via M0
}


def compute_returns_for_assets_map(name2code: Dict[str, str], fetcher) -> pd.DataFrame:
    """
    Compute annual returns for a mapping (name -> code) using the provided fetcher,
    which must return a DataFrame containing columns ['日期','收盘'].
    """
    records = []
    for name, code in name2code.items():
        try:
            df = fetcher(code)
            ser = compute_annual_returns_from_df(df, "日期", "收盘")
            row = {"资产": name}
            row.update({y: ser.get(y, math.nan) for y in YEARS})
            records.append(row)
        except Exception as e:
            # Collect a row of NaNs if fetch failed
            row = {"资产": f"{name} (获取失败: {e})"}
            row.update({y: math.nan for y in YEARS})
            records.append(row)
    out = pd.DataFrame.from_records(records).set_index("资产")
    return out


def to_markdown_table(df: pd.DataFrame, title: str) -> str:
    """
    Convert a returns DataFrame to markdown with percentage formatting.
    """
    df_fmt = df.copy()
    for y in YEARS:
        if y in df_fmt.columns:
            df_fmt[y] = (df_fmt[y] * 100).map(lambda x: "" if pd.isna(x) else f"{x:.2f}%")
    md = []
    md.append(f"### {title}")
    md.append("")
    md.append("| 资产 | " + " | ".join(str(y) for y in YEARS) + " |")
    md.append("| --- | " + " | ".join(["---"] * len(YEARS)) + " |")
    for idx, row in df_fmt.iterrows():
        md.append("| " + str(idx) + " | " + " | ".join(str(row.get(y, "")) for y in YEARS) + " |")
    md.append("")
    return "\n".join(md)


def main():
    all_sections: List[str] = []

    # 1) 核心A股宽基指数
    cn_core_df = compute_returns_for_assets_map(CN_CORE_INDICES, lambda code: fetch_cn_index_daily(code)[["日期", "收盘"]])
    all_sections.append(to_markdown_table(cn_core_df, "A股宽基指数 年度回报率"))

    # 2) 风格/规模指数
    cn_style_df = compute_returns_for_assets_map(CN_STYLE_INDICES, lambda code: fetch_cn_index_daily(code)[["日期", "收盘"]])
    all_sections.append(to_markdown_table(cn_style_df, "风格/规模指数 年度回报率"))

    # 3) 申万一级行业
    sw_map = get_sw_l1_map()
    sw_df = compute_returns_for_assets_map(sw_map, lambda code: fetch_sw_l1_daily(code)[["日期", "收盘"]])
    all_sections.append(to_markdown_table(sw_df, "申万一级行业 年度回报率"))

    # 4) 特色/补充A股指数（仅CSI网站有）：如中证2000
    csindex_map = {
        "中证2000(CSI)": "932000",
    }
    csindex_df = compute_returns_for_assets_map(csindex_map, lambda code: fetch_csindex_daily(code))
    # 国证2000（深证）
    try:
        gn2000_df = fetch_cn_index_daily("sz399303")[["日期", "收盘"]]
        gn2000_ser = compute_annual_returns_from_df(gn2000_df, "日期", "收盘")
        gn2000_out = pd.DataFrame([{"资产": "国证2000", **{y: gn2000_ser.get(y, math.nan) for y in YEARS}}]).set_index("资产")
        csindex_df = pd.concat([csindex_df, gn2000_out], axis=0)
    except Exception:
        pass
    all_sections.append(to_markdown_table(csindex_df, "特色A股指数 年度回报率"))

    # 5) 债券指数
    cn_bond_df = compute_returns_for_assets_map(CN_BOND_INDICES, lambda code: fetch_cn_index_daily(code)[["日期", "收盘"]])
    all_sections.append(to_markdown_table(cn_bond_df, "各类债券指数 年度回报率"))

    # 6) 商品类
    # 黄金
    try:
        gold_df = fetch_gold_sge_benchmark()
        gold_ser = compute_annual_returns_from_df(gold_df, "日期", "收盘")
        gold_out = pd.DataFrame([{"资产": "黄金(SGE基准价)", **{y: gold_ser.get(y, math.nan) for y in YEARS}}]).set_index("资产")
    except Exception as e:
        gold_out = pd.DataFrame([{"资产": f"黄金(SGE基准价) (获取失败: {e})", **{y: math.nan for y in YEARS}}]).set_index("资产")
    # 有色（用申万有色金属）
    try:
        nonfer_df = fetch_sw_l1_daily("801050")[["日期", "收盘"]]
        nonfer_ser = compute_annual_returns_from_df(nonfer_df, "日期", "收盘")
        nonfer_out = pd.DataFrame([{"资产": "有色金属(申万801050)", **{y: nonfer_ser.get(y, math.nan) for y in YEARS}}]).set_index("资产")
    except Exception as e:
        nonfer_out = pd.DataFrame([{"资产": f"有色金属(申万801050) (获取失败: {e})", **{y: math.nan for y in YEARS}}]).set_index("资产")
    # 豆粕（主力连续）
    try:
        soy_df = fetch_soymeal_main_continuous()[["日期", "收盘"]]
        soy_ser = compute_annual_returns_from_df(soy_df, "日期", "收盘")
        soy_out = pd.DataFrame([{"资产": "豆粕主力连续(M0)", **{y: soy_ser.get(y, math.nan) for y in YEARS}}]).set_index("资产")
    except Exception as e:
        soy_out = pd.DataFrame([{"资产": f"豆粕主力连续(M0) (获取失败: {e})", **{y: math.nan for y in YEARS}}]).set_index("资产")
    commodities_df = pd.concat([gold_out, nonfer_out, soy_out], axis=0)
    all_sections.append(to_markdown_table(commodities_df, "大宗商品指标 年度回报率"))

    # 7) 海外指数/ETF（Stooq）
    def stooq_fetcher(code: str) -> pd.DataFrame:
        return fetch_stooq_csv(code)[["日期", "收盘"]]
    global_df = compute_returns_for_assets_map(GLOBAL_ASSETS_STOOQ, stooq_fetcher)
    all_sections.append(to_markdown_table(global_df, "海外指数/ETF 年度回报率"))

    # Write output
    md_path = os.path.join(OUTPUT_DIR, "annual_returns_2014_2024.md")
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(f"# 各类资产年度回报率（{START_YEAR}-{END_YEAR}）\n\n")
        f.write("> 注：数据源见脚本说明；回报为各自然年末收盘价相对上一年底收盘价的涨跌幅。\n\n")
        f.write("\n\n".join(all_sections))
    print(f"Wrote Markdown to: {md_path}")


if __name__ == "__main__":
    main()
