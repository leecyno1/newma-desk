"""评分只消费显式窗口和单位；隔离数据，不写真实库。"""
import sys
import unittest
import asyncio
from copy import deepcopy
from datetime import date, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.performance_nav_series import METHODOLOGY_VERSION
from services.source_fund_metrics import SOURCE_METHODOLOGY_VERSION
from services.scoring_engine import FundScoringEngine
from services.metric_factory import MetricFactory
from services.fund_trading_calendar import get_trading_calendar
from services.professional_scoring_service import ProfessionalScoringService


def panel():
    as_of = date(2026, 9, 30)
    one_year = {'annualized_return': .18, 'max_drawdown': -.12, 'annualized_volatility': .16,
                'sharpe_ratio': 1.2, 'sortino_ratio': 1.5, 'calmar_ratio': 1., 'information_ratio': .6,
                'var_95': -.02, 'downside_risk': .10, 'tracking_error': .05}
    result = []
    for window, days, values in [('1y', 365, one_year), ('3y', 1095, {'annualized_return': .10}),
                                 ('5y', 1825, {'annualized_return': .08})]:
        for name, value in values.items():
            result.append({'metric_name': name, 'metric_value': value, 'metric_window': window,
                           'metric_unit': 'ratio', 'source_snapshot_id': 's1', 'as_of_date': as_of,
                           'benchmark_code': 'REAL.INDEX' if name in {'information_ratio', 'tracking_error'} else None,
                           'details': {'methodology_version': METHODOLOGY_VERSION, 'nav_basis': 'adj_nav', 'daily_risk_eligible': True,
                                       'window_start_date': as_of - timedelta(days=days), 'window_end_date': as_of}})
    return result


class ScoringEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.engine = FundScoringEngine()
        self.rows = panel()

    def score(self):
        return self.engine.score_fund_from_metric_snapshots('UNIT.TEST', SimpleNamespace(get_latest_panel=lambda *_: self.rows))

    def test_complete_explicit_windows_keep_distinct_returns(self):
        output = self.score()
        self.assertEqual(output['data_quality']['status'], 'complete')
        self.assertIsNotNone(output['overall_score'])
        self.assertEqual(output['metric_scores']['annualized_return_1y_raw'], 18)
        self.assertEqual(output['metric_scores']['annualized_return_3y_raw'], 10)
        self.assertEqual(output['metric_scores']['annualized_return_5y_raw'], 8)
        self.assertIn('年化收益表现较强', output['positive_factors'])
        self.assertEqual(output['source_snapshot_ids'], ['s1'])

    def test_one_window_does_not_fill_longer_history(self):
        self.rows = [row for row in self.rows if row['metric_window'] == '1y']
        output = self.score()
        self.assertIsNone(output['overall_score'])
        self.assertIsNone(output['overall_grade'])
        self.assertEqual(output['dimension_scores']['return']['count'], 1)
        self.assertIn('annualized_return_3y', output['missing_data'])

    def test_legacy_unversioned_snapshots_are_not_relabelled(self):
        for row in self.rows:
            row.pop('details')
        output = self.score()
        self.assertIsNone(output['overall_score'])
        self.assertEqual(output['source_snapshot_ids'], [])
        self.assertIsNone(output['dimension_scores']['return']['score'])
        audit = output['evidence_audit']
        self.assertTrue(all(row['status'] == 'rejected' for row in audit['rows']))
        self.assertIn('旧方法或未记录方法版本', audit['rows'][0]['reasons'])

    def test_factory_named_window_can_be_consumed_by_new_score_without_relabelling(self):
        as_of = date(2026, 10, 2)
        days = sorted(get_trading_calendar().open_days(date(2021, 9, 29), as_of))
        rows = [{'date': day, 'adj_nav': 1+i*.001, 'risk_calendar': 'SSE'} for i, day in enumerate(days)]
        original = deepcopy(rows)
        records = MetricFactory().build_metric_records('fund', 'UNIT.TEST', as_of, rows, window='1y')
        self.assertTrue(records)
        self.assertEqual(rows, original)
        self.assertTrue(all(record['details']['window_start_date'] >= date(2025, 9, 30) for record in records))
        proposed = [{**record, 'metric_window': record['window']} for record in records]
        metrics, used, audit = self.engine._snapshot_evidence(proposed)
        self.assertIn('annualized_return_1y', metrics)
        self.assertNotIn('annualized_return_3y', metrics)
        self.assertNotIn('annualized_return_5y', metrics)
        self.assertTrue(used)
        self.assertEqual(audit['as_of_date'], '2026-10-02')

    def test_factory_short_history_cannot_be_saved_with_year_label(self):
        rows = [{'date': date(2026, 9, day), 'adj_nav': 1+day*.001} for day in range(1, 30)]
        self.assertEqual(MetricFactory().build_metric_records('fund', 'UNIT.TEST', date(2026, 10, 2), rows, window='1y'), [])

    def test_partial_history_not_annual_metric(self):
        for row in self.rows:
            row['details']['window_start_date'] = date(2026, 9, 1)
        self.assertIsNone(self.score()['metric_scores']['annualized_return_1y_raw'])

    def test_unit_nav_snapshot_cannot_claim_adjusted_method(self):
        for row in self.rows:
            row['details']['nav_basis'] = 'unit_nav'
        self.assertIsNone(self.score()['overall_score'])
        self.assertIsNone(self.score()['metric_scores']['annualized_return_1y_raw'])

    def test_units_are_explicit_not_magnitude_heuristic(self):
        self.rows[0]['metric_value'] = 2.5
        self.assertEqual(self.score()['metric_scores']['annualized_return_1y_raw'], 250)
        self.rows[0].update(metric_value=2.5, metric_unit='percent')
        self.assertEqual(self.score()['metric_scores']['annualized_return_1y_raw'], 2.5)
        self.rows[0]['metric_unit'] = None
        self.assertIsNone(self.score()['metric_scores']['annualized_return_1y_raw'])

    def test_different_cutoffs_are_not_combined(self):
        self.rows[-1]['as_of_date'] = date(2026, 9, 29)
        self.assertIsNone(self.score()['metric_scores']['annualized_return_5y_raw'])

    def test_unrelated_latest_aum_cannot_invalidate_performance_panel(self):
        before = self.score()
        self.rows.append({'metric_name': 'aum', 'metric_window': 'latest', 'metric_value': 5,
                          'as_of_date': date(2026, 10, 1)})
        after = self.score()
        self.assertEqual(before['metric_scores'], after['metric_scores'])
        self.assertEqual(after['evidence_audit']['as_of_date'], '2026-09-30')
        self.assertEqual(after['evidence_audit']['out_of_scope_row_count'], 1)

    def test_conflicting_benchmark_rows_are_not_arbitrary(self):
        index = next(row for row in self.rows if row['metric_name'] == 'information_ratio')
        self.rows.append({**deepcopy(index), 'benchmark_code': 'OTHER.INDEX'})
        self.assertIsNone(self.score()['metric_scores']['information_ratio_raw'])
        audit = self.score()['evidence_audit']
        rule = next(rule for rule in audit['rules'] if rule['metric_name'] == 'information_ratio')
        self.assertIn('多个基准', rule['reason'])

    def test_zero_denominator_is_not_zero_risk_adjusted_score(self):
        for row in self.rows:
            if row['metric_name'] == 'tracking_error':
                row['metric_value'] = 0
        self.assertIsNone(self.score()['metric_scores']['information_ratio_normalized'])

    def test_missing_values_do_not_get_fifty_points(self):
        output = self.engine.score_fund({}, {}, {})
        self.assertIsNone(output['overall_score'])
        self.assertIsNone(output['dimension_scores']['return']['score'])
        self.assertEqual(output['dimension_scores']['risk']['count'], 0)
        self.assertTrue(all(value is None for value in output['metric_scores'].values()))

    def test_ratio_source_is_scored_in_percent_points(self):
        output = self.engine.score_fund({'metric_unit': 'ratio', 'annualized_return_1y': .18}, {}, {})
        self.assertEqual(output['metric_scores']['annualized_return_1y_raw'], 18)
        self.assertAlmostEqual(output['dimension_scores']['return']['score'], 43.64)
        self.assertIsNone(output['overall_score'])

    def test_nonfinite_missing_and_raw_precision(self):
        output = self.engine.score_fund({'sharpe_ratio': float('nan'), 'max_drawdown': -.00012}, {'var_95': float('inf')}, {})
        self.assertIsNone(output['metric_scores']['sharpe_ratio_raw'])
        self.assertIsNone(output['metric_scores']['var_95_raw'])
        self.assertEqual(output['metric_scores']['max_drawdown_raw'], -.00012)

    def test_professional_fallback_does_not_borrow_two_year_drawdown(self):
        service = ProfessionalScoringService.__new__(ProfessionalScoringService)
        fund = {'performance': {'methodology_version': SOURCE_METHODOLOGY_VERSION, 'return_1y': .2},
                'risk_metrics': {'methodology_version': SOURCE_METHODOLOGY_VERSION, 'max_drawdown_1y': None,
                                 'max_drawdown_2y': -.2}}
        metrics = service._fund_fallback_metrics(fund)['1y']
        self.assertNotIn('max_drawdown', metrics)
        self.assertNotIn('annualized_return', metrics)

    def test_manager_routes_handle_unavailable_fund_scores(self):
        from routes import scoring, managers
        source = SimpleNamespace(get_manager_info=lambda _: {}, get_manager_funds=lambda _: [{'wind_code': 'UNIT.TEST'}],
                                 get_fund_performance=lambda _: {}, get_fund_risk_metrics=lambda _: {}, get_fund_style=lambda _: {})
        with patch.object(scoring, '_get_services', return_value=(source, self.engine)):
            output = asyncio.run(scoring.get_manager_scoring('UNIT.MANAGER'))
        self.assertIsNone(output['scoring']['overall_score'])
        self.assertEqual(output['score_coverage'], {'available': 0, 'requested': 1})
        with patch.object(managers, '_get_services', return_value=(source, self.engine)):
            output = asyncio.run(managers.get_manager_score('UNIT.MANAGER'))
        self.assertIsNone(output['overall_score'])


if __name__ == '__main__':
    unittest.main()
