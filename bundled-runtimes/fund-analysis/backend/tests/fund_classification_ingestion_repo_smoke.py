import os
import sys
import atexit

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from database import init_database
from repositories.fund_classification_repo import FundClassificationRepo
from repositories.fund_repo import FundRepo
from services.fund_classification_ingestion_service import FundClassificationIngestionService
from smoke_cleanup import cleanup_fund_codes


def main() -> int:
    init_database()
    fund_repo = FundRepo()
    classification_repo = FundClassificationRepo()
    service = FundClassificationIngestionService(repository=classification_repo)
    fixture_codes = ["990001.OF", "990002.OF", "990003.OF"]
    cleanup_fund_codes(fixture_codes)
    atexit.register(cleanup_fund_codes, fixture_codes)

    fixtures = [
        {
            "wind_code": "990001.OF",
            "name": "自动归一现金货币A",
            "type": "货币型",
            "establishment_date": "2020-01-01",
            "raw_data": {"source": "classification_ingestion_smoke"},
        },
        {
            "wind_code": "990002.OF",
            "name": "自动归一现金货币B",
            "type": "货币型",
            "establishment_date": "2020-01-02",
            "raw_data": {"source": "classification_ingestion_smoke"},
        },
        {
            "wind_code": "990003.OF",
            "name": "自动归一沪深300ETF联接A",
            "type": "指数型",
            "establishment_date": "2021-01-01",
            "raw_data": {
                "source": "classification_ingestion_smoke",
                "info": {"benchmark": "沪深300指数收益率*95%+银行活期存款利率*5%"},
            },
        },
    ]
    for fixture in fixtures:
        if not fund_repo.upsert_fund(fixture["wind_code"], fixture):
            raise AssertionError(f"Could not persist classification fixture: {fixture}")

    persisted = [fund_repo.get_fund(fixture["wind_code"]) for fixture in fixtures]
    plan = service.build_plan(persisted)
    first = service.apply_plan(plan)
    second = service.apply_plan(plan)
    if first.get("applied_groups") != 2 or first.get("applied_shares") != 3:
        raise AssertionError(f"Classification plan was not persisted: {first}")
    if second.get("conflicts"):
        raise AssertionError(f"Classification ingestion must be idempotent: {second}")

    money_a = classification_repo.get_classification_context("990001.OF")
    money_b = classification_repo.get_classification_context("990002.OF")
    index = classification_repo.get_classification_context("990003.OF")
    if money_a.get("status") != "resolved" or money_b.get("status") != "resolved":
        raise AssertionError(f"Money classification context is unresolved: {money_a} / {money_b}")
    if money_a.get("entity_id") != money_b.get("entity_id"):
        raise AssertionError(f"Money A/B shares must resolve to one entity: {money_a} / {money_b}")
    if money_a.get("benchmark_mapping", {}).get("benchmark_code") != "DR007":
        raise AssertionError(f"Money benchmark mapping missing: {money_a}")
    if money_a.get("peer_group_membership_count", 0) < 2:
        raise AssertionError(f"Peer membership count must describe the full group: {money_a}")
    if index.get("benchmark_mapping", {}).get("benchmark_code") != "000300.SH":
        raise AssertionError(f"Index benchmark mapping missing: {index}")
    if index.get("strategy_family_key") != "index_broad" or index.get("active_passive") != "passive":
        raise AssertionError(f"Index classification is not standardized: {index}")

    cleanup_fund_codes(fixture_codes)
    print("OK classification ingestion persists idempotent entities, shares, peers and benchmarks")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
