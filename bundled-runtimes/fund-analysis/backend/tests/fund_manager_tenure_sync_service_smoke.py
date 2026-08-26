import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from services.fund_manager_tenure_sync_service import FundManagerTenureSyncService


class FundRepo:
    def __init__(self):
        self.assignment = None

    def get_fund(self, code):
        return {
            "wind_code": code,
            "name": "真实基金",
            "raw_data": {"universe": {"company": "示例基金管理有限公司"}},
        }

    def update_manager_assignments(self, code, manager_ids, evidence):
        self.assignment = (code, manager_ids, evidence)
        return True


class ManagerRepo:
    def __init__(self):
        self.rows = []

    def upsert_manager(self, manager_id, data):
        self.rows.append((manager_id, data))
        return True

    def upsert_fund_tenures(self, manager_id, rows):
        self.tenure_rows = getattr(self, "tenure_rows", []) + [(manager_id, rows)]
        return len(rows)


class ProfileRepo:
    def __init__(self):
        self.fields = None

    def upsert_manager_tenure(self, **fields):
        self.fields = fields
        return fields


class ClassificationRepo:
    def get_classification_context(self, code):
        return {
            "peer_group_name": "混合型-偏股配置",
            "benchmark_mapping": {"benchmark_code": "000300.SH"},
        }


class TenureService:
    def __init__(self):
        self.code = None

    def calculate_and_save_for_fund(self, code):
        self.code = code
        return {"saved": 7}


class DataService:
    def get_fund_managers(self, code):
        return [
            {
                "manager_id": "前任|M|硕士", "name": "前任", "education": "硕士",
                "begin_date": "2018-01-01", "end_date": "2022-01-01",
                "is_current_manager": False,
            },
            {
                "manager_id": "现任甲|M|硕士", "name": "现任甲", "education": "硕士",
                "begin_date": "2019-01-01", "end_date": "2020-01-01",
                "is_current_manager": False,
            },
            {
                "manager_id": "现任甲|M|硕士", "name": "现任甲", "education": "硕士",
                "begin_date": "2022-01-02", "end_date": None,
                "is_current_manager": True,
            },
            {
                "manager_id": "现任乙|F|博士", "name": "现任乙", "education": "博士",
                "begin_date": "2024-06-01", "end_date": None,
                "is_current_manager": True,
            },
        ]


def main() -> int:
    fund_repo = FundRepo()
    manager_repo = ManagerRepo()
    profile_repo = ProfileRepo()
    tenure_service = TenureService()
    service = FundManagerTenureSyncService(
        DataService(),
        fund_repo=fund_repo,
        manager_repo=manager_repo,
        profile_repo=profile_repo,
        classification_repo=ClassificationRepo(),
        tenure_metric_service=tenure_service,
    )
    result = service.sync_fund("000390.OF")
    if result.get("status") != "synced" or result.get("tenure_metrics_saved") != 7:
        raise AssertionError(result)
    if result.get("manager_tenure_start") != "2024-06-01":
        raise AssertionError("多人共同管理时必须使用现任团队中最晚的起始日")
    if fund_repo.assignment[1] != ["现任甲|M|硕士", "现任乙|F|博士"]:
        raise AssertionError(fund_repo.assignment)
    if profile_repo.fields.get("peer_group") != "混合型-偏股配置":
        raise AssertionError(profile_repo.fields)
    if profile_repo.fields.get("primary_benchmark") != "000300.SH":
        raise AssertionError(profile_repo.fields)
    if tenure_service.code != "000390.OF" or len(manager_repo.rows) != 3:
        raise AssertionError("经理关系或任期指标没有完整同步")
    if any(row[1].get("company") != "示例基金管理有限公司" for row in manager_repo.rows):
        raise AssertionError("经理同步必须继承基金档案中的真实基金公司")
    history_result = service.sync_fund_history("000390.OF")
    if history_result.get("status") != "synced" or history_result.get("tenure_records_saved") != 4:
        raise AssertionError(history_result)
    if len(manager_repo.tenure_rows) != 3:
        raise AssertionError("基金经理历史没有按真实经理增量写入")
    print("OK real manager records feed fund assignments, conservative team tenure and tenure metrics")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
