import os
import sys
import atexit
from datetime import date, timedelta
from decimal import Decimal

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from database import init_database
from repositories import get_metric_snapshot_repo, get_nav_repo
from services.rolling_metric_service import RollingMetricService
from smoke_cleanup import cleanup_fund_codes


def _build_nav_series(start: date, days: int) -> list[dict]:
    nav = Decimal("1.0000")
    series = []
    for offset in range(days):
        trade_date = start + timedelta(days=offset)
        daily_change = Decimal("0.0008") if offset % 17 else Decimal("-0.0040")
        nav = max(Decimal("0.7000"), nav * (Decimal("1") + daily_change))
        series.append({
            "date": trade_date.isoformat(),
            "nav": float(nav),
            "accum_nav": float(nav),
        })
    return series


def main() -> int:
    init_database()

    fund_code = "ROLLING.TEST"
    cleanup_fund_codes([fund_code])
    atexit.register(cleanup_fund_codes, [fund_code])
    nav_repo = get_nav_repo()
    metric_repo = get_metric_snapshot_repo()

    nav_repo.delete_nav(fund_code)
    nav_repo.upsert_nav_series(fund_code, _build_nav_series(date(2023, 1, 1), 900))

    service = RollingMetricService(
        windows={"3m": 63, "6m": 126, "1y": 252, "3y": 756},
        min_observation_ratio=0.75,
    )
    result = service.calculate_and_save_for_fund(
        fund_code,
        peer_group_key="主动权益-滚动测试",
        benchmark_code="沪深300",
    )

    if result["saved"] <= 0:
        raise AssertionError(f"Expected saved rolling metrics, got {result}")

    panel = metric_repo.get_latest_panel("fund", fund_code)
    windows = {item.get("metric_window") for item in panel}
    for expected_window in {"3m", "6m", "1y", "3y"}:
        if expected_window not in windows:
            raise AssertionError(f"Missing window {expected_window}, got {windows}")

    by_window = {}
    for item in panel:
        by_window.setdefault(item.get("metric_window"), set()).add(item.get("metric_name"))

    required_metrics = {
        "total_return",
        "annualized_return",
        "max_drawdown",
        "annualized_volatility",
        "positive_return_ratio",
        "sortino_ratio",
        "calmar_ratio",
    }
    missing = {
        window: sorted(required_metrics - names)
        for window, names in by_window.items()
        if window in {"3m", "6m", "1y", "3y"} and required_metrics - names
    }
    if missing:
        raise AssertionError(f"Missing rolling metrics: {missing}")

    if not all(item.get("peer_group_key") == "主动权益-滚动测试" for item in panel if item.get("metric_window") in {"3m", "6m", "1y", "3y"}):
        raise AssertionError("Expected peer_group_key to be persisted on rolling metrics")

    cleanup_fund_codes([fund_code])
    print("OK rolling metric service persisted multi-window metrics")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
