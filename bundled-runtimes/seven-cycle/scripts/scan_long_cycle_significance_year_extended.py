from __future__ import annotations

"""
Scan long-cycle significance on the *annual year-index extended* panel (1800+).

We specifically target:
- 200 months  (~16.7 years)
- 100 months  (~8.3 years)

Score = band-power ratio around the target band using Welch PSD on transformed series:
- price/level/index: log-diff (growth/returns); fall back to diff if non-positive
- rate_level: first difference
- return/rate_yoy/rate_mom: as-is

Inputs:
- data/indicator_panel_annual_year_extended.parquet
- output/indicator_universe_latest_mapped.csv (for value_type metadata, when available)

Outputs:
- output/long_cycle_bandpower_scores_year_extended.csv
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

    @property
    def years(self) -> float:
        return float(self.months) / 12.0

    def band(self) -> tuple[float, float]:
        f0 = 1.0 / self.years  # cycles per year
        low = max(1e-6, f0 * (1.0 - self.band_tol))
        high = min(0.5 - 1e-6, f0 * (1.0 + self.band_tol))
        return low, high


TARGETS = [TargetCycle(200), TargetCycle(100)]


def prepare_regular_series_year(s: pd.Series, *, max_missing_frac: float = 0.15, min_points: int = 60) -> pd.Series | None:
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


def infer_value_type(col: str) -> str:
    c = str(col).upper()
    if "YOY" in c:
        return "rate_yoy"
    if any(k in c for k in ["PCT", "RATE", "YIELD", "UNEMP", "INFLATION"]):
        return "rate_level"
    if any(k in c for k in ["RET", "RETURN"]):
        return "return"
    return "level"


def transform_for_psd(s: pd.Series, value_type: str) -> pd.Series | None:
    x = pd.to_numeric(s, errors="coerce")
    if x.dropna().shape[0] < 30:
        return None

    if value_type in {"price", "price_adj", "level"}:
        # Prefer log-diff for strictly positive series
        if (x > 0).all():
            x = np.log(x)
        x = x.diff()
    elif value_type == "rate_level":
        x = x.diff()
    # return / rate_yoy / rate_mom: keep as-is

    x = x.replace([np.inf, -np.inf], np.nan).dropna()
    if x.shape[0] < 30:
        return None
    std = float(x.std(ddof=0))
    if std == 0.0 or np.isnan(std):
        return None
    x = (x - float(x.mean())) / std
    return x


def welch_bandpower_ratio(x: np.ndarray, *, fs: float, low: float, high: float) -> float:
    if x.size < 30:
        return float("nan")
    nperseg = int(min(256, x.size))
    if nperseg < 16:
        return float("nan")
    f, pxx = signal.welch(x, fs=fs, window="hann", nperseg=nperseg, detrend="constant", scaling="density")
    if len(f) < 3:
        return float("nan")
    mask_total = f > 0  # exclude DC
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
    data_dir = root / "data"
    out_dir = root / "output"
    out_dir.mkdir(parents=True, exist_ok=True)

    panel_path = data_dir / "indicator_panel_annual_year_extended.parquet"
    mapping_path = out_dir / "indicator_universe_latest_mapped.csv"
    if not panel_path.exists():
        raise FileNotFoundError(panel_path)

    panel = pd.read_parquet(panel_path)
    if panel.index.name != "year":
        panel.index = pd.Index(pd.to_numeric(panel.index, errors="coerce").astype("Int64"), name="year")
    panel = panel.sort_index()

    mapping = pd.DataFrame()
    col_meta: dict[str, dict[str, object]] = {}
    if mapping_path.exists():
        mapping = pd.read_csv(mapping_path)
        # Map panel_main_column -> meta
        for r in mapping.itertuples(index=False):
            col = str(getattr(r, "panel_main_column"))
            col_meta[col] = {
                "id": str(getattr(r, "id")),
                "name": str(getattr(r, "name")),
                "universe_category": str(getattr(r, "universe_category")),
                "primary_source": str(getattr(r, "primary_source")),
                "backend": str(getattr(r, "backend")),
                "base_freq": str(getattr(r, "base_freq")),
                "value_type": str(getattr(r, "value_type")),
            }

    rows: list[dict[str, object]] = []
    fs = 1.0  # annual

    for col in panel.columns:
        s0 = panel[col]
        s1 = prepare_regular_series_year(s0)
        if s1 is None:
            continue

        meta = col_meta.get(col)
        value_type = str(meta.get("value_type")) if meta else infer_value_type(col)
        x = transform_for_psd(s1, value_type=value_type)
        if x is None:
            continue

        start_year = int(pd.to_numeric(x.index, errors="coerce").min())
        end_year = int(pd.to_numeric(x.index, errors="coerce").max())

        for tgt in TARGETS:
            low, high = tgt.band()
            score = welch_bandpower_ratio(x.values.astype("float64"), fs=fs, low=low, high=high)
            if not np.isfinite(score):
                continue
            rows.append(
                {
                    "freq": "A",
                    "cycle_months": tgt.months,
                    "cycle_years": tgt.years,
                    "column": str(col),
                    "id": (meta.get("id") if meta else str(col)),
                    "name": (meta.get("name") if meta else str(col)),
                    "universe_category": (meta.get("universe_category") if meta else "LongHistory"),
                    "primary_source": (meta.get("primary_source") if meta else "long_history"),
                    "backend": (meta.get("backend") if meta else "long_history"),
                    "base_freq": (meta.get("base_freq") if meta else "A"),
                    "value_type": value_type,
                    "n_points": int(x.shape[0]),
                    "start_year": start_year,
                    "end_year": end_year,
                    "bandpower_ratio": float(score),
                }
            )

    out = pd.DataFrame(rows)
    out_path = out_dir / "long_cycle_bandpower_scores_year_extended.csv"
    if not out.empty:
        out = out.sort_values(["cycle_months", "bandpower_ratio", "n_points"], ascending=[True, False, False])
    out.to_csv(out_path, index=False)
    print("Wrote:", out_path)


if __name__ == "__main__":
    main()

