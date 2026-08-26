import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from repositories.fund_repo import FundRepo
from repositories.research_profile_repo import ResearchProfileRepo


def main() -> int:
    fund_repo = FundRepo()
    profile_repo = ResearchProfileRepo()
    wind_code = "SMOKE.PROFILE"

    if not fund_repo.upsert_fund(wind_code, {
        "name": "研究画像 smoke 基金",
        "type": "stock",
        "nav": 1.2345,
        "nav_date": "2026-06-03",
        "total_asset": 12.3,
        "establishment_date": "2021-01-01",
        "performance_data": {"return_1y": 0.12},
        "risk_metrics": {"max_drawdown": -0.08},
    }):
        print("Expected fund upsert to succeed")
        return 1

    profile = profile_repo.upsert_profile(
        wind_code=wind_code,
        primary_benchmark="沪深300",
        secondary_benchmark="中证800",
        peer_group="主动权益-大盘均衡",
        style_label="大盘均衡",
        strategy_tags=["主动权益", "均衡风格"],
        manager_tenure_start="2024-01-01",
        capacity_notes="规模仍在可管理区间",
        data_quality_notes="基准与同类池已人工确认",
        evidence={"source": "smoke"},
        updated_by="smoke-test",
    )
    if profile.get("peer_group") != "主动权益-大盘均衡":
        print(f"Expected peer group profile, got: {profile}")
        return 1

    fetched = profile_repo.get_profile(wind_code)
    if not fetched or fetched.get("primary_benchmark") != "沪深300":
        print(f"Expected fetched benchmark profile, got: {fetched}")
        return 1

    listed = profile_repo.list_profiles([wind_code])
    if wind_code not in listed:
        print(f"Expected profile map to contain {wind_code}, got: {listed}")
        return 1

    print("OK research profile repository lifecycle")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
