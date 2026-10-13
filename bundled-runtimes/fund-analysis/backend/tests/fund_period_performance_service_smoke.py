import os
import sys
from datetime import date, timedelta

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from services.fund_period_performance_service import FundPeriodPerformanceService
from services.fund_trading_calendar import get_trading_calendar


class _FundRepo:
    def get_fund(self, wind_code):
        return {"wind_code": wind_code, "name": "测试基金", "type": "债券型"}


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
            rows.append({"date": current.isoformat(), "nav": value, "accum_nav": value, "adj_nav": value, "risk_calendar": "SSE"})
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
                "nav_basis": "adj_nav", "risk_calendar": "SSE",
                "baseline_date": start_date - timedelta(days=1),
                "baseline_nav": 1.0,
                "first_date": start_date,
                "first_nav": 1.0,
                "last_date": end_date,
                "last_nav": 1.0 + item_return,
                "last_record_date": end_date, "last_record_nav": 1.0 + item_return,
                "observations": len(get_trading_calendar().open_days(start_date, end_date)),
                "valid_dates": sorted(get_trading_calendar().open_days(start_date, end_date)),
                "missing_observations": 0,
            }
            for index, item_return in enumerate(peer_returns, start=1)
        ]


class _AdjNavRepo:
    """单位净值全年持平（收益全分红），累计净值线性加回 10%，复权净值按再投资增长 15%"""

    def get_nav_series(self, wind_code, start_date=None, end_date=None):
        start = date(2024, 12, 20)
        end = date(2026, 8, 12)
        rows = []
        current = start
        while current <= end:
            if current <= date(2024, 12, 31):
                unit = accum = adj = 1.0
            elif current <= date(2025, 12, 31):
                elapsed = (current - date(2025, 1, 1)).days
                unit = 1.0
                accum = 1.0 + 0.10 * elapsed / 364
                adj = 1.0 + 0.15 * elapsed / 364
            else:
                elapsed = (current - date(2026, 1, 1)).days
                total = (end - date(2026, 1, 1)).days
                unit = 1.0
                accum = 1.10 + 0.05 * elapsed / total
                adj = 1.15 + 0.05 * elapsed / total
            rows.append({"date": current.isoformat(), "nav": unit, "accum_nav": accum, "adj_nav": adj})
            current += timedelta(days=1)
        return rows


def main():
    service = FundPeriodPerformanceService(
        nav_repo=_NavRepo(),
        fund_repo=_FundRepo(),
        classification_repo=_ClassificationRepo(),
        today=date(2026, 8, 12),
    )
    result = service.get("TEST.OF", years=3)
    assert result["status"] == "available"
    assert result["nav_basis"] == "adj_nav"
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
    assert partial["return_basis"] == "visible_period_only"

    adj_service = FundPeriodPerformanceService(
        nav_repo=_AdjNavRepo(),
        fund_repo=_FundRepo(),
        classification_repo=_ClassificationRepo(),
        today=date(2026, 8, 12),
    )
    adj_result = adj_service.get("TEST.OF", years=3)
    assert adj_result["status"] == "available"
    assert adj_result["nav_basis"] == "adj_nav", f"adj-populated rows must use adj_nav basis, got {adj_result['nav_basis']}"
    adj_2025 = next(item for item in adj_result["periods"] if item["year"] == 2025)
    assert round(adj_2025["return"], 6) == 0.15, f"2025 return must come from adj_nav (reinvested), got {adj_2025['return']}"
    assert adj_2025["rank"] == 1

    sparse_rows = [dict(row, adj_nav=None) for row in _NavRepo().get_nav_series("TEST.OF")]
    sparse_rows[0]["adj_nav"] = sparse_rows[0]["accum_nav"]
    sparse_rows[1]["adj_nav"] = sparse_rows[1]["accum_nav"]
    sparse_points, sparse_basis = FundPeriodPerformanceService._points(sparse_rows)
    assert sparse_basis == "adj_nav"
    assert sum(row['nav'] is not None for row in sparse_points) == 2
    assert len(sparse_points) == len(sparse_rows), "known missing dates must remain explicit"
    print("OK calendar-year returns and strict peer ranks use aligned real NAV periods")


if __name__ == "__main__":
    main()
