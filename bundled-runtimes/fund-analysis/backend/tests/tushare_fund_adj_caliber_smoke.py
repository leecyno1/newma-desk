import math
import os
import sys
from datetime import date, timedelta

import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from services.tushare_service import TushareDataService

DAYS = 25
EX_DIV_OFFSET = 10


class FakeProWithAdj:
    """分红基金：供应商复权净值连续，行情因子不得参与净值计算。"""

    def __init__(self):
        self.adj_calls = []

    def fund_nav(self, **kwargs):
        start = date.today() - timedelta(days=DAYS - 1)
        rows = []
        for offset in range(DAYS):
            if offset < EX_DIV_OFFSET:
                unit_nav = 1.05
                accum_nav = 1.05
            else:
                unit_nav = 1.00 + (offset - EX_DIV_OFFSET) * 0.001
                accum_nav = unit_nav + 0.05
            rows.append({
                "ts_code": "000001.OF",
                "nav_date": (start + timedelta(days=offset)).strftime("%Y%m%d"),
                "unit_nav": unit_nav,
                "accum_nav": accum_nav,
                "adj_nav": unit_nav if offset < EX_DIV_OFFSET else unit_nav * 1.05,
            })
        return pd.DataFrame(rows)

    def fund_adj(self, **kwargs):
        self.adj_calls.append(kwargs)
        start = date.today() - timedelta(days=DAYS - 1)
        return pd.DataFrame([
            {
                "ts_code": "000001.OF",
                "trade_date": (start + timedelta(days=offset)).strftime("%Y%m%d"),
                "adj_factor": 1.0 if offset < EX_DIV_OFFSET else 1.05,
            }
            for offset in range(DAYS)
        ])


class FakeProWithoutAdj:
    def fund_nav(self, **kwargs):
        start = date.today() - timedelta(days=DAYS - 1)
        return pd.DataFrame([
            {
                "ts_code": "000002.OF",
                "nav_date": (start + timedelta(days=offset)).strftime("%Y%m%d"),
                "unit_nav": 1.0 + offset * 0.001,
                "accum_nav": 1.0 + offset * 0.001,
            }
            for offset in range(DAYS)
        ])


class FakeProWithDirtyAdj:
    """复权列混入 0/负数/inf：非有限正数的虚假覆盖不得让 adj_nav 入选。"""

    def fund_nav(self, **kwargs):
        start = date.today() - timedelta(days=DAYS - 1)
        rows = []
        for offset in range(DAYS):
            if offset < 6:
                adj_nav = 1.0 + offset * 0.001
            elif offset < 10:
                adj_nav = 0.0
            elif offset < 13:
                adj_nav = -1.0
            elif offset < 16:
                adj_nav = float("inf")
            else:
                adj_nav = None
            rows.append({
                "ts_code": "000003.OF",
                "nav_date": (start + timedelta(days=offset)).strftime("%Y%m%d"),
                "unit_nav": 1.0 + offset * 0.001,
                "accum_nav": 1.0 + offset * 0.001,
                "adj_nav": adj_nav,
            })
        return pd.DataFrame(rows)


class FakeProWithInfTail:
    """复权列整体可用但末尾数行为 inf：inf 行不得泄漏进净值序列。"""

    def fund_nav(self, **kwargs):
        start = date.today() - timedelta(days=DAYS - 1)
        rows = []
        for offset in range(DAYS):
            adj_nav = float("inf") if offset >= DAYS - 5 else 1.0 + offset * 0.001
            rows.append({
                "ts_code": "000004.OF",
                "nav_date": (start + timedelta(days=offset)).strftime("%Y%m%d"),
                "unit_nav": 1.0 + offset * 0.001,
                "accum_nav": 1.0 + offset * 0.001,
                "adj_nav": adj_nav,
            })
        return pd.DataFrame(rows)


def build_service(fake_pro) -> TushareDataService:
    service = TushareDataService(token="test", mock_mode=True)
    service.mock_mode = False
    service._pro = fake_pro
    return service


def main() -> int:
    fake_pro = FakeProWithAdj()
    service = build_service(fake_pro)
    series = service.get_fund_nav("000001.OF", "2020-01-01", "2099-01-01")

    if fake_pro.adj_calls:
        raise AssertionError("get_fund_nav must not borrow ETF price adjustment factors")

    for item in series:
        expected_adj = round(item.get("unit_nav") * (1.0 if item.get("date") <= series[EX_DIV_OFFSET - 1].get("date") else 1.05), 6)
        if item.get("adj_nav") is None or abs(item.get("adj_nav") - expected_adj) > 1e-4:
            raise AssertionError(f"adj_nav must preserve the provider adjusted NAV: {item} vs {expected_adj}")
        if item.get("metric_nav_source") != "tushare.fund_nav.adj_nav":
            raise AssertionError(f"metric nav must prefer adjusted caliber with lineage: {item.get('metric_nav_source')}")
        if item.get("unit_nav") is None or item.get("nav") is None:
            raise AssertionError(f"unit nav must remain available for display: {item}")

    ex_div_row = series[EX_DIV_OFFSET]
    artificial_drop = 1.00 / 1.05 - 1
    if ex_div_row.get("daily_return") is None or abs(ex_div_row["daily_return"] - artificial_drop) < 1e-6:
        raise AssertionError(f"daily_return must not contain the artificial ex-dividend drop: {ex_div_row}")
    if abs(ex_div_row["daily_return"]) > 0.005:
        raise AssertionError(f"adjusted daily_return at ex-dividend must stay continuous: {ex_div_row}")

    fallback = build_service(FakeProWithoutAdj())
    fallback_series = fallback.get_fund_nav("000002.OF", "2020-01-01", "2099-01-01")
    if any(item.get("metric_nav_source") != "tushare.fund_nav.accum_nav" for item in fallback_series):
        raise AssertionError(f"without fund_adj the caliber must fall back to accum_nav: {fallback_series[0]}")

    dirty = build_service(FakeProWithDirtyAdj())
    dirty_series = dirty.get_fund_nav("000003.OF", "2020-01-01", "2099-01-01")
    if any(item.get("metric_nav_source") != "tushare.fund_nav.accum_nav" for item in dirty_series):
        raise AssertionError(f"adj_nav kept alive only by 0/negative/inf values must fall back to accum_nav: {dirty_series[0]}")
    if len(dirty_series) != DAYS:
        raise AssertionError(f"fallback caliber must keep the full series: got {len(dirty_series)}, expected {DAYS}")

    inf_tail = build_service(FakeProWithInfTail())
    inf_tail_series = inf_tail.get_fund_nav("000004.OF", "2020-01-01", "2099-01-01")
    if len(inf_tail_series) != DAYS or any(row['adj_nav'] is not None or row['daily_return'] is not None for row in inf_tail_series[-5:]):
        raise AssertionError("invalid NAV dates must remain explicit gaps without daily returns")
    if any(row['daily_return'] is not None for row in fallback_series):
        raise AssertionError("compatibility cumulative NAV must not generate adjusted daily returns")
    if fallback.get_fund_performance('000002.OF')['annualized_return_1y'] is not None:
        raise AssertionError("missing adjusted NAV must not generate annual performance")
    for name, series in (("dirty", dirty_series), ("inf_tail", inf_tail_series)):
        for item in series:
            for key, value in item.items():
                if isinstance(value, float) and not math.isfinite(value):
                    raise AssertionError(f"{name} series must never contain non-finite values: {key}={value} at {item.get('date')}")

    performance_service = build_service(fake_pro)
    performance = performance_service.get_fund_performance("000001.OF")
    if fake_pro.adj_calls:
        raise AssertionError("get_fund_performance must not borrow ETF price adjustment factors")
    adjusted_ret_1y = round((1.00 + (DAYS - 1 - EX_DIV_OFFSET) * 0.001) * 1.05 / 1.05 - 1, 4)
    accum_ret_1y = round(((1.00 + (DAYS - 1 - EX_DIV_OFFSET) * 0.001) + 0.05) / 1.05 - 1, 4)
    observed_return = performance['periods']['1y']['observed_metrics']['total_return']
    if not math.isclose(observed_return, adjusted_ret_1y):
        raise AssertionError(
            f"observed returns must use the adjusted caliber: expected {adjusted_ret_1y}, got {observed_return}"
        )
    if math.isclose(observed_return, accum_ret_1y):
        raise AssertionError(f"performance returns must not stay on the accum_nav caliber: {performance}")
    if performance.get('annualized_return_1y') is not None or performance.get('annualized_return_3y') is not None:
        raise AssertionError("25 days of NAV must not be published as full-year performance")

    print("OK Tushare fund NAV preserves provider adjusted NAV, with explicit fallback lineage")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
