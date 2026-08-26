import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from lib.holding_weight_validation import (
    INVALID_WEIGHT_SCALE,
    VALID_WEIGHT,
    normalize_holding_weights,
    validate_fund_nav_weights,
)
from services.holding_style_factor_service import HoldingStyleFactorService
from services.performance_attribution_service import PerformanceAttributionService


class DataService:
    pro = object()


def main():
    normal = [
        {"stock_code": "600000.SH", "weight": 0.30, "weight_basis": "fund_nav"},
        {"stock_code": "000001.SZ", "weight": 0.20, "weight_basis": "fund_nav"},
    ]
    assert validate_fund_nav_weights(normal).status == VALID_WEIGHT

    single_overflow = [
        {
            "stock_code": "600000.SH",
            "weight": 1.20,
            "fund_nav_weight": 1.20,
            "equity_portfolio_weight": 0.50,
            "weight_basis": "fund_nav",
        }
    ]
    normalized, validation = normalize_holding_weights(single_overflow)
    assert validation.status == INVALID_WEIGHT_SCALE, validation
    assert normalized[0]["weight"] is None, normalized
    assert normalized[0]["fund_nav_weight"] is None, normalized
    assert normalized[0]["weight_basis"] == "equity_portfolio", normalized
    assert normalized[0]["weight_validation_status"] == INVALID_WEIGHT_SCALE, normalized

    total_overflow = [
        {"stock_code": "600000.SH", "weight": 0.60, "weight_basis": "fund_nav"},
        {"stock_code": "000001.SZ", "weight": 0.50, "weight_basis": "fund_nav"},
    ]
    assert validate_fund_nav_weights(total_overflow).status == INVALID_WEIGHT_SCALE

    style = HoldingStyleFactorService(DataService()).analyze(total_overflow, "2026Q1")
    assert style["status"] == "insufficient_evidence", style
    assert style["source"] == "invalid_weight_scale_gate", style
    assert not style["descriptors"], style

    cross_market_style = HoldingStyleFactorService(DataService()).analyze([
        {"stock_code": "600000.SH", "weight": 0.18, "weight_basis": "fund_nav"},
        {"stock_code": "01109.HK", "weight": 0.31, "weight_basis": "fund_nav"},
    ], "2026Q1")
    assert cross_market_style["status"] == "insufficient_evidence", cross_market_style
    assert cross_market_style["holdings_disclosed_weight"] == 0.49, cross_market_style
    assert cross_market_style["model_eligible_weight"] == 0.18, cross_market_style
    assert cross_market_style["cross_market_excluded_weight"] == 0.31, cross_market_style
    assert "合计覆盖基金净值的 49.0%" in cross_market_style["missing_items"][0], cross_market_style
    assert "跨市场持仓 31.0%" in cross_market_style["missing_items"][0], cross_market_style

    attribution = PerformanceAttributionService()
    barra = attribution._barra_evidence({"type": "股票型"}, total_overflow, {}, "2026Q1")
    assert barra["status"] == "insufficient_evidence", barra
    assert barra["source"] == "invalid_weight_scale_gate", barra
    assert not barra["industry_exposures"], barra

    brinson = attribution._brinson_evidence(
        data_service=DataService(),
        fund={"type": "股票型"},
        holdings=total_overflow,
        benchmark_code="000300.SH",
        benchmark_source="test",
        benchmark_detail={},
        attribution_quarter="2026Q2",
        holding_quarter="2026Q1",
    )
    assert brinson["status"] == "insufficient_evidence", brinson
    assert brinson["source"] == "invalid_weight_scale_gate", brinson
    assert not brinson["effects"], brinson
    print("OK invalid holding weight scales cannot enter style, Barra, or Brinson")


if __name__ == "__main__":
    main()
