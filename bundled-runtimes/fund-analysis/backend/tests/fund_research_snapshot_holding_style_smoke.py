import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from services.fund_research_snapshot_service import FundResearchSnapshotService


class FakeEvaluationService:
    def load_context(self, wind_code):
        return {
            "found": True,
            "fund": {"wind_code": wind_code, "name": "测试基金", "manager_ids": []},
            "profile": {"style_label": "人工确认风格"},
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


class FakeHoldingStyleRepo:
    def __init__(self, snapshot, history=None):
        self.snapshot = snapshot
        self.history = history or ([snapshot] if snapshot else [])

    def get_latest_map(self, codes):
        return {codes[0]: self.snapshot} if self.snapshot else {}

    def list_history(self, _wind_code, limit=6):
        return self.history[:limit]


def build(snapshot, history=None):
    return FundResearchSnapshotService(
        evaluation_service=FakeEvaluationService(),
        holding_style_repo=FakeHoldingStyleRepo(snapshot, history),
    ).build("001938.OF", include_research=False)


def main():
    ready = build({
        "wind_code": "001938.OF",
        "quarter": "2026Q1",
        "peer_group_id": "peer-active-equity",
        "peer_group_key": "active-equity",
        "peer_group_name": "主动权益同类",
        "descriptors": [{"factor": "SIZE", "exposure": 320.0, "unit": "cny_100m"}],
        "peer_percentiles": [{"factor": "SIZE", "percentile": 0.82, "sample_size": 8}],
        "style_labels": ["偏大盘"],
        "peer_sample_size": 8,
        "minimum_peer_count": 5,
        "holdings_disclosed_weight": 0.4575,
        "source": "holding_style_peer_percentile_v1",
        "status": "peer_percentile_ready",
        "missing_items": ["不是完整 Barra 风险模型"],
    })["style_profile"]
    assert ready["quantitative_labels"] == ["偏大盘"], ready
    assert ready["holding_style"]["status"] == "peer_percentile_ready", ready
    assert ready["holding_style"]["quarter"] == "2026Q1", ready
    assert ready["holding_style"]["sample_size"] == 8, ready
    assert ready["holding_style"]["model_scope"].endswith("不是完整 Barra 风险模型。"), ready

    thin = build({
        "wind_code": "001938.OF",
        "quarter": "2026Q1",
        "peer_group_id": "peer-active-equity",
        "peer_group_name": "主动权益同类",
        "descriptors": [{"factor": "SIZE", "exposure": 320.0, "unit": "cny_100m"}],
        "peer_percentiles": [],
        "style_labels": [],
        "peer_sample_size": 1,
        "minimum_peer_count": 5,
        "status": "descriptor_ready",
    })["style_profile"]
    assert thin["quantitative_labels"] == [], thin
    assert thin["holding_style"]["status"] == "descriptor_ready", thin
    assert "只展示原始持仓描述子" in thin["holding_style"]["missing_items"][0], thin

    neutral = build({
        "wind_code": "001938.OF",
        "quarter": "2026Q1",
        "peer_group_id": "peer-index-star50",
        "peer_group_name": "指数-科创50",
        "descriptors": [{"factor": "SIZE", "exposure": 3336.0, "unit": "cny_100m"}],
        "peer_percentiles": [{"factor": "SIZE", "percentile": 1.0, "percentile_label": "同类差异不显著", "signal_status": "not_material", "sample_size": 5}],
        "style_labels": [],
        "peer_sample_size": 5,
        "minimum_peer_count": 5,
        "status": "peer_percentile_ready",
    })["style_profile"]
    assert neutral["holding_style"]["status"] == "peer_percentile_neutral", neutral
    assert neutral["quantitative_labels"] == [], neutral

    drift_latest = {
        "wind_code": "001938.OF",
        "quarter": "2026Q2",
        "peer_group_id": "peer-active-equity",
        "peer_group_name": "主动权益同类",
        "peer_percentiles": [
            {"factor": "SIZE", "percentile": 0.74, "percentile_label": "同类偏大盘", "signal_status": "material"},
            {"factor": "GROWTH", "percentile": 0.55, "percentile_label": "同类成长中等", "signal_status": "material"},
        ],
        "style_labels": ["偏大盘", "价值成长均衡"],
        "peer_sample_size": 8,
        "minimum_peer_count": 5,
        "status": "peer_percentile_ready",
    }
    drift_previous = {
        **drift_latest,
        "quarter": "2026Q1",
        "peer_percentiles": [
            {"factor": "SIZE", "percentile": 0.37, "percentile_label": "同类中盘", "signal_status": "material"},
            {"factor": "GROWTH", "percentile": 0.28, "percentile_label": "同类成长偏弱", "signal_status": "material"},
        ],
        "style_labels": ["中盘", "价值成长均衡"],
    }
    drift_snapshot = build(drift_latest, [drift_latest, drift_previous])
    assert drift_snapshot["holding_style_drift"]["level"] == "medium", drift_snapshot
    assert drift_snapshot["assessment_summary"]["style_drift_evidence"]["included_in_score"] is False, drift_snapshot
    assert drift_snapshot["analysis_evidence"]["factor_evidence"]["holding_style_drift_evidence"]["latest_quarter"] == "2026Q2", drift_snapshot
    assert any(item["key"] == "style_drift" for item in drift_snapshot["plain_language_brief"]["items"]), drift_snapshot
    print("OK unified fund snapshot exposes holding peer styles only after the same-quarter sample gate")


if __name__ == "__main__":
    main()
