from __future__ import annotations

"""
Hybrid long+short cycle phase timeline:
- Long cycles (200m/100m): governed very-long annual panel, mapped to monthly by calendar year.
- Short cycles (42m/20m): short-panel monthly macro (2000+).

This produces a single monthly-index timeline for joint analysis/plotting.

Inputs:
- output/cycle_phase_timeline_very_long_history_long.parquet
- output/cycle_phase_timeline_short_macro.parquet
- data/research_input_monthly_macro.parquet (for monthly index anchor)

Outputs:
- output/cycle_phase_timeline_long_short_hybrid.parquet
- output/cycle_phase_timeline_long_short_hybrid.png
- output/cycle_phase_timeline_long_short_hybrid.md
"""

from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt


TARGET_END = pd.Timestamp("2025-12-31")

LONG_PERIODS = [200, 100]
SHORT_PERIODS = [42, 20]

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


def map_annual_to_monthly(s_annual: pd.Series, monthly_index: pd.DatetimeIndex) -> pd.Series:
    # Annual index is expected to be integer year. Map to each month by its calendar year.
    years = pd.Index(monthly_index.year.astype(int), name="year")
    mapped = s_annual.reindex(years)
    mapped.index = monthly_index
    # Carry the latest known annual state forward until the next annual observation is available.
    return mapped.ffill()


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    out_dir = root / "output"
    data_dir = root / "data"

    monthly_panel = pd.read_parquet(data_dir / "research_input_monthly_macro.parquet")
    monthly_periods = monthly_panel.index.to_period("M").unique().sort_values()
    monthly_index = monthly_periods.to_timestamp("M")
    monthly_index = monthly_index[monthly_index <= TARGET_END]

    long_annual = pd.read_parquet(out_dir / "cycle_phase_timeline_very_long_history_long.parquet")
    short_monthly = pd.read_parquet(out_dir / "cycle_phase_timeline_short_macro.parquet")
    short_monthly = short_monthly.groupby(short_monthly.index.to_period("M")).last()
    short_monthly.index = short_monthly.index.to_timestamp("M")
    short_monthly = short_monthly.reindex(monthly_index)

    long_mapped = pd.DataFrame(index=monthly_index)
    for p in LONG_PERIODS:
        long_mapped[f"Cycle_{p}m"] = map_annual_to_monthly(long_annual[f"Cycle_{p}m"], monthly_index)
        long_mapped[f"Phase_{p}m"] = map_annual_to_monthly(long_annual[f"Phase_{p}m"], monthly_index)

    timeline = pd.concat([long_mapped, short_monthly], axis=1)
    out_parquet = out_dir / "cycle_phase_timeline_long_short_hybrid.parquet"
    timeline.to_parquet(out_parquet)

    fig, axes = plt.subplots(4, 1, figsize=(14, 11.2), sharex=True)
    order = LONG_PERIODS + SHORT_PERIODS
    for ax, p in zip(axes, order):
        comp = timeline.get(f"Cycle_{p}m")
        ph = timeline.get(f"Phase_{p}m")
        if comp is None or ph is None:
            continue
        shade_phases(ax, ph)
        ax.plot(comp.index, comp.values, lw=1.1, color="#1f77b4")
        ax.axhline(0.0, color="#999999", lw=0.8)
        ax.set_ylabel(f"{p}m")

    handles = [plt.Line2D([0], [0], color=PHASE_COLORS[k], lw=6) for k in [1, 2, 3, 4]]
    labels = [PHASE_LABELS[k] for k in [1, 2, 3, 4]]
    fig.legend(handles, labels, loc="upper right", frameon=True)
    fig.suptitle("Hybrid long+short cycle phase timeline (monthly index, cut @ 2025-12-31)", y=0.995)
    fig.tight_layout()

    out_png = out_dir / "cycle_phase_timeline_long_short_hybrid.png"
    fig.savefig(out_png, dpi=150)
    plt.close(fig)

    last_row = timeline.loc[timeline.index.max()]
    phases = {k: int(v) if np.isfinite(v) else None for k, v in last_row.items() if k.startswith("Phase_")}

    lines: list[str] = []
    lines.append("# Hybrid long+short cycle phase timeline (monthly)")
    lines.append("")
    lines.append(f"- Cutoff: `{TARGET_END.date()}`")
    lines.append(f"- Timeline parquet: `{out_parquet.relative_to(root)}`")
    lines.append(f"- Plot: `{out_png.relative_to(root)}`")
    lines.append("")
    lines.append("## Latest phases (as of cutoff)")
    lines.append("```")
    for p in order:
        v = phases.get(f"Phase_{p}m")
        label = PHASE_LABELS.get(v, "NA") if v is not None else "NA"
        lines.append(f"{p:>4}m : {v} ({label})")
    lines.append("```")
    lines.append("")

    out_md = out_dir / "cycle_phase_timeline_long_short_hybrid.md"
    out_md.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print("Wrote:", out_parquet)
    print("Wrote:", out_png)
    print("Wrote:", out_md)


if __name__ == "__main__":
    main()
