import os
import sys
import atexit
from datetime import date, timedelta
from decimal import Decimal

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from database import init_database
from repositories import get_fund_repo, get_metric_snapshot_repo, get_nav_repo, get_research_profile_repo
from services.data_quality_service import DataQualityService
from services.manager_tenure_metric_service import ManagerTenureMetricService
from smoke_cleanup import cleanup_fund_codes


def _nav_series(start: date, days: int) -> list[dict]:
    nav = Decimal("1.0000")
    series = []
    for offset in range(days):
        trade_date = start + timedelta(days=offset)
        daily_change = Decimal("0.0006") if offset % 19 else Decimal("-0.0030")
        nav = max(Decimal("0.7000"), nav * (Decimal("1") + daily_change))
        series.append({"date": trade_date.isoformat(), "nav": float(nav), "accum_nav": float(nav)})
    return series


def main() -> int:
    init_database()

    fund_code = "TENURE.TEST"
    cleanup_fund_codes([fund_code])
    atexit.register(cleanup_fund_codes, [fund_code])
    fund_repo = get_fund_repo()
    nav_repo = get_nav_repo()
    profile_repo = get_research_profile_repo()
    metric_repo = get_metric_snapshot_repo()

    fund_repo.upsert_fund(fund_code, {
        "name": "任期切片测试基金",
        "type": "stock",
        "nav": 1.2345,
        "nav_date": "2026-05-29",
        "total_asset": 42.0,
        "establishment_date": "2023-01-01",
        "performance": {"return_1y": 0.12},
        "risk_metrics": {"max_drawdown": -0.12},
    })
    profile_repo.upsert_profile(
        wind_code=fund_code,
        primary_benchmark="沪深300",
        peer_group="主动权益-任期测试",
        style_label="任期测试",
        manager_tenure_start="2025-01-01",
        data_quality_notes="smoke 任期切片数据齐备",
        updated_by="tenure-smoke",
    )
    nav_repo.delete_nav(fund_code)
    nav_repo.upsert_nav_series(fund_code, _nav_series(date(2024, 1, 1), 780))

    tenure_result = ManagerTenureMetricService().calculate_and_save_for_fund(fund_code)
    if tenure_result.get("saved", 0) <= 0:
        raise AssertionError(f"Expected tenure metrics to be saved, got {tenure_result}")

    panel = metric_repo.get_latest_panel("fund", fund_code)
    tenure_metrics = {
        item.get("metric_name"): item
        for item in panel
        if item.get("metric_window") == "manager_tenure"
    }
    for metric_name in {"total_return", "annualized_return", "max_drawdown", "positive_return_ratio", "tenure_days", "observations"}:
        if metric_name not in tenure_metrics:
            raise AssertionError(f"Missing manager tenure metric {metric_name}")

    quality = DataQualityService().evaluate_fund(fund_code)
    if quality.get("status") != "complete":
        raise AssertionError(f"Expected complete quality status, got {quality}")
    if quality.get("score", 0) < 85:
        raise AssertionError(f"Expected high data quality score, got {quality}")
    if not quality.get("checks", {}).get("manager_tenure_start", {}).get("passed"):
        raise AssertionError(f"Expected manager tenure check to pass, got {quality}")

    cleanup_fund_codes([fund_code])
    print("OK manager tenure metrics and data quality evaluation")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
