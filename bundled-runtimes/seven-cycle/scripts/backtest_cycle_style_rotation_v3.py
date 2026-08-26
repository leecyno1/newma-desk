from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from cycle_realtime_core import PHASE_LABELS, ROOT


ASSET_COLUMNS = (
    "idx_hs300_ret_m",
    "idx_csi500_ret_m",
    "idx_csi1000_ret_m",
)


ASSET_LABELS = {
    "idx_hs300_ret_m": "HS300",
    "idx_csi500_ret_m": "CSI500",
    "idx_csi1000_ret_m": "CSI1000",
}


RETURNS_PATH = ROOT / "data" / "huatai_db_monthly.parquet"
SIGNALS_PATH = ROOT / "output" / "cycle_realtime_signals_hybrid.parquet"
RETURNS_OUT = ROOT / "output" / "cycle_style_rotation_backtest_returns.parquet"
WEIGHTS_OUT = ROOT / "output" / "cycle_style_rotation_backtest_weights.csv"
SUMMARY_OUT = ROOT / "output" / "cycle_style_rotation_backtest_summary.csv"
SUBPERIOD_OUT = ROOT / "output" / "cycle_style_rotation_backtest_subperiod.csv"
SENSITIVITY_OUT = ROOT / "output" / "cycle_style_rotation_backtest_sensitivity.csv"
CONDITIONAL_OUT = ROOT / "output" / "cycle_style_rotation_conditional_returns.csv"
REPORT_OUT = ROOT / "output" / "cycle_style_rotation_backtest.md"
PLOT_OUT = ROOT / "output" / "cycle_style_rotation_backtest.png"


DEFAULT_COST_BPS = 15.0
DEFAULT_PRIOR_STRENGTH = 24.0
DEFAULT_TEMPERATURE = 0.015
MIN_TRAIN_MONTHS = 60


@dataclass(frozen=True)
class SignalSpec:
    name: str
    phase_columns: tuple[str, ...]
    role: str


@dataclass(frozen=True)
class RunSpec:
    signal_spec: SignalSpec
    mode: str
    rolling_window: int | None = None

    @property
    def name(self) -> str:
        if self.mode == "expanding":
            return f"{self.signal_spec.name}_Expanding"
        return f"{self.signal_spec.name}_Rolling{self.rolling_window}"


SIGNAL_SPECS = (
    SignalSpec(
        "V2_CB_All",
        (
            "Confirmed_Phase_CB_9y",
            "Confirmed_Phase_CB_14y",
            "Confirmed_Phase_CB_16_5m",
            "Confirmed_Phase_CB_21m",
            "Confirmed_Phase_CB_42m",
        ),
        "primary",
    ),
    SignalSpec(
        "V2_CB_Short",
        (
            "Confirmed_Phase_CB_16_5m",
            "Confirmed_Phase_CB_21m",
            "Confirmed_Phase_CB_42m",
        ),
        "short_cycle_ablation",
    ),
    SignalSpec(
        "V2_Macro_All",
        (
            "Confirmed_Phase_Macro_9y",
            "Confirmed_Phase_Macro_14y",
            "Confirmed_Phase_Macro_16_5m",
            "Confirmed_Phase_Macro_21m",
            "Confirmed_Phase_Macro_42m",
        ),
        "macro_only_robustness",
    ),
    SignalSpec(
        "V2_Macro_Short",
        (
            "Confirmed_Phase_Macro_16_5m",
            "Confirmed_Phase_Macro_21m",
            "Confirmed_Phase_Macro_42m",
        ),
        "macro_short_robustness",
    ),
    SignalSpec(
        "V1_CB_Fixed",
        (
            "Confirmed_Phase_CB_8_33y",
            "Confirmed_Phase_CB_16_67y",
            "Confirmed_Phase_CB_20m",
            "Confirmed_Phase_CB_42m",
        ),
        "v1_fixed_period_baseline",
    ),
)


RUN_SPECS = (
    RunSpec(SIGNAL_SPECS[0], "expanding"),
    RunSpec(SIGNAL_SPECS[0], "rolling", 120),
    RunSpec(SIGNAL_SPECS[1], "expanding"),
    RunSpec(SIGNAL_SPECS[2], "expanding"),
    RunSpec(SIGNAL_SPECS[2], "rolling", 120),
    RunSpec(SIGNAL_SPECS[3], "expanding"),
    RunSpec(SIGNAL_SPECS[4], "expanding"),
    RunSpec(SIGNAL_SPECS[4], "rolling", 120),
)


def load_inputs() -> tuple[pd.DataFrame, pd.DataFrame]:
    returns = pd.read_parquet(RETURNS_PATH).loc[:, ASSET_COLUMNS]
    returns.index = pd.to_datetime(returns.index).to_period("M").to_timestamp("M")
    returns = returns.groupby(level=0).last().dropna(how="any")

    signals = pd.read_parquet(SIGNALS_PATH)
    signals.index = pd.to_datetime(signals.index).to_period("M").to_timestamp("M")
    signals = signals.groupby(level=0).last().reindex(returns.index)
    return returns, signals


def estimate_expected_returns(
    training_returns: pd.DataFrame,
    training_states: pd.DataFrame,
    current_state: pd.Series,
    *,
    prior_strength: float,
) -> tuple[pd.Series, dict[str, int]]:
    unconditional = training_returns.mean(axis=0)
    state_deltas = []
    state_counts: dict[str, int] = {}

    for column in training_states.columns:
        state = current_state.get(column)
        if state is None or not np.isfinite(state):
            continue
        mask = training_states[column].eq(state)
        count = int(mask.sum())
        state_counts[column] = count
        if count < 3:
            continue
        conditional = training_returns.loc[mask].mean(axis=0)
        shrunk = (count * conditional + prior_strength * unconditional) / (
            count + prior_strength
        )
        state_deltas.append(shrunk - unconditional)

    if not state_deltas:
        return unconditional, state_counts
    expected = unconditional + pd.concat(state_deltas, axis=1).mean(axis=1)
    return expected, state_counts


def expected_returns_to_weights(
    expected_returns: pd.Series,
    *,
    temperature: float,
    active_blend: float = 0.50,
    minimum_weight: float = 0.10,
    maximum_weight: float = 0.60,
) -> pd.Series:
    expected = expected_returns.reindex(ASSET_COLUMNS).astype("float64")
    equal_weight = pd.Series(1.0 / len(ASSET_COLUMNS), index=ASSET_COLUMNS)
    if expected.isna().any() or not np.isfinite(expected.to_numpy()).all():
        return equal_weight

    centered = expected - float(expected.max())
    raw = np.exp(centered / float(temperature))
    softmax = raw / float(raw.sum())
    weights = (1.0 - active_blend) * equal_weight + active_blend * softmax
    weights = weights.clip(lower=minimum_weight, upper=maximum_weight)
    return weights / float(weights.sum())


def run_strategy(
    returns: pd.DataFrame,
    signals: pd.DataFrame,
    run_spec: RunSpec,
    *,
    cost_bps: float = DEFAULT_COST_BPS,
    prior_strength: float = DEFAULT_PRIOR_STRENGTH,
    temperature: float = DEFAULT_TEMPERATURE,
    min_train_months: int = MIN_TRAIN_MONTHS,
) -> pd.DataFrame:
    missing_columns = [
        column for column in run_spec.signal_spec.phase_columns if column not in signals.columns
    ]
    if missing_columns:
        raise KeyError(f"Missing signal columns for {run_spec.name}: {missing_columns}")

    lagged_states = signals.loc[:, run_spec.signal_spec.phase_columns].shift(1)
    pretrade_weights = pd.Series(1.0 / len(ASSET_COLUMNS), index=ASSET_COLUMNS)
    records = []

    for date in returns.index:
        prior_dates = returns.index[returns.index < date]
        if run_spec.mode == "rolling" and run_spec.rolling_window is not None:
            prior_dates = prior_dates[-run_spec.rolling_window :]
        training_states = lagged_states.reindex(prior_dates)
        valid_training_dates = training_states.notna().any(axis=1)
        valid_dates = training_states.index[valid_training_dates]
        if len(valid_dates) < min_train_months:
            continue

        current_state = lagged_states.loc[date]
        if not current_state.notna().any():
            continue

        training_returns = returns.reindex(valid_dates)
        training_states = training_states.reindex(valid_dates)
        expected_returns, state_counts = estimate_expected_returns(
            training_returns,
            training_states,
            current_state,
            prior_strength=prior_strength,
        )
        target_weights = expected_returns_to_weights(
            expected_returns,
            temperature=temperature,
        )
        turnover = 0.5 * float((target_weights - pretrade_weights).abs().sum())
        cost = turnover * float(cost_bps) / 10000.0
        asset_return = returns.loc[date]
        gross_return = float((target_weights * asset_return).sum())
        net_return = gross_return - cost
        denominator = 1.0 + gross_return
        if denominator > 0.0:
            pretrade_weights = target_weights * (1.0 + asset_return) / denominator
        else:
            pretrade_weights = target_weights

        position = returns.index.get_loc(date)
        signal_date = returns.index[position - 1] if position > 0 else pd.NaT
        record = {
            "date": date,
            "strategy": run_spec.name,
            "role": run_spec.signal_spec.role,
            "mode": run_spec.mode,
            "rolling_window": run_spec.rolling_window,
            "signal_date": signal_date,
            "training_start": valid_dates.min(),
            "training_end": valid_dates.max(),
            "training_months": len(valid_dates),
            "features_used": int(current_state.notna().sum()),
            "gross_return": gross_return,
            "net_return": net_return,
            "turnover": turnover,
            "cost": cost,
        }
        for column in ASSET_COLUMNS:
            record[f"weight_{ASSET_LABELS[column]}"] = float(target_weights[column])
            record[f"expected_{ASSET_LABELS[column]}"] = float(expected_returns[column])
        for column in run_spec.signal_spec.phase_columns:
            state = current_state.get(column)
            record[f"state_{column}"] = float(state) if np.isfinite(state) else np.nan
            record[f"count_{column}"] = state_counts.get(column, 0)
        records.append(record)

    if not records:
        raise RuntimeError(f"No backtest observations produced for {run_spec.name}")
    return pd.DataFrame(records).set_index("date")


def performance_metrics(
    returns: pd.Series,
    *,
    benchmark: pd.Series | None = None,
    gross_returns: pd.Series | None = None,
    turnover: pd.Series | None = None,
    costs: pd.Series | None = None,
) -> dict[str, float | int | str]:
    series = pd.to_numeric(returns, errors="coerce").dropna()
    if series.empty:
        return {}
    months = len(series)
    wealth = (1.0 + series).cumprod()
    cagr = float(wealth.iloc[-1] ** (12.0 / months) - 1.0)
    annual_volatility = float(series.std(ddof=1) * np.sqrt(12.0))
    sharpe = (
        float(series.mean() / series.std(ddof=1) * np.sqrt(12.0))
        if float(series.std(ddof=1)) > 0.0
        else np.nan
    )
    drawdown = wealth / wealth.cummax() - 1.0
    max_drawdown = float(drawdown.min())
    calmar = cagr / abs(max_drawdown) if max_drawdown < 0.0 else np.nan
    metrics: dict[str, float | int | str] = {
        "start": str(series.index.min().date()),
        "end": str(series.index.max().date()),
        "months": months,
        "cagr": cagr,
        "annual_volatility": annual_volatility,
        "sharpe": sharpe,
        "max_drawdown": max_drawdown,
        "calmar": calmar,
        "positive_month_rate": float((series > 0.0).mean()),
        "best_month": float(series.max()),
        "worst_month": float(series.min()),
    }
    if benchmark is not None:
        aligned = pd.concat([series, benchmark], axis=1).dropna()
        metrics["benchmark_win_rate"] = float(
            (aligned.iloc[:, 0] > aligned.iloc[:, 1]).mean()
        )
        benchmark_wealth = (1.0 + aligned.iloc[:, 1]).cumprod()
        benchmark_cagr = float(benchmark_wealth.iloc[-1] ** (12.0 / len(aligned)) - 1.0)
        metrics["excess_cagr_vs_equal_weight"] = cagr - benchmark_cagr
    if gross_returns is not None:
        gross = gross_returns.reindex(series.index).dropna()
        gross_wealth = (1.0 + gross).cumprod()
        gross_cagr = float(gross_wealth.iloc[-1] ** (12.0 / len(gross)) - 1.0)
        metrics["gross_cagr"] = gross_cagr
        metrics["cost_drag_cagr"] = gross_cagr - cagr
    if turnover is not None:
        metrics["annual_turnover"] = float(turnover.reindex(series.index).mean() * 12.0)
    if costs is not None:
        metrics["cumulative_cost"] = float(costs.reindex(series.index).sum())
    return metrics


def _common_return_frame(
    returns: pd.DataFrame,
    strategy_results: dict[str, pd.DataFrame],
) -> pd.DataFrame:
    frame = pd.DataFrame(index=returns.index)
    for strategy, result in strategy_results.items():
        frame[f"{strategy}_Gross"] = result["gross_return"]
        frame[f"{strategy}_Net"] = result["net_return"]
    frame["EqualWeight"] = returns.mean(axis=1)
    for column in ASSET_COLUMNS:
        frame[ASSET_LABELS[column]] = returns[column]
    active_net_columns = [column for column in frame if column.endswith("_Net")]
    common_index = frame[active_net_columns].dropna().index
    return frame.reindex(common_index)


def build_summary(
    return_frame: pd.DataFrame,
    strategy_results: dict[str, pd.DataFrame],
) -> pd.DataFrame:
    equal_weight = return_frame["EqualWeight"]
    rows = []
    for strategy, result in strategy_results.items():
        net_column = f"{strategy}_Net"
        gross_column = f"{strategy}_Gross"
        metrics = performance_metrics(
            return_frame[net_column],
            benchmark=equal_weight,
            gross_returns=return_frame[gross_column],
            turnover=result["turnover"],
            costs=result["cost"],
        )
        metrics["strategy"] = strategy
        metrics["type"] = "cycle_strategy"
        rows.append(metrics)

    for benchmark in ("EqualWeight", "HS300", "CSI500", "CSI1000"):
        metrics = performance_metrics(return_frame[benchmark], benchmark=equal_weight)
        metrics["strategy"] = benchmark
        metrics["type"] = "benchmark"
        rows.append(metrics)
    return pd.DataFrame(rows).set_index("strategy")


def build_subperiod_table(
    return_frame: pd.DataFrame,
    strategy_results: dict[str, pd.DataFrame],
) -> pd.DataFrame:
    periods = (
        ("early", return_frame.index.min(), pd.Timestamp("2014-12-31")),
        ("middle", pd.Timestamp("2015-01-31"), pd.Timestamp("2019-12-31")),
        ("recent", pd.Timestamp("2020-01-31"), return_frame.index.max()),
    )
    rows = []
    selected = (
        "V2_CB_All_Expanding",
        "V2_Macro_All_Expanding",
        "V1_CB_Fixed_Expanding",
    )
    for period_name, start, end in periods:
        for strategy in selected:
            net = return_frame.loc[start:end, f"{strategy}_Net"]
            if len(net.dropna()) < 12:
                continue
            result = strategy_results[strategy]
            metrics = performance_metrics(
                net,
                benchmark=return_frame.loc[start:end, "EqualWeight"],
                gross_returns=return_frame.loc[start:end, f"{strategy}_Gross"],
                turnover=result.loc[start:end, "turnover"],
                costs=result.loc[start:end, "cost"],
            )
            metrics["period"] = period_name
            metrics["strategy"] = strategy
            rows.append(metrics)
    return pd.DataFrame(rows)


def build_conditional_returns(returns: pd.DataFrame, signals: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for signal_spec in SIGNAL_SPECS:
        lagged = signals.loc[:, signal_spec.phase_columns].shift(1).reindex(returns.index)
        for phase_column in signal_spec.phase_columns:
            for phase, phase_returns in returns.groupby(lagged[phase_column]):
                if not np.isfinite(phase):
                    continue
                for asset in ASSET_COLUMNS:
                    rows.append(
                        {
                            "signal_set": signal_spec.name,
                            "phase_column": phase_column,
                            "phase": int(phase),
                            "phase_label": PHASE_LABELS[int(phase)],
                            "asset": ASSET_LABELS[asset],
                            "months": len(phase_returns),
                            "average_monthly_return": float(phase_returns[asset].mean()),
                            "annualized_mean_return": float(phase_returns[asset].mean() * 12.0),
                        }
                    )
    return pd.DataFrame(rows)


def _sensitivity_metrics(
    strategy: str,
    result: pd.DataFrame,
    equal_weight: pd.Series,
    *,
    sensitivity_type: str,
    sensitivity_value: float,
) -> dict[str, float | int | str]:
    metrics = performance_metrics(
        result["net_return"],
        benchmark=equal_weight,
        gross_returns=result["gross_return"],
        turnover=result["turnover"],
        costs=result["cost"],
    )
    metrics["strategy"] = strategy
    metrics["sensitivity_type"] = sensitivity_type
    metrics["sensitivity_value"] = sensitivity_value
    return metrics


def build_sensitivity_table(
    returns: pd.DataFrame,
    signals: pd.DataFrame,
    strategy_results: dict[str, pd.DataFrame],
    common_index: pd.DatetimeIndex,
) -> pd.DataFrame:
    rows = []
    primary_name = "V2_CB_All_Expanding"
    primary = strategy_results[primary_name].reindex(common_index).dropna(subset=["net_return"])
    equal_weight = returns.mean(axis=1).reindex(common_index)

    for cost_bps in (0.0, 10.0, 15.0, 20.0, 30.0):
        adjusted = primary.copy()
        adjusted["cost"] = adjusted["turnover"] * cost_bps / 10000.0
        adjusted["net_return"] = adjusted["gross_return"] - adjusted["cost"]
        rows.append(
            _sensitivity_metrics(
                primary_name,
                adjusted,
                equal_weight,
                sensitivity_type="cost_bps",
                sensitivity_value=cost_bps,
            )
        )

    primary_run = RunSpec(SIGNAL_SPECS[0], "expanding")
    for prior_strength in (12.0, 24.0, 36.0, 48.0):
        result = run_strategy(
            returns,
            signals,
            primary_run,
            prior_strength=prior_strength,
        ).reindex(common_index).dropna(subset=["net_return"])
        rows.append(
            _sensitivity_metrics(
                primary_name,
                result,
                equal_weight,
                sensitivity_type="prior_strength",
                sensitivity_value=prior_strength,
            )
        )

    for temperature in (0.010, 0.015, 0.020, 0.030):
        result = run_strategy(
            returns,
            signals,
            primary_run,
            temperature=temperature,
        ).reindex(common_index).dropna(subset=["net_return"])
        rows.append(
            _sensitivity_metrics(
                primary_name,
                result,
                equal_weight,
                sensitivity_type="temperature",
                sensitivity_value=temperature,
            )
        )

    for rolling_window in (84, 120, 156):
        run_spec = RunSpec(SIGNAL_SPECS[0], "rolling", rolling_window)
        result = (
            run_strategy(returns, signals, run_spec)
            .reindex(common_index)
            .dropna(subset=["net_return"])
        )
        rows.append(
            _sensitivity_metrics(
                run_spec.name,
                result,
                equal_weight,
                sensitivity_type="rolling_window",
                sensitivity_value=float(rolling_window),
            )
        )
    return pd.DataFrame(rows)


def plot_cumulative_returns(return_frame: pd.DataFrame) -> None:
    selected = {
        "V2 CB all": "V2_CB_All_Expanding_Net",
        "V2 macro all": "V2_Macro_All_Expanding_Net",
        "V1 fixed": "V1_CB_Fixed_Expanding_Net",
        "Equal weight": "EqualWeight",
    }
    figure, axis = plt.subplots(figsize=(14, 7))
    for label, column in selected.items():
        wealth = (1.0 + return_frame[column]).cumprod()
        axis.plot(wealth.index, wealth.values, linewidth=1.5, label=label)
    axis.set_yscale("log")
    axis.set_title("Cycle-state A-share style rotation (net of 15 bps one-way costs)")
    axis.set_ylabel("Cumulative wealth (log scale)")
    axis.legend(loc="upper left")
    axis.grid(alpha=0.25)
    figure.tight_layout()
    figure.savefig(PLOT_OUT, dpi=150)
    plt.close(figure)


def _format_percent(value: float) -> str:
    return f"{value:.2%}" if np.isfinite(value) else "NA"


def write_report(
    summary: pd.DataFrame,
    subperiod: pd.DataFrame,
    sensitivity: pd.DataFrame,
    conditional: pd.DataFrame,
) -> None:
    primary = summary.loc["V2_CB_All_Expanding"]
    macro = summary.loc["V2_Macro_All_Expanding"]
    v1 = summary.loc["V1_CB_Fixed_Expanding"]
    equal_weight = summary.loc["EqualWeight"]
    best_strategy = summary[summary["type"].eq("cycle_strategy")]["sharpe"].idxmax()

    conclusion_lines = [
        f"- 预先指定的 V2 类别等权全周期策略净 CAGR 为 {_format_percent(primary['cagr'])}，Sharpe 为 {primary['sharpe']:.2f}，相对等权 CAGR 为 {_format_percent(primary['excess_cagr_vs_equal_weight'])}。",
        f"- 宏观-only V2 全周期策略净 CAGR 为 {_format_percent(macro['cagr'])}，Sharpe 为 {macro['sharpe']:.2f}；它是稳健性规格，不作为事后替代主模型。",
        f"- V1 固定周期基线净 CAGR 为 {_format_percent(v1['cagr'])}，Sharpe 为 {v1['sharpe']:.2f}；等权基准 CAGR 为 {_format_percent(equal_weight['cagr'])}。",
        f"- 当前样本中风险调整后最高的周期规格是 `{best_strategy}`，但是否可进入实盘仍取决于子样本与参数平台是否稳定。",
    ]

    sensitivity_view = sensitivity[
        sensitivity["sensitivity_type"].isin(["cost_bps", "prior_strength", "temperature"])
    ][
        [
            "sensitivity_type",
            "sensitivity_value",
            "cagr",
            "sharpe",
            "max_drawdown",
            "annual_turnover",
            "excess_cagr_vs_equal_weight",
        ]
    ]
    conditional_view = (
        conditional[conditional["signal_set"].eq("V2_CB_All")]
        .sort_values(["phase_column", "phase", "annualized_mean_return"], ascending=[True, True, False])
        .groupby(["phase_column", "phase"], as_index=False)
        .first()
    )

    lines = [
        "# 周期状态到A股风格轮动：实时走步回测",
        "",
        "## 结论",
        "",
        *conclusion_lines,
        "",
        "## 回测约束",
        "",
        "- 可投资产仅为 HS300、CSI500、CSI1000，样本为三者共同可用的月度收益。",
        "- 月 t 收益只使用月 t-1 的已确认信号；年频信号在进入月频层前已滞后一年。",
        "- 每个月的状态条件收益只从此前样本估计，最低训练期 60 个月，并向无条件均值收缩 24 个月等价样本。",
        "- 权重为长仓、和为 1；用温度 1.5% 的 softmax 与等权各混合 50%，不进行收益最大化参数搜索。",
        "- 默认按单边换手 15bp 扣费，并使用收益后漂移权重计算下月实际再平衡换手。",
        "- `V2_CB_All_Expanding` 是预先指定主模型；宏观-only、短周期剔除、120个月滚动窗口均为稳健性对照。",
        "",
        "## 全样本表现",
        "",
        summary.round(4).to_markdown(),
        "",
        "## 子样本稳定性",
        "",
        subperiod.round(4).to_markdown(index=False),
        "",
        "## 参数与成本敏感性",
        "",
        sensitivity_view.round(4).to_markdown(index=False),
        "",
        "## V2状态下历史最强风格（描述性，非回测输入）",
        "",
        conditional_view.round(4).to_markdown(index=False),
        "",
        "## 决策规则",
        "",
        "- 若 V2 主模型在净 Sharpe、最大回撤和多数子样本上均优于 V1 与等权，可进入行业扩展和模拟盘。",
        "- 若优势只出现在宏观-only或单一参数点，应保留为研究信号，不做资产配置覆盖。",
        "- 若 20–30bp 成本即消除优势，优先降低换手或改为季度再平衡，而不是继续调参。",
        "",
        "## 输出",
        "",
        f"- 回测收益：`{RETURNS_OUT}`",
        f"- 月度权重与审计轨迹：`{WEIGHTS_OUT}`",
        f"- 汇总指标：`{SUMMARY_OUT}`",
        f"- 子样本：`{SUBPERIOD_OUT}`",
        f"- 敏感性：`{SENSITIVITY_OUT}`",
        f"- 条件收益：`{CONDITIONAL_OUT}`",
        f"- 累计净值图：`{PLOT_OUT}`",
    ]
    REPORT_OUT.write_text("\n".join(lines), encoding="utf-8")


def run_all_backtests() -> tuple[
    pd.DataFrame,
    dict[str, pd.DataFrame],
    pd.DataFrame,
    pd.DataFrame,
    pd.DataFrame,
    pd.DataFrame,
]:
    returns, signals = load_inputs()
    strategy_results = {
        run_spec.name: run_strategy(returns, signals, run_spec) for run_spec in RUN_SPECS
    }
    return_frame = _common_return_frame(returns, strategy_results)
    summary = build_summary(return_frame, strategy_results)
    subperiod = build_subperiod_table(return_frame, strategy_results)
    sensitivity = build_sensitivity_table(
        returns,
        signals,
        strategy_results,
        return_frame.index,
    )
    conditional = build_conditional_returns(returns, signals)
    return return_frame, strategy_results, summary, subperiod, sensitivity, conditional


def main() -> None:
    return_frame, strategy_results, summary, subperiod, sensitivity, conditional = (
        run_all_backtests()
    )
    RETURNS_OUT.parent.mkdir(parents=True, exist_ok=True)
    return_frame.to_parquet(RETURNS_OUT)
    pd.concat(
        [result.reset_index() for result in strategy_results.values()],
        ignore_index=True,
    ).to_csv(WEIGHTS_OUT, index=False)
    summary.to_csv(SUMMARY_OUT)
    subperiod.to_csv(SUBPERIOD_OUT, index=False)
    sensitivity.to_csv(SENSITIVITY_OUT, index=False)
    conditional.to_csv(CONDITIONAL_OUT, index=False)
    plot_cumulative_returns(return_frame)
    write_report(summary, subperiod, sensitivity, conditional)
    print(f"Wrote {RETURNS_OUT}")
    print(f"Wrote {SUMMARY_OUT}")
    print(f"Wrote {REPORT_OUT}")


if __name__ == "__main__":
    main()
