import os
import sys
from copy import deepcopy

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from services.research_memo_profile_projection_service import (  # noqa: E402
    ResearchMemoProfileProjectionService,
)


class MemoryReportRepo:
    def __init__(self, reports):
        self.reports = {report["id"]: deepcopy(report) for report in reports}

    def list_reports_for_fund(self, wind_code):
        return [
            deepcopy(report)
            for report in self.reports.values()
            if wind_code in report.get("fund_ids", [])
        ]


class MemoryProfileRepo:
    def __init__(self):
        self.profiles = {}

    def get_profile(self, wind_code):
        profile = self.profiles.get(wind_code)
        return deepcopy(profile) if profile else None

    def upsert_profile(self, **fields):
        saved = deepcopy(fields)
        self.profiles[fields["wind_code"]] = saved
        return deepcopy(saved)

    def delete_projected_profile(self, wind_code, updated_by):
        profile = self.profiles.get(wind_code)
        if not profile or profile.get("updated_by") != updated_by:
            return False
        del self.profiles[wind_code]
        return True

    def clear_projected_style(self, wind_code, updated_by):
        profile = self.profiles.get(wind_code)
        if not profile or profile.get("updated_by") != updated_by or not profile.get("manager_tenure_start"):
            return False
        profile["style_label"] = ""
        profile["strategy_tags"] = []
        profile["updated_by"] = "manager-tenure-sync"
        return True


class FakeClassificationAdapter:
    def get_classification_context(self, wind_code):
        return {
            "status": "resolved",
            "fund_code": wind_code,
            "canonical_code": "000001.OF" if wind_code in {"000001.OF", "000001.C"} else wind_code,
            "peer_group_key": "peer-active-equity-stock-hs300",
            "peer_group_name": "主动权益-沪深300参考组",
            "benchmark_mapping": {
                "benchmark_code": "000300.SH",
                "benchmark_name": "沪深300",
            },
            "classification_evidence": [{
                "field": "peer_group_members.peer_group_id",
                "source": "peer_group_members",
            }],
            "missing_items": [],
        }

    def list_entity_share_codes(self, wind_code):
        if wind_code in {"000001.OF", "000001.C"}:
            return ["000001.OF", "000001.C"]
        return [wind_code]


def proposal(proposal_id, kind, value, status, excerpt, confidence=0.9, target_fund_ids=None):
    return {
        "id": proposal_id,
        "kind": kind,
        "value": value,
        "review_status": status,
        "reviewed_at": "2026-08-10T08:00:00+00:00" if status != "pending" else None,
        "confidence": confidence,
        "scope": "fund",
        "target_fund_ids": target_fund_ids if target_fund_ids is not None else ["000001.OF", "000001.C"],
        "source_ref": {
            "relative_path": f"张三/{proposal_id}.md",
            "source_path": f"/research/张三/{proposal_id}.md",
            "excerpt": excerpt,
        },
    }


def main() -> int:
    reports = [
        {
            "id": "report-1",
            "title": "第一次访谈",
            "report_date": "2026-06-01",
            "updated_at": "2026-08-10T08:00:00+00:00",
            "fund_ids": ["000001.C"],
            "style_labels": ["成长"],
            "classifications": ["主动权益"],
            "tags": ["低换手"],
            "review_proposals": [
                proposal("style-growth-1", "style_label", "成长", "confirmed", "长期偏好成长股", 0.95),
                proposal(
                    "manager-style",
                    "style_label",
                    "红利",
                    "confirmed",
                    "经理整体偏好红利",
                    0.99,
                    target_fund_ids=[],
                ),
                proposal("class-equity", "classification", "主动权益", "confirmed", "以主动选股为主"),
                proposal("tag-turnover", "tag", "低换手", "confirmed", "组合换手率较低"),
                proposal("style-pending", "style_label", "主题", "pending", "阶段性关注主题"),
            ],
        },
        {
            "id": "report-2",
            "title": "第二次访谈",
            "report_date": "2026-07-01",
            "updated_at": "2026-08-10T09:00:00+00:00",
            "fund_ids": ["000001.OF"],
            "style_labels": ["成长", "价值"],
            "classifications": ["QDII"],
            "tags": ["质量"],
            "review_proposals": [
                proposal("style-growth-2", "style_label", "成长", "confirmed", "成长仍是主要风格", 0.92),
                proposal("style-value", "style_label", "价值", "confirmed", "也关注估值保护", 0.84),
                proposal("class-qdii", "classification", "QDII", "confirmed", "纪要中的分类不得覆盖标准目录"),
                proposal("tag-quality", "tag", "质量", "confirmed", "重视盈利质量"),
            ],
        },
    ]
    report_repo = MemoryReportRepo(reports)
    profile_repo = MemoryProfileRepo()
    service = ResearchMemoProfileProjectionService(
        report_repo=report_repo,
        profile_repo=profile_repo,
        classification_adapter=FakeClassificationAdapter(),
    )

    result = service.project_report(reports[1], ["000001.C", "000001.OF"])
    profile = profile_repo.get_profile("000001.OF")
    if result.get("projected_count") != 1 or len(result.get("funds") or []) != 1 or not profile:
        raise AssertionError(f"Confirmed memo labels should create a profile: {result}")
    if profile.get("style_label") != "成长":
        raise AssertionError(f"Most frequently confirmed style should be primary: {profile}")
    if profile.get("peer_group") != "主动权益-沪深300参考组" or profile.get("primary_benchmark") != "沪深300":
        raise AssertionError(f"Peer group and benchmark must come from standardized classification: {profile}")
    if set(profile.get("strategy_tags") or []) != {"成长", "价值", "主动权益", "QDII", "低换手", "质量"}:
        raise AssertionError(f"Confirmed labels should aggregate and deduplicate: {profile}")
    if "主题" in profile.get("strategy_tags", []):
        raise AssertionError(f"Pending labels must not enter the profile: {profile}")
    if "红利" in profile.get("strategy_tags", []):
        raise AssertionError(f"Manager-level styles must not leak into a fund profile: {profile}")

    profile_repo.profiles["000001.C"] = {
        "wind_code": "000001.C",
        "style_label": "旧份额标签",
        "updated_by": service.UPDATED_BY,
    }
    alias_cleaned = service.project_report(reports[1], ["000001.C"])
    if profile_repo.get_profile("000001.C") is not None:
        raise AssertionError("Non-canonical share-class style profiles must be removed")
    if alias_cleaned.get("funds", [{}])[0].get("alias_cleanup_count") != 1:
        raise AssertionError(f"Share-class cleanup must be auditable: {alias_cleaned}")

    evidence = profile.get("evidence", {}).get("research_memos", [])
    growth_evidence = next(item for item in evidence if item.get("value") == "成长")
    if not growth_evidence.get("report_id") or not growth_evidence.get("source_path") or not growth_evidence.get("excerpt"):
        raise AssertionError(f"Projected evidence must retain report, file and excerpt: {growth_evidence}")
    if growth_evidence.get("review_status") != "confirmed" or growth_evidence.get("confidence") is None:
        raise AssertionError(f"Projected evidence must retain review status and confidence: {growth_evidence}")

    for report in report_repo.reports.values():
        report["style_labels"] = []
        for item in report["review_proposals"]:
            if item.get("kind") == "style_label":
                item["review_status"] = "rejected"
    current = report_repo.reports["report-2"]
    deleted = service.project_report(current, ["000001.OF"])
    if deleted.get("deleted_count") != 1 or profile_repo.get_profile("000001.OF") is not None:
        raise AssertionError(f"Revoking all styles should delete only the projected profile: {deleted}")

    profile_repo.profiles["000002.OF"] = {
        "wind_code": "000002.OF",
        "style_label": "手工标签",
        "updated_by": "analyst",
    }
    manual_report = deepcopy(reports[0])
    manual_report["id"] = "manual-report"
    manual_report["fund_ids"] = ["000002.OF"]
    report_repo.reports[manual_report["id"]] = manual_report
    preserved = service.project_report(manual_report, ["000002.OF"])
    if preserved.get("funds", [{}])[0].get("reason") != "manual_profile_preserved":
        raise AssertionError(f"Manual profiles must not be overwritten: {preserved}")
    if profile_repo.get_profile("000002.OF",).get("style_label") != "手工标签":
        raise AssertionError("Manual profile changed unexpectedly")

    tenure_report = deepcopy(reports[0])
    tenure_report["id"] = "tenure-report"
    tenure_report["fund_ids"] = ["000003.OF"]
    tenure_report["style_labels"] = ["成长"]
    tenure_report["review_proposals"] = [
        proposal("tenure-growth", "style_label", "成长", "confirmed", "成长风格", target_fund_ids=["000003.OF"])
    ]
    report_repo.reports[tenure_report["id"]] = tenure_report
    profile_repo.profiles["000003.OF"] = {
        "wind_code": "000003.OF",
        "manager_tenure_start": "2024-06-01",
        "updated_by": "manager-tenure-sync",
    }
    merged = service.project_report(tenure_report, ["000003.OF"])
    merged_profile = profile_repo.get_profile("000003.OF")
    if merged.get("projected_count") != 1 or merged_profile.get("style_label") != "成长":
        raise AssertionError(f"Manager tenure profile must accept reviewed memo styles: {merged}")
    if merged_profile.get("manager_tenure_start") != "2024-06-01":
        raise AssertionError("Memo style projection must preserve manager tenure start")
    tenure_report["style_labels"] = []
    tenure_report["review_proposals"][0]["review_status"] = "rejected"
    report_repo.reports[tenure_report["id"]] = tenure_report
    cleared = service.project_report(tenure_report, ["000003.OF"])
    retained_profile = profile_repo.get_profile("000003.OF")
    if cleared.get("cleared_count") != 1 or not retained_profile:
        raise AssertionError("Revoking memo styles must retain the manager tenure profile")
    if retained_profile.get("style_label") or retained_profile.get("manager_tenure_start") != "2024-06-01":
        raise AssertionError(retained_profile)

    print("OK reviewed memo evidence projects into fund profiles without overriding standardized classification")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
