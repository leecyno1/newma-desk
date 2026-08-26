import os
import sys

import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from services.performance_attribution_service import PerformanceAttributionService
from services.tushare_service import TushareDataService


class Pro:
    def __init__(self, net_asset=None, total_netasset=None):
        self.net_asset = net_asset
        self.total_netasset = total_netasset

    def fund_portfolio(self, **_kwargs):
        return pd.DataFrame([
            {
                "ts_code": "000001.OF",
                "ann_date": "20260721",
                "end_date": "20260630",
                "symbol": "600000.SH",
                "mkv": 100.0,
                "amount": 10.0,
                "stk_mkv_ratio": 50.0,
            }
        ])

    def fund_nav(self, **_kwargs):
        return pd.DataFrame([{
            "net_asset": self.net_asset,
            "total_netasset": self.total_netasset,
        }])

    def stock_basic(self, **_kwargs):
        return pd.DataFrame([{"ts_code": "600000.SH", "name": "浦发银行", "industry": "银行"}])

    def hk_basic(self, **_kwargs):
        return pd.DataFrame([{"ts_code": "01109.HK", "name": "华润置地", "market": "主板"}])


def service(net_asset=None, total_netasset=None):
    instance = object.__new__(TushareDataService)
    instance.mock_mode = False
    instance.strict_no_mock = True
    instance._pro = Pro(net_asset, total_netasset)
    instance.get_hang_seng_index_snapshot = lambda refresh=False: {
        "constituents": [
            {"constituent_code": "01109.HK", "industry": "地产建筑"},
        ],
    }
    return instance


def main():
    equity_only = service().get_fund_holdings("000001.OF", "2026Q2")[0]
    assert equity_only["weight"] is None
    assert equity_only["fund_nav_weight"] is None
    assert equity_only["equity_portfolio_weight"] == 0.5
    assert equity_only["weight_basis"] == "equity_portfolio"

    converted = service(1000.0).get_fund_holdings("000001.OF", "2026Q2")[0]
    assert converted["fund_nav_weight"] == 0.1
    assert converted["weight"] == 0.1
    assert converted["equity_portfolio_weight"] == 0.5
    assert converted["weight_basis"] == "fund_nav"
    assert converted["fund_net_asset_basis"] == "net_asset"

    multi_share = service(net_asset=50.0, total_netasset=1000.0).get_fund_holdings("000001.OF", "2026Q2")[0]
    assert multi_share["fund_nav_weight"] == 0.1, multi_share
    assert multi_share["fund_net_asset_basis"] == "total_netasset", multi_share

    invalid_scale = service(50.0).get_fund_holdings("000001.OF", "2026Q2")[0]
    assert invalid_scale["weight"] is None, invalid_scale
    assert invalid_scale["fund_nav_weight"] is None, invalid_scale
    assert invalid_scale["equity_portfolio_weight"] == 0.5, invalid_scale
    assert invalid_scale["weight_basis"] == "equity_portfolio", invalid_scale
    assert invalid_scale["weight_validation_status"] == "invalid_weight_scale", invalid_scale

    wrong_period = service()
    wrong_period.pro.fund_portfolio = lambda **_kwargs: pd.DataFrame([{
        "ts_code": "000001.OF",
        "ann_date": "20260721",
        "end_date": "20260331",
        "symbol": "600000.SH",
        "mkv": 100.0,
        "amount": 10.0,
        "stk_mkv_ratio": 50.0,
    }])
    assert wrong_period.get_fund_holdings("000001.OF", "2026Q2") == []

    cross_market = service(1000.0)
    cross_market.pro.fund_portfolio = lambda **_kwargs: pd.DataFrame([
        {
            "ann_date": "20260721",
            "end_date": "20260630",
            "symbol": "01109.HK",
            "mkv": 100.0,
            "amount": 10.0,
            "stk_mkv_ratio": 50.0,
        },
        {
            "ann_date": "20260721",
            "end_date": "20260630",
            "symbol": "1109.HK",
            "mkv": 100.0,
            "amount": 10.0,
            "stk_mkv_ratio": 50.0,
        },
    ])
    normalized_hk = cross_market.get_fund_holdings("001583.OF", "2026Q2")
    assert len(normalized_hk) == 1, normalized_hk
    assert normalized_hk[0]["stock_code"] == "01109.HK", normalized_hk
    assert normalized_hk[0]["stock_name"] == "华润置地", normalized_hk
    assert normalized_hk[0]["industry"] == "地产建筑", normalized_hk
    assert normalized_hk[0]["fund_nav_weight"] == 0.1, normalized_hk

    attribution = PerformanceAttributionService()
    barra = attribution._barra_evidence(
        {"type": "股票型"},
        [equity_only],
        {},
        "2026Q2",
    )
    assert barra["status"] == "insufficient_evidence"
    assert not barra["industry_exposures"]

    brinson = attribution._brinson_evidence(
        data_service=object(),
        fund={"type": "股票型"},
        holdings=[equity_only],
        benchmark_code="000300.SH",
        benchmark_source="test",
        benchmark_detail={},
        attribution_quarter="2026Q3",
        holding_quarter="2026Q2",
    )
    assert brinson["status"] == "insufficient_evidence"
    assert "占股票市值比" in brinson["missing_items"][0]
    print("OK holdings keep equity-portfolio and fund-NAV weights separate")


if __name__ == "__main__":
    main()
