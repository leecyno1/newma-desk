import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from services.cross_market_peer_comparison_service import CrossMarketPeerComparisonService


def profile(cn_weight, hk_weight, industry_split=(0.6, 0.4)):
    total = cn_weight + hk_weight
    markets = []
    for market_code, market_label, weight in (
        ("CN_A", "A股", cn_weight),
        ("HK", "港股", hk_weight),
    ):
        if weight <= 0:
            continue
        markets.append({
            "market_code": market_code,
            "market_label": market_label,
            "disclosed_weight": weight,
            "share_of_disclosed": weight / total,
            "security_hhi": 0.25,
            "industry_hhi": sum(item * item for item in industry_split),
            "industry_exposures": [
                {"industry": f"{market_label}行业一", "fund_nav_weight": weight * industry_split[0]},
                {"industry": f"{market_label}行业二", "fund_nav_weight": weight * industry_split[1]},
            ],
            "top_holdings": [
                {"stock_code": f"{market_code}{index}", "fund_nav_weight": weight * share}
                for index, share in enumerate((0.4, 0.3, 0.2, 0.1), start=1)
            ],
        })
    return {
        "status": "partial_evidence",
        "quarter": "2026Q2",
        "total_disclosed_weight": total,
        "markets": markets,
        "missing_items": ["公开持仓只代表已披露部分。"],
    }


class FakeHoldingRepo:
    def __init__(self, codes):
        self.codes = codes
        self.requested_quarter = None

    def get_latest_weighted_quarter(self, wind_code):
        return "2026Q2"

    def get_holdings_map(self, wind_codes, quarter):
        self.requested_quarter = quarter
        return {code: [{"fund_code": code}] for code in self.codes if code in wind_codes}


class FakeClassificationRepo:
    def __init__(self, codes):
        self.codes = codes

    def get_classification_context(self, wind_code):
        return CLASSIFICATION

    def list_peer_funds(self, peer_group_id, target_wind_code=None):
        return [{"wind_code": code} for code in self.codes]


class FakeProfileService:
    def __init__(self, profiles):
        self.profiles = profiles

    def analyze(self, holdings, quarter):
        return self.profiles[holdings[0]["fund_code"]]


CLASSIFICATION = {
    "status": "resolved",
    "peer_group_id": "peer-cross-market-test",
    "peer_group_name": "主动权益-沪港深",
    "minimum_peer_count": 5,
}


def build(codes):
    profiles = {
        code: profile(0.40 - index * 0.05, index * 0.10)
        for index, code in enumerate(codes)
    }
    holding_repo = FakeHoldingRepo(codes)
    service = CrossMarketPeerComparisonService(
        holding_repo=holding_repo,
        classification_repo=FakeClassificationRepo(codes),
        profile_service=FakeProfileService(profiles),
    )
    return service.build(codes[-1], CLASSIFICATION), holding_repo


def main():
    ready, holding_repo = build(["PEER1", "PEER2", "PEER3", "PEER4", "TARGET"])
    assert ready["status"] == "peer_comparison_ready", ready
    assert holding_repo.requested_quarter == "2026Q2", ready
    assert ready["profile_peer_count"] == 5, ready
    assert ready["included_in_score"] is False, ready
    assert any("已披露持仓中港股暴露同类偏高" == label for label in ready["labels"]), ready
    hk_metric = next(item for item in ready["comparisons"] if item["metric"] == "hk_weight")
    assert hk_metric["sample_status"] == "sufficient", hk_metric
    assert hk_metric["percentile"] == 100.0, hk_metric

    thin, _ = build(["PEER1", "PEER2", "PEER3", "TARGET"])
    assert thin["status"] == "insufficient_peer_sample", thin
    assert thin["labels"] == [], thin
    assert all(item["percentile"] is None for item in thin["comparisons"]), thin
    assert "只展示本基金持仓证据" in " ".join(thin["missing_items"]), thin

    print("OK cross-market holding comparison is same-quarter, category-relative and score-neutral")


if __name__ == "__main__":
    main()
