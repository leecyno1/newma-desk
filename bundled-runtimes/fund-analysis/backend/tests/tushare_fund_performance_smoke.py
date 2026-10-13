import math
import os
import sys
import unittest
from datetime import date, datetime, timedelta
from unittest.mock import Mock, patch

import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from services.tushare_service import TushareDataService
from services.fund_trading_calendar import get_trading_calendar
from services.metric_factory import MetricFactory


NAV_VALUES = [
    1.0000, 1.0200, 0.9900, 1.0150, 1.0050, 0.9800, 1.0100, 1.0300,
    1.0000, 0.9700, 1.0050, 1.0250, 0.9950, 1.0150, 1.0400, 1.0100,
    0.9850, 1.0200, 1.0350, 1.0050, 0.9750, 1.0150, 1.0300, 1.0500,
    1.0200, 1.0000, 1.0250, 1.0450, 1.0150, 1.0350,
]


class FakePro:
    def fund_nav(self, **kwargs):
        start = date.today() - timedelta(days=len(NAV_VALUES) - 1)
        return pd.DataFrame([
            {
                "ts_code": "000001.OF",
                "nav_date": (start + timedelta(days=offset)).strftime("%Y%m%d"),
                "unit_nav": value,
                "accum_nav": value,
                "adj_nav": value,
            }
            for offset, value in enumerate(NAV_VALUES)
        ])


def expected_sortino() -> float:
    daily_returns = [
        NAV_VALUES[index] / NAV_VALUES[index - 1] - 1
        for index in range(1, len(NAV_VALUES))
    ]
    annual_excess_return = (sum(daily_returns) / len(daily_returns)) * 252 - 0.02
    downside_shortfalls = [min(value - 0.02 / 252, 0.0) for value in daily_returns]
    second_moment = sum(value**2 for value in downside_shortfalls) / len(daily_returns)
    downside_deviation = math.sqrt(second_moment * 252)
    return annual_excess_return / downside_deviation


def main() -> int:
    service = TushareDataService.__new__(TushareDataService)
    service.mock_mode = False
    service.strict_no_mock = True
    service._pro = FakePro()

    performance = service.get_fund_performance("000001.OF")
    observed = performance['periods']['1y']['observed_metrics']
    sortino = observed.get("sortino_ratio")
    sharpe = observed.get("sharpe_ratio")

    real_sortino = expected_sortino()
    if sortino is None or abs(sortino - real_sortino) > 1e-4:
        raise AssertionError(
            f"sortino must be derived from downside deviation, expected {real_sortino}, got {sortino}"
        )
    if abs(sortino - round(sharpe * 1.2, 4)) < 1e-9:
        raise AssertionError(f"sortino must not be fabricated as sharpe*1.2: {sortino}")

    print("OK Tushare fund performance derives sortino from downside deviation")
    return 0


class FramePro:
    def __init__(self, rows, factors=None):
        self.rows = rows
        self.factors = factors or []
        self.adj_calls = []

    def fund_nav(self, **kwargs):
        return pd.DataFrame(self.rows)

    def fund_adj(self, **kwargs):
        self.adj_calls.append(kwargs)
        return pd.DataFrame(self.factors)


def nav_rows(count=20):
    start = date.today() - timedelta(days=count - 1)
    return [
        {
            "nav_date": (start + timedelta(days=index)).strftime("%Y%m%d"),
            "unit_nav": 1.5 + index * 0.001,
            "accum_nav": 2.0 + index * 0.002,
            "adj_nav": 10.0 + index * 0.01,
        }
        for index in range(count)
    ]


def frame_service(rows, factors=None):
    service = TushareDataService.__new__(TushareDataService)
    service.mock_mode = False
    service.strict_no_mock = True
    service._pro = FramePro(rows, factors)
    service._mock_performance = Mock(side_effect=AssertionError("Unexpected mock performance"))
    return service


class ConsistentPerformanceNavTests(unittest.TestCase):
    def test_short_history_is_observed_period_not_one_or_three_years(self):
        rows = nav_rows()
        actual = frame_service(rows).get_fund_performance('UNIT.TEST')
        self.assertIsNone(actual['annualized_return_1y'])
        self.assertIsNone(actual['annualized_return_3y'])
        self.assertEqual(actual['periods']['1y']['coverage_status'], 'partial')
        observed = actual['periods']['1y']['observed_metrics']
        total = rows[-1]['adj_nav'] / rows[0]['adj_nav'] - 1
        self.assertAlmostEqual(observed['total_return'], total)
        self.assertAlmostEqual(observed['annualized_return'], (1 + total) ** (365.25 / 19) - 1)

    def test_adjusted_gaps_never_borrow_accumulated_nav(self):
        rows = nav_rows()
        rows[10]['adj_nav'] = None
        actual = frame_service(rows).get_fund_performance('UNIT.TEST')
        period = actual['periods']['1y']
        self.assertEqual(period['methodology']['missing_observations'], 1)
        self.assertNotIn('annualized_volatility', period['observed_metrics'])
        self.assertEqual(actual['metric_nav_source'], 'tushare.fund_nav.adj_nav')

    def test_missing_adjusted_never_uses_cumulative_or_unit_nav(self):
        rows = nav_rows()
        for row in rows:
            row.pop("adj_nav")
        service = frame_service(rows)
        actual = service.get_fund_performance("UNIT.TEST")
        self.assertEqual(actual['periods']['1y']['observed_metrics'], {})
        self.assertIsNone(actual['max_drawdown'])
        self.assertEqual(len(service._pro.adj_calls), 0)

    def test_sparse_adjusted_retains_its_real_dates(self):
        rows = nav_rows()
        for row in rows[11:]:
            row["adj_nav"] = None
        actual = frame_service(rows).get_fund_performance("UNIT.TEST")
        period = actual['periods']['1y']
        self.assertEqual(period['methodology']['valid_observations'], 11)
        self.assertEqual(period['methodology']['missing_observations'], 9)
        self.assertEqual(period['actual_end_date'], date.fromisoformat(rows[10]['nav_date']).isoformat())
        self.assertIsNone(actual['annualized_return_1y'])

    def test_invalid_adjusted_value_is_not_an_observation(self):
        for invalid in (0, -1, "invalid", float("nan"), float("inf")):
            with self.subTest(invalid=invalid):
                rows = nav_rows()
                rows[10]["adj_nav"] = invalid
                actual = frame_service(rows).get_fund_performance("UNIT.TEST")
                self.assertEqual(actual['periods']['1y']['methodology']['missing_observations'], 1)
                self.assertNotIn('sharpe_ratio', actual['periods']['1y']['observed_metrics'])

    def test_price_adjustment_factors_never_generate_adjusted_nav(self):
        rows = nav_rows()
        for row in rows:
            row.pop("adj_nav")
        selected = [row for index, row in enumerate(rows) if index != 10]
        factors = [{"trade_date": row["nav_date"], "adj_factor": 3.0} for row in selected]
        service = frame_service(rows, factors)
        actual = service.get_fund_performance("UNIT.TEST")
        self.assertEqual(actual['periods']['1y']['observed_metrics'], {})
        self.assertEqual(service._pro.adj_calls, [])

    def test_money_market_adjusted_gap_keeps_real_yield_evidence(self):
        rows = nav_rows()
        for index, row in enumerate(rows):
            row.update(unit_nav=1.0, accum_nav=None, adj_nav=13940.0 + index * 0.4)
        rows[10]["adj_nav"] = None
        actual = frame_service(rows).get_fund_performance("UNIT.TEST")
        self.assertIsNone(actual["max_drawdown"])
        expected_yield = ((13940.0 + 19 * 0.4) / (13940.0 + 12 * 0.4)) ** (365 / 7) - 1
        self.assertAlmostEqual(actual["seven_day_annualized_yield"], expected_yield, places=8)
        self.assertEqual(actual["seven_day_yield_source"], "derived:tushare.fund_nav.adj_nav")

    def full_service(self):
        as_of = date(2026, 9, 30)
        days = sorted(get_trading_calendar().open_days(as_of - timedelta(days=1125), as_of))
        rows = [dict(nav_date=day.strftime('%Y%m%d'), unit_nav=5+i*.002, accum_nav=100+i,
                     adj_nav=1+i*.0001+(i%7)*.001) for i,day in enumerate(days)]
        service = frame_service(rows)
        service._fund_risk_calendars = {'UNIT.TEST': 'SSE'}
        return service, rows, as_of

    def test_complete_years_share_factory_dates_and_calendar(self):
        service, rows, as_of = self.full_service()
        with patch('services.tushare_service.datetime') as clock:
            clock.now.return_value = datetime.combine(as_of, datetime.min.time())
            actual = service.get_fund_performance('UNIT.TEST')
            risk = service.get_fund_risk_metrics('UNIT.TEST')
        for key in ('1y','3y'):
            self.assertEqual(actual['periods'][key]['coverage_status'], 'full')
            self.assertEqual(actual['periods'][key]['methodology']['calendar_status'], 'verified')
            period = actual['periods'][key]
            raw = [{'date':date.fromisoformat(row['nav_date']), 'adj_nav':row['adj_nav'], 'risk_calendar':'SSE'}
                   for row in rows if period['actual_start_date'].replace('-','') <= row['nav_date'] <= period['actual_end_date'].replace('-','')]
            expected = MetricFactory().calculate_return_metrics(raw)
            self.assertAlmostEqual(actual[f'annualized_return_{key}'], expected['annualized_return'], delta=1e-8)
        self.assertEqual(actual['volatility'], risk['annualized_volatility_1y'])
        self.assertEqual(actual['max_drawdown'], risk['max_drawdown_1y'])
        self.assertNotEqual(actual['return_1y'], actual['annualized_return_1y'])

    def test_missing_open_day_never_publishes_daily_risk_or_fills_forward(self):
        service, rows, as_of = self.full_service()
        rows[-50]['adj_nav'] = None
        with patch('services.tushare_service.datetime') as clock:
            clock.now.return_value = datetime.combine(as_of, datetime.min.time())
            risk = service.get_fund_risk_metrics('UNIT.TEST')
        self.assertEqual(risk['periods']['1y']['methodology']['missing_open_days'], 1)
        self.assertIsNone(risk['annualized_volatility_1y'])
        self.assertIsNone(risk['max_drawdown_1y'])
        self.assertEqual(risk['status'], 'partial')

    def test_no_default_market_or_fabricated_relative_risk(self):
        service, rows, as_of = self.full_service()
        with patch('services.tushare_service.datetime') as clock:
            clock.now.return_value = datetime.combine(as_of, datetime.min.time())
            risk = service.get_fund_risk_metrics('UNIT.TEST')
        for key in ('beta','alpha','tracking_error','information_ratio'):
            self.assertIsNone(risk[key])
        self.assertEqual(risk['relative_metrics_status'], 'requires_explicit_real_benchmark')

    def test_zero_denominator_is_undefined_not_zero_ratio(self):
        service, rows, as_of = self.full_service()
        for row in rows:
            row['adj_nav'] = 1.
        with patch('services.tushare_service.datetime') as clock:
            clock.now.return_value = datetime.combine(as_of, datetime.min.time())
            actual = service.get_fund_performance('UNIT.TEST')
        self.assertEqual(actual['volatility'], 0)
        self.assertIsNone(actual['sharpe_ratio'])
        self.assertIsNone(actual['calmar_ratio'])

    def test_source_failure_in_real_mode_does_not_return_mock_metrics(self):
        service = frame_service([])
        service.strict_no_mock = False
        with self.assertLogs('services.tushare_service', level='ERROR'):
            actual = service.get_fund_performance('UNIT.TEST')
        self.assertEqual(actual['status'], 'unavailable')
        service._mock_performance.assert_not_called()


if __name__ == "__main__":
    main()
    unittest.main()
