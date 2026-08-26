import math
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from services.public_holdings_risk_service import PublicHoldingsRiskService  # noqa: E402


class FakePro:
    def __init__(self):
        dates = pd.date_range("2025-01-02", periods=180, freq="B")
        date_values = [item.strftime("%Y%m%d") for item in dates]
        market_returns = [0.001 + 0.004 * math.sin(index / 8) for index in range(len(dates) - 1)]
        stock_returns = {
            "600000.SH": [1.2 * value + 0.002 * math.cos(index / 5) for index, value in enumerate(market_returns)],
            "000001.SZ": [0.8 * value + 0.0015 * math.sin(index / 6) for index, value in enumerate(market_returns)],
        }
        self.market = self._price_frame("000985.CSI", date_values, market_returns)
        self.prices = pd.concat([
            self._price_frame(code, date_values, returns)
            for code, returns in stock_returns.items()
        ], ignore_index=True)
        self.adjustments = self.prices[["ts_code", "trade_date"]].copy()
        self.adjustments["adj_factor"] = 1.0

    @staticmethod
    def _price_frame(code, dates, returns):
        prices = [100.0]
        for value in returns:
            prices.append(prices[-1] * (1 + value))
        return pd.DataFrame({"ts_code": code, "trade_date": dates, "close": prices})

    def daily(self, **_kwargs):
        return self.prices.copy()

    def adj_factor(self, **_kwargs):
        return self.adjustments.copy()

    def index_daily(self, **_kwargs):
        return self.market.copy()


class FakeDataService:
    def __init__(self):
        self.pro = FakePro()


def main() -> int:
    result = PublicHoldingsRiskService(FakeDataService()).analyze([
        {"stock_code": "600000.SH", "weight": 0.4, "weight_basis": "fund_nav"},
        {"stock_code": "000001.SZ", "weight": 0.3, "weight_basis": "fund_nav"},
    ], "2025Q4")

    assert result["status"] == "partial_evidence", result
    assert result["is_formal_barra"] is False, result
    assert result["observations"] >= 170, result
    assert 0.9 < result["portfolio_beta"] < 1.15, result
    assert result["observed_volatility"] > 0, result
    assert result["specific_volatility"] > 0, result
    assert result["market_benchmark"] == "000985.CSI", result
    assert 0 < result["modeled_r_squared"] < 1, result
    assert result["systematic_share_of_modeled_risk"] == result["risk_contributions"][0]["risk_share"], result
    shares = {item["factor"]: item["risk_share"] for item in result["risk_contributions"]}
    assert abs(shares["MARKET"] + shares["SPECIFIC"] - 1) < 1e-5, result
    assert result["fund_nav_coverage"] == 0.7, result
    print("OK public holdings risk model estimates market and specific risk without claiming formal Barra")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
