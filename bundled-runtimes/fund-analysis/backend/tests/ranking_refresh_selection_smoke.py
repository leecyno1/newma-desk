import copy
import sys
import unittest
from contextlib import ExitStack
from datetime import date, datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts import sync_fund_ranking_metrics as sync


class FrozenDate(date):
    @classmethod
    def today(cls):
        return cls(2026, 9, 19)


def active_panel(as_of_date="2026-09-18"):
    return [
        {
            "metric_window": "1y",
            "metric_name": name,
            "metric_value": value,
            "as_of_date": as_of_date,
        }
        for name, value in (
            ("annualized_return", 0.08),
            ("max_drawdown", -0.1),
            ("sharpe_ratio", 0.8),
        )
    ]


def index_panel(as_of_date="2026-09-18"):
    return [
        {"metric_window": window, "metric_name": name, "metric_value": value, "as_of_date": day}
        for window, name, value, day in (
            ("1y", "tracking_error", 0.02, as_of_date),
            ("1y", "excess_return", -0.01, as_of_date),
            ("latest", "aum", 15, "2026-06-30"),
            ("latest", "expense_ratio", 0.002, "2026-01-01"),
        )
    ]


class RankingRefreshSelectionTests(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.rows = {}
        self.panels = {}
        self.coverage = {}
        self.groups = []
        self.statements = []
        self.engine = Mock()
        self.engine.connect.return_value.__enter__ = Mock(return_value=self.engine)
        self.engine.connect.return_value.__exit__ = Mock(return_value=False)
        self.engine.execute.side_effect = self.execute
        self.stack.enter_context(patch.object(sync, "get_engine", return_value=self.engine))
        metric_repo = Mock()
        metric_repo.get_latest_panels.side_effect = lambda target_type, codes: {
            code: self.panels.get(code, []) for code in codes
        }
        self.stack.enter_context(patch.object(sync, "get_metric_snapshot_repo", return_value=metric_repo))
        peer_service = Mock()
        peer_service.build_peer_percentiles.side_effect = lambda code, window: self.coverage[code]
        self.stack.enter_context(patch.object(sync, "PeerComparisonService", return_value=peer_service))
        self.stack.enter_context(patch.object(sync, "date", FrozenDate))
        self.stack.enter_context(patch.object(sync, "log"))
        self.no_init = self.stack.enter_context(patch.object(sync, "init_database"))
        self.no_source = self.stack.enter_context(patch.object(sync, "TushareDataService"))

    def execute(self, statement, params):
        self.statements.append((str(statement), params))
        rows = self.rows[params["peer_group_key"]] if "peer_group_key" in params else self.groups
        return SimpleNamespace(fetchall=lambda: [SimpleNamespace(_mapping=row) for row in rows])

    def add_group(self, key="peer-a", valid=10, classified=12):
        self.groups.append({"peer_group_key": key, "target_wind_code": key})
        self.rows[key] = []
        self.coverage[key] = {
            "valid_metric_peer_count": valid,
            "classified_peer_count": classified,
            "minimum_valid_peer_count": 5,
        }

    def add_fund(self, code, group="peer-a", nav_date="2026-09-18", panel=None,
                 family="active_equity_core", last_synced_at="2026-09-01T00:00:00+00:00"):
        self.rows[group].append({
            "wind_code": code,
            "strategy_family_key": family,
            "nav_date": nav_date,
            "last_synced_at": last_synced_at,
        })
        self.panels[code] = active_panel() if panel is None else panel

    def select(self, limit=100):
        result = sync.select_peer_evaluation_coverage_codes(
            limit=limit,
            peer_group_keys=[group["peer_group_key"] for group in self.groups],
            target_per_group=10,
            include_exchange_funds=True,
        )
        self.no_init.assert_not_called()
        self.no_source.assert_not_called()
        return result

    def test_met_coverage_still_refreshes_old_nav(self):
        self.add_group()
        self.add_fund("OLD.OF", nav_date="2020-01-01")
        self.assertEqual(self.select(), ["OLD.OF"])

    def test_recent_nav_does_not_hide_old_required_metric(self):
        self.add_group()
        panel = active_panel()
        panel[1]["as_of_date"] = "2020-01-01"
        panel.append({"metric_window": "latest", "metric_name": "aum",
                      "metric_value": 15, "as_of_date": "2026-09-19"})
        self.add_fund("OLD_METRIC.OF", panel=panel)
        self.assertEqual(self.select(), ["OLD_METRIC.OF"])

    def test_recent_label_does_not_hide_old_window_end(self):
        self.add_group()
        panel = active_panel()
        panel[0]["details"] = {"window_end_date": "2020-01-01"}
        self.add_fund("OLD_WINDOW.OF", panel=panel)
        self.assertEqual(self.select(), ["OLD_WINDOW.OF"])

    def test_undated_required_metric_needs_refresh(self):
        self.add_group()
        panel = active_panel()
        del panel[0]["as_of_date"]
        self.add_fund("UNDATED.OF", panel=panel)
        self.assertEqual(self.select(), ["UNDATED.OF"])

    def test_missing_nav_date_needs_refresh(self):
        self.add_group()
        self.add_fund("UNDATED_NAV.OF", nav_date=None)
        self.assertEqual(self.select(), ["UNDATED_NAV.OF"])

    def test_week_boundary_is_inclusive_for_supported_date_shapes(self):
        self.add_group()
        for value in ("2026-09-12", date(2026, 9, 12), datetime(2026, 9, 12, 12)):
            with self.subTest(value=value):
                self.rows["peer-a"] = []
                self.add_fund("BOUNDARY.OF", nav_date=value, panel=active_panel(value))
                self.assertEqual(self.select(), [])
        self.rows["peer-a"] = []
        self.add_fund("EXPIRED.OF", nav_date="2026-09-11")
        self.assertEqual(self.select(), ["EXPIRED.OF"])

    def test_recent_data_is_not_refreshed(self):
        self.add_group()
        self.add_fund("FRESH.OF")
        self.assertEqual(self.select(), [])

    def test_historical_static_metrics_do_not_force_daily_refresh(self):
        self.add_group()
        self.add_fund("INDEX.SH", family="index_broad", panel=index_panel())
        self.assertEqual(self.select(), [])

    def test_recent_absolute_returns_do_not_hide_old_index_metrics(self):
        self.add_group()
        self.add_fund("INDEX.SH", family="index_broad",
                      panel=index_panel("2020-01-01") + active_panel())
        self.assertEqual(self.select(), ["INDEX.SH"])

    def test_recent_fallback_does_not_hide_old_preferred_metric(self):
        self.add_group()
        panel = index_panel() + [
            {"metric_window": "1y", "metric_name": "tracking_difference",
             "metric_value": -0.01, "as_of_date": "2020-01-01"},
        ]
        self.add_fund("INDEX.SH", family="index_broad", panel=panel)
        self.assertEqual(self.select(), ["INDEX.SH"])

    def test_old_fallback_does_not_expire_fresh_preferred_metric(self):
        self.add_group()
        panel = index_panel()
        panel[1]["as_of_date"] = "2020-01-01"
        panel.append({"metric_window": "1y", "metric_name": "tracking_difference",
                      "metric_value": -0.01, "as_of_date": "2026-09-18"})
        self.add_fund("INDEX.SH", family="index_broad", panel=panel)
        self.assertEqual(self.select(), [])

    def test_money_market_latest_yield_is_dynamic(self):
        self.add_group()
        panel = active_panel() + [
            {"metric_window": "latest", "metric_name": "seven_day_annualized_yield",
             "metric_value": 0.015, "as_of_date": "2020-01-01"},
            {"metric_window": "latest", "metric_name": "aum", "metric_value": 15,
             "as_of_date": "2026-06-30"},
        ]
        self.add_fund("MONEY.OF", family="cash_management", panel=panel)
        self.assertEqual(self.select(), ["MONEY.OF"])

    def test_old_optional_metric_does_not_force_refresh(self):
        self.add_group()
        panel = active_panel() + [
            {"metric_window": "1y", "metric_name": "sortino_ratio",
             "metric_value": 1.0, "as_of_date": "2020-01-01"},
        ]
        self.add_fund("FRESH.OF", panel=panel)
        self.assertEqual(self.select(), [])

    def test_met_coverage_does_not_expand_missing_pool(self):
        self.add_group()
        self.add_fund("MISSING.OF", panel=[])
        self.add_fund("STALE.OF", nav_date="2020-01-01")
        self.assertEqual(self.select(), ["STALE.OF"])

    def test_refresh_and_backfill_share_limit_without_starvation(self):
        for key in ("peer-a", "peer-b"):
            self.add_group(key, valid=9)
            self.add_fund(f"{key}-OLD1.OF", group=key, nav_date="2020-01-01")
            self.add_fund(f"{key}-OLD2.OF", group=key, nav_date="2020-01-01")
            self.add_fund(f"{key}-MISSING1.OF", group=key, panel=[])
            self.add_fund(f"{key}-MISSING2.OF", group=key, panel=[])
        self.assertEqual(set(self.select(limit=4)), {
            "PEER-A-OLD1.OF", "PEER-B-OLD1.OF", "PEER-A-MISSING1.OF", "PEER-B-MISSING1.OF",
        })
        self.assertEqual(len(self.select()), 6)

    def test_small_global_limit_keeps_backfill_progress(self):
        for key in ("peer-a", "peer-b", "peer-c"):
            self.add_group(key, valid=9)
            self.add_fund(f"{key}-OLD.OF", group=key, nav_date="2020-01-01")
            self.add_fund(f"{key}-MISSING.OF", group=key, panel=[])
        selected = self.select(limit=2)
        self.assertEqual(len(selected), 2)
        self.assertEqual(sum("MISSING" in code for code in selected), 1)
        self.assertEqual(sum("OLD" in code for code in selected), 1)

    def test_single_slot_preserves_backfill_priority(self):
        self.add_group(valid=9)
        self.add_fund("STALE.OF", nav_date="2020-01-01")
        self.add_fund("MISSING.OF", panel=[])
        self.assertEqual(self.select(limit=1), ["MISSING.OF"])

    def test_old_source_does_not_monopolize_successive_runs(self):
        self.add_group()
        self.add_fund("RECENT_ATTEMPT.OF", nav_date="2020-01-01",
                      last_synced_at="2026-09-18T00:00:00+00:00")
        self.add_fund("OLDER_ATTEMPT.OF", nav_date="2020-01-01",
                      last_synced_at="2026-08-01T00:00:00+00:00")
        self.assertEqual(self.select(limit=1), ["OLDER_ATTEMPT.OF"])
        self.rows["peer-a"][1]["last_synced_at"] = "2026-09-19T00:00:00+00:00"
        self.assertEqual(self.select(limit=1), ["RECENT_ATTEMPT.OF"])

    def test_duplicate_membership_does_not_duplicate_selected_funds(self):
        for key in ("peer-a", "peer-b"):
            self.add_group(key)
            self.add_fund("SHARED.OF", group=key, nav_date="2020-01-01")
        self.add_fund("OTHER.OF", group="peer-b", nav_date="2020-01-01")
        selected = self.select(limit=2)
        self.assertEqual(set(selected), {"SHARED.OF", "OTHER.OF"})
        self.assertEqual(len(selected), 2)

    def test_candidates_separate_missing_from_stale(self):
        self.add_group(valid=9)
        self.add_fund("STALE.OF", nav_date="2020-01-01", panel=active_panel("2020-01-01"))
        self.add_fund("MISSING.OF", panel=[])
        self.assertEqual(sync.select_peer_group_metric_candidates(
            "peer-a", 10, min_as_of_date=date(2026, 9, 12),
        ), {"missing": ["MISSING.OF"], "stale": ["STALE.OF"]})

    def test_historical_coverage_check_remains_date_agnostic(self):
        configs = sync.ProfessionalScoringService().methodology.peer_metric_configs("active_equity")
        self.assertTrue(configs)
        panel = active_panel("2020-01-01")
        original = copy.deepcopy(panel)
        self.assertTrue(sync._panel_has_required_category_metrics(panel, configs))
        self.assertEqual(panel, original)


if __name__ == "__main__":
    unittest.main()
