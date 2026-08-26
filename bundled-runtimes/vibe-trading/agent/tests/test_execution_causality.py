"""Causality regressions for the shared execution loop."""

from __future__ import annotations

import pandas as pd

from backtest.engines.base import BaseEngine


class _FrictionlessEngine(BaseEngine):
    def can_execute(self, symbol, direction, bar):
        return True

    def round_size(self, raw_size, price):
        return raw_size

    def calc_commission(self, size, price, direction, is_open):
        return 0.0

    def apply_slippage(self, price, direction):
        return price


def _rotation(last_close_a: float, codes: list[str]) -> _FrictionlessEngine:
    dates = pd.bdate_range("2026-01-05", periods=2)
    bars_a = pd.DataFrame(
        {"open": [100.0, 100.0], "close": [100.0, last_close_a]}, index=dates
    )
    bars_b = pd.DataFrame(
        {"open": [100.0, 100.0], "close": [100.0, 100.0]}, index=dates
    )
    data = {"A": bars_a, "B": bars_b}
    close = pd.DataFrame({"A": bars_a.close, "B": bars_b.close}, index=dates)
    targets = pd.DataFrame({"A": [0.5, 0.0], "B": [0.0, 0.5]}, index=dates)
    engine = _FrictionlessEngine({"initial_cash": 100_000.0})
    engine._execute_bars(dates, data, close, targets, codes)
    return engine


def test_unknown_decision_bar_close_cannot_change_open_size() -> None:
    baseline = _rotation(100.0, ["A", "B"])
    shocked = _rotation(200.0, ["A", "B"])

    baseline_b = next(trade for trade in baseline.trades if trade.symbol == "B")
    shocked_b = next(trade for trade in shocked.trades if trade.symbol == "B")
    assert baseline_b.size == shocked_b.size == 500.0


def test_rotation_is_independent_of_symbol_order() -> None:
    first = _rotation(100.0, ["A", "B"])
    reversed_order = _rotation(100.0, ["B", "A"])

    def normalize(engine: _FrictionlessEngine) -> list[tuple[str, float, str]]:
        return sorted(
            (trade.symbol, trade.size, trade.exit_reason) for trade in engine.trades
        )

    assert normalize(first) == normalize(reversed_order)
