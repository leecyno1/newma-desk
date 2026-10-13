"""自然年度复权、完整日历、端点对齐；纯计算，不写库。"""
import sys
import unittest
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from services.fund_trading_calendar import get_trading_calendar
from services.fund_period_performance_service import FundPeriodPerformanceService as Service


class PeriodEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.start, self.end = date(2025, 1, 1), date(2025, 12, 31)
        days = sorted(get_trading_calendar().open_days(date(2024, 12, 20), self.end))
        self.rows = [{'date': day, 'adj_nav': 1 + i * .001, 'nav': 9, 'accum_nav': 10, 'risk_calendar': 'SSE'} for i, day in enumerate(days)]

    def result(self, rows=None):
        points, _ = Service._points(self.rows if rows is None else rows)
        return Service._period_result(points, self.start, self.end)

    def summary(self, rows=None):
        rows = self.rows if rows is None else rows
        prior = [row for row in rows if row['date'] < self.start]
        inside = [row for row in rows if row['date'] >= self.start]
        valid = [row for row in inside if row['adj_nav'] is not None]
        return {'entity_id': 'peer', 'nav_basis': 'adj_nav', 'risk_calendar': 'SSE',
                'baseline_date': prior[-1]['date'], 'baseline_nav': prior[-1]['adj_nav'],
                'first_date': valid[0]['date'], 'first_nav': valid[0]['adj_nav'],
                'last_date': valid[-1]['date'], 'last_nav': valid[-1]['adj_nav'],
                'last_record_date': inside[-1]['date'], 'last_record_nav': inside[-1]['adj_nav'],
                'valid_dates': [row['date'] for row in valid], 'observations': len(valid),
                'missing_observations': len(inside) - len(valid)}

    def test_full_calendar_uses_adjusted_endpoints(self):
        result = self.result()
        self.assertEqual(result['coverage_status'], 'complete')
        self.assertEqual(result['observation_coverage'], 1)
        self.assertEqual(result['methodology']['missing_open_days'], 0)
        self.assertGreater(result['return'], 0)

    def test_missing_open_day_is_not_hidden_by_seventy_percent_coverage(self):
        result = self.result(self.rows[:30] + self.rows[31:])
        self.assertEqual(result['coverage_status'], 'partial')
        self.assertEqual(result['methodology']['missing_open_days'], 1)

    def test_null_gap_preserved(self):
        rows = [dict(row) for row in self.rows]
        rows[30]['adj_nav'] = None
        result = self.result(rows)
        self.assertEqual(result['coverage_status'], 'partial')
        self.assertEqual(result['methodology']['missing_observations'], 1)

    def test_null_baseline_cannot_revive_prior_valid_date(self):
        rows = [dict(row) for row in self.rows]
        rows[next(i for i, row in enumerate(rows) if row['date'] == date(2024, 12, 31))]['adj_nav'] = None
        result = self.result(rows)
        self.assertEqual(result['coverage_status'], 'partial')
        self.assertEqual(result['actual_start_date'], '2025-01-02')

    def test_null_last_date_cannot_be_called_complete(self):
        rows = [dict(row) for row in self.rows]
        rows[-1]['adj_nav'] = None
        self.assertEqual(self.result(rows)['coverage_status'], 'partial')

    def test_missing_adjusted_does_not_use_unit_or_accum(self):
        points, basis = Service._points([{**row, 'adj_nav': None} for row in self.rows])
        self.assertEqual(basis, 'adj_nav')
        self.assertTrue(all(row['nav'] is None for row in points))

    def test_unknown_market_not_exchange_verified(self):
        self.assertEqual(self.result([{**row, 'risk_calendar': None} for row in self.rows])['coverage_status'], 'partial')
        with patch('services.fund_period_performance_service.get_trading_calendar', return_value=None):
            self.assertEqual(self.result()['coverage_status'], 'partial')

    def test_closed_day_disclosure_not_added_to_expected_count(self):
        result = self.result(self.rows + [{'date': date(2025, 10, 1), 'adj_nav': 1.1, 'risk_calendar': 'SSE'}])
        self.assertEqual(result['coverage_status'], 'complete')
        self.assertEqual(result['observation_coverage'], 1)
        self.assertEqual(result['observations'], result['expected_observations'] + 1)

    def test_nonfinite_values_and_latest_null_revision(self):
        for invalid in (float('inf'), float('nan'), -1, 0):
            points, _ = Service._points(self.rows + [{**self.rows[30], 'adj_nav': invalid}])
            self.assertIsNone(next(row for row in points if row['date'] == self.rows[30]['date'])['nav'])

    def test_sql_summary_matches_python_period(self):
        self.assertEqual(Service._summary_period_result(self.summary(), self.start, self.end), self.result())
        rows = [dict(row) for row in self.rows]
        rows[-1]['adj_nav'] = None
        self.assertEqual(Service._summary_period_result(self.summary(rows), self.start, self.end), self.result(rows))

    def test_peer_rank_requires_exact_endpoints_and_unique_entity(self):
        repo = Mock()
        good = self.summary()
        shifted = {**good, 'entity_id': 'wrong', 'baseline_date': date(2024, 12, 30)}
        repo.list_peer_calendar_period_summaries.return_value = [good, good, shifted, {**good, 'entity_id': 'target'}]
        service = Service(Mock(), Mock(), repo)
        result = service._peer_rank(self.result(), 'group', 'target', self.start, self.end, 2)
        self.assertEqual(result['peer_count'], 2)
        self.assertEqual(result['rank'], 1)

    def test_ytd_not_counted_as_completed_year_and_future_data_excluded(self):
        future = {'date': date(2027, 1, 1), 'adj_nav': 10000, 'risk_calendar': 'SSE'}
        repo = Mock(get_nav_series=Mock(return_value=[*self.rows, future]))
        fund = Mock(get_fund=Mock(return_value={'type': '债券型'}))
        service = Service(repo, fund, Mock(get_classification_context=Mock(return_value={})), today=self.end)
        result = service.get('UNIT.TEST', 1)
        self.assertEqual(result['latest_nav_date'], self.end.isoformat())
        self.assertEqual(result['summary']['complete_period_count'], 0)
        self.assertTrue(result['periods'][0]['is_ytd'])


if __name__ == '__main__':
    unittest.main()
