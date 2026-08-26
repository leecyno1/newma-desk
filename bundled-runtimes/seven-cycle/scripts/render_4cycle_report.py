from __future__ import annotations

from pathlib import Path

import pandas as pd


def _pct(x: float) -> str:
    if x != x or x is None:
        return "NA"
    return f"{x*100:.1f}%"


def _fmt(x) -> str:
    if x != x or x is None:
        return "NA"
    return f"{x:.3f}"


def _md_table(df: pd.DataFrame, cols: list[str], n: int = 25) -> str:
    if df.empty:
        return "(empty)"
    show = df[cols].head(n).copy()
    return "```\n" + show.to_string(index=False) + "\n```"


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    out_dir = root / "output"

    scores_m = pd.read_csv(out_dir / "cycle_bandpower_scores_monthly.csv")
    scores_a = pd.read_csv(out_dir / "cycle_bandpower_scores_annual.csv")
    reps = pd.read_csv(out_dir / "cycle_representative_indicators_4cycle.csv")

    phase_summary = pd.read_csv(out_dir / "cycle_selected_4cycle" / "summary.csv")
    annual_long_summary = pd.read_csv(out_dir / "cycle_selected_annual_long_4cycle" / "summary.csv")

    lines: list[str] = []
    lines.append("# 4-Cycle Framework Report (200/100/42/20m)")
    lines.append("")

    lines.append("## 1) 框架是否可行？")
    lines.append("- **可行（作为粗分的频带滤波框架）**：对同一频率体系/采样频率下的时间序列，线性滤波可写成 `X ≈ Σ Cycle_i + Residual`，可用于解释“哪些频带主导波动”。")
    lines.append("- **但必须承认统计边界**：周期越长，对样本长度要求越高；月频 2000–2024 仅 300 个点，200m≈16.7y 基本只有 1-2 个波动，显著性容易不稳。")
    lines.append("- **最佳实践**：200m/100m 更建议用年频 1960–2024 做显著性筛选（再映射回月频做跟踪），42m/20m 用月频做更可靠。")
    lines.append("")

    lines.append("### 理论对应（粗分）")
    lines.append("- **200m（≈15–25年）**：库兹涅茨/地产-建造-基建相关（长投资周期，叠加人口与信用扩张/收缩）。")
    lines.append("- **100m（≈7–11年）**：朱格拉/设备投资与企业资本开支周期。")
    lines.append("- **42m（≈3–5年）**：库存/基钦周期（产成品/原材料、PMI、PPI 等）。")
    lines.append("- **20m（≈1–2年）**：流动性/政策短周期（货币信用、利率、资金松紧）。")
    lines.append("")

    lines.append("## 2) 周期显著性扫描（Bandpower Ratio）")
    lines.append("- 评分方法：对每个指标的加工序列（price/level→log-diff；rate_level→diff；return/YoY/MoM 保持）做 Welch PSD，计算目标频带功率占比。")
    lines.append("")

    def cycle_stats(scores: pd.DataFrame, freq: str, cycles: list[int]) -> list[str]:
        out: list[str] = []
        df = scores.copy()
        df["bandpower_ratio"] = pd.to_numeric(df["bandpower_ratio"], errors="coerce")
        df = df.dropna(subset=["bandpower_ratio"])
        for c in cycles:
            sub = df[df["cycle_months"] == c]
            if sub.empty:
                continue
            out.append(
                f"- {freq} {int(c)}m: n={len(sub)}, mean={_pct(sub['bandpower_ratio'].mean())}, "
                f"p50={_pct(sub['bandpower_ratio'].median())}, p90={_pct(sub['bandpower_ratio'].quantile(0.9))}, "
                f"max={_pct(sub['bandpower_ratio'].max())}"
            )
        return out

    lines.append("### Monthly (2000-2024 window; better for 42/20)")
    lines += cycle_stats(scores_m, "M", cycles=[42, 20])
    lines.append("")
    lines.append("### Annual (1960-2024 window; better for 200/100)")
    lines += cycle_stats(scores_a, "A", cycles=[200, 100])
    lines.append("")

    lines.append("## 3) 代表指标组（去重后）")
    if reps.empty:
        lines.append("(no representatives selected)")
    else:
        for c in [200, 100, 42, 20]:
            sub = reps[reps["cycle_months"] == c].copy()
            if sub.empty:
                continue
            sub["bandpower_ratio"] = pd.to_numeric(sub["bandpower_ratio"], errors="coerce")
            sub = sub.sort_values(["bandpower_ratio", "n_points"], ascending=[False, False])
            lines.append(f"### {int(c)}m")
            lines.append(
                _md_table(
                    sub,
                    cols=["id", "name", "universe_category", "value_type", "n_points", "start", "end", "bandpower_ratio"],
                    n=30,
                )
            )
            lines.append("")

    lines.append("## 4) 周期分解 + 历史相位标注（图表）")
    if phase_summary.empty:
        lines.append("(no phase outputs)")
    else:
        phase_summary["reconstruction_r2"] = pd.to_numeric(phase_summary["reconstruction_r2"], errors="coerce")
        good = phase_summary.dropna(subset=["reconstruction_r2"]).copy()
        if not good.empty:
            lines.append(
                "- 月频（2000-）分解解释度（`reconstruction_r2`，按 `X ≈ ΣCycle + Residual`）："
                + f" mean={_fmt(good['reconstruction_r2'].mean())}, "
                + f"p50={_fmt(good['reconstruction_r2'].median())}, "
                + f"p10={_fmt(good['reconstruction_r2'].quantile(0.10))}, "
                + f"p90={_fmt(good['reconstruction_r2'].quantile(0.90))}"
            )
        lines.append("- 图表目录：`output/cycle_selected_4cycle/plots/`（每个指标一张 4-cycle+phase 标注图）")
        lines.append("- 明细：`output/cycle_selected_4cycle/summary.csv`（含每个指标的组件文件路径与 R2）")
    lines.append("")

    if annual_long_summary.empty:
        lines.append("### 年频长周期（1960-）")
        lines.append("(no annual-long outputs)")
    else:
        annual_long_summary["reconstruction_r2"] = pd.to_numeric(annual_long_summary["reconstruction_r2"], errors="coerce")
        good = annual_long_summary.dropna(subset=["reconstruction_r2"]).copy()
        if not good.empty:
            lines.append("### 年频长周期（1960-）")
            lines.append(
                "- 年频长周期分解解释度："
                + f" mean={_fmt(good['reconstruction_r2'].mean())}, "
                + f"p50={_fmt(good['reconstruction_r2'].median())}, "
                + f"p10={_fmt(good['reconstruction_r2'].quantile(0.10))}, "
                + f"p90={_fmt(good['reconstruction_r2'].quantile(0.90))}"
            )
        lines.append("- 图表目录：`output/cycle_selected_annual_long_4cycle/plots/`")
        lines.append("- 明细：`output/cycle_selected_annual_long_4cycle/summary.csv`")
    lines.append("")

    lines.append("## 5) 对“周期划分代码”的吸收与改造建议")
    lines.append("- `周期划分-寻最高最低点.ipynb` 用 `find_peaks` 对单序列标注峰谷，再用阈值规则拟合“肉眼分段”。")
    lines.append("- 该思路适合做‘拐点标注’，但缺点是：对噪声敏感、参数依赖强、无法区分不同时间尺度的周期。")
    lines.append("- 本项目建议：先做 4 个频带分量（200/100/42/20），再分别做相位（Quadrant/Hilbert 或峰谷法），最后在多指标上聚合成“周期合成指数”用于资产轮动。")
    lines.append("")

    out_path = out_dir / "cycle_framework_4cycle_report.md"
    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("Wrote:", out_path)


if __name__ == "__main__":
    main()

