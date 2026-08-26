import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from services.professional_scoring_service import ProfessionalScoringService


def _panel() -> list[dict]:
    values = {
        "1y": {
            "annualized_return": 0.14,
            "max_drawdown": -0.12,
            "annualized_volatility": 0.18,
            "sharpe_ratio": 1.1,
            "calmar_ratio": 1.2,
            "positive_return_ratio": 0.56,
        },
        "3y": {
            "annualized_return": 0.11,
            "max_drawdown": -0.18,
            "sharpe_ratio": 0.9,
        },
        "manager_tenure": {
            "annualized_return": 0.13,
            "max_drawdown": -0.14,
            "tenure_days": 720,
        },
    }
    return [
        {
            "metric_window": window,
            "metric_name": metric_name,
            "metric_value": metric_value,
            "as_of_date": "2026-08-01",
        }
        for window, metrics in values.items()
        for metric_name, metric_value in metrics.items()
    ]


def main() -> int:
    service = ProfessionalScoringService()
    quality = {"status": "complete", "score": 90, "issues": []}

    active = service.score_from_inputs(
        {"wind_code": "ACTIVE.TEST", "name": "均衡成长股票基金", "type": "stock"},
        {"peer_group": "主动权益-核心均衡", "primary_benchmark": "中证800"},
        _panel(),
        quality,
    )
    if active.get("status") not in {"ok", "partial"}:
        raise AssertionError(f"Supported category should produce evaluation: {active}")
    if active.get("overall_score") is None:
        raise AssertionError(f"Supported category should have a score: {active}")
    if active.get("classification", {}).get("evaluation_profile_key") != "active_equity":
        raise AssertionError(f"Classification must drive scoring profile: {active}")
    if active.get("product_scope", {}).get("investment_decision") != "excluded":
        raise AssertionError(f"Investment decision must be outside this product: {active}")
    for banned_key in ["recommendation", "disposition", "watchlist", "purchase_gate"]:
        if banned_key in active:
            raise AssertionError(f"Evaluation output leaked decision field {banned_key}: {active}")

    index_fund = service.score_from_inputs(
        {"wind_code": "INDEX.TEST", "name": "沪深300ETF联接A", "type": "指数型"},
        {},
        _panel(),
        quality,
    )
    if index_fund.get("status") != "insufficient_evidence":
        raise AssertionError(f"Index fund needs a dedicated methodology before scoring: {index_fund}")
    if index_fund.get("overall_score") is not None:
        raise AssertionError(f"Index fund must not reuse equity score: {index_fund}")
    if index_fund.get("classification", {}).get("evaluation_profile_key") != "index_fund":
        raise AssertionError(f"Index classification must remain intact: {index_fund}")

    unknown = service.score_from_inputs(
        {"wind_code": "UNKNOWN.TEST", "name": "无法识别产品", "type": "其他"},
        {},
        _panel(),
        quality,
    )
    if unknown.get("status") != "insufficient_evidence":
        raise AssertionError(f"Unknown category must stop evaluation: {unknown}")
    if unknown.get("overall_score") is not None:
        raise AssertionError(f"Unknown category must never default to a score: {unknown}")
    if unknown.get("fund_type_profile") is not None:
        raise AssertionError(f"Unknown category must never default active_equity: {unknown}")

    missing_metrics = service.score_from_inputs(
        {"wind_code": "EMPTY.TEST", "name": "均衡价值股票基金", "type": "stock"},
        {"peer_group": "主动权益-核心均衡", "primary_benchmark": "中证800"},
        [],
        quality,
    )
    if missing_metrics.get("status") != "insufficient_evidence":
        raise AssertionError(f"Core metric gaps must stop scoring: {missing_metrics}")
    if missing_metrics.get("overall_score") is not None:
        raise AssertionError(f"Missing metrics must not become a default 50 score: {missing_metrics}")
    if not any("core_metric" in item for item in missing_metrics.get("missing_data", [])):
        raise AssertionError(f"Metric evidence gap must be explicit: {missing_metrics}")

    print("OK professional scoring is classification-gated and excludes investment decisions")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
