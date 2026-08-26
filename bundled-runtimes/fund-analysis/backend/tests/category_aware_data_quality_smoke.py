import os
import sys
from datetime import date, timedelta

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from services.data_quality_service import DataQualityService
from services.fund_manager_tenure_context import resolve_manager_tenure_context


def main() -> int:
    service = DataQualityService()
    standardized = {
        "status": "resolved",
        "strategy_family_key": "index_broad",
        "peer_group_key": "peer-index-hs300",
        "benchmark_mapping": {"benchmark_code": "000300.SH"},
    }
    context_check = service._check_research_context({}, standardized)
    if not context_check.get("passed") or context_check.get("source") != "standardized_classification":
        raise AssertionError(f"Standardized classification must replace duplicate profile fields: {context_check}")

    index_manager = service._check_manager_tenure(None, "index_broad")
    qdii_index_manager = service._check_manager_tenure(None, "qdii_index")
    money_manager = service._check_manager_tenure(None, "cash_management")
    if not all(item.get("not_applicable") for item in (index_manager, qdii_index_manager, money_manager)):
        raise AssertionError("Passive index and money-market quality must not require manager-tenure evidence")

    active_manager = service._check_manager_tenure(None, "active_equity_core")
    if active_manager.get("passed"):
        raise AssertionError("Active management quality must retain the manager-tenure requirement")

    china_market_year = [
        {"date": (date(2025, 7, 28) + timedelta(days=round(index * 382 / 248))).isoformat(), "nav": 1 + index / 1000}
        for index in range(249)
    ]
    if not service._check_nav_coverage(china_market_year).get("passed"):
        raise AssertionError("A full calendar year with 240+ China-market NAV observations must pass")
    if service._check_nav_coverage_from_metrics([
        {"metric_window": "1y", "metric_name": "observations", "metric_value": 239},
    ]).get("passed"):
        raise AssertionError("Fewer than 240 one-year NAV observations must remain insufficient")

    resolved = resolve_manager_tenure_context(
        {
            "manager_ids": ["经理甲"],
            "raw_data": {"manager_sync": {"manager_tenure_start": "2024-01-01"}},
        },
        {"manager_tenure_start": "2025-01-01"},
        {"start_date": "2023-11-07", "manager_ids": ["经理甲"], "source": "manager_fund_tenures"},
    )
    if resolved.get("start_date") != "2023-11-07" or resolved.get("source") != "manager_fund_tenures":
        raise AssertionError(f"Authoritative manager tenure must override fallbacks: {resolved}")

    print("OK data quality reuses standardized classification and applies category-aware tenure checks")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
