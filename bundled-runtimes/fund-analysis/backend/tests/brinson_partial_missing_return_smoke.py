import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from lib.brinson.attribution import BrinsonAttributor


def main():
    result = BrinsonAttributor().calculate_from_industry_inputs(
        portfolio_industries={
            "电子": {"weight": 0.4999, "return": 0.10},
            "未知": {"weight": 0.0001, "return": None},
        },
        benchmark_industries={
            "电子": {"weight": 0.50, "return": 0.09},
            "未知": {"weight": 0.0, "return": None},
        },
        fund_return=0.06,
        benchmark_return=0.05,
        portfolio_coverage=0.50,
        benchmark_coverage=1.0,
        return_coverage=0.9998,
    )
    assert result["status"] == "partial_evidence", result
    assert result["industry_details"], result
    assert result["coverage"]["skipped_portfolio_weight"] == 0.0001, result
    assert any("未进入效应分解" in item for item in result["missing_items"]), result
    print("OK Brinson preserves usable evidence when a tiny disclosed holding lacks returns")


if __name__ == "__main__":
    main()
