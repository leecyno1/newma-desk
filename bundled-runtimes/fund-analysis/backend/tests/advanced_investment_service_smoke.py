import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from database import init_database
from services.investment_analysis_service import InvestmentAnalysisService


def main() -> int:
    init_database()

    service = InvestmentAnalysisService()
    factor_lens = service.factor_lens("000002.OF")
    if factor_lens.get("fund", {}).get("wind_code") != "000002.OF":
        raise AssertionError(f"Factor lens should identify fund: {factor_lens}")
    if len(factor_lens.get("style_exposures", [])) < 5:
        raise AssertionError(f"Factor lens should return multiple exposures: {factor_lens}")
    if not factor_lens.get("risk_contributions"):
        raise AssertionError(f"Factor lens should include risk contributions: {factor_lens}")

    attribution = service.advanced_attribution("000002.OF")
    returns = attribution.get("returns", {})
    if "active" not in returns:
        raise AssertionError(f"Attribution should include active return: {attribution}")
    if len(attribution.get("effects", [])) < 3:
        raise AssertionError(f"Attribution should include effect breakdown: {attribution}")

    print("OK advanced factor lens and fund attribution")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
