import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from services.fund_scale_trend_service import FundScaleTrendService


def rows(values):
    return [
        {"report_date": date, "net_asset_yi": asset}
        for date, asset in values
    ]


def main():
    stable = FundScaleTrendService.analyze(rows([
        ("2026-06-30", 7.24), ("2026-03-31", 6.98), ("2025-12-31", 7.11),
        ("2025-09-30", 7.31), ("2025-06-30", 7.31),
    ]))
    assert stable["status"] == "stable"
    assert round(stable["one_year_change"], 4) == -0.0096
    assert stable["included_in_score"] is False

    shrinking = FundScaleTrendService.analyze(rows([
        ("2026-06-30", 4.0), ("2026-03-31", 4.5), ("2025-12-31", 5.0),
        ("2025-09-30", 6.0), ("2025-06-30", 10.0),
    ]))
    assert shrinking["status"] == "shrinking"
    assert shrinking["one_year_change"] == -0.6

    small = FundScaleTrendService.analyze(rows([
        ("2026-06-30", 0.75), ("2026-03-31", 0.90), ("2025-06-30", 2.0),
    ]))
    assert small["status"] == "small_scale"
    assert "低于 2 亿元" in small["note"]

    recovering = FundScaleTrendService.analyze(rows([
        ("2026-06-30", 8.0), ("2026-03-31", 6.0), ("2025-06-30", 4.0),
        ("2024-06-30", 20.0),
    ]))
    assert recovering["status"] == "recovering"
    assert "仍明显低于" in recovering["note"]
    print("fund scale trend service smoke passed")


if __name__ == "__main__":
    main()
