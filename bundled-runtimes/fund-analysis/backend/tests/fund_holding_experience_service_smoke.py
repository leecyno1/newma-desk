from datetime import date, timedelta
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from services.fund_holding_experience_service import FundHoldingExperienceService


class NavRepo:
    def get_nav_series(self, _wind_code):
        start = date(2024, 1, 1)
        return [
            {
                "date": (start + timedelta(days=index)).isoformat(),
                "nav": 1.0,
                "accum_nav": 1.0 + index * 0.001,
            }
            for index in range(760)
        ]


def main():
    result = FundHoldingExperienceService(NavRepo()).analyze("000001.OF")
    assert result["status"] == "available", result
    assert result["nav_basis"] == "accum_nav_preferred", result
    assert [item["months"] for item in result["periods"]] == [1, 3, 6, 12]
    assert all(item["positive_probability"] == 1 for item in result["periods"]), result
    assert all(item["sample_count"] >= 20 for item in result["periods"]), result
    for period in result["periods"]:
        target_probabilities = period["return_threshold_probabilities"]
        assert [item["threshold"] for item in target_probabilities] == [0, 0.01, 0.02, 0.03, 0.04, 0.05]
        assert target_probabilities[0]["probability"] == period["positive_probability"]
        probabilities = [item["probability"] for item in target_probabilities]
        assert probabilities == sorted(probabilities, reverse=True), period
    assert FundHoldingExperienceService._add_months(date(2025, 1, 31), 1) == date(2025, 2, 28)
    print("OK holding experience includes accumulated NAV, calendar periods and return target probabilities")


if __name__ == "__main__":
    main()
