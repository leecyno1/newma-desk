#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Shared point-in-time execution primitives for validation modules."""

from __future__ import annotations

import math
from typing import Any

import numpy as np
import pandas as pd


def valid_execution_price(value: Any) -> float | None:
    try:
        price = float(value)
    except (TypeError, ValueError):
        return None
    return price if math.isfinite(price) and price > 0 else None


def check_open_limit(evidence, side):
    """Compare only an explicitly unadjusted open with same-day limits."""
    evidence = evidence or {}
    result = {"state": "unverified", "reason": evidence.get("reason") or "missing_limit_pair"}
    if evidence.get("status") != "paired" or evidence.get("priceBasis") != "unadjusted":
        return result
    opening, upper, lower = (valid_execution_price(evidence.get(key)) for key in ("rawOpen", "upperLimit", "lowerLimit"))
    if None in (opening, upper, lower) or lower >= upper or not lower - 1e-8 <= opening <= upper + 1e-8:
        return {**result, "reason": "invalid_price_limit_pair"}
    reason = ("buy_at_upper_limit" if side == "buy" and opening >= upper - 1e-8
              else "sell_at_lower_limit" if side == "sell" and opening <= lower + 1e-8 else None)
    return {"state": "adverse" if reason else "checked", "reason": reason,
            "rawOpen": opening, "upperLimit": upper, "lowerLimit": lower, "priceBasis": "unadjusted"}


def audit_open_bar(bar, *, limit=None, side=None):
    """Ex-post evidence, not an opening-time filter or a fill guarantee.

    A positive full-day volume cannot prove that our order filled at the open.
    Zero volume contradicts a simulated fill; missing volume cannot certify it.
    Callers must retain planned signals/capacity rather than choose replacements.
    """
    price = valid_execution_price(bar.get("open"))
    try:
        volume = float(bar.get("volume"))
    except (TypeError, ValueError):
        volume = math.nan
    volume = volume if math.isfinite(volume) and volume >= 0 else None
    reason = ("missing_open" if price is None else "missing_volume" if volume is None
              else "zero_volume" if volume == 0 else None)
    limit_check = check_open_limit(limit, side) if side else None
    if reason is None and limit_check and limit_check["state"] == "adverse":
        reason = limit_check["reason"]
    return {"price": price if reason is None else None, "volume": volume, "reason": reason,
            "limit_check": limit_check}


def round_trip_cost(cost_bps_per_side: int | float, *, executed: bool = True) -> float:
    return 2 * float(cost_bps_per_side) / 10_000 if executed else 0.0


def resolve_next_open_window(
    frame: pd.DataFrame,
    *,
    decision_date: pd.Timestamp,
    holding_period_sessions: int,
):
    dates = pd.to_datetime(frame["date"]).reset_index(drop=True)
    positions = np.flatnonzero(dates.to_numpy() <= np.datetime64(decision_date))
    if positions.size == 0:
        return None
    entry_position = int(positions[-1]) + 1
    exit_position = entry_position + int(holding_period_sessions)
    if exit_position >= len(frame):
        return None
    entry_price = valid_execution_price(frame["open"].iloc[entry_position])
    exit_price = valid_execution_price(frame["open"].iloc[exit_position])
    if entry_price is None or exit_price is None:
        return None
    return dates.iloc[entry_position], dates.iloc[exit_position], entry_price, exit_price
