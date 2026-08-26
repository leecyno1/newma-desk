import math
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from services.metric_factory import MetricFactory


def assert_close(actual, expected, tolerance=1e-6):
    if not math.isclose(actual, expected, rel_tol=tolerance, abs_tol=tolerance):
        raise AssertionError(f"Expected {expected}, got {actual}")


def main() -> int:
    nav_series = [
        {"date": "2026-01-01", "nav": 1.00},
        {"date": "2026-01-02", "nav": 1.01},
        {"date": "2026-01-03", "nav": 0.99},
        {"date": "2026-01-04", "nav": 1.03},
    ]
    benchmark_series = [
        {"date": "2026-01-01", "nav": 1.00},
        {"date": "2026-01-02", "nav": 1.005},
        {"date": "2026-01-03", "nav": 1.000},
        {"date": "2026-01-04", "nav": 1.010},
    ]

    factory = MetricFactory(trading_days=252, risk_free_rate=0)
    returns = factory.calculate_return_metrics(nav_series)
    risks = factory.calculate_risk_metrics(nav_series)
    relative = factory.calculate_relative_metrics(nav_series, benchmark_series)

    assert_close(returns["total_return"], 0.03)
    assert_close(returns["record_breaking_days_ratio"], 0.75)
    if returns["annualized_return"] <= 0:
        raise AssertionError(f"Expected positive annualized return, got {returns}")
    if risks["annualized_volatility"] <= 0:
        raise AssertionError(f"Expected positive volatility, got {risks}")
    assert_close(risks["max_drawdown"], -0.01980198019801982)
    if risks["sharpe_ratio"] <= 0:
        raise AssertionError(f"Expected positive sharpe, got {risks}")
    assert_close(relative["excess_return"], 0.02)
    if "information_ratio" not in relative:
        raise AssertionError(f"Expected information_ratio, got {relative}")

    empty = factory.calculate_return_metrics([])
    if empty:
        raise AssertionError(f"Expected empty metrics for empty series, got {empty}")

    print("OK metric factory deterministic metrics")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
