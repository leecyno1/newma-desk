"""Execution-derived turnover regressions."""

from __future__ import annotations

import pandas as pd
import pytest

from backtest.engines.base import BaseEngine
from backtest.metrics import calc_execution_turnover


class _RoundedEngine(BaseEngine):
    def can_execute(self, symbol, direction, bar):
        return True

    def round_size(self, raw_size, price):
        return float(int(raw_size))

    def calc_commission(self, size, price, direction, is_open):
        return 0.0

    def apply_slippage(self, price, direction):
        return price


def test_turnover_uses_filled_size_instead_of_target_weight() -> None:
    dates = pd.bdate_range("2026-01-05", periods=2)
    bars = pd.DataFrame({"open": [60.0, 60.0], "close": [60.0, 60.0]}, index=dates)
    close = pd.DataFrame({"TEST": bars.close}, index=dates)
    targets = pd.DataFrame({"TEST": [0.55, 0.0]}, index=dates)
    engine = _RoundedEngine({"initial_cash": 1_000.0})

    engine._execute_bars(dates, {"TEST": bars}, close, targets, ["TEST"])
    equity = pd.Series([snapshot.equity for snapshot in engine.equity_snapshots], index=dates)
    turnover = calc_execution_turnover(pd.Series(engine._executed_margin), equity)

    assert turnover.tolist() == pytest.approx([0.27, 0.27])


def test_rejected_target_records_no_execution() -> None:
    class _RejectingEngine(_RoundedEngine):
        def can_execute(self, symbol, direction, bar):
            return False

    date = pd.DatetimeIndex(["2026-01-05"])
    bars = pd.DataFrame({"open": [10.0], "close": [10.0]}, index=date)
    engine = _RejectingEngine({"initial_cash": 1_000.0})

    engine._execute_bars(
        date,
        {"TEST": bars},
        pd.DataFrame({"TEST": bars.close}, index=date),
        pd.DataFrame({"TEST": [1.0]}, index=date),
        ["TEST"],
    )

    assert engine._executed_margin == {}
