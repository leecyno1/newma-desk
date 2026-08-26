import os
import sys
from datetime import date, timedelta
from decimal import Decimal

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
BACKEND_DIR = os.path.join(ROOT_DIR, "backend")
sys.path.insert(0, BACKEND_DIR)

from database import init_database
from repositories import get_nav_repo, get_research_profile_repo
from services.manager_tenure_metric_service import ManagerTenureMetricService
from services.rolling_metric_service import RollingMetricService


FUND_PATTERNS = {
    "000002.OF": Decimal("0.00072"),
    "000007.OF": Decimal("0.00088"),
    "000003.OF": Decimal("0.00046"),
    "000004.OF": Decimal("0.00056"),
    "000005.OF": Decimal("0.00016"),
    "000006.OF": Decimal("0.00014"),
    "000008.OF": Decimal("0.00038"),
    "000009.OF": Decimal("0.00034"),
    "000010.OF": Decimal("0.00005"),
    "000011.OF": Decimal("0.00042"),
    "000012.OF": Decimal("0.00031"),
    "000013.OF": Decimal("0.00013"),
}


def build_nav_series(start: date, days: int, base_change: Decimal) -> list[dict]:
    nav = Decimal("1.0000")
    series = []
    for offset in range(days):
        trade_date = start + timedelta(days=offset)
        cycle_drag = Decimal("-0.0055") if offset % 41 == 0 else Decimal("0")
        small_noise = Decimal("0.0003") if offset % 9 in {2, 5} else Decimal("-0.0002") if offset % 13 == 0 else Decimal("0")
        nav = max(Decimal("0.6500"), nav * (Decimal("1") + base_change + cycle_drag + small_noise))
        series.append({
            "date": trade_date.isoformat(),
            "nav": float(nav),
            "accum_nav": float(nav),
        })
    return series


def main() -> int:
    init_database()
    nav_repo = get_nav_repo()
    profile_repo = get_research_profile_repo()
    service = RollingMetricService()
    tenure_service = ManagerTenureMetricService()

    saved_total = 0
    tenure_saved_total = 0
    start = date(2023, 12, 12)
    days = 900
    for fund_code, base_change in FUND_PATTERNS.items():
        nav_repo.delete_nav(fund_code)
        nav_repo.upsert_nav_series(fund_code, build_nav_series(start, days, base_change))
        profile = profile_repo.get_profile(fund_code) or {}
        result = service.calculate_and_save_for_fund(
            fund_code,
            benchmark_code=profile.get("primary_benchmark"),
            peer_group_key=profile.get("peer_group"),
        )
        saved_total += result.get("saved", 0)
        tenure_result = tenure_service.calculate_and_save_for_fund(fund_code)
        tenure_saved_total += tenure_result.get("saved", 0)

    print(f"OK seeded rolling metrics for {len(FUND_PATTERNS)} funds, snapshots={saved_total}, tenure_snapshots={tenure_saved_total}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
