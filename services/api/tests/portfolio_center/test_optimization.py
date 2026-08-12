import pytest

from vibe_visualization_api.portfolio_center.optimization import optimize_weights


def _series(step: float, *, wobble: float = 0.0) -> list[float]:
    values = [100.0]
    for index in range(80):
        direction = -1 if index % 2 else 1
        values.append(values[-1] * (1 + step + direction * wobble))
    return values


def test_minimum_volatility_prefers_the_more_stable_series() -> None:
    estimate = optimize_weights(
        [_series(0.002, wobble=0.001), _series(0.003, wobble=0.035)],
        objective="minimum-volatility",
        max_weight=0.8,
    )

    assert estimate.observations == 80
    assert sum(estimate.weights) == pytest.approx(1)
    assert estimate.weights[0] > estimate.weights[1]
    assert estimate.weights[0] <= 0.8 + 1e-9
    assert estimate.portfolio_volatility > 0


def test_return_seeking_respects_cash_and_weight_caps() -> None:
    estimate = optimize_weights(
        [_series(0.004), _series(0.002), _series(0.001)],
        objective="return-seeking",
        total_weight=0.9,
        max_weight=0.45,
        risk_free_rate=0.02,
        cash_weight=0.1,
    )

    assert sum(estimate.weights) == pytest.approx(0.9)
    assert max(estimate.weights) <= 0.45 + 1e-9
    assert estimate.portfolio_return > 0
