#!/usr/bin/env python3
"""
Gold futures (AU.SHF) leverage (1 / margin rate) + implied vol (from gold options) over last 10 years.

Outputs:
  - figures/gold_leverage_iv_10y.png
  - data/tushare/gold_leverage_iv_10y.csv

Notes:
  - Futures leverage uses SHFE exchange margin rate from TuShare `fut_settle` for the mapped main contract.
  - Implied vol is approximated via Black-76 on the nearest-to-money call/put of the mapped underlying month.
    TuShare SHFE gold options data in this dataset appears to start around 2025-02, so IV will be missing before that.
  - Risk-free rate is fixed at 2% for IV inversion (small impact vs the volatility itself).
"""

from __future__ import annotations

import math
import os
from pathlib import Path
from typing import Dict, Optional, Tuple


def read_token() -> str:
    token = (os.environ.get("TUSHARE_TOKEN") or os.environ.get("TS_TOKEN") or "").strip()
    if token:
        return token
    p = Path(".tushare_token")
    if p.exists():
        return p.read_text(encoding="utf-8").strip()
    return ""


def norm_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def black76_price(F: float, K: float, T: float, r: float, sigma: float, call: bool) -> float:
    if T <= 0:
        intrinsic = max(F - K, 0.0) if call else max(K - F, 0.0)
        return intrinsic
    if sigma <= 0:
        intrinsic = max(F - K, 0.0) if call else max(K - F, 0.0)
        return math.exp(-r * T) * intrinsic

    srt = sigma * math.sqrt(T)
    d1 = (math.log(F / K) + 0.5 * sigma * sigma * T) / srt
    d2 = d1 - srt
    df = math.exp(-r * T)
    if call:
        return df * (F * norm_cdf(d1) - K * norm_cdf(d2))
    return df * (K * norm_cdf(-d2) - F * norm_cdf(-d1))


def implied_vol_black76(price: float, F: float, K: float, T: float, r: float, call: bool) -> Optional[float]:
    if price is None:
        return None
    price = float(price)
    if price <= 0 or F <= 0 or K <= 0 or T <= 0:
        return None

    # No-arbitrage bounds (European)
    df = math.exp(-r * T)
    intrinsic = df * (max(F - K, 0.0) if call else max(K - F, 0.0))
    upper = df * (F if call else K)  # loose but safe
    if price < intrinsic * 0.999 or price > upper * 1.001:
        return None

    lo, hi = 1e-6, 4.0  # 400% vol upper bound
    for _ in range(80):
        mid = (lo + hi) / 2.0
        pmid = black76_price(F, K, T, r, mid, call)
        if pmid > price:
            hi = mid
        else:
            lo = mid
    return (lo + hi) / 2.0


def parse_opt_strike(ts_code: str) -> Tuple[Optional[str], Optional[float], Optional[str]]:
    """
    Example: AU2610C960.SHF -> (underlying_prefix='AU2610', strike=960.0, cp='C')
    """
    s = ts_code.split(".")[0]
    if len(s) < 7:
        return None, None, None
    if not s.startswith("AU"):
        return None, None, None
    # Find call/put marker
    if "C" in s:
        cp = "C"
        parts = s.split("C")
    elif "P" in s:
        cp = "P"
        parts = s.split("P")
    else:
        return None, None, None
    if len(parts) != 2:
        return None, None, None
    underlying = parts[0]  # AU2610
    try:
        strike = float(parts[1])
    except Exception:
        return underlying, None, cp
    return underlying, strike, cp


def main() -> int:
    token = read_token()
    if not token:
        print("Missing TuShare token. Set TUSHARE_TOKEN/TS_TOKEN or create .tushare_token.", flush=True)
        return 2

    # Local imports (keep repo importable without deps)
    import pandas as pd
    import matplotlib.pyplot as plt
    import tushare as ts

    ts.set_token(token)
    pro = ts.pro_api()

    def query_all(api_name: str, **kwargs):
        # TuShare endpoints commonly cap at 2000 rows per call; paginate via offset.
        import pandas as pd

        parts = []
        offset = 0
        while True:
            chunk = pro.query(api_name, limit=2000, offset=offset, **kwargs)
            if chunk is None or len(chunk.index) == 0:
                break
            parts.append(chunk)
            if len(chunk.index) < 2000:
                break
            offset += 2000
        if not parts:
            return pd.DataFrame()
        return pd.concat(parts, ignore_index=True)

    out_fig = Path("figures")
    out_fig.mkdir(parents=True, exist_ok=True)
    out_csv_dir = Path("data") / "tushare"
    out_csv_dir.mkdir(parents=True, exist_ok=True)

    # 10y window ending today-ish (we pin end to 20260201 because system date is 2026-02-01).
    start_date = "20160201"
    end_date = "20260201"

    # 1) Futures continuous + mapping to main contract
    fut = query_all("fut_daily", ts_code="AU.SHF", start_date=start_date, end_date=end_date)
    if fut is None or len(fut.index) == 0:
        raise RuntimeError("No AU.SHF fut_daily data returned")
    fut["trade_date"] = pd.to_datetime(fut["trade_date"])
    fut = fut.sort_values("trade_date")

    mapping = query_all("fut_mapping", ts_code="AU.SHF", start_date=start_date, end_date=end_date)
    mapping["trade_date"] = pd.to_datetime(mapping["trade_date"])
    mapping = mapping.sort_values("trade_date")

    df = fut.merge(mapping[["trade_date", "mapping_ts_code"]], on="trade_date", how="left")

    # 2) Margin rate per mapped contract: pull fut_settle per unique contract once.
    settle_by_contract: Dict[str, pd.DataFrame] = {}
    contracts = sorted({c for c in df["mapping_ts_code"].dropna().unique().tolist() if isinstance(c, str) and c.endswith(".SHF")})
    for c in contracts:
        s = pro.query("fut_settle", ts_code=c, start_date=start_date, end_date=end_date)
        if s is None or len(s.index) == 0:
            continue
        s["trade_date"] = pd.to_datetime(s["trade_date"])
        settle_by_contract[c] = s[["trade_date", "long_margin_rate"]].sort_values("trade_date")

    # Map margin onto df.
    df["margin_rate"] = pd.NA
    for c, s in settle_by_contract.items():
        m = df["mapping_ts_code"] == c
        if not m.any():
            continue
        # join on trade_date
        tmp = df.loc[m, ["trade_date"]].merge(s, on="trade_date", how="left")["long_margin_rate"]
        df.loc[m, "margin_rate"] = tmp.values

    df["leverage"] = df["margin_rate"].astype("float64").rdiv(1.0)  # 1 / margin_rate

    # 3) Implied vol from options (best-effort).
    # Build option basics map for gold options only.
    opt_basic = query_all("opt_basic", exchange="SHFE")
    opt_basic = opt_basic[opt_basic["opt_code"].str.contains("OPAU", na=False)].copy()
    if len(opt_basic.index) == 0:
        df["iv"] = pd.NA
    else:
        opt_basic["maturity_date"] = pd.to_datetime(opt_basic["maturity_date"])
        opt_basic = opt_basic.set_index("ts_code")

        # Only compute IV for dates where gold options exist (based on opt_basic list_date range).
        opt_start = pd.to_datetime(opt_basic["list_date"]).min() if "list_date" in opt_basic.columns else df["trade_date"].min()
        df["iv"] = pd.NA

        r = 0.02

        # For each trade_date >= opt_start: pull all SHFE options for that day, then filter down to AU* and active month.
        for t in df.loc[df["trade_date"] >= opt_start, "trade_date"].tolist():
            td = t.strftime("%Y%m%d")
            try:
                od = pro.query("opt_daily", exchange="SHFE", trade_date=td)
            except Exception:
                continue
            if od is None or len(od.index) == 0:
                continue

            # Filter gold option rows by prefix.
            od = od[od["ts_code"].str.startswith("AU", na=False)].copy()
            if len(od.index) == 0:
                continue

            # Active underlying month from mapping contract (AUxxxx.SHF).
            row = df.loc[df["trade_date"] == t].iloc[0]
            mapping_code = row["mapping_ts_code"]
            if not isinstance(mapping_code, str) or not mapping_code.startswith("AU"):
                continue
            underlying = mapping_code.split(".")[0]  # AU2610

            # Keep options matching this underlying prefix.
            od = od[od["ts_code"].str.startswith(underlying, na=False)]
            if len(od.index) == 0:
                continue

            F = float(row["settle"]) if "settle" in row and pd.notna(row["settle"]) else float(row["close"])
            if not (F and F > 0):
                continue

            # Parse strikes + CP, choose nearest to money call/put by strike distance.
            od["underlying"], od["strike"], od["cp"] = zip(*od["ts_code"].map(parse_opt_strike))
            od = od[pd.notna(od["strike"]) & pd.notna(od["cp"])].copy()
            if len(od.index) == 0:
                continue

            # Attach maturity_date (needed for T). Drop if missing.
            od = od.join(opt_basic[["maturity_date"]], on="ts_code", how="left")
            od = od[pd.notna(od["maturity_date"])].copy()
            if len(od.index) == 0:
                continue

            T = (od["maturity_date"].iloc[0] - t).days / 365.0
            if T <= 0:
                continue

            def pick_nearest(cp: str):
                sub = od[od["cp"] == cp].copy()
                if len(sub.index) == 0:
                    return None
                sub["dist"] = (sub["strike"] - F).abs()
                sub = sub.sort_values(["dist", "vol"], ascending=[True, False])
                return sub.iloc[0]

            c_row = pick_nearest("C")
            p_row = pick_nearest("P")

            ivs = []
            if c_row is not None and pd.notna(c_row.get("settle")):
                iv = implied_vol_black76(float(c_row["settle"]), F, float(c_row["strike"]), T, r, True)
                if iv is not None:
                    ivs.append(iv)
            if p_row is not None and pd.notna(p_row.get("settle")):
                iv = implied_vol_black76(float(p_row["settle"]), F, float(p_row["strike"]), T, r, False)
                if iv is not None:
                    ivs.append(iv)

            if ivs:
                df.loc[df["trade_date"] == t, "iv"] = sum(ivs) / len(ivs)

    out = df[["trade_date", "settle", "mapping_ts_code", "margin_rate", "leverage", "iv"]].copy()
    out.to_csv(out_csv_dir / "gold_leverage_iv_10y.csv", index=False)

    # Plot with two y-axes.
    fig, ax1 = plt.subplots(figsize=(12, 5.2))
    lev = pd.to_numeric(out["leverage"], errors="coerce")
    iv = pd.to_numeric(out["iv"], errors="coerce")
    ax1.plot(out["trade_date"], lev, label="Futures leverage (1 / margin rate)", linewidth=1.2)
    ax1.set_ylabel("Leverage (x)")
    ax1.grid(True, alpha=0.25)

    ax2 = ax1.twinx()
    ax2.plot(out["trade_date"], iv * 100.0, label="Implied volatility (ATM-ish, %)", linewidth=1.0, color="orange")
    ax2.set_ylabel("Implied Vol (%)")

    ax1.set_title("Gold futures leverage vs implied volatility (last 10 years, AU.SHF)")

    # Combined legend
    lines, labels = ax1.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()
    ax1.legend(lines + lines2, labels + labels2, loc="upper left", fontsize=9)

    fig.tight_layout()
    fig.savefig(out_fig / "gold_leverage_iv_10y.png", dpi=180)
    plt.close(fig)

    print("Wrote:")
    print(" - figures/gold_leverage_iv_10y.png")
    print(" - data/tushare/gold_leverage_iv_10y.csv")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
