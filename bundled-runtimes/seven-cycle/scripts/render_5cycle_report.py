from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd


def _pct(x: float) -> str:
    if x != x or x is None:
        return "NA"
    return f"{x*100:.1f}%"


def _fmt(x) -> str:
    if x != x or x is None:
        return "NA"
    return f"{x:.3f}"


def _md_table(df: pd.DataFrame, cols: list[str], n: int = 20) -> str:
    if df.empty:
        return "(empty)"
    show = df[cols].head(n).copy()
    return "```\n" + show.to_string(index=False) + "\n```"


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    out_dir = root / "output"

    scores_m = pd.read_csv(out_dir / "cycle_bandpower_scores_monthly.csv")
    scores_a = pd.read_csv(out_dir / "cycle_bandpower_scores_annual.csv")
    reps = pd.read_csv(out_dir / "cycle_representative_indicators.csv")
    phase_summary = pd.read_csv(out_dir / "cycle_selected" / "summary.csv")

    lines: list[str] = []
    lines.append("# 5-Cycle Framework Report (200/100/42/20/12m)")
    lines.append("")
    lines.append("## 1) 框架可行性（结论）")
    lines.append("- **可行（作为粗分的频带滤波框架）**：用线性滤波器组把时间序列拆成 5 个频带分量（+残差）在数学上成立。")
    lines.append("- **但不是“物理定律”**：经济周期不是严格稳定的正弦波，周期长度会漂移、结构会变、并且不同指标的传导链路非线性。")
    lines.append("- **统计上需要约束**：周期越长，对样本长度要求越高；对中国宏观月频（多从 2000s/2005 起），200m/100m 的显著性检验天然偏弱。")
    lines.append("")
    lines.append("**关于“叠加解释”**")
    lines.append("- 如果用的是线性分解（例如 band-pass filter bank），那么 `X = Σ Cycle_i + Residual` 是线性的叠加恒等式（在同一频率体系/同一采样频率下）。")
    lines.append("- 关键不在“能不能叠加”，而在：每个频带是否真的有稳定能量（显著性）、以及 Residual 是否可解释（结构变化/噪声/漏掉的频带）。")
    lines.append("")

    lines.append("## 2) 周期显著性扫描（Bandpower Ratio）")
    lines.append("- 评分方法：对每个指标的**加工后序列**（price/level→log-diff；rate_level→diff；return/YoY/MoM 保持）做 Welch PSD，计算目标频带功率占比。")
    lines.append("")

    def cycle_stats(scores: pd.DataFrame, freq: str) -> list[str]:
        out: list[str] = []
        df = scores.copy()
        df["bandpower_ratio"] = pd.to_numeric(df["bandpower_ratio"], errors="coerce")
        df = df.dropna(subset=["bandpower_ratio"])
        for c in sorted(df["cycle_months"].unique()):
            sub = df[df["cycle_months"] == c]
            if sub.empty:
                continue
            out.append(
                f"- {freq} {int(c)}m: n={len(sub)}, mean={_pct(sub['bandpower_ratio'].mean())}, "
                f"p50={_pct(sub['bandpower_ratio'].median())}, p90={_pct(sub['bandpower_ratio'].quantile(0.9))}, "
                f"max={_pct(sub['bandpower_ratio'].max())}"
            )
        return out

    lines.append("### Monthly (2000-2024 window; better for 42/20/12)")
    lines += cycle_stats(scores_m, "M")
    lines.append("")
    lines.append("### Annual (1960-2024 window; better for 200/100)")
    lines += cycle_stats(scores_a, "A")
    lines.append("")

    lines.append("## 3) 代表指标组（去重后）")
    if reps.empty:
        lines.append("(no representatives selected)")
    else:
        for c in sorted(reps["cycle_months"].unique()):
            sub = reps[reps["cycle_months"] == c].copy()
            sub["bandpower_ratio"] = pd.to_numeric(sub["bandpower_ratio"], errors="coerce")
            sub = sub.sort_values(["bandpower_ratio", "n_points"], ascending=[False, False])
            lines.append(f"### {int(c)}m")
            lines.append(
                _md_table(
                    sub,
                    cols=["id", "name", "universe_category", "value_type", "n_points", "start", "end", "bandpower_ratio"],
                    n=25,
                )
            )
            lines.append("")

    lines.append("## 4) 5类周期分解 + 历史相位标注（图表）")
    if phase_summary.empty:
        lines.append("(no phase outputs)")
    else:
        phase_summary["reconstruction_r2"] = pd.to_numeric(phase_summary["reconstruction_r2"], errors="coerce")
        good = phase_summary.dropna(subset=["reconstruction_r2"]).copy()
        if not good.empty:
            lines.append(
                "- 分解解释度（`reconstruction_r2`，按 `X ≈ ΣCycle + Residual`）："
                + f" mean={_fmt(good['reconstruction_r2'].mean())}, "
                + f"p50={_fmt(good['reconstruction_r2'].median())}, "
                + f"p10={_fmt(good['reconstruction_r2'].quantile(0.10))}, "
                + f"p90={_fmt(good['reconstruction_r2'].quantile(0.90))}"
            )
        lines.append("- 图表目录：`output/cycle_selected/plots/`（每个指标一张 5-cycle+phase 标注图）")
        lines.append("- 明细：`output/cycle_selected/summary.csv`（含每个指标的组件文件路径与 R2）")
        lines.append("- 长周期年度版（更适合 200m/100m）：`output/cycle_selected_annual_long/plots/` 与 `output/cycle_selected_annual_long/summary.csv`")
    lines.append("")

    lines.append("## 5) 对“周期划分代码”的评价与改进方向")
    lines.append("- 现有 `周期划分-寻最高最低点.ipynb` 本质是：对单一指标做峰谷识别（find_peaks），再用阈值规则拟合‘肉眼’分段。")
    lines.append("- 它能做‘拐点标注’，但不足以区分 **不同时间尺度的周期**（200/100/42/20/12）或做跨指标一致性检验。")
    lines.append("- 建议：用本次生成的 **5个频带分量** 取代原始序列，分别做相位（Quadrant/Hilbert）与拐点标注；再把多指标聚合成“周期合成指数”用于资产轮动回测。")
    lines.append("")

    out_path = out_dir / "cycle_framework_5cycle_report.md"
    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("Wrote:", out_path)


if __name__ == "__main__":
    main()
