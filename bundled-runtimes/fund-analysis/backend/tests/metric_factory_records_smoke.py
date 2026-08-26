import os
import sys
from datetime import date

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from services.metric_factory import MetricFactory


def main() -> int:
    factory = MetricFactory(risk_free_rate=0)
    records = factory.build_metric_records(
        target_type="fund",
        target_id="UNIT.TEST",
        as_of_date=date(2026, 5, 15),
        nav_series=[
            {"date": "2026-01-01", "nav": 1.0},
            {"date": "2026-01-02", "nav": 1.1},
        ],
        window="all",
    )
    names = {record["metric_name"] for record in records}
    expected = {
        "total_return", "annualized_return", "record_breaking_days_ratio",
        "max_drawdown", "sharpe_ratio",
    }
    missing = expected - names
    if missing:
        print(f"Missing metric records {missing}: {records}")
        return 1
    if not all(record["target_type"] == "fund" and record["target_id"] == "UNIT.TEST" for record in records):
        print(f"Expected target metadata on all records: {records}")
        return 1
    print("OK metric factory builds persistable records")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
