from __future__ import annotations

"""
Annual-frequency decomposition for long cycles (200m/100m) for selected indicators.

Why:
- Monthly panel is truncated to post-2000 by design, which is too short for 200m (≈16-18y).
- Annual panel spans ~1960-2024 for many global series; better suited to assess 200m/100m bands.

Inputs:
- output/cycle_representative_indicators.csv
- output/indicator_universe_latest_mapped.csv
- data/indicator_panel_annual.parquet

Outputs:
- output/cycle_selected_annual_long/summary.csv
- output/cycle_selected_annual_long/plots/<id>_annual_long.png
"""

from dataclasses import dataclass
from pathlib import Path
import re

import numpy as np
import pandas as pd
from scipy import signal
import matplotlib.pyplot as plt


TARGET_MONTHS = [200, 100, 42]  # annual can meaningfully handle >= ~2y; keep 42m≈3.5y as optional
BAND_TOL = 0.25
FILTER_ORDER = 2

PHASE_LABELS = {
    1: "Expansion",
    2: "Downturn",
    3: "Contraction",
    4: "Recovery",
}
PHASE_COLORS = {
    1: "#A5D6A7",
    2: "#FFF59D",
    3: "#EF9A9A",
    4: "#90CAF9",
}


@dataclass(frozen=True)
class SeriesSpec:
    id: str
    name: str
    value_type: str
    panel_main_column: str


def sanitize(s: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", s).strip("_") or "NA"


def prepare_regular_series(s: pd.Series, max_missing_frac: float = 0.15) -> pd.Series | None:
    s = s.sort_index()
    first = s.first_valid_index()
    last = s.last_valid_index()
    if first is None or last is None:
        return None
    w = s.loc[first:last].copy()
    if len(w) < 30:
        return None
    if float(w.isna().mean()) > max_missing_frac:
        return None
    return w.interpolate(method="time").ffill().bfill()


def transform_for_decompose(s: pd.Series, value_type: str) -> pd.Series | None:
    x = pd.to_numeric(s, errors="coerce")
    if value_type in {"price", "price_adj", "level"}:
        if (x > 0).all():
            x = np.log(x)
        x = x.diff()
    elif value_type == "rate_level":
        x = x.diff()
    x = x.replace([np.inf, -np.inf], np.nan).dropna()
    if x.shape[0] < 30:
        return None
    std = float(x.std(ddof=0))
    if std == 0.0 or np.isnan(std):
        return None
    x = (x - float(x.mean())) / std
    return x


def design_bandpass_sos(period_years: float) -> np.ndarray | None:
    fs = 1.0  # per year
    nyq = 0.5 * fs
    f0 = 1.0 / float(period_years)
    low = max(1e-6, f0 * (1.0 - BAND_TOL))
    high = min(0.5 - 1e-6, f0 * (1.0 + BAND_TOL))
    if not (0 < low < high < 0.5):
        return None
    wn = [low / nyq, high / nyq]
    try:
        return signal.butter(FILTER_ORDER, wn, btype="band", output="sos")
    except Exception:
        return None


def bandpass_component(x: pd.Series, period_years: float) -> pd.Series:
    sos = design_bandpass_sos(period_years)
    if sos is None or x.shape[0] < 30:
        return pd.Series(index=x.index, dtype="float64")
    try:
        y = signal.sosfiltfilt(sos, x.values.astype("float64"))
        return pd.Series(y, index=x.index)
    except Exception:
        return pd.Series(index=x.index, dtype="float64")


def quadrant_phase(component: pd.Series, smooth: int = 2) -> pd.Series:
    c = pd.to_numeric(component, errors="coerce")
    d = c.diff()
    if smooth > 1:
        d = d.rolling(smooth, min_periods=1).mean()
    out = pd.Series(index=c.index, dtype="float64")
    out[(c >= 0) & (d >= 0)] = 1
    out[(c >= 0) & (d < 0)] = 2
    out[(c < 0) & (d < 0)] = 3
    out[(c < 0) & (d >= 0)] = 4
    return out


def shade_phases(ax: plt.Axes, phases: pd.Series) -> None:
    s = phases.dropna().astype(int)
    if s.empty:
        return
    idx = s.index
    vals = s.values
    start = idx[0]
    cur = vals[0]
    for t, v in zip(idx[1:], vals[1:]):
        if v != cur:
            ax.axvspan(start, t, color=PHASE_COLORS.get(int(cur), "#EEEEEE"), alpha=0.35, lw=0)
            start = t
            cur = v
    ax.axvspan(start, idx[-1], color=PHASE_COLORS.get(int(cur), "#EEEEEE"), alpha=0.35, lw=0)


def plot(name: str, x: pd.Series, comps: pd.DataFrame, phases: pd.DataFrame, out_path: Path) -> None:
    periods = comps.columns.tolist()
    nrows = 1 + len(periods)
    fig, axes = plt.subplots(nrows, 1, figsize=(14, 2.2 * nrows), sharex=True)
    if nrows == 1:
        axes = [axes]

    ax0 = axes[0]
    ax0.plot(x.index, x.values, color="black", lw=1.0)
    ax0.axhline(0.0, color="#999999", lw=0.8)
    ax0.set_title(f"{name} (annual standardized transform)")

    for i, p in enumerate(periods, start=1):
        ax = axes[i]
        shade_phases(ax, phases[p])
        ax.plot(comps[p].index, comps[p].values, lw=1.0, color="#1f77b4")
        ax.axhline(0.0, color="#999999", lw=0.8)
        ax.set_ylabel(p)

    handles = [plt.Line2D([0], [0], color=PHASE_COLORS[k], lw=6) for k in [1, 2, 3, 4]]
    labels = [PHASE_LABELS[k] for k in [1, 2, 3, 4]]
    fig.legend(handles, labels, loc="upper right", frameon=True)

    fig.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=150)
    plt.close(fig)


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    out_dir = root / "output"
    data_dir = root / "data"

    reps = pd.read_csv(out_dir / "cycle_representative_indicators.csv")
    mapping = pd.read_csv(out_dir / "indicator_universe_latest_mapped.csv").drop_duplicates(subset=["id"])
    annual = pd.read_parquet(data_dir / "indicator_panel_annual.parquet")

    # Prefer indicators that were selected using annual scoring (cycle_freq_used == 'A'), and long-cycle groups.
    reps = reps[(reps["cycle_freq_used"] == "A") & (reps["cycle_months"].isin([200, 100]))]
    ids = sorted(set(reps["id"].astype(str).tolist()))

    id_to_spec: dict[str, SeriesSpec] = {}
    for r in mapping.itertuples(index=False):
        id_to_spec[str(r.id)] = SeriesSpec(
            id=str(r.id),
            name=str(r.name),
            value_type=str(r.value_type),
            panel_main_column=str(r.panel_main_column),
        )

    out_base = out_dir / "cycle_selected_annual_long"
    plot_dir = out_base / "plots"
    out_base.mkdir(parents=True, exist_ok=True)
    plot_dir.mkdir(parents=True, exist_ok=True)

    rows: list[dict[str, object]] = []

    for id_ in ids:
        spec = id_to_spec.get(id_)
        if spec is None:
            continue
        col = spec.panel_main_column
        if col not in annual.columns:
            continue
        s0 = prepare_regular_series(annual[col])
        if s0 is None:
            continue
        x = transform_for_decompose(s0, spec.value_type)
        if x is None:
            continue

        comps: dict[str, pd.Series] = {}
        phases: dict[str, pd.Series] = {}
        for m in TARGET_MONTHS:
            period_years = m / 12.0
            if period_years < 2.0:
                continue
            c = bandpass_component(x, period_years)
            if c.empty or c.isna().all():
                continue
            key = f"{m}m"
            comps[key] = c
            phases[key] = quadrant_phase(c)

        if not comps:
            continue

        comp_df = pd.DataFrame(comps)
        phase_df = pd.DataFrame(phases)
        residual = x - comp_df.sum(axis=1)
        r2 = 1.0 - float(residual.var(ddof=0) / x.var(ddof=0)) if float(x.var(ddof=0)) > 0 else np.nan

        plot_path = plot_dir / f"{sanitize(id_)}_annual_long.png"
        plot(spec.id, x, comp_df, phase_df, plot_path)

        rows.append(
            {
                "id": id_,
                "name": spec.name,
                "value_type": spec.value_type,
                "panel_main_column": col,
                "points_used": int(x.shape[0]),
                "start": str(x.index.min().date()),
                "end": str(x.index.max().date()),
                "components": ",".join(comp_df.columns.tolist()),
                "reconstruction_r2": r2,
                "plot_path": str(plot_path.relative_to(root)),
            }
        )

    summary = pd.DataFrame(rows).sort_values(["reconstruction_r2", "points_used"], ascending=[False, False])
    summary_path = out_base / "summary.csv"
    summary.to_csv(summary_path, index=False)
    print("Wrote:", summary_path)


if __name__ == "__main__":
    main()

