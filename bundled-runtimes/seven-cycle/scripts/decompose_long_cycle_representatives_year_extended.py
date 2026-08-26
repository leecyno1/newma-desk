from __future__ import annotations

"""
Decompose selected long-cycle representatives (200m/100m) on the annual
year-index extended panel (1800+), and plot phase labels.

Inputs:
- output/long_cycle_representatives_year_extended.csv
- data/indicator_panel_annual_year_extended.parquet

Outputs:
- output/long_cycle_selected_year_extended/summary.csv
- output/long_cycle_selected_year_extended/components_<id>.parquet
- output/long_cycle_selected_year_extended/phases_<id>.parquet
- output/long_cycle_selected_year_extended/plots/<id>_annual_long.png
"""

from dataclasses import dataclass
from pathlib import Path
import re

import numpy as np
import pandas as pd
from scipy import signal
import matplotlib.pyplot as plt


TARGET_MONTHS = [200, 100]
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
    column: str


def sanitize(s: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", s).strip("_") or "NA"


def prepare_regular_series_year(s: pd.Series, *, max_missing_frac: float = 0.15, min_points: int = 80) -> pd.Series | None:
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
    return w.interpolate(method="linear").ffill().bfill()


def transform_for_decompose(s: pd.Series, value_type: str) -> pd.Series | None:
    x = pd.to_numeric(s, errors="coerce")
    if value_type in {"price", "price_adj", "level"}:
        if (x > 0).all():
            x = np.log(x)
        x = x.diff()
    elif value_type == "rate_level":
        x = x.diff()
    x = x.replace([np.inf, -np.inf], np.nan).dropna()
    if x.shape[0] < 40:
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
    if sos is None or x.shape[0] < 40:
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


def plot(spec: SeriesSpec, x: pd.Series, comps: pd.DataFrame, phases: pd.DataFrame, out_path: Path) -> None:
    cols = [m for m in TARGET_MONTHS if m in comps.columns]
    nrows = 1 + len(cols)
    fig, axes = plt.subplots(nrows, 1, figsize=(14, 2.4 * nrows), sharex=True)
    if nrows == 1:
        axes = [axes]

    ax0 = axes[0]
    ax0.plot(x.index, x.values, color="black", lw=1.0)
    ax0.axhline(0.0, color="#999999", lw=0.8)
    ax0.set_title(f"{spec.id} (annual standardized transform)")

    for i, m in enumerate(cols, start=1):
        ax = axes[i]
        shade_phases(ax, phases[m])
        ax.plot(comps[m].index, comps[m].values, lw=1.0, color="#1f77b4")
        ax.axhline(0.0, color="#999999", lw=0.8)
        ax.set_ylabel(f"{m}m")

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

    reps_path = out_dir / "long_cycle_representatives_year_extended.csv"
    panel_path = data_dir / "indicator_panel_annual_year_extended.parquet"
    if not reps_path.exists():
        raise FileNotFoundError(reps_path)
    if not panel_path.exists():
        raise FileNotFoundError(panel_path)

    reps = pd.read_csv(reps_path)
    panel = pd.read_parquet(panel_path)
    if panel.index.name != "year":
        panel.index = pd.Index(pd.to_numeric(panel.index, errors="coerce").astype("Int64"), name="year")
    panel = panel.sort_index()

    # Unique series by column (some ids can repeat across cycles)
    reps = reps.drop_duplicates(subset=["column"]).copy()
    specs: list[SeriesSpec] = []
    for r in reps.itertuples(index=False):
        specs.append(
            SeriesSpec(
                id=str(getattr(r, "id")),
                name=str(getattr(r, "name")),
                value_type=str(getattr(r, "value_type")),
                column=str(getattr(r, "column")),
            )
        )

    out_base = out_dir / "long_cycle_selected_year_extended"
    plot_dir = out_base / "plots"
    out_base.mkdir(parents=True, exist_ok=True)
    plot_dir.mkdir(parents=True, exist_ok=True)

    rows: list[dict[str, object]] = []

    for spec in specs:
        col = spec.column
        if col not in panel.columns:
            continue
        s0 = prepare_regular_series_year(panel[col])
        if s0 is None:
            continue
        x = transform_for_decompose(s0, spec.value_type)
        if x is None:
            continue

        comps: dict[int, pd.Series] = {}
        phases: dict[int, pd.Series] = {}
        for m in TARGET_MONTHS:
            period_years = m / 12.0
            c = bandpass_component(x, period_years)
            if c.empty or c.isna().all():
                continue
            comps[m] = c
            phases[m] = quadrant_phase(c)

        if not comps:
            continue

        comp_df = pd.DataFrame(comps)
        phase_df = pd.DataFrame(phases)
        residual = x - comp_df.sum(axis=1)
        r2 = 1.0 - float(residual.var(ddof=0) / x.var(ddof=0)) if float(x.var(ddof=0)) > 0 else np.nan

        base = sanitize(spec.id)
        comp_path = out_base / f"components_{base}.parquet"
        phase_path = out_base / f"phases_{base}.parquet"
        comp_df.to_parquet(comp_path)
        phase_df.to_parquet(phase_path)

        plot_path = plot_dir / f"{base}_annual_long.png"
        plot(spec, x, comp_df, phase_df, plot_path)

        rows.append(
            {
                "id": spec.id,
                "name": spec.name,
                "value_type": spec.value_type,
                "column": col,
                "points_used": int(x.shape[0]),
                "start_year": int(pd.to_numeric(x.index, errors="coerce").min()),
                "end_year": int(pd.to_numeric(x.index, errors="coerce").max()),
                "components": ",".join([str(c) for c in comp_df.columns.tolist()]),
                "reconstruction_r2": r2,
                "components_path": str(comp_path.relative_to(root)),
                "phases_path": str(phase_path.relative_to(root)),
                "plot_path": str(plot_path.relative_to(root)),
            }
        )

    summary = pd.DataFrame(rows).sort_values(["reconstruction_r2", "points_used"], ascending=[False, False])
    summary_path = out_base / "summary.csv"
    summary.to_csv(summary_path, index=False)
    print("Wrote:", summary_path)


if __name__ == "__main__":
    main()

