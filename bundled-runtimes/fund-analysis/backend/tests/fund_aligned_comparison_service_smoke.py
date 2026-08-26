from datetime import date, timedelta
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.fund_aligned_comparison_service import FundAlignedComparisonService


class NavRepo:
    def get_nav_series(self, wind_code, start_date=None, end_date=None):
        start = date(2025, 1, 2)
        rows = []
        for index in range(320):
            item_date = start + timedelta(days=index)
            if item_date.weekday() >= 5:
                continue
            if wind_code == "000002.OF" and index % 17 == 0:
                continue
            value = 1 + index * (0.0007 if wind_code == "000001.OF" else 0.0005)
            rows.append({
                "date": item_date.isoformat(),
                "nav": value,
                "accum_nav": value + 0.1,
            })
        return rows


def main():
    payload = FundAlignedComparisonService(
        nav_repo=NavRepo(),
        today=date(2025, 11, 30),
    ).build(["000001.OF", "000002.OF"])
    assert payload["status"] == "available"
    assert payload["methodology"] == "same_period_shared_nav_dates_v1"
    assert payload["windows"]["6m"]["status"] == "available"
    assert payload["windows"]["6m"]["ranking_eligible"] is True
    assert payload["windows"]["1y"]["status"] == "partial"
    assert payload["windows"]["1y"]["ranking_eligible"] is False
    assert "不输出领先排名" in payload["windows"]["1y"]["scope_note"]
    for window in ("6m", "1y"):
        result = payload["windows"][window]
        assert result["observations"] == len(result["chart"])
        assert 0 < result["calendar_coverage_ratio"] <= 1
        assert 0 < result["observation_coverage_ratio"] <= 1
        assert {item["observations"] for item in result["funds"]} == {result["observations"]}
        assert {item["nav_basis"] for item in result["funds"]} == {"accum_nav"}
        assert all(set(point["values"]) == {"000001.OF", "000002.OF"} for point in result["chart"])
        assert all(item["max_drawdown"] is not None for item in result["funds"])
        assert all(item["drawdown_status"] == "near_high" for item in result["funds"])
        assert all(item["current_drawdown"] == 0 for item in result["funds"])
        assert all(item["longest_underwater_days"] == 0 for item in result["funds"])
        assert "回撤和修复时间" in result["scope_note"]
    print("fund aligned comparison uses shared NAV dates for returns, risk and drawdown recovery")


if __name__ == "__main__":
    main()
