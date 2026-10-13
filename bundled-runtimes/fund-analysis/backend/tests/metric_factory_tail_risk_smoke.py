import math
import os
import sys
from datetime import date, timedelta

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from services.metric_factory import MetricFactory


def build_nav_series(daily_returns, start=date(2026, 1, 1)):
    nav = 1.0
    series = [{"date": start.isoformat(), "nav": nav}]
    for offset, value in enumerate(daily_returns, start=1):
        nav *= 1 + value
        series.append({"date": (start + timedelta(days=offset)).isoformat(), "nav": nav})
    return series


def expected_var_cvar(daily_returns, level=0.05):
    ordered = sorted(daily_returns)
    position = level * (len(ordered) - 1)
    lower = int(math.floor(position))
    upper = int(math.ceil(position))
    fraction = position - lower
    var = ordered[lower] + (ordered[upper] - ordered[lower]) * fraction
    tail = [value for value in ordered if value <= var + 1e-15]
    cvar = sum(tail) / len(tail)
    return var, cvar


def main() -> int:
    factory = MetricFactory()

    daily_returns = [0.012, -0.030, 0.008, -0.011, 0.020, -0.045, 0.006, 0.004, -0.018, 0.009,
                     -0.007, 0.015, -0.022, 0.011, 0.003, -0.009, 0.017, -0.013, 0.007, 0.005]
    risk = factory.calculate_risk_metrics(build_nav_series(daily_returns))

    expected_var, expected_cvar = expected_var_cvar(daily_returns)
    if abs(risk.get("var_95", 0) - expected_var) > 1e-9:
        raise AssertionError(f"var_95 must be the 5th percentile of daily returns: {risk} vs {expected_var}")
    if abs(risk.get("cvar_95", 0) - expected_cvar) > 1e-9:
        raise AssertionError(f"cvar_95 must be the mean of returns beyond var_95: {risk} vs {expected_cvar}")

    nav = 1.00
    monthly_nav = [{"date": "2026-01-05", "nav": nav}]
    month_returns = [("2026-01-30", 0.02), ("2026-02-27", -0.01), ("2026-03-31", 0.03),
                     ("2026-04-30", 0.01), ("2026-05-29", -0.02), ("2026-06-30", 0.015)]
    for month_end, month_return in month_returns:
        nav = nav * (1 + month_return)
        monthly_nav.append({"date": month_end, "nav": nav})

    risk_monthly = factory.calculate_risk_metrics(monthly_nav)
    expected_win_rate = 4 / 6
    if abs(risk_monthly.get("monthly_win_rate", -1) - expected_win_rate) > 1e-9:
        raise AssertionError(f"monthly_win_rate must be positive-month share: {risk_monthly} vs {expected_win_rate}")

    flat_risk = factory.calculate_risk_metrics(build_nav_series([0.001] * 10))
    if flat_risk.get("monthly_win_rate") != 1.0:
        raise AssertionError(f"all-positive months must give win rate 1.0: {flat_risk}")

    print("OK metric factory derives tail risk and monthly win rate from nav series")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
