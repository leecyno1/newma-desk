from __future__ import annotations

"""
Build composite phase timelines for long cycles (200m/100m) from long-history
annual decomposition outputs.

Inputs:
- output/cycle_representative_indicators_long_history_long.csv
- output/long_history_long_cycles/components_<col>.parquet

Outputs:
- output/cycle_phase_timeline_long_history_long.parquet
- output/cycle_phase_timeline_long_history_long.png
- output/cycle_phase_timeline_long_history_long.md
"""

from dataclasses import dataclass
from pathlib import Path
import re

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt


TARGET_MONTHS = [200, 100]
TOP_N_PER_CYCLE = 10

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
    months: int
    component: pd.Series
    phase: pd.Series
    members: pd.DataFrame


def sanitize(s: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", s).strip("_") or "NA"


def _zscore(s: pd.Series) -> pd.Series:
    x = pd.to_numeric(s, errors="coerce")
    mu = float(x.mean())
    sd = float(x.std(ddof=0))
    if sd == 0.0 or np.isnan(sd):
        return pd.Series(index=s.index, dtype="float64")
    return (x - mu) / sd


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


def build_cycle_composite(
    reps: pd.DataFrame,
    *,
    months: int,
    components_dir: Path,
    top_n: int,
) -> CycleComposite | None:
    sub = reps[reps["cycle_months"] == months].copy()
    if sub.empty:
        return None
    sub["bandpower_ratio"] = pd.to_numeric(sub["bandpower_ratio"], errors="coerce")
    sub = sub.dropna(subset=["bandpower_ratio"]).sort_values(["bandpower_ratio", "n_points"], ascending=[False, False])
    sub = sub.head(top_n).reset_index(drop=True)

    members: list[dict[str, object]] = []
    comps: list[pd.Series] = []
    for r in sub.itertuples(index=False):
        col = str(getattr(r, "column"))
        comp_path = components_dir / f"components_{sanitize(col)}.parquet"
        if not comp_path.exists():
            continue
        df = pd.read_parquet(comp_path)
        key = f"{months}m"
        if key not in df.columns:
            continue
        s = pd.to_numeric(df[key], errors="coerce")
        if s.dropna().shape[0] < 80:
            continue
        members.append(
            {
                "column": col,
                "source": str(getattr(r, "source")),
                "value_type": str(getattr(r, "value_type")),
                "bandpower_ratio": float(getattr(r, "bandpower_ratio")),
            }
        )
        comps.append(s.rename(col))

    if not comps:
        return None

    mat = pd.concat(comps, axis=1)
    mat = mat.apply(_zscore, axis=0)
    mat = mat.dropna(how="all")
    if mat.empty:
        return None

    ref = mat.mean(axis=1)
    for c in mat.columns:
        aligned = pd.concat([mat[c], ref], axis=1).dropna()
        if aligned.shape[0] < 60:
            continue
        corr = float(aligned.iloc[:, 0].corr(aligned.iloc[:, 1]))
        if np.isfinite(corr) and corr < 0:
            mat[c] = -mat[c]

    comp = mat.mean(axis=1).rename(f"Cycle_{months}m")
    phase = quadrant_phase(comp).rename(f"Phase_{months}m")
    members_df = pd.DataFrame(members).sort_values("bandpower_ratio", ascending=False)
    return CycleComposite(months=months, component=comp, phase=phase, members=members_df)


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    out_dir = root / "output"
    reps_path = out_dir / "cycle_representative_indicators_long_history_long.csv"
    comps_dir = out_dir / "long_history_long_cycles"

    reps = pd.read_csv(reps_path)

    composites: list[CycleComposite] = []
    for m in TARGET_MONTHS:
        c = build_cycle_composite(reps, months=m, components_dir=comps_dir, top_n=TOP_N_PER_CYCLE)
        if c is not None:
            composites.append(c)

    if not composites:
        raise RuntimeError("No composites were built (missing component files?)")

    timeline = pd.concat([c.component for c in composites] + [c.phase for c in composites], axis=1).sort_index()
    out_parquet = out_dir / "cycle_phase_timeline_long_history_long.parquet"
    timeline.to_parquet(out_parquet)

    fig, axes = plt.subplots(len(composites), 1, figsize=(14, 2.8 * len(composites)), sharex=True)
    if len(composites) == 1:
        axes = [axes]
    for ax, c in zip(axes, composites):
        shade_phases(ax, c.phase)
        ax.plot(c.component.index, c.component.values, lw=1.1, color="#1f77b4")
        ax.axhline(0.0, color="#999999", lw=0.8)
        ax.set_ylabel(f"{c.months}m")

    handles = [plt.Line2D([0], [0], color=PHASE_COLORS[k], lw=6) for k in [1, 2, 3, 4]]
    labels = [PHASE_LABELS[k] for k in [1, 2, 3, 4]]
    fig.legend(handles, labels, loc="upper right", frameon=True)
    fig.suptitle("Long-history composite long-cycle timeline (annual)", y=0.995)
    fig.tight_layout()

    out_png = out_dir / "cycle_phase_timeline_long_history_long.png"
    fig.savefig(out_png, dpi=150)
    plt.close(fig)

    lines: list[str] = []
    lines.append("# Long-history long-cycle phase timeline (annual)")
    lines.append("")
    lines.append(f"- Timeline parquet: `{out_parquet.relative_to(root)}`")
    lines.append(f"- Plot: `{out_png.relative_to(root)}`")
    lines.append("")
    for c in composites:
        lines.append(f"## {c.months}m members (top {TOP_N_PER_CYCLE})")
        lines.append("```")
        lines.append(c.members.to_string(index=False))
        lines.append("```")
        lines.append("")

    out_md = out_dir / "cycle_phase_timeline_long_history_long.md"
    out_md.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print("Wrote:", out_parquet)
    print("Wrote:", out_png)
    print("Wrote:", out_md)


if __name__ == "__main__":
    main()

