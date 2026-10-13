import math
import sys
import unittest
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
from statistics import stdev
from types import SimpleNamespace
from unittest.mock import Mock

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.metric_factory import MetricFactory
from services.rolling_metric_service import RollingMetricService
from services.tushare_service import TushareDataService


def nav_from_returns(returns):
    nav = 1.0
    start = date(2026, 9, 1)
    rows = [{"date": start.isoformat(), "nav": nav}]
    for offset, value in enumerate(returns, start=1):
        nav *= 1 + value
        rows.append({"date": (start + timedelta(days=offset)).isoformat(), "nav": nav})
    return rows


def source_performance(nav_series):
    frame = pd.DataFrame([
        {"nav_date": row["date"].replace("-", ""), "unit_nav": row["nav"],
         "accum_nav": row["nav"], "adj_nav": row["nav"]}
        for row in nav_series
    ])
    service = TushareDataService.__new__(TushareDataService)
    service.mock_mode = False
    service.strict_no_mock = True
    service._pro = SimpleNamespace(fund_nav=Mock(return_value=frame))
    service._fetch_fund_adj_factors = Mock(side_effect=AssertionError("Unexpected data fetch"))
    result = service.get_fund_performance("UNIT.TEST")
    service._pro.fund_nav.assert_called_once()
    service._fetch_fund_adj_factors.assert_not_called()
    assert result['annualized_return_1y'] is None
    return result['periods']['1y']['observed_metrics']


class SortinoDownsideTests(unittest.TestCase):
    def test_equal_losses_have_nonzero_downside_risk(self):
        risk = MetricFactory(risk_free_rate=0).calculate_risk_metrics(nav_from_returns([-0.125] * 10))
        self.assertAlmostEqual(risk["downside_risk"], 0.125 * math.sqrt(252))
        self.assertAlmostEqual(risk["sortino_ratio"], -math.sqrt(252))

    def test_mixed_returns_use_full_sample_second_moment(self):
        risk = MetricFactory(trading_days=4, risk_free_rate=0).calculate_risk_metrics(
            nav_from_returns([-0.125, 0.25, 0.0, -0.125]),
        )
        self.assertAlmostEqual(risk["downside_risk"], math.sqrt(2 * 0.125**2))
        self.assertAlmostEqual(risk["sortino_ratio"], 0.0)

    def test_positive_returns_below_target_are_downside(self):
        risk = MetricFactory(trading_days=4, risk_free_rate=0.5).calculate_risk_metrics(
            nav_from_returns([0.0625] * 4),
        )
        self.assertAlmostEqual(risk["downside_risk"], 0.0625 * math.sqrt(4))
        self.assertAlmostEqual(risk["sortino_ratio"], -2.0)

    def test_numerator_and_denominator_use_same_target(self):
        risk = MetricFactory(trading_days=4, risk_free_rate=0.5).calculate_risk_metrics(
            nav_from_returns([-0.125, 0.25, 0.0, 0.5]),
        )
        downside = math.sqrt(0.25**2 + 0.125**2)
        self.assertAlmostEqual(risk["downside_risk"], downside)
        self.assertAlmostEqual(risk["sortino_ratio"], 0.125 / downside)

    def test_flat_nav_has_shortfall_against_positive_target(self):
        risk = MetricFactory().calculate_risk_metrics(nav_from_returns([0.0] * 10))
        self.assertAlmostEqual(risk["downside_risk"], 0.02 / math.sqrt(252))
        self.assertAlmostEqual(risk["sortino_ratio"], -math.sqrt(252))

    def test_single_loss_is_not_zero_risk(self):
        risk = MetricFactory(risk_free_rate=0).calculate_risk_metrics(nav_from_returns([-0.125]))
        self.assertAlmostEqual(risk["downside_risk"], 0.125 * math.sqrt(252))
        self.assertAlmostEqual(risk["sortino_ratio"], -math.sqrt(252))

    def test_negative_target_is_not_clamped_to_zero(self):
        risk = MetricFactory(trading_days=4, risk_free_rate=-0.5).calculate_risk_metrics(
            nav_from_returns([-0.25, -0.125, 0.0, 0.125]),
        )
        self.assertAlmostEqual(risk["downside_risk"], 0.125)
        self.assertAlmostEqual(risk["sortino_ratio"], 2.0)

    def test_zero_downside_keeps_existing_zero_output(self):
        factory = MetricFactory(trading_days=4, risk_free_rate=0.5)
        for returns in ([0.125] * 4, [0.25] * 4):
            with self.subTest(returns=returns):
                risk = factory.calculate_risk_metrics(nav_from_returns(returns))
                self.assertEqual(risk["downside_risk"], 0.0)
                self.assertEqual(risk["sortino_ratio"], 0.0)

    def test_empty_and_single_nav_keep_no_metrics(self):
        factory = MetricFactory()
        self.assertEqual(factory.calculate_risk_metrics([]), {})
        self.assertEqual(factory.calculate_risk_metrics(nav_from_returns([])), {})

    def test_volatility_sharpe_and_drawdown_are_unchanged(self):
        returns = [-0.125, 0.25, 0.0, -0.125]
        risk = MetricFactory(trading_days=4, risk_free_rate=0.5).calculate_risk_metrics(
            nav_from_returns(returns),
        )
        volatility = stdev(returns) * 2
        self.assertAlmostEqual(risk["annualized_volatility"], volatility)
        self.assertAlmostEqual(risk["sharpe_ratio"], -0.5 / volatility)
        self.assertAlmostEqual(risk["max_drawdown"], -0.125)
        self.assertAlmostEqual(risk["daily_return_mean"], 0.0)
        self.assertAlmostEqual(risk["daily_return_std"], stdev(returns))

    def test_source_equal_losses_do_not_return_zero_sortino(self):
        performance = source_performance(nav_from_returns([-0.125] * 10))
        self.assertAlmostEqual(performance["sortino_ratio"], -math.sqrt(252), delta=0.00005)

    def test_source_and_factory_share_default_target(self):
        for returns in (
            [-0.125] * 10,
            [0.0] * 10,
            [0.00001] * 10,
            [0.001] * 10,
            [-0.02, 0.03, -0.01, 0.02, 0.0] * 2,
        ):
            with self.subTest(returns=returns):
                nav_series = nav_from_returns(returns)
                result = source_performance(nav_series)
                risk = MetricFactory().calculate_risk_metrics(nav_series)
                if risk['downside_risk'] == 0:
                    self.assertIsNone(result['sortino_ratio'])
                else:
                    self.assertAlmostEqual(result["sortino_ratio"], risk["sortino_ratio"], delta=0.00005)

    def test_source_risk_metrics_share_factory_target_and_units(self):
        returns = [-0.125, 0.25, 0.0, -0.125, 0.0] * 2
        result = source_performance(nav_from_returns(returns))
        expected = MetricFactory().calculate_risk_metrics(nav_from_returns(returns))
        for key in ('sharpe_ratio', 'annualized_volatility', 'max_drawdown'):
            self.assertAlmostEqual(result[key], expected[key])
        self.assertEqual(result['positive_return_ratio'], 0.2)

    def test_metric_records_keep_finite_decimal_values(self):
        nav_series = nav_from_returns([-0.125] * 10)
        records = MetricFactory(risk_free_rate=0).build_metric_records(
            "fund", "UNIT.TEST", date(2026, 9, 11), nav_series, window="all",
        )
        by_name = {row["metric_name"]: row for row in records}
        for name in ("downside_risk", "sortino_ratio"):
            value = by_name[name]["metric_value"]
            self.assertIsInstance(value, Decimal)
            self.assertTrue(value.is_finite())
            self.assertEqual(by_name[name]["metric_unit"], "ratio")
        self.assertAlmostEqual(float(by_name["sortino_ratio"]["metric_value"]), -math.sqrt(252))

    def test_rolling_snapshot_uses_correct_downside_before_cutoff(self):
        series = nav_from_returns([-0.125] * 10 + [0.5] * 5)
        records = RollingMetricService(
            windows={"10d": 10}, metric_factory=MetricFactory(risk_free_rate=0),
        ).calculate_for_nav_series(series, "fund", "UNIT.TEST", as_of_date=date(2026, 9, 11))
        by_name = {row["metric_name"]: row for row in records}
        self.assertAlmostEqual(float(by_name["sortino_ratio"]["metric_value"]), -math.sqrt(252))
        self.assertAlmostEqual(float(by_name["downside_risk"]["metric_value"]), 0.125 * math.sqrt(252))
        self.assertEqual(by_name["sortino_ratio"]["details"]["window_end_date"], date(2026, 9, 11))
        self.assertEqual(by_name["sortino_ratio"]["window"], "10d")


if __name__ == "__main__":
    unittest.main()
