"""Index source and coverage tests; no network or database writes."""
import io
import json
import os
import sys
import unittest
from datetime import date, timedelta
from unittest.mock import Mock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from repositories.bond_duration_repo import BondDurationRepo
from services.chinabond_index_service import ChinaBondIndexService


class ChinaBondCoverageTest(unittest.TestCase):
    def inventory_rows(self):
        return [dict(series_key=d["series_key"], indicator=i, observations=500,
                     start_date="2024-01-01", end_date="2026-09-30")
                for d in ChinaBondIndexService.definitions() for i in ChinaBondIndexService.INDICATORS]

    def test_expected_pairs_and_freshness_not_aggregate_count(self):
        rows = self.inventory_rows()
        result = BondDurationRepo._inventory_from_rows(rows, date(2026, 10, 1))
        self.assertEqual(result["status"], "ready")
        self.assertEqual(result["ready_pairs"], 40)
        rows[0]["end_date"] = "2026-08-01"
        result = BondDurationRepo._inventory_from_rows(rows, date(2026, 10, 1))
        self.assertEqual(result["status"], "incomplete")
        self.assertEqual(result["ready_pairs"], 39)
        self.assertIn("2026-08-01", result["missing_items"][0])

    def test_wrong_series_cannot_replace_a_missing_required_series(self):
        rows = self.inventory_rows()
        rows[0]["series_key"] = "unrelated:01"
        result = BondDurationRepo._inventory_from_rows(rows, date(2026, 10, 1))
        self.assertEqual(result["status"], "incomplete")
        self.assertEqual(result["ready_pairs"], 39)
        self.assertIn("缺失", result["missing_items"][0])

    def test_empty_inventory_reports_all_requirements(self):
        result = BondDurationRepo._inventory_from_rows([])
        self.assertEqual(result["ready_pairs"], 0)
        self.assertEqual(len(result["missing_items"]), 40)

    def test_source_filters_invalid_future_and_nonfinite_values(self):
        raw = {"1704038400000": 100., "1704124800000": float("inf"),
               "1704211200000": 0, "1704297600000": -1,
               "1704384000000": float("nan"), "bad-date": 1., "4102444800000": 10.}
        payload = json.dumps({"CFZS_01": raw}).encode()
        service = ChinaBondIndexService(repo=Mock(), opener=lambda *a, **k: io.BytesIO(payload))
        self.assertEqual(service.fetch(service.definitions()[0], "wealth"), [{"trade_date": "2024-01-01", "value": 100.}])

    def test_all_invalid_source_points_raise_clear_error(self):
        payload = json.dumps({"CFZS_01": {"1704038400000": 0}}).encode()
        service = ChinaBondIndexService(repo=Mock(), opener=lambda *a, **k: io.BytesIO(payload))
        with self.assertRaisesRegex(ValueError, "没有有效观测"):
            service.fetch(service.definitions()[0], "wealth")

    def test_partial_sync_preserves_successes_and_reports_failed_pair(self):
        repo = Mock(upsert_index_points=Mock(return_value=1))
        service = ChinaBondIndexService(repo=repo)
        service.definitions = lambda: [ChinaBondIndexService.definitions()[0]]
        service.fetch = Mock(side_effect=[[{"trade_date": date.today().isoformat(), "value": 100.}], OSError("source unavailable")])
        result = service.sync()
        self.assertEqual(result["status"], "partial")
        self.assertEqual(result["records"], 1)
        self.assertEqual(result["requests"], 2)
        self.assertEqual(result["failures"][0]["indicator"], "duration")
        repo.upsert_index_points.assert_called_once()

    def test_out_of_window_data_never_reports_successful_sync(self):
        repo = Mock()
        service = ChinaBondIndexService(repo=repo)
        service.definitions = lambda: [ChinaBondIndexService.definitions()[0]]
        service.fetch = Mock(return_value=[{"trade_date": "2000-01-01", "value": 100.}])
        result = service.sync()
        self.assertEqual(result["status"], "partial")
        self.assertEqual(result["records"], 0)
        repo.upsert_index_points.assert_not_called()

    def test_ready_inventory_does_not_sync_again(self):
        repo = Mock(index_inventory=Mock(return_value={"status": "ready", "indicators": {"wealth": {"end_date": date.today().isoformat()}, "duration": {"end_date": date.today().isoformat()}}}))
        service = ChinaBondIndexService(repo=repo)
        service.sync = Mock()
        self.assertEqual(service.ensure_local_data()["status"], "ready")
        service.sync.assert_not_called()


if __name__ == "__main__":
    unittest.main()
