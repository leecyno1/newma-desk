#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
频谱扫描脚本（60 年窗口，月频）

目标：
- 基于 cycle_analysis_system/docs/INDICATORS_60Y.md 中列出的可得指标，
  从 FRED / Stooq / Fama-French 获取尽可能长的月度序列（目标 1965–2024）。
- 统一转为“环比”或“收益”（对价格/指数用月度收益，对利率类用差分）。
- 对每个指标做频谱分析（Welch periodogram），在 6–600 个月周期范围内寻找功率谱峰值。
- 输出：
  - 文本摘要：output/spectral_60y_summary.md
  - 可选：每个指标的 periodogram 图：output/spectral_60y_plots/<name>.png

注意：
- 本脚本暂不依赖 5 个预设周期，而是让数据“说话”，找出显著的周期候选。
"""
from __future__ import annotations

import os
import io
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd
import requests
from scipy import signal

try:
    from pandas_datareader import data as web
except Exception:
    web = None

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR = os.path.join(ROOT, "output")
PLOT_DIR = os.path.join(OUT_DIR, "spectral_60y_plots")
os.makedirs(OUT_DIR, exist_ok=True)
os.makedirs(PLOT_DIR, exist_ok=True)

START = pd.Timestamp("1965-01-01")
END = pd.Timestamp("2024-12-31")


def fetch_fred(symbol: str) -> pd.Series:
    if web is None:
        return pd.Series(dtype="float64")
    try:
        df = web.DataReader(symbol, "fred", START, END)
        s = df.iloc[:, 0]
        s.index = pd.to_datetime(s.index)
        # 有的系列是日/周频，统一为月末
        s = s.resample("ME").last()
        return s
    except Exception:
        return pd.Series(dtype="float64")


def fetch_stooq(symbol: str) -> pd.Series:
    url = f"https://stooq.com/q/d/l/?s={symbol}&i=m"
    try:
        r = requests.get(url, timeout=30)
        r.raise_for_status()
        df = pd.read_csv(io.StringIO(r.text))
        if "Date" not in df.columns or "Close" not in df.columns or df.empty:
            return pd.Series(dtype="float64")
        df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
        s = df.set_index("Date")["Close"].sort_index()
        s = s.loc[(s.index >= START) & (s.index <= END)]
        return s
    except Exception:
        return pd.Series(dtype="float64")


def fetch_ff_17() -> pd.DataFrame:
    if web is None:
        return pd.DataFrame()
    try:
        ff = web.DataReader("17_Industry_Portfolios", "famafrench")
        m = ff[0]  # monthly returns (%)
        m.index = m.index.to_timestamp("M")
        m = m.sort_index()
        m = m.loc[(m.index >= START) & (m.index <= END)]
        # 转为小数
        return m / 100.0
    except Exception:
        return pd.DataFrame()


def preprocess_to_mom(series: pd.Series, kind: str) -> pd.Series:
    """
    kind:
      - 'level'   -> pct_change (如 CPI, INDPRO, M2)
      - 'rate'    -> diff (如 UNRATE, FEDFUNDS, yields, spreads)
      - 'price'   -> pct_change (如 股指/ETF/大宗商品)
      - 'return'  -> 本身即为月度收益 (如 Fama-French 行业组合)
    """
    s = series.copy().sort_index()
    if kind == "level":
        return s.pct_change()
    elif kind == "rate":
        return s.diff()
    elif kind == "price":
        return s.pct_change()
    elif kind == "return":
        return s  # 已是收益
    else:
        return s


def welch_periodogram(x: pd.Series, fs: float = 1.0) -> Tuple[np.ndarray, np.ndarray]:
    """
    Welch periodogram, 返回频率 f (cycles per unit) 和功率谱 Pxx。
    fs=1.0 表示单位为“每月一次采样”。
    """
    x = x.dropna()
    if len(x) < 120:  # 不足 10 年，频谱意义不大
        return np.array([]), np.array([])
    x_d = x - x.mean()
    f, Pxx = signal.welch(x_d.values, fs=fs, window="hann", nperseg=min(256, len(x_d)//2), noverlap=None)
    return f, Pxx


def find_peak_periods(f: np.ndarray, Pxx: np.ndarray, min_period: float = 6, max_period: float = 600, top_n: int = 5) -> List[Tuple[float, float]]:
    """
    在给定频谱中寻找主要峰值，返回 (周期(个月), 归一化功率) 列表，按功率降序。
    只考虑对应周期在 [min_period, max_period] 范围内的峰。
    """
    if f.size == 0:
        return []
    # 频率为 cycles/month，周期=1/f
    with np.errstate(divide="ignore", invalid="ignore"):
        periods = 1.0 / f
    mask = (periods >= min_period) & (periods <= max_period) & np.isfinite(periods)
    f_sel = f[mask]
    P_sel = Pxx[mask]
    if f_sel.size == 0:
        return []
    # 找峰
    peaks, _ = signal.find_peaks(P_sel)
    if peaks.size == 0:
        return []
    peak_periods = periods[mask][peaks]
    peak_powers = P_sel[peaks]
    # 正则化功率便于比较
    if peak_powers.sum() > 0:
        norm_powers = peak_powers / peak_powers.sum()
    else:
        norm_powers = peak_powers
    res = list(zip(peak_periods, norm_powers))
    # 按功率降序，取前 top_n
    res.sort(key=lambda x: x[1], reverse=True)
    return res[:top_n]


def main():
    # 1) 定义需要分析的指标及其类型
    fred_level = {
        "CPIAUCSL": "CPI(ALL)",
        "PPIACO": "PPI(All Commodities)",
        "INDPRO": "Industrial Production",
        "PAYEMS": "Nonfarm Payrolls",
        "M2SL": "M2 Money Stock",
    }
    fred_rate = {
        "UNRATE": "Unemployment Rate",
        "FEDFUNDS": "Fed Funds Rate",
        "DGS10": "US 10Y Yield",
        "DGS2": "US 2Y Yield",
        "T10Y3M": "Term Spread 10Y-3M",
        "BAA10Y": "Credit Spread BAA-10Y",
    }
    fred_other = {
        "DCOILWTICO": "WTI Oil",
        "GOLDAMGBD228NLBM": "Gold Price",
        "DTWEXBGS": "Broad Dollar Index",
    }
    stooq_idx = {
        "^spx": "S&P 500",
        "^dji": "Dow Jones",
        "^ndx": "NASDAQ 100",
        "^ukx": "FTSE 100",
        "^cac": "CAC 40",
        "^dax": "DAX",
        "^nkx": "Nikkei 225",
    }

    # 2) 拉取数据并预处理为月度环比/收益
    series_dict: Dict[str, pd.Series] = {}

    # FRED level
    for sym, name in fred_level.items():
        s = fetch_fred(sym)
        if s.empty:
            continue
        series_dict[f"FRED:{sym}:{name}"] = preprocess_to_mom(s, "level")

    # FRED rate
    for sym, name in fred_rate.items():
        s = fetch_fred(sym)
        if s.empty:
            continue
        series_dict[f"FRED:{sym}:{name}"] = preprocess_to_mom(s, "rate")

    # FRED other (treat as price)
    for sym, name in fred_other.items():
        s = fetch_fred(sym)
        if s.empty:
            continue
        series_dict[f"FRED:{sym}:{name}"] = preprocess_to_mom(s, "price")

    # Stooq indices (price)
    for sym, name in stooq_idx.items():
        s = fetch_stooq(sym)
        if s.empty:
            continue
        series_dict[f"Stooq:{sym}:{name}"] = preprocess_to_mom(s, "price")

    # Fama-French 17 industries (monthly returns)
    ff_df = fetch_ff_17()
    if not ff_df.empty:
        for col in ff_df.columns:
            key = f"FF17:{col}"
            series_dict[key] = preprocess_to_mom(ff_df[col], "return")

    # 3) 对每个序列做 Welch 频谱分析，记录主要周期
    summary_lines = []
    summary_lines.append("# 60 年窗口频谱分析摘要\n")
    summary_lines.append("说明：周期单位为“月”；功率为该峰在选定频段内的相对能量权重（归一化）。\n")

    for key, s in series_dict.items():
        f, Pxx = welch_periodogram(s, fs=1.0)
        peaks = find_peak_periods(f, Pxx, min_period=6, max_period=600, top_n=5)
        if not peaks:
            continue
        summary_lines.append(f"## {key}")
        summary_lines.append("")
        summary_lines.append("| 序号 | 周期(月) | 相对功率 |")
        summary_lines.append("| --- | --- | --- |")
        for i, (T, power) in enumerate(peaks, 1):
            summary_lines.append(f"| {i} | {T:.1f} | {power:.3f} |")
        summary_lines.append("")

        # 可选：画 periodogram 图
        try:
            import matplotlib.pyplot as plt

            periods = np.where(f > 0, 1.0 / f, np.nan)
            mask = (periods >= 6) & (periods <= 600)
            fig, ax = plt.subplots(figsize=(8, 4))
            ax.plot(periods[mask], Pxx[mask])
            ax.set_xscale("log")
            ax.set_xlabel("Period (months, log scale)")
            ax.set_ylabel("Power")
            ax.set_title(key)
            ax.grid(True, which="both", ls="--", alpha=0.4)
            png_name = key.replace(":", "_").replace("/", "_")
            fig.tight_layout()
            fig.savefig(os.path.join(PLOT_DIR, f"{png_name}_periodogram.png"), dpi=150)
            plt.close(fig)
        except Exception:
            pass

    # 4) 写入摘要 Markdown
    out_md = os.path.join(OUT_DIR, "spectral_60y_summary.md")
    with open(out_md, "w", encoding="utf-8") as f:
        f.write("\n".join(summary_lines))
    print("Wrote", out_md)


if __name__ == "__main__":
    main()

