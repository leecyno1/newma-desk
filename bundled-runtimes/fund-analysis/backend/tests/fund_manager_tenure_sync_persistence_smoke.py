from pathlib import Path
import sys
from datetime import date, timedelta

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.fund_manager_tenure_sync_service import FundManagerTenureSyncService


class FundRepo:
    def get_fund(self, code):
        return {"wind_code": code, "name": code}

    def update_manager_assignments(self, *_args):
        return True


class ManagerRepo:
    def __init__(self):
        self.manager = None
        self.bootstrap = None

    def get_manager(self, manager_id):
        return self.manager

    def upsert_manager(self, manager_id, data):
        self.bootstrap = data
        self.manager = {"wind_code": manager_id, **data}
        return True

    def replace_fund_tenures(self, manager_id, rows):
        self.manager_id = manager_id
        self.rows = rows
        return True


class ProfileRepo:
    pass


class ClassificationRepo:
    def __init__(self, code):
        self.code = code

    def get_classification_context(self, _fund_code):
        return {"benchmark_mapping": {"benchmark_code": self.code}} if self.code else {}


class NavRepo:
    def __init__(self):
        self.calls = []

    def upsert_nav_series(self, code, rows, replace_range=False):
        self.calls.append((code, rows, replace_range))
        return True


class DataService:
    def __init__(self, benchmark_rows):
        self.benchmark_rows = benchmark_rows

    def get_manager_tenures(self, _manager_id):
        return [{
            "manager_id": "真实经理|M|硕士",
            "fund_code": "000001.OF",
            "fund_name": "真实基金",
            "start_date": "2026-01-01",
            "end_date": None,
            "is_current": True,
        }]

    def get_fund_nav(self, *_args):
        return [
            {
                "date": (date(2026, 1, 2) + timedelta(days=index)).isoformat(),
                "nav": 1.0 + index * 0.01,
                "accum_nav": 1.0 + index * 0.01,
            }
            for index in range(20)
        ]

    def get_benchmark_nav(self, *_args, **_kwargs):
        return list(self.benchmark_rows)


def run(benchmark_code, benchmark_rows):
    nav_repo = NavRepo()
    manager_repo = ManagerRepo()
    result = FundManagerTenureSyncService(
        DataService(benchmark_rows),
        fund_repo=FundRepo(),
        manager_repo=manager_repo,
        profile_repo=ProfileRepo(),
        classification_repo=ClassificationRepo(benchmark_code),
        nav_repo=nav_repo,
    ).sync_manager("真实经理|M|硕士")
    return result, nav_repo, manager_repo


def main():
    result, nav_repo, manager_repo = run("000300.SH", [
        {
            "date": (date(2026, 1, 2) + timedelta(days=index)).isoformat(),
            "nav": 4000.0 + index * 10,
        }
        for index in range(20)
    ])
    assert result["nav_points_saved"] == 20
    assert result["manager_bootstrapped"] is True
    assert manager_repo.bootstrap["current_funds"] == ["000001.OF"]
    assert manager_repo.bootstrap["raw_data"]["bootstrapped_from_manager_tenures"] is True
    assert result["benchmark_points_saved"] == 20
    assert len(nav_repo.calls) == 1 and nav_repo.calls[0][2] is True
    assert [row.get("benchmark_nav") for row in nav_repo.calls[0][1]][:3] == [4000.0, 4010.0, 4020.0]
    snapshot = manager_repo.rows[0]["performance_snapshot"]
    assert snapshot["benchmark_code"] == "000300.SH"
    assert snapshot["benchmark_return"] is not None and snapshot["excess_return"] is not None
    assert snapshot["sortino_ratio"] is not None

    missing, missing_nav, missing_manager = run("MIXED-EQUITY-60", [])
    assert missing["benchmark_points_saved"] == 0
    assert all(row.get("benchmark_nav") is None for row in missing_nav.calls[0][1])
    missing_snapshot = missing_manager.rows[0]["performance_snapshot"]
    assert missing_snapshot["benchmark_return"] is None
    assert missing_snapshot["excess_return"] is None
    assert missing_snapshot["benchmark_observations"] == 0
    assert "simulated" not in str(missing).lower()
    print("fund manager tenure sync persists real NAV/benchmark and leaves missing benchmark blank")


if __name__ == "__main__":
    main()
