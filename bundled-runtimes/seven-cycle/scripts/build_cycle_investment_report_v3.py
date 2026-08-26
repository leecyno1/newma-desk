from __future__ import annotations

import numpy as np
import pandas as pd

from cycle_realtime_core import ROOT, phase_label


SIGNALS_PATH = ROOT / "output" / "cycle_realtime_signals_hybrid.parquet"
REVISION_PATH = ROOT / "output" / "cycle_realtime_signal_revision.csv"
SUMMARY_PATH = ROOT / "output" / "cycle_style_rotation_backtest_summary.csv"
SUBPERIOD_PATH = ROOT / "output" / "cycle_style_rotation_backtest_subperiod.csv"
SENSITIVITY_PATH = ROOT / "output" / "cycle_style_rotation_backtest_sensitivity.csv"
WEIGHTS_PATH = ROOT / "output" / "cycle_style_rotation_backtest_weights.csv"
REPORT_OUT = ROOT / "output" / "CYCLE_INVESTMENT_APPLICATION_V3.md"


def _latest_phase_table(signals: pd.DataFrame) -> pd.DataFrame:
    columns = (
        "Confirmed_Phase_CB_9y",
        "Confirmed_Phase_CB_14y",
        "Confirmed_Phase_CB_16_5m",
        "Confirmed_Phase_CB_21m",
        "Confirmed_Phase_CB_42m",
        "Confirmed_Phase_Macro_42m",
    )
    latest = signals.iloc[-1]
    rows = []
    for column in columns:
        value = latest[column]
        parts = column.split("_")
        view = parts[2]
        period = "_".join(parts[3:])
        rows.append(
            {
                "view": view,
                "period": period,
                "phase": int(value) if np.isfinite(value) else np.nan,
                "phase_label": phase_label(value),
                "signal_as_of": signals.index[-1],
            }
        )
    return pd.DataFrame(rows)


def _latest_weight_table(weights: pd.DataFrame) -> pd.DataFrame:
    primary = weights[weights["strategy"].eq("V2_CB_All_Expanding")].copy()
    latest = primary.sort_values("date").iloc[-1]
    rows = []
    for asset in ("HS300", "CSI500", "CSI1000"):
        rows.append(
            {
                "asset": asset,
                "weight": latest[f"weight_{asset}"],
                "expanding_expected_monthly_return": latest[f"expected_{asset}"],
                "portfolio_return_month": latest["date"],
                "signal_vintage": latest["signal_date"],
            }
        )
    return pd.DataFrame(rows)


def _selected_summary(summary: pd.DataFrame) -> pd.DataFrame:
    selected = (
        "V2_CB_All_Expanding",
        "V2_CB_All_Rolling120",
        "V2_Macro_All_Expanding",
        "V1_CB_Fixed_Expanding",
        "EqualWeight",
        "HS300",
    )
    columns = (
        "cagr",
        "annual_volatility",
        "sharpe",
        "max_drawdown",
        "annual_turnover",
        "excess_cagr_vs_equal_weight",
    )
    return summary.reindex(selected).loc[:, columns]


def _revision_view(revision: pd.DataFrame) -> pd.DataFrame:
    selected = revision[
        revision["period_label"].isin(["9y", "14y", "16_5m", "21m", "42m"])
        & revision["view"].isin(["CB", "Macro"])
        & revision["reference"].isin(
            ["state_space_full_sample_smoother", "two_sided_v2"]
        )
    ].copy()
    return selected[
        [
            "frequency",
            "view",
            "period_label",
            "reference",
            "correlation",
            "phase_match",
            "median_abs_revision",
            "best_confirmation_lag",
            "best_lag_correlation",
        ]
    ]


def _sensitivity_summary(sensitivity: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for sensitivity_type, group in sensitivity.groupby("sensitivity_type"):
        rows.append(
            {
                "dimension": sensitivity_type,
                "tested_min": group["sensitivity_value"].min(),
                "tested_max": group["sensitivity_value"].max(),
                "cagr_min": group["cagr"].min(),
                "cagr_max": group["cagr"].max(),
                "sharpe_min": group["sharpe"].min(),
                "sharpe_max": group["sharpe"].max(),
                "excess_cagr_min": group["excess_cagr_vs_equal_weight"].min(),
                "excess_cagr_max": group["excess_cagr_vs_equal_weight"].max(),
            }
        )
    return pd.DataFrame(rows)


def main() -> None:
    signals = pd.read_parquet(SIGNALS_PATH)
    revision = pd.read_csv(REVISION_PATH)
    summary = pd.read_csv(SUMMARY_PATH, index_col=0)
    subperiod = pd.read_csv(SUBPERIOD_PATH)
    sensitivity = pd.read_csv(SENSITIVITY_PATH)
    weights = pd.read_csv(WEIGHTS_PATH, parse_dates=["date", "signal_date"])

    latest_phases = _latest_phase_table(signals)
    latest_weights = _latest_weight_table(weights)
    performance = _selected_summary(summary)
    revision_view = _revision_view(revision)
    sensitivity_view = _sensitivity_summary(sensitivity)
    subperiod_view = subperiod[
        subperiod["strategy"].isin(
            [
                "V2_CB_All_Expanding",
                "V2_Macro_All_Expanding",
                "V1_CB_Fixed_Expanding",
            ]
        )
    ][
        [
            "period",
            "strategy",
            "cagr",
            "sharpe",
            "max_drawdown",
            "excess_cagr_vs_equal_weight",
        ]
    ]

    primary = summary.loc["V2_CB_All_Expanding"]
    v1 = summary.loc["V1_CB_Fixed_Expanding"]
    equal_weight = summary.loc["EqualWeight"]
    macro = summary.loc["V2_Macro_All_Expanding"]

    lines = [
        "# 多周期框架 V3：实时信号与投资应用验证",
        "",
        "## 一页结论",
        "",
        "- **研究工程通过，投资策略未通过。** 已完成无前视的实时状态空间信号、历史修订跟踪、扩展窗口状态收益映射、滚动走步回测和交易摩擦测试。",
        f"- 预先指定的 V2 类别等权全周期策略净 CAGR 为 `{primary['cagr']:.2%}`、Sharpe 为 `{primary['sharpe']:.2f}`，均未超过三风格等权基准的 `{equal_weight['cagr']:.2%}` 和 `{equal_weight['sharpe']:.2f}`。",
        f"- V2 宏观-only（CAGR `{macro['cagr']:.2%}`）与 V1 固定周期（`{v1['cagr']:.2%}`）结果接近，说明当前样本不能证明新的周期带能稳定改善风格轮动。",
        "- **当前决策：研究用途，暂不进入实盘/模拟盘，不扩展到行业和全球资产。** 周期相位保留为宏观背景与风险沟通层，而不是独立配置引擎。",
        "",
        "## V3 相对 V2 的关键变化",
        "",
        "| 环节 | V2 历史研究 | V3 投资应用 |",
        "|---|---|---|",
        "| 周期提取 | 双边 Butterworth/HP，适合历史解释 | 阻尼谐波状态空间滤波，只用当期及过去数据 |",
        "| 相位确认 | 当期象限直接标记 | 月频连续两个月确认，年频映射时滞后一年 |",
        "| 资产映射 | 手工权重或事后条件收益 | 每月仅用此前样本估计，向无条件均值收缩 |",
        "| 验证 | 全样本相关与事件研究 | 扩展窗口、滚动120月、成本、回撤、子样本和参数平台 |",
        "| 决策门槛 | 方法稳健即可保留 | 必须净收益优于 V1 与等权且子样本稳定 |",
        "",
        "## 最新实时状态",
        "",
        latest_phases.to_markdown(index=False),
        "",
        "- 类别等权短周期均处于扩张，但宏观-only 42m 仍处于收缩；该分歧本身说明股票估值类别正在显著影响综合相位。",
        "- 年频 9y/14y 信号在 2025 年月度投资层使用的是 2024 年已形成的数据，避免把未发布的当年全年信息提前使用。",
        "",
        "## 最新模型权重（研究输出，不构成投资建议）",
        "",
        latest_weights.round(4).to_markdown(index=False),
        "",
        "## 实时信号修订与确认",
        "",
        revision_view.round(4).to_markdown(index=False),
        "",
        "- 月频 42m 的类别等权实时值相对最终平滑值存在较长确认延迟，而宏观-only 视图更稳定；V3 没有据此事后替换主模型，而是将两者并列呈现。",
        "- 实时与双边历史时间轴不应被视为同一个信号：双边版本用于解释历史，实时版本用于验证可交易性。",
        "",
        "## 走步回测结果",
        "",
        performance.round(4).to_markdown(),
        "",
        "### 子样本",
        "",
        subperiod_view.round(4).to_markdown(index=False),
        "",
        "### 参数平台",
        "",
        sensitivity_view.round(4).to_markdown(index=False),
        "",
        "- 10–30bp 成本变化只造成很小影响，因为策略年化换手较低；弱表现不是交易摩擦造成。",
        "- 收缩强度、权重温度和滚动窗口改变后，超额收益仍围绕零附近，未形成可部署的平台。",
        "",
        "## 决策与后续举措",
        "",
        "### 保留",
        "",
        "- 保留 V2 周期带及 V3 实时相位，作为历史解释、宏观风险状态和投资委员会沟通工具。",
        "- 保留类别等权与宏观-only双视图，显式展示市场价格信号与纯宏观信号的分歧。",
        "- 保留完整走步审计轨迹，使每个权重可追溯到信号 vintage、训练样本和状态计数。",
        "",
        "### 暂停",
        "",
        "- 暂停将周期状态直接映射为 HS300/CSI500/CSI1000 月度轮动。",
        "- 暂停扩展到行业、全球资产和更复杂优化器，避免在基础三资产原型未通过时扩大过拟合空间。",
        "",
        "### 下一轮研究优先级",
        "",
        "1. 将预测目标从单月绝对收益改为 3–6 个月相对收益/风格价差，匹配周期信号的低频性质。",
        "2. 用连续的周期水平、斜率和状态不确定性替代四象限离散标签，并采用嵌套走步的岭回归或排序模型。",
        "3. 对三指数先做市场 beta 残差化，检验周期是否能解释真正的风格相对收益，而非共同市场方向。",
        "4. 引入真实宏观发布日和数据 vintage；当前一月/一年滞后是保守近似，但不是完整实时数据库。",
        "5. 只有上述规格在外部留出期和多数子样本上超过等权后，才恢复行业或全球资产扩展。",
        "",
        "## 可复现命令",
        "",
        "```bash",
        ".venv2/bin/python scripts/run_cycle_investment_application.py",
        "# 或分步运行：",
        ".venv2/bin/python scripts/build_realtime_cycle_signals.py",
        ".venv2/bin/python scripts/backtest_cycle_style_rotation_v3.py",
        ".venv2/bin/python scripts/build_cycle_investment_report_v3.py",
        ".venv2/bin/python scripts/verify_cycle_investment_application.py",
        "```",
        "",
        "## 主要文件",
        "",
        f"- 实时信号报告：`{ROOT / 'output' / 'cycle_realtime_signal_report.md'}`",
        f"- 走步回测报告：`{ROOT / 'output' / 'cycle_style_rotation_backtest.md'}`",
        f"- V3 报告：`{REPORT_OUT}`",
        f"- 实时混合信号：`{SIGNALS_PATH}`",
        f"- 回测审计权重：`{WEIGHTS_PATH}`",
    ]
    REPORT_OUT.write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote {REPORT_OUT}")


if __name__ == "__main__":
    main()
