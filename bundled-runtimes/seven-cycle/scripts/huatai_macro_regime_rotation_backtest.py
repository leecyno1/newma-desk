"""
Macro Regime -> Style Rotation Backtest (Huatai-style, simplified).

Idea:
- Use CPI (100m) and PPI (42m) cycle phase labels to define 4 macro regimes:
    * Reflation (复苏): 通胀与工业价格自低位回升
    * Overheat (过热): 通胀与工业价格高位/上行
    * Disinflation (通胀回落): 工业价格回落，通胀仍偏高或回落
    * Deflation (通缩/疲弱): 通胀与工业价格均低位/下行
- For each regime, allocate among HS300 / CSI500 / CSI1000 as style proxies:
    * HS300: large-cap / quality
    * CSI500: mid-cap / cyclicals
    * CSI1000: small-cap / high beta
- Compare regime-rotated portfolio to HS300 and equal-weight benchmark.

Outputs:
- Markdown report: output/huatai_macro_regime_rotation_backtest.md
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


ASSET_COLS = ["idx_hs300_ret_m", "idx_csi500_ret_m", "idx_csi1000_ret_m"]


def load_data():
    df = pd.read_parquet(Path("data") / "huatai_db_monthly.parquet")
    cpi_phase = pd.read_parquet(Path("data") / "huatai_phase_macro_cpi_yoy.parquet")
    ppi_phase = pd.read_parquet(Path("data") / "huatai_phase_macro_ppi_yoy.parquet")

    # Extract needed phase labels
    phase = pd.DataFrame(index=df.index)
    phase["cpi_100"] = cpi_phase.get("PhaseLabel_100m")
    phase["ppi_42"] = ppi_phase.get("PhaseLabel_42m")

    return df, phase


def classify_regime(cpi_phase: str | float, ppi_phase: str | float) -> str | None:
    """
    Define 4 macro regimes based on CPI 100m and PPI 42m phase labels.
    """
    if not isinstance(cpi_phase, str) or not isinstance(ppi_phase, str):
        return None

    # Reflation: both below zero and turning up / early Up
    if ppi_phase in {"Low", "Up"} and cpi_phase in {"Low", "Up"}:
        return "Reflation"

    # Overheat: both above zero and still Up/High
    if ppi_phase in {"Up", "High"} and cpi_phase in {"Up", "High"}:
        return "Overheat"

    # Disinflation: PPI cooling while CPI still high or falling from high
    if ppi_phase in {"Down", "Low"} and cpi_phase in {"High", "Down"}:
        return "Disinflation"

    # Deflation / Weak: both below zero and not clearly reflating
    if ppi_phase in {"Down", "Low"} and cpi_phase in {"Low", "Down"}:
        return "Deflation"

    return None


REGIME_WEIGHTS = {
    # Reflation: risk-on, tilt to mid/small
    "Reflation": {
        "idx_hs300_ret_m": 0.2,
        "idx_csi500_ret_m": 0.4,
        "idx_csi1000_ret_m": 0.4,
    },
    # Overheat: take profit on small, lean towards large but keep some cyclicals
    "Overheat": {
        "idx_hs300_ret_m": 0.5,
        "idx_csi500_ret_m": 0.3,
        "idx_csi1000_ret_m": 0.2,
    },
    # Disinflation: growth/quality, strong large-cap tilt
    "Disinflation": {
        "idx_hs300_ret_m": 0.6,
        "idx_csi500_ret_m": 0.3,
        "idx_csi1000_ret_m": 0.1,
    },
    # Deflation: defensive, even more large-cap
    "Deflation": {
        "idx_hs300_ret_m": 0.7,
        "idx_csi500_ret_m": 0.2,
        "idx_csi1000_ret_m": 0.1,
    },
}


def compute_portfolio_returns(rets: pd.DataFrame, regimes: pd.Series) -> pd.Series:
    """
    Given asset returns and regime labels, compute monthly portfolio returns
    using the REGIME_WEIGHTS mapping.
    """
    # Build a weights DataFrame aligned with rets index
    weights = pd.DataFrame(0.0, index=rets.index, columns=ASSET_COLS)
    for reg, wmap in REGIME_WEIGHTS.items():
        mask = regimes == reg
        for col, w in wmap.items():
            weights.loc[mask, col] = w

    # Normalize per row in case of missing columns
    row_sums = weights.sum(axis=1)
    row_sums[row_sums == 0] = 1.0
    weights = weights.div(row_sums, axis=0)

    port_ret = (rets * weights).sum(axis=1)
    return port_ret


def summary_stats(ret: pd.Series) -> dict:
    r = ret.dropna()
    if r.empty:
        return {"ann_ret": np.nan, "ann_vol": np.nan, "sharpe": np.nan, "max_dd": np.nan}

    # Annualized return
    total_ret = (1 + r).prod()
    n_months = len(r)
    ann_ret = total_ret ** (12 / n_months) - 1

    # Annualized vol
    ann_vol = r.std() * np.sqrt(12)
    sharpe = ann_ret / ann_vol if ann_vol > 0 else np.nan

    # Max drawdown
    cum = (1 + r).cumprod()
    peak = cum.cummax()
    dd = (cum / peak) - 1
    max_dd = dd.min()

    return {
        "ann_ret": float(ann_ret),
        "ann_vol": float(ann_vol),
        "sharpe": float(sharpe),
        "max_dd": float(max_dd),
    }


def run_backtest() -> str:
    df, phase = load_data()

    # Restrict to period where all three indices exist (HS300 etc. from 2005)
    rets = df[ASSET_COLS].dropna()

    # Align phases
    phase = phase.reindex(rets.index)
    phase = phase.dropna(subset=["cpi_100", "ppi_42"])

    # Classify regimes
    regimes = phase.apply(lambda row: classify_regime(row["cpi_100"], row["ppi_42"]), axis=1)
    regimes = regimes.dropna()

    # Align returns again
    rets = rets.reindex(regimes.index).dropna()
    regimes = regimes.reindex(rets.index)

    # Regime-rotated portfolio
    port_ret = compute_portfolio_returns(rets, regimes)

    # Benchmarks
    hs300 = rets["idx_hs300_ret_m"]
    ew = rets.mean(axis=1)  # equal-weight of HS300/500/1000

    # Summary stats
    stats_rows = []
    for name, series in [
        ("RegimeRotation", port_ret),
        ("HS300", hs300),
        ("EqualWeight", ew),
    ]:
        s = summary_stats(series)
        s["strategy"] = name
        stats_rows.append(s)

    stats_df = pd.DataFrame(stats_rows).set_index("strategy")

    # Regime distribution & conditional returns
    reg_counts = regimes.value_counts().sort_index()
    reg_avg_ret = port_ret.groupby(regimes).mean().sort_index()

    lines: list[str] = []
    lines.append("# Huatai Macro Regime -> Style Rotation Backtest")
    lines.append("")
    lines.append("样本：对齐 HS300/CSI500/CSI1000 和 CPI/PPI 相位后的月度数据（约自 2005 年起）。")
    lines.append("")
    lines.append("## 1. 策略说明")
    lines.append("")
    lines.append("- 周期信号：CPI 100m / PPI 42m 的相位 (Low/Up/High/Down)。")
    lines.append("- 宏观 Regime 划分：")
    lines.append("    - Reflation: PPI_42 in {Low, Up} & CPI_100 in {Low, Up}")
    lines.append("    - Overheat: PPI_42 in {Up, High} & CPI_100 in {Up, High}")
    lines.append("    - Disinflation: PPI_42 in {Down, Low} & CPI_100 in {High, Down}")
    lines.append("    - Deflation: PPI_42 in {Down, Low} & CPI_100 in {Low, Down}")
    lines.append("- 风格权重 (HS300 / CSI500 / CSI1000)：")
    for reg, wmap in REGIME_WEIGHTS.items():
        lines.append(f"    - {reg}: {wmap}")
    lines.append("")

    lines.append("## 2. 年化表现对比")
    lines.append("")
    lines.append(stats_df.round(3).to_markdown())
    lines.append("")

    lines.append("## 3. Regime 覆盖与条件收益")
    lines.append("")
    reg_df = pd.DataFrame(
        {
            "months": reg_counts,
            "weight": reg_counts / reg_counts.sum(),
            "avg_port_ret": reg_avg_ret,
        }
    ).round(4)
    lines.append(reg_df.to_markdown())
    lines.append("")

    return "\n".join(lines)


def main() -> None:
    md = run_backtest()
    out_dir = Path("output")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "huatai_macro_regime_rotation_backtest.md"
    out_path.write_text(md, encoding="utf-8")
    print(f"Wrote macro regime rotation backtest to {out_path}")


if __name__ == "__main__":
    main()

