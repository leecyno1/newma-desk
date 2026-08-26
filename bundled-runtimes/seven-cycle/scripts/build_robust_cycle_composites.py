from __future__ import annotations

"""
Build category-balanced composite timelines from robust discovered cycle bands.

Annual bands:
- 9 years: broad Juglar-like investment rhythm.
- 14 years: data-supported long-investment band replacing a fixed 200m point.

Monthly bands:
- 16.5 months: broad market/short macro rhythm.
- 21 months: liquidity/credit diagnostic band.
- 42 months: inventory/business-cycle band.
"""

from dataclasses import dataclass

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from cycle_robustness_core import (
    PANEL_SPECS,
    ROOT,
    annual_category,
    butterworth_component,
    load_metadata,
    preprocess_series,
    regularize_series,
    safe_correlation,
)


ANNUAL_OUT = ROOT / "output" / "cycle_phase_timeline_robust_annual.parquet"
MONTHLY_OUT = ROOT / "output" / "cycle_phase_timeline_robust_monthly.parquet"
HYBRID_OUT = ROOT / "output" / "cycle_phase_timeline_robust_hybrid.parquet"
MEMBERS_OUT = ROOT / "output" / "cycle_phase_timeline_robust_members.csv"
COMPARE_OUT = ROOT / "output" / "cycle_phase_timeline_robust_vs_legacy.csv"
REPORT_OUT = ROOT / "output" / "cycle_phase_timeline_robust.md"
ANNUAL_PLOT = ROOT / "output" / "cycle_phase_timeline_robust_annual.png"
MONTHLY_PLOT = ROOT / "output" / "cycle_phase_timeline_robust_monthly.png"


@dataclass(frozen=True)
class CompositeSpec:
    panel: str
    preprocess_method: str
    periods: tuple[tuple[str, float], ...]
    growth_categories: tuple[str, ...]


COMPOSITE_SPECS = {
    "annual_long": CompositeSpec(
        panel="annual_long",
        preprocess_method="hp_100",
        periods=(("9y", 9.0), ("14y", 14.0)),
        growth_categories=("real_activity", "real_aggregate", "real_per_capita", "labor_productivity"),
    ),
    "monthly_macro": CompositeSpec(
        panel="monthly_macro",
        preprocess_method="canonical_hp",
        periods=(("16_5m", 16.5), ("21m", 21.0), ("42m", 42.0)),
        growth_categories=("宏观增长类（Macro Growth）",),
    ),
}


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


def zscore(values: pd.Series) -> pd.Series:
    standard_deviation = float(values.std(ddof=0))
    if not np.isfinite(standard_deviation) or standard_deviation == 0.0:
        return pd.Series(index=values.index, dtype="float64")
    return (values - float(values.mean())) / standard_deviation


def align_matrix(matrix: pd.DataFrame, trim: int) -> tuple[pd.DataFrame, dict[str, bool]]:
    normalized = matrix.apply(zscore, axis=0).dropna(how="all")
    reference = normalized.mean(axis=1)
    flipped = {}
    for column in normalized.columns:
        correlation = safe_correlation(normalized[column], reference, trim=trim)
        should_flip = bool(np.isfinite(correlation) and correlation < 0.0)
        if should_flip:
            normalized[column] = -normalized[column]
        flipped[str(column)] = should_flip
    return normalized, flipped


def quadrant_phase(component: pd.Series, smooth: int) -> pd.Series:
    level = pd.to_numeric(component, errors="coerce")
    change = level.diff().rolling(smooth, min_periods=1).mean()
    phase = pd.Series(index=level.index, dtype="float64")
    phase[(level >= 0.0) & (change >= 0.0)] = 1
    phase[(level >= 0.0) & (change < 0.0)] = 2
    phase[(level < 0.0) & (change < 0.0)] = 3
    phase[(level < 0.0) & (change >= 0.0)] = 4
    return phase


def category_for_column(panel_spec, metadata: pd.DataFrame, column: str) -> str:
    if panel_spec.frequency == "A":
        return annual_category(column)
    return str(metadata.loc[column, "universe_category"])


def build_period_composite(panel_spec, composite_spec, period_label: str, period: float) -> tuple[pd.Series, pd.Series, pd.DataFrame]:
    panel = pd.read_parquet(panel_spec.path)
    metadata = load_metadata(panel_spec)
    components_by_category: dict[str, list[pd.Series]] = {}
    source_rows = []

    for column in panel.columns:
        value_type = str(metadata.loc[column, "value_type"]) if column in metadata.index else "level"
        regular = regularize_series(panel[column], panel_spec.frequency, panel_spec.min_points)
        if regular is None:
            continue
        base = preprocess_series(
            regular,
            value_type=value_type,
            frequency=panel_spec.frequency,
            method=composite_spec.preprocess_method,
        )
        if base is None:
            continue
        component = butterworth_component(base, period)
        if component.dropna().shape[0] < max(60, int(period * 3)):
            continue
        category = category_for_column(panel_spec, metadata, column)
        components_by_category.setdefault(category, []).append(component.rename(column))
        source_rows.append(
            {
                "panel": panel_spec.name,
                "period_label": period_label,
                "period": period,
                "category": category,
                "column": column,
            }
        )

    trim = max(3, int(round(period * 0.5)))
    category_components = []
    flip_records = []
    for category, components in sorted(components_by_category.items()):
        matrix = pd.concat(components, axis=1)
        aligned, flipped = align_matrix(matrix, trim)
        if aligned.empty:
            continue
        category_component = aligned.mean(axis=1).rename(category)
        category_components.append(category_component)
        for column, was_flipped in flipped.items():
            flip_records.append(
                {
                    "panel": panel_spec.name,
                    "period_label": period_label,
                    "period": period,
                    "category": category,
                    "column": column,
                    "flipped_within_category": was_flipped,
                }
            )

    if not category_components:
        raise RuntimeError(f"No category components for {panel_spec.name} {period_label}")

    category_matrix = pd.concat(category_components, axis=1)
    aligned_categories, category_flips = align_matrix(category_matrix, trim)
    composite = aligned_categories.mean(axis=1)

    available_growth_categories = [
        category for category in composite_spec.growth_categories if category in category_matrix.columns
    ]
    orientation_flipped = False
    if available_growth_categories:
        growth_anchor = category_matrix[available_growth_categories].mean(axis=1)
        orientation = safe_correlation(composite, growth_anchor, trim=trim)
        if np.isfinite(orientation) and orientation < 0.0:
            composite = -composite
            orientation_flipped = True

    smooth = 2 if panel_spec.frequency == "A" else 3
    component_name = f"Cycle_{period_label}"
    phase_name = f"Phase_{period_label}"
    composite = zscore(composite).rename(component_name)
    phase = quadrant_phase(composite, smooth=smooth).rename(phase_name)

    members = pd.DataFrame(flip_records)
    if members.empty:
        members = pd.DataFrame(source_rows)
        members["flipped_within_category"] = False
    members["category_flipped"] = members["category"].map(category_flips).fillna(False)
    members["final_orientation_flipped"] = orientation_flipped
    return composite, phase, members


def shade_phases(axis: plt.Axes, phases: pd.Series) -> None:
    valid = phases.dropna().astype(int)
    if valid.empty:
        return
    start = valid.index[0]
    current = int(valid.iloc[0])
    for timestamp, phase in valid.iloc[1:].items():
        phase = int(phase)
        if phase != current:
            axis.axvspan(start, timestamp, color=PHASE_COLORS[current], alpha=0.3, linewidth=0)
            start = timestamp
            current = phase
    axis.axvspan(start, valid.index[-1], color=PHASE_COLORS[current], alpha=0.3, linewidth=0)


def plot_timeline(timeline: pd.DataFrame, periods: tuple[tuple[str, float], ...], title: str, path) -> None:
    figure, axes = plt.subplots(len(periods), 1, figsize=(14, 3.0 * len(periods)), sharex=True)
    if len(periods) == 1:
        axes = [axes]
    for axis, (label, _period) in zip(axes, periods):
        component = timeline[f"Cycle_{label}"]
        phase = timeline[f"Phase_{label}"]
        shade_phases(axis, phase)
        axis.plot(component.index, component.values, color="#1f77b4", linewidth=1.1)
        axis.axhline(0.0, color="#888888", linewidth=0.8)
        axis.set_ylabel(label)
    handles = [plt.Line2D([0], [0], color=PHASE_COLORS[key], linewidth=6) for key in PHASE_LABELS]
    figure.legend(handles, [PHASE_LABELS[key] for key in PHASE_LABELS], loc="upper right")
    figure.suptitle(title, y=0.995)
    figure.tight_layout()
    figure.savefig(path, dpi=150)
    plt.close(figure)


def build_panel_timeline(panel_spec) -> tuple[pd.DataFrame, pd.DataFrame]:
    composite_spec = COMPOSITE_SPECS[panel_spec.name]
    components = []
    phases = []
    members = []
    for period_label, period in composite_spec.periods:
        component, phase, period_members = build_period_composite(
            panel_spec,
            composite_spec,
            period_label,
            period,
        )
        components.append(component)
        phases.append(phase)
        members.append(period_members)
    timeline = pd.concat(components + phases, axis=1).sort_index()
    return timeline, pd.concat(members, ignore_index=True)


def map_annual_to_monthly(annual: pd.DataFrame, monthly_index: pd.DatetimeIndex) -> pd.DataFrame:
    mapped = pd.DataFrame(index=monthly_index)
    years = pd.Index(monthly_index.year.astype(int), name="year")
    for column in annual.columns:
        values = annual[column].reindex(years)
        values.index = monthly_index
        mapped[column] = values.ffill()
    return mapped


def legacy_comparison(annual: pd.DataFrame, monthly: pd.DataFrame) -> pd.DataFrame:
    rows = []
    annual_legacy_path = ROOT / "output" / "cycle_phase_timeline_very_long_history_long.parquet"
    monthly_legacy_path = ROOT / "output" / "cycle_phase_timeline_short_macro.parquet"
    if annual_legacy_path.exists():
        legacy = pd.read_parquet(annual_legacy_path)
        for robust_column, legacy_column in (("Cycle_9y", "Cycle_100m"), ("Cycle_14y", "Cycle_200m")):
            rows.append(
                {
                    "robust_column": robust_column,
                    "legacy_column": legacy_column,
                    "correlation": safe_correlation(annual[robust_column], legacy[legacy_column]),
                }
            )
    if monthly_legacy_path.exists():
        legacy = pd.read_parquet(monthly_legacy_path)
        for robust_column, legacy_column in (("Cycle_21m", "Cycle_20m"), ("Cycle_42m", "Cycle_42m")):
            rows.append(
                {
                    "robust_column": robust_column,
                    "legacy_column": legacy_column,
                    "correlation": safe_correlation(monthly[robust_column], legacy[legacy_column]),
                }
            )
    return pd.DataFrame(rows)


def latest_phase_lines(timeline: pd.DataFrame) -> list[str]:
    latest = timeline.iloc[-1]
    lines = []
    for column in timeline.columns:
        if not column.startswith("Phase_") or pd.isna(latest[column]):
            continue
        phase = int(latest[column])
        lines.append(f"- {column.removeprefix('Phase_')}: {phase} ({PHASE_LABELS[phase]})")
    return lines


def main() -> None:
    panel_lookup = {spec.name: spec for spec in PANEL_SPECS}
    annual, annual_members = build_panel_timeline(panel_lookup["annual_long"])
    monthly, monthly_members = build_panel_timeline(panel_lookup["monthly_macro"])

    monthly_periods = monthly.index.to_period("M").unique().sort_values()
    monthly_index = monthly_periods.to_timestamp("M")
    monthly = monthly.groupby(monthly.index.to_period("M")).last()
    monthly.index = monthly.index.to_timestamp("M")
    monthly = monthly.reindex(monthly_index)
    annual_mapped = map_annual_to_monthly(annual, monthly_index)
    hybrid = pd.concat([annual_mapped, monthly], axis=1)

    annual.to_parquet(ANNUAL_OUT)
    monthly.to_parquet(MONTHLY_OUT)
    hybrid.to_parquet(HYBRID_OUT)
    pd.concat([annual_members, monthly_members], ignore_index=True).to_csv(MEMBERS_OUT, index=False)
    comparison = legacy_comparison(annual, monthly)
    comparison.to_csv(COMPARE_OUT, index=False)

    plot_timeline(
        annual,
        COMPOSITE_SPECS["annual_long"].periods,
        "Robust category-balanced annual cycle bands",
        ANNUAL_PLOT,
    )
    plot_timeline(
        monthly,
        COMPOSITE_SPECS["monthly_macro"].periods,
        "Robust category-balanced monthly cycle bands",
        MONTHLY_PLOT,
    )

    lines = [
        "# 数据支持的多周期组合时间轴",
        "",
        "## 周期带",
        "",
        "- 年频：9年与14年；14年用于替代不稳健的固定200个月点估计。",
        "- 月频：16.5个月、21个月与42个月；21个月保留为货币信用诊断，42个月为宏观库存周期主线。",
        "- 所有组合均先在类别内做符号对齐，再按类别等权，避免股票估值或单一数据源主导。",
        "",
        "## 最新阶段",
        "",
        *latest_phase_lines(hybrid),
        "",
        "## 与旧固定周期时间轴的相关性",
        "",
        comparison.round(4).to_markdown(index=False),
        "",
        "## 文件",
        "",
        f"- 年频时间轴：`{ANNUAL_OUT.relative_to(ROOT)}`",
        f"- 月频时间轴：`{MONTHLY_OUT.relative_to(ROOT)}`",
        f"- 混合时间轴：`{HYBRID_OUT.relative_to(ROOT)}`",
        f"- 成员与符号对齐：`{MEMBERS_OUT.relative_to(ROOT)}`",
        f"- 年频图：`{ANNUAL_PLOT.relative_to(ROOT)}`",
        f"- 月频图：`{MONTHLY_PLOT.relative_to(ROOT)}`",
        "",
        "## 限制",
        "",
        "这些时间轴仍由双边Butterworth滤波构建，适合历史解释；最新端点会修订，实时信号需要单边或状态空间确认层。",
        "",
    ]
    REPORT_OUT.write_text("\n".join(lines), encoding="utf-8")

    print("Wrote:", ANNUAL_OUT)
    print("Wrote:", MONTHLY_OUT)
    print("Wrote:", HYBRID_OUT)
    print("Wrote:", MEMBERS_OUT)
    print("Wrote:", COMPARE_OUT)
    print("Wrote:", REPORT_OUT)


if __name__ == "__main__":
    main()
