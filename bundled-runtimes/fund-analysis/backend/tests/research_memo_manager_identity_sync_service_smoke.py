from copy import deepcopy
from pathlib import Path
import sys


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.research_memo_manager_identity_sync_service import (  # noqa: E402
    ResearchMemoManagerIdentitySyncService,
)


class DataService:
    def get_manager_identity_candidates(self, name):
        if name == "张三":
            return [{
                "manager_id": "张三|M|硕士",
                "name": "张三",
                "gender": "M",
                "education": "硕士",
                "current_funds": ["000001.OF"],
                "tenures": [{
                    "fund_code": "000001.OF",
                    "start_date": "2020-01-01",
                    "end_date": None,
                    "is_current": True,
                }],
            }]
        if name == "同名人":
            return [{"manager_id": "同名人|M|硕士", "tenures": []}, {"manager_id": "同名人|F|硕士", "tenures": []}]
        if name == "冲突人":
            return [{
                "manager_id": "冲突人|M|硕士",
                "name": "冲突人",
                "tenures": [
                    {"fund_code": "000001.OF", "start_date": "2020-01-01", "end_date": None, "is_current": True},
                    {"fund_code": "000002.OF", "start_date": "2020-01-01", "end_date": None, "is_current": True},
                ],
            }]
        return []


class ReportRepo:
    def __init__(self):
        self.report = {
            "id": "report-1",
            "review_proposals": [{
                "id": "proposal-1",
                "kind": "manager",
                "value": "张三",
                "confidence": 0.98,
                "review_status": "pending",
                "extraction_source": "explicit_field",
                "source_ref": {"excerpt": "测试基金 基金经理：张三"},
            }],
        }

    def list_pending_reviews(self, folder_id=None):
        return [{"report_id": "report-1", "report_title": "测试基金张三纪要", "report_date": "2026-01-10", "report_date_source": "filename", **deepcopy(self.report["review_proposals"][0])}, {
            "report_id": "report-2", "id": "proposal-2", "kind": "manager", "value": "同名人",
            "report_date_source": "filename", "confidence": 0.98, "review_status": "pending", "extraction_source": "explicit_field",
        }, {
            "report_id": "report-3", "id": "proposal-3", "kind": "manager", "value": "冲突人",
            "report_date": "2026-01-10", "report_date_source": "filename", "confidence": 0.98,
            "review_status": "pending", "extraction_source": "explicit_field",
            "source_ref": {"excerpt": "测试基金 基金经理：冲突人"},
        }]

    def get_report(self, report_id):
        return deepcopy(self.report) if report_id == "report-1" else None

    def update_report(self, report_id, fields):
        self.report.update(deepcopy(fields))
        return deepcopy(self.report)

    def list_manager_review_reports(self, folder_id=None):
        return []

    def list_report_manager_links(self, report_id):
        return []

    def remove_report_manager_link(self, report_id, manager_id):
        return None


class ManagerRepo:
    def __init__(self):
        self.saved = {}
        self.tenures = {}

    def upsert_manager(self, manager_id, data):
        self.saved[manager_id] = deepcopy(data)
        return True

    def replace_fund_tenures(self, manager_id, tenures):
        self.tenures[manager_id] = deepcopy(tenures)
        return True

    def list_identity_catalog(self):
        return []

    def list_fund_tenures(self, manager_id):
        return []


class FundRepo:
    def __init__(self):
        self.assignments = {}

    def get_fund(self, code):
        return {
            "wind_code": code,
            "manager_ids": self.assignments.get(code, []),
            "raw_data": {"universe": {"company": (
                "另一基金管理有限公司" if code == "000002.OF" else "测试基金管理有限公司"
            )}},
        }

    def update_manager_assignments(self, code, manager_ids, manager_sync):
        self.assignments[code] = list(manager_ids)
        return True


def main():
    repo = ReportRepo()
    manager_repo = ManagerRepo()
    fund_repo = FundRepo()
    service = ResearchMemoManagerIdentitySyncService(
        DataService(), repo, manager_repo, fund_repo,
        company_names=["测试基金管理有限公司", "另一基金管理有限公司"],
    )

    preview = service.sync_pending(apply=False)
    assert preview["resolved_name_count"] == 1
    assert preview["ambiguous_name_count"] == 1
    assert preview["identity_conflict_name_count"] == 1
    assert not manager_repo.saved

    result = service.sync_pending(apply=True)
    assert result["persisted_manager_count"] == 1
    assert result["persisted_tenure_count"] == 1
    assert result["updated_proposal_count"] == 1
    assert result["updated_fund_assignment_count"] == 1
    assert fund_repo.assignments["000001.OF"] == ["张三|M|硕士"]
    assert manager_repo.saved["张三|M|硕士"]["company"] == "测试基金管理有限公司"
    assert manager_repo.tenures["张三|M|硕士"][0]["fund_name"] == "000001.OF"
    proposal = repo.report["review_proposals"][0]
    assert proposal["candidate_id"] == "张三|M|硕士"
    assert proposal["identity_verification"]["status"] == "unique_exact_name"
    assert service._company_alias("安信基金管理有限责任公司") == "安信"
    assert service._company_alias("万家基金管理") == "万家"

    exact = service._audit_verification({
        "title": "测试基金张三纪要",
        "local_relative_path": "2026/测试基金张三20260110.docx",
        "report_date": "2026-01-10",
        "report_date_source": "filename",
        "report_date_precision": "day",
    }, {
        "kind": "manager",
        "value": "张三",
        "candidate_id": "张三|M|硕士",
        "source_ref": {"excerpt": "测试基金 基金经理：张三"},
    }, DataService().get_manager_identity_candidates("张三"))
    assert exact["status"] == "unique_exact_name", exact

    incomplete = service._audit_verification({
        "title": "测试基金张三纪要",
        "local_relative_path": "2026/测试基金张三.docx",
        "report_date": None,
        "report_date_source": "unknown",
        "report_date_precision": "unknown",
    }, {
        "kind": "manager",
        "value": "张三",
        "candidate_id": "张三|M|硕士",
        "source_ref": {"excerpt": "测试基金 基金经理：张三"},
    }, DataService().get_manager_identity_candidates("张三"))
    assert incomplete["status"] == "exact_name_evidence_incomplete", incomplete

    conflict = service._audit_verification({
        "title": "测试基金冲突人纪要",
        "local_relative_path": "2026/测试基金冲突人20260110.docx",
        "report_date": "2026-01-10",
        "report_date_source": "filename",
        "report_date_precision": "day",
    }, {
        "kind": "manager",
        "value": "冲突人",
        "candidate_id": "冲突人|M|硕士",
        "source_ref": {"excerpt": "测试基金 基金经理：冲突人"},
    }, DataService().get_manager_identity_candidates("冲突人"))
    assert conflict["status"] == "identity_conflict", conflict
    print("research memo manager identity sync smoke passed")


if __name__ == "__main__":
    main()
