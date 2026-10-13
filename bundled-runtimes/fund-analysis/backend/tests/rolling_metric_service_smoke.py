import os
import sys
from datetime import date
from decimal import Decimal
from unittest.mock import Mock, patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from services.rolling_metric_service import RollingMetricService
from services.fund_trading_calendar import get_trading_calendar


def _build_nav_series(start: date, days: int) -> list[dict]:
    nav = Decimal("1.0000")
    series = []
    calendar_days = sorted(get_trading_calendar().open_days(start, date(2026, 10, 2)))[:days]
    for offset, trade_date in enumerate(calendar_days):
        daily_change = Decimal("0.0008") if offset % 17 else Decimal("-0.0040")
        nav = max(Decimal("0.7000"), nav * (Decimal("1") + daily_change))
        series.append({
            "date": trade_date.isoformat(),
            "nav": float(nav),
            "accum_nav": float(nav),
            "adj_nav": float(nav),
            "risk_calendar": 'SSE',
        })
    return series


def main() -> int:
    fund_code = "ROLLING.TEST"
    nav_repo = Mock(get_nav_series=Mock(return_value=_build_nav_series(date(2023, 1, 1), 900)))
    panel = []
    def store(**record):
        stored = {**record, "metric_window": record["window"]}
        panel.append(stored)
        return stored
    metric_repo = Mock(upsert_metrics=lambda records: [store(**record) for record in records])

    service = RollingMetricService(
        windows={"3m": 63, "6m": 126, "1y": 252, "3y": 756},
        min_observation_ratio=0.75,
    )
    with patch('repositories.get_nav_repo', return_value=nav_repo), \
         patch('repositories.get_metric_snapshot_repo', return_value=metric_repo), \
         patch('repositories.get_research_profile_repo', return_value=Mock(get_profile=Mock(return_value={}))), \
         patch('repositories.get_fund_classification_repo', return_value=Mock(get_classification_context=Mock(return_value={}))):
        result = service.calculate_and_save_for_fund(
            fund_code,
            peer_group_key="主动权益-滚动测试",
            benchmark_code="沪深300",
        )

    if result["saved"] <= 0:
        raise AssertionError(f"Expected saved rolling metrics, got {result}")

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

    print("OK rolling metric service generates multi-window persistence records in isolated repositories")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
