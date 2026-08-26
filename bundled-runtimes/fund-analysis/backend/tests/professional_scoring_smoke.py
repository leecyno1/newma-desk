import os
import sys
import atexit
from datetime import date, timedelta
from decimal import Decimal

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from database import init_database
from repositories import get_fund_repo, get_nav_repo, get_research_profile_repo
from services.manager_tenure_metric_service import ManagerTenureMetricService
from services.fund_evaluation_methodology import FundEvaluationMethodology
from services.professional_scoring_service import ProfessionalScoringService
from services.rolling_metric_service import RollingMetricService
from smoke_cleanup import cleanup_fund_codes


def _nav_series(start: date, days: int) -> list[dict]:
    nav = Decimal("1.0000")
    series = []
    for offset in range(days):
        trade_date = start + timedelta(days=offset)
        daily_change = Decimal("0.00075") if offset % 31 else Decimal("-0.0040")
        nav = max(Decimal("0.7000"), nav * (Decimal("1") + daily_change))
        series.append({"date": trade_date.isoformat(), "nav": float(nav), "accum_nav": float(nav)})
    return series


def main() -> int:
    methodology = FundEvaluationMethodology()
    fixed_income_plus = methodology.evaluate(
        "fixed_income_plus",
        {"1y": {"annualized_return": 0.06, "max_drawdown": -0.06, "sharpe_ratio": 0.8}},
        {"score": 90, "issues": []},
    )
    if fixed_income_plus.get("status") not in {"ok", "partial"}:
        raise AssertionError(f"含权益配置债券评价不可用: {fixed_income_plus}")
    mixed_profiles = ["multi_asset", "multi_asset_equity", "multi_asset_balanced", "multi_asset_bond"]
    for profile_key in mixed_profiles:
        configs = methodology.peer_metric_configs(profile_key)
        required_metrics = {"annualized_return", "max_drawdown", "sharpe_ratio"}
        if not required_metrics.issubset({item["metric_name"] for item in configs}):
            raise AssertionError(f"{profile_key} 缺少核心同类指标: {configs}")
        evaluation = methodology.evaluate(
            profile_key,
            {
                "1y": {
                    "annualized_return": 0.08,
                    "max_drawdown": -0.08,
                    "sharpe_ratio": 0.9,
                    "annualized_volatility": 0.12,
                    "positive_return_ratio": 0.58,
                },
                "manager_tenure": {"annualized_return": 0.07, "max_drawdown": -0.10},
            },
            {"score": 90, "issues": []},
        )
        if evaluation.get("status") not in {"ok", "partial"}:
            raise AssertionError(f"{profile_key} 应可用核心指标评价: {evaluation}")

    risk_weights = {
        key: methodology.evaluate(
            key,
            {
                "1y": {"annualized_return": 0.08, "max_drawdown": -0.08, "sharpe_ratio": 0.9},
                "manager_tenure": {},
            },
            {"score": 90, "issues": []},
        )["dimensions"]["risk"]["weight"]
        for key in mixed_profiles
    }
    if not (risk_weights["multi_asset_equity"] < risk_weights["multi_asset_balanced"] < risk_weights["multi_asset_bond"]):
        raise AssertionError(f"混合型风险权重顺序错误: {risk_weights}")

    init_database()

    fund_code = "PROSCORE.TEST"
    cleanup_fund_codes([fund_code])
    atexit.register(cleanup_fund_codes, [fund_code])
    fund_repo = get_fund_repo()
    nav_repo = get_nav_repo()
    profile_repo = get_research_profile_repo()

    fund_repo.upsert_fund(fund_code, {
        "name": "专业评分测试基金",
        "type": "stock",
        "nav": 1.5678,
        "nav_date": "2026-05-29",
        "total_asset": 68.5,
        "establishment_date": "2022-01-01",
        "performance": {"return_1y": 0.18},
        "risk_metrics": {"max_drawdown": -0.16},
    })
    profile_repo.upsert_profile(
        wind_code=fund_code,
        primary_benchmark="沪深300",
        peer_group="主动权益-专业评分",
        style_label="均衡成长",
        manager_tenure_start="2024-01-01",
        capacity_notes="规模适中",
        data_quality_notes="专业评分 smoke 数据齐备",
        updated_by="professional-scoring-smoke",
    )
    nav_repo.delete_nav(fund_code)
    nav_repo.upsert_nav_series(fund_code, _nav_series(date(2023, 1, 1), 900))
    RollingMetricService().calculate_and_save_for_fund(fund_code)
    ManagerTenureMetricService().calculate_and_save_for_fund(fund_code)

    result = ProfessionalScoringService().score_fund(fund_code)
    if result.get("calculation_method") != "category_evaluation_methodology_v6:active_equity:1y":
        raise AssertionError(f"Unexpected calculation method: {result}")
    if result.get("fund_type_profile") != "active_equity":
        raise AssertionError(f"Expected active_equity profile, got {result}")
    if result.get("overall_score", 0) <= 60:
        raise AssertionError(f"Expected usable professional evaluation score, got {result}")

    dimensions = result.get("dimension_scores", {})
    for dimension in {"return", "risk", "risk_adjusted", "consistency", "manager_tenure", "data_quality"}:
        if dimension not in dimensions:
            raise AssertionError(f"Missing professional dimension {dimension}: {result}")

    if result.get("data_quality", {}).get("status") != "complete":
        raise AssertionError(f"Expected complete data quality, got {result}")
    if not result.get("positive_factors"):
        raise AssertionError(f"Expected positive scoring factors, got {result}")

    cleanup_fund_codes([fund_code])
    print("OK professional scoring uses rolling, tenure and quality inputs")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
