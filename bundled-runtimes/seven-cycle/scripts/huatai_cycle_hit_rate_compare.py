"""
Compare Gaussian vs Butterworth cycle components in terms of their ability to
predict future equity index returns (命中率).

Design (简化版 Huatai 框架验证):
- 指标: 通胀相关 macro_cpi_yoy, macro_ppi_yoy
- 资产: idx_hs300_ret_m (沪深300收益)
- 周期: 200 / 100 / 42 月
- 预测规则: 用周期成分的符号预测未来12个月累积收益的方向
- 命中率: 预测方向与实际方向一致的比例

Outputs:
- Markdown report at output/huatai_cycle_hit_rate_compare.md
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
from cycle_analysis_system.huatai.gaussian_filtering import (  # type: ignore
    GaussianCycleConfig,
    gaussian_cycle_component,
)


INDICATORS = ["macro_cpi_yoy", "macro_ppi_yoy"]
ASSET = "idx_hs300_ret_m"
PERIODS = [200, 100, 42]
HORIZON = 12  # months


def load_huatai_db() -> pd.DataFrame:
    path = Path("data") / "huatai_db_monthly.parquet"
    if not path.exists():
        raise FileNotFoundError(f"{path} not found – run build_huatai_db_from_tushare.py first.")
    return pd.read_parquet(path)


def compute_forward_return(ret_m: pd.Series, horizon: int = 12) -> pd.Series:
    """
    Compute forward cumulative log return over `horizon` months.
    """
    r = ret_m.dropna()
    log_r = np.log1p(r)
    # Rolling sum over horizon, then shift so that value at t uses [t, t+H-1]
    cum_log = log_r.rolling(horizon).sum().shift(-horizon + 1)
    fwd = np.expm1(cum_log)
    return fwd


def sign_series(s: pd.Series) -> pd.Series:
    """Map series to -1/0/+1 sign."""
    out = s.copy()
    out[:] = 0
    out[s > 0] = 1
    out[s < 0] = -1
    return out


def hit_rate_from_signs(pred: pd.Series, realized: pd.Series) -> float:
    """
    Compute hit rate: fraction of non-zero predictions where sign matches.
    """
    aligned = pd.concat([pred, realized], axis=1, keys=["pred", "real"]).dropna()
    aligned = aligned[aligned["pred"] != 0]
    if aligned.empty:
        return np.nan
    hits = (aligned["pred"] == aligned["real"]).sum()
    return hits / len(aligned)


def run_comparison(df: pd.DataFrame) -> str:
    lines: list[str] = []
    lines.append("# Huatai Cycle Hit-Rate Comparison (Gaussian vs Butterworth)")
    lines.append("")
    lines.append("数据：`data/huatai_db_monthly.parquet`；资产：idx_hs300_ret_m；指标：CPI/PPI。")
    lines.append("预测规则：周期成分 > 0 预测未来12个月收益为正，< 0 预测为负。")
    lines.append("")

    asset_ret = df[ASSET].dropna()
    fwd_12m = compute_forward_return(asset_ret, horizon=HORIZON)

    # Butterworth decomposer
    decomposer = CycleDecomposer(periods=PERIODS, sample_rate=1)

    rows = []

    for ind in INDICATORS:
        if ind not in df.columns:
            continue
        s = df[ind].dropna()
        if s.size < 60:
            continue

        # Align indicator with asset forward returns
        common_idx = s.index.intersection(fwd_12m.index)
        s_common = s.loc[common_idx]
        fwd_common = fwd_12m.loc[common_idx]

        # Butterworth components
        decomp = decomposer.decompose(s_common)

        for p in PERIODS:
            comp_b = pd.Series(decomp[f"Cycle_{p}m"], index=s_common.index)
            pred_b = sign_series(comp_b)
            real_sign = sign_series(fwd_common)
            hr_b = hit_rate_from_signs(pred_b, real_sign)

            # Gaussian component
            cfg = GaussianCycleConfig(target_period=float(p), width_frac=0.25)
            comp_g = gaussian_cycle_component(s_common, cfg, dt=1.0)
            pred_g = sign_series(comp_g)
            hr_g = hit_rate_from_signs(pred_g, real_sign)

            # Sample size
            n_obs = pd.concat([pred_b, real_sign], axis=1).dropna()
            n_obs = n_obs[n_obs.iloc[:, 0] != 0].shape[0]

            rows.append(
                {
                    "indicator": ind,
                    "period_m": p,
                    "n_obs": n_obs,
                    "hit_rate_butterworth": hr_b,
                    "hit_rate_gaussian": hr_g,
                }
            )

    if not rows:
        lines.append("No valid results.")
        return "\n".join(lines)

    res_df = pd.DataFrame.from_records(rows)
    res_df = res_df.sort_values(["indicator", "period_m"])
    res_df_rounded = res_df.round({"hit_rate_butterworth": 3, "hit_rate_gaussian": 3})

    lines.append("## 命中率结果（预测未来12个月沪深300收益方向）")
    lines.append("")
    lines.append(res_df_rounded.to_markdown(index=False))
    lines.append("")

    return "\n".join(lines)


def main() -> None:
    df = load_huatai_db()
    md = run_comparison(df)

    out_dir = Path("output")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "huatai_cycle_hit_rate_compare.md"
    out_path.write_text(md, encoding="utf-8")
    print(f"Wrote hit-rate comparison to {out_path}")


if __name__ == "__main__":
    main()

