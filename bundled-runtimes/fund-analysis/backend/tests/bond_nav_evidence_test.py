"""Isolated bond calculations: no database, synchronization or model calls."""
import os
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import Mock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import numpy as np
import pandas as pd

from services.fund_bond_anomaly_service import FundBondAnomalyService
from services.fund_bond_duration_service import FundBondDurationService
from services.bond_nav_series import returns_at_endpoints, weekly_endpoints
from services.chinabond_index_service import ChinaBondIndexService


def rows(count=100):
    return [dict(date=d, adj_nav=1 + i * .001, accum_nav=2 + i * .001,
                 nav=1 + i * .001)
            for i, d in enumerate(pd.bdate_range("2025-01-02", periods=count))]


class BondEvidenceTest(unittest.TestCase):
    def anomaly(self, target=None, peers=None):
        return FundBondAnomalyService(
            fund_repo=SimpleNamespace(get_fund_by_identifier=lambda _: {"wind_code": "target", "type": "债券"}),
            nav_repo=SimpleNamespace(get_nav_series=lambda _: target if target is not None else rows()),
            classification_repo=SimpleNamespace(
                get_classification_context=lambda _: {"peer_group_id": "bond", "minimum_peer_count": 5},
                list_peer_nav_series=lambda *args: peers or []),
        )

    def duration(self, target=None, cached=None):
        return FundBondDurationService(
            repo=SimpleNamespace(latest_estimate=lambda *args: cached, index_inventory=lambda: {}),
            nav_repo=SimpleNamespace(get_nav_series=lambda _: target or []),
            fund_repo=SimpleNamespace(get_fund_by_identifier=lambda _: {"wind_code": "target", "type": "债券"}),
            index_service=Mock(ensure_local_data=Mock(return_value={"status": "ready"})),
        )

    def test_dividend_uses_adjusted_not_unit_or_accumulated_nav(self):
        data = rows()
        for row in data[60:]:
            row["nav"] -= .2
        levels, basis = self.anomaly()._levels(data)
        self.assertEqual(basis, "adj_nav")
        self.assertAlmostEqual(levels.iloc[61] / levels.iloc[60] - 1, 1.061 / 1.06 - 1)
        result = self.anomaly(data).analyze("target")
        self.assertEqual(result["events"], [])

    def test_missing_adjusted_nav_is_not_replaced_with_legacy_nav(self):
        data = rows()
        for row in data:
            row.pop("adj_nav")
        result = self.anomaly(data).analyze("target")
        self.assertEqual(result["status"], "insufficient_evidence")
        service = self.duration(data)
        self.assertEqual(service.calculate("target")["status"], "insufficient_evidence")
        service.index_service.ensure_local_data.assert_not_called()

    def test_invalid_values_keep_gaps_without_forward_fill(self):
        data = rows()
        for i, value in enumerate([float("inf"), float("nan"), 0, -1, None], 40):
            data[i]["adj_nav"] = value
        data.append({"date": "invalid", "adj_nav": 2})
        data.append({"date": None, "adj_nav": 2})
        levels, _ = self.anomaly()._levels(data)
        self.assertEqual(levels.count(), 95)
        self.assertTrue(levels.iloc[40:45].isna().all())
        self.assertTrue(pd.isna(levels.pct_change(fill_method=None).iloc[45]))

    def test_no_peers_is_unknown_not_normal(self):
        result = self.anomaly().analyze("target")
        self.assertEqual(result["market_regime"], "unknown")
        self.assertEqual(result["current_signal"], "insufficient_evidence")
        self.assertFalse(result["formal_monitor_ready"])
        self.assertIn("未知", result["market_regime_label"])

    def test_current_peer_coverage_not_historical_column_count(self):
        peers = [dict(row, wind_code=f"p{i}") for i in range(5) for row in rows()[:-1]]
        result = self.anomaly(peers=peers).analyze("target")
        self.assertFalse(result["peer_model_ready"])
        self.assertFalse(result["formal_monitor_ready"])
        self.assertEqual(result["market_regime"], "unknown")

    def test_peer_returns_share_target_interval_endpoints(self):
        data = rows()
        peers = [dict(row, wind_code="p") for i, row in enumerate(data) if i != 50]
        dates = pd.DatetimeIndex([row["date"] for row in data])
        returns, _ = self.anomaly()._peer_returns(peers, "target", target_dates=dates)
        self.assertTrue(pd.isna(returns.loc[dates[51], "p"]))
        self.assertAlmostEqual(returns.loc[dates[52], "p"], 1.052 / 1.051 - 1)

    def test_peer_gap_requires_new_market_history(self):
        target = pd.Series(np.linspace(1, 1.1, 100), index=pd.bdate_range("2025-01-02", periods=100))
        peers = pd.DataFrame(.001, index=target.index, columns=list("abcde"))
        peers.iloc[90] = np.nan
        result = self.anomaly()._analyze_series(target, peers, 5, 100)
        self.assertEqual(result["market_regime"], "unknown")

    def test_complete_current_evidence_is_ready(self):
        peers = [dict(row, wind_code=f"p{i}") for i in range(5) for row in rows()]
        result = self.anomaly(peers=peers).analyze("target")
        self.assertTrue(result["formal_monitor_ready"])
        self.assertEqual(result["current_signal"], "normal")

    def test_own_anomaly_remains_visible_without_peers(self):
        data = rows()
        data[-1]["adj_nav"] = .8
        result = self.anomaly(data).analyze("target")
        self.assertEqual(result["current_signal"], "abnormal")
        self.assertFalse(result["formal_monitor_ready"])

    def test_old_cache_cannot_be_relabelled_as_new_methodology(self):
        result = self.duration(cached={"methodology_version": "jigouyun_public_rbsa_v1", "status": "ok", "r_squared": .9, "estimated_duration": 4}).get("target")
        self.assertFalse(result["formal_duration_ready"])
        self.assertIsNone(result["estimated_duration"])
        self.assertTrue(result["missing_items"])

    def test_weekly_sampling_does_not_replace_invalid_last_observation(self):
        data = pd.Series([1., 1.01, np.nan, 1.03], index=pd.to_datetime(["2025-01-03", "2025-01-09", "2025-01-10", "2025-01-17"]))
        self.assertTrue(self.duration()._weekly_returns(data).empty)

    def test_benchmark_does_not_substitute_different_week_end_day(self):
        fund = pd.Series([1., 1.01, 1.02], index=pd.to_datetime(["2025-01-03", "2025-01-09", "2025-01-17"]))
        index = pd.Series([100., 101., 102.], index=pd.to_datetime(["2025-01-03", "2025-01-10", "2025-01-17"]))
        self.assertTrue(returns_at_endpoints(index, weekly_endpoints(fund)).empty)

    def test_missing_latest_target_is_not_an_old_normal_result(self):
        data = rows()
        data[-1]["adj_nav"] = None
        result = self.anomaly(data).analyze("target")
        self.assertEqual(result["status"], "insufficient_evidence")
        self.assertFalse(result["formal_monitor_ready"])

    def test_new_cache_keeps_adjusted_basis(self):
        result = self.duration(cached={"methodology_version": FundBondDurationService.METHODOLOGY_VERSION, "status": "ok", "r_squared": .9, "estimated_duration": 4}).get("target")
        self.assertTrue(result["formal_duration_ready"])
        self.assertEqual(result["nav_basis"], "adj_nav")

    def test_old_observation_date_is_historical_not_current_evidence(self):
        result = self.duration(cached={"methodology_version": FundBondDurationService.METHODOLOGY_VERSION,
            "status": "ok", "r_squared": .9, "estimated_duration": 4, "as_of_date": "2020-01-01"}).get("target")
        self.assertEqual(result["status"], "stale")
        self.assertFalse(result["formal_duration_ready"])
        self.assertEqual(result["estimated_duration"], 4)

    def test_incomplete_indices_stop_before_regression(self):
        dates = pd.date_range("2024-01-04", periods=80, freq="W-THU")
        service = self.duration([dict(date=d, adj_nav=1 + i * .001) for i, d in enumerate(dates)])
        service.index_service.ensure_local_data.return_value = {"status": "incomplete", "missing_items": ["信用债久期缺失"]}
        service._style_regression = Mock()
        result = service.calculate("target")
        self.assertEqual(result["status"], "insufficient_evidence")
        self.assertEqual(result["missing_items"], ["信用债久期缺失"])
        service._style_regression.assert_not_called()

    def test_duration_calculation_preserves_actual_dates_and_writes_only_new_method(self):
        dates = pd.date_range(end=pd.Timestamp.today().normalize(), periods=80, freq="W-THU")
        levels = np.cumprod(1 + np.array([.001, -.002, .003, .002] * 20))
        data = [dict(date=d, adj_nav=v, accum_nav=v + 1) for d, v in zip(dates, levels)]
        service = self.duration(data)
        definitions = ChinaBondIndexService.definitions()
        service.repo.list_index_series = Mock(return_value={
            item["series_key"]: [dict(trade_date=d, value=v * 100) for d, v in zip(dates, levels)]
            for item in definitions
        })
        service.repo.latest_indicator_values = Mock(side_effect=lambda keys, *args: {
            key: {"value": 3., "trade_date": dates[-1].date().isoformat()} for key in keys})
        service.repo.upsert_estimate = Mock()
        # Selection/regression separately have a mathematical smoke test.
        service._select_group = lambda fund, candidates, *args: ({**candidates[0], "selection_r_squared": 1.}, {})
        result = service.calculate("target", window_weeks=52)
        self.assertTrue(result["formal_duration_ready"])
        self.assertAlmostEqual(result["estimated_duration"], 3.)
        self.assertEqual(result["as_of_date"], dates[-1].date().isoformat())
        self.assertEqual(result["data_start"], dates[-53].date().isoformat())
        self.assertEqual(service.repo.latest_indicator_values.call_args.args[-1], result["as_of_date"])
        self.assertEqual(service.repo.upsert_estimate.call_args.args[0]["methodology_version"], service.METHODOLOGY_VERSION)

        service.repo.latest_indicator_values.side_effect = lambda keys, *args: {
            key: {"value": None, "trade_date": dates[-1].date().isoformat()} for key in keys}
        service.repo.upsert_estimate.reset_mock()
        self.assertEqual(service.calculate("target")["status"], "insufficient_evidence")
        service.repo.upsert_estimate.assert_not_called()


if __name__ == "__main__":
    unittest.main()
