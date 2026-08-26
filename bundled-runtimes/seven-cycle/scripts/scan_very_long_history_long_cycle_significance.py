from __future__ import annotations

"""
Scan long-cycle significance on the *very* long-history annual panel (year index).

Purpose (formal research):
- Extend annual sample earlier than 1800 (BoE millennium + MPD) to improve long-cycle identification.
- Targets: 200m (~16.7y), 100m (~8.3y)

Method:
- Preprocess: contiguous window (first..last), interpolate small gaps.
- Transform: (optional log for positive levels) -> HP filter (annual lamb=100) -> z-score.
- Welch PSD -> bandpower ratio around target frequencies (±25% tolerance).

Inputs:
- data/research_input_annual_long.parquet

Outputs:
- output/cycle_bandpower_scores_annual_very_long_history_long.csv
"""

from dataclasses import dataclass
from pathlib import Path
import re
import warnings

import numpy as np
import pandas as pd
from scipy import signal
import statsmodels.api as sm


warnings.filterwarnings("ignore")


@dataclass(frozen=True)
class TargetCycle:
    months: int
    band_tol: float = 0.25  # +/- 25%

    @property
    def years(self) -> float:
        return float(self.months) / 12.0


TARGETS = [TargetCycle(200), TargetCycle(100)]


def _infer_source(col: str) -> str:
    if col.startswith("UK_BOE_") or col.startswith("UK_CPI_") or col.startswith("UK_GDP_"):
        return "boe/wb"
    if col.startswith("UK_OECD_") or col.startswith("EA_OECD_") or col.endswith("_OECD_CPI_YOY_PCT"):
        return "oecd(openbb)"
    if col.startswith("US_SHILLER_"):
        return "shiller"
    if col.startswith("MPD_"):
        return "maddison_mpd2020"
    return "unknown"


def _infer_value_type(col: str) -> str:
    c = col.upper()
    if "RET" in c:
        return "return"
    if "YOY" in c:
        return "rate_yoy"
    if "UNEMPLOY" in c:
        return "level"
    if c.endswith("_PCT") or "YIELD" in c or "IR_LONG" in c or "IR_SHORT" in c or "BANK_RATE" in c:
        return "rate_level"
    return "level"


def _slug(s: str, max_len: int = 80) -> str:
    s = str(s).strip()
    s = re.sub(r"[^A-Za-z0-9]+", "_", s).strip("_") or "NA"
    return s[:max_len]


def prepare_regular_series(s: pd.Series, *, min_points: int = 80, max_missing_frac: float = 0.2) -> pd.Series | None:
    s = s.sort_index()
    first = s.first_valid_index()
    last = s.last_valid_index()
    if first is None or last is None:
        return None
    w = s.loc[first:last].copy()
    if len(w) < min_points:
        return None
    if float(w.isna().mean()) > max_missing_frac:
        return None
    w = w.interpolate(method="linear").ffill().bfill()
    return w


def _zscore(x: pd.Series) -> pd.Series | None:
    x = pd.to_numeric(x, errors="coerce").replace([np.inf, -np.inf], np.nan).dropna()
    if x.shape[0] < 60:
        return None
    sd = float(x.std(ddof=0))
    if sd == 0.0 or np.isnan(sd):
        return None
    return (x - float(x.mean())) / sd


def transform_for_long_cycle(s: pd.Series, value_type: str, *, hp_lamb: float = 100.0) -> pd.Series | None:
    x = pd.to_numeric(s, errors="coerce").replace([np.inf, -np.inf], np.nan).dropna()
    if x.shape[0] < 80:
        return None

    y = x.astype("float64")
    if value_type in {"level", "price", "price_adj"}:
        if (y > 0).all():
            y = np.log(y)

    try:
        cycle, _trend = sm.tsa.filters.hpfilter(y.values, lamb=hp_lamb)
        y = pd.Series(cycle, index=y.index)
    except Exception:
        y = y - y.rolling(10, min_periods=1).mean()

    return _zscore(y)


def welch_bandpower_ratio(x: np.ndarray, *, low: float, high: float) -> float:
    x = np.asarray(x, dtype="float64")
    x = x[np.isfinite(x)]
    if x.size < 60:
        return float("nan")
    fs = 1.0  # per year
    nperseg = int(min(256, x.size))
    if nperseg < 16:
        return float("nan")
    f, pxx = signal.welch(x, fs=fs, window="hann", nperseg=nperseg, detrend="constant", scaling="density")
    if len(f) < 3:
        return float("nan")
    mask_total = f > 0
    total = float(np.trapezoid(pxx[mask_total], f[mask_total]))
    if total <= 0 or np.isnan(total):
        return float("nan")
    mask_band = (f >= low) & (f <= high)
    band = float(np.trapezoid(pxx[mask_band], f[mask_band]))
    if band < 0 or np.isnan(band):
        return float("nan")
    return band / total


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    panel_path = root / "data" / "research_input_annual_long.parquet"
    if not panel_path.exists():
        raise FileNotFoundError(panel_path)
    panel = pd.read_parquet(panel_path)

    rows: list[dict[str, object]] = []
    for col in panel.columns:
        s0 = prepare_regular_series(panel[col])
        if s0 is None:
            continue
        value_type = _infer_value_type(col)
        x = transform_for_long_cycle(s0, value_type=value_type)
        if x is None:
            continue

        start = int(x.index.min())
        end = int(x.index.max())
        n_points = int(x.shape[0])
        for tgt in TARGETS:
            period_years = tgt.years
            f0 = 1.0 / period_years
            low = max(1e-6, f0 * (1.0 - tgt.band_tol))
            high = min(0.5 - 1e-6, f0 * (1.0 + tgt.band_tol))
            if not (0 < low < high < 0.5):
                continue
            score = welch_bandpower_ratio(x.values, low=low, high=high)
            rows.append(
                {
                    "freq": "A_VERY_LONG",
                    "cycle_months": int(tgt.months),
                    "cycle_years": float(period_years),
                    "column": col,
                    "id": _slug(col),
                    "name": col,
                    "source": _infer_source(col),
                    "value_type": value_type,
                    "n_points": n_points,
                    "start_year": start,
                    "end_year": end,
                    "bandpower_ratio": score,
                }
            )

    out = pd.DataFrame(rows)
    out_path = root / "output" / "cycle_bandpower_scores_annual_very_long_history_long.csv"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(out_path, index=False)
    print("Wrote:", out_path)


if __name__ == "__main__":
    main()
