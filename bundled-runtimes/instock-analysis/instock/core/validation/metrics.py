#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Shared return and benchmark metrics for point-in-time validations."""

from __future__ import annotations

import math
from typing import Any, Mapping, Sequence

import numpy as np
import pandas as pd


def round_metric(value: float, digits: int = 4) -> float:
    return round(float(value), digits)


def _drawdown(returns: np.ndarray) -> float:
    if returns.size == 0:
        return 0.0
    # Include the capital invested before the first observed holding-period return.
    equity = pd.Series(np.concatenate(([1.0], np.cumprod(1 + returns))))
    return abs(float((equity / equity.cummax() - 1).min()))


def calculate_return_metrics(
    trades: Sequence[Mapping[str, Any]],
    *,
    period_sessions: int,
) -> dict[str, Any]:
    strategy = np.asarray([float(row["net_return"]) for row in trades], dtype=float)
    benchmark = np.asarray([float(row["benchmark_return"]) for row in trades], dtype=float)
    count = int(strategy.size)
    if count == 0:
        return {
            "trades": 0,
            "total_return_pct": None,
            "annualized_return_pct": None,
            "annualized_volatility_pct": None,
            "sharpe": None,
            "max_drawdown_pct": None,
            "win_rate_pct": None,
            "benchmark_return_pct": None,
            "excess_return_pct": None,
            "information_ratio": None,
            "beat_benchmark_rate_pct": None,
        }
    total = float(np.prod(1 + strategy) - 1)
    benchmark_total = float(np.prod(1 + benchmark) - 1)
    periods_per_year = 252 / max(int(period_sessions), 1)
    annualized = (1 + total) ** (periods_per_year / count) - 1 if total > -1 else -1.0
    volatility = float(strategy.std(ddof=0))
    annualized_volatility = volatility * math.sqrt(periods_per_year) if count >= 2 else None
    # Keep the existing population dispersion convention. A single observation
    # cannot estimate volatility; numerical zero is not a defined risk ratio.
    sharpe = float(strategy.mean() / volatility * math.sqrt(periods_per_year)) if count >= 2 and volatility > 1e-12 else None
    active = strategy - benchmark
    active_volatility = float(active.std(ddof=0))
    information_ratio = float(active.mean() / active_volatility * math.sqrt(periods_per_year)) if count >= 2 and active_volatility > 1e-12 else None
    return {
        "trades": count,
        "total_return_pct": round_metric(total * 100),
        "annualized_return_pct": round_metric(annualized * 100),
        "annualized_volatility_pct": round_metric(annualized_volatility * 100) if annualized_volatility is not None else None,
        "sharpe": round_metric(sharpe) if sharpe is not None else None,
        "max_drawdown_pct": round_metric(_drawdown(strategy) * 100),
        "win_rate_pct": round_metric(float((strategy > 0).mean()) * 100),
        "benchmark_return_pct": round_metric(benchmark_total * 100),
        "excess_return_pct": round_metric((total - benchmark_total) * 100),
        "information_ratio": round_metric(information_ratio) if information_ratio is not None else None,
        "beat_benchmark_rate_pct": round_metric(float((strategy > benchmark).mean()) * 100),
    }


def calculate_rotation_metrics(
    trades: Sequence[Mapping[str, Any]],
    *,
    period_sessions: int,
) -> dict[str, Any]:
    result = calculate_return_metrics(trades, period_sessions=period_sessions)
    if not trades:
        return {
            **result,
            "equal_weight_return_pct": None,
            "switches": 0,
            "turnover_rate_pct": None,
            "invested_rate_pct": None,
            "transaction_cost_total_pct": 0.0,
        }
    equal_weight = [row["equal_weight_return"] for row in trades]
    equal_weight_return = (
        round_metric((float(np.prod(1 + np.asarray(equal_weight, dtype=float))) - 1) * 100)
        if all(value is not None for value in equal_weight) else None
    )
    count = len(trades)
    switches = sum(bool(row.get("switched")) for row in trades)
    invested = sum(bool(row.get("invested", row.get("symbol") != "CASH")) for row in trades)
    return {
        **result,
        "equal_weight_return_pct": equal_weight_return,
        "switches": switches,
        "turnover_rate_pct": round_metric(switches / count * 100),
        "invested_rate_pct": round_metric(invested / count * 100),
        "transaction_cost_total_pct": round_metric(
            sum(float(row.get("transaction_cost") or 0) for row in trades) * 100
        ),
    }
