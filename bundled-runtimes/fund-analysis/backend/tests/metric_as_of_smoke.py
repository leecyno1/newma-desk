import os
import sys
import unittest
from datetime import date, datetime, timedelta
from unittest.mock import Mock, patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import repositories
from services.metric_factory import MetricFactory
from services.rolling_metric_service import RollingMetricService
from services.manager_tenure_metric_service import ManagerTenureMetricService


class MetricAsOfTests(unittest.TestCase):
    def setUp(self):
        self.cutoff = date(2026, 6, 1)
        self.history = [
            {"date": self.cutoff - timedelta(days=19 - i), "nav": 1 + i * 0.001, "benchmark_nav": 1 + i * 0.0005}
            for i in range(20)
        ]
        self.future = [
            {"date": self.cutoff + timedelta(days=i + 1), "nav": 1.2, "benchmark_nav": 1.1}
            for i in range(20)
        ]
        self.factory = MetricFactory()
        self.rolling = RollingMetricService(windows={"20d": 20})

    def build_records(self, rows, benchmark_rows):
        return self.factory.build_metric_records(
            "fund", "ASOF.TEST", self.cutoff, rows,
            benchmark_series=benchmark_rows, benchmark_code="000300.SH", window="20d",
        )

    def rolling_records(self, rows, cutoff):
        return self.rolling.calculate_for_nav_series(
            rows, "fund", "ASOF.TEST", benchmark_code="000300.SH", as_of_date=cutoff,
        )

    def test_factory_records_ignore_future_fund_and_benchmark_data(self):
        benchmark = [{"date": row["date"], "nav": row["benchmark_nav"]} for row in self.history]
        future_benchmark = [{"date": row["date"], "nav": row["benchmark_nav"]} for row in self.future]
        expected = self.build_records(self.history, benchmark)
        actual = self.build_records(self.history + self.future, benchmark + future_benchmark)
        self.assertEqual(actual, expected)
        values = {row["metric_name"]: float(row["metric_value"]) for row in actual}
        self.assertAlmostEqual(values["total_return"], 0.019)
        self.assertAlmostEqual(values["benchmark_return"], 0.0095)
        self.assertEqual(values["observations"], 20)

    def test_rolling_windows_ignore_future_data_before_slicing(self):
        expected = self.rolling_records(self.history, self.cutoff)
        actual = self.rolling_records(self.history + self.future, self.cutoff)
        self.assertEqual(actual, expected)
        self.assertTrue(actual)
        self.assertTrue(all(row["details"]["window_end_date"] <= self.cutoff for row in actual))

    def test_future_rows_cannot_satisfy_minimum_observations(self):
        self.assertEqual(self.rolling_records(self.history[:1] + self.future, self.cutoff), [])

    def test_no_historical_observations_produce_no_records(self):
        self.assertEqual(self.build_records(self.future, self.future), [])
        self.assertEqual(self.rolling_records(self.future, self.cutoff), [])

    def test_cutoff_is_inclusive_with_supported_date_shapes(self):
        expected = self.rolling_records(self.history, self.cutoff)
        for shape in (lambda value: value, lambda value: value.isoformat(), lambda value: datetime.combine(value, datetime.min.time())):
            with self.subTest(shape=shape):
                rows = [{"trade_date": shape(row["date"]), "nav": row["nav"], "benchmark_nav": row["benchmark_nav"]} for row in self.history + self.future]
                self.assertEqual(self.rolling_records(rows, self.cutoff), expected)

    def test_default_cutoff_still_uses_latest_observation(self):
        rows = self.history + self.future
        actual = self.rolling_records(rows, None)
        self.assertTrue(actual)
        self.assertTrue(all(row["as_of_date"] == self.future[-1]["date"] for row in actual))
        self.assertTrue(all(row["details"]["window_end_date"] == self.future[-1]["date"] for row in actual))

    def test_factory_persistence_queries_and_saves_only_history(self):
        nav_repo = Mock()
        nav_repo.get_nav_series.return_value = self.history + self.future
        metric_repo = Mock()
        metric_repo.upsert_metrics.side_effect = lambda records: records
        with (
            patch.object(repositories, "get_nav_repo", return_value=nav_repo),
            patch.object(repositories, "get_metric_snapshot_repo", return_value=metric_repo),
        ):
            result = self.factory.calculate_and_save_fund_metrics("ASOF.TEST", as_of_date=self.cutoff)
        values = {row["metric_name"]: float(row["metric_value"]) for row in result["metrics"]}
        self.assertAlmostEqual(values["total_return"], 0.019)
        nav_repo.get_nav_series.assert_called_once_with("ASOF.TEST", end_date=self.cutoff.isoformat())
        metric_repo.upsert_metrics.assert_called_once()
        metric_repo.upsert_metric.assert_not_called()

    def test_factory_persistence_skips_empty_usable_history(self):
        for rows in (self.future, [{"date": self.cutoff, "nav": None}]):
            with self.subTest(rows=rows):
                metric_repo = Mock()
                nav_repo = Mock()
                nav_repo.get_nav_series.return_value = rows
                with (
                    patch.object(repositories, "get_nav_repo", return_value=nav_repo),
                    patch.object(repositories, "get_metric_snapshot_repo", return_value=metric_repo),
                ):
                    result = self.factory.calculate_and_save_fund_metrics("ASOF.TEST", as_of_date=self.cutoff)
                self.assertEqual(result["saved"], 0)
                metric_repo.upsert_metric.assert_not_called()
                metric_repo.upsert_metrics.assert_not_called()

    def test_rolling_persistence_limits_database_query(self):
        nav_repo = Mock()
        nav_repo.get_nav_series.return_value = self.history + self.future
        metric_repo = Mock()
        metric_repo.upsert_metrics.side_effect = lambda records: records
        profile_repo = Mock()
        profile_repo.get_profile.return_value = None
        classification_repo = Mock()
        classification_repo.get_classification_context.return_value = {}
        with (
            patch.object(repositories, "get_nav_repo", return_value=nav_repo),
            patch.object(repositories, "get_metric_snapshot_repo", return_value=metric_repo),
            patch.object(repositories, "get_research_profile_repo", return_value=profile_repo),
            patch.object(repositories, "get_fund_classification_repo", return_value=classification_repo),
        ):
            result = self.rolling.calculate_and_save_for_fund("ASOF.TEST", as_of_date=self.cutoff, benchmark_code="000300.SH")
        nav_repo.get_nav_series.assert_called_once_with("ASOF.TEST", end_date=self.cutoff.isoformat())
        self.assertTrue(result["metrics"])
        self.assertTrue(all(row["details"]["window_end_date"] <= self.cutoff for row in result["metrics"]))
        metric_repo.upsert_metrics.assert_called_once()
        metric_repo.upsert_metric.assert_not_called()

    def test_manager_tenure_saves_complete_panel_in_one_batch(self):
        nav_repo = Mock()
        nav_repo.get_nav_series.return_value = self.history
        metric_repo = Mock()
        metric_repo.upsert_metrics.side_effect = lambda records: records
        factory = Mock()
        factory._normalize_nav_series.side_effect = self.factory._normalize_nav_series
        factory.build_metric_records.return_value = [{
            "target_type": "fund", "target_id": "ASOF.TEST", "as_of_date": self.cutoff,
            "metric_name": name, "metric_value": value, "metric_unit": "ratio",
            "window": "manager_tenure", "details": {"methodology_version": "test_method"},
        } for name, value in (("total_return", 0.019), ("max_drawdown", 0))]
        classification_repo = Mock()
        classification_repo.get_classification_context.return_value = {"peer_group_key": "test_peer"}
        profile_repo = Mock()
        profile_repo.get_profile.return_value = {}
        service = ManagerTenureMetricService(factory, Mock(), classification_repo)
        tenure_start = self.history[0]["date"]
        with (
            patch.object(repositories, "get_fund_repo", return_value=Mock()),
            patch.object(repositories, "get_research_profile_repo", return_value=profile_repo),
            patch.object(repositories, "get_nav_repo", return_value=nav_repo),
            patch.object(repositories, "get_metric_snapshot_repo", return_value=metric_repo),
            patch("services.manager_tenure_metric_service.resolve_manager_tenure_context",
                  return_value={"start_date": tenure_start, "source": "test_tenure"}),
        ):
            result = service.calculate_and_save_for_fund("ASOF.TEST")
        metric_repo.upsert_metrics.assert_called_once()
        metric_repo.upsert_metric.assert_not_called()
        nav_repo.get_nav_series.assert_called_once_with("ASOF.TEST", start_date=tenure_start.isoformat())
        self.assertEqual(result["saved"], 5)
        panel = metric_repo.upsert_metrics.call_args.args[0]
        self.assertEqual({row["metric_name"] for row in panel}, {
            "total_return", "max_drawdown", "tenure_days", "metric_coverage_days", "tenure_coverage_ratio",
        })
        self.assertTrue(all(row["peer_group_key"] == "test_peer" for row in panel))
        self.assertTrue(all(row["details"]["manager_tenure_source"] == "test_tenure" for row in panel))


if __name__ == "__main__":
    unittest.main()
