from __future__ import annotations

"""
Hybrid 4-cycle phase timeline:
- Long cycles (200m/100m): annual year-extended long panel (1800+), mapped to monthly by year.
- Short cycles (42m/20m): monthly short panel (2000+).

Inputs:
- output/long_cycle_representatives_year_extended.csv
- output/long_cycle_selected_year_extended/components_<id>.parquet
- output/cycle_representative_indicators_4cycle.csv
- output/cycle_selected_4cycle/components_<id>.parquet
- data/indicator_panel_monthly.parquet (for monthly index)

Outputs:
- output/cycle_phase_timeline_4cycle_hybrid.parquet
- output/cycle_phase_timeline_4cycle_hybrid.png
- output/cycle_phase_timeline_4cycle_hybrid.md
"""

from dataclasses import dataclass
from pathlib import Path
import re

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt


LONG_PERIODS = [200, 100]
SHORT_PERIODS = [42, 20]
TOP_N_PER_CYCLE = 12
TARGET_END_YEAR = 2024
MIN_RECENT_MEMBERS = 3

PHASE_LABELS = {
    1: "Expansion",
    2: "Downturn",
    3: "Contraction",
    4: "Recovery",
}
HUATAI_PHASE_LABELS = {
    1: "Up",
    2: "High",
    3: "Down",
    4: "Low",
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


def build_composite_from_components(
    reps: pd.DataFrame,
    *,
    period: int,
    components_dir: Path,
    top_n: int,
    min_end_year: int | None = None,
    min_recent_members: int = 0,
) -> CycleComposite | None:
    sub = reps[reps["cycle_months"] == period].copy()
    if sub.empty:
        return None
    sub["bandpower_ratio"] = pd.to_numeric(sub["bandpower_ratio"], errors="coerce")
    sub = sub.dropna(subset=["bandpower_ratio"])

    # Prefer series that still have data near TARGET_END_YEAR for long-cycle tracking.
    if min_end_year is not None and "end_year" in sub.columns:
        sub["end_year"] = pd.to_numeric(sub["end_year"], errors="coerce")
        recent = sub[sub["end_year"] >= min_end_year].copy()
        if recent.shape[0] >= max(1, int(min_recent_members)):
            sub = recent

    sort_cols = ["bandpower_ratio", "n_points"]
    if "end_year" in sub.columns:
        sort_cols.append("end_year")
    sub = sub.sort_values(sort_cols, ascending=[False] * len(sort_cols))
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
        if s.dropna().shape[0] < 30:
            continue
        comps.append(s.rename(id_))
        members.append(
            {
                "id": id_,
                "name": str(getattr(r, "name", id_)),
                "universe_category": str(getattr(r, "universe_category", "")),
                "bandpower_ratio": float(getattr(r, "bandpower_ratio")),
            }
        )

    if not comps:
        return None

    mat = pd.concat(comps, axis=1)
    mat = mat.apply(_zscore, axis=0).dropna(how="all")
    if mat.empty:
        return None

    # Align signs to avoid cancellation.
    ref = mat.mean(axis=1)
    for c in mat.columns:
        aligned = pd.concat([mat[c], ref], axis=1).dropna()
        if aligned.shape[0] < 30:
            continue
        corr = float(aligned.iloc[:, 0].corr(aligned.iloc[:, 1]))
        if np.isfinite(corr) and corr < 0:
            mat[c] = -mat[c]

    comp = mat.mean(axis=1).rename(f"Cycle_{period}m")
    phase = quadrant_phase(comp).rename(f"Phase_{period}m")
    members_df = pd.DataFrame(members).sort_values("bandpower_ratio", ascending=False)
    return CycleComposite(period=period, component=comp, phase=phase, members=members_df)


def map_annual_to_monthly(s_annual: pd.Series, monthly_index: pd.DatetimeIndex) -> pd.Series:
    # Annual index is expected to be integer year. Map to each month by its calendar year.
    years = pd.Index(monthly_index.year.astype(int), name="year")
    mapped = s_annual.reindex(years)
    mapped.index = monthly_index
    return mapped


def find_turning_points(component: pd.Series, *, period: int, freq: str) -> pd.DataFrame:
    """
    Turning points on a (band-pass) cycle component via smoothed slope sign-changes.

    - freq="A": component indexed by integer year
    - freq="M": component indexed by Timestamp (month-end)
    """
    s = pd.to_numeric(component, errors="coerce").dropna()
    if s.shape[0] < 10:
        return pd.DataFrame(columns=["when", "type", "value"])

    if freq not in {"A", "M"}:
        raise ValueError(f"freq must be 'A' or 'M', got {freq}")

    # Convert expected period to "points" in this frequency domain.
    period_points = int(round(period / 12)) if freq == "A" else int(period)
    period_points = max(2, period_points)

    min_distance = max(1, int(round(period_points / 4)))
    smooth = max(2, int(round(period_points / 10)))
    y = pd.Series(s.values.astype("float64")).rolling(smooth, min_periods=1).mean().values
    dy = np.diff(y)
    sign = np.sign(dy).astype("float64")
    # Handle flat runs by forward/back filling.
    sign = pd.Series(sign).replace(0.0, np.nan).ffill().bfill().values
    if sign.size < 2:
        return pd.DataFrame(columns=["when", "type", "value"])

    peaks = np.where((sign[:-1] > 0) & (sign[1:] < 0))[0] + 1
    troughs = np.where((sign[:-1] < 0) & (sign[1:] > 0))[0] + 1

    events: list[tuple[int, str]] = [(int(i), "Peak") for i in peaks.tolist()] + [
        (int(i), "Trough") for i in troughs.tolist()
    ]
    if not events:
        return pd.DataFrame(columns=["when", "type", "value"])
    events.sort(key=lambda x: x[0])

    # Enforce minimum spacing to avoid noise.
    kept: list[tuple[int, str]] = []
    last_i: int | None = None
    for i, t in events:
        if last_i is None or (i - last_i) >= min_distance:
            kept.append((i, t))
            last_i = i

    out = pd.DataFrame(
        [{"when": s.index[i], "type": t, "value": float(s.iloc[i])} for i, t in kept]
    )
    if out.empty:
        return pd.DataFrame(columns=["when", "type", "value"])
    return out.sort_values("when").reset_index(drop=True)


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    out_dir = root / "output"
    data_dir = root / "data"

    # Monthly index anchor
    monthly_panel = pd.read_parquet(data_dir / "indicator_panel_monthly.parquet")
    monthly_index = monthly_panel.index

    # Long cycles (annual long panel)
    long_reps = pd.read_csv(out_dir / "long_cycle_representatives_year_extended.csv")
    long_comp_dir = out_dir / "long_cycle_selected_year_extended"

    # Short cycles (monthly short panel)
    short_reps = pd.read_csv(out_dir / "cycle_representative_indicators_4cycle.csv")
    short_reps = short_reps[short_reps["cycle_months"].isin(SHORT_PERIODS)].copy()
    short_comp_dir = out_dir / "cycle_selected_4cycle"

    composites: dict[int, CycleComposite] = {}

    for p in LONG_PERIODS:
        c = build_composite_from_components(
            long_reps,
            period=p,
            components_dir=long_comp_dir,
            top_n=TOP_N_PER_CYCLE,
            min_end_year=TARGET_END_YEAR,
            min_recent_members=MIN_RECENT_MEMBERS,
        )
        if c is not None:
            composites[p] = c

    for p in SHORT_PERIODS:
        c = build_composite_from_components(short_reps, period=p, components_dir=short_comp_dir, top_n=TOP_N_PER_CYCLE)
        if c is not None:
            composites[p] = c

    # Build monthly timeline
    cols: list[pd.Series] = []
    for p in [200, 100]:
        c = composites.get(p)
        if c is None:
            cols.append(pd.Series(index=monthly_index, dtype="float64", name=f"Cycle_{p}m"))
            cols.append(pd.Series(index=monthly_index, dtype="float64", name=f"Phase_{p}m"))
            continue
        comp_m = map_annual_to_monthly(c.component, monthly_index)
        ph_m = map_annual_to_monthly(c.phase, monthly_index)
        comp_m.name = f"Cycle_{p}m"
        ph_m.name = f"Phase_{p}m"
        cols.append(comp_m)
        cols.append(ph_m)

    for p in [42, 20]:
        c = composites.get(p)
        if c is None:
            cols.append(pd.Series(index=monthly_index, dtype="float64", name=f"Cycle_{p}m"))
            cols.append(pd.Series(index=monthly_index, dtype="float64", name=f"Phase_{p}m"))
            continue
        comp_m = c.component.reindex(monthly_index)
        ph_m = c.phase.reindex(monthly_index)
        comp_m.name = f"Cycle_{p}m"
        ph_m.name = f"Phase_{p}m"
        cols.append(comp_m)
        cols.append(ph_m)

    timeline = pd.concat(cols, axis=1).sort_index()

    out_parquet = out_dir / "cycle_phase_timeline_4cycle_hybrid.parquet"
    timeline.to_parquet(out_parquet)

    # Turning points per cycle (computed on native freq component; then mapped to monthly for plotting)
    turning: dict[int, pd.DataFrame] = {}
    for p in [200, 100, 42, 20]:
        c = composites.get(p)
        if c is None:
            continue
        freq = "A" if p in LONG_PERIODS else "M"
        turning[p] = find_turning_points(c.component, period=p, freq=freq)

    # Plot (4 panels)
    fig, axes = plt.subplots(4, 1, figsize=(14, 11), sharex=True)
    order = [200, 100, 42, 20]
    for ax, p in zip(axes, order):
        comp = timeline[f"Cycle_{p}m"]
        ph = timeline[f"Phase_{p}m"]
        shade_phases(ax, ph)
        ax.plot(comp.index, comp.values, lw=1.1, color="#1f77b4")
        # turning-point markers
        ev = turning.get(p)
        if ev is not None and not ev.empty:
            when = ev["when"].tolist()
            if p in LONG_PERIODS:
                when = [pd.Timestamp(f"{int(y)}-12-31") for y in when]
            vals = comp.reindex(pd.DatetimeIndex(when))
            peak_mask = ev["type"].astype(str).eq("Peak").values
            trough_mask = ev["type"].astype(str).eq("Trough").values
            when_idx = pd.DatetimeIndex(when)
            ax.scatter(
                when_idx[peak_mask],
                vals.reindex(when_idx)[peak_mask],
                marker="^",
                s=18,
                color="#d62728",
                alpha=0.9,
                zorder=3,
            )
            ax.scatter(
                when_idx[trough_mask],
                vals.reindex(when_idx)[trough_mask],
                marker="v",
                s=18,
                color="#2ca02c",
                alpha=0.9,
                zorder=3,
            )
        ax.axhline(0.0, color="#999999", lw=0.8)
        ax.set_ylabel(f"{p}m")

    handles = [plt.Line2D([0], [0], color=PHASE_COLORS[k], lw=6) for k in [1, 2, 3, 4]]
    labels = [PHASE_LABELS[k] for k in [1, 2, 3, 4]]
    fig.legend(handles, labels, loc="upper right", frameon=True)
    fig.suptitle("Hybrid 4-cycle phase timeline (200/100 annual-long + 42/20 monthly-short)", y=0.995)
    fig.tight_layout()

    out_png = out_dir / "cycle_phase_timeline_4cycle_hybrid.png"
    fig.savefig(out_png, dpi=150)
    plt.close(fig)

    # Markdown summary
    lines: list[str] = []
    lines.append("# Hybrid 4-cycle phase timeline")
    lines.append("")
    lines.append(f"- Timeline parquet: `{out_parquet.relative_to(root)}`")
    lines.append(f"- Plot: `{out_png.relative_to(root)}`")
    lines.append("")
    lines.append("## Coverage & latest phase (composite-level)")
    lines.append("")
    lines.append(
        "| cycle | freq | start | end | last_phase_date | phase(code) | phase(label) | phase(Huatai) |"
    )
    lines.append("|---:|:---:|---:|---:|---:|---:|:---|:---|")

    def _fmt_idx(x: object) -> str:
        if isinstance(x, (int, np.integer)):
            return str(int(x))
        if isinstance(x, pd.Timestamp):
            return x.strftime("%Y-%m-%d")
        return str(x)

    for p in [200, 100, 42, 20]:
        c = composites.get(p)
        if c is None or c.component.dropna().empty or c.phase.dropna().empty:
            lines.append(f"| {p}m | - | - | - | - | - | - | - |")
            continue
        comp = c.component.dropna()
        ph = c.phase.dropna().astype(int)
        last_dt = ph.index.max()
        last_code = int(ph.loc[last_dt])
        lines.append(
            "| "
            + " | ".join(
                [
                    f"{p}m",
                    "A" if p in LONG_PERIODS else "M",
                    _fmt_idx(comp.index.min()),
                    _fmt_idx(comp.index.max()),
                    _fmt_idx(last_dt),
                    str(last_code),
                    PHASE_LABELS.get(last_code, "NA"),
                    HUATAI_PHASE_LABELS.get(last_code, "NA"),
                ]
            )
            + " |"
        )

    lines.append("")
    lines.append("## Snapshot @ 2024-12-31 (monthly timeline)")
    lines.append("")
    snap_date = pd.Timestamp("2024-12-31")
    if snap_date in timeline.index:
        snap = timeline.loc[snap_date]
        lines.append("| cycle | phase(code) | phase(label) | phase(Huatai) | value |")
        lines.append("|---:|---:|:---|:---|---:|")
        for p in [200, 100, 42, 20]:
            ph = snap.get(f"Phase_{p}m", np.nan)
            val = snap.get(f"Cycle_{p}m", np.nan)
            if pd.isna(ph) or pd.isna(val):
                lines.append(f"| {p}m | - | - | - | - |")
                continue
            code = int(ph)
            lines.append(
                f"| {p}m | {code} | {PHASE_LABELS.get(code, 'NA')} | {HUATAI_PHASE_LABELS.get(code, 'NA')} | {float(val):.6f} |"
            )
    else:
        lines.append(f"- (missing index row: {snap_date.date()})")

    lines.append("")
    lines.append("## Turning Points (slope sign-change; recent)")
    lines.append("")
    lines.append("- Markers on plot: Peak=^ (red), Trough=v (green)")
    lines.append("")

    for p in [200, 100, 42, 20]:
        ev = turning.get(p)
        if ev is None or ev.empty:
            lines.append(f"### {p}m")
            lines.append("")
            lines.append("- (no turning points detected)")
            lines.append("")
            continue

        show = ev.tail(12).copy()
        show["when"] = show["when"].astype(str)
        lines.append(f"### {p}m")
        lines.append("")
        lines.append(show.to_markdown(index=False))
        lines.append("")

    for p in order:
        c = composites.get(p)
        if c is None:
            lines.append(f"## {p}m members (none)")
            lines.append("")
            continue
        lines.append(f"## {p}m members (top {TOP_N_PER_CYCLE})")
        lines.append("```")
        lines.append(c.members.to_string(index=False))
        lines.append("```")
        lines.append("")

    out_md = out_dir / "cycle_phase_timeline_4cycle_hybrid.md"
    out_md.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print("Wrote:", out_parquet)
    print("Wrote:", out_png)
    print("Wrote:", out_md)


if __name__ == "__main__":
    main()
