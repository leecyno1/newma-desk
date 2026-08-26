import json
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from services.hong_kong_market_service import HongKongMarketDataService
from services.hang_seng_index_service import HangSengIndexService
from services.performance_attribution_service import PerformanceAttributionService


class Response:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        return json.dumps(self.payload).encode("utf-8")


class Pro:
    def index_daily(self, **_kwargs):
        return pd.DataFrame([
            {"trade_date": "20260401", "close": 100.0},
            {"trade_date": "20260630", "close": 110.0},
        ])

    def fund_nav(self, **_kwargs):
        return pd.DataFrame([
            {"nav_date": "20260401", "adj_nav": 1.0},
            {"nav_date": "20260630", "adj_nav": 1.05},
        ])

    def index_weight(self, **_kwargs):
        return pd.DataFrame([
            {"trade_date": "20260331", "con_code": "600000.SH", "weight": 100.0},
        ])

    def daily(self, trade_date):
        close = 10.0 if trade_date == "20260401" else 11.0
        return pd.DataFrame([{"ts_code": "600000.SH", "close": close}])

    def adj_factor(self, **_kwargs):
        return pd.DataFrame([{"ts_code": "600000.SH", "adj_factor": 1.0}])

    def stock_basic(self, **_kwargs):
        return pd.DataFrame([{"ts_code": "600000.SH", "name": "浦发银行", "industry": "银行"}])

    def hk_daily(self, **_kwargs):
        return pd.DataFrame([
            {"ts_code": "01109.HK", "trade_date": "20260401", "close": 20.0},
            {"ts_code": "01109.HK", "trade_date": "20260630", "close": 22.0},
        ])


class DataService:
    def __init__(self):
        self.pro = Pro()

    def get_benchmark_nav(self, benchmark_code, start_date, end_date):
        _ = (start_date, end_date)
        closes = {
            "000300.SH": (100.0, 110.0),
            "HSI": (100.0, 120.0),
            "H11001.CSI": (100.0, 101.0),
        }[benchmark_code]
        return [
            {"date": "2026-04-01", "nav": closes[0]},
            {"date": "2026-06-30", "nav": closes[1]},
        ]

    def get_hong_kong_stock_returns(self, stock_codes, start_date, end_date):
        _ = (stock_codes, start_date, end_date)
        return {
            "returns": {"01109.HK": 0.1, "00700.HK": 0.3},
            "source": "tencent.hk.fqkline",
            "adjustment": "unadjusted_close",
        }

    def get_hang_seng_index_snapshot_before(self, _as_of_date):
        return {
            "index_code": "HSI",
            "as_of_date": "2026-03-31",
            "source": "hang_seng_indexes.official",
            "constituents": [
                {"constituent_code": "01109.HK", "weight": 0.6, "industry": "地产建筑"},
                {"constituent_code": "00700.HK", "weight": 0.3, "industry": "信息技术"},
            ],
        }


def main():
    official_constituents = HangSengIndexService.parse_constituents({
        "indexSeriesList": [{"indexList": [{"constituentContent": [
            {"code": "700", "constituentName": "TENCENT", "type": "O"},
        ]}]}],
    })
    assert official_constituents[0]["constituent_code"] == "00700.HK", official_constituents
    official_industries = HangSengIndexService.parse_industry_map({
        "indexSeriesList": [{"indexList": [{
            "indexName": "Hang Seng Composite Industry Index - Information Technology",
            "constituentContent": [{"code": "700"}],
        }]}],
    })
    assert official_industries["00700.HK"] == "信息技术", official_industries
    official_weights = HangSengIndexService.parse_factsheet_weights(
        "0700 KYG875721634 TENCENT Information Technology Other HK-listed Mainland Co. 7.94"
    )
    assert official_weights["00700.HK"]["weight"] == 0.0794, official_weights
    assert HangSengIndexService.parse_factsheet_date("Hang Seng Index\nJuly 2026") == "2026-07-31"

    public_market = HongKongMarketDataService(
        opener=lambda *_args, **_kwargs: Response({
            "data": {
                "hk01109": {
                    "day": [
                        ["2026-04-01", "20.0", "20.0"],
                        ["2026-06-30", "22.0", "22.0"],
                    ],
                },
            },
        })
    ).get_period_returns(["01109.HK"], "20260401", "20260630")
    assert public_market["returns"] == {"01109.HK": 0.1}, public_market

    components = [
        {"code": "000300.SH", "name": "沪深300", "asset": "mainland_equity", "weight": 45.0},
        {"code": "HSI", "name": "恒生指数", "asset": "hong_kong_equity", "weight": 45.0},
        {"code": "H11001.CSI", "name": "中证全债", "asset": "fixed_income", "weight": 10.0},
    ]
    result = PerformanceAttributionService()._tushare_brinson(
        data_service=DataService(),
        fund={"wind_code": "001583.OF", "type": "股票型"},
        holdings=[
            {"stock_code": "600000.SH", "fund_nav_weight": 0.3, "industry": "银行"},
            {"stock_code": "01109.HK", "fund_nav_weight": 0.2, "industry": "未知"},
        ],
        benchmark_code="000300.SH",
        benchmark_source="fund_declared_benchmark_equity_component",
        benchmark_detail={"benchmark_name": "沪深300", "contract_components": components},
        attribution_quarter="2026Q2",
        holding_quarter="2026Q1",
    )

    assert result["returns"]["benchmark"] == 0.136, result
    assert result["returns"]["active"] == -0.086, result
    assert result["coverage"]["holding_returns"] == 1.0, result
    details = {item["industry"]: item for item in result["industry_detail"]}
    assert details["银行"]["benchmark_weight"] == 0.45, details
    assert details["地产建筑"]["benchmark_weight"] == 0.27, details
    assert details["地产建筑"]["portfolio_return"] == 0.1, details
    assert details["信息技术"]["benchmark_weight"] == 0.135, details
    assert details["港股-其他成分"]["benchmark_weight"] == 0.045, details
    assert details["固定收益"]["benchmark_weight"] == 0.1, details
    assert "tencent.hk.fqkline" in result["source"], result
    assert "hang_seng_indexes.official" in result["source"], result
    assert result["period"]["hong_kong_benchmark_weight_date"] == "2026-03-31", result
    assert any("恒生指数官方成分快照" in item for item in result["missing_items"]), result
    print("OK cross-market Brinson scales contract weights and uses real Hong Kong holding returns")


if __name__ == "__main__":
    main()
