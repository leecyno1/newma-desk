from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from cycle_realtime_core import (
    ANNUAL_GROWTH_CATEGORIES,
    ANNUAL_PERIODS,
    MONTHLY_GROWTH_CATEGORIES,
    MONTHLY_PERIODS,
    PHASE_LABELS,
    ROOT,
    build_component_cache,
    build_signal_view,
    map_annual_to_monthly,
    phase_label,
    prepare_transformed_panel,
)


MONTHLY_PANEL_PATH = ROOT / "data" / "research_input_monthly_macro.parquet"
MONTHLY_METADATA_PATH = ROOT / "output" / "research_input_monthly_macro_selection.csv"
ANNUAL_PANEL_PATH = ROOT / "data" / "research_input_annual_long.parquet"
ANNUAL_METADATA_PATH = ROOT / "output" / "research_input_annual_long_selection.csv"

MONTHLY_OUT = ROOT / "output" / "cycle_realtime_signals_monthly.parquet"
ANNUAL_OUT = ROOT / "output" / "cycle_realtime_signals_annual.parquet"
HYBRID_OUT = ROOT / "output" / "cycle_realtime_signals_hybrid.parquet"
MEMBERS_OUT = ROOT / "output" / "cycle_realtime_signal_members.csv"
REVISION_OUT = ROOT / "output" / "cycle_realtime_signal_revision.csv"
REPORT_OUT = ROOT / "output" / "cycle_realtime_signal_report.md"
MONTHLY_PLOT = ROOT / "output" / "cycle_realtime_signals_monthly.png"
ANNUAL_PLOT = ROOT / "output" / "cycle_realtime_signals_annual.png"


MONTHLY_EQUITY_CATEGORY = "股票市场与估值（Equity Market & Valuation）"
ANNUAL_MARKET_CATEGORY = "markets"


def _truncate_panel(panel: pd.DataFrame, cutoff: str | int | None) -> pd.DataFrame:
    if cutoff is None:
        return panel
    if isinstance(cutoff, str):
        return panel.loc[pd.to_datetime(panel.index) <= pd.Timestamp(cutoff)]
    return panel.loc[pd.to_numeric(panel.index, errors="coerce") <= int(cutoff)]


def build_monthly_signals(
    cutoff: str | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.Series]:
    panel = _truncate_panel(pd.read_parquet(MONTHLY_PANEL_PATH), cutoff)
    metadata = pd.read_csv(MONTHLY_METADATA_PATH)
    transformed, categories = prepare_transformed_panel(
        panel,
        metadata,
        frequency="M",
        min_history=24,
    )
    cache = build_component_cache(transformed, MONTHLY_PERIODS)
    all_categories = sorted(categories.dropna().unique())
    macro_categories = [
        category for category in all_categories if category != MONTHLY_EQUITY_CATEGORY
    ]

    category_balanced, category_diagnostics = build_signal_view(
        cache,
        MONTHLY_PERIODS,
        categories,
        view_name="CB",
        growth_categories=MONTHLY_GROWTH_CATEGORIES,
        included_categories=all_categories,
        min_observations=24,
        phase_smoothing=3,
        confirmation_observations=2,
    )
    macro_only, macro_diagnostics = build_signal_view(
        cache,
        MONTHLY_PERIODS,
        categories,
        view_name="Macro",
        growth_categories=MONTHLY_GROWTH_CATEGORIES,
        included_categories=macro_categories,
        min_observations=24,
        phase_smoothing=3,
        confirmation_observations=2,
    )
    diagnostics = pd.concat([category_diagnostics, macro_diagnostics], ignore_index=True)
    diagnostics["frequency"] = "M"
    return pd.concat([category_balanced, macro_only], axis=1), diagnostics, categories


def build_annual_signals(
    cutoff: int | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.Series]:
    panel = _truncate_panel(pd.read_parquet(ANNUAL_PANEL_PATH), cutoff)
    metadata = pd.read_csv(ANNUAL_METADATA_PATH)
    transformed, categories = prepare_transformed_panel(
        panel,
        metadata,
        frequency="A",
        min_history=20,
    )
    cache = build_component_cache(transformed, ANNUAL_PERIODS)
    all_categories = sorted(categories.dropna().unique())
    macro_categories = [category for category in all_categories if category != ANNUAL_MARKET_CATEGORY]

    category_balanced, category_diagnostics = build_signal_view(
        cache,
        ANNUAL_PERIODS,
        categories,
        view_name="CB",
        growth_categories=ANNUAL_GROWTH_CATEGORIES,
        included_categories=all_categories,
        min_observations=20,
        phase_smoothing=2,
        confirmation_observations=1,
    )
    macro_only, macro_diagnostics = build_signal_view(
        cache,
        ANNUAL_PERIODS,
        categories,
        view_name="Macro",
        growth_categories=ANNUAL_GROWTH_CATEGORIES,
        included_categories=macro_categories,
        min_observations=20,
        phase_smoothing=2,
        confirmation_observations=1,
    )
    diagnostics = pd.concat([category_diagnostics, macro_diagnostics], ignore_index=True)
    diagnostics["frequency"] = "A"
    return pd.concat([category_balanced, macro_only], axis=1), diagnostics, categories


def build_signal_bundle(
    *,
    monthly_cutoff: str | None = None,
    annual_cutoff: int | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    monthly, monthly_diagnostics, _monthly_categories = build_monthly_signals(monthly_cutoff)
    annual, annual_diagnostics, _annual_categories = build_annual_signals(annual_cutoff)
    annual_mapped = map_annual_to_monthly(annual, monthly.index, availability_lag_years=1)
    hybrid = pd.concat([annual_mapped, monthly], axis=1)
    diagnostics = pd.concat([annual_diagnostics, monthly_diagnostics], ignore_index=True)
    return monthly, annual, hybrid, diagnostics


def _comparison_metrics(
    realtime: pd.Series,
    reference: pd.Series,
    realtime_phase: pd.Series,
    reference_phase: pd.Series,
    max_lag: int,
) -> dict[str, float | int]:
    aligned = pd.concat([realtime, reference], axis=1).dropna()
    phase_aligned = pd.concat([realtime_phase, reference_phase], axis=1).dropna()
    if aligned.empty:
        return {
            "correlation": np.nan,
            "phase_match": np.nan,
            "median_abs_revision": np.nan,
            "endpoint_revision": np.nan,
            "best_confirmation_lag": np.nan,
            "best_lag_correlation": np.nan,
        }

    best_lag = 0
    best_correlation = -np.inf
    for lag in range(max_lag + 1):
        candidate = pd.concat([realtime, reference.shift(lag)], axis=1).dropna()
        if len(candidate) < 12:
            continue
        correlation = float(candidate.iloc[:, 0].corr(candidate.iloc[:, 1]))
        if np.isfinite(correlation) and correlation > best_correlation:
            best_lag = lag
            best_correlation = correlation

    return {
        "correlation": float(aligned.iloc[:, 0].corr(aligned.iloc[:, 1])),
        "phase_match": float((phase_aligned.iloc[:, 0] == phase_aligned.iloc[:, 1]).mean())
        if not phase_aligned.empty
        else np.nan,
        "median_abs_revision": float((aligned.iloc[:, 0] - aligned.iloc[:, 1]).abs().median()),
        "endpoint_revision": float(aligned.iloc[-1, 0] - aligned.iloc[-1, 1]),
        "best_confirmation_lag": int(best_lag),
        "best_lag_correlation": float(best_correlation) if np.isfinite(best_correlation) else np.nan,
    }


def build_revision_table(monthly: pd.DataFrame, annual: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for frequency, signals, periods in (
        ("M", monthly, MONTHLY_PERIODS),
        ("A", annual, ANNUAL_PERIODS),
    ):
        for view in ("CB", "Macro"):
            for period_spec in periods:
                realtime_column = f"RT_Cycle_{view}_{period_spec.label}"
                smoother_column = f"Smooth_Cycle_{view}_{period_spec.label}"
                realtime_phase_column = f"RT_Phase_{view}_{period_spec.label}"
                smoother_phase_column = f"Smooth_Phase_{view}_{period_spec.label}"
                metrics = _comparison_metrics(
                    signals[realtime_column],
                    signals[smoother_column],
                    signals[realtime_phase_column],
                    signals[smoother_phase_column],
                    max_lag=max(1, int(round(period_spec.period / 2.0))),
                )
                rows.append(
                    {
                        "frequency": frequency,
                        "view": view,
                        "period_label": period_spec.label,
                        "period": period_spec.period,
                        "reference": "state_space_full_sample_smoother",
                        **metrics,
                    }
                )

    external_references = [
        (
            "M",
            monthly,
            ROOT / "output" / "cycle_phase_timeline_robust_monthly.parquet",
            "two_sided_v2",
            {"16_5m": "16_5m", "21m": "21m", "42m": "42m"},
        ),
        (
            "M",
            monthly,
            ROOT / "output" / "cycle_phase_timeline_short_macro.parquet",
            "two_sided_v1",
            {"20m": "20m", "42m": "42m"},
        ),
        (
            "A",
            annual,
            ROOT / "output" / "cycle_phase_timeline_robust_annual.parquet",
            "two_sided_v2",
            {"9y": "9y", "14y": "14y"},
        ),
        (
            "A",
            annual,
            ROOT / "output" / "cycle_phase_timeline_very_long_history_long.parquet",
            "two_sided_v1",
            {"8_33y": "100m", "16_67y": "200m"},
        ),
    ]
    period_lookup = {
        period.label: period.period for period in tuple(MONTHLY_PERIODS) + tuple(ANNUAL_PERIODS)
    }
    for frequency, signals, path, reference_name, mapping in external_references:
        if not path.exists():
            continue
        reference = pd.read_parquet(path)
        for signal_label, reference_label in mapping.items():
            realtime_column = f"RT_Cycle_CB_{signal_label}"
            realtime_phase_column = f"RT_Phase_CB_{signal_label}"
            reference_column = f"Cycle_{reference_label}"
            reference_phase_column = f"Phase_{reference_label}"
            if reference_column not in reference or reference_phase_column not in reference:
                continue
            metrics = _comparison_metrics(
                signals[realtime_column],
                reference[reference_column],
                signals[realtime_phase_column],
                reference[reference_phase_column],
                max_lag=max(1, int(round(period_lookup[signal_label] / 2.0))),
            )
            rows.append(
                {
                    "frequency": frequency,
                    "view": "CB",
                    "period_label": signal_label,
                    "period": period_lookup[signal_label],
                    "reference": reference_name,
                    **metrics,
                }
            )
    return pd.DataFrame(rows)


def _plot_signal_comparison(
    signals: pd.DataFrame,
    labels: tuple[str, ...],
    title: str,
    output_path: Path,
) -> None:
    figure, axes = plt.subplots(len(labels), 1, figsize=(14, 3.0 * len(labels)), sharex=True)
    if len(labels) == 1:
        axes = [axes]
    for axis, label in zip(axes, labels):
        axis.plot(
            signals.index,
            signals[f"Smooth_Cycle_CB_{label}"],
            color="#B0BEC5",
            linewidth=1.4,
            label="Full-sample smoother",
        )
        axis.plot(
            signals.index,
            signals[f"RT_Cycle_CB_{label}"],
            color="#1565C0",
            linewidth=1.1,
            label="Real-time filter",
        )
        axis.axhline(0.0, color="#777777", linewidth=0.7)
        axis.set_ylabel(label)
    axes[0].legend(loc="upper right")
    figure.suptitle(title, y=0.995)
    figure.tight_layout()
    figure.savefig(output_path, dpi=150)
    plt.close(figure)


def _latest_phase_table(signals: pd.DataFrame, frequency: str) -> pd.DataFrame:
    rows = []
    latest_index = signals.index[-1]
    for column in signals.columns:
        if not column.startswith("Confirmed_Phase_"):
            continue
        value = signals[column].dropna().iloc[-1] if signals[column].notna().any() else np.nan
        _, _, view, period_label = column.split("_", 3)
        rows.append(
            {
                "frequency": frequency,
                "as_of": latest_index,
                "view": view,
                "period": period_label,
                "phase": int(value) if np.isfinite(value) else np.nan,
                "phase_label": phase_label(value),
            }
        )
    return pd.DataFrame(rows)


def write_report(
    monthly: pd.DataFrame,
    annual: pd.DataFrame,
    revision: pd.DataFrame,
    diagnostics: pd.DataFrame,
) -> None:
    latest = pd.concat(
        [_latest_phase_table(monthly, "monthly"), _latest_phase_table(annual, "annual")],
        ignore_index=True,
    )
    smoother_rows = revision[revision["reference"].eq("state_space_full_sample_smoother")]
    external_rows = revision[~revision["reference"].eq("state_space_full_sample_smoother")]
    sign_summary = (
        diagnostics.groupby(["frequency", "view", "period_label"], dropna=False)
        .agg(members=("member", "count"), median_sign_flips=("sign_flips", "median"))
        .reset_index()
    )

    lines = [
        "# 实时周期信号与修订跟踪",
        "",
        "## 结论",
        "",
        "- 已将历史用的双边 Butterworth/HP 相位替换为只使用当期及过去数据的阻尼谐波状态空间滤波器。",
        "- 月频信号要求相位连续出现两个月才确认；年频信号按年度确认，并在映射至月度投资时额外滞后一年。",
        "- 同时保留类别等权（CB）和剔除股票估值类别的宏观-only视图，后续回测将把两者作为稳健性对照。",
        "- `Smooth_*` 仅用于衡量事后修订，不进入任何投资回测。",
        "",
        "## 方法约束",
        "",
        "- 所有原始序列先归一化为每个自然月一个月末观测。",
        "- 水平/价格序列使用仅依赖过去值的一阶变化，标准化均使用滞后一阶的扩展窗口均值与波动率。",
        "- 成员方向、类别方向和最终增长方向均使用扩展窗口相关性并设置滞后，不使用未来样本确定符号。",
        "- 固定周期只决定状态转移频率；V2 为 16.5m/21m/42m 与 9y/14y，V1 对照为 20m/42m 与 100m/200m。",
        "",
        "## 最新确认相位",
        "",
        latest.to_markdown(index=False),
        "",
        "## 状态空间实时值相对最终平滑值",
        "",
        smoother_rows.round(4).to_markdown(index=False),
        "",
        "## 相对历史双边时间轴",
        "",
        external_rows.round(4).to_markdown(index=False),
        "",
        "## 成员方向稳定性",
        "",
        sign_summary.round(2).to_markdown(index=False),
        "",
        "## 输出",
        "",
        f"- 月频信号：`{MONTHLY_OUT}`",
        f"- 年频信号：`{ANNUAL_OUT}`",
        f"- 月频混合信号：`{HYBRID_OUT}`",
        f"- 修订指标：`{REVISION_OUT}`",
        f"- 成员诊断：`{MEMBERS_OUT}`",
        f"- 月频图：`{MONTHLY_PLOT}`",
        f"- 年频图：`{ANNUAL_PLOT}`",
    ]
    REPORT_OUT.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    monthly, annual, hybrid, diagnostics = build_signal_bundle()
    revision = build_revision_table(monthly, annual)

    MONTHLY_OUT.parent.mkdir(parents=True, exist_ok=True)
    monthly.to_parquet(MONTHLY_OUT)
    annual.to_parquet(ANNUAL_OUT)
    hybrid.to_parquet(HYBRID_OUT)
    diagnostics.to_csv(MEMBERS_OUT, index=False)
    revision.to_csv(REVISION_OUT, index=False)

    _plot_signal_comparison(
        monthly,
        ("16_5m", "21m", "42m"),
        "Real-time versus full-sample monthly cycle estimates",
        MONTHLY_PLOT,
    )
    _plot_signal_comparison(
        annual,
        ("9y", "14y"),
        "Real-time versus full-sample annual cycle estimates",
        ANNUAL_PLOT,
    )
    write_report(monthly, annual, revision, diagnostics)
    print(f"Wrote {MONTHLY_OUT}")
    print(f"Wrote {ANNUAL_OUT}")
    print(f"Wrote {HYBRID_OUT}")
    print(f"Wrote {REPORT_OUT}")


if __name__ == "__main__":
    main()
