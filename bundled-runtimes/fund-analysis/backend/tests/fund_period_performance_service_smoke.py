import os
import sys
from datetime import date, timedelta

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from services.fund_period_performance_service import FundPeriodPerformanceService


class _FundRepo:
    def get_fund(self, wind_code):
        return {"wind_code": wind_code, "name": "测试基金"}


class _NavRepo:
    def get_nav_series(self, wind_code, start_date=None, end_date=None):
        start = date(2024, 12, 20)
        end = date(2026, 8, 12)
        rows = []
        current = start
        while current <= end:
            if current <= date(2024, 12, 31):
                value = 1.0
            elif current <= date(2025, 12, 31):
                elapsed = (current - date(2025, 1, 1)).days
                value = 1.0 + 0.10 * elapsed / 364
            else:
                elapsed = (current - date(2026, 1, 1)).days
                total = (end - date(2026, 1, 1)).days
                value = 1.10 + 0.05 * elapsed / total
            rows.append({"date": current.isoformat(), "nav": value, "accum_nav": value})
            current += timedelta(days=1)
        return rows


class _ClassificationRepo:
    def get_classification_context(self, wind_code):
        return {
            "status": "resolved",
            "entity_id": "target-entity",
            "peer_group_id": "peer-test",
            "peer_group_name": "测试同类组",
            "minimum_peer_count": 3,
        }

    def list_peer_calendar_period_summaries(self, peer_group_id, start_date, end_date, baseline_start_date):
        peer_returns = [0.05, 0.08, 0.12]
        return [
            {
                "entity_id": f"peer-{index}",
                "wind_code": f"PEER{index}.OF",
                "nav_basis": "accum_nav",
                "baseline_date": start_date - timedelta(days=1),
                "baseline_nav": 1.0,
                "first_date": start_date,
                "first_nav": 1.0,
                "last_date": end_date,
                "last_nav": 1.0 + item_return,
                "observations": 252,
            }
            for index, item_return in enumerate(peer_returns, start=1)
        ]


def main():
    service = FundPeriodPerformanceService(
        nav_repo=_NavRepo(),
        fund_repo=_FundRepo(),
        classification_repo=_ClassificationRepo(),
    )
    result = service.get("TEST.OF", years=3)
    assert result["status"] == "available"
    assert result["nav_basis"] == "accum_nav"
    year_2025 = next(item for item in result["periods"] if item["year"] == 2025)
    assert year_2025["coverage_status"] == "complete"
    assert round(year_2025["return"], 6) == 0.1
    assert year_2025["rank"] == 2
    assert year_2025["peer_count"] == 4
    assert round(year_2025["peer_median_return"], 6) == 0.08
    assert year_2025["above_peer_median"] is True

    partial = FundPeriodPerformanceService._period_result(
        [
            {"date": date(2025, 7, 1), "nav": 1.0},
            {"date": date(2025, 12, 31), "nav": 1.1},
        ],
        date(2025, 1, 1),
        date(2025, 12, 31),
    )
    assert partial and partial["coverage_status"] == "partial"
    assert partial["return_basis"] == "since_inception_or_data_start"
    print("OK calendar-year returns and strict peer ranks use aligned real NAV periods")


if __name__ == "__main__":
    main()
