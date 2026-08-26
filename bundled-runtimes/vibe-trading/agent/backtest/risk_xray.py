"""Compact portfolio risk diagnostics computed from trailing close prices."""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np
import pandas as pd

from backtest.validation import _json_safe


MIN_HISTORY_DAYS = 30
PERIODS_PER_YEAR = 252
VAR_LEVELS = (0.95, 0.99)


def _finite(value: Any) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def _validate_weights(
    closes: pd.DataFrame,
    weights: Mapping[str, float],
) -> tuple[dict[str, float], list[str]]:
    if not weights:
        raise ValueError("weights must name at least one symbol")
    unknown = sorted(str(symbol) for symbol in weights if symbol not in closes.columns)
    if unknown:
        raise ValueError(f"weights reference symbols with no price data: {unknown}")

    cleaned: dict[str, float] = {}
    for symbol, raw in weights.items():
        value = _finite(raw)
        if value is None:
            raise ValueError(f"weight for {symbol!r} is not finite: {raw!r}")
        if value < 0:
            raise ValueError(
                f"weight for {symbol!r} is negative ({value}); risk x-ray is long-only"
            )
        cleaned[str(symbol)] = value

    total = sum(cleaned.values())
    if total <= 0:
        raise ValueError("weights must sum to a positive value")
    warnings: list[str] = []
    if abs(total - 1.0) > 1e-6:
        cleaned = {symbol: value / total for symbol, value in cleaned.items()}
        warnings.append(f"weights summed to {total:.6f}; renormalized to 1.0")
    return cleaned, warnings


def compute_risk_xray(
    closes: pd.DataFrame,
    weights: Mapping[str, float],
    *,
    periods_per_year: int = PERIODS_PER_YEAR,
    var_levels: Sequence[float] = VAR_LEVELS,
    min_history: int = MIN_HISTORY_DAYS,
) -> dict[str, Any]:
    """Compute concentration, tail, drawdown and co-movement diagnostics."""
    if closes is None or closes.empty:
        raise ValueError("price panel is empty")
    if isinstance(periods_per_year, bool) or periods_per_year <= 0:
        raise ValueError("periods_per_year must be a positive integer")
    if isinstance(min_history, bool) or min_history < 2:
        raise ValueError("min_history must be at least 2")
    levels = tuple(float(level) for level in var_levels)
    if not levels or any(not math.isfinite(level) or not 0 < level < 1 for level in levels):
        raise ValueError("var_levels must contain probabilities in (0, 1)")

    frame = closes.replace([np.inf, -np.inf], np.nan).dropna(axis=1, how="all")
    if frame.empty:
        raise ValueError("price panel has no finite closes")
    cleaned_weights, warnings = _validate_weights(frame, weights)

    kept: list[str] = []
    skipped: list[dict[str, str]] = []
    for symbol in cleaned_weights:
        valid = int(frame[symbol].count())
        if valid < min_history:
            skipped.append(
                {"symbol": symbol, "reason": f"only {valid} valid bars (min {min_history})"}
            )
        else:
            kept.append(symbol)
    if not kept:
        raise ValueError(f"no symbol has at least {min_history} valid bars")
    if skipped:
        surviving_total = sum(cleaned_weights[symbol] for symbol in kept)
        if surviving_total <= 0:
            raise ValueError("surviving symbols have zero total weight")
        cleaned_weights = {
            symbol: cleaned_weights[symbol] / surviving_total for symbol in kept
        }
        warnings.append("weights renormalized over symbols that survived the history filter")

    aligned = frame[kept].dropna(axis=0, how="any")
    if len(aligned) < 2:
        raise ValueError("fewer than 2 shared trading days after calendar alignment")
    returns = aligned.pct_change(fill_method=None).replace([np.inf, -np.inf], np.nan)
    returns = returns.dropna(axis=0, how="any")
    if returns.empty:
        raise ValueError("no overlapping finite return observations")

    weight_array = np.array([cleaned_weights[symbol] for symbol in kept], dtype=float)
    portfolio = pd.Series(
        returns.to_numpy(dtype=float) @ weight_array,
        index=returns.index,
    )
    report = {
        "inputs": {
            "symbols": kept,
            "weights": {
                symbol: round(float(cleaned_weights[symbol]), 8) for symbol in kept
            },
            "aligned_days": int(len(aligned)),
            "return_observations": int(len(returns)),
            "first_date": str(aligned.index[0]),
            "last_date": str(aligned.index[-1]),
        },
        "concentration": _concentration(weight_array),
        "volatility": _volatility(portfolio, periods_per_year),
        "drawdown": _drawdown(portfolio),
        "tail_risk": _tail_risk(portfolio, levels),
        "diversification": _diversification(returns, weight_array, portfolio),
        "correlation": _correlation(returns, portfolio),
        "skipped": skipped,
        "warnings": warnings,
    }
    return _json_safe(report)


def _concentration(weights: np.ndarray) -> dict[str, float | None]:
    hhi = float(np.sum(weights**2))
    ordered = np.argsort(weights)[::-1]
    return {
        "hhi": _finite(hhi),
        "effective_n": _finite(1.0 / hhi) if hhi > 0 else None,
        "top1_weight": _finite(weights[ordered[0]]) if len(ordered) else None,
        "top3_weight": _finite(weights[ordered[:3]].sum()) if len(ordered) else None,
    }


def _volatility(portfolio: pd.Series, periods_per_year: int) -> dict[str, float | None]:
    volatility = float(portfolio.std(ddof=1)) if len(portfolio) > 1 else None
    downside = portfolio[portfolio < 0]
    downside_deviation = float(downside.std(ddof=1)) if len(downside) > 1 else None
    annualizer = math.sqrt(periods_per_year)
    return {
        "period_vol": _finite(volatility),
        "annualized_vol": _finite(volatility * annualizer) if volatility is not None else None,
        "downside_deviation_annualized": (
            _finite(downside_deviation * annualizer)
            if downside_deviation is not None
            else None
        ),
    }


def _drawdown(portfolio: pd.Series) -> dict[str, Any]:
    equity = (1.0 + portfolio).cumprod()
    drawdown = equity / equity.cummax() - 1.0
    trough = drawdown.idxmin()
    peak = equity.loc[:trough].idxmax()
    return {
        "max_drawdown": _finite(drawdown.loc[trough]),
        "max_drawdown_start": str(peak),
        "max_drawdown_trough": str(trough),
    }


def _tail_risk(portfolio: pd.Series, levels: Sequence[float]) -> dict[str, Any]:
    losses = -portfolio.to_numpy(dtype=float)
    result: dict[str, Any] = {"method": "historical simulation (non-parametric)"}
    for level in levels:
        value_at_risk = float(np.quantile(losses, level))
        tail = losses[losses >= value_at_risk]
        suffix = str(int(round(level * 100)))
        result[f"var_{suffix}"] = _finite(value_at_risk)
        result[f"expected_shortfall_{suffix}"] = _finite(tail.mean()) if len(tail) else None
    return result


def _diversification(
    returns: pd.DataFrame,
    weights: np.ndarray,
    portfolio: pd.Series,
) -> dict[str, Any]:
    if returns.shape[1] < 2:
        return {"diversification_ratio": None, "note": "needs at least 2 assets"}
    portfolio_volatility = float(portfolio.std(ddof=1))
    if not math.isfinite(portfolio_volatility) or portfolio_volatility <= 0:
        return {"diversification_ratio": None, "note": "portfolio variance is zero"}
    asset_volatilities = returns.std(ddof=1).to_numpy(dtype=float)
    return {
        "diversification_ratio": _finite(
            float(np.dot(weights, asset_volatilities) / portfolio_volatility)
        )
    }


def _correlation(returns: pd.DataFrame, portfolio: pd.Series) -> dict[str, Any]:
    if returns.shape[1] < 2:
        return {
            "avg_pairwise_abs": None,
            "max_pair": None,
            "beta_to_equal_weight": None,
            "note": "needs at least 2 assets",
        }
    matrix = returns.corr().to_numpy(dtype=float)
    pairs = [
        (row, column)
        for row in range(matrix.shape[0])
        for column in range(row + 1, matrix.shape[1])
        if math.isfinite(float(matrix[row, column]))
    ]
    maximum = max(pairs, key=lambda pair: abs(matrix[pair])) if pairs else None
    market = returns.mean(axis=1)
    market_variance = float(market.var(ddof=1))
    beta = (
        float(portfolio.cov(market) / market_variance)
        if math.isfinite(market_variance) and market_variance > 0
        else None
    )
    return {
        "avg_pairwise_abs": (
            _finite(np.mean([abs(matrix[pair]) for pair in pairs])) if pairs else None
        ),
        "max_pair": (
            {
                "symbols": [
                    str(returns.columns[maximum[0]]),
                    str(returns.columns[maximum[1]]),
                ],
                "corr": _finite(matrix[maximum]),
            }
            if maximum is not None
            else None
        ),
        "beta_to_equal_weight": _finite(beta),
    }


def average_invested_weights(target_pos: pd.DataFrame) -> tuple[dict[str, float], float]:
    """Derive a representative long-only basket from average target exposure."""
    if target_pos is None or target_pos.empty:
        raise ValueError("target position frame is empty")
    means = target_pos.replace([np.inf, -np.inf], np.nan).mean(axis=0)
    short_symbols = [str(symbol) for symbol, weight in means.items() if float(weight) < 0]
    if short_symbols:
        raise ValueError(
            "long-only risk x-ray cannot describe net short average exposure in "
            + ", ".join(short_symbols)
        )
    weights = {
        str(symbol): float(weight)
        for symbol, weight in means.items()
        if math.isfinite(float(weight)) and float(weight) > 0
    }
    if not weights:
        raise ValueError("strategy held no average exposure")
    avg_invested = float(target_pos.fillna(0.0).sum(axis=1).mean())
    return weights, avg_invested


def write_risk_xray(path: Path, report: Mapping[str, Any]) -> dict[str, Any]:
    """Write strict JSON and return the sanitized payload."""
    payload = _json_safe(dict(report))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False)
        + "\n",
        encoding="utf-8",
    )
    return payload
