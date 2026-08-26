"""Shared backtest metrics, extracted from daily_portfolio.py for reuse.

Provides annualisation helpers, trade statistics, and full metric calculation.
"""

from __future__ import annotations

import logging
import math
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

from backtest.models import TradeRecord

# ─── Annualisation factor mapping ───

# mootdx (A-share) and futu (HK + A-share) are equity sources, so they mirror
# the tushare/akshare column: 252 trading days and a 240-minute session. HK
# sessions are marginally longer (~330 min) — an approximation in line with the
# rest of this annualisation table; the key fix is that intraday mootdx/futu no
# longer fall back to the bars_per_day=1 default, which mis-annualised vol/Sharpe.
_A_SHARE_SOURCES = {
    "tushare", "akshare", "baostock", "tencent", "mootdx", "futu",
    "eastmoney", "sina",
}
_US_EQUITY_SOURCES = {
    "yfinance", "yahoo", "finnhub", "alphavantage", "tiingo", "fmp",
    "stooq", "qveris", "local",
}
_CRYPTO_SOURCES = {"okx", "ccxt"}
_INDIA_SOURCES = {"india_broker"}

_TRADING_DAYS = {
    **dict.fromkeys(_A_SHARE_SOURCES | _US_EQUITY_SOURCES | _INDIA_SOURCES, 252),
    **dict.fromkeys(_CRYPTO_SOURCES, 365),
}
_SESSION_MINUTES = {
    **dict.fromkeys(_A_SHARE_SOURCES, 240),
    **dict.fromkeys(_US_EQUITY_SOURCES, 390),
    **dict.fromkeys(_CRYPTO_SOURCES, 1440),
    **dict.fromkeys(_INDIA_SOURCES, 375),
}
_INTERVAL_MINUTES = {"1m": 1, "5m": 5, "15m": 15, "30m": 30, "1H": 60, "4H": 240}
_BARS_PER_DAY = {
    interval: {
        source: math.ceil(session_minutes / interval_minutes)
        for source, session_minutes in _SESSION_MINUTES.items()
    }
    for interval, interval_minutes in _INTERVAL_MINUTES.items()
}
_BARS_PER_DAY["1D"] = dict.fromkeys(_SESSION_MINUTES, 1)


def _normalize_interval(interval: str) -> str:
    token = str(interval or "1D").strip().lower()
    return token.upper() if token in {"1h", "4h", "1d"} else token


def calc_bars_per_year(interval: str = "1D", source: str = "tushare") -> int:
    """Number of bars per year for annualisation.

    Args:
        interval: Bar size (1m / 5m / 15m / 30m / 1H / 4H / 1D).
        source: Registered market-data source name, case-insensitive.

    Returns:
        Bars per year.
    """
    source_key = str(source or "").strip().lower()
    interval_key = _normalize_interval(interval)
    trading_days = _TRADING_DAYS.get(source_key, 252)
    bars_per_day = _BARS_PER_DAY.get(interval_key, {}).get(source_key, 1)
    return trading_days * bars_per_day


_log = logging.getLogger(__name__)


def bar_returns(close: Any, *, label: str = "") -> Any:
    """Return held-position returns without infinities or erased gap moves."""
    previous = close.ffill().shift(1)
    usable = np.isfinite(previous) & (previous > 0)
    undefined = int((previous.notna() & ~usable).to_numpy().sum())
    if undefined:
        _log.warning(
            "%s: %d return(s) follow a non-positive or non-finite price; using 0.0",
            label or "returns",
            undefined,
        )
    returns = close / previous.where(usable) - 1
    return returns.replace([np.inf, -np.inf], np.nan).fillna(0.0)


def buy_and_hold_return(close: Any) -> Optional[float]:
    """Return the entry-to-exit price relative when mathematically valid."""
    if len(close) < 2:
        return None
    first = float(close.iloc[0])
    last = float(close.iloc[-1])
    if not (np.isfinite(first) and first > 0 and np.isfinite(last)):
        return None
    return last / first - 1.0


def win_rate_and_stats(trades: List[TradeRecord]) -> Dict[str, float]:
    """Win rate and P&L statistics from completed trades.

    Args:
        trades: Completed round-trip trades.

    Returns:
        Dict with win_rate, profit_loss_ratio, max_consecutive_loss,
        avg_holding_bars, profit_factor.
    """
    if not trades:
        return {
            "win_rate": 0.0,
            "profit_loss_ratio": 0.0,
            "max_consecutive_loss": 0,
            "avg_holding_bars": 0.0,
            "profit_factor": 0.0,
        }

    wins = [t.pnl for t in trades if t.pnl > 0]
    losses = [t.pnl for t in trades if t.pnl < 0]

    win_rate = len(wins) / len(trades)

    avg_win = float(np.mean(wins)) if wins else 0.0
    avg_loss = abs(float(np.mean(losses))) if losses else 1e-10
    profit_loss_ratio = avg_win / avg_loss if avg_loss > 1e-10 else 0.0

    gross_profit = sum(wins) if wins else 0.0
    gross_loss = abs(sum(losses)) if losses else 1e-10
    profit_factor = gross_profit / gross_loss if gross_loss > 1e-10 else 0.0

    max_consec = 0
    cur_consec = 0
    for t in trades:
        if t.pnl < 0:
            cur_consec += 1
            max_consec = max(max_consec, cur_consec)
        else:
            cur_consec = 0

    hold_bars = [t.holding_bars for t in trades if t.holding_bars > 0]
    avg_holding = float(np.mean(hold_bars)) if hold_bars else 0.0

    return {
        "win_rate": win_rate,
        "profit_loss_ratio": round(profit_loss_ratio, 4),
        "max_consecutive_loss": max_consec,
        "avg_holding_bars": round(avg_holding, 1),
        "profit_factor": round(profit_factor, 4),
    }


def by_symbol_stats(trades: List[TradeRecord]) -> Dict[str, Dict[str, Any]]:
    """Per-symbol trade statistics.

    Args:
        trades: Completed round-trip trades.

    Returns:
        {symbol: {count, win_rate, total_pnl, avg_pnl}}.
    """
    groups: Dict[str, list] = {}
    for t in trades:
        groups.setdefault(t.symbol, []).append(t)

    result = {}
    for sym, sym_trades in groups.items():
        pnls = [t.pnl for t in sym_trades]
        wins = [p for p in pnls if p > 0]
        result[sym] = {
            "count": len(sym_trades),
            "win_rate": round(len(wins) / len(sym_trades), 4) if sym_trades else 0.0,
            "total_pnl": round(sum(pnls), 2),
            "avg_pnl": round(float(np.mean(pnls)), 2) if pnls else 0.0,
        }
    return result


def by_exit_reason_stats(trades: List[TradeRecord]) -> Dict[str, Dict[str, Any]]:
    """Per-exit-reason trade statistics.

    Args:
        trades: Completed round-trip trades.

    Returns:
        {reason: {count, total_pnl}}.
    """
    groups: Dict[str, list] = {}
    for t in trades:
        groups.setdefault(t.exit_reason, []).append(t)

    result = {}
    for reason, reason_trades in groups.items():
        pnls = [t.pnl for t in reason_trades]
        result[reason] = {
            "count": len(reason_trades),
            "total_pnl": round(sum(pnls), 2),
        }
    return result


def calc_execution_turnover(
    executed_margin: pd.Series,
    equity_curve: pd.Series,
) -> pd.Series:
    """Normalize actual filled margin by portfolio equity per bar."""
    if equity_curve.empty:
        return pd.Series(dtype=float)
    traded = executed_margin.reindex(equity_curve.index).fillna(0.0).clip(lower=0.0)
    denominator = 2.0 * equity_curve.abs().replace(0.0, np.nan)
    return (traded / denominator).replace([np.inf, -np.inf], np.nan).fillna(0.0)


def calc_metrics(
    equity_curve: pd.Series,
    trades: List[TradeRecord],
    initial_cash: float,
    bars_per_year: Optional[int] = 252,
    bench_ret: Optional[pd.Series] = None,
    turnover_series: Optional[pd.Series] = None,
) -> Dict[str, Any]:
    """Full set of performance metrics.

    Args:
        equity_curve: Equity time series (index=timestamp, values=equity).
        trades: Completed round-trip trades.
        initial_cash: Starting capital.
        bars_per_year: Bars per year for annualisation. None = auto-detect
            from equity curve dates (calendar-day method, for cross-market).
        bench_ret: Benchmark per-bar return series (optional).
        turnover_series: Actual filled turnover aligned to the equity curve.

    Returns:
        Metrics dictionary (compatible with daily_portfolio format).
    """
    if len(equity_curve) == 0:
        return _empty_metrics(initial_cash)

    n = len(equity_curve)

    # Calendar-day annualization for cross-market (bars_per_year=None)
    if bars_per_year is None:
        first, last = equity_curve.index[0], equity_curve.index[-1]
        calendar_days = (last - first).days
        years = calendar_days / 365.25 if calendar_days > 0 else 1.0
        bpy = int(n / years) if years > 0 else 252
    else:
        bpy = bars_per_year

    port_ret = bar_returns(equity_curve, label="portfolio equity")

    total_ret = float(equity_curve.iloc[-1] / initial_cash - 1)
    ann_ret = float((1 + total_ret) ** (bpy / max(n, 1)) - 1)
    vol = float(port_ret.std())
    sharpe = float(port_ret.mean() / (vol + 1e-10) * np.sqrt(bpy))

    # Drawdown
    peak = equity_curve.cummax()
    dd = (equity_curve - peak) / peak.replace(0, 1)
    max_dd = float(dd.min())

    calmar = ann_ret / abs(max_dd) if abs(max_dd) > 1e-10 else 0.0

    # Sortino
    downside = port_ret[port_ret < 0]
    downside_std = float(downside.std()) if len(downside) > 1 else 1e-10
    sortino = float(port_ret.mean() / (downside_std + 1e-10) * np.sqrt(bpy))

    trade_stats = win_rate_and_stats(trades)
    turnover = (
        turnover_series.reindex(equity_curve.index).fillna(0.0).clip(lower=0.0)
        if turnover_series is not None
        else pd.Series(dtype=float)
    )
    avg_turnover = float(turnover.mean()) if not turnover.empty else 0.0
    total_turnover = float(turnover.sum()) if not turnover.empty else 0.0

    # Benchmark comparison
    bench_return = 0.0
    excess = 0.0
    ir = 0.0
    if bench_ret is not None and len(bench_ret) > 0:
        bench_return = float((1 + bench_ret).prod() - 1)
        excess = total_ret - bench_return
        active_ret = port_ret - bench_ret.reindex(port_ret.index).fillna(0.0)
        active_std = float(active_ret.std())
        ir = float(active_ret.mean() / (active_std + 1e-10) * np.sqrt(bpy))

    return {
        "final_value": float(equity_curve.iloc[-1]),
        "total_return": total_ret,
        "annual_return": ann_ret,
        "max_drawdown": max_dd,
        "sharpe": sharpe,
        "calmar": round(calmar, 4),
        "sortino": round(sortino, 4),
        "win_rate": trade_stats["win_rate"],
        "profit_loss_ratio": trade_stats["profit_loss_ratio"],
        "profit_factor": trade_stats["profit_factor"],
        "max_consecutive_loss": trade_stats["max_consecutive_loss"],
        "avg_holding_days": trade_stats["avg_holding_bars"],
        "trade_count": len(trades),
        "avg_turnover": avg_turnover,
        "total_turnover": total_turnover,
        "benchmark_return": round(bench_return, 6),
        "excess_return": round(excess, 6),
        "information_ratio": round(ir, 4),
    }


def _empty_metrics(initial_cash: float) -> Dict[str, Any]:
    """Return zero-valued metrics when no data is available."""
    return {
        "final_value": initial_cash,
        "total_return": 0, "annual_return": 0, "max_drawdown": 0,
        "sharpe": 0, "calmar": 0, "sortino": 0,
        "win_rate": 0, "profit_loss_ratio": 0, "profit_factor": 0,
        "max_consecutive_loss": 0, "avg_holding_days": 0, "trade_count": 0,
        "avg_turnover": 0, "total_turnover": 0,
        "benchmark_return": 0, "excess_return": 0, "information_ratio": 0,
    }
