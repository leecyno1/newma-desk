from services.fund_evaluation_methodology import FundEvaluationMethodology
from services.fund_evaluation_service import FundEvaluationService


CLASSIFICATION = {
    "status": "classified",
    "evaluation_profile_key": "index_fund",
    "peer_group_id": "peer-index-hs300",
    "peer_group": "指数-沪深300",
    "primary_benchmark": "沪深300",
    "minimum_peer_count": 5,
}


class WindowScoringService:
    def __init__(self):
        self.methodology = FundEvaluationMethodology()

    def score_from_inputs(
        self,
        fund,
        profile,
        panel,
        quality,
        standardized_classification,
        evaluation_window="1y",
    ):
        score = {"6m": 61.0, "1y": 45.0, "3y": 70.0}[evaluation_window]
        return {
            "status": "ok",
            "target_id": fund["wind_code"],
            "overall_score": score,
            "overall_grade": "C",
            "dimension_scores": {"tracking_quality": {"score": score, "weight": 1.0, "weighted_score": score, "evidence": []}},
            "metric_scores": {f"{evaluation_window}.tracking_error": 0.01},
            "positive_factors": [],
            "negative_factors": [],
            "missing_data": [],
            "data_quality": quality,
            "classification": CLASSIFICATION,
            "fund_type_profile": "index_fund",
            "as_of_date": "2026-08-12",
            "calculation_method": f"category_evaluation_methodology_v3:index_fund:{evaluation_window}",
        }


class WindowPeerService:
    def build_peer_percentiles(self, wind_code, window="1y", target_context=None):
        score = {"6m": 61.0, "1y": 45.0, "3y": 70.0}[window]
        return {
            "target_id": wind_code,
            "classification": CLASSIFICATION,
            "peer_group": CLASSIFICATION["peer_group"],
            "primary_benchmark": CLASSIFICATION["primary_benchmark"],
            "peer_group_source": "standardized_peer_group_membership",
            "peer_count": 10,
            "classified_peer_count": 10,
            "valid_metric_peer_count": 10,
            "minimum_valid_peer_count": 5,
            "sample_status": "sufficient",
            "metric_window": window,
            "metrics": {
                "professional_score": {
                    "value": score,
                    "rank": 5,
                    "peer_count": 10,
                    "percentile": 55.56,
                    "sample_status": "sufficient",
                }
            },
        }


class CrossMarketService:
    def build(self, wind_code, classification=None):
        return {
            "status": "not_requested",
            "included_in_score": False,
            "comparisons": [],
            "labels": [],
            "missing_items": [],
        }


class HoldingChangeService:
    def analyze(self, wind_code, refresh_missing=False):
        assert wind_code == "005639.OF"
        assert refresh_missing is False
        return {
            "status": "available",
            "latest_quarter": "2026Q2",
            "previous_quarter": "2026Q1",
            "source": "local.postgres.holdings",
            "stability": {
                "status": "available",
                "label": "前十大持仓延续性较高",
                "top10_overlap_ratio": 0.8,
                "industry_overlap_ratio": 0.9,
                "included_in_score": False,
            },
        }


if __name__ == "__main__":
    methodology = FundEvaluationMethodology()
    metrics = {
        "6m": {"tracking_error": 0.006, "tracking_difference": 0.004},
        "1y": {"tracking_error": 0.025, "tracking_difference": 0.02},
        "latest": {"expense_ratio": 0.006, "aum": 20.0},
    }
    quality = {"score": 90, "issues": []}
    six_month = methodology.evaluate("index_fund", metrics, quality, selected_window="6m")
    one_year = methodology.evaluate("index_fund", metrics, quality, selected_window="1y")
    assert six_month["total_score"] != one_year["total_score"], (six_month, one_year)
    assert six_month["evaluation_window"] == "6m", six_month
    assert six_month["calculation_method"].endswith(":index_fund:6m"), six_month
    detail = methodology.describe("index_fund", "6m")
    assert detail["profile_name"] == "被动指数基金评价", detail
    assert detail["dimensions"][0]["metrics"][0]["path"] == "6m.tracking_error", detail

    service = FundEvaluationService(
        scoring_service=WindowScoringService(),
        peer_comparison_service=WindowPeerService(),
        cross_market_peer_service=CrossMarketService(),
        holding_change_service=HoldingChangeService(),
    )
    results = service.evaluate_windows_from_context({
        "found": True,
        "fund": {"wind_code": "005639.OF"},
        "profile": {},
        "metric_panel": [],
        "data_quality": {"status": "complete", "score": 90},
        "standardized_classification": CLASSIFICATION,
    }, ["6m", "1y", "3y"])
    assert [results[window]["evaluation"]["overall_score"] for window in ("6m", "1y", "3y")] == [61.0, 45.0, 70.0], results
    assert results["6m"]["methodology"]["evaluation_window"] == "6m", results["6m"]
    assert results["1y"]["methodology_version"] == "fund_evaluation_v3", results["1y"]
    stability = results["1y"]["explanatory_evidence"]["holding_stability"]
    assert stability["top10_overlap_ratio"] == 0.8, stability
    assert stability["included_in_score"] is False, stability

    print("OK formal evaluation score and score detail use the selected window")
