import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from routes.funds import _holding_summary


def main():
    invalid = _holding_summary([
        {
            "stock_code": "600000.SH",
            "weight": None,
            "equity_portfolio_weight": 0.5,
            "weight_basis": "equity_portfolio",
            "weight_validation_status": "invalid_weight_scale",
            "industry": "银行",
        }
    ])
    assert invalid["weight_basis"] == "equity_portfolio", invalid
    assert invalid["top_ten_weight"] is None, invalid
    assert invalid["weight_validation"]["status"] == "invalid_weight_scale", invalid

    valid = _holding_summary([
        {"stock_code": "600000.SH", "weight": 0.3, "weight_basis": "fund_nav", "industry": "银行"},
        {"stock_code": "000001.SZ", "weight": 0.2, "weight_basis": "fund_nav", "industry": "银行"},
    ])
    assert valid["weight_basis"] == "fund_nav", valid
    assert valid["top_ten_weight"] == 0.5, valid
    assert valid["weight_validation"]["status"] == "valid", valid
    print("OK holding summaries disclose invalid scales and keep normal fund-NAV weights")


if __name__ == "__main__":
    main()
