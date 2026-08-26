from __future__ import annotations

"""
Decompose selected indicators into the 5-cycle components and plot phase labels.

Inputs:
- output/cycle_representative_indicators.csv
- output/indicator_universe_latest_mapped.csv
- data/indicator_panel_monthly.parquet
- data/indicator_panel_annual.parquet

Outputs:
- output/cycle_selected/summary.csv
- output/cycle_selected/components_<id>.parquet
- output/cycle_selected/phases_<id>.parquet
- output/cycle_selected/plots/<id>_5cycle.png
"""

from dataclasses import dataclass
from pathlib import Path
import re

import numpy as np
import pandas as pd
from scipy import signal
import matplotlib.pyplot as plt


TARGET_PERIODS = [200, 100, 42, 20, 12]
BAND_TOL = 0.25
FILTER_ORDER = 2  # sosfiltfilt => zero-phase (effectively 4th order)

PHASE_LABELS = {
    0: "NA",
    1: "Expansion",
    2: "Downturn",
    3: "Contraction",
    4: "Recovery",
}
PHASE_COLORS = {
    1: "#A5D6A7",  # green-ish
    2: "#FFF59D",  # yellow
    3: "#EF9A9A",  # red-ish
    4: "#90CAF9",  # blue-ish
}


@dataclass(frozen=True)
class SeriesSpec:
    id: str
    name: str
    value_type: str
    panel_main_column: str


def sanitize(s: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", s).strip("_") or "NA"


def prepare_regular_series(s: pd.Series, max_missing_frac: float = 0.1) -> pd.Series | None:
    s = s.sort_index()
    first = s.first_valid_index()
    last = s.last_valid_index()
    if first is None or last is None:
        return None
    w = s.loc[first:last].copy()
    if len(w) < 60:
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
    if x.shape[0] < 60:
        return None
    std = float(x.std(ddof=0))
    if std == 0.0 or np.isnan(std):
        return None
    x = (x - float(x.mean())) / std
    return x


def design_bandpass_sos(period: int) -> np.ndarray | None:
    fs = 1.0
    nyq = 0.5 * fs
    f0 = 1.0 / float(period)
    low = max(1e-6, f0 * (1.0 - BAND_TOL))
    high = min(0.5 - 1e-6, f0 * (1.0 + BAND_TOL))
    if not (0 < low < high < 0.5):
        return None
    wn = [low / nyq, high / nyq]
    try:
        return signal.butter(FILTER_ORDER, wn, btype="band", output="sos")
    except Exception:
        return None


def bandpass_component(x: pd.Series, period: int) -> pd.Series:
    sos = design_bandpass_sos(period)
    if sos is None:
        return pd.Series(index=x.index, dtype="float64")
    # Need enough length for filtfilt padding and minimal stability.
    if x.shape[0] < 60:
        return pd.Series(index=x.index, dtype="float64")
    try:
        y = signal.sosfiltfilt(sos, x.values.astype("float64"))
        return pd.Series(y, index=x.index)
    except Exception:
        return pd.Series(index=x.index, dtype="float64")


def quadrant_phase(component: pd.Series, smooth: int = 3) -> pd.Series:
    """
    4-quadrant phase label using (level, slope) signs:
    - Expansion:    comp>=0 and dcomp>=0
    - Downturn:     comp>=0 and dcomp<0
    - Contraction:  comp<0  and dcomp<0
    - Recovery:     comp<0  and dcomp>=0
    """
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
    if phases.empty:
        return
    # Draw contiguous segments with same phase.
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


def plot_decomposition(name: str, x: pd.Series, comps: pd.DataFrame, phases: pd.DataFrame, out_path: Path) -> None:
    periods = [p for p in TARGET_PERIODS if p in comps.columns]
    nrows = 1 + len(periods)
    fig, axes = plt.subplots(nrows, 1, figsize=(14, 2.2 * nrows), sharex=True)
    if nrows == 1:
        axes = [axes]

    # Original (transformed) series
    ax0 = axes[0]
    ax0.plot(x.index, x.values, color="black", lw=1.0)
    ax0.axhline(0.0, color="#999999", lw=0.8)
    ax0.set_title(f"{name} (standardized transform)")

    for i, p in enumerate(periods, start=1):
        ax = axes[i]
        c = comps[p]
        ph = phases[p]
        shade_phases(ax, ph)
        ax.plot(c.index, c.values, lw=1.0, color="#1f77b4")
        ax.axhline(0.0, color="#999999", lw=0.8)
        ax.set_ylabel(f"{p}m")

    # Legend for phases (static)
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

    selected_path = out_dir / "cycle_representative_indicators.csv"
    mapping_path = out_dir / "indicator_universe_latest_mapped.csv"

    selected = pd.read_csv(selected_path)
    mapping = pd.read_csv(mapping_path)
    monthly = pd.read_parquet(data_dir / "indicator_panel_monthly.parquet")

    # Build id -> spec
    mapping = mapping.drop_duplicates(subset=["id"])
    id_to_spec: dict[str, SeriesSpec] = {}
    for r in mapping.itertuples(index=False):
        id_to_spec[str(r.id)] = SeriesSpec(
            id=str(r.id),
            name=str(r.name),
            value_type=str(r.value_type),
            panel_main_column=str(r.panel_main_column),
        )

    # Unique indicators to process (limit to the selected list)
    ids = sorted(set(selected["id"].astype(str).tolist()))

    comp_dir = out_dir / "cycle_selected"
    plot_dir = comp_dir / "plots"
    comp_dir.mkdir(parents=True, exist_ok=True)
    plot_dir.mkdir(parents=True, exist_ok=True)

    summary_rows: list[dict[str, object]] = []

    for id_ in ids:
        spec = id_to_spec.get(id_)
        if spec is None:
            continue
        col = spec.panel_main_column
        if col not in monthly.columns:
            continue

        s0 = prepare_regular_series(monthly[col])
        if s0 is None:
            continue
        x = transform_for_decompose(s0, value_type=spec.value_type)
        if x is None:
            continue

        comps: dict[int, pd.Series] = {}
        phases: dict[int, pd.Series] = {}

        for p in TARGET_PERIODS:
            c = bandpass_component(x, p)
            if c.empty or c.isna().all():
                continue
            comps[p] = c
            phases[p] = quadrant_phase(c)

        if not comps:
            continue

        comp_df = pd.DataFrame(comps)
        phase_df = pd.DataFrame(phases)

        residual = x - comp_df.sum(axis=1)
        r2 = 1.0 - float(residual.var(ddof=0) / x.var(ddof=0)) if float(x.var(ddof=0)) > 0 else np.nan
        cycles_coverage = {p: float(x.shape[0]) / float(p) for p in comp_df.columns.tolist()}

        base = sanitize(id_)
        comp_path = comp_dir / f"components_{base}.parquet"
        phase_path = comp_dir / f"phases_{base}.parquet"
        comp_df.to_parquet(comp_path)
        phase_df.to_parquet(phase_path)

        plot_path = plot_dir / f"{base}_5cycle.png"
        # Use id in plot title to avoid missing CJK font warnings; name remains in summary.csv.
        plot_decomposition(spec.id, x, comp_df, phase_df, plot_path)

        summary_rows.append(
            {
                "id": id_,
                "name": spec.name,
                "value_type": spec.value_type,
                "panel_main_column": col,
                "points_used": int(x.shape[0]),
                "start": str(x.index.min().date()),
                "end": str(x.index.max().date()),
                "components_periods": ",".join([str(p) for p in comp_df.columns.tolist()]),
                "cycles_coverage": ",".join([f"{p}:{cycles_coverage[p]:.2f}x" for p in comp_df.columns.tolist()]),
                "reconstruction_r2": r2,
                "components_path": str(comp_path.relative_to(root)),
                "phases_path": str(phase_path.relative_to(root)),
                "plot_path": str(plot_path.relative_to(root)),
            }
        )

    summary = pd.DataFrame(summary_rows).sort_values(["reconstruction_r2", "points_used"], ascending=[False, False])
    summary_path = comp_dir / "summary.csv"
    summary.to_csv(summary_path, index=False)
    print("Wrote:", summary_path)


if __name__ == "__main__":
    main()
