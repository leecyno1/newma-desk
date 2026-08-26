from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import sys

import numpy as np
import pandas as pd

from backtest_cycle_style_rotation_v3 import (
    DEFAULT_COST_BPS,
    MIN_TRAIN_MONTHS,
    SIGNAL_SPECS,
)
from build_realtime_cycle_signals import build_annual_signals, build_monthly_signals
from cycle_realtime_core import ROOT


REPORT_OUT = ROOT / "output" / "cycle_investment_application_verification.md"


@dataclass
class CheckResult:
    name: str
    passed: bool
    detail: str


def _max_difference(left: pd.DataFrame, right: pd.DataFrame) -> tuple[float, bool]:
    aligned_right = right.reindex(index=left.index, columns=left.columns)
    same_missingness = left.isna().equals(aligned_right.isna())
    difference = (left - aligned_right).abs().to_numpy(dtype="float64")
    finite = difference[np.isfinite(difference)]
    return (float(finite.max()) if finite.size else 0.0), same_missingness


def _append(
    checks: list[CheckResult],
    name: str,
    passed: bool,
    detail: str,
) -> None:
    checks.append(CheckResult(name=name, passed=bool(passed), detail=detail))


def main() -> None:
    required_paths = (
        ROOT / "output" / "cycle_realtime_signals_monthly.parquet",
        ROOT / "output" / "cycle_realtime_signals_annual.parquet",
        ROOT / "output" / "cycle_realtime_signals_hybrid.parquet",
        ROOT / "output" / "cycle_realtime_signal_revision.csv",
        ROOT / "output" / "cycle_style_rotation_backtest_returns.parquet",
        ROOT / "output" / "cycle_style_rotation_backtest_weights.csv",
        ROOT / "output" / "cycle_style_rotation_backtest_summary.csv",
        ROOT / "output" / "cycle_style_rotation_backtest_sensitivity.csv",
        ROOT / "output" / "cycle_style_rotation_backtest.md",
        ROOT / "output" / "CYCLE_INVESTMENT_APPLICATION_V3.md",
    )
    checks: list[CheckResult] = []
    missing_paths = [str(path) for path in required_paths if not path.exists()]
    _append(
        checks,
        "required_outputs_exist",
        not missing_paths,
        "all required files present" if not missing_paths else f"missing: {missing_paths}",
    )
    if missing_paths:
        _write_report(checks)
        raise SystemExit(1)

    monthly = pd.read_parquet(required_paths[0])
    annual = pd.read_parquet(required_paths[1])
    hybrid = pd.read_parquet(required_paths[2])
    revision = pd.read_csv(required_paths[3])
    backtest_returns = pd.read_parquet(required_paths[4])
    weights = pd.read_csv(
        required_paths[5],
        parse_dates=["date", "signal_date", "training_start", "training_end"],
    )
    summary = pd.read_csv(required_paths[6], index_col=0)
    sensitivity = pd.read_csv(required_paths[7])
    v3_text = required_paths[9].read_text(encoding="utf-8")

    expected_monthly_index = monthly.index.to_period("M").to_timestamp("M")
    _append(
        checks,
        "monthly_index_is_unique_month_end",
        monthly.index.is_unique and monthly.index.equals(expected_monthly_index),
        f"rows={len(monthly)}, duplicates={monthly.index.duplicated().sum()}",
    )
    expected_annual_index = pd.Index(
        range(int(annual.index.min()), int(annual.index.max()) + 1), name=annual.index.name
    )
    _append(
        checks,
        "annual_index_is_unique_contiguous",
        annual.index.is_unique and annual.index.equals(expected_annual_index),
        f"rows={len(annual)}, range={annual.index.min()}-{annual.index.max()}",
    )
    _append(
        checks,
        "hybrid_matches_monthly_index",
        hybrid.index.equals(monthly.index) and hybrid.index.is_unique,
        f"hybrid_rows={len(hybrid)}, monthly_rows={len(monthly)}",
    )

    truncated_monthly, _, _ = build_monthly_signals("2018-12-31")
    realtime_monthly_columns = [
        column
        for column in monthly.columns
        if column.startswith(("RT_Cycle_", "RT_Phase_", "Confirmed_Phase_"))
    ]
    full_monthly_vintage = monthly.loc[:"2018-12-31", realtime_monthly_columns]
    monthly_difference, monthly_missingness = _max_difference(
        full_monthly_vintage,
        truncated_monthly[realtime_monthly_columns],
    )
    _append(
        checks,
        "monthly_cutoff_reconstruction_is_exact",
        monthly_difference <= 1e-10 and monthly_missingness,
        f"max_abs_difference={monthly_difference:.3e}, missingness_equal={monthly_missingness}",
    )

    truncated_annual, _, _ = build_annual_signals(2018)
    realtime_annual_columns = [
        column
        for column in annual.columns
        if column.startswith(("RT_Cycle_", "RT_Phase_", "Confirmed_Phase_"))
    ]
    full_annual_vintage = annual.loc[:2018, realtime_annual_columns]
    annual_difference, annual_missingness = _max_difference(
        full_annual_vintage,
        truncated_annual[realtime_annual_columns],
    )
    _append(
        checks,
        "annual_cutoff_reconstruction_is_exact",
        annual_difference <= 1e-10 and annual_missingness,
        f"max_abs_difference={annual_difference:.3e}, missingness_equal={annual_missingness}",
    )

    annual_mapping_columns = [
        column
        for column in annual.columns
        if column.startswith(("RT_Cycle_", "RT_Phase_", "Confirmed_Phase_"))
    ]
    mapping_differences = []
    for year in sorted(hybrid.index.year.unique()):
        source_year = int(year) - 1
        if source_year not in annual.index:
            continue
        actual = hybrid.loc[hybrid.index.year == year, annual_mapping_columns]
        expected = annual.loc[source_year, annual_mapping_columns]
        difference = actual.subtract(expected, axis=1).abs().to_numpy(dtype="float64")
        finite = difference[np.isfinite(difference)]
        if finite.size:
            mapping_differences.append(float(finite.max()))
    mapping_max = max(mapping_differences, default=0.0)
    _append(
        checks,
        "annual_signals_are_mapped_with_one_year_lag",
        mapping_max <= 1e-10,
        f"max_abs_difference={mapping_max:.3e}",
    )

    phase_columns = [column for spec in SIGNAL_SPECS for column in spec.phase_columns]
    _append(
        checks,
        "backtest_uses_confirmed_realtime_phases_only",
        all(column.startswith("Confirmed_Phase_") and "Smooth" not in column for column in phase_columns),
        f"phase_columns={len(phase_columns)}",
    )

    weight_columns = [column for column in weights.columns if column.startswith("weight_")]
    weight_sum_error = float((weights[weight_columns].sum(axis=1) - 1.0).abs().max())
    weight_min = float(weights[weight_columns].min().min())
    weight_max = float(weights[weight_columns].max().max())
    _append(
        checks,
        "weights_are_long_only_and_fully_invested",
        weight_sum_error <= 1e-10 and weight_min >= -1e-12 and weight_max <= 1.0 + 1e-12,
        f"max_sum_error={weight_sum_error:.3e}, bounds=({weight_min:.4f}, {weight_max:.4f})",
    )

    signal_lag_ok = bool((weights["signal_date"] < weights["date"]).all())
    training_lag_ok = bool((weights["training_end"] < weights["date"]).all())
    previous_month = weights["date"].dt.to_period("M") - 1
    exact_one_month_lag = bool((weights["signal_date"].dt.to_period("M") == previous_month).all())
    _append(
        checks,
        "signal_and_training_dates_precede_returns",
        signal_lag_ok and training_lag_ok and exact_one_month_lag,
        (
            f"signal_lag_ok={signal_lag_ok}, training_lag_ok={training_lag_ok}, "
            f"exact_one_month_lag={exact_one_month_lag}"
        ),
    )
    _append(
        checks,
        "minimum_training_window_is_enforced",
        int(weights["training_months"].min()) >= MIN_TRAIN_MONTHS,
        f"minimum_training_months={int(weights['training_months'].min())}",
    )

    cost_formula_error = float(
        (
            weights["cost"]
            - weights["turnover"] * DEFAULT_COST_BPS / 10000.0
        )
        .abs()
        .max()
    )
    net_formula_error = float(
        (weights["net_return"] - (weights["gross_return"] - weights["cost"]))
        .abs()
        .max()
    )
    _append(
        checks,
        "transaction_cost_and_net_return_formulas_hold",
        cost_formula_error <= 1e-12 and net_formula_error <= 1e-12,
        f"cost_error={cost_formula_error:.3e}, net_error={net_formula_error:.3e}",
    )

    active_net_columns = [column for column in backtest_returns if column.endswith("_Net")]
    net_exceeds_gross = 0
    for net_column in active_net_columns:
        gross_column = net_column.removesuffix("_Net") + "_Gross"
        net_exceeds_gross += int(
            (backtest_returns[net_column] > backtest_returns[gross_column] + 1e-12).sum()
        )
    _append(
        checks,
        "backtest_return_panel_is_complete_and_net_not_above_gross",
        int(backtest_returns.isna().sum().sum()) == 0 and net_exceeds_gross == 0,
        f"shape={backtest_returns.shape}, net_above_gross={net_exceeds_gross}",
    )

    default_sensitivity = sensitivity[
        sensitivity["sensitivity_type"].eq("cost_bps")
        & sensitivity["sensitivity_value"].eq(DEFAULT_COST_BPS)
    ].iloc[0]
    primary_summary = summary.loc["V2_CB_All_Expanding"]
    metric_columns = ("cagr", "sharpe", "max_drawdown", "annual_turnover")
    sensitivity_error = max(
        abs(float(default_sensitivity[column]) - float(primary_summary[column]))
        for column in metric_columns
    )
    _append(
        checks,
        "default_sensitivity_matches_primary_summary",
        sensitivity_error <= 1e-12,
        f"max_metric_difference={sensitivity_error:.3e}",
    )

    cost_rows = sensitivity[sensitivity["sensitivity_type"].eq("cost_bps")].sort_values(
        "sensitivity_value"
    )
    cost_monotonic = bool((cost_rows["cagr"].diff().dropna() <= 1e-12).all())
    _append(
        checks,
        "higher_costs_do_not_improve_cagr",
        cost_monotonic,
        f"tested_costs={cost_rows['sensitivity_value'].tolist()}",
    )

    revision_required = {
        "correlation",
        "phase_match",
        "median_abs_revision",
        "best_confirmation_lag",
    }
    _append(
        checks,
        "revision_table_contains_required_diagnostics",
        revision_required.issubset(revision.columns) and len(revision) >= 20,
        f"rows={len(revision)}, columns={sorted(revision_required)}",
    )

    decision_language = "研究用途，暂不进入实盘/模拟盘" in v3_text
    _append(
        checks,
        "v3_report_records_no_deployment_decision",
        decision_language,
        "explicit research-only decision found" if decision_language else "decision text missing",
    )

    _write_report(checks)
    failures = [check for check in checks if not check.passed]
    print(f"Verification: {len(checks) - len(failures)}/{len(checks)} checks passed")
    if failures:
        for failure in failures:
            print(f"FAIL {failure.name}: {failure.detail}")
        raise SystemExit(1)


def _write_report(checks: list[CheckResult]) -> None:
    passed = sum(check.passed for check in checks)
    rows = pd.DataFrame(
        [
            {
                "check": check.name,
                "status": "PASS" if check.passed else "FAIL",
                "detail": check.detail,
            }
            for check in checks
        ]
    )
    lines = [
        "# 周期投资应用端到端验证",
        "",
        f"- 结果：`{passed}/{len(checks)}` 项通过。",
        "- 验证覆盖：输出完整性、截断因果重建、年频可用性滞后、信号/训练日期、权重约束、成本公式、敏感性一致性及V3决策语言。",
        "",
        rows.to_markdown(index=False),
    ]
    REPORT_OUT.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    main()
