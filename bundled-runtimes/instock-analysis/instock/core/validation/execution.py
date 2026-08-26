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
