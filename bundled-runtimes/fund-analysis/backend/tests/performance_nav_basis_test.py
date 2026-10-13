"""净值口径回归：纯计算和隔离仓储，不写业务数据库。"""
import sys
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import repositories
from services.fund_aligned_comparison_service import FundAlignedComparisonService
from services.fund_manager_career_service import FundManagerCareerService
from services.fund_manager_comparison_service import FundManagerComparisonService
from services.metric_factory import MetricFactory
from services.performance_nav_series import METHODOLOGY_VERSION, normalize_performance_rows
from services.rolling_metric_service import RollingMetricService
from fund_manager_career_service_smoke import service as career_service
from fund_manager_comparison_service_smoke import service as comparison_service, CATEGORY
from services.manager_tenure_peer_ranking_service import ManagerTenurePeerRankingService


class PerformanceNavBasisTests(unittest.TestCase):
    def setUp(self):
        self.factory = MetricFactory()
        self.rows = [
            {"date": "2026-09-01", "unit_nav": 1.0, "accum_nav": 2.0, "adj_nav": 1.0},
            {"date": "2026-09-02", "unit_nav": 0.94, "accum_nav": 2.04, "adj_nav": 1.04},
            {"date": "2026-09-03", "unit_nav": 0.95, "accum_nav": 2.05, "adj_nav": 1.05},
        ]

    def test_dividend_uses_adjusted_not_cumulative_or_unit_nav(self):
        result = self.factory.calculate_return_metrics(self.rows)
        self.assertAlmostEqual(result["total_return"], 0.05)
        self.assertEqual(result["start_nav"], 1.0)

    def test_missing_adjusted_does_not_borrow_another_field(self):
        self.rows[1]["adj_nav"] = None
        normalized = normalize_performance_rows(self.rows)
        self.assertIsNone(normalized[1]["nav"])
        returns = self.factory._daily_returns([(row["date"], row["nav"]) for row in normalized])
        self.assertEqual(returns, [])
        self.assertNotIn("annualized_volatility", self.factory.calculate_risk_metrics(self.rows))
        self.assertEqual(self.factory.build_metric_records("fund", "X", date(2026, 9, 3), self.rows), [])

    def test_cumulative_only_is_not_total_return_evidence(self):
        for row in self.rows:
            row.pop("adj_nav")
        self.assertEqual(self.factory.calculate_return_metrics(self.rows), {})
        self.assertEqual(FundManagerCareerService._normalize_rows(self.rows), [])
        self.assertEqual(FundManagerComparisonService._points(self.rows), {})

    def test_raw_and_generic_rows_never_mix_fields(self):
        self.rows[1] = {"date": "2026-09-02", "nav": 50}
        self.assertIsNone(normalize_performance_rows(self.rows)[1]["nav"])

    def test_nonfinite_nonpositive_and_duplicate_revision(self):
        for value in (float("nan"), float("inf"), 0, -1):
            with self.subTest(value=value):
                rows = self.rows + [{**self.rows[-1], "adj_nav": value}]
                normalized = normalize_performance_rows(rows)
                self.assertEqual(len(normalized), 3)
                self.assertIsNone(normalized[-1]["nav"])

    def test_generic_benchmark_series_remains_supported(self):
        points = self.factory._normalize_nav_series([{"date": "2026-09-01", "nav": 100}, {"date": "2026-09-02", "nav": 101}])
        self.assertEqual([value for _, value in points], [100, 101])

    def test_future_schema_cannot_change_historical_basis(self):
        rows = [{"date": "2026-09-01", "nav": 1}, {"date": "2026-09-02", "nav": 1.01},
                {"date": "2026-09-03", "adj_nav": 2}]
        records = self.factory.build_metric_records("fund", "X", date(2026, 9, 2), rows)
        self.assertAlmostEqual(float(next(row["metric_value"] for row in records if row["metric_name"] == "total_return")), 0.01)

    def test_return_annualization_uses_actual_dates_not_observation_count(self):
        result = self.factory.calculate_return_metrics([{"date": "2024-01-01", "nav": 1}, {"date": "2025-01-01", "nav": 1.1}])
        self.assertAlmostEqual(result["annualized_return"], 1.1 ** (365.25 / 366) - 1)

    def test_sparse_monthly_nav_does_not_fabricate_daily_risk(self):
        rows = [{"date": "2026-01-30", "adj_nav": 1}, {"date": "2026-02-27", "adj_nav": 1.02}, {"date": "2026-03-31", "adj_nav": 1.01}]
        risk = self.factory.calculate_risk_metrics(rows)
        self.assertAlmostEqual(risk["max_drawdown"], 1.01 / 1.02 - 1)
        self.assertNotIn("sharpe_ratio", risk)
        self.assertNotIn("var_95", risk)

    def test_manager_and_fund_comparison_use_identical_adjusted_points(self):
        career = FundManagerCareerService._normalize_rows(self.rows)
        manager = FundManagerComparisonService._points(self.rows)
        aligned, basis = FundAlignedComparisonService._normalize_series(self.rows)
        self.assertEqual([row["nav"] for row in career], [value for _, value in aligned])
        self.assertEqual(manager, dict(aligned))
        self.assertEqual(basis, "adj_nav")

    def test_rolling_retains_gaps_and_metadata(self):
        rolling = RollingMetricService(windows={"3d": 3})
        records = rolling.calculate_for_nav_series(self.rows, "fund", "X")
        self.assertTrue(records)
        self.assertTrue(all(row["details"]["methodology_version"] == METHODOLOGY_VERSION for row in records))
        self.assertTrue(all(row["details"]["nav_basis"] == "adj_nav" for row in records))
        self.rows[1]["adj_nav"] = None
        self.assertEqual(rolling.calculate_for_nav_series(self.rows, "fund", "X"), [])

    def test_benchmark_date_intersection_does_not_fabricate_daily_tracking_error(self):
        benchmark = [{"date": self.rows[0]["date"], "nav": 100}, {"date": self.rows[2]["date"], "nav": 101}]
        relative = self.factory.calculate_relative_metrics(self.rows, benchmark)
        self.assertAlmostEqual(relative["excess_return"], 0.04)
        self.assertNotIn("tracking_error", relative)
        self.assertEqual(self.factory.build_metric_records("fund", "X", date(2026, 9, 3), self.rows,
                                                          benchmark_series=benchmark, benchmark_code="B"), [])

    def test_persistence_keeps_calculation_version_without_retagging_old_metrics(self):
        nav_repo, metric_repo = Mock(), Mock()
        nav_repo.get_nav_series.return_value = self.rows
        metric_repo.upsert_metrics.side_effect = lambda records: records
        with patch.object(repositories, "get_nav_repo", return_value=nav_repo), patch.object(repositories, "get_metric_snapshot_repo", return_value=metric_repo):
            result = self.factory.calculate_and_save_fund_metrics("X")
        self.assertGreater(result["saved"], 0)
        self.assertTrue(all(row["details"]["nav_basis"] == "adj_nav" for row in result["metrics"]))
        metric_repo.get_latest_panel.assert_not_called()

    def test_career_gap_survives_chart_normalization(self):
        service = career_service(benchmark=False)
        rows = [dict(row, date=row["date"].replace("09-", "01-")) for row in self.rows]
        rows[1]["adj_nav"] = None
        service._nav_repo = Mock()
        service._nav_repo.get_nav_series.return_value = rows
        result = service.build("manager", period="ytd")
        self.assertAlmostEqual(result["metrics"]["total_return"], 0.05)
        self.assertNotIn("sharpe_ratio", result["metrics"])
        self.assertEqual(result["evidence"]["missing_observations"], 1)
        self.assertEqual(result["evidence"]["nav_basis"], "adj_nav")

    def test_comparison_does_not_erase_a_gap_shared_by_both_managers(self):
        service = comparison_service()
        for rows in service._nav_repo.rows.values():
            for index, row in enumerate(rows):
                row["unit_nav"] = 0.5
                row["accum_nav"] = 10.0
                row["adj_nav"] = None if index == 5 else row["nav"]
        result = service.build(["manager-1", "manager-2"], category=CATEGORY)
        self.assertEqual(result["common_period"]["status"], "available")
        self.assertNotIn("sharpe_ratio", result["common_period"]["leaders"])
        for metrics in result["common_period"]["metrics"].values():
            self.assertNotIn("annualized_volatility", metrics)
            self.assertFalse(metrics["methodology"]["daily_risk_eligible"])
            self.assertEqual(metrics["methodology"]["nav_basis"], "adj_nav")

    def test_peer_rank_annualization_uses_same_calendar_span(self):
        self.assertAlmostEqual(ManagerTenurePeerRankingService._annualized_return(0.1, 366), 1.1 ** (365.25 / 366) - 1)


if __name__ == "__main__":
    unittest.main()
