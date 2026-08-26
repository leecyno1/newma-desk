import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from services.fund_evaluation_service import FundEvaluationService


CLASSIFICATION = {
    "status": "classified",
    "asset_class": "equity",
    "strategy_family_key": "active_equity_core",
    "active_passive": "active",
    "evaluation_profile_key": "active_equity",
    "peer_group": "主动权益-核心均衡",
    "primary_benchmark": "中证800",
    "confidence": 0.92,
    "evidence": [{"field": "strategy_family_key", "value": "active_equity_core"}],
    "missing_items": [],
}


class FakeScoringService:
    def __init__(self, status="ok", classification=None):
        self.status = status
        self.classification = classification or CLASSIFICATION

    def score_fund(self, wind_code: str):
        if self.status == "insufficient_evidence":
            return {
                "status": "insufficient_evidence",
                "target_id": wind_code,
                "overall_score": None,
                "overall_grade": "insufficient_evidence",
                "classification": {**self.classification, "status": "insufficient_evidence"},
                "dimension_scores": {},
                "metric_scores": {},
                "missing_data": ["基金分类证据不足"],
            }
        return {
            "status": self.status,
            "target_id": wind_code,
            "overall_score": 78.4,
            "overall_grade": "B",
            "classification": self.classification,
            "dimension_scores": {"risk": {"score": 82.0}},
            "metric_scores": {"1y.sharpe_ratio": 1.15},
            "positive_factors": ["风险控制维度得分较高"],
            "negative_factors": [],
            "missing_data": [],
            "data_quality": {"status": "complete", "score": 90},
            "as_of_date": "2026-08-01",
            "calculation_method": "professional_metric_snapshot_v2",
        }


class FakePeerComparisonService:
    def __init__(self, sample_status="sufficient", classification=None):
        self.sample_status = sample_status
        self.classification = classification or CLASSIFICATION

    def build_peer_percentiles(self, wind_code: str, window="1y"):
        percentile = 72.5 if self.sample_status == "sufficient" else None
        return {
            "target_id": wind_code,
            "name": "测试基金",
            "classification": self.classification,
            "peer_group": self.classification.get("peer_group"),
            "primary_benchmark": self.classification.get("primary_benchmark"),
            "peer_group_source": "research_profile_peer_group",
            "peer_count": 12 if percentile is not None else 3,
            "classified_peer_count": 12,
            "valid_metric_peer_count": 12 if percentile is not None else 3,
            "minimum_valid_peer_count": 5,
            "sample_status": self.sample_status,
            "metric_window": window,
            "metrics": {
                "sharpe_ratio": {
                    "value": 1.15,
                    "percentile": percentile,
                    "sample_status": self.sample_status,
                }
            },
            "peer_metric_gap": {"blocking_metrics": [] if percentile is not None else ["sharpe_ratio"]},
        }


def main() -> int:
    ready = FundEvaluationService(
        scoring_service=FakeScoringService(),
        peer_comparison_service=FakePeerComparisonService(),
    ).evaluate_fund("ACTIVE.TEST")
    if ready.get("status") != "ok":
        raise AssertionError(f"Complete category evaluation should be ready: {ready}")
    if ready.get("evaluation_scope") != "category_relative":
        raise AssertionError(f"Evaluation must be category-relative: {ready}")
    if ready.get("classification", {}).get("strategy_family_key") != "active_equity_core":
        raise AssertionError(f"Classification missing from snapshot: {ready}")
    if ready.get("peer_context", {}).get("peer_count") != 12:
        raise AssertionError(f"Peer context missing from snapshot: {ready}")
    if ready.get("evaluation", {}).get("overall_score") != 78.4:
        raise AssertionError(f"Professional evaluation missing: {ready}")
    if ready.get("product_scope", {}).get("investment_decision") != "excluded":
        raise AssertionError(f"Investment decision must remain out of scope: {ready}")
    if ready.get("explanatory_evidence", {}).get("barra", {}).get("role") != "optional":
        raise AssertionError(f"Barra must be optional explanatory evidence: {ready}")
    for banned_key in ["recommendation", "disposition", "watchlist", "purchase_gate"]:
        if banned_key in ready:
            raise AssertionError(f"Evaluation snapshot leaked {banned_key}: {ready}")

    thin_peer = FundEvaluationService(
        scoring_service=FakeScoringService(),
        peer_comparison_service=FakePeerComparisonService("insufficient_peer_sample"),
    ).evaluate_fund("ACTIVE.TEST")
    if thin_peer.get("status") != "partial":
        raise AssertionError(f"Thin peer sample must be partial, not fabricated: {thin_peer}")
    if thin_peer.get("evaluation", {}).get("overall_score") is not None:
        raise AssertionError(f"Thin peer sample must not expose a composite score: {thin_peer}")
    if thin_peer.get("evaluation", {}).get("peer_percentiles"):
        raise AssertionError(f"Thin peer sample must not expose peer percentiles: {thin_peer}")
    if not thin_peer.get("missing_items"):
        raise AssertionError(f"Thin peer sample must explain the gap: {thin_peer}")
    if "已分类产品 12 只，具备完整指标 3 只" not in " ".join(thin_peer.get("missing_items", [])):
        raise AssertionError(f"Thin peer explanation must separate classification from coverage: {thin_peer}")

    missing_benchmark = {
        **CLASSIFICATION,
        "primary_benchmark": None,
        "missing_items": ["缺少有效基准映射，不能形成完整的分类内基金评价"],
    }
    blocked_context = FundEvaluationService(
        scoring_service=FakeScoringService(classification=missing_benchmark),
        peer_comparison_service=FakePeerComparisonService(classification=missing_benchmark),
    ).evaluate_fund("ACTIVE.TEST")
    if blocked_context.get("status") != "insufficient_evidence":
        raise AssertionError(f"Missing benchmark must block category-relative evaluation: {blocked_context}")
    if blocked_context.get("evaluation", {}).get("overall_score") is not None:
        raise AssertionError(f"Blocked category-relative evaluation must not expose a composite score: {blocked_context}")

    unavailable = FundEvaluationService(
        scoring_service=FakeScoringService("insufficient_evidence"),
        peer_comparison_service=FakePeerComparisonService(),
    ).evaluate_fund("UNKNOWN.TEST")
    if unavailable.get("status") != "insufficient_evidence":
        raise AssertionError(f"Classification gate must stop the evaluation: {unavailable}")
    if unavailable.get("evaluation", {}).get("overall_score") is not None:
        raise AssertionError(f"Unavailable evaluation must not expose a score: {unavailable}")

    print("OK fund evaluation snapshot unifies classification, peers and scoring without decisions")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
