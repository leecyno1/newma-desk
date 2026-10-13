"""交易日历及风险采样：纯计算，不更新净值或历史评分。"""
import sys
import unittest
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import Mock, patch

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.fund_trading_calendar import fund_risk_calendar, get_trading_calendar, fetch_calendar_snapshot
from services.performance_nav_series import normalize_performance_rows, performance_evidence, daily_risk_rows
from services.metric_factory import MetricFactory
from services.fund_aligned_comparison_service import FundAlignedComparisonService
from services.rolling_metric_service import RollingMetricService


class TradingCalendarTests(unittest.TestCase):
    def setUp(self):
        self.calendar = get_trading_calendar()
        self.factory = MetricFactory()
        self.rows = [
            {"date": day, "adj_nav": 1 + index * 0.002 + (index % 3) * 0.001, "risk_calendar": "SSE"}
            for index, day in enumerate(sorted(self.calendar.open_days(date(2025, 9, 25), date(2025, 10, 15))))
        ]

    def evidence(self, rows):
        return performance_evidence(normalize_performance_rows(rows))

    def test_holidays_and_makeup_working_weekends_are_closed(self):
        self.assertEqual(self.calendar.open_days(date(2025, 10, 1), date(2025, 10, 8)), set())
        self.assertEqual(self.calendar.open_days(date(2025, 9, 28), date(2025, 9, 28)), set())
        self.assertEqual(self.calendar.open_days(date(2025, 1, 28), date(2025, 2, 4)), set())
        self.assertEqual(self.calendar.open_days(date(2025, 10, 9), date(2025, 10, 9)), {date(2025, 10, 9)})
        self.assertEqual(self.evidence(self.rows)["calendar_status"], "verified")
        self.assertIn("sharpe_ratio", self.factory.calculate_risk_metrics(self.rows))

    def test_absent_or_null_open_day_is_not_a_holiday(self):
        for replacement in ([], [{**self.rows[3], "adj_nav": None}]):
            rows = self.rows[:3] + replacement + self.rows[4:]
            self.assertEqual(self.evidence(rows)["missing_open_days"], 1)
            self.assertFalse(self.evidence(rows)["daily_risk_eligible"])
            self.assertNotIn("annualized_volatility", self.factory.calculate_risk_metrics(rows))

    def test_closed_day_disclosure_preserves_path_but_not_daily_risk(self):
        rows = self.rows + [{"date": date(2025, 10, 5), "adj_nav": 0.8, "risk_calendar": "SSE"}]
        evidence = self.evidence(rows)
        self.assertEqual(evidence["off_calendar_observations"], 1)
        self.assertEqual(evidence["risk_observations"], len(self.rows))
        self.assertTrue(evidence["daily_risk_eligible"])
        self.assertEqual(daily_risk_rows(normalize_performance_rows(rows)), normalize_performance_rows(self.rows))
        original, extra = (self.factory.calculate_risk_metrics(items) for items in (self.rows, rows))
        for metric in ("annualized_volatility", "sharpe_ratio", "sortino_ratio", "var_95", "cvar_95"):
            self.assertAlmostEqual(original[metric], extra[metric])
        self.assertLess(extra["max_drawdown"], -0.19)
        self.assertEqual(self.factory.calculate_return_metrics(rows)["observations"], len(rows))

    def test_relative_metrics_align_open_days_not_closed_disclosures(self):
        rows = self.rows + [{"date": date(2025, 10, 5), "adj_nav": 0.8, "risk_calendar": "SSE"}]
        benchmark = [{"date": row["date"], "nav": row["adj_nav"] * 100, "risk_calendar": "SSE"} for row in self.rows]
        self.assertAlmostEqual(self.factory.calculate_relative_metrics(rows, benchmark)["tracking_error"], 0, places=12)
        self.assertNotIn("tracking_error", self.factory.calculate_relative_metrics(rows, benchmark[:3] + benchmark[4:]))

    def test_missing_calendar_and_out_of_range_do_not_relax_thresholds(self):
        with patch("services.performance_nav_series.get_trading_calendar", return_value=None):
            self.assertEqual(self.evidence(self.rows)["calendar_status"], "unavailable")
            self.assertFalse(self.evidence(self.rows)["daily_risk_eligible"])
        rows = [{"date": date(2019, 12, 30) + timedelta(days=i), "adj_nav": 1, "risk_calendar": "SSE"} for i in range(2)]
        self.assertEqual(self.evidence(rows)["calendar_status"], "out_of_range")
        self.assertFalse(self.evidence(rows)["daily_risk_eligible"])

    def test_cross_market_unknown_and_mixed_calendars_are_not_verified(self):
        self.assertEqual(fund_risk_calendar({"type": "债券型", "name": "国内债券"}), "SSE")
        for fund in ({"type": "QDII", "name": "海外债券"}, {"type": "债券型", "name": "全球债券"},
                     {"type": "指数型", "name": "沪港深指数"}, {"name": "未知"}):
            self.assertIsNone(fund_risk_calendar(fund))
        unknown = [{**row, "risk_calendar": None} for row in self.rows]
        self.assertFalse(self.evidence(unknown)["daily_risk_eligible"])
        mixed = self.rows[:-1] + [{**self.rows[-1], "risk_calendar": None}]
        self.assertEqual(self.evidence(mixed)["calendar_status"], "mixed_or_unsupported")

    def test_rolling_carries_calendar_and_sample_evidence(self):
        records = RollingMetricService(windows={"sample": len(self.rows)}).calculate_for_nav_series(self.rows, "fund", "X")
        self.assertTrue(records)
        self.assertTrue(all(record["details"]["calendar_status"] == "verified" for record in records))
        self.assertTrue(all(record["details"]["risk_sampling"] == "exchange_open_days" for record in records))

    def test_comparison_keeps_risk_when_only_closed_disclosures_differ(self):
        rows = [{"date": day, "adj_nav": 1 + i * 0.0002 + (i % 3) * 0.0001, "risk_calendar": "SSE"}
                for i, day in enumerate(sorted(self.calendar.open_days(date(2024, 1, 2), date(2025, 10, 15))))]
        repo = Mock()
        repo.get_nav_series.side_effect = lambda code, *args: rows + (
            [{"date": date(2025, 6, 1), "adj_nav": 1.05, "risk_calendar": "SSE"}] if code == "A" else [])
        result = FundAlignedComparisonService(nav_repo=repo, today=date(2025, 10, 15)).build(["A", "B"])
        for fund in result["windows"]["1y"]["funds"]:
            self.assertTrue(fund["methodology"]["daily_risk_eligible"])
            self.assertIsNotNone(fund["annualized_volatility"])

    def test_source_empty_truncated_or_conflicting_cannot_build_snapshot(self):
        days = [{"exchange": "SSE", "cal_date": day.strftime("%Y%m%d"), "is_open": int(day.weekday() < 5)}
                for day in (date(2025, 1, 1) + timedelta(days=i) for i in range(365))]
        for data in ([], days[:-1], days + [{**days[0], "is_open": 1 - days[0]["is_open"]}]):
            pro = Mock()
            pro.trade_cal.return_value = pd.DataFrame(data)
            with self.assertRaises(ValueError):
                fetch_calendar_snapshot(pro, 2025, 2025)


if __name__ == "__main__":
    unittest.main()
