#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Build a consolidated monthly dataset (1984-2024) for cycle analysis:
- Load reference Excel indicators if present
- Fetch FRED macro, Stooq market series, and selected commodities
- Standardize to monthly and transform to MoM (or diff for rates)
- Save parquet and a metadata CSV
"""
from __future__ import annotations

import os
from typing import Dict, List, Tuple
from datetime import datetime

import pandas as pd
import numpy as np
from pandas_datareader import data as web

from cycle_utils import SeriesMeta, stooq_daily, to_monthly_end, mom_change, diff_change, ensure_dir

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(ROOT, "data")
OUTPUT_DIR = os.path.join(ROOT, "output")
ensure_dir(DATA_DIR)
ensure_dir(OUTPUT_DIR)

START = "1984-01-01"
END = "2024-12-31"

# FRED series (monthly or daily -> monthly):
# Levels (use pct_change):
FRED_LEVELS = {
    "CPIAUCSL": "CPI(ALL)",         # CPI All Urban Consumers
    "PPIACO": "PPI",                # PPI All Commodities
    "INDPRO": "Industrial Production",
    "PAYEMS": "Nonfarm Payrolls",
    "RSAFS": "Retail Sales",
    "M2SL": "M2 Money Stock",
    "DCOILWTICO": "WTI Oil (Daily)",  # daily -> monthly average
    "GOLDAMGBD228NLBM": "Gold LBMA (Daily)",  # daily -> monthly avg
    "DTWEXBGS": "Dollar Index (DTWEXBGS)",
}
# Rates (use diff):
FRED_RATES = {
    "UNRATE": "Unemployment Rate",
    "FEDFUNDS": "Fed Funds Rate",
    "DGS10": "US 10Y Yield",
    "DGS2": "US 2Y Yield",
    "T10Y3M": "Term Spread (10Y-3M)",
    "BAA10Y": "Credit Spread (BAA-10Y)",
}

# Stooq indices/ETFs (close) -> monthly pct_change:
STOOQ_SERIES = {
    "^spx": "S&P 500",
    "^ndx": "NASDAQ 100",
    "^dji": "Dow Jones",
    "^rut": "Russell 2000 (index)",
    "iwm.us": "Russell 2000 (ETF)",
    "spy.us": "S&P 500 (ETF)",
    "qqq.us": "NASDAQ 100 (ETF)",
    "ewg.us": "Germany ETF",
    "inda.us": "India ETF",
    "^ukx": "FTSE100",
    "^cac": "CAC40",
    "dxy.us": "DXY (ETF proxy)",  # may be empty; DTWEXBGS from FRED is primary
}


def fetch_fred_series(symbol: str) -> pd.Series:
    df = web.DataReader(symbol, "fred", START, END)
    s = df.iloc[:, 0]
    s.index = pd.to_datetime(s.index)
    # Some are daily; unify monthly
    if s.index.freq is None or s.index.freqstr is None or s.index.freqstr[0] not in ("M",):
        s = s.resample("ME").mean()
    return s


def main():
    metas: List[SeriesMeta] = []
    frames: Dict[str, pd.Series] = {}

    # 1) Reference Excel (if present)
    xlsx_path = os.environ.get("SEVEN_CYCLE_REFERENCE_XLSX", "")
    if os.path.exists(xlsx_path):
        try:
            xls = pd.ExcelFile(xlsx_path)
            for sheet in xls.sheet_names:
                df = xls.parse(sheet)
                # Guess datetime column
                dt_col = None
                for c in df.columns[:3]:
                    if str(c).lower() in ("date", "时间", "日期", "dt", "month"):
                        dt_col = c
                        break
                if dt_col is None:
                    continue
                df[dt_col] = pd.to_datetime(df[dt_col], errors="coerce")
                df = df.dropna(subset=[dt_col])
                for col in df.columns:
                    if col == dt_col:
                        continue
                    s = df[[dt_col, col]].dropna()
                    if s.empty:
                        continue
                    s = s.rename(columns={dt_col: "date", col: "val"})
                    s_m = s.set_index("date")["val"].sort_index().resample("ME").last()
                    # Default transform: mom
                    s_tr = s_m.pct_change()
                    name = f"Ref:{sheet}:{col}"
                    frames[name] = s_tr
                    metas.append(SeriesMeta(name=name, source="Excel", transform="level->mom"))
        except Exception:
            pass

    # 2) FRED level series -> MoM pct change
    for fred_sym, name in FRED_LEVELS.items():
        try:
            s = fetch_fred_series(fred_sym)
            s_tr = s.pct_change()
            frames[f"FRED:{fred_sym}:{name}"] = s_tr
            metas.append(SeriesMeta(name=f"FRED:{fred_sym}:{name}", source="FRED", transform="level->mom"))
        except Exception:
            continue

    # 3) FRED rate series -> first difference
    for fred_sym, name in FRED_RATES.items():
        try:
            s = fetch_fred_series(fred_sym)
            s_tr = s.diff()
            frames[f"FRED:{fred_sym}:{name}"] = s_tr
            metas.append(SeriesMeta(name=f"FRED:{fred_sym}:{name}", source="FRED", transform="rate->diff"))
        except Exception:
            continue

    # 4) Stooq -> monthly returns
    for sym, name in STOOQ_SERIES.items():
        try:
            dfd = stooq_daily(sym)
            if dfd.empty:
                continue
            s_m = to_monthly_end(dfd, "date", "close", how="last")
            s_tr = s_m.pct_change()
            frames[f"Stooq:{sym}:{name}"] = s_tr
            metas.append(SeriesMeta(name=f"Stooq:{sym}:{name}", source="Stooq", transform="price->mom"))
        except Exception:
            continue

    # Combine
    df_all = pd.concat(frames, axis=1)
    # Trim 1984-01..2024-12
    df_all = df_all.loc[(df_all.index >= pd.Timestamp(START)) & (df_all.index <= pd.Timestamp(END))]
    # Drop all-NaN columns
    df_all = df_all.dropna(how="all", axis=1)
    # Save
    df_all.to_parquet(os.path.join(DATA_DIR, "cycle_dataset_mom.parquet"))
    meta_df = pd.DataFrame([m.__dict__ for m in metas])
    meta_df.to_csv(os.path.join(DATA_DIR, "cycle_dataset_meta.csv"), index=False)
    print(f"Saved dataset with {df_all.shape[1]} series and {df_all.shape[0]} months -> data/cycle_dataset_mom.parquet")


if __name__ == "__main__":
    main()
