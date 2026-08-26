"""
Compute cycle phase timelines (上行/下行/高位/低位) for key series using the
Butterworth-based CycleDecomposer.

Output:
- Per-series parquet files under data/, e.g. data/huatai_phase_macro_cpi_yoy.parquet
- A Markdown summary at output/huatai_cycle_phase_timeline.md
"""

from __future__ import annotations

from pathlib import Path
import sys

import numpy as np
import pandas as pd

# Ensure project root on path
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from cycle_analysis_system.analysis.deep_cycle_decomposition import CycleDecomposer  # type: ignore


KEY_SERIES = [
    "macro_cpi_yoy",
    "macro_ppi_yoy",
    "idx_sh_comp_ret_m",
    "idx_hs300_ret_m",
]

PERIODS = [200, 100, 42, 21, 12]


def classify_phase(component: pd.Series) -> pd.Series:
    """
    Map cycle component into four qualitative phases:
    - Up:    above 0 and rising (扩张)
    - High:  above 0 and falling (高位回落/过热)
    - Down:  below 0 and falling (衰退)
    - Low:   below 0 and rising (筑底复苏)
    """
    comp = component
    dcomp = comp.diff()

    phase = pd.Series(index=comp.index, dtype="object")

    phase[(comp >= 0) & (dcomp >= 0)] = "Up"
    phase[(comp >= 0) & (dcomp < 0)] = "High"
    phase[(comp < 0) & (dcomp < 0)] = "Down"
    phase[(comp < 0) & (dcomp >= 0)] = "Low"

    return phase


def load_huatai_db() -> pd.DataFrame:
    path = Path("data") / "huatai_db_monthly.parquet"
    if not path.exists():
        raise FileNotFoundError(f"{path} not found – run build_huatai_db_from_tushare.py first.")
    return pd.read_parquet(path)


def build_phase_timeline(df: pd.DataFrame) -> str:
    lines: list[str] = []
    lines.append("# Huatai Cycle Phase Timeline (Butterworth 分解)")
    lines.append("")
    lines.append("数据：`data/huatai_db_monthly.parquet`；周期：200/100/42/21/12 月。")
    lines.append("")

    decomposer = CycleDecomposer(periods=PERIODS, sample_rate=1)

    for col in KEY_SERIES:
        if col not in df.columns:
            continue
        s = df[col].dropna()
        if s.size < 60:
            continue

        res = decomposer.decompose(s)

        # 构建包含相位标签的 DataFrame
        out = pd.DataFrame(index=s.index)
        out["Original"] = res["Original"]
        out["Trend"] = res["Trend"]

        for p in PERIODS:
            comp_name = f"Cycle_{p}m"
            phase_label_name = f"PhaseLabel_{p}m"
            comp = res[comp_name]
            phase_label = classify_phase(comp)
            out[comp_name] = comp
            out[phase_label_name] = phase_label

        # 保存详细结果
        fname = f"huatai_phase_{col}.parquet"
        fpath = Path("data") / fname
        fpath.parent.mkdir(parents=True, exist_ok=True)
        out.to_parquet(fpath)

        # 摘要：最近 20 年的主要周期相位（200/100/42 月）
        lines.append(f"## 指标：{col}")
        lines.append("")

        recent = out.loc[out.index >= (out.index.max() - pd.DateOffset(years=20))]
        summary_rows = []
        for idx, row in recent.iterrows():
            summary_rows.append(
                {
                    "Date": idx.strftime("%Y-%m"),
                    "200m": row.get("PhaseLabel_200m", None),
                    "100m": row.get("PhaseLabel_100m", None),
                    "42m": row.get("PhaseLabel_42m", None),
                }
            )
        summary_df = pd.DataFrame(summary_rows).set_index("Date")

        lines.append("最近 20 年关键周期相位（200/100/42 月）：")
        lines.append("")
        # 仅展示每年 12 月，避免表格过长
        annual = summary_df[summary_df.index.str.endswith("-12")]
        lines.append(annual.to_markdown())
        lines.append("")

    return "\n".join(lines)


def main() -> None:
    df = load_huatai_db()
    md = build_phase_timeline(df)

    out_dir = Path("output")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "huatai_cycle_phase_timeline.md"
    out_path.write_text(md, encoding="utf-8")
    print(f"Wrote phase timeline summary to {out_path}")


if __name__ == "__main__":
    main()

