import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from services.fund_holding_weight_service import FundHoldingWeightService


class AllocationService:
    def __init__(self, history):
        self.history = history
        self.calls = []

    def get(self, wind_code, limit=20, refresh=False):
        self.calls.append((wind_code, limit, refresh))
        return {"status": "available", "history": self.history}


def main():
    allocation = AllocationService([{
        "report_date": "2026-06-30",
        "stock_ratio": 0.8,
        "net_asset_yi": 10,
        "source": "eastmoney.fundf10.asset_allocation",
        "source_url": "https://fundf10.eastmoney.com/zcpz_000001.html",
    }])
    service = FundHoldingWeightService(allocation)
    result = service.enrich("000001.OF", "2026Q2", [
        {"stock_code": "600000.SH", "market_cap": 500_000_000, "equity_portfolio_weight": 0.7, "weight_basis": "equity_portfolio"},
        {"stock_code": "000001.SZ", "market_cap": 200_000_000, "equity_portfolio_weight": 0.3, "weight_basis": "equity_portfolio"},
    ], refresh_allocation=True)
    assert result["changed"] is True, result
    assert result["weight_validation"]["status"] == "valid", result
    assert result["weight_source"] == "eastmoney.asset_allocation.net_asset_yi", result
    assert [round(item["fund_nav_weight"], 4) for item in result["holdings"]] == [0.5, 0.2], result
    assert allocation.calls == [("000001.OF", 20, True)]

    mismatch = FundHoldingWeightService(AllocationService([{
        "report_date": "2026-03-31",
        "stock_ratio": 0.8,
        "net_asset_yi": 10,
    }])).enrich("000001.OF", "2026Q2", result["holdings"][:1])
    assert mismatch["weight_source"] == "existing_fund_nav_weight", mismatch

    rejected = FundHoldingWeightService(AllocationService([{
        "report_date": "2026-06-30",
        "stock_ratio": 0.6,
        "net_asset_yi": 10,
    }])).enrich("000001.OF", "2026Q2", [
        {"stock_code": "600000.SH", "market_cap": 900_000_000, "weight_basis": "equity_portfolio"},
    ])
    assert rejected["changed"] is False, rejected
    assert rejected["weight_source"] == "allocation_consistency_gate", rejected
    assert rejected["weight_validation"]["status"] == "missing_fund_nav_weight", rejected

    print("OK holding weights use same-period public net assets and reject inconsistent denominators")


if __name__ == "__main__":
    main()
