#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Cycle analysis utilities:
- Data loading (FRED, Stooq CSV, Excel reference)
- Standardize to monthly frequency and MoM change
- Signal processing: band-pass filtering around given cycle length, Hilbert phase
"""
from __future__ import annotations

import io
import os
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass

import numpy as np
import pandas as pd
import requests
from scipy import signal


@dataclass
class SeriesMeta:
    name: str
    source: str
    transform: str  # 'level->mom', 'rate->diff', 'return', etc.


def stooq_daily(symbol: str) -> pd.DataFrame:
    url = f"https://stooq.com/q/d/l/?s={symbol}&i=d"
    r = requests.get(url, timeout=30)
    r.raise_for_status()
    df = pd.read_csv(io.StringIO(r.text))
    if "Date" not in df.columns or "Close" not in df.columns:
        return pd.DataFrame()
    df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
    df = df.dropna(subset=["Date"]).sort_values("Date")
    df = df.rename(columns={"Date": "date", "Close": "close"})
    return df[["date", "close"]]


def to_monthly_end(df: pd.DataFrame, date_col: str, value_col: str, how: str = "last") -> pd.Series:
    s = df.copy()
    s[date_col] = pd.to_datetime(s[date_col], errors="coerce")
    s = s.dropna(subset=[date_col]).set_index(date_col)[value_col].sort_index()
    if how == "last":
        return s.resample("ME").last()
    elif how == "mean":
        return s.resample("ME").mean()
    else:
        return s.resample("ME").last()


def mom_change(series: pd.Series) -> pd.Series:
    """Month-over-month percent change."""
    return series.pct_change()


def diff_change(series: pd.Series) -> pd.Series:
    """First difference for rates already in percent."""
    return series.diff()


def bandpass_component(x: pd.Series, period_months: int, bandwidth: float = 0.25, order: int = 4) -> pd.Series:
    """
    Extract band-pass component around target cycle length (in months) using Butterworth + filtfilt.
    Sampling rate fs = 1 (per month), Nyquist = 0.5 cycles/month.
    f0 = 1/period; passband = [f0*(1-bw), f0*(1+bw)] clipped to (0, 0.5).
    """
    x = x.astype("float64").copy()
    x = x - np.nanmean(x)
    fs = 1.0
    nyq = 0.5 * fs
    f0 = 1.0 / float(period_months)
    low = max(1e-6, f0 * (1.0 - bandwidth))
    high = min(0.5 - 1e-6, f0 * (1.0 + bandwidth))
    if not (0 < low < high < 0.5):
        return pd.Series(index=x.index, dtype="float64")
    wn = [low / nyq, high / nyq]
    b, a = signal.butter(order, wn, btype="bandpass")
    # Fill missing for filtering then restore NaNs
    mask = x.isna()
    xf = x.fillna(method="ffill").fillna(method="bfill")
    y = signal.filtfilt(b, a, xf.values)
    y = pd.Series(y, index=x.index)
    y[mask] = np.nan
    return y


def analytic_phase(x: pd.Series) -> pd.Series:
    """
    Analytic signal phase via Hilbert transform; returns phase in radians [-pi, pi].
    """
    xi = x.astype("float64").copy()
    xi = xi.fillna(method="ffill").fillna(method="bfill")
    z = signal.hilbert(xi.values)
    phase = np.angle(z)
    return pd.Series(phase, index=x.index)


def instantaneous_period(phase: pd.Series) -> pd.Series:
    """
    Instantaneous period in months from phase time-derivative.
    """
    p = np.unwrap(phase.values)
    dp = np.diff(p)  # radians per month
    inst_T = 2.0 * np.pi / np.where(dp == 0, np.nan, dp)
    return pd.Series(np.concatenate([[np.nan], inst_T]), index=phase.index)


def flag_outliers(inst_T: pd.Series, target_period: int, tol: float = 0.35) -> pd.Series:
    """
    Flag observations where instantaneous period deviates too much from target.
    tol=0.35 -> +/-35% allowed.
    Returns boolean series: True if normal, False if outlier.
    """
    lower = target_period * (1.0 - tol)
    upper = target_period * (1.0 + tol)
    return (inst_T >= lower) & (inst_T <= upper)


def ensure_dir(path: str):
    os.makedirs(path, exist_ok=True)
