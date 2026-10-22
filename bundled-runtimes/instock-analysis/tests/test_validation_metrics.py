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
import pytest


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
    assert all(value is None for key, value in result.items() if key != "trades")
    assert rotation_metrics([], 10)["execution_state"] == "unavailable"
    assert rotation_metrics([], 10)["equal_weight_return_pct"] is None


@pytest.mark.parametrize("returns, benchmark", [
    ([0.01], [0.0]),
    ([0.0, 0.0], [0.0, 0.0]),
    ([0.01] * 10, [0.0] * 10),
    ([-0.01] * 10, [0.0] * 10),
])
def test_zero_dispersion_or_single_observation_has_no_risk_ratio(returns, benchmark):
    result = calculate_return_metrics([
        {"net_return": a, "benchmark_return": b} for a, b in zip(returns, benchmark)
    ], period_sessions=10)
    assert result["sharpe"] is None
    assert result["information_ratio"] is None
    assert result["total_return_pct"] is not None
    assert result["max_drawdown_pct"] is not None
    assert result["annualized_volatility_pct"] == (None if len(returns) == 1 else 0.0)


def test_zero_active_dispersion_does_not_hide_valid_strategy_sharpe():
    result = calculate_return_metrics([
        {"net_return": a, "benchmark_return": a - .01} for a in [.02, -.01, .03]
    ], period_sessions=10)
    assert result["sharpe"] is not None
    assert result["information_ratio"] is None


def test_actual_zero_mean_with_nonzero_dispersion_is_valid_zero_ratio():
    result = calculate_return_metrics([
        {"net_return": a, "benchmark_return": 0} for a in [.01, -.01]
    ], period_sessions=10)
    assert result["sharpe"] == 0.0
    assert result["information_ratio"] == 0.0


def test_undefined_training_ratios_cannot_be_scored_as_zero():
    metrics = {"trades": 12, "execution_state": "complete", "sharpe": None,
               "information_ratio": 1.0, "excess_return_pct": 5, "max_drawdown_pct": 0}
    assert not RotationExperiment._can_score(metrics)
    metrics["sharpe"] = 0.0
    assert RotationExperiment._can_score(metrics)


def test_empty_forecast_and_ensemble_have_no_hit_rate_or_confidence_interval():
    for summary in [RotationExperiment._effect_summary([], horizon=10),
                    *RotationExperiment._summarize_prediction_records([])["horizons"]]:
        assert summary["samples"] == 0
        assert summary["rank_ic_mean"] is None
        assert summary["top3_beat_benchmark_rate_pct"] is None
        assert summary["top3_beat_benchmark_wilson_95_pct"] is None
    for high in (False, True):
        summary = RotationExperiment._ensemble_signal_summary([], high_confidence_only=high)
        assert summary["gross_beat_benchmark_rate_pct"] is None
        assert summary["gross_beat_benchmark_wilson_95_pct"] is None
    confidence = RotationExperiment._confidence_diagnostics([], [], horizon=10)
    assert confidence["verdict"]["state"] == "insufficient_samples"
    assert confidence["out_of_sample"]["high_confidence"]["top3_hit_delta_pct"] is None


@pytest.mark.parametrize("returns, expected", [
    ([-0.10], 10.0),
    ([-0.10, -0.10], 19.0),
    ([-0.10, 0.05], 10.0),
    ([0.10, -0.20, 0.10], 20.0),
    ([0.0, 0.0], 0.0),
    ([0.10, 0.10], 0.0),
    ([-1.0], 100.0),
])
def test_drawdown_includes_initial_investment(returns, expected):
    trades = [{"net_return": value, "benchmark_return": 0.0} for value in returns]
    result = calculate_return_metrics(trades, period_sessions=5)
    assert result["max_drawdown_pct"] == pytest.approx(expected)


def test_rotation_curve_starts_at_invested_capital():
    assert RotationExperiment._equity_curve([]) == []
    curve = RotationExperiment._equity_curve([{
        "entry_date": "2026-01-05", "exit_date": "2026-01-12", "symbol": "510300",
        "net_return": -0.10, "benchmark_return": -0.05, "equal_weight_return": -0.02,
    }])
    assert curve[0] == {"date": "2026-01-05", "strategy": 1.0, "benchmark": 1.0,
                        "equal_weight": 1.0, "symbol": None}
    assert curve[1]["strategy"] == 0.9


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
