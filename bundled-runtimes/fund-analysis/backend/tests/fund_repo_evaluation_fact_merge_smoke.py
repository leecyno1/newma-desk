import os
import sys
import atexit

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from database import init_database
from repositories.fund_repo import FundRepo
from repositories.nav_repo import NavRepo
from smoke_cleanup import cleanup_fund_codes


def main() -> int:
    init_database()
    repo = FundRepo()
    wind_code = "FACT.MERGE.TEST"
    nav_code = "BENCH.MERGE.TEST"
    fixture_codes = [wind_code, nav_code]
    cleanup_fund_codes(fixture_codes)
    atexit.register(cleanup_fund_codes, fixture_codes)

    if not repo.upsert_fund(wind_code, {
        "name": "评价事实合并测试基金",
        "type": "货币型",
        "performance_data": {
            "seven_day_annualized_yield": 0.019,
            "seven_day_yield_source": "derived:tushare.fund_nav.adj_nav",
        },
        "raw_data": {
            "source": "tushare",
            "info": {"management_fee": 0.30, "custodian_fee": 0.07},
        },
    }):
        raise AssertionError("Initial evaluation facts could not be persisted")

    if not repo.upsert_fund(wind_code, {
        "name": "评价事实合并测试基金",
        "type": "货币型",
        "performance_data": {"annualized_return_1y": 0.021},
        "risk_metrics": {"max_drawdown_1y": -0.0004},
        "raw_data": {
            "source": "tushare",
            "ranking_metrics": {"source": "tushare.fund_nav"},
        },
    }):
        raise AssertionError("Rolling evaluation facts could not be merged")

    fund = repo.get_fund(wind_code) or {}
    performance = fund.get("performance_data") or {}
    raw_data = fund.get("raw_data") or {}
    if performance.get("seven_day_annualized_yield") != 0.019:
        raise AssertionError(f"Rolling sync erased money-market evidence: {fund}")
    if performance.get("annualized_return_1y") != 0.021:
        raise AssertionError(f"Rolling metric was not merged: {fund}")
    if (raw_data.get("info") or {}).get("management_fee") != 0.30:
        raise AssertionError(f"Ranking sync erased fee evidence: {fund}")
    if not raw_data.get("ranking_metrics"):
        raise AssertionError(f"Ranking sync provenance was not retained: {fund}")

    nav_repo = NavRepo()
    nav_repo.upsert_nav_series(nav_code, [
        {"date": "2026-07-01", "nav": 1.0, "accum_nav": 1.0, "benchmark_nav": 4000.0},
        {"date": "2026-07-02", "nav": 1.01, "accum_nav": 1.01, "benchmark_nav": 4010.0},
    ])
    nav_repo.upsert_nav_series(nav_code, [
        {"date": "2026-07-01", "nav": 1.0, "accum_nav": 1.0},
        {"date": "2026-07-02", "nav": 1.01, "accum_nav": 1.01},
    ])
    persisted_nav = nav_repo.get_nav_series(nav_code)
    if [float(item["benchmark_nav"]) for item in persisted_nav] != [4000.0, 4010.0]:
        raise AssertionError(f"A later NAV sync erased real benchmark evidence: {persisted_nav}")

    cleanup_fund_codes(fixture_codes)
    print("OK repositories merge evaluation facts without erasing source evidence")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
