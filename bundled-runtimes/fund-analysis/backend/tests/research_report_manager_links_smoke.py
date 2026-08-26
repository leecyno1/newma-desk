from copy import deepcopy
from pathlib import Path
import sys


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.local_research_folder_service import LocalResearchFolderService  # noqa: E402


class Repo:
    def __init__(self):
        self.report = {
            "id": "report-1",
            "manager_id": "",
            "manager_name": "",
            "manager_links": [],
            "fund_ids": [],
            "classifications": [],
            "style_labels": [],
            "tags": [],
            "review_status": "pending",
            "review_proposals": [
                {
                    "id": "manager-a",
                    "kind": "manager",
                    "value": "张三",
                    "candidate_id": "manager-a-id",
                    "identity_verification": {"status": "unique_exact_name"},
                    "confidence": 0.96,
                    "review_status": "pending",
                    "extraction_source": "filename_pattern",
                    "source_ref": {"excerpt": "文件名：张三、李四.docx"},
                },
                {
                    "id": "manager-b",
                    "kind": "manager",
                    "value": "李四",
                    "candidate_id": "manager-b-id",
                    "identity_verification": {"status": "unique_exact_name"},
                    "confidence": 0.96,
                    "review_status": "pending",
                    "extraction_source": "filename_pattern",
                    "source_ref": {"excerpt": "文件名：张三、李四.docx"},
                },
            ],
        }

    def list_pending_reviews(self, folder_id=None):
        return [
            {
                "report_id": self.report["id"],
                "report_title": "多人纪要",
                "report_date_source": "filename",
                **deepcopy(item),
            }
            for item in self.report["review_proposals"]
            if item["review_status"] == "pending"
        ]

    def get_report(self, report_id):
        assert report_id == self.report["id"]
        return deepcopy(self.report)

    def update_report(self, report_id, fields):
        assert report_id == self.report["id"]
        self.report.update(deepcopy(fields))
        return self.get_report(report_id)

    def list_report_manager_links(self, report_id):
        return deepcopy(self.report["manager_links"])

    def set_report_manager_link(self, report_id, manager_id, manager_name, source="research_memo_review", confirmed_at=None):
        self.remove_report_manager_link(report_id, manager_id)
        self.report["manager_links"].append({
            "manager_id": manager_id,
            "manager_name": manager_name,
            "source": source,
            "confirmed_at": confirmed_at,
        })

    def remove_report_manager_link(self, report_id, manager_id):
        self.report["manager_links"] = [
            item for item in self.report["manager_links"]
            if item["manager_id"] != manager_id
        ]


def main():
    repo = Repo()
    result = LocalResearchFolderService(repo=repo).confirm_manager_proposals(min_confidence=0.88)
    assert result["confirmed"] == 1
    assert result["multi_manager"] == 1
    assert result["ambiguous"] == 0
    assert {item["manager_id"] for item in repo.report["manager_links"]} == {
        "manager-a-id", "manager-b-id",
    }
    assert repo.report["manager_id"] == ""
    assert repo.report["manager_name"] == ""
    assert all(item["review_status"] == "confirmed" for item in repo.report["review_proposals"])

    service = LocalResearchFolderService(repo=repo)
    service.review_proposal("report-1", "manager-a", "rejected")
    assert [item["manager_id"] for item in repo.report["manager_links"]] == ["manager-b-id"]
    assert repo.report["manager_id"] == "manager-b-id"
    assert repo.report["manager_name"] == "李四"
    print("research report manager links smoke passed")


if __name__ == "__main__":
    main()
