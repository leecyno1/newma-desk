import os
import sys
from datetime import date, timedelta

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

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
    service = ProfessionalScoringService()

    index = service.score_from_inputs(
        {
            "wind_code": "INDEX.METHOD",
            "name": "沪深300ETF联接A",
            "type": "指数型",
        },
        {"peer_group": "沪深300同指数", "primary_benchmark": "沪深300"},
        _panel({
            "1y": {"tracking_error": 0.006, "excess_return": -0.004},
            "latest": {"expense_ratio": 0.006, "aum": 45.0},
        }),
        QUALITY,
    )
    if index.get("status") not in {"ok", "partial"} or index.get("overall_score") is None:
        raise AssertionError(f"Index-specific evidence should produce an evaluation: {index}")
    if index.get("fund_type_profile") != "index_fund":
        raise AssertionError(f"Index methodology key missing: {index}")
    if set(index.get("dimension_scores", {})) != {
        "tracking_quality",
        "cost_efficiency",
        "scale_liquidity",
        "data_quality",
    }:
        raise AssertionError(f"Index dimensions leaked another category's method: {index}")
    if "index_fund" not in str(index.get("calculation_method")):
        raise AssertionError(f"Index method version must be auditable: {index}")

    recent_index = service.score_from_inputs(
        {
            "wind_code": "INDEX.RECENT",
            "name": "沪深300ETF联接A",
            "type": "指数型",
            "establishment_date": (date.today() - timedelta(days=300)).isoformat(),
        },
        {"peer_group": "沪深300同指数", "primary_benchmark": "沪深300"},
        _panel({
            "1y": {"tracking_error": 0.006, "excess_return": -0.004},
            "latest": {"expense_ratio": 0.006, "aum": 45.0},
        }),
        QUALITY,
    )
    if recent_index.get("overall_score") is not None:
        raise AssertionError(f"A fund younger than the selected window must not enter the ranking: {recent_index}")
    if not any("近 1 年历史不足" in item for item in recent_index.get("missing_data", [])):
        raise AssertionError(f"Selected-window history gap must be explicit: {recent_index}")

    index_gap = service.score_from_inputs(
        {"wind_code": "INDEX.GAP", "name": "中证500ETF", "type": "指数型"},
        {"peer_group": "中证500同指数", "primary_benchmark": "中证500"},
        _panel({"1y": {"annualized_return": 0.10}, "latest": {"expense_ratio": 0.005, "aum": 20.0}}),
        QUALITY,
    )
    if index_gap.get("status") != "insufficient_evidence" or index_gap.get("overall_score") is not None:
        raise AssertionError(f"Index evaluation must stop without tracking evidence: {index_gap}")
    if not any("tracking_error" in item for item in index_gap.get("missing_data", [])):
        raise AssertionError(f"Index tracking gap must be explicit: {index_gap}")

    invalid_index = service.score_from_inputs(
        {"wind_code": "INDEX.INVALID", "name": "沪深300ETF联接", "type": "指数型"},
        {"peer_group": "沪深300同指数", "primary_benchmark": "沪深300"},
        _panel({
            "1y": {"tracking_error": 0.35, "excess_return": -0.004},
            "latest": {"expense_ratio": 0.005, "aum": 20.0},
        }),
        QUALITY,
    )
    if invalid_index.get("status") != "insufficient_evidence":
        raise AssertionError(f"Implausible index tracking evidence must be blocked: {invalid_index}")
    if not any("invalid_metric_range:tracking_error" in item for item in invalid_index.get("missing_data", [])):
        raise AssertionError(f"Invalid index range must remain auditable: {invalid_index}")

    money = service.score_from_inputs(
        {
            "wind_code": "MONEY.METHOD",
            "name": "现金管理货币基金",
            "type": "货币型",
        },
        {"peer_group": "货币-现金管理", "primary_benchmark": "DR007"},
        _panel({
            "1y": {
                "annualized_return": 0.021,
                "max_drawdown": -0.0004,
                "annualized_volatility": 0.0018,
                "positive_return_ratio": 0.99,
            },
            "latest": {
                "seven_day_annualized_yield": 0.019,
                "benchmark_annualized_rate": 0.015,
                "benchmark_yield_spread": 0.004,
                "aum": 120.0,
            },
        }),
        QUALITY,
    )
    if money.get("status") not in {"ok", "partial"} or money.get("overall_score") is None:
        raise AssertionError(f"Money-market evidence should produce an evaluation: {money}")
    if money.get("fund_type_profile") != "money_market":
        raise AssertionError(f"Money-market methodology key missing: {money}")
    if set(money.get("dimension_scores", {})) != {
        "income_competitiveness",
        "capital_preservation",
        "income_stability",
        "scale_liquidity",
        "data_quality",
    }:
        raise AssertionError(f"Money-market dimensions leaked another category's method: {money}")
    if money.get("metric_scores", {}).get("latest.benchmark_annualized_rate") != 0.015:
        raise AssertionError(f"Money-market evaluation must expose typed DR007 evidence: {money}")

    money_gap = service.score_from_inputs(
        {"wind_code": "MONEY.GAP", "name": "现金管理货币基金", "type": "货币型"},
        {"peer_group": "货币-现金管理", "primary_benchmark": "DR007"},
        _panel({"1y": {"annualized_return": 0.02, "max_drawdown": 0.0}, "latest": {"aum": 60.0}}),
        QUALITY,
    )
    if money_gap.get("status") != "insufficient_evidence":
        raise AssertionError(f"Money-market evaluation must stop without seven-day yield: {money_gap}")
    if not any("seven_day_annualized_yield" in item for item in money_gap.get("missing_data", [])):
        raise AssertionError(f"Money-market yield gap must be explicit: {money_gap}")

    index_from_fund_facts = service.score_from_inputs(
        {
            "wind_code": "INDEX.FACTS",
            "name": "沪深300ETF",
            "type": "指数型",
            "total_asset": 80.0,
            "performance_data": {"excess_return": -0.003},
            "risk_metrics": {"tracking_error": 0.005},
            "raw_data": {"info": {"management_fee": 0.5, "custodian_fee": 0.1}},
        },
        {"peer_group": "沪深300同指数", "primary_benchmark": "沪深300"},
        [],
        QUALITY,
    )
    if index_from_fund_facts.get("overall_score") is None:
        raise AssertionError(f"Fund facts should adapt into index methodology metrics: {index_from_fund_facts}")

    enhanced = service.score_from_inputs(
        {
            "wind_code": "INDEX.ENHANCED",
            "name": "沪深300指数增强A",
            "type": "指数型",
        },
        {
            "strategy_family_key": "index_enhanced",
            "peer_group": "指数增强-沪深300",
            "primary_benchmark": "沪深300",
        },
        _panel({
            "1y": {
                "excess_return": 0.035,
                "information_ratio": 0.85,
                "tracking_error": 0.06,
                "max_drawdown": -0.16,
            },
            "latest": {"expense_ratio": 0.012, "aum": 35.0},
        }),
        QUALITY,
    )
    if enhanced.get("status") not in {"ok", "partial"} or enhanced.get("overall_score") is None:
        raise AssertionError(f"Enhanced index evidence should produce an evaluation: {enhanced}")
    if enhanced.get("fund_type_profile") != "index_enhanced":
        raise AssertionError(f"Enhanced index methodology key missing: {enhanced}")
    if set(enhanced.get("dimension_scores", {})) != {
        "excess_return",
        "active_efficiency",
        "drawdown_control",
        "cost_efficiency",
        "scale_liquidity",
        "data_quality",
    }:
        raise AssertionError(f"Enhanced index dimensions must be independent from passive tracking: {enhanced}")
    if "index_enhanced" not in str(enhanced.get("calculation_method")):
        raise AssertionError(f"Enhanced index method must be auditable: {enhanced}")

    enhanced_gap = service.score_from_inputs(
        {
            "wind_code": "INDEX.ENHANCED.GAP",
            "name": "中证500指数增强A",
            "type": "指数型",
        },
        {
            "strategy_family_key": "index_enhanced",
            "peer_group": "指数增强-中证500",
            "primary_benchmark": "中证500",
        },
        _panel({
            "1y": {"excess_return": 0.03, "tracking_error": 0.06, "max_drawdown": -0.16},
            "latest": {"expense_ratio": 0.012, "aum": 35.0},
        }),
        QUALITY,
    )
    if enhanced_gap.get("status") != "insufficient_evidence":
        raise AssertionError(f"Enhanced index evaluation must stop without information ratio: {enhanced_gap}")
    if not any("information_ratio" in item for item in enhanced_gap.get("missing_data", [])):
        raise AssertionError(f"Enhanced index information-ratio gap must be explicit: {enhanced_gap}")

    fee_facts = service.metric_facts_from_fund({
        "raw_data": {
            "source": "tushare",
            "universe": {"management_fee": 0.15, "custodian_fee": 0.05},
        },
    })
    expense_ratio = fee_facts.get("latest", {}).get("expense_ratio")
    if expense_ratio is None or abs(expense_ratio - 0.002) > 1e-12:
        raise AssertionError(f"Tushare percentage-point fees must normalize to decimal rates: {fee_facts}")

    index_peer_score = service.score_peer_metrics(
        "index_fund",
        {"tracking_error": 0.006, "excess_return": -0.004, "expense_ratio": 0.006, "aum": 45.0},
    )
    if index_peer_score is None:
        raise AssertionError("Index peer proxy must reuse the index methodology")
    wrong_index_peer_score = service.score_peer_metrics(
        "index_fund",
        {"annualized_return": 0.15, "max_drawdown": -0.10, "sharpe_ratio": 1.2},
    )
    if wrong_index_peer_score is not None:
        raise AssertionError(f"Index peer proxy must not reuse active-equity metrics: {wrong_index_peer_score}")

    money_peer_score = service.score_peer_metrics(
        "money_market",
        {
            "seven_day_annualized_yield": 0.019,
            "annualized_return": 0.021,
            "max_drawdown": -0.0004,
            "annualized_volatility": 0.0018,
            "positive_return_ratio": 0.99,
            "aum": 120.0,
        },
    )
    if money_peer_score is None:
        raise AssertionError("Money-market peer proxy must reuse the money-market methodology")
    wrong_money_peer_score = service.score_peer_metrics(
        "money_market",
        {"annualized_return": 0.15, "max_drawdown": -0.10, "sharpe_ratio": 1.2},
    )
    if wrong_money_peer_score is not None:
        raise AssertionError(f"Money-market peer proxy must not reuse active-equity metrics: {wrong_money_peer_score}")

    print("OK passive index, enhanced index and money-market evaluations use dedicated evidence gates and dimensions")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
