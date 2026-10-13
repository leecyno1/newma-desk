import pytest
from datetime import datetime

from vibe_visualization_api.portfolio_center.performance import analyze_performance
from vibe_visualization_api.portfolio_center.history import PortfolioPriceHistory, align_weekly_histories, DataServicePortfolioHistoryProvider


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


def test_extreme_returns_are_not_silently_clipped():
    result = analyze_performance([[100, 5, 25, 25, 25, 25, 25, 25, 25]], [1])
    assert result.worst_period == pytest.approx(-0.95)
    assert result.best_period == pytest.approx(4)
    with pytest.raises(ValueError):
        analyze_performance([[100, 0, 101, 102, 103, 104, 105, 106, 107]], [1])


def test_cvar_uses_fractional_five_percent_tail():
    result = analyze_performance([[100, 10, 5] + [5] * 28], [1])
    assert result.observations == 30
    assert result.value_at_risk_95 == pytest.approx(-0.5)
    assert result.conditional_value_at_risk_95 == pytest.approx(-0.5 - 0.4 / 1.5)


def test_weekly_history_uses_dates_not_array_offsets_or_missing_week_bridges():
    stamps = tuple(1_700_000_000_000 + i * 604_800_000 for i in range(20))
    first = PortfolioPriceHistory(tuple(range(100,120)), stamps)
    second = PortfolioPriceHistory(tuple(range(200,215)), stamps[5:])
    aligned, labels, as_of = align_weekly_histories([first,second], 100)
    assert aligned[0][0] == 105
    assert aligned[1][0] == 200
    assert len(labels) == 15
    assert as_of is not None
    gap = PortfolioPriceHistory(tuple(range(200,214)), stamps[5:10] + stamps[11:])
    aligned, labels, _ = align_weekly_histories([first,gap], 100)
    assert len(labels) == 9
    assert aligned[0][0] == 111
    assert align_weekly_histories([PortfolioPriceHistory(first.closes)],100)[1] == []


def test_missing_timestamps_are_not_fabricated():
    history = DataServicePortfolioHistoryProvider._parse({'data': {'items': [{'close':100},{'close':110}]}})
    assert history is None


def test_weekly_buckets_use_exchange_timezone():
    cn = datetime.fromisoformat('2026-09-07T00:00:00+08:00').timestamp() * 1000
    us = datetime.fromisoformat('2026-09-07T00:00:00-04:00').timestamp() * 1000
    aligned, labels, _ = align_weekly_histories([
        PortfolioPriceHistory((100,), (cn,)), PortfolioPriceHistory((200,), (us,)),
    ], 100, ['Asia/Shanghai','America/New_York'])
    assert labels == ['2026-09-07']
    assert aligned == [[100],[200]]


def test_performance_normalizes_covered_asset_weights() -> None:
    first = [100 * (1.01**index) for index in range(20)]
    second = [100 * (1.005**index) for index in range(20)]

    estimate = analyze_performance([first, second], [2, 1])

    assert estimate.win_rate == pytest.approx(1)
    assert estimate.total_return > 0
