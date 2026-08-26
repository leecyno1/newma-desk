import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from lib.brinson.attribution import BrinsonAttributor
from services.performance_attribution_service import PerformanceAttributionService
from services.holding_style_factor_service import HoldingStyleFactorService


class DataService:
    pro = object()


def main():
    brinson = BrinsonAttributor().calculate_from_industry_inputs(
        portfolio_industries={"电子": {"weight": 0.01, "return": 0.10}},
        benchmark_industries={"电子": {"weight": 0.50, "return": 0.08}},
        fund_return=0.06,
        benchmark_return=0.05,
        portfolio_coverage=0.01,
        benchmark_coverage=1.0,
        return_coverage=1.0,
    )
    assert brinson["status"] == "insufficient_evidence", brinson
    assert brinson["allocation_effect"] is None, brinson
    assert brinson["coverage"]["portfolio_holdings"] == 0.01, brinson

    style = HoldingStyleFactorService(DataService()).analyze(
        [{"stock_code": "600000.SH", "weight": 0.01, "weight_basis": "fund_nav"}],
        "2026Q1",
    )
    assert style["status"] == "insufficient_evidence", style
    assert not style["descriptors"], style
    assert style["holdings_disclosed_weight"] == 0.01, style

    barra = PerformanceAttributionService()._barra_evidence(
        {"type": "指数型"},
        [{"stock_code": "600000.SH", "industry": "银行", "weight": 0.01, "weight_basis": "fund_nav"}],
        {},
        "2026Q1",
        style,
    )
    assert barra["status"] == "insufficient_evidence", barra
    assert not barra["descriptor_model_ready"], barra
    assert not barra["industry_exposures"], barra
    print("OK low disclosed-holding coverage cannot be presented as whole-fund style or Brinson effects")


if __name__ == "__main__":
    main()
