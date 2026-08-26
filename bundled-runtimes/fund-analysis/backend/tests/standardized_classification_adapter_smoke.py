import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from services.fund_classification_service import FundClassificationService
from services.peer_comparison_service import PeerComparisonService
from services.professional_scoring_service import ProfessionalScoringService


def _panel() -> list[dict]:
    return [
        {"metric_window": "1y", "metric_name": "annualized_return", "metric_value": 0.045, "as_of_date": "2026-08-01"},
        {"metric_window": "1y", "metric_name": "max_drawdown", "metric_value": -0.025, "as_of_date": "2026-08-01"},
        {"metric_window": "1y", "metric_name": "annualized_volatility", "metric_value": 0.035, "as_of_date": "2026-08-01"},
        {"metric_window": "1y", "metric_name": "sharpe_ratio", "metric_value": 1.1, "as_of_date": "2026-08-01"},
        {"metric_window": "1y", "metric_name": "positive_return_ratio", "metric_value": 0.60, "as_of_date": "2026-08-01"},
    ]


def _standardized_context() -> dict:
    return {
        "status": "resolved",
        "fund_code": "STANDARD.TEST",
        "entity_id": "entity-standard",
        "canonical_code": "STANDARD",
        "canonical_name": "标准化信用债基金",
        "strategy_family_key": "fixed_income_credit",
        "strategy_family_name": "信用债策略",
        "asset_class": "fixed_income",
        "active_passive": "active",
        "peer_group_id": "peer-fixed-income",
        "peer_group_key": "peer-fixed-income-credit",
        "peer_group_name": "固收-信用债-中久期",
        "minimum_peer_count": 3,
        "benchmark_mapping": {
            "benchmark_code": "CBA_CREDIT",
            "benchmark_name": "中债信用债总财富指数",
            "mapping_method": "peer_group_policy",
            "confidence": 0.91,
            "rationale": "按信用债策略族谱和久期层映射",
            "effective_from": "2026-01-01",
            "effective_to": None,
            "source": "benchmark_mapping_policy",
        },
        "classification_confidence": 0.93,
        "classification_evidence": [
            {
                "field": "strategy_family.key",
                "value": "fixed_income_credit",
                "source": "strategy_families",
                "reason": "标准化策略族谱",
            }
        ],
    }


class FakeClassificationAdapter:
    def __init__(self):
        self.context_requests = []
        self.peer_requests = []

    def get_classification_context(self, fund_code: str):
        self.context_requests.append(fund_code)
        return _standardized_context()

    def list_peer_funds(self, peer_group_id: str, target_wind_code: str | None = None):
        self.peer_requests.append((peer_group_id, target_wind_code))
        return [
            {"wind_code": "STANDARD.TEST", "name": "标准化信用债基金", "type": "bond"},
            {"wind_code": "PEER.1", "name": "信用债同类一号", "type": "bond"},
            {"wind_code": "PEER.2", "name": "信用债同类二号", "type": "bond"},
        ]


class FakeFundRepo:
    def get_fund_by_identifier(self, fund_code: str):
        return {"wind_code": fund_code, "name": "名称看起来像指数基金ETF", "type": "指数型"}


class FakeProfileRepo:
    def get_profile(self, fund_code: str):
        return {
            "strategy_family_key": "active_equity_core",
            "peer_group": "旧主动权益同类组",
            "primary_benchmark": "沪深300",
        }

    def list_profiles(self, fund_codes: list[str]):
        return {code: {} for code in fund_codes}


class FakeMetricRepo:
    def get_latest_panel(self, target_type: str, target_id: str):
        return _panel()


class FakeDataQualityService:
    def evaluate_fund(self, fund_code: str):
        return {"status": "complete", "score": 90, "issues": []}


def main() -> int:
    context = _standardized_context()
    classification = FundClassificationService().classify(
        {"wind_code": "STANDARD.TEST", "name": "沪深300ETF联接", "type": "指数型"},
        {"strategy_family_key": "active_equity_core", "peer_group": "旧同类组"},
        context,
    )
    if classification.get("strategy_family_key") != "fixed_income_credit":
        raise AssertionError(f"Standardized strategy family must override legacy guesses: {classification}")
    if classification.get("source") != "standardized_classification_adapter":
        raise AssertionError(f"Standardized source must remain auditable: {classification}")
    if classification.get("peer_group_id") != "peer-fixed-income":
        raise AssertionError(f"Peer group identity must survive classification: {classification}")
    if classification.get("benchmark_code") != "CBA_CREDIT":
        raise AssertionError(f"Benchmark mapping must survive classification: {classification}")

    unknown_context = dict(context, strategy_family_key="unregistered_family")
    blocked = FundClassificationService().classify(
        {"wind_code": "STANDARD.TEST", "name": "股票基金", "type": "stock"},
        {},
        unknown_context,
    )
    if blocked.get("status") != "insufficient_evidence":
        raise AssertionError(f"Unknown standardized taxonomy must not fall back to name guessing: {blocked}")

    adapter = FakeClassificationAdapter()
    scoring = ProfessionalScoringService(
        data_quality_service=FakeDataQualityService(),
        classification_adapter=adapter,
        fund_repo=FakeFundRepo(),
        metric_repo=FakeMetricRepo(),
        profile_repo=FakeProfileRepo(),
    ).score_fund("STANDARD.TEST")
    if scoring.get("fund_type_profile") != "fixed_income":
        raise AssertionError(f"Production scoring path must consume standardized classification: {scoring}")
    if scoring.get("classification", {}).get("peer_group_key") != "peer-fixed-income-credit":
        raise AssertionError(f"Scoring output lost standardized peer context: {scoring}")

    peer_adapter = FakeClassificationAdapter()
    peer_service = PeerComparisonService(
        classification_adapter=peer_adapter,
        fund_repo=FakeFundRepo(),
        profile_repo=FakeProfileRepo(),
    )
    target, peers, source = peer_service._peer_universe("STANDARD.TEST")
    if source != "standardized_peer_group_membership":
        raise AssertionError(f"Peer universe must prefer normalized membership: {source}")
    if peer_adapter.peer_requests != [("peer-fixed-income", "STANDARD.TEST")]:
        raise AssertionError(f"Peer adapter received the wrong request: {peer_adapter.peer_requests}")
    if {fund.get("wind_code") for fund in peers} != {"STANDARD.TEST", "PEER.1", "PEER.2"}:
        raise AssertionError(f"Peer universe must come from explicit membership: {peers}")
    if target.get("classification", {}).get("minimum_peer_count") != 3:
        raise AssertionError(f"Peer policy minimum must survive the seam: {target}")

    print("OK standardized classification adapter drives classification, scoring and peer membership")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
