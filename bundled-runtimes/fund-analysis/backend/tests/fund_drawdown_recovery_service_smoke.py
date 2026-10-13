import os
import sys
from datetime import date, timedelta

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from services.fund_drawdown_recovery_service import FundDrawdownRecoveryService


def series(values):
    start = date(2025, 1, 1)
    return [
        {"date": (start + timedelta(days=index)).isoformat(), "accum_nav": value, "nav": value}
        for index, value in enumerate(values)
    ]


def main():
    recovered = FundDrawdownRecoveryService.analyze(series([1.0, 1.1, 1.0, 0.88, 0.95, 1.1, 1.2]))
    assert recovered["status"] == "near_high"
    assert round(recovered["worst_drawdown"], 4) == -0.2
    assert recovered["worst_recovery_days"] == 2
    assert recovered["material_episode_count"] == 1
    assert recovered["recovered_material_episode_count"] == 1

    unrecovered = FundDrawdownRecoveryService.analyze(series([1.0, 1.1, 1.0, 0.9, 0.92]))
    assert unrecovered["status"] == "current_drawdown"
    assert round(unrecovered["current_drawdown"], 4) == round(0.92 / 1.1 - 1, 4)
    assert unrecovered["episodes"][0]["recovery_date"] is None
    assert unrecovered["included_in_score"] is False
    assert unrecovered["nav_basis"] == "accum_nav"

    adjusted = FundDrawdownRecoveryService.analyze([
        {"date": "2025-01-01", "unit_nav": 1.05, "nav": 1.05, "accum_nav": 1.05, "adj_nav": 1.05},
        {"date": "2025-01-02", "unit_nav": 1.00, "nav": 1.00, "accum_nav": 1.05, "adj_nav": 1.05},
        {"date": "2025-01-03", "unit_nav": 1.01, "nav": 1.01, "accum_nav": 1.06, "adj_nav": 1.0605},
    ])
    assert adjusted["nav_basis"] == "adj_nav", adjusted["nav_basis"]
    assert abs(adjusted["current_drawdown"] - (1.0605 / 1.0605 - 1)) < 1e-9, adjusted["current_drawdown"]
    print("fund drawdown recovery service smoke passed")


if __name__ == "__main__":
    main()
