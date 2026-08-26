from __future__ import annotations

from instock.core.rotation.rotation_experiment import _metrics as rotation_metrics
from instock.core.rotation.rotation_experiment import RotationExperiment
from instock.core.validation.execution import (
    resolve_next_open_window,
    round_trip_cost,
    valid_execution_price,
)
from instock.core.validation.metrics import calculate_return_metrics
from instock.core.validation.strategy_validation import StrategyValidationEngine
from instock.core.validation.strategy_validation import _metrics as strategy_metrics
import pandas as pd


def _trades():
    return [
        {
            "net_return": 0.04,
            "benchmark_return": 0.01,
            "equal_weight_return": 0.02,
            "transaction_cost": 0.005,
            "switched": True,
            "invested": True,
        },
        {
            "net_return": -0.02,
            "benchmark_return": -0.01,
            "equal_weight_return": -0.015,
            "transaction_cost": 0.0,
            "switched": False,
            "invested": True,
        },
        {
            "net_return": 0.03,
            "benchmark_return": 0.015,
            "equal_weight_return": 0.02,
            "transaction_cost": 0.005,
            "switched": True,
            "invested": True,
        },
    ]


def test_strategy_and_rotation_share_identical_core_return_metrics():
    trades = _trades()
    strategy = strategy_metrics(trades, 10)
    rotation = rotation_metrics(trades, 10)
    shared = calculate_return_metrics(trades, period_sessions=10)

    core_keys = {
        "trades",
        "total_return_pct",
        "annualized_return_pct",
        "annualized_volatility_pct",
        "sharpe",
        "max_drawdown_pct",
        "win_rate_pct",
        "benchmark_return_pct",
        "excess_return_pct",
        "information_ratio",
        "beat_benchmark_rate_pct",
    }
    assert {key: strategy[key] for key in core_keys} == shared
    assert {key: rotation[key] for key in core_keys} == shared


def test_shared_metrics_handles_empty_evidence_deterministically():
    result = calculate_return_metrics([], period_sessions=10)

    assert result["trades"] == 0
    assert result["total_return_pct"] == 0.0
    assert result["max_drawdown_pct"] == 0.0


def test_strategy_and_rotation_share_execution_price_and_cost_primitives():
    frame = pd.DataFrame({
        "date": pd.bdate_range("2026-01-02", periods=5),
        "open": [10.0, 10.5, 11.0, 11.5, 12.0],
    })

    shared_window = resolve_next_open_window(
        frame, decision_date=pd.Timestamp("2026-01-02"), holding_period_sessions=2
    )
    strategy_window = StrategyValidationEngine._execution_window(
        frame, pd.Timestamp("2026-01-02"), 2
    )

    assert strategy_window == shared_window
    assert RotationExperiment._valid_execution_price(11.5) == valid_execution_price(11.5)
    assert round_trip_cost(25, executed=True) == 0.005
    assert round_trip_cost(25, executed=False) == 0.0
