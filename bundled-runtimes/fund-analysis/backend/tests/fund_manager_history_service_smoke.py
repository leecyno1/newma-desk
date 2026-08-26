import os
import sys
from datetime import date

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from services.fund_manager_history_service import FundManagerHistoryService


class FakeFundRepo:
    def get_fund(self, _wind_code):
        return {"wind_code": "000001.OF", "name": "示例基金A"}


class FakeManagerRepo:
    def list_fund_manager_history(self, _wind_code):
        common = {
            "entity_id": "entity-1",
            "canonical_code": "000001.OF",
            "canonical_name": "示例基金",
            "source": "tushare.fund_manager",
            "record_updated_at": "2026-08-14",
        }
        return [
            {**common, "manager_id": "m1", "manager_name": "甲经理", "fund_code": "000001.OF", "start_date": "2020-01-01", "end_date": "2022-12-31", "is_current": False},
            {**common, "manager_id": "m1", "manager_name": "甲经理", "fund_code": "000002.OF", "start_date": "2020-01-01", "end_date": "2022-12-31", "is_current": False},
            {**common, "manager_id": "m1", "manager_name": "甲经理", "fund_code": "000001.OF", "start_date": "2023-01-01", "end_date": "2024-06-30", "is_current": False},
            {**common, "manager_id": "m2", "manager_name": "乙经理", "fund_code": "000001.OF", "start_date": "2024-06-01", "end_date": None, "is_current": True},
            {**common, "manager_id": "m2", "manager_name": "乙经理", "fund_code": "000002.OF", "start_date": "2024-06-01", "end_date": None, "is_current": True},
            {**common, "manager_id": "m3", "manager_name": "丙经理", "fund_code": "000001.OF", "start_date": "2025-01-01", "end_date": None, "is_current": True},
        ]


def main():
    service = FundManagerHistoryService(FakeManagerRepo(), FakeFundRepo(), today=date(2026, 8, 14))
    result = service.get("000001.OF")
    assert result["status"] == "available"
    assert result["summary"]["manager_count"] == 3
    assert result["summary"]["current_manager_count"] == 2
    assert result["summary"]["team_mode"] == "co_managed"
    assert len(result["tenures"]) == 3
    first_manager = next(item for item in result["tenures"] if item["manager_id"] == "m1")
    assert first_manager["start_date"] == "2020-01-01"
    assert first_manager["end_date"] == "2024-06-30"
    assert first_manager["share_codes"] == ["000001.OF", "000002.OF"]
    stability = result["stability_evidence"]
    assert stability["status"] == "observation_period"
    assert stability["current_manager_count"] == 2
    assert stability["changes_last_three_years"] == 3
    assert stability["included_in_score"] is False
    print("fund manager history service smoke passed")


if __name__ == "__main__":
    main()
