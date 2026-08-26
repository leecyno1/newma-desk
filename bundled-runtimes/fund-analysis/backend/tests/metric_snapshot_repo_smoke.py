import os
import sys
from datetime import date
from decimal import Decimal

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from repositories.metric_snapshot_repo import MetricSnapshotRepo


def main() -> int:
    repo = MetricSnapshotRepo()
    metric = repo.upsert_metric(
        target_type="fund",
        target_id="UNIT.TEST",
        as_of_date=date(2026, 5, 15),
        metric_name="annualized_return",
        metric_value=Decimal("0.12345678"),
        metric_unit="ratio",
        window="1y",
        benchmark_code="000300.SH",
        peer_group_key="equity_large_cap",
        details={"purpose": "smoke"},
    )
    if metric.get("metric_name") != "annualized_return":
        print(f"Expected annualized_return, got: {metric}")
        return 1

    updated = repo.upsert_metric(
        target_type="fund",
        target_id="UNIT.TEST",
        as_of_date=date(2026, 5, 15),
        metric_name="annualized_return",
        metric_value=Decimal("0.25"),
        metric_unit="ratio",
        window="1y",
        benchmark_code="000300.SH",
        peer_group_key="equity_large_cap",
    )
    if Decimal(str(updated.get("metric_value"))) != Decimal("0.25000000"):
        print(f"Expected updated metric value, got: {updated}")
        return 1

    panel = repo.get_latest_panel("fund", "UNIT.TEST")
    if not any(item.get("metric_name") == "annualized_return" for item in panel):
        print(f"Expected annualized_return in panel, got: {panel}")
        return 1

    print("OK metric snapshot repository upsert and panel")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
