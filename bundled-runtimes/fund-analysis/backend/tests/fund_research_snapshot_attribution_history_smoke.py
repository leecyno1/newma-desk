from datetime import datetime
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from services.fund_research_snapshot_service import FundResearchSnapshotService


class FakeEvaluationService:
    def load_context(self, wind_code):
        return {
            "found": True,
            "fund": {"wind_code": wind_code, "name": "测试基金", "manager_ids": []},
            "profile": {},
            "metric_panel": [],
            "data_quality": {},
        }

    def evaluate_windows_from_context(self, _context, windows):
        return {
            window: {
                "status": "ok",
                "target": {"wind_code": "001938.OF"},
                "peer_context": {"metric_window": window},
                "evaluation": {},
                "missing_items": [],
            }
            for window in windows
        }


class FakeAttributionService:
    def __init__(self):
        self.calls = []

    def latest_completed_quarter(self):
        return "2026Q2"

    def analyze(self, wind_code, quarter=None):
        self.calls.append((wind_code, quarter))
        return {
            "fund": {"wind_code": wind_code},
            "status": "partial_evidence",
            "quarter": quarter,
            "barra": {"status": "partial_evidence", "missing_items": []},
            "brinson": {"status": "partial_evidence", "effects": [], "missing_items": []},
            "nav_factor_lens": {"status": "ok", "missing_items": []},
            "nav_return_attribution": {"status": "ok", "missing_items": []},
        }


class FakeAttributionRepo:
    def __init__(self, saved=None):
        self.saved = saved

    def get_bundle(self, wind_code, quarter):
        assert wind_code == "001938.OF"
        assert quarter == "2026Q2"
        return self.saved


def build_snapshot(repo, service, live_attribution=True):
    return FundResearchSnapshotService(
        evaluation_service=FakeEvaluationService(),
        attribution_service=service,
        attribution_repo=repo,
    ).build(
        "001938.OF",
        include_research=False,
        include_attribution=True,
        live_attribution=live_attribution,
    )


def main():
    saved_bundle = {
        "bundle": {
            "fund": {"wind_code": "001938.OF"},
            "status": "partial_evidence",
            "quarter": "2026Q2",
            "barra": {"status": "partial_evidence", "missing_items": []},
            "brinson": {"status": "partial_evidence", "effects": [], "missing_items": []},
            "nav_factor_lens": {"status": "ok", "missing_items": []},
            "nav_return_attribution": {"status": "ok", "missing_items": []},
        },
        "updated_at": datetime(2026, 8, 13, 9, 30),
    }
    saved_service = FakeAttributionService()
    saved = build_snapshot(FakeAttributionRepo(saved_bundle), saved_service)["attribution"]
    assert saved_service.calls == [], "有当前季度历史时不应重新计算"
    assert saved["history_reused"] is True
    assert saved["evidence_origin"]["mode"] == "saved_history"

    live_service = FakeAttributionService()
    live = build_snapshot(FakeAttributionRepo(), live_service)["attribution"]
    assert live_service.calls == [("001938.OF", "2026Q2")]
    assert live["history_reused"] is False
    assert live["evidence_origin"]["mode"] == "live_calculation"
    skipped_service = FakeAttributionService()
    skipped = build_snapshot(FakeAttributionRepo(), skipped_service, live_attribution=False)["attribution"]
    assert skipped_service.calls == [], "现场评价关闭归因计算时不得拉取外部数据"
    assert skipped["evidence_origin"]["mode"] == "not_run"
    print("OK AI fund evaluation reuses current-quarter attribution history before live calculation")


if __name__ == "__main__":
    main()
