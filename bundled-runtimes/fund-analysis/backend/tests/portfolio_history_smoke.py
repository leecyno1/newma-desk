"""Numerical portfolio-history regression. All inputs are isolated; no DB writes."""
import math
import os
import sys
from datetime import date, timedelta
from unittest.mock import patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from services.portfolio_service import PortfolioService, HISTORY_METHODOLOGY


service = PortfolioService(repo=object(), similarity_service=object(), style_repo=object())
assert service._correlation_matrix(["A"], {})["methodology_version"] == HISTORY_METHODOLOGY
dates = [(date.today() - timedelta(days=70-i)).isoformat() for i in range(71)]
holdings = [{"wind_code": "A", "weight": 0.5}, {"wind_code": "B", "weight": 0.5}]
service.get_portfolio = lambda _: {"name": "isolated", "holdings": holdings}
series = {code: {day: 1 if i == 0 else 0.8 for i, day in enumerate(dates)} for code in ("A", "B")}
service._load_nav_series = lambda codes, days: {code: series[code] for code in codes}
bench_calls = []
def benchmark(code, start, end):
    bench_calls.append(code)
    return {day: 1 for day in dates}
service._load_benchmark_series = benchmark
service._load_benchmark_metadata = lambda _: {"code": "isolated", "name": "isolated"}
with patch.object(service, "_save_portfolio_snapshot", side_effect=AssertionError("must not save")):
    result = service.backtest("isolated")
assert result["methodology_version"] == HISTORY_METHODOLOGY
assert result["metrics"]["cumulative_return"] == -0.2
assert result["metrics"]["max_drawdown"] == -0.2
assert result["curve"][0] == {"date": dates[0], "value": 1}
assert len(result["curve"]) == 71 and result["sample"]["return_intervals"] == 70
assert result["benchmark"]["metrics"]["start_date"] == result["metrics"]["start_date"]
assert result["benchmark"]["excess_return"] == -0.2

# A missing initial/interior benchmark date must not generate an unmatched excess.
service._load_benchmark_series = lambda code, start, end: (bench_calls.append(code) or {day: 1 for day in dates[1:]})
bench_calls.clear()
result = service.backtest("isolated", benchmark_wind_code="CHOSEN")
assert bench_calls == ["CHOSEN"]
assert result["benchmark"]["status"] == "insufficient"
assert "excess_return" not in result["benchmark"]

# Align NAV dates before returns: missing B dates otherwise compare multi-day vs one-day returns.
path = {day: 1 + i * 0.004 + (i % 3) * 0.002 for i, day in enumerate(dates)}
series = {"A": path, "B": {day: value * 2 for day, value in path.items() if day != dates[20]}}
pair = service._correlation_matrix(["A", "B"], {})["pairs"][0]
assert pair["correlation"] == 1 and pair["return_intervals"] == 69
result = service.backtest("isolated")
assert result["sample"]["omitted_union_dates"] == 1
assert result["metrics"]["annualized_volatility"] is None

series = {"A": {day: 1 for day in dates}, "B": path}
pair = service._correlation_matrix(["A", "B"], {})["pairs"][0]
assert pair["correlation"] is None and pair["status"] == "zero_variance"
series["A"] = dict(list(series["A"].items())[:60])
assert service.backtest("isolated")["status"] == "insufficient_sample"
assert service._correlation_matrix(["A", "B"], {})["pairs"][0]["status"] == "insufficient_overlap"

metrics = PortfolioService._performance_metrics([0.1, 0.1], ["2025-01-01", "2025-06-01", "2026-01-01"])
assert math.isclose(metrics["annualized_return"], 1.21 ** (365.25/365) - 1, abs_tol=1e-6)
assert metrics["annualized_volatility"] is None

# Read-path contract: only positive finite adjusted NAVs survive, with a calendar cutoff.
class FakeConnection:
    def __enter__(self): return self
    def __exit__(self, *args): pass
    def execute(self, query, params):
        assert params["start"] == (date.today() - timedelta(days=365)).isoformat()
        assert params["end"] == date.today().isoformat()
        return self
    def fetchall(self): return [(dates[i], value) for i, value in enumerate([None, 0, -1, float('nan'), float('inf'), 1.2])]
class FakeEngine:
    def connect(self): return FakeConnection()
with patch('services.portfolio_service.get_engine', return_value=FakeEngine()):
    points = PortfolioService._load_nav_series(service, ["A"], 365)
assert points == {"A": {dates[5]: 1.2}}
print("PASS portfolio adjusted NAV, common intervals, baseline drawdown, calendar annualization, benchmark alignment and zero variance")
