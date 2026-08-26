"""
Build a unified indicator panel from multiple data sources (Tushare Pro, OpenBB).

Rules:
- 2000 年之前：以年频为主（year-end），主要用于长周期统计；
- 2000 年之后：以月频为主，同时保留年频（由月频聚合）；
- 对每个指标，尽量构造：
    * level / price / index（标准化主序列）
    * MoM（环比）
    * YoY（同比）
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

from cycle_analysis_system.indicators.indicator_registry import INDICATORS  # type: ignore
from cycle_analysis_system.indicators.fetchers import (  # type: ignore
    TSConfig,
    fetch_raw_series,
    to_monthly_and_annual,
    derive_yoy_mom,
)


def build_panel():
    ts_cfg = TSConfig(token=os.environ.get("TUSHARE_TOKEN", ""))

    monthly_frames = {}
    annual_frames = {}

    def add_variants(frames: dict[str, pd.Series], ind, series: pd.Series, base_freq: str) -> None:
        """
        Store a base series and its derived variants into frames.

        Column naming policy:
        - rate_yoy / rate_mom: store as `ind.id` (avoid double-suffix)
        - return   -> *_RET (+ optional *_TRAIL12 for monthly)
        - others   -> *_LEVEL (+ derived *_MOM/*_YOY when applicable)
        """
        if series.empty:
            return

        if ind.value_type == "rate_yoy":
            frames[ind.id] = series
            return
        if ind.value_type == "rate_mom":
            frames[ind.id] = series
            return
        if ind.value_type == "return":
            frames[f"{ind.id}_RET"] = series
            if base_freq == "M":
                trail12 = derive_yoy_mom(series, base_freq="M", value_type="return").get("yoy")
                if trail12 is not None and not trail12.empty:
                    frames[f"{ind.id}_TRAIL12"] = trail12
            return

        frames[f"{ind.id}_LEVEL"] = series
        derived = derive_yoy_mom(series, base_freq=base_freq, value_type=ind.value_type)
        for k, s in derived.items():
            # Do not overwrite an existing base YoY/MoM series if it exists.
            frames.setdefault(f"{ind.id}_{k.upper()}", s)

    for ind in INDICATORS:
        print(f"Fetching {ind.id} from {ind.primary_source} ({ind.backend})...")
        try:
            raw = fetch_raw_series(ind, ts_cfg=ts_cfg)
        except Exception as e:
            print(f"  ERROR: {e}")
            continue
        if raw.empty:
            print("  -> no data")
            continue

        m, a = to_monthly_and_annual(raw, ind.value_type, ind.base_freq)

        # Truncate: pre-2000 年的月频数据只保留为年频，2000 年后保留月频
        if not m.empty:
            m_post2000 = m[m.index >= pd.Timestamp("2000-01-31")]
            if not m_post2000.empty:
                add_variants(monthly_frames, ind, m_post2000, base_freq="M")

        if not a.empty:
            a_all = a.copy()
            add_variants(annual_frames, ind, a_all, base_freq="A")

    # 合并成宽表
    if monthly_frames:
        df_m = pd.concat(monthly_frames.values(), axis=1, keys=monthly_frames.keys()).sort_index()
    else:
        df_m = pd.DataFrame()

    if annual_frames:
        df_a = pd.concat(annual_frames.values(), axis=1, keys=annual_frames.keys()).sort_index()
    else:
        df_a = pd.DataFrame()

    out_dir = Path("data")
    out_dir.mkdir(parents=True, exist_ok=True)
    df_m.to_parquet(out_dir / "indicator_panel_monthly.parquet")
    df_a.to_parquet(out_dir / "indicator_panel_annual.parquet")

    print("Monthly panel shape:", df_m.shape)
    print("Annual panel shape:", df_a.shape)


def main():
    build_panel()


if __name__ == "__main__":
    main()
