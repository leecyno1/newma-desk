"""Adjustment source regression tests; fake market API, no database writes."""
import os
import sys
import unittest
from datetime import date, timedelta
from unittest.mock import Mock

import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from services.tushare_service import TushareDataService


def service(rows, factors):
    s = TushareDataService.__new__(TushareDataService)
    s.mock_mode = False
    s.strict_no_mock = True
    s._pro = Mock()
    s._pro.fund_nav.return_value = pd.DataFrame(rows)
    s._pro.fund_adj.side_effect = lambda **kw: pd.DataFrame(factors[kw['offset']:kw['offset'] + kw['limit']])
    return s


def sample():
    start = date.today() - timedelta(days=24)
    rows = [dict(nav_date=(start + timedelta(days=i)).strftime('%Y%m%d'),
                 unit_nav=1 + i * .002, accum_nav=2 + i * .002,
                 adj_nav=100 + i * .2 if i < 5 else None) for i in range(25)]
    factors = [dict(trade_date=r['nav_date'], adj_factor=3.) for r in rows]
    return rows, factors


class AdjustmentSourceTest(unittest.TestCase):
    def test_partial_native_series_preserves_gaps_without_price_factor_splice(self):
        rows, factors = sample()
        s = service(rows, factors)
        result = s.get_fund_nav('TEST.OF', '2020-01-01', '2099-01-01')
        self.assertEqual(len(result), 25)
        for index, (raw, actual) in enumerate(zip(rows, result)):
            self.assertEqual(actual['adj_nav'], raw['adj_nav'])
            self.assertEqual(actual['adj_nav_source'], 'tushare.fund_nav.adj_nav' if index < 5 else None)
            self.assertEqual(actual['reported_accum_nav'], raw['accum_nav'])
        s._pro.fund_adj.assert_not_called()

    def test_performance_and_nav_use_same_adjustment_source(self):
        rows, factors = sample()
        s = service(rows, factors)
        nav = s.get_fund_nav('TEST.OF', '2020-01-01', '2099-01-01')
        performance = s.get_fund_performance('TEST.OF')
        self.assertEqual(performance['metric_nav_source'], nav[-1]['daily_return_source'])
        self.assertIsNone(performance['annualized_return_1y'])
        observed = performance['periods']['1y']['observed_metrics']
        self.assertAlmostEqual(observed['total_return'], rows[4]['adj_nav'] / rows[0]['adj_nav'] - 1)
        self.assertTrue(all(row['daily_return'] is None for row in nav[5:]))

    def test_gap_breaks_daily_return_and_unit_nav_is_not_filled(self):
        rows, factors = sample()
        for row in rows:
            row['adj_nav'] = row['unit_nav']
        rows[4]['adj_nav'] = None
        rows[6]['unit_nav'] = None
        result = service(rows, factors).get_fund_nav('TEST.OF', '2020-01-01', '2099-01-01')
        self.assertEqual(len(result), 25)
        self.assertIsNone(result[4]['daily_return'])
        self.assertIsNone(result[5]['daily_return'])
        self.assertIsNone(result[6]['unit_nav'])
        self.assertIsNotNone(result[6]['daily_return'])

    def test_complete_native_source_does_not_fetch_factors(self):
        rows, factors = sample()
        for r in rows:
            r['adj_nav'] = r['unit_nav'] * 100
        s = service(rows, factors)
        prepared, source = s._prepare_adjusted_nav(pd.DataFrame(rows))
        self.assertEqual(source, 'tushare.fund_nav.adj_nav')
        s._pro.fund_adj.assert_not_called()
        self.assertAlmostEqual(prepared.iloc[-1]['adj_nav'], rows[-1]['adj_nav'])

    def test_etf_nav_also_must_not_borrow_market_price_factors(self):
        rows, factors = sample()
        for row in rows:
            row.pop('adj_nav')
        s = service(rows, factors)
        result = s.get_fund_nav('510300.SH', '2020-01-01', '2099-01-01')
        self.assertTrue(all(row['adj_nav'] is None for row in result))
        s._pro.fund_adj.assert_not_called()

    def test_dividend_and_split_keep_total_return_continuous(self):
        rows = [dict(nav_date='20260101', unit_nav=1.05, accum_nav=1.05),
                dict(nav_date='20260102', unit_nav=1., accum_nav=1.05),
                dict(nav_date='20260103', unit_nav=.5, accum_nav=1.05)]
        for row in rows:
            row['adj_nav'] = 1.05
        result = service(rows, []).get_fund_nav('TEST.OF', '2026-01-01', '2026-01-03')
        self.assertEqual([r['adj_nav'] for r in result], [1.05, 1.05, 1.05])
        self.assertEqual([r['daily_return'] for r in result], [None, 0., 0.])

    def test_latest_announced_revision_selected_before_returns(self):
        rows, factors = sample()
        for r in rows:
            r['ann_date'] = r['nav_date']
            r['adj_nav'] = r['unit_nav']
        corrected = {**rows[4], 'ann_date': rows[6]['nav_date'], 'unit_nav': 1.009, 'adj_nav': 1.009}
        s = service([corrected, *rows], factors)
        result = s.get_fund_nav('TEST.OF', '2020-01-01', '2099-01-01')
        self.assertEqual(len(result), 25)
        self.assertEqual(result[4]['unit_nav'], 1.009)
        self.assertEqual(result[4]['announcement_date'], s._format_date_value(corrected['ann_date']))
        self.assertAlmostEqual(result[5]['daily_return'], rows[5]['unit_nav'] / 1.009 - 1)

    def test_invalid_adjusted_values_remain_missing(self):
        rows, factors = sample()
        for row, invalid in zip(rows, [0, -1, float('inf'), float('nan'), 'invalid']):
            row['adj_nav'] = invalid
        s = service(rows, factors)
        prepared, _ = s._prepare_adjusted_nav(pd.DataFrame(rows))
        self.assertTrue(prepared['adj_nav'].isna().all())
        self.assertEqual(rows[0]['adj_nav'], 0)  # Caller raw data is not overwritten.
        s._pro.fund_adj.assert_not_called()

    def test_missing_announcement_date_stays_null_and_not_a_fake_date(self):
        for value in (None, float('nan'), pd.NA, '', 'nan', '20260230'):
            with self.subTest(value=value):
                self.assertIsNone(TushareDataService._format_date_value(value))
        self.assertEqual(TushareDataService._format_date_value(20260930.0), '2026-09-30')

    def test_missing_announced_revision_cannot_displace_a_known_later_revision(self):
        rows = [dict(nav_date='20260929', ann_date=float('nan'), adj_nav=1.1, unit_nav=1),
                dict(nav_date='20260929', ann_date='20261001', adj_nav=1.2, unit_nav=1)]
        result = service(rows, []).get_fund_nav('TEST.OF', '2026-09-29', '2026-10-02')
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['adj_nav'], 1.2)
        self.assertEqual(result[0]['announcement_date'], '2026-10-01')


if __name__ == '__main__':
    unittest.main()
