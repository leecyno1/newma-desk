import pytest

from vibe_visualization_api.portfolio_center.performance import analyze_performance


def test_performance_metrics_cover_return_risk_and_drawdown() -> None:
    first = [100, 103, 105, 101, 107, 110, 108, 114, 118, 117, 122]
    second = [100, 101, 102, 103, 102, 105, 106, 108, 109, 111, 112]

    estimate = analyze_performance([first, second], [0.6, 0.4], risk_free_rate=0.02)

    assert estimate.observations == 10
    assert estimate.total_return > 0
    assert estimate.annualized_volatility > 0
    assert estimate.max_drawdown < 0
    assert estimate.max_drawdown_duration >= 1
    assert estimate.sharpe is not None
    assert estimate.best_period > estimate.worst_period
    assert len(estimate.equity_curve) == 10


def test_performance_normalizes_covered_asset_weights() -> None:
    first = [100 * (1.01**index) for index in range(20)]
    second = [100 * (1.005**index) for index in range(20)]

    estimate = analyze_performance([first, second], [2, 1])

    assert estimate.win_rate == pytest.approx(1)
    assert estimate.total_return > 0
