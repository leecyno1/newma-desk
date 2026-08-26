import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from services.holding_style_peer_service import HoldingStylePeerService


def snapshot(code, size, btop, growth, resvol, minimum=5):
    return {
        "wind_code": code,
        "quarter": "2026Q1",
        "peer_group_id": "peer-group-1",
        "peer_group_key": "peer-active-equity",
        "peer_group_name": "主动权益同类",
        "minimum_peer_count": minimum,
        "descriptors": [
            {"factor": "SIZE", "label": "规模", "exposure": size, "unit": "cny_100m"},
            {"factor": "BTOP", "label": "价值", "exposure": btop, "unit": "multiple"},
            {"factor": "GROWTH", "label": "成长", "exposure": growth, "unit": "ratio"},
            {"factor": "RESVOL", "label": "残差波动率", "exposure": resvol, "unit": "ratio"},
        ],
        "status": "descriptor_ready",
        "missing_items": [],
    }


def main():
    peers = [
        snapshot("A", 100, 0.10, 0.05, 0.50),
        snapshot("B", 200, 0.20, 0.10, 0.40),
        snapshot("C", 300, 0.30, 0.15, 0.30),
        snapshot("D", 400, 0.40, 0.20, 0.20),
        snapshot("E", 500, 0.50, 0.25, 0.10),
    ]
    result = HoldingStylePeerService().enrich(peers[-1], peers)
    percentiles = {item["factor"]: item for item in result["peer_percentiles"]}
    assert percentiles["SIZE"]["percentile"] == 1.0, result
    assert percentiles["SIZE"]["percentile_label"] == "同类偏大盘", result
    assert percentiles["BTOP"]["percentile_label"] == "同类偏价值", result
    assert percentiles["RESVOL"]["percentile_label"] == "同类低波", result
    assert result["style_labels"] == ["偏大盘", "偏价值", "低波"], result
    assert all(item["sample_size"] == 5 for item in result["peer_percentiles"]), result

    stale = dict(peers[-1])
    stale["missing_items"] = [
        "未接入完整风险模型。",
        "同季度同类描述子样本未达到 5 只，只展示原始持仓描述子，不贴风格标签。",
    ]
    refreshed = HoldingStylePeerService().enrich(stale, peers)
    assert refreshed["style_labels"] == ["偏大盘", "偏价值", "低波"], refreshed
    assert refreshed["missing_items"] == ["未接入完整风险模型。"], refreshed

    thin = HoldingStylePeerService().enrich(peers[0], peers[:4])
    assert not thin["peer_percentiles"], thin
    assert not thin["style_labels"], thin
    assert "只展示原始持仓描述子" in thin["missing_items"][-1], thin

    near_identical = [
        snapshot("A", 3330.0, 0.0980, 0.9000, 0.4730),
        snapshot("B", 3332.0, 0.0981, 0.9005, 0.4732),
        snapshot("C", 3334.0, 0.0982, 0.9010, 0.4734),
        snapshot("D", 3336.0, 0.0983, 0.9015, 0.4736),
        snapshot("E", 3338.0, 0.0984, 0.9020, 0.4738),
    ]
    indistinguishable = HoldingStylePeerService().enrich(near_identical[-1], near_identical)
    assert indistinguishable["peer_percentiles"], indistinguishable
    assert not indistinguishable["style_labels"], indistinguishable
    assert indistinguishable["status"] == "peer_percentile_neutral", indistinguishable
    assert all(item["signal_status"] == "not_material" for item in indistinguishable["peer_percentiles"]), indistinguishable
    assert all(item["percentile_label"] == "同类差异不显著" for item in indistinguishable["peer_percentiles"]), indistinguishable
    assert "横截面差异不显著" in indistinguishable["missing_items"][-1], indistinguishable
    print("OK style labels require enough same-quarter peers and material cross-sectional dispersion")


if __name__ == "__main__":
    main()
