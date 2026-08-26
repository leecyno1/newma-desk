"""
Build a first-pass Huatai-style monthly database using Tushare.

Design:
- Use Tushare as the single source for China-related data
- Focus initially on a small but representative set of indices and macro series
- Output a wide monthly DataFrame suitable for both:
  * Huatai Gaussian-wave cycle replication
  * Our Butterworth-based deep-cycle decomposition

Usage (example):
    export TUSHARE_TOKEN='your_token_here'
    python scripts/build_huatai_db_from_tushare.py
"""

from __future__ import annotations

from pathlib import Path
import os
import sys

import pandas as pd

# Ensure project root is on sys.path so that cycle_analysis_system is importable
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from cycle_analysis_system.huatai.data_loader_ts import (  # type: ignore
    TSConfig,
    get_index_monthly_return,
    get_macro_monthly,
)


def build_huatai_db(
    start_date: str = "19600101",
    end_date: str | None = None,
) -> pd.DataFrame:
    """
    Construct a monthly panel of key indices and macro indicators.

    Notes
    -----
    - Index series are stored as simple monthly price returns.
    - Macro series keep the provider's original units (e.g. YoY%).
      We can add transformed versions (MoM, filtered, etc.) in later passes.
    """
    cfg = TSConfig(token="")  # read token from TUSHARE_TOKEN env by default

    # 1) Equity indices (basic set; can be extended later)
    index_codes = {
        "idx_sh_comp": "000001.SH",  # 上证综指
        "idx_sz_comp": "399001.SZ",  # 深证成指
        "idx_hs300": "000300.SH",
        "idx_csi500": "000905.SH",
        "idx_csi1000": "000852.SH",
    }

    monthly_frames: dict[str, pd.Series] = {}

    for col_name, ts_code in index_codes.items():
        s = get_index_monthly_return(cfg, ts_code=ts_code, start_date=start_date, end_date=end_date)
        if s.empty:
            continue
        monthly_frames[f"{col_name}_ret_m"] = s

    # 2) Macro inflation indicators (CPI YoY, PPI YoY as a start)
    macro_keys = ["cpi_yoy", "ppi_yoy"]
    for key in macro_keys:
        s = get_macro_monthly(cfg, indicator=key, start_date=start_date, end_date=end_date)
        if s.empty:
            continue
        monthly_frames[f"macro_{key}"] = s

    if not monthly_frames:
        raise RuntimeError("No series were loaded from Tushare – check token and connectivity.")

    # Align all series on a common monthly index (outer join, then sort)
    df = pd.concat(monthly_frames.values(), axis=1, keys=monthly_frames.keys())
    df = df.sort_index()

    return df


def main() -> None:
    df = build_huatai_db()

    out_dir = Path("data")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "huatai_db_monthly.parquet"

    df.to_parquet(out_path)
    print(f"Saved Huatai monthly DB to {out_path} with shape {df.shape}")


if __name__ == "__main__":
    main()
