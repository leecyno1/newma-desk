import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from services.fund_evaluation_methodology import FundEvaluationMethodology
from services.professional_scoring_service import ProfessionalScoringService


QUALITY = {"status": "complete", "score": 92, "issues": []}


def _panel(values: dict[str, dict[str, float]]) -> list[dict]:
    return [
        {
            "metric_window": window,
            "metric_name": metric_name,
            "metric_value": metric_value,
            "as_of_date": "2026-08-03",
        }
        for window, metrics in values.items()
        for metric_name, metric_value in metrics.items()
    ]


def main() -> int:
    methodology = FundEvaluationMethodology()

    return_risk_profiles = sorted(methodology.RETURN_RISK_PROFILES)
    missing_configs = [
        key for key in return_risk_profiles if not methodology.peer_metric_configs(key)
    ]
    if missing_configs:
        raise AssertionError(f"return-risk profiles missing peer metric configs: {missing_configs}")

    active_metrics = {
        config["metric_name"] for config in methodology.peer_metric_configs("active_equity")
    }
    for expected in ("sortino_ratio", "var_95", "monthly_win_rate"):
        if expected not in active_metrics:
            raise AssertionError(f"active_equity peer metrics must include {expected}: {active_metrics}")
    for config in methodology.peer_metric_configs("active_equity"):
        if config["metric_name"] in {"sortino_ratio", "var_95", "monthly_win_rate"} and config.get("required_for_sample"):
            raise AssertionError(f"new tail-risk metrics must not gate the peer sample: {config}")

    money_metrics = {
        config["metric_name"] for config in methodology.peer_metric_configs("money_market")
    }
    if money_metrics & {"sortino_ratio", "var_95", "monthly_win_rate"}:
        raise AssertionError(f"money-market peer metrics must stay yield-based: {money_metrics}")

    service = ProfessionalScoringService()
    evaluation = service.score_from_inputs(
        {"wind_code": "ACTIVE.TAIL", "name": "主动权益尾部风险测试", "type": "股票型"},
        {"peer_group": "主动权益", "primary_benchmark": "沪深300"},
        _panel({
            "1y": {
                "annualized_return": 0.12,
                "max_drawdown": -0.18,
                "annualized_volatility": 0.21,
                "sharpe_ratio": 0.6,
                "sortino_ratio": 0.9,
                "var_95": -0.021,
                "cvar_95": -0.033,
                "monthly_win_rate": 0.58,
            },
            "latest": {"expense_ratio": 0.012, "aum": 30.0},
        }),
        QUALITY,
    )
    metric_scores = evaluation.get("metric_scores") or {}
    for key in ("1y.sortino_ratio", "1y.var_95", "1y.cvar_95", "1y.monthly_win_rate"):
        if key not in metric_scores:
            raise AssertionError(f"evaluation metric panel must expose {key}: {sorted(metric_scores)}")

    print("OK peer metric configs cover all return-risk profiles with tail-risk metrics")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
