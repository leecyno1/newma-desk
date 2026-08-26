from __future__ import annotations

"""
Scan cycle significance across the indicator universe.

We score each indicator by band-power ratio around target cycle lengths
(200/100/42/20/12 months) using Welch PSD on *transformed* series:

- price/level/index: log-diff (returns/growth)
- rate_level: first difference
- return/rate_yoy/rate_mom: as-is

Outputs:
- output/cycle_bandpower_scores_monthly.csv
- output/cycle_bandpower_scores_annual.csv
"""

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import signal


@dataclass(frozen=True)
class TargetCycle:
    months: int
    band_tol: float = 0.25  # +/- 25%

    def band_cpm(self, sample_rate: float) -> tuple[float, float]:
        """
        Return (low, high) cutoff in cycles per sample.
        sample_rate is 1.0 for monthly (per month) or 1.0 for annual (per year).
        """
        # Convert months to sampling-period units.
        period = float(self.months)
        if sample_rate == 1.0:  # interpreted by caller: monthly -> months, annual -> years mapping done outside
            f0 = 1.0 / period
        else:
            # Not used currently.
            f0 = sample_rate / period
        low = f0 * (1.0 - self.band_tol)
        high = f0 * (1.0 + self.band_tol)
        return max(low, 1e-6), min(high, 0.5 - 1e-6)


TARGETS = [TargetCycle(200), TargetCycle(100), TargetCycle(42), TargetCycle(20), TargetCycle(12)]


def prepare_regular_series(s: pd.Series, max_missing_frac: float = 0.1) -> pd.Series | None:
    s = s.sort_index()
    first = s.first_valid_index()
    last = s.last_valid_index()
    if first is None or last is None:
        return None
    w = s.loc[first:last].copy()
    if len(w) < 24:
        return None
    miss = float(w.isna().mean())
    if miss > max_missing_frac:
        return None
    w = w.interpolate(method="time").ffill().bfill()
    return w


def transform_for_psd(s: pd.Series, value_type: str) -> pd.Series | None:
    x = pd.to_numeric(s, errors="coerce")
    if x.dropna().shape[0] < 24:
        return None

    if value_type in {"price", "price_adj", "level"}:
        x_pos = (x > 0).all()
        if x_pos:
            x = np.log(x)
        x = x.diff()
    elif value_type == "rate_level":
        x = x.diff()
    # return / rate_yoy / rate_mom: keep as-is

    x = x.replace([np.inf, -np.inf], np.nan).dropna()
    if x.shape[0] < 24:
        return None
    std = float(x.std(ddof=0))
    if std == 0.0 or np.isnan(std):
        return None
    x = (x - float(x.mean())) / std
    return x


def welch_bandpower_ratio(x: np.ndarray, fs: float, low: float, high: float) -> float:
    if x.size < 24:
        return float("nan")
    nperseg = int(min(256, x.size))
    if nperseg < 16:
        return float("nan")
    f, pxx = signal.welch(x, fs=fs, window="hann", nperseg=nperseg, detrend="constant", scaling="density")
    if len(f) < 3:
        return float("nan")
    # Exclude DC component
    mask_total = f > 0
    total = float(np.trapezoid(pxx[mask_total], f[mask_total]))
    if total <= 0 or np.isnan(total):
        return float("nan")
    mask_band = (f >= low) & (f <= high)
    band = float(np.trapezoid(pxx[mask_band], f[mask_band]))
    if band < 0 or np.isnan(band):
        return float("nan")
    return band / total


def scan(panel: pd.DataFrame, mapping: pd.DataFrame, freq_label: str, period_unit: str) -> pd.DataFrame:
    """
    period_unit:
    - 'month'  => TargetCycle.months are interpreted as months (monthly panel)
    - 'year'   => TargetCycle.months are converted to years = months/12 (annual panel)
    """
    out_rows: list[dict[str, object]] = []
    for row in mapping.itertuples(index=False):
        col = getattr(row, "panel_main_column")
        value_type = getattr(row, "value_type")
        if col not in panel.columns:
            continue
        s0 = panel[col]
        s1 = prepare_regular_series(s0)
        if s1 is None:
            continue
        x = transform_for_psd(s1, value_type=value_type)
        if x is None:
            continue

        # Determine sampling unit conversion.
        # We keep fs=1.0. For annual we convert months->years.
        fs = 1.0
        for tgt in TARGETS:
            if period_unit == "month":
                period = float(tgt.months)
            else:
                period = float(tgt.months) / 12.0
                if period < 2.0:
                    # Annual data cannot resolve ~1y seasonal cycle meaningfully.
                    continue

            low = (1.0 / period) * (1.0 - tgt.band_tol)
            high = (1.0 / period) * (1.0 + tgt.band_tol)
            low = max(low, 1e-6)
            high = min(high, 0.5 - 1e-6)
            if not (0 < low < high < 0.5):
                continue
            score = welch_bandpower_ratio(x.values.astype("float64"), fs=fs, low=low, high=high)
            out_rows.append(
                {
                    "freq": freq_label,
                    "cycle_months": tgt.months,
                    "cycle_unit_period": period,
                    "id": getattr(row, "id"),
                    "name": getattr(row, "name"),
                    "universe_category": getattr(row, "universe_category"),
                    "primary_source": getattr(row, "primary_source"),
                    "backend": getattr(row, "backend"),
                    "base_freq": getattr(row, "base_freq"),
                    "value_type": value_type,
                    "panel_main_column": col,
                    "n_points": int(x.shape[0]),
                    "start": str(x.index.min().date()),
                    "end": str(x.index.max().date()),
                    "bandpower_ratio": float(score) if score == score else np.nan,
                }
            )
    return pd.DataFrame(out_rows)


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    out_dir = root / "output"
    out_dir.mkdir(parents=True, exist_ok=True)

    mapping = pd.read_csv(out_dir / "indicator_universe_latest_mapped.csv")
    monthly = pd.read_parquet(root / "data" / "indicator_panel_monthly.parquet")
    annual = pd.read_parquet(root / "data" / "indicator_panel_annual.parquet")

    # Monthly scan: best for 42/20/12. (100/200 will be short-window)
    df_m = scan(monthly, mapping, freq_label="M", period_unit="month")
    df_m.to_csv(out_dir / "cycle_bandpower_scores_monthly.csv", index=False)

    # Annual scan: best for 200/100 (in years).
    df_a = scan(annual, mapping, freq_label="A", period_unit="year")
    df_a.to_csv(out_dir / "cycle_bandpower_scores_annual.csv", index=False)

    print("Wrote:", out_dir / "cycle_bandpower_scores_monthly.csv")
    print("Wrote:", out_dir / "cycle_bandpower_scores_annual.csv")


if __name__ == "__main__":
    main()
