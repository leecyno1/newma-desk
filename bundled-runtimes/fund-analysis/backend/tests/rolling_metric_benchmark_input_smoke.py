import os
import sys
from datetime import date, timedelta

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from services.rolling_metric_service import RollingMetricService


def main() -> int:
    start = date(2026, 1, 1)
    fund_nav = 1.0
    benchmark_nav = 1.0
    series = []
    for offset in range(40):
        fund_nav *= 1.0010 if offset % 9 else 0.9980
        benchmark_nav *= 1.0008 if offset % 11 else 0.9985
        series.append({
            "date": (start + timedelta(days=offset)).isoformat(),
            "nav": fund_nav,
            "benchmark_nav": benchmark_nav,
        })

    records = RollingMetricService(windows={"20d": 20}).calculate_for_nav_series(
        series,
        target_type="fund",
        target_id="INDEX.BENCHMARK",
        benchmark_code="000300.SH",
    )
    by_name = {record.get("metric_name"): record for record in records}
    for metric_name in ["benchmark_return", "excess_return", "tracking_error", "information_ratio"]:
        if metric_name not in by_name:
            raise AssertionError(f"Benchmark-aware rolling metric missing {metric_name}: {by_name}")
        if by_name[metric_name].get("benchmark_code") != "000300.SH":
            raise AssertionError(f"Relative metric lost benchmark identity: {by_name[metric_name]}")
    for metric_name in ["annualized_return", "max_drawdown", "sharpe_ratio"]:
        if by_name[metric_name].get("benchmark_code") is not None:
            raise AssertionError(f"Absolute metric must not be keyed by a benchmark: {by_name[metric_name]}")

    no_benchmark_records = RollingMetricService(windows={"20d": 20}).calculate_for_nav_series(
        [{"date": item["date"], "nav": item["nav"]} for item in series],
        target_type="fund",
        target_id="NO.BENCHMARK",
        benchmark_code="000300.SH",
    )
    if any(record.get("metric_name") == "tracking_error" for record in no_benchmark_records):
        raise AssertionError("Benchmark code alone must not fabricate relative metrics")

    print("OK rolling metrics consume actual benchmark NAV and never infer it from a code")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
