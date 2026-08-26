"""
Huatai-style Gaussian cycle scan on Tushare-based data.

This script:
- Loads `data/huatai_db_monthly.parquet` (built via build_huatai_db_from_tushare.py)
- For each series, computes Gaussian-FFT cycle metrics for:
    200, 100, 42, 21, 12 个月周期（按月频）
- 同时基于年度数据（年末值）重复一次扫描，用于验证长期周期
- 输出 Markdown 报告：`output/huatai_gauss_cycle_summary.md`

核心指标：
- variance_share: 该周期成分方差占总方差的比例
- snr_local: 频谱在目标频率附近的局部信噪比
"""

from __future__ import annotations

from pathlib import Path
import os
import sys

import pandas as pd

# Ensure project root on path
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from cycle_analysis_system.huatai.gaussian_filtering import (  # type: ignore
    scan_cycles_for_series,
)


TARGET_PERIODS_MONTHS = [200.0, 100.0, 42.0, 21.0, 12.0]


def load_huatai_db() -> pd.DataFrame:
    path = Path("data") / "huatai_db_monthly.parquet"
    if not path.exists():
        raise FileNotFoundError(f"{path} not found – run build_huatai_db_from_tushare.py first.")
    df = pd.read_parquet(path)
    return df


def series_to_annual(s: pd.Series) -> pd.Series:
    """
    Convert a monthly series to annual frequency by taking year-end observation.
    For同比类（如CPI、PPI），这相当于看每年12月的同比。
    """
    return s.resample("A-DEC").last().dropna()


def build_summary(df: pd.DataFrame) -> str:
    lines = []
    lines.append("# Huatai Gaussian Cycle Scan (Tushare 数据)\n")
    lines.append("")
    lines.append("数据来源：`data/huatai_db_monthly.parquet`，起始约 1960-12，截止 2025-12。")
    lines.append("")
    lines.append("目标周期（按月）：200, 100, 42, 21, 12。")
    lines.append("")

    for col in df.columns:
        s = df[col].dropna()
        if s.size < 60:
            continue  # too short

        lines.append(f"## 指标：{col}")
        lines.append("")

        # Monthly scan
        scan_m = scan_cycles_for_series(s, TARGET_PERIODS_MONTHS, dt=1.0, width_frac=0.25)
        scan_m.index.name = "周期(月)"
        scan_m_rounded = scan_m.round(3)

        lines.append("**月度数据 (dt = 1 月)**")
        lines.append("")
        lines.append(scan_m_rounded.to_markdown())
        lines.append("")

        # Annual scan – convert target months to years
        s_a = series_to_annual(s)
        if s_a.size >= 20:
            target_years = [p / 12.0 for p in TARGET_PERIODS_MONTHS]
            scan_y = scan_cycles_for_series(s_a, target_years, dt=1.0, width_frac=0.25)
            # 索引显示为“xx月对应的年数”
            scan_y.index = [f"{int(p)}m({p/12:.1f}y)" for p in TARGET_PERIODS_MONTHS]
            scan_y.index.name = "目标周期"
            scan_y_rounded = scan_y.round(3)

            lines.append("**年度数据 (年末, dt = 1 年)**")
            lines.append("")
            lines.append(scan_y_rounded.to_markdown())
            lines.append("")

    return "\n".join(lines)


def main() -> None:
    df = load_huatai_db()
    md = build_summary(df)

    out_dir = Path("output")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "huatai_gauss_cycle_summary.md"

    out_path.write_text(md, encoding="utf-8")
    print(f"Wrote Gaussian cycle summary to {out_path}")


if __name__ == "__main__":
    main()

