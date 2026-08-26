from __future__ import annotations

"""
Compare Gaussian FFT and Butterworth band-pass extraction on robust cycle bands.

Outputs quantify:
- component correlation and phase agreement;
- variance share;
- endpoint revision from truncated samples;
- multi-band reconstruction R-squared and residual share.
"""

from dataclasses import dataclass

import numpy as np
import pandas as pd

from cycle_robustness_core import (
    PANEL_SPECS,
    ROOT,
    annual_category,
    butterworth_component,
    gaussian_fft_component,
    load_metadata,
    phase_agreement,
    preprocess_series,
    regularize_series,
    safe_correlation,
    variance_share,
)


OUT_SERIES = ROOT / "output" / "cycle_filter_robustness_series.csv"
OUT_SUMMARY = ROOT / "output" / "cycle_filter_robustness_summary.csv"
OUT_RECONSTRUCTION = ROOT / "output" / "cycle_filter_reconstruction_summary.csv"
OUT_REPORT = ROOT / "output" / "cycle_filter_robustness_report.md"


@dataclass(frozen=True)
class FilterSpec:
    panel: str
    preprocess_methods: tuple[str, ...]
    evaluation_periods: tuple[tuple[str, float], ...]
    reconstruction_periods: tuple[tuple[str, float], ...]


FILTER_SPECS = {
    "annual_long": FilterSpec(
        panel="annual_long",
        preprocess_methods=("hp_100", "linear_detrend"),
        evaluation_periods=(
            ("juglar_9y", 9.0),
            ("long_band_14y", 14.0),
            ("legacy_200m", 200.0 / 12.0),
        ),
        reconstruction_periods=(("juglar_9y", 9.0), ("long_band_14y", 14.0)),
    ),
    "monthly_macro": FilterSpec(
        panel="monthly_macro",
        preprocess_methods=("canonical", "canonical_hp"),
        evaluation_periods=(
            ("market_16_5m", 16.5),
            ("legacy_20m", 20.0),
            ("market_24m", 24.0),
            ("inventory_42m", 42.0),
        ),
        reconstruction_periods=(
            ("short_market_16_5m", 16.5),
            ("liquidity_21m", 21.0),
            ("inventory_42m", 42.0),
        ),
    ),
}


def endpoint_revision(
    values: pd.Series,
    *,
    period: float,
    filter_name: str,
) -> tuple[float, float]:
    filter_function = gaussian_fft_component if filter_name == "gaussian" else butterworth_component
    full_component = filter_function(values, period)
    full_scale = float(full_component.std(ddof=0))
    if not np.isfinite(full_scale) or full_scale <= 1e-12:
        return np.nan, np.nan

    window = max(3, int(round(period * 0.25)))
    root_mean_square_revisions = []
    endpoint_revisions = []
    for fraction in (0.70, 0.80, 0.90):
        cutoff = int(round(len(values) * fraction))
        minimum = max(60, int(round(period * 3.0)))
        if cutoff < minimum or cutoff <= window:
            continue
        truncated_values = values.iloc[:cutoff]
        truncated_component = filter_function(truncated_values, period)
        full_window = full_component.iloc[cutoff - window : cutoff]
        truncated_window = truncated_component.iloc[-window:]
        difference = truncated_window.to_numpy(dtype="float64") - full_window.to_numpy(dtype="float64")
        root_mean_square_revisions.append(float(np.sqrt(np.mean(difference**2)) / full_scale))
        endpoint_revisions.append(float(abs(difference[-1]) / full_scale))
    if not root_mean_square_revisions:
        return np.nan, np.nan
    return float(np.mean(root_mean_square_revisions)), float(np.mean(endpoint_revisions))


def reconstruction_r_squared(base: pd.Series, components: list[pd.Series], trim: int) -> float:
    matrix = pd.concat([base.rename("base")] + components, axis=1).dropna()
    if len(matrix) <= 2 * trim + len(components) + 8:
        return np.nan
    if trim > 0:
        matrix = matrix.iloc[trim:-trim]
    target = matrix["base"].to_numpy(dtype="float64")
    design = matrix.drop(columns="base").to_numpy(dtype="float64")
    design = np.column_stack([np.ones(len(design)), design])
    coefficients, *_ = np.linalg.lstsq(design, target, rcond=None)
    fitted = design @ coefficients
    total = float(np.sum((target - target.mean()) ** 2))
    residual = float(np.sum((target - fitted) ** 2))
    if total <= 0.0:
        return np.nan
    return float(1.0 - residual / total)


def category_for_column(spec, metadata: pd.DataFrame, column: str) -> str:
    if spec.frequency == "A":
        return annual_category(column)
    return str(metadata.loc[column, "universe_category"])


def run_panel(spec) -> tuple[pd.DataFrame, pd.DataFrame]:
    panel = pd.read_parquet(spec.path)
    metadata = load_metadata(spec)
    filter_spec = FILTER_SPECS[spec.name]
    rows = []
    reconstruction_rows = []

    for preprocess_method in filter_spec.preprocess_methods:
        for column in panel.columns:
            value_type = str(metadata.loc[column, "value_type"]) if column in metadata.index else "level"
            regular = regularize_series(panel[column], spec.frequency, spec.min_points)
            if regular is None:
                continue
            base = preprocess_series(
                regular,
                value_type=value_type,
                frequency=spec.frequency,
                method=preprocess_method,
            )
            if base is None:
                continue
            category = category_for_column(spec, metadata, column)

            for period_label, period in filter_spec.evaluation_periods:
                gaussian = gaussian_fft_component(base, period)
                butterworth = butterworth_component(base, period)
                trim = max(3, int(round(period * 0.5)))
                gaussian_revision, gaussian_endpoint = endpoint_revision(
                    base,
                    period=period,
                    filter_name="gaussian",
                )
                butterworth_revision, butterworth_endpoint = endpoint_revision(
                    base,
                    period=period,
                    filter_name="butterworth",
                )
                rows.append(
                    {
                        "panel": spec.name,
                        "preprocess_method": preprocess_method,
                        "column": column,
                        "category": category,
                        "period_label": period_label,
                        "period": period,
                        "n_points": len(base),
                        "gaussian_butterworth_correlation": safe_correlation(gaussian, butterworth, trim),
                        "phase_agreement": phase_agreement(gaussian, butterworth, trim),
                        "gaussian_variance_share": variance_share(gaussian, base, trim),
                        "butterworth_variance_share": variance_share(butterworth, base, trim),
                        "gaussian_revision_rmse": gaussian_revision,
                        "butterworth_revision_rmse": butterworth_revision,
                        "gaussian_endpoint_revision": gaussian_endpoint,
                        "butterworth_endpoint_revision": butterworth_endpoint,
                    }
                )

            gaussian_components = [
                gaussian_fft_component(base, period).rename(label)
                for label, period in filter_spec.reconstruction_periods
            ]
            butterworth_components = [
                butterworth_component(base, period).rename(label)
                for label, period in filter_spec.reconstruction_periods
            ]
            maximum_period = max(period for _label, period in filter_spec.reconstruction_periods)
            reconstruction_trim = max(3, int(round(maximum_period * 0.5)))
            reconstruction_rows.append(
                {
                    "panel": spec.name,
                    "preprocess_method": preprocess_method,
                    "column": column,
                    "category": category,
                    "gaussian_reconstruction_r2": reconstruction_r_squared(
                        base,
                        gaussian_components,
                        reconstruction_trim,
                    ),
                    "butterworth_reconstruction_r2": reconstruction_r_squared(
                        base,
                        butterworth_components,
                        reconstruction_trim,
                    ),
                }
            )
    return pd.DataFrame(rows), pd.DataFrame(reconstruction_rows)


def balanced_aggregate(data: pd.DataFrame, group_columns: list[str], value_columns: list[str]) -> pd.DataFrame:
    category_medians = data.groupby(group_columns + ["category"], as_index=False)[value_columns].median()
    balanced = category_medians.groupby(group_columns, as_index=False)[value_columns].median()
    balanced["aggregation"] = "category_balanced"
    return balanced


def summarize_series(rows: pd.DataFrame) -> pd.DataFrame:
    group_columns = ["panel", "preprocess_method", "period_label", "period"]
    value_columns = [
        "gaussian_butterworth_correlation",
        "phase_agreement",
        "gaussian_variance_share",
        "butterworth_variance_share",
        "gaussian_revision_rmse",
        "butterworth_revision_rmse",
        "gaussian_endpoint_revision",
        "butterworth_endpoint_revision",
    ]
    all_series = rows.groupby(group_columns, as_index=False)[value_columns].median()
    all_series["aggregation"] = "all_series"
    balanced = balanced_aggregate(rows, group_columns, value_columns)
    return pd.concat([all_series, balanced], ignore_index=True)


def summarize_reconstruction(rows: pd.DataFrame) -> pd.DataFrame:
    group_columns = ["panel", "preprocess_method"]
    value_columns = ["gaussian_reconstruction_r2", "butterworth_reconstruction_r2"]
    all_series = rows.groupby(group_columns, as_index=False)[value_columns].median()
    all_series["aggregation"] = "all_series"
    balanced = balanced_aggregate(rows, group_columns, value_columns)
    result = pd.concat([all_series, balanced], ignore_index=True)
    result["gaussian_residual_share"] = 1.0 - result["gaussian_reconstruction_r2"]
    result["butterworth_residual_share"] = 1.0 - result["butterworth_reconstruction_r2"]
    return result


def write_report(summary: pd.DataFrame, reconstruction: pd.DataFrame) -> None:
    category_balanced = summary[summary["aggregation"] == "category_balanced"].copy()
    correlation_min = float(category_balanced["gaussian_butterworth_correlation"].min())
    correlation_max = float(category_balanced["gaussian_butterworth_correlation"].max())
    phase_min = float(category_balanced["phase_agreement"].min())
    phase_max = float(category_balanced["phase_agreement"].max())
    monthly_reconstruction = reconstruction[
        (reconstruction["panel"] == "monthly_macro")
        & (reconstruction["aggregation"] == "category_balanced")
    ]
    annual_hp_reconstruction = reconstruction[
        (reconstruction["panel"] == "annual_long")
        & (reconstruction["preprocess_method"] == "hp_100")
        & (reconstruction["aggregation"] == "category_balanced")
    ].iloc[0]
    annual_linear_reconstruction = reconstruction[
        (reconstruction["panel"] == "annual_long")
        & (reconstruction["preprocess_method"] == "linear_detrend")
        & (reconstruction["aggregation"] == "category_balanced")
    ].iloc[0]
    display_columns = [
        "panel",
        "preprocess_method",
        "period_label",
        "period",
        "gaussian_butterworth_correlation",
        "phase_agreement",
        "gaussian_variance_share",
        "butterworth_variance_share",
        "gaussian_revision_rmse",
        "butterworth_revision_rmse",
    ]
    lines = [
        "# 周期滤波稳健性比较：Gaussian vs Butterworth",
        "",
        "## 结论先行",
        "",
        f"- 两种滤波器在样本中段的一致性较高：分类等权相关系数约为 {correlation_min:.2f}-{correlation_max:.2f}，相位一致度约为 {phase_min:.2f}-{phase_max:.2f}；但幅度和端点修订仍明显。",
        f"- 月频主要周期带联合解释率约为 {monthly_reconstruction[['gaussian_reconstruction_r2', 'butterworth_reconstruction_r2']].min().min():.0%}-{monthly_reconstruction[['gaussian_reconstruction_r2', 'butterworth_reconstruction_r2']].max().max():.0%}，即仍有约 {monthly_reconstruction[['gaussian_residual_share', 'butterworth_residual_share']].min().min():.0%}-{monthly_reconstruction[['gaussian_residual_share', 'butterworth_residual_share']].max().max():.0%} 无法由这些窄频带解释；高残差是实证结果，不等于程序错误。",
        f"- 年频长周期结论对预处理高度敏感：HP(100)下分类等权解释率约为 {min(annual_hp_reconstruction['gaussian_reconstruction_r2'], annual_hp_reconstruction['butterworth_reconstruction_r2']):.0%}-{max(annual_hp_reconstruction['gaussian_reconstruction_r2'], annual_hp_reconstruction['butterworth_reconstruction_r2']):.0%}，线性去趋势下仅约 {min(annual_linear_reconstruction['gaussian_reconstruction_r2'], annual_linear_reconstruction['butterworth_reconstruction_r2']):.0%}-{max(annual_linear_reconstruction['gaussian_reconstruction_r2'], annual_linear_reconstruction['butterworth_reconstruction_r2']):.0%}。",
        "- Gaussian FFT 存在循环延拓假设，Butterworth 零相位滤波同样使用未来数据；两者都适合历史分解，不宜直接充当实时交易信号。",
        "- 正式阶段建议保存两套历史分解，但实时状态应另建单边滤波或状态空间模型作为确认层。",
        "",
        "## 分类等权的滤波比较",
        "",
        category_balanced[display_columns].round(4).to_markdown(index=False),
        "",
        "## 多频带联合解释率",
        "",
        reconstruction.round(4).to_markdown(index=False),
        "",
        "## 指标解释",
        "",
        "- `gaussian_butterworth_correlation`：剔除两端后，两种滤波成分的相关系数。",
        "- `phase_agreement`：Hilbert相位差的平均余弦，1表示同相，0表示无稳定关系。",
        "- `variance_share`：单一窄频带成分的方差占比，不应期待接近100%。",
        "- `revision_rmse`：截断样本与完整样本在历史端点附近的修订幅度，以完整成分标准差归一化。",
        "- `reconstruction_r2`：多个周期成分联合回归解释预处理序列的样本内R²，仅用于分解诊断，不代表预测能力。",
        "",
        f"- 单指标明细：`{OUT_SERIES.relative_to(ROOT)}`",
        f"- 汇总表：`{OUT_SUMMARY.relative_to(ROOT)}`",
        f"- 联合解释率：`{OUT_RECONSTRUCTION.relative_to(ROOT)}`",
        "",
    ]
    OUT_REPORT.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    series_frames = []
    reconstruction_frames = []
    for panel_spec in PANEL_SPECS:
        series_rows, reconstruction_rows = run_panel(panel_spec)
        series_frames.append(series_rows)
        reconstruction_frames.append(reconstruction_rows)
    series = pd.concat(series_frames, ignore_index=True)
    reconstruction_series = pd.concat(reconstruction_frames, ignore_index=True)
    summary = summarize_series(series)
    reconstruction = summarize_reconstruction(reconstruction_series)

    OUT_SERIES.parent.mkdir(parents=True, exist_ok=True)
    series.to_csv(OUT_SERIES, index=False)
    summary.to_csv(OUT_SUMMARY, index=False)
    reconstruction.to_csv(OUT_RECONSTRUCTION, index=False)
    write_report(summary, reconstruction)

    print("Wrote:", OUT_SERIES)
    print("Wrote:", OUT_SUMMARY)
    print("Wrote:", OUT_RECONSTRUCTION)
    print("Wrote:", OUT_REPORT)


if __name__ == "__main__":
    main()
