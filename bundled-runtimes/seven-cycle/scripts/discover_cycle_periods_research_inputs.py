from __future__ import annotations

"""
Discover candidate cycle periods from governed research inputs.

Purpose:
- Move from fixed prior cycle lengths toward data-driven candidate periods.
- Aggregate spectral evidence separately on:
  - annual long panel (`1700-2024`)
  - monthly macro panel (`2000-2025`)

Outputs:
- output/cycle_discovery_annual_long_profile.csv
- output/cycle_discovery_monthly_macro_profile.csv
- output/cycle_discovery_consensus_peaks.csv
- output/cycle_discovery_report.md
"""

from dataclasses import dataclass
from pathlib import Path
import warnings

import numpy as np
import pandas as pd
from scipy import signal
from scipy.sparse import SparseEfficiencyWarning
import statsmodels.api as sm


ROOT = Path(__file__).resolve().parents[1]

warnings.filterwarnings("ignore", category=SparseEfficiencyWarning)

ANNUAL_PANEL = ROOT / "data" / "research_input_annual_long.parquet"
MONTHLY_PANEL = ROOT / "data" / "research_input_monthly_macro.parquet"

OUT_ANNUAL = ROOT / "output" / "cycle_discovery_annual_long_profile.csv"
OUT_MONTHLY = ROOT / "output" / "cycle_discovery_monthly_macro_profile.csv"
OUT_PEAKS = ROOT / "output" / "cycle_discovery_consensus_peaks.csv"
OUT_MD = ROOT / "output" / "cycle_discovery_report.md"


@dataclass(frozen=True)
class PanelSpec:
    name: str
    path: Path
    freq: str
    min_points: int
    period_min: int
    period_max: int
    hp_lambda: float | None


PANELS = [
    PanelSpec(
        name="annual_long",
        path=ANNUAL_PANEL,
        freq="A",
        min_points=120,
        period_min=6,   # years
        period_max=30,  # years
        hp_lambda=100.0,
    ),
    PanelSpec(
        name="monthly_macro",
        path=MONTHLY_PANEL,
        freq="M",
        min_points=120,
        period_min=12,  # months
        period_max=60,  # months
        hp_lambda=None,
    ),
]


def infer_value_type(col: str) -> str:
    c = str(col).upper()
    if "RET" in c:
        return "return"
    if "YOY" in c or "GROWTH_PCT" in c:
        return "rate_yoy"
    if "MOM" in c:
        return "rate_mom"
    if "UNEMPLOY" in c:
        return "level"
    if c.endswith("_PCT") or "YIELD" in c or "IR_LONG" in c or "IR_SHORT" in c or "BANK_RATE" in c:
        return "rate_level"
    return "level"


def prepare_series(s: pd.Series, freq: str, min_points: int) -> pd.Series | None:
    s = s.sort_index()
    if freq == "M":
        s = s.groupby(s.index.to_period("M")).last()
        s.index = s.index.to_timestamp("M")
        first = s.first_valid_index()
        last = s.last_valid_index()
        if first is None or last is None:
            return None
        idx = pd.date_range(first, last, freq="ME")
        w = s.reindex(idx)
    else:
        first = s.first_valid_index()
        last = s.last_valid_index()
        if first is None or last is None:
            return None
        idx = pd.Index(range(int(first), int(last) + 1), name="year")
        w = s.reindex(idx)

    if len(w) < min_points:
        return None
    if float(w.isna().mean()) > 0.2:
        return None

    if freq == "M":
        return w.interpolate(method="time").ffill().bfill()
    return w.interpolate(method="linear").ffill().bfill()


def zscore(x: pd.Series) -> pd.Series | None:
    x = pd.to_numeric(x, errors="coerce").replace([np.inf, -np.inf], np.nan).dropna()
    if x.shape[0] < 60:
        return None
    sd = float(x.std(ddof=0))
    if sd == 0.0 or np.isnan(sd):
        return None
    return (x - float(x.mean())) / sd


def transform_series(s: pd.Series, value_type: str, freq: str, hp_lambda: float | None) -> pd.Series | None:
    x = pd.to_numeric(s, errors="coerce").replace([np.inf, -np.inf], np.nan).dropna()
    if x.shape[0] < 60:
        return None

    y = x.astype("float64")
    if freq == "A":
        if value_type in {"level", "price", "price_adj"} and (y > 0).all():
            y = np.log(y)
        if hp_lambda is not None:
            try:
                cycle, _trend = sm.tsa.filters.hpfilter(y.values, lamb=hp_lambda)
                y = pd.Series(cycle, index=y.index)
            except Exception:
                y = y - y.rolling(10, min_periods=1).mean()
        return zscore(y)

    if value_type in {"price", "price_adj", "level"}:
        if (y > 0).all():
            y = np.log(y)
        y = y.diff()
    elif value_type == "rate_level":
        y = y.diff()
    return zscore(y)


def welch_periodogram(x: pd.Series) -> tuple[np.ndarray, np.ndarray]:
    vals = pd.to_numeric(x, errors="coerce").dropna().values.astype("float64")
    if vals.size < 60:
        return np.array([]), np.array([])
    nperseg = int(min(256, vals.size))
    if nperseg < 16:
        return np.array([]), np.array([])
    f, pxx = signal.welch(vals, fs=1.0, window="hann", nperseg=nperseg, detrend="constant", scaling="density")
    mask = f > 0
    return f[mask], pxx[mask]


def power_at_periods(freqs: np.ndarray, pxx: np.ndarray, periods: np.ndarray) -> np.ndarray:
    if freqs.size == 0 or pxx.size == 0:
        return np.full(periods.shape, np.nan, dtype="float64")
    target_freqs = 1.0 / periods
    out = np.full(periods.shape, np.nan, dtype="float64")
    for i, tf in enumerate(target_freqs):
        idx = int(np.argmin(np.abs(freqs - tf)))
        out[i] = float(pxx[idx])
    total = np.nansum(out)
    if np.isfinite(total) and total > 0:
        out = out / total
    return out


def summarize_panel(spec: PanelSpec) -> tuple[pd.DataFrame, pd.DataFrame]:
    panel = pd.read_parquet(spec.path)
    periods = np.arange(spec.period_min, spec.period_max + 1, dtype="float64")

    profile_rows: list[dict[str, object]] = []
    peak_rows: list[dict[str, object]] = []
    all_profiles: list[pd.Series] = []

    for col in panel.columns:
        vt = infer_value_type(col)
        if vt == "return":
            continue
        s0 = prepare_series(panel[col], freq=spec.freq, min_points=spec.min_points)
        if s0 is None:
            continue
        x = transform_series(s0, value_type=vt, freq=spec.freq, hp_lambda=spec.hp_lambda)
        if x is None:
            continue
        freqs, pxx = welch_periodogram(x)
        if freqs.size == 0:
            continue
        prof = power_at_periods(freqs, pxx, periods)
        prof_s = pd.Series(prof, index=periods, name=col)
        all_profiles.append(prof_s)

        peaks, props = signal.find_peaks(prof, prominence=np.nanpercentile(prof[np.isfinite(prof)], 75))
        prominences = props.get("prominences", np.full(len(peaks), np.nan))
        for idx, prom in zip(peaks, prominences):
            peak_rows.append(
                {
                    "panel": spec.name,
                    "column": col,
                    "value_type": vt,
                    "n_points": int(x.shape[0]),
                    "period": float(periods[idx]),
                    "power": float(prof[idx]),
                    "prominence": float(prom),
                }
            )

    if not all_profiles:
        return pd.DataFrame(), pd.DataFrame()

    mat = pd.concat(all_profiles, axis=1)
    prof_df = pd.DataFrame(
        {
            "panel": spec.name,
            "period": mat.index.astype(float),
            "series_count": int(mat.shape[1]),
            "mean_power": mat.mean(axis=1).values,
            "median_power": mat.median(axis=1).values,
            "p75_power": mat.quantile(0.75, axis=1).values,
            "top_decile_share": (mat.ge(mat.quantile(0.9, axis=0), axis=1)).mean(axis=1).values,
        }
    )

    peak_df = pd.DataFrame(peak_rows)
    if peak_df.empty:
        return prof_df, peak_df

    peak_summary = (
        peak_df.groupby(["panel", "period"], as_index=False)
        .agg(
            peak_count=("column", "size"),
            mean_peak_power=("power", "mean"),
            median_peak_power=("power", "median"),
            mean_prominence=("prominence", "mean"),
        )
        .sort_values(["panel", "peak_count", "mean_prominence", "mean_peak_power"], ascending=[True, False, False, False])
    )
    return prof_df, peak_summary


def find_consensus_peaks(profile: pd.DataFrame, top_n: int = 5) -> pd.DataFrame:
    out_rows: list[dict[str, object]] = []
    for panel_name, sub in profile.groupby("panel"):
        x = sub.sort_values("period").reset_index(drop=True)
        y = x["mean_power"].values.astype("float64")
        peaks, props = signal.find_peaks(y, prominence=np.nanpercentile(y[np.isfinite(y)], 60))
        prominences = props.get("prominences", np.full(len(peaks), np.nan))
        for idx, prom in zip(peaks, prominences):
            row = x.iloc[idx]
            out_rows.append(
                {
                    "panel": panel_name,
                    "period": float(row["period"]),
                    "mean_power": float(row["mean_power"]),
                    "median_power": float(row["median_power"]),
                    "p75_power": float(row["p75_power"]),
                    "top_decile_share": float(row["top_decile_share"]),
                    "prominence": float(prom),
                }
            )
    out = pd.DataFrame(out_rows)
    if out.empty:
        return out
    return out.sort_values(["panel", "prominence", "mean_power"], ascending=[True, False, False]).groupby("panel", as_index=False).head(top_n)


def main() -> None:
    profiles: list[pd.DataFrame] = []
    peaks: list[pd.DataFrame] = []

    for spec in PANELS:
        prof, peak = summarize_panel(spec)
        if prof.empty:
            continue
        profiles.append(prof)
        peaks.append(peak)
        if spec.name == "annual_long":
            prof.to_csv(OUT_ANNUAL, index=False)
        else:
            prof.to_csv(OUT_MONTHLY, index=False)

    if not profiles:
        raise RuntimeError("No cycle discovery profiles were produced.")

    profile_all = pd.concat(profiles, ignore_index=True)
    peaks_all = pd.concat(peaks, ignore_index=True) if peaks else pd.DataFrame()
    consensus = find_consensus_peaks(profile_all, top_n=6)
    consensus.to_csv(OUT_PEAKS, index=False)

    lines: list[str] = []
    lines.append("# Cycle Discovery Report")
    lines.append("")
    lines.append("Method:")
    lines.append("- Annual panel: `research_input_annual_long.parquet`, window `1700-2024`, HP-cycle + Welch PSD, search range `6-30` years.")
    lines.append("- Monthly panel: `research_input_monthly_macro.parquet`, window `2000-2025`, transformed growth/diff series + Welch PSD, search range `12-60` months.")
    lines.append("- Consensus peaks are found from local maxima of cross-series mean power profiles.")
    lines.append("")
    lines.append("## Consensus peaks")
    lines.append("")
    if consensus.empty:
        lines.append("(empty)")
    else:
        lines.append(consensus.to_markdown(index=False))
    lines.append("")

    for panel_name, sub in profile_all.groupby("panel"):
        lines.append(f"## {panel_name} profile top periods")
        lines.append("")
        top = sub.sort_values(["mean_power", "top_decile_share"], ascending=[False, False]).head(12)
        lines.append(top.to_markdown(index=False))
        lines.append("")
        if not peaks_all.empty:
            panel_peaks = peaks_all[peaks_all["panel"] == panel_name].head(12)
            lines.append(f"## {panel_name} peak-count ranking")
            lines.append("")
            lines.append(panel_peaks.to_markdown(index=False))
            lines.append("")

    OUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print("Wrote:", OUT_ANNUAL)
    print("Wrote:", OUT_MONTHLY)
    print("Wrote:", OUT_PEAKS)
    print("Wrote:", OUT_MD)


if __name__ == "__main__":
    main()
