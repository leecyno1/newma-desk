from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal


Objective = Literal["minimum-volatility", "risk-balanced", "return-seeking"]
_EPSILON = 1e-12
_PERIODS_PER_YEAR = 52


@dataclass(frozen=True)
class OptimizationEstimate:
    weights: tuple[float, ...]
    annual_returns: tuple[float, ...]
    annual_volatilities: tuple[float, ...]
    risk_contributions: tuple[float, ...]
    portfolio_return: float
    portfolio_volatility: float
    observations: int
    method: str
    warnings: tuple[str, ...] = ()


def optimize_weights(
    close_series: list[list[float] | tuple[float, ...]],
    *,
    objective: Objective,
    total_weight: float = 1.0,
    max_weight: float = 1.0,
    risk_free_rate: float = 0.0,
    cash_weight: float = 0.0,
) -> OptimizationEstimate:
    if not close_series:
        raise ValueError("at least one price series is required")
    returns = [_returns(series) for series in close_series]
    observations = min(len(items) for items in returns)
    if observations < 8:
        raise ValueError("at least eight return observations are required")
    aligned = [items[-observations:] for items in returns]
    means = [sum(items) / observations for items in aligned]
    covariance = _covariance(aligned, means)
    annual_returns = tuple(value * _PERIODS_PER_YEAR for value in means)
    annual_volatilities = tuple(
        math.sqrt(max(0.0, covariance[index][index] * _PERIODS_PER_YEAR))
        for index in range(len(aligned))
    )
    warnings: list[str] = []
    if objective == "minimum-volatility":
        scores = _minimum_variance_scores(covariance)
        method = "lightweight-minimum-variance"
    elif objective == "return-seeking":
        scores = [
            max(0.0, annual_return - risk_free_rate)
            / max(volatility, 0.01)
            for annual_return, volatility in zip(
                annual_returns, annual_volatilities, strict=True
            )
        ]
        method = "lightweight-risk-adjusted-return"
        if sum(scores) <= _EPSILON:
            scores = _inverse_volatility_scores(annual_volatilities)
            warnings.append("历史超额收益均不为正，已回退到风险均衡权重。")
    else:
        scores = _inverse_volatility_scores(annual_volatilities)
        method = "lightweight-inverse-volatility"
    weights, cap_relaxed = _capped_weights(
        scores,
        total=max(0.0, total_weight),
        cap=max(0.0, max_weight),
    )
    if cap_relaxed:
        warnings.append("资产数量不足以满足单一资产上限，已使用最小可行上限。")
    portfolio_return = sum(
        weight * expected
        for weight, expected in zip(weights, annual_returns, strict=True)
    ) + cash_weight * risk_free_rate
    portfolio_variance = _portfolio_variance(weights, covariance) * _PERIODS_PER_YEAR
    portfolio_volatility = math.sqrt(max(0.0, portfolio_variance))
    risk_contributions = _risk_contributions(weights, covariance)
    return OptimizationEstimate(
        weights=tuple(weights),
        annual_returns=annual_returns,
        annual_volatilities=annual_volatilities,
        risk_contributions=tuple(risk_contributions),
        portfolio_return=portfolio_return,
        portfolio_volatility=portfolio_volatility,
        observations=observations,
        method=method,
        warnings=tuple(warnings),
    )


def _returns(closes: list[float] | tuple[float, ...]) -> list[float]:
    clean = [float(value) for value in closes if value > 0 and math.isfinite(value)]
    return [
        max(-0.8, min(3.0, clean[index] / clean[index - 1] - 1))
        for index in range(1, len(clean))
        if clean[index - 1] > _EPSILON
    ]


def _covariance(rows: list[list[float]], means: list[float]) -> list[list[float]]:
    count = len(rows)
    observations = len(rows[0])
    denominator = max(1, observations - 1)
    return [
        [
            sum(
                (rows[left][index] - means[left])
                * (rows[right][index] - means[right])
                for index in range(observations)
            )
            / denominator
            for right in range(count)
        ]
        for left in range(count)
    ]


def _inverse_volatility_scores(volatilities: tuple[float, ...]) -> list[float]:
    return [1 / max(value, 0.005) for value in volatilities]


def _minimum_variance_scores(covariance: list[list[float]]) -> list[float]:
    size = len(covariance)
    if size == 1:
        return [1.0]
    scale = max(max(row[index] for index, row in enumerate(covariance)), _EPSILON)
    regularized = [
        [
            value + (scale * 1e-5 if row == column else 0.0)
            for column, value in enumerate(values)
        ]
        for row, values in enumerate(covariance)
    ]
    try:
        solution = _solve(regularized, [1.0] * size)
    except ValueError:
        return [1 / math.sqrt(max(covariance[index][index], _EPSILON)) for index in range(size)]
    positive = [max(0.0, value) for value in solution]
    if sum(positive) <= _EPSILON:
        return [1 / math.sqrt(max(covariance[index][index], _EPSILON)) for index in range(size)]
    return positive


def _solve(matrix: list[list[float]], target: list[float]) -> list[float]:
    size = len(target)
    augmented = [list(matrix[row]) + [target[row]] for row in range(size)]
    for column in range(size):
        pivot = max(range(column, size), key=lambda row: abs(augmented[row][column]))
        if abs(augmented[pivot][column]) <= _EPSILON:
            raise ValueError("singular covariance matrix")
        augmented[column], augmented[pivot] = augmented[pivot], augmented[column]
        divisor = augmented[column][column]
        augmented[column] = [value / divisor for value in augmented[column]]
        for row in range(size):
            if row == column:
                continue
            factor = augmented[row][column]
            augmented[row] = [
                value - factor * pivot_value
                for value, pivot_value in zip(
                    augmented[row], augmented[column], strict=True
                )
            ]
    return [augmented[row][-1] for row in range(size)]


def _capped_weights(
    scores: list[float],
    *,
    total: float,
    cap: float,
) -> tuple[list[float], bool]:
    if total <= _EPSILON:
        return [0.0] * len(scores), False
    size = len(scores)
    effective_cap = max(cap, total / size)
    relaxed = effective_cap > cap + _EPSILON
    positive = [max(0.0, value) if math.isfinite(value) else 0.0 for value in scores]
    active = set(range(size))
    weights = [0.0] * size
    remaining = total
    while active:
        score_total = sum(positive[index] for index in active)
        if score_total <= _EPSILON:
            proposed = {index: remaining / len(active) for index in active}
        else:
            proposed = {
                index: remaining * positive[index] / score_total
                for index in active
            }
        over = [index for index, value in proposed.items() if value > effective_cap]
        if not over:
            for index, value in proposed.items():
                weights[index] = value
            break
        for index in over:
            weights[index] = effective_cap
            remaining -= effective_cap
            active.remove(index)
    return weights, relaxed


def _portfolio_variance(weights: list[float], covariance: list[list[float]]) -> float:
    return sum(
        weights[left] * covariance[left][right] * weights[right]
        for left in range(len(weights))
        for right in range(len(weights))
    )


def _risk_contributions(
    weights: list[float], covariance: list[list[float]]
) -> list[float]:
    marginal = [
        sum(covariance[row][column] * weights[column] for column in range(len(weights)))
        for row in range(len(weights))
    ]
    total = sum(weight * value for weight, value in zip(weights, marginal, strict=True))
    if abs(total) <= _EPSILON:
        return [0.0] * len(weights)
    return [weight * value / total for weight, value in zip(weights, marginal, strict=True)]
