import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from services.fund_classification_ingestion_service import FundClassificationIngestionService
from services.fund_evaluation_methodology import FundEvaluationMethodology
from services.fund_research_snapshot_service import FundResearchSnapshotService


def _fund(code: str, name: str, invest_type: str, contract_type: str, benchmark: str):
    return {
        "wind_code": code,
        "name": name,
        "type": "QDII",
        "establishment_date": "2020-01-01",
        "raw_data": {"universe": {
            "invest_type": invest_type,
            "contract_type": contract_type,
            "benchmark": benchmark,
        }},
    }


def main() -> int:
    service = FundClassificationIngestionService()
    equity_benchmark = "MSCI全球指数收益率×100%"
    plan = service.build_plan([
        _fund("970001.OF", "审计全球股票(QDII)-A-CNY", "股票型", "股票型", equity_benchmark),
        _fund("970002.OF", "审计全球股票(QDII)-A-USD-现汇", "股票型", "股票型", equity_benchmark),
        _fund("970003.OF", "审计亚洲债券(QDII)-CNY", "债券型", "债券型", "摩根大通亚洲债券指数×100%"),
        _fund("970004.OF", "审计全球配置(QDII)-A", "混合型", "混合型", "MSCI全球指数×60%+全球债券指数×40%"),
        _fund("970005.OF", "审计纳指(QDII)-A-CNY", "被动指数型", "股票型", "经人民币汇率调整的纳斯达克100指数收益率×100%"),
        _fund("970006.OF", "审计纳指口径未声明(QDII)-A", "被动指数型", "股票型", "纳斯达克100指数×100%"),
        _fund("970007.OF", "审计纳指联接(QDII)-A", "被动指数型", "股票型", "经汇率调整的纳斯达克100指数收益率×95%+活期存款利率×5%"),
    ])

    if plan["summary"]["eligible_funds"] != 5 or len(plan["groups"]) != 4:
        raise AssertionError(f"QDII active categories and verified passive index products should form four peer groups: {plan}")
    equity = next(group for group in plan["groups"] if group["strategy_family_key"] == "qdii_equity")
    if equity["peer_group_benchmark_code"] != "QDII-ACTIVE-EQUITY":
        raise AssertionError(f"QDII peer bucket code missing: {equity}")
    if equity["benchmark_name"] != equity_benchmark or not equity["benchmark_code"].startswith("CONTRACT-QDII-"):
        raise AssertionError(f"QDII contract benchmark must be retained independently: {equity}")
    if equity["benchmark_code"] == equity["peer_group_benchmark_code"]:
        raise AssertionError(f"QDII contract benchmark cannot be replaced by the peer bucket: {equity}")
    if equity["canonical_code"] != "970001.OF":
        raise AssertionError(f"CNY share must be the representative share: {equity}")
    if {share["currency"] for share in equity["shares"]} != {"CNY", "USD"}:
        raise AssertionError(f"QDII share currencies were not recognized: {equity}")
    qdii_index = next(group for group in plan["groups"] if group["strategy_family_key"] == "qdii_index")
    if qdii_index["benchmark_code"] != "NDX.CNY" or qdii_index["peer_group_key"] != "peer-qdii-index-ndx-cny":
        raise AssertionError(f"Verified Nasdaq 100 QDII must use the CNY benchmark and independent peer group: {qdii_index}")
    if plan["summary"]["skipped_by_reason"].get("qdii_index_currency_basis_unverified") != 1:
        raise AssertionError(f"QDII index funds without an explicit currency basis must remain excluded: {plan}")
    if plan["summary"]["skipped_by_reason"].get("qdii_index_reference_not_100_percent") != 1:
        raise AssertionError(f"QDII feeder benchmarks below 100% index weight must remain excluded: {plan}")

    methodology = FundEvaluationMethodology()
    metrics = {
        "1y": {
            "annualized_return": 0.10,
            "max_drawdown": -0.12,
            "annualized_volatility": 0.18,
            "sharpe_ratio": 0.8,
            "positive_return_ratio": 0.56,
        }
    }
    quality = {"score": 90, "issues": []}
    for profile_key in ("qdii_equity", "qdii_bond", "qdii_multi_asset"):
        result = methodology.evaluate(profile_key, metrics, quality)
        if result.get("status") not in {"ok", "partial"} or result.get("total_score") is None:
            raise AssertionError(f"{profile_key} methodology should be available: {result}")
        if not methodology.peer_metric_configs(profile_key):
            raise AssertionError(f"{profile_key} peer metrics should be configured")

    index_result = methodology.evaluate(
        "qdii_index",
        {
            "1y": {"tracking_error": 0.034, "tracking_difference": -0.012},
            "latest": {"expense_ratio": 0.006, "aum": 45.0},
        },
        quality,
    )
    if index_result.get("status") not in {"ok", "partial"} or index_result.get("total_score") is None:
        raise AssertionError(f"QDII passive index methodology should be independently available: {index_result}")
    if index_result.get("profile_key") != "qdii_index" or ":qdii_index:" not in index_result.get("calculation_method", ""):
        raise AssertionError(f"QDII index evaluation must retain its own methodology identity: {index_result}")
    if not methodology.peer_metric_configs("qdii_index"):
        raise AssertionError("QDII index peer metrics should be configured")

    tenure = FundResearchSnapshotService()._manager_tenure_performance(
        "513300.SH",
        {},
        {},
        {"evaluation_profile_key": "qdii_index"},
    )
    if tenure.get("status") != "not_applicable" or tenure.get("included_in_score") is not False:
        raise AssertionError(f"QDII passive index evaluation must not treat manager tenure as a gap: {tenure}")

    print("OK QDII classification separates active categories and verified CNY Nasdaq 100 index evaluation")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
