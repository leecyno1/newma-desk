"""Price-limit decisions must use the open fill, never the current close."""

from __future__ import annotations

import pandas as pd
import pytest

from backtest.engines.china_a import ChinaAEngine
from backtest.engines.china_futures import ChinaFuturesEngine
from backtest.engines.global_futures import GlobalFuturesEngine
from backtest.engines.india_equity import IndiaEquityEngine
from backtest.models import Position


@pytest.mark.parametrize(
    ("engine", "symbol", "limit", "base_field"),
    [
        (ChinaAEngine({"slippage": 0.0}), "000001.SZ", 0.10, "pre_close"),
        (IndiaEquityEngine({"slippage": 0.0}), "RELIANCE.NS", 0.20, "pre_close"),
        (ChinaFuturesEngine({"slippage": 0.0}), "IF2406.CFFEX", 0.10, "pre_settle"),
        (GlobalFuturesEngine({"slippage": 0.0}), "ESZ4", 0.07, "pre_settle"),
    ],
)
def test_locked_open_blocks_buy_even_when_close_moves_inside_band(
    engine, symbol: str, limit: float, base_field: str
) -> None:
    bar = pd.Series(
        {"open": 100.0 * (1 + limit), "close": 101.0, base_field: 100.0}
    )

    assert engine.can_execute(symbol, 1, bar) is False


@pytest.mark.parametrize(
    ("engine", "symbol", "limit", "base_field"),
    [
        (ChinaAEngine({"slippage": 0.0}), "000001.SZ", 0.10, "pre_close"),
        (IndiaEquityEngine({"slippage": 0.0}), "RELIANCE.NS", 0.20, "pre_close"),
        (ChinaFuturesEngine({"slippage": 0.0}), "IF2406.CFFEX", 0.10, "pre_settle"),
        (GlobalFuturesEngine({"slippage": 0.0}), "ESZ4", 0.07, "pre_settle"),
    ],
)
def test_tradeable_open_allows_buy_even_when_close_locks(
    engine, symbol: str, limit: float, base_field: str
) -> None:
    bar = pd.Series(
        {"open": 100.5, "close": 100.0 * (1 + limit), base_field: 100.0}
    )

    assert engine.can_execute(symbol, 1, bar) is True


def test_futures_close_uses_position_side() -> None:
    engine = ChinaFuturesEngine({"slippage": 0.0})
    symbol = "IF2406.CFFEX"
    engine.positions[symbol] = Position(
        symbol=symbol,
        direction=-1,
        entry_price=100.0,
        entry_time=pd.Timestamp("2026-01-01"),
        size=1.0,
    )
    bar = pd.Series({"open": 110.0, "close": 101.0, "pre_settle": 100.0})

    assert engine.can_execute(symbol, 0, bar) is False


def test_previous_close_panel_supplies_missing_base_price() -> None:
    engine = ChinaAEngine({"slippage": 0.0})
    engine._close_arr = pd.DataFrame({"A": [100.0, 101.0]}).to_numpy()
    engine._code_to_col = {"000001.SZ": 0}
    engine._bar_idx = 1
    bar = pd.Series({"open": 110.0, "close": 101.0})

    assert engine.can_execute("000001.SZ", 1, bar) is False
