from __future__ import annotations

"""
Decompose selected short-cycle macro indicators into 42m/20m components
and plot phase labels.

Inputs:
- output/cycle_representative_indicators_short_macro.csv
- data/research_input_monthly_macro.parquet

Outputs:
- output/short_cycle_macro/summary.csv
- output/short_cycle_macro/components_<id>.parquet
- output/short_cycle_macro/phases_<id>.parquet
- output/short_cycle_macro/plots/<id>_42_20.png
"""

from dataclasses import dataclass
from pathlib import Path
import re

import numpy as np
import pandas as pd
from scipy import signal
import matplotlib.pyplot as plt
from pandas.errors import EmptyDataError


TARGET_PERIODS = [42, 20]
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


def prepare_regular_series(s: pd.Series, max_missing_frac: float = 0.1) -> pd.Series | None:
    s = s.sort_index()
    # Normalize to one observation per calendar month before gap checks.
    s = s.groupby(s.index.to_period("M")).last()
    s.index = s.index.to_timestamp("M")
    first = s.first_valid_index()
    last = s.last_valid_index()
    if first is None or last is None:
        return None
    full_index = pd.date_range(first, last, freq="ME")
    w = s.reindex(full_index).copy()
    if len(w) < 120:
        return None
    if float(w.isna().mean()) > max_missing_frac:
        return None
    return w.interpolate(method="time").ffill().bfill()


def transform_for_decompose(s: pd.Series, value_type: str, *, pmi_center: bool = True) -> pd.Series | None:
    x = pd.to_numeric(s, errors="coerce")
    # Heuristic: PMI-like diffusion index. Center at 0 by subtracting 50, then treat as level.
    if pmi_center and ("PMI" in s.name.upper() if isinstance(s.name, str) else False):
        x = x - 50.0
        value_type = "level"

    if value_type in {"price", "price_adj", "level"}:
        if (x > 0).all():
            x = np.log(x)
        x = x.diff()
    elif value_type == "rate_level":
        x = x.diff()
    # return / rate_yoy / rate_mom: keep as-is

    x = x.replace([np.inf, -np.inf], np.nan).dropna()
    if x.shape[0] < 120:
        return None
    std = float(x.std(ddof=0))
    if std == 0.0 or np.isnan(std):
        return None
    return (x - float(x.mean())) / std


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
    if sos is None or x.shape[0] < 120:
        return pd.Series(index=x.index, dtype="float64")
    try:
        y = signal.sosfiltfilt(sos, x.values.astype("float64"))
        return pd.Series(y, index=x.index)
    except Exception:
        return pd.Series(index=x.index, dtype="float64")


def quadrant_phase(component: pd.Series, smooth: int = 3) -> pd.Series:
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


def plot_decomposition(name: str, x: pd.Series, comps: pd.DataFrame, phases: pd.DataFrame, out_path: Path) -> None:
    nrows = 1 + len(comps.columns)
    fig, axes = plt.subplots(nrows, 1, figsize=(14, 2.4 * nrows), sharex=True)
    if nrows == 1:
        axes = [axes]

    ax0 = axes[0]
    ax0.plot(x.index, x.values, color="black", lw=1.0)
    ax0.axhline(0.0, color="#999999", lw=0.8)
    ax0.set_title(f"{name} (standardized transform)")

    for i, p in enumerate(comps.columns.tolist(), start=1):
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

    selected_path = out_dir / "cycle_representative_indicators_short_macro.csv"
    panel = pd.read_parquet(data_dir / "research_input_monthly_macro.parquet")
    try:
        selected = pd.read_csv(selected_path)
    except EmptyDataError as exc:
        raise RuntimeError(
            f"Representative file is empty or not ready: {selected_path}. "
            "Run the selector first and rerun this script sequentially."
        ) from exc
    selected = selected.drop_duplicates(subset=["id", "panel_main_column"]).copy()

    specs: list[SeriesSpec] = []
    for r in selected.itertuples(index=False):
        specs.append(
            SeriesSpec(
                id=str(getattr(r, "id")),
                name=str(getattr(r, "name")),
                value_type=str(getattr(r, "value_type")),
                panel_main_column=str(getattr(r, "panel_main_column")),
            )
        )

    out_base = out_dir / "short_cycle_macro"
    plot_dir = out_base / "plots"
    out_base.mkdir(parents=True, exist_ok=True)
    plot_dir.mkdir(parents=True, exist_ok=True)

    rows: list[dict[str, object]] = []
    for spec in specs:
        col = spec.panel_main_column
        if col not in panel.columns:
            continue
        s0 = panel[col].copy()
        s0.name = spec.name
        s1 = prepare_regular_series(s0)
        if s1 is None:
            continue
        x = transform_for_decompose(s1, spec.value_type)
        if x is None:
            continue

        comps: dict[str, pd.Series] = {}
        phases: dict[str, pd.Series] = {}
        for p in TARGET_PERIODS:
            c = bandpass_component(x, p)
            if c.empty or c.isna().all():
                continue
            key = f"{p}m"
            comps[key] = c
            phases[key] = quadrant_phase(c)

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

        plot_path = plot_dir / f"{base}_42_20.png"
        plot_decomposition(spec.id, x, comp_df, phase_df, plot_path)

        rows.append(
            {
                "id": spec.id,
                "name": spec.name,
                "value_type": spec.value_type,
                "panel_main_column": col,
                "points_used": int(x.shape[0]),
                "start": str(x.index.min().date()),
                "end": str(x.index.max().date()),
                "components": ",".join(comp_df.columns.tolist()),
                "reconstruction_r2": r2,
                "components_path": str(comp_path.relative_to(root)),
                "phases_path": str(phase_path.relative_to(root)),
                "plot_path": str(plot_path.relative_to(root)),
            }
        )

    if not rows:
        raise RuntimeError("No short-cycle macro series passed decomposition checks on the research input panel.")

    summary = pd.DataFrame(rows).sort_values(["reconstruction_r2", "points_used"], ascending=[False, False])
    summary_path = out_base / "summary.csv"
    summary.to_csv(summary_path, index=False)
    print("Wrote:", summary_path)


if __name__ == "__main__":
    main()
