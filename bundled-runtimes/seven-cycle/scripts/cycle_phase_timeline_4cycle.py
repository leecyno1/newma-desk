from __future__ import annotations

"""
Build a composite 4-cycle phase timeline (200/100/42/20m) from the selected
representative indicators and render a plot.

Inputs:
- output/cycle_representative_indicators_4cycle.csv
- output/cycle_selected_4cycle/components_<id>.parquet

Outputs:
- output/cycle_phase_timeline_4cycle.parquet
- output/cycle_phase_timeline_4cycle.png
- output/cycle_phase_timeline_4cycle.md
"""

from dataclasses import dataclass
from pathlib import Path
import re

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt


TARGET_PERIODS = [200, 100, 42, 20]
TOP_N_PER_CYCLE = 12

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
class CycleComposite:
    period: int
    component: pd.Series
    phase: pd.Series
    members: pd.DataFrame


def sanitize(s: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", s).strip("_") or "NA"


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


def _zscore(s: pd.Series) -> pd.Series:
    x = pd.to_numeric(s, errors="coerce")
    mu = float(x.mean())
    sd = float(x.std(ddof=0))
    if sd == 0.0 or np.isnan(sd):
        return pd.Series(index=s.index, dtype="float64")
    return (x - mu) / sd


def build_cycle_composite(
    reps: pd.DataFrame,
    *,
    period: int,
    components_dir: Path,
    top_n: int,
) -> CycleComposite | None:
    sub = reps[reps["cycle_months"] == period].copy()
    if sub.empty:
        return None
    sub["bandpower_ratio"] = pd.to_numeric(sub["bandpower_ratio"], errors="coerce")
    sub = sub.dropna(subset=["bandpower_ratio"]).sort_values(["bandpower_ratio", "n_points"], ascending=[False, False])
    sub = sub.head(top_n).reset_index(drop=True)

    members: list[dict[str, object]] = []
    comps: list[pd.Series] = []
    for r in sub.itertuples(index=False):
        id_ = str(getattr(r, "id"))
        comp_path = components_dir / f"components_{sanitize(id_)}.parquet"
        if not comp_path.exists():
            continue
        df = pd.read_parquet(comp_path)
        if period not in df.columns:
            continue
        s = pd.to_numeric(df[period], errors="coerce")
        if s.dropna().shape[0] < 60:
            continue
        members.append(
            {
                "id": id_,
                "name": str(getattr(r, "name")),
                "universe_category": str(getattr(r, "universe_category")),
                "bandpower_ratio": float(getattr(r, "bandpower_ratio")),
            }
        )
        comps.append(s.rename(id_))

    if not comps:
        return None

    mat = pd.concat(comps, axis=1)
    # Standardize per series
    mat = mat.apply(_zscore, axis=0)
    mat = mat.dropna(how="all")
    if mat.empty:
        return None

    # Align signs to avoid cancellation (relative to cross-sectional mean reference).
    ref = mat.mean(axis=1)
    for c in mat.columns:
        aligned = pd.concat([mat[c], ref], axis=1).dropna()
        if aligned.shape[0] < 36:
            continue
        corr = float(aligned.iloc[:, 0].corr(aligned.iloc[:, 1]))
        if np.isfinite(corr) and corr < 0:
            mat[c] = -mat[c]

    comp = mat.mean(axis=1).rename(f"Cycle_{period}m")
    phase = quadrant_phase(comp).rename(f"Phase_{period}m")
    members_df = pd.DataFrame(members).sort_values("bandpower_ratio", ascending=False)
    return CycleComposite(period=period, component=comp, phase=phase, members=members_df)


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    out_dir = root / "output"
    reps_path = out_dir / "cycle_representative_indicators_4cycle.csv"
    comp_dir = out_dir / "cycle_selected_4cycle"
    components_dir = comp_dir

    if not reps_path.exists():
        raise FileNotFoundError(f"Missing: {reps_path}")
    reps = pd.read_csv(reps_path)

    composites: list[CycleComposite] = []
    for p in TARGET_PERIODS:
        c = build_cycle_composite(reps, period=p, components_dir=components_dir, top_n=TOP_N_PER_CYCLE)
        if c is not None:
            composites.append(c)

    if not composites:
        raise RuntimeError("No composites were built (missing component files?)")

    # Merge into a single timeline frame
    parts = []
    for c in composites:
        parts.append(c.component)
        parts.append(c.phase)
    timeline = pd.concat(parts, axis=1).sort_index()

    out_parquet = out_dir / "cycle_phase_timeline_4cycle.parquet"
    timeline.to_parquet(out_parquet)

    # Plot
    n = len(composites)
    fig, axes = plt.subplots(n, 1, figsize=(14, 2.6 * n), sharex=True)
    if n == 1:
        axes = [axes]

    for ax, c in zip(axes, composites):
        shade_phases(ax, c.phase)
        ax.plot(c.component.index, c.component.values, lw=1.1, color="#1f77b4")
        ax.axhline(0.0, color="#999999", lw=0.8)
        ax.set_ylabel(f"{c.period}m")

    handles = [plt.Line2D([0], [0], color=PHASE_COLORS[k], lw=6) for k in [1, 2, 3, 4]]
    labels = [PHASE_LABELS[k] for k in [1, 2, 3, 4]]
    fig.legend(handles, labels, loc="upper right", frameon=True)
    fig.suptitle("Composite 4-cycle phase timeline (from representative indicators)", y=0.995)
    fig.tight_layout()

    out_png = out_dir / "cycle_phase_timeline_4cycle.png"
    fig.savefig(out_png, dpi=150)
    plt.close(fig)

    # Markdown summary
    lines: list[str] = []
    lines.append("# 4-cycle phase timeline (composite)")
    lines.append("")
    lines.append(f"- Timeline parquet: `{out_parquet.relative_to(root)}`")
    lines.append(f"- Plot: `{out_png.relative_to(root)}`")
    lines.append("")
    for c in composites:
        lines.append(f"## {c.period}m members (top {TOP_N_PER_CYCLE})")
        lines.append("```")
        lines.append(c.members.to_string(index=False))
        lines.append("```")
        lines.append("")

    out_md = out_dir / "cycle_phase_timeline_4cycle.md"
    out_md.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print("Wrote:", out_parquet)
    print("Wrote:", out_png)
    print("Wrote:", out_md)


if __name__ == "__main__":
    main()

