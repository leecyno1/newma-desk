#!/usr/bin/env python3
"""
Generate gold/silver/crude + ratio charts from TuShare and save as PNGs.

Setup (recommended):
  python3 -m venv .venv
  .venv/bin/python -m pip install --upgrade pip
  .venv/bin/python -m pip install pandas matplotlib tushare

Token:
  export TUSHARE_TOKEN=xxxxxxxx
  # or put it in .tushare_token (one line)

Run:
  .venv/bin/python scripts/tushare_make_charts.py
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Callable, List, Tuple


def read_token() -> str:
    token = (os.environ.get("TUSHARE_TOKEN") or os.environ.get("TS_TOKEN") or "").strip()
    if token:
        return token
    p = Path(".tushare_token")
    if p.exists():
        return p.read_text(encoding="utf-8").strip()
    return ""


def ensure_dirs() -> Tuple[Path, Path]:
    out_dir = Path("figures") / "2026-01-31"
    data_dir = Path("data") / "tushare" / "2026-01-31"
    out_dir.mkdir(parents=True, exist_ok=True)
    data_dir.mkdir(parents=True, exist_ok=True)
    return out_dir, data_dir


def fetch_first(fn: Callable, candidates: List[str], **kwargs):
    last_err = None
    for ts_code in candidates:
        try:
            df = fn(ts_code=ts_code, **kwargs)
            if df is not None and len(df.index) > 0:
                return ts_code, df
        except Exception as e:  # noqa: BLE001
            last_err = e
            continue
    if last_err:
        raise last_err
    raise RuntimeError("No ts_code candidates succeeded")


def rsi(series, period: int = 14):
    # Wilder-style RSI via EMA smoothing (good enough for discussion charts).
    import pandas as pd

    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, pd.NA)
    return 100 - (100 / (1 + rs))


def main() -> int:
    token = read_token()
    if not token:
        print("Missing TuShare token. Set TUSHARE_TOKEN/TS_TOKEN or create .tushare_token.", flush=True)
        return 2

    out_dir, data_dir = ensure_dirs()

    import pandas as pd
    import matplotlib.pyplot as plt
    import tushare as ts

    ts.set_token(token)
    pro = ts.pro_api()

    # Date format: YYYYMMDD
    start_date = "20230101"
    end_date = "20260131"
    event_date = pd.to_datetime("2026-01-30")  # “沃什提名”冲击点（素材使用该日期）

    fut_kwargs = dict(start_date=start_date, end_date=end_date)

    # Futures (best-effort; TuShare symbols vary across accounts/versions).
    gold_code, gold = fetch_first(pro.fut_daily, ["AU.SHF", "AU.SHFE", "AU0.SHF", "AU9999.SGE"], **fut_kwargs)
    silver_code, silver = fetch_first(pro.fut_daily, ["AG.SHF", "AG.SHFE", "AG0.SHF", "AG9999.SGE"], **fut_kwargs)
    oil_code, oil = fetch_first(pro.fut_daily, ["SC.INE", "SC0.INE", "SC.INE0"], **fut_kwargs)

    # ETF (optional)
    etf = None
    etf_code = None
    try:
        etf_code, etf = fetch_first(
            pro.fund_daily,
            ["518880.SH", "159934.SZ", "518800.SH", "518660.SH"],
            start_date=start_date,
            end_date=end_date,
        )
    except Exception:
        etf = None
        etf_code = None

    def prep(df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        if "trade_date" not in df.columns or "close" not in df.columns:
            raise RuntimeError(f"Unexpected schema: {list(df.columns)}")
        df["trade_date"] = pd.to_datetime(df["trade_date"])
        return df.sort_values("trade_date")

    gold = prep(gold)
    silver = prep(silver)
    oil = prep(oil)
    if etf is not None and len(etf.index) > 0:
        etf = prep(etf)

    gold.to_csv(data_dir / f"gold_{gold_code}.csv", index=False)
    silver.to_csv(data_dir / f"silver_{silver_code}.csv", index=False)
    oil.to_csv(data_dir / f"oil_{oil_code}.csv", index=False)
    if etf is not None:
        etf.to_csv(data_dir / f"gold_etf_{etf_code}.csv", index=False)

    def plot_price_ma(df: pd.DataFrame, title: str, out_path: Path):
        fig, ax = plt.subplots(figsize=(10, 4.5))
        ax.plot(df["trade_date"], df["close"], label="Close", linewidth=1.2)
        for w in (20, 60, 120):
            ax.plot(df["trade_date"], df["close"].rolling(w).mean(), label=f"MA{w}", linewidth=1.0)
        ax.axvline(event_date, color="red", linestyle="--", linewidth=1.0, alpha=0.8)
        ax.set_title(title)
        ax.grid(True, alpha=0.25)
        ax.legend(loc="upper left", ncol=4, fontsize=8)
        fig.tight_layout()
        fig.savefig(out_path, dpi=160)
        plt.close(fig)

    plot_price_ma(gold, f"Gold futures ({gold_code}) - Close & MAs", out_dir / "gold_futures_ma.png")
    plot_price_ma(silver, f"Silver futures ({silver_code}) - Close & MAs", out_dir / "silver_futures_ma.png")
    plot_price_ma(oil, f"Crude futures ({oil_code}) - Close & MAs", out_dir / "crude_futures_ma.png")

    merged = (
        gold[["trade_date", "close"]]
        .rename(columns={"close": "gold"})
        .merge(silver[["trade_date", "close"]].rename(columns={"close": "silver"}), on="trade_date", how="inner")
        .merge(oil[["trade_date", "close"]].rename(columns={"close": "oil"}), on="trade_date", how="inner")
    )
    merged["gold_silver"] = merged["gold"] / merged["silver"]
    merged["gold_oil"] = merged["gold"] / merged["oil"]
    merged.to_csv(data_dir / "merged_ratios.csv", index=False)

    def plot_line(x, y, title: str, out_path: Path):
        fig, ax = plt.subplots(figsize=(10, 4.5))
        ax.plot(x, y, linewidth=1.2)
        ax.axvline(event_date, color="red", linestyle="--", linewidth=1.0, alpha=0.8)
        ax.set_title(title)
        ax.grid(True, alpha=0.25)
        fig.tight_layout()
        fig.savefig(out_path, dpi=160)
        plt.close(fig)

    plot_line(merged["trade_date"], merged["gold_silver"], "Gold/Silver ratio", out_dir / "gold_silver_ratio.png")
    plot_line(merged["trade_date"], merged["gold_oil"], "Gold/Oil ratio", out_dir / "gold_oil_ratio.png")

    rets = merged.copy()
    rets["gold_ret"] = rets["gold"].pct_change()
    rets["oil_ret"] = rets["oil"].pct_change()
    rets["corr_60d"] = rets["gold_ret"].rolling(60).corr(rets["oil_ret"])
    plot_line(
        rets["trade_date"],
        rets["corr_60d"],
        "Rolling 60D correlation: gold vs oil returns",
        out_dir / "rolling_corr_gold_oil.png",
    )

    if etf is not None:
        etf_plot = etf.copy()
        etf_plot["rsi14"] = rsi(etf_plot["close"], 14)
        fig, ax = plt.subplots(figsize=(10, 4.5))
        ax.plot(etf_plot["trade_date"], etf_plot["close"], label="ETF Close", linewidth=1.2)
        ax2 = ax.twinx()
        ax2.plot(etf_plot["trade_date"], etf_plot["rsi14"], label="RSI14", linewidth=1.0, color="orange", alpha=0.9)
        ax.axvline(event_date, color="red", linestyle="--", linewidth=1.0, alpha=0.8)
        ax.set_title(f"Gold ETF ({etf_code}) - Close & RSI14")
        ax.grid(True, alpha=0.25)
        ax.legend(loc="upper left", fontsize=8)
        ax2.legend(loc="upper right", fontsize=8)
        fig.tight_layout()
        fig.savefig(out_dir / "gold_etf_close_rsi.png", dpi=160)
        plt.close(fig)

    (out_dir / "README.md").write_text(
        """# Charts (TuShare)

Generated by `scripts/tushare_make_charts.py`.

- `gold_futures_ma.png`
- `silver_futures_ma.png`
- `crude_futures_ma.png`
- `gold_silver_ratio.png`
- `gold_oil_ratio.png`
- `rolling_corr_gold_oil.png`
- `gold_etf_close_rsi.png` (if ETF data is available)
""",
        encoding="utf-8",
    )

    print(f"Wrote charts to {out_dir}/ and data to {data_dir}/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
