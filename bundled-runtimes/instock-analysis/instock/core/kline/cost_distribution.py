#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Volume-weighted price distribution built from Desk OHLCV bars.

This is deliberately a transaction-cost proxy.  It does not claim to model
the remaining shareholder chips because Desk OHLCV currently has no daily
turnover-rate series or point-in-time free-float shares.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd


def build_volume_cost_distribution(
    frame: pd.DataFrame,
    *,
    max_bars: int = 240,
    bins: int = 48,
) -> dict[str, Any]:
    """Return a compact volume-weighted price profile for one OHLCV window."""

    required = {"high", "low", "close", "volume"}
    if frame is None or frame.empty or not required.issubset(frame.columns):
        return _unavailable("K 线缺少 high、low、close 或 volume 字段")

    data = frame.tail(max(1, int(max_bars))).copy()
    for column in required:
        data[column] = pd.to_numeric(data[column], errors="coerce")
    data = data.replace([np.inf, -np.inf], np.nan).dropna(subset=list(required))
    data = data[(data["high"] > 0) & (data["low"] > 0) & (data["close"] > 0) & (data["volume"] > 0)]
    if data.empty:
        return _unavailable("K 线没有可用于成本分布的有效量价记录")

    typical = (data["high"] + data["low"] + data["close"]) / 3.0
    weights = data["volume"].astype(float)
    total_volume = float(weights.sum())
    if total_volume <= 0:
        return _unavailable("K 线成交量合计为零")

    current_price = float(data.iloc[-1]["close"])
    average_cost = float(np.average(typical, weights=weights))
    median_cost = _weighted_quantile(typical, weights, 0.50)
    interval_70 = _interval(typical, weights, 0.15, 0.85)
    interval_90 = _interval(typical, weights, 0.05, 0.95)
    profit_volume_pct = float(weights[typical <= current_price].sum() / total_volume * 100)

    low = float(min(data["low"].min(), typical.min()))
    high = float(max(data["high"].max(), typical.max()))
    bin_count = max(16, min(int(bins), 80))
    if abs(high - low) < 1e-12:
        profile = [{"price": round(current_price, 4), "volume_share_pct": 100.0}]
        dominant_cost = current_price
    else:
        histogram, edges = np.histogram(
            typical.to_numpy(dtype=float),
            bins=bin_count,
            range=(low, high),
            weights=weights.to_numpy(dtype=float),
        )
        centers = (edges[:-1] + edges[1:]) / 2
        shares = histogram / total_volume * 100
        profile = [
            {
                "price": round(float(price), 4),
                "volume_share_pct": round(float(share), 4),
            }
            for price, share in zip(centers, shares)
            if share > 0
        ]
        dominant_cost = float(centers[int(np.argmax(histogram))])

    return {
        "state": "available",
        "model": "instock-volume-price-cost-proxy-v1",
        "label": "成交成本分布代理",
        "basis": "typical_price_weighted_by_volume",
        "window_bars": int(len(data)),
        "current_price": round(current_price, 4),
        "average_cost": round(average_cost, 4),
        "median_cost": round(median_cost, 4),
        "dominant_cost": round(dominant_cost, 4),
        "profit_volume_pct": round(profit_volume_pct, 2),
        "current_vs_average_pct": round(
            (current_price / average_cost - 1) * 100 if average_cost else 0.0,
            2,
        ),
        "intervals": {
            "70": interval_70,
            "90": interval_90,
        },
        "profile": profile,
        "limitations": [
            "volume_price_proxy_not_shareholder_chip_distribution",
            "no_turnover_decay_without_daily_turnover_rate",
            "adjusted_prices_are_relative_not_literal_historical_costs",
        ],
    }


def _weighted_quantile(values: pd.Series, weights: pd.Series, quantile: float) -> float:
    order = np.argsort(values.to_numpy(dtype=float))
    sorted_values = values.to_numpy(dtype=float)[order]
    sorted_weights = weights.to_numpy(dtype=float)[order]
    cumulative = np.cumsum(sorted_weights)
    threshold = float(sorted_weights.sum()) * quantile
    index = min(int(np.searchsorted(cumulative, threshold, side="left")), len(sorted_values) - 1)
    return float(sorted_values[index])


def _interval(
    values: pd.Series,
    weights: pd.Series,
    lower_quantile: float,
    upper_quantile: float,
) -> dict[str, float]:
    low = _weighted_quantile(values, weights, lower_quantile)
    high = _weighted_quantile(values, weights, upper_quantile)
    midpoint = (low + high) / 2
    return {
        "low": round(low, 4),
        "high": round(high, 4),
        "concentration_pct": round((high - low) / midpoint * 100 if midpoint else 0.0, 2),
    }


def _unavailable(reason: str) -> dict[str, Any]:
    return {
        "state": "unavailable",
        "model": "instock-volume-price-cost-proxy-v1",
        "label": "成交成本分布代理",
        "reason": reason,
        "profile": [],
        "limitations": ["volume_price_proxy_not_shareholder_chip_distribution"],
    }
