from services.fund_research_snapshot_service import FundResearchSnapshotService
from services.fund_browser_service import FundBrowserService


class SnapshotEvaluationService:
    def __init__(self):
        self.scoring_calls = 0

    def load_context(self, wind_code):
        return {
            "found": True,
            "fund": {"wind_code": wind_code, "name": "多窗口基金", "manager_ids": []},
            "profile": {},
            "metric_panel": [],
            "data_quality": {},
            "standardized_classification": {},
        }

    def evaluate_windows_from_context(self, _context, windows):
        self.scoring_calls += 1
        return {
            window: {
                "status": "ok",
                "target": {"wind_code": "000001.OF"},
                "peer_context": {"metric_window": window},
                "evaluation": {"peer_percentiles": {}},
                "missing_items": [],
            }
            for window in windows
        }


def main() -> None:
    evaluation_service = SnapshotEvaluationService()
    multi_window = FundResearchSnapshotService(evaluation_service=evaluation_service).build(
        "000001.OF",
        window="3y",
        include_research=False,
    )
    assert evaluation_service.scoring_calls == 1
    assert set(multi_window["evaluation_windows"]) == {"6m", "1y", "3y"}
    assert multi_window["evaluation"]["peer_context"]["metric_window"] == "3y"

    from repositories import get_fund_classification_repo

    repo = get_fund_classification_repo()
    rows = repo.list_recommendation_funds(
        "指数-沪深300",
        limit=5,
        return_6m_min=0,
        return_1y_min=0,
        return_3y_min=0,
        sort_by="multi_period",
    )
    assert rows, "沪深300同类组应有多周期指标完整的真实基金"

    for row in rows:
        for window in ("6m", "1y", "3y"):
            assert row.get(f"return_{window}_metric") is not None
            percentile = row.get(f"return_{window}_peer_percentile")
            rank = row.get(f"return_{window}_peer_rank")
            peer_count = row.get(f"return_{window}_peer_count")
            assert percentile is not None and 0 <= float(percentile) <= 100
            assert rank is not None and peer_count is not None
            assert 1 <= int(rank) <= int(peer_count)

        projected = FundResearchSnapshotService.project_fund(row)
        assert set(projected["peer_return_metrics"]) == {"6m", "1y", "3y"}

    scores = [
        sum(float(row[f"return_{window}_peer_percentile"]) for window in ("6m", "1y", "3y"))
        for row in rows
    ]
    assert scores == sorted(scores, reverse=True), "多周期排序应按同类分位合计降序"

    browser_result = FundBrowserService().browse(
        peer_group="指数-沪深300",
        page_size=5,
        return_6m_min=0,
        return_1y_min=0,
        return_3y_min=0,
        sort_by="multi_period",
    )
    context = browser_result["selection_context"]
    assert context["sort_label"] == "多周期同类领先", context
    assert {item["key"] for item in context["rules"]} == {
        "peer_group", "return_6m_min", "return_1y_min", "return_3y_min"
    }, context
    assert browser_result["funds"], browser_result
    for fund in browser_result["funds"]:
        explanation = fund["selection_explanation"]
        assert explanation["status"] == "matched", explanation
        assert len(explanation["matched_rules"]) == 4, explanation
        assert "多周期同类位置" in explanation["sort_reason"], explanation
        assert "标准分类目录" in explanation["classification_reason"], explanation

    style_catalog = browser_result["style_tag_catalog"]
    assert style_catalog["coverage"]["fund_count"] >= 10, style_catalog
    assert any(item["value"] == "宽基" for item in style_catalog["tags"]), style_catalog
    style_result = FundBrowserService().browse(
        peer_group="指数-沪深300",
        page_size=5,
        style_tags=["宽基", "被动"],
        style_match="all",
    )
    assert style_result["funds"], style_result
    assert style_result["selection_context"]["style_match"] == "all"
    for fund in style_result["funds"]:
        assert {"宽基", "被动"}.issubset(set(fund["research_profile"]["filter_style_tags"]))
        style_rule = next(
            item for item in fund["selection_explanation"]["matched_rules"]
            if item["key"] == "style_tags"
        )
        assert style_rule["operator"] == "all", style_rule

    holding_style_result = FundBrowserService().browse(
        peer_group="主动权益-沪深300参考",
        page_size=10,
        style_tags=["偏价值"],
    )
    assert holding_style_result["funds"], holding_style_result
    assert holding_style_result["style_tag_catalog"]["coverage"]["holding_quantitative_fund_count"] >= 3
    for fund in holding_style_result["funds"]:
        evidence = fund["research_profile"]["style_tag_evidence"]
        assert any(
            item["value"] == "偏价值" and item["evidence_level"] == "strong"
            for item in evidence
        ), evidence
    print("OK fund browser exposes filtered 6m/1y/3y returns with full-peer percentiles")


if __name__ == "__main__":
    main()
