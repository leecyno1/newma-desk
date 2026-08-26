"""Contract smoke test for the AI analysis version timeline."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.analysis_history_service import AnalysisHistoryService


class FakeAnalysisReportRepo:
    def __init__(self):
        self.records = [
            {
                "id": "v3-other-type",
                "target_type": "fund",
                "target_id": "110011.OF",
                "report_type": "fund_research_report",
                "content": "other",
                "generation_params": {"mode": "deterministic"},
                "created_at": "2026-08-03T09:00:00",
            },
            {
                "id": "v2",
                "target_type": "fund",
                "target_id": "110011.OF",
                "report_type": "fund_evaluation_analysis",
                "content": "second",
                "generation_params": {
                    "mode": "llm_evaluation_evidence",
                    "provider": "siliconflow",
                    "model": "deepseek-ai/DeepSeek-V4-Flash",
                    "question": "风格是否稳定？",
                },
                "created_at": "2026-08-02T09:00:00",
            },
            {
                "id": "v1",
                "target_type": "fund",
                "target_id": "110011.OF",
                "report_type": "fund_evaluation_analysis",
                "content": "first",
                "generation_params": {
                    "mode": "deterministic_evaluation_evidence",
                    "question": "",
                },
                "created_at": "2026-08-01T09:00:00",
            },
        ]

    def get_report(self, report_id):
        return next((record for record in self.records if record["id"] == report_id), None)

    def list_versions(self, target_type, target_id, report_type, limit):
        assert (target_type, target_id, report_type) == (
            "fund",
            "110011.OF",
            "fund_evaluation_analysis",
        )
        return [
            record
            for record in self.records
            if record["target_type"] == target_type
            and record["target_id"] == target_id
            and record["report_type"] == report_type
        ][:limit]


timeline = AnalysisHistoryService(FakeAnalysisReportRepo()).timeline_for_report("v2")

assert timeline["target_id"] == "110011.OF"
assert timeline["current_revision"] == 2
assert timeline["total_revisions"] == 2
assert [item["id"] for item in timeline["revisions"]] == ["v2", "v1"]
assert [item["revision"] for item in timeline["revisions"]] == [2, 1]
assert timeline["revisions"][0]["is_current"] is True
assert timeline["revisions"][0]["mode"] == "llm_evaluation_evidence"
assert timeline["revisions"][0]["question"] == "风格是否稳定？"
assert "模型" in timeline["revisions"][0]["change_summary"]
assert timeline["revisions"][1]["mode_label"] == "本地证据评价"

try:
    AnalysisHistoryService(FakeAnalysisReportRepo()).timeline_for_report("missing")
except ValueError as error:
    assert str(error) == "analysis_report_not_found"
else:
    raise AssertionError("Missing reports must fail closed")

print("OK analysis history timeline contract")
