import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from database import get_engine, init_database
from services.investment_analysis_service import InvestmentAnalysisService


def pick_metric_rich_fund() -> str:
    # 冒烟依赖真实指标数据：动态选取 1y 指标快照最多的基金，避免硬编码基金随数据集变化失效。
    from sqlalchemy import text

    with get_engine().connect() as conn:
        row = conn.execute(text(
            "SELECT target_id FROM metric_snapshots WHERE metric_window = '1y'"
            " GROUP BY target_id ORDER BY COUNT(*) DESC LIMIT 1"
        )).fetchone()
    if not row:
        raise AssertionError("metric_snapshots has no 1y metrics to run the smoke")
    return str(row[0])


def main() -> int:
    init_database()

    wind_code = pick_metric_rich_fund()
    service = InvestmentAnalysisService()
    factor_lens = service.factor_lens(wind_code)
    if factor_lens.get("fund", {}).get("wind_code") != wind_code:
        raise AssertionError(f"Factor lens should identify fund: {factor_lens}")
    if len(factor_lens.get("style_exposures", [])) < 5:
        raise AssertionError(f"Factor lens should return multiple exposures: {factor_lens}")
    if not factor_lens.get("risk_contributions"):
        raise AssertionError(f"Factor lens should include risk contributions: {factor_lens}")

    attribution = service.advanced_attribution(wind_code)
    returns = attribution.get("returns", {})
    if "active" not in returns:
        raise AssertionError(f"Attribution should include active return: {attribution}")
    if len(attribution.get("effects", [])) < 3:
        raise AssertionError(f"Attribution should include effect breakdown: {attribution}")

    print("OK advanced factor lens and fund attribution")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
