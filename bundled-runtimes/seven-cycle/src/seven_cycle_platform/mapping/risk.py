"""Risk metrics for retained current-mapping return paths."""

from __future__ import annotations

from dataclasses import dataclass
from numbers import Real

import numpy as np


def _finite_vector(values: object, *, name: str) -> np.ndarray:
    array = np.asarray(values, dtype="float64")
    if array.ndim != 1 or array.size == 0:
        raise ValueError(f"{name} must be a non-empty one-dimensional array")
    if not np.isfinite(array).all():
        raise ValueError(f"{name} must contain only finite values")
    return array


def _finite_nonnegative(value: object, *, name: str) -> float:
    if isinstance(value, (bool, np.bool_)) or not isinstance(
        value,
        (Real, np.integer, np.floating),
    ):
        raise TypeError(f"{name} must be a finite real number")
    numeric = float(value)
    if not np.isfinite(numeric):
        raise ValueError(f"{name} must be a finite real number")
    if numeric < 0.0:
        raise ValueError(f"{name} must be nonnegative")
    return numeric


def _finite_unit_interval(value: object, *, name: str) -> float:
    numeric = _finite_nonnegative(value, name=name)
    if numeric > 1.0:
        raise ValueError(f"{name} must be in [0, 1]")
    return numeric


@dataclass(frozen=True)
class RiskMetrics:
    """Coherent loss-tail and path-drawdown summary metrics."""

    volatility: float
    var95: float
    cvar95: float
    drawdown_q50: float
    drawdown_q80: float
    drawdown_q95: float

    def __post_init__(self) -> None:
        volatility = _finite_nonnegative(self.volatility, name="volatility")
        var95 = _finite_nonnegative(self.var95, name="var95")
        cvar95 = _finite_nonnegative(self.cvar95, name="cvar95")
        drawdown_q50 = _finite_unit_interval(
            self.drawdown_q50,
            name="drawdown_q50",
        )
        drawdown_q80 = _finite_unit_interval(
            self.drawdown_q80,
            name="drawdown_q80",
        )
        drawdown_q95 = _finite_unit_interval(
            self.drawdown_q95,
            name="drawdown_q95",
        )
        if cvar95 < var95:
            raise ValueError("cvar95 must be greater than or equal to var95")
        if not drawdown_q50 <= drawdown_q80 <= drawdown_q95:
            raise ValueError("drawdown quantiles must be ordered")
        object.__setattr__(self, "volatility", volatility)
        object.__setattr__(self, "var95", var95)
        object.__setattr__(self, "cvar95", cvar95)
        object.__setattr__(self, "drawdown_q50", drawdown_q50)
        object.__setattr__(self, "drawdown_q80", drawdown_q80)
        object.__setattr__(self, "drawdown_q95", drawdown_q95)


def compute_max_drawdown(monthly_returns: object) -> float | np.ndarray:
    """Return running peak-to-trough maximum drawdown for one or many paths."""

    returns = np.asarray(monthly_returns, dtype="float64")
    if returns.ndim not in {1, 2} or returns.shape[-1] == 0:
        raise ValueError("monthly_returns must be a non-empty 1D or 2D array")
    if not np.isfinite(returns).all():
        raise ValueError("monthly_returns must contain only finite values")
    if bool((returns <= -1.0).any()):
        raise ValueError("monthly returns must be greater than -1 (-100%)")

    path_matrix = returns[np.newaxis, :] if returns.ndim == 1 else returns
    log_wealth = np.cumsum(np.log1p(path_matrix), axis=1)
    log_wealth_with_origin = np.concatenate(
        [np.zeros((len(path_matrix), 1), dtype="float64"), log_wealth],
        axis=1,
    )
    running_log_peak = np.maximum.accumulate(log_wealth_with_origin, axis=1)
    log_peak_ratio = np.minimum(log_wealth_with_origin - running_log_peak, 0.0)
    drawdown = -np.expm1(log_peak_ratio)
    maxima = np.max(drawdown, axis=1)
    maxima = np.clip(maxima, 0.0, 1.0)
    if returns.ndim == 1:
        return float(maxima[0])
    return maxima


def summarize_risk(horizon_returns: object, max_drawdowns: object) -> RiskMetrics:
    """Summarize volatility, loss VaR/CVaR, and drawdown quantiles."""

    returns = _finite_vector(horizon_returns, name="horizon_returns")
    drawdowns = _finite_vector(max_drawdowns, name="max_drawdowns")
    if len(returns) != len(drawdowns):
        raise ValueError("horizon_returns and max_drawdowns must align")
    if bool(((drawdowns < 0.0) | (drawdowns > 1.0)).any()):
        raise ValueError("max_drawdowns must be in [0, 1]")

    losses = np.maximum(-returns, 0.0)
    var95 = float(np.quantile(losses, 0.95))
    tail = losses[losses >= var95 - 1e-15]
    cvar95 = float(np.mean(tail)) if tail.size else var95
    drawdown_q50, drawdown_q80, drawdown_q95 = np.quantile(
        drawdowns,
        [0.50, 0.80, 0.95],
    )
    return RiskMetrics(
        volatility=float(np.std(returns, ddof=0)),
        var95=var95,
        cvar95=max(cvar95, var95),
        drawdown_q50=float(drawdown_q50),
        drawdown_q80=float(drawdown_q80),
        drawdown_q95=float(drawdown_q95),
    )


__all__ = ["RiskMetrics", "compute_max_drawdown", "summarize_risk"]
