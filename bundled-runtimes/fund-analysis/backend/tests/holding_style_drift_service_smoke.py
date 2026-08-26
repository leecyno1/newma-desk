import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from services.holding_style_drift_service import HoldingStyleDriftService


def snapshot(quarter, size, growth, *, group="peer-active-equity", labels=None):
    def factor(name, percentile, label):
        return {
            "factor": name,
            "percentile": percentile,
            "percentile_label": label,
            "signal_status": "material",
        }

    return {
        "wind_code": "000063.OF",
        "quarter": quarter,
        "peer_group_id": group,
        "peer_group_name": "主动权益同类",
        "peer_percentiles": [
            factor("SIZE", size, "同类偏大盘" if size >= 2 / 3 else "同类中盘"),
            factor("GROWTH", growth, "同类成长偏强" if growth >= 2 / 3 else "同类成长中等"),
            factor("RESVOL", 0.78, "同类高波"),
        ],
        "style_labels": labels or ["高波"],
        "holdings_disclosed_weight": 0.52,
        "status": "peer_percentile_ready",
    }


def main():
    medium = HoldingStyleDriftService.analyze("000063.OF", [
        snapshot("2026Q2", 0.736842, 0.55, labels=["偏大盘", "价值成长均衡", "高波"]),
        snapshot("2026Q1", 0.371429, 0.28, labels=["中盘", "价值成长均衡", "高波"]),
    ])
    assert medium["status"] == "available", medium
    assert medium["level"] == "medium", medium
    assert medium["previous_quarter"] == "2026Q1", medium
    assert medium["latest_quarter"] == "2026Q2", medium
    assert medium["max_percentile_change"] == 0.365413, medium
    assert medium["included_in_score"] is False, medium
    assert "不是收益基础风格分析" in medium["note"], medium

    low = HoldingStyleDriftService.analyze("000063.OF", [
        snapshot("2026Q2", 0.54, 0.52),
        snapshot("2026Q1", 0.50, 0.48),
    ])
    assert low["level"] == "low", low

    high = HoldingStyleDriftService.analyze("000063.OF", [
        snapshot("2026Q2", 0.88, 0.80, labels=["偏大盘", "偏成长", "高波"]),
        snapshot("2026Q1", 0.25, 0.20, labels=["偏小盘", "偏价值", "低波"]),
    ])
    assert high["level"] == "high", high

    incomparable = HoldingStyleDriftService.analyze("000063.OF", [
        snapshot("2026Q2", 0.70, 0.60, group="peer-active-equity"),
        snapshot("2026Q1", 0.45, 0.40, group="peer-index"),
    ])
    assert incomparable["status"] == "incomparable", incomparable
    assert incomparable["level"] == "unavailable", incomparable

    insufficient = HoldingStyleDriftService.analyze(
        "000063.OF",
        [snapshot("2026Q2", 0.70, 0.60)],
    )
    assert insufficient["status"] == "insufficient_evidence", insufficient
    print("OK adjacent disclosed holding style drift keeps comparable evidence and score boundaries")


if __name__ == "__main__":
    main()
