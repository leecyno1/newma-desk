from __future__ import annotations

import math
from dataclasses import dataclass


_PERIODS_PER_YEAR = 52
_EPSILON = 1e-12


@dataclass(frozen=True)
class PerformanceEstimate:
    observations: int
    returns: tuple[float, ...]
    equity_curve: tuple[float, ...]
    drawdowns: tuple[float, ...]
    total_return: float
    annualized_return: float
    annualized_volatility: float
    sharpe: float | None
    sortino: float | None
    calmar: float | None
    max_drawdown: float
    max_drawdown_duration: int
    win_rate: float
    profit_factor: float | None
    best_period: float
    worst_period: float
    value_at_risk_95: float
    conditional_value_at_risk_95: float


def analyze_performance(
    close_series: list[list[float] | tuple[float, ...]],
    weights: list[float] | tuple[float, ...],
    *,
    risk_free_rate: float = 0.0,
) -> PerformanceEstimate:
    if not close_series or len(close_series) != len(weights):
        raise ValueError("price series and weights must be non-empty and aligned")
    asset_returns = [_returns(series) for series in close_series]
    observations = min(len(items) for items in asset_returns)
    if observations < 8:
        raise ValueError("at least eight return observations are required")
    total_weight = sum(max(0.0, weight) for weight in weights)
    if total_weight <= _EPSILON:
        raise ValueError("portfolio weights must be positive")
    normalized = [max(0.0, weight) / total_weight for weight in weights]
    aligned = [items[-observations:] for items in asset_returns]
    returns = [
        sum(
            normalized[asset] * aligned[asset][period]
            for asset in range(len(aligned))
        )
        for period in range(observations)
    ]
    equity_curve: list[float] = []
    value = 1.0
    peak = 1.0
    drawdowns: list[float] = []
    max_duration = 0
    duration = 0
    for period_return in returns:
        value *= 1 + period_return
        equity_curve.append(value)
        peak = max(peak, value)
        drawdown = value / peak - 1 if peak > _EPSILON else 0.0
        drawdowns.append(drawdown)
        if drawdown < 0:
            duration += 1
            max_duration = max(max_duration, duration)
        else:
            duration = 0
    total_return = value - 1
    annualized_return = (
        value ** (_PERIODS_PER_YEAR / observations) - 1
        if value > 0
        else -1.0
    )
    mean = sum(returns) / observations
    variance = sum((item - mean) ** 2 for item in returns) / max(1, observations - 1)
    weekly_volatility = math.sqrt(max(0.0, variance))
    annualized_volatility = weekly_volatility * math.sqrt(_PERIODS_PER_YEAR)
    weekly_risk_free = (1 + risk_free_rate) ** (1 / _PERIODS_PER_YEAR) - 1
    sharpe = (
        (mean - weekly_risk_free) / weekly_volatility * math.sqrt(_PERIODS_PER_YEAR)
        if weekly_volatility > _EPSILON
        else None
    )
    downside = math.sqrt(
        sum(min(0.0, item - weekly_risk_free) ** 2 for item in returns)
        / observations
    ) * math.sqrt(_PERIODS_PER_YEAR)
    sortino = (
        (mean - weekly_risk_free) * _PERIODS_PER_YEAR / downside
        if downside > _EPSILON
        else None
    )
    max_drawdown = min(drawdowns, default=0.0)
    calmar = (
        annualized_return / abs(max_drawdown)
        if abs(max_drawdown) > _EPSILON
        else None
    )
    wins = [item for item in returns if item > 0]
    losses = [item for item in returns if item < 0]
    profit_factor = (
        sum(wins) / abs(sum(losses))
        if losses and abs(sum(losses)) > _EPSILON
        else None
    )
    ordered = sorted(returns)
    var_index = max(0, math.ceil(observations * 0.05) - 1)
    value_at_risk = ordered[var_index]
    tail = [item for item in returns if item <= value_at_risk]
    conditional_value_at_risk = sum(tail) / len(tail)
    return PerformanceEstimate(
        observations=observations,
        returns=tuple(returns),
        equity_curve=tuple(equity_curve),
        drawdowns=tuple(drawdowns),
        total_return=total_return,
        annualized_return=annualized_return,
        annualized_volatility=annualized_volatility,
        sharpe=sharpe,
        sortino=sortino,
        calmar=calmar,
        max_drawdown=max_drawdown,
        max_drawdown_duration=max_duration,
        win_rate=len(wins) / observations,
        profit_factor=profit_factor,
        best_period=max(returns),
        worst_period=min(returns),
        value_at_risk_95=value_at_risk,
        conditional_value_at_risk_95=conditional_value_at_risk,
    )


def _returns(closes: list[float] | tuple[float, ...]) -> list[float]:
    clean = [float(value) for value in closes if value > 0 and math.isfinite(value)]
    return [
        max(-0.8, min(3.0, clean[index] / clean[index - 1] - 1))
        for index in range(1, len(clean))
        if clean[index - 1] > _EPSILON
    ]
