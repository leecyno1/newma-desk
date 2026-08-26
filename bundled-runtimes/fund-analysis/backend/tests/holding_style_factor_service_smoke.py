import os
import sys

import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from services.holding_style_factor_service import HoldingStyleFactorService


class Pro:
    def daily(self, **_kwargs):
        dates = pd.bdate_range("2025-01-02", "2026-03-31").strftime("%Y%m%d")
        rows = []
        for index, date in enumerate(dates):
            rows.append({"ts_code": "600000.SH", "trade_date": date, "close": 10 + index * 0.01})
            rows.append({"ts_code": "000001.SZ", "trade_date": date, "close": 12 + index * 0.008})
        return pd.DataFrame(rows)

    def adj_factor(self, **_kwargs):
        dates = pd.bdate_range("2025-01-02", "2026-03-31").strftime("%Y%m%d")
        return pd.DataFrame([
            {"ts_code": code, "trade_date": date, "adj_factor": 1.0}
            for code in ("600000.SH", "000001.SZ")
            for date in dates
        ])

    def index_daily(self, **_kwargs):
        dates = pd.bdate_range("2025-01-02", "2026-03-31").strftime("%Y%m%d")
        return pd.DataFrame([
            {"ts_code": "000300.SH", "trade_date": date, "close": 4000 + index * 2}
            for index, date in enumerate(dates)
        ])

    def daily_basic(self, ts_code, **_kwargs):
        return pd.DataFrame([
            {"ts_code": ts_code, "trade_date": "20260330", "turnover_rate": 1.0, "pb": 2.0, "total_mv": 1000000},
            {"ts_code": ts_code, "trade_date": "20260331", "turnover_rate": 2.0, "pb": 2.5, "total_mv": 1200000},
        ])

    def fina_indicator(self, ts_code, **_kwargs):
        return pd.DataFrame([
            {"ts_code": ts_code, "ann_date": "20260320", "end_date": "20251231", "debt_to_assets": 40, "q_sales_yoy": 20, "q_profit_yoy": 10},
            {"ts_code": ts_code, "ann_date": "20260420", "end_date": "20260331", "debt_to_assets": 90, "q_sales_yoy": 90, "q_profit_yoy": 90},
        ])


class DataService:
    def __init__(self):
        self.pro = Pro()


def main():
    HoldingStyleFactorService._stock_cache.clear()
    HoldingStyleFactorService._market_return_cache.clear()
    result = HoldingStyleFactorService(DataService()).analyze([
        {"stock_code": "600000.SH", "weight": 0.30, "weight_basis": "fund_nav"},
        {"stock_code": "000001.SZ", "weight": 0.20, "weight_basis": "fund_nav"},
    ], "2026Q1")
    assert result["status"] == "partial_evidence", result
    factors = {item["factor"]: item for item in result["descriptors"]}
    for required in ("SIZE", "BTOP", "BETA", "MOMENTUM", "RESVOL", "LIQUIDITY", "LEVERAGE", "GROWTH"):
        assert required in factors, (required, result)
    assert factors["LEVERAGE"]["exposure"] == 0.4, factors["LEVERAGE"]
    assert factors["GROWTH"]["exposure"] == 0.15, factors["GROWTH"]
    assert result["holdings_disclosed_weight"] == 0.5, result
    print("OK real holding style descriptors are weighted, dated, and free of financial look-ahead")


if __name__ == "__main__":
    main()
