import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from services.cross_market_holding_profile_service import CrossMarketHoldingProfileService
from services.performance_attribution_service import PerformanceAttributionService


class IndustryRepo:
    def get_latest(self, index_code):
        assert index_code == "HSCI-INDUSTRY"
        return {
            "as_of_date": "2026-07-31",
            "source": "hang_seng_indexes.official",
            "constituents": [
                {"constituent_code": "01109.HK", "industry": "地产建筑"},
                {"constituent_code": "02328.HK", "industry": "金融"},
            ],
        }


def main():
    holdings = [
        {"stock_code": "600000.SH", "stock_name": "浦发银行", "industry": "银行", "fund_nav_weight": 0.3},
        {"stock_code": "01109.HK", "stock_name": "华润置地", "industry": "未知", "fund_nav_weight": 0.2},
        {"stock_code": "02328.HK", "stock_name": "中国财险", "industry": "未知", "fund_nav_weight": 0.1},
    ]
    profile = CrossMarketHoldingProfileService(IndustryRepo()).analyze(holdings, "2026Q2")
    markets = {item["market_code"]: item for item in profile["markets"]}
    assert profile["total_disclosed_weight"] == 0.6, profile
    assert markets["CN_A"]["disclosed_weight"] == 0.3, markets
    assert markets["HK"]["disclosed_weight"] == 0.3, markets
    assert markets["HK"]["share_of_disclosed"] == 0.5, markets
    assert markets["HK"]["industry_exposures"][0]["industry"] == "地产建筑", markets
    assert markets["HK"]["industry_source"] == "hang_seng_indexes.official", markets
    assert "已披露持仓以港股为主" in profile["labels"], profile

    barra = PerformanceAttributionService()._barra_evidence(
        fund={"type": "混合型"},
        holdings=holdings,
        style_factors={},
        holding_quarter="2026Q2",
        style_factor_payload={},
    )
    assert barra["market_scope"] == "china_a_share", barra
    assert barra["industry_exposures"] == {"银行": 0.3}, barra
    assert barra["model_eligible_weight"] == 0.3, barra
    assert barra["cross_market_excluded_weight"] == 0.3, barra
    print("OK A-share Barra evidence and Hong Kong holding profile are calculated separately")


if __name__ == "__main__":
    main()
