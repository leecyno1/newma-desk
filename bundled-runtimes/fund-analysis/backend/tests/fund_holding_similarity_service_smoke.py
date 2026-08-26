from services.fund_holding_similarity_service import FundHoldingSimilarityService


def rows(code, quarter, weights):
    return [
        {
            "wind_code": code,
            "quarter": quarter,
            "stock_code": stock_code,
            "stock_name": stock_code,
            "equity_portfolio_weight": weight,
            "weight_basis": "equity_portfolio",
            "report_date": "2026-06-30",
        }
        for stock_code, weight in weights
    ]


class FakeHoldingRepo:
    def __init__(self):
        self.histories = {
            "A.OF": rows("A.OF", "2026Q2", [("A", 4), ("B", 3), ("C", 2), ("D", 1), ("E", 0.5)]),
            "B.OF": rows("B.OF", "2026Q2", [("A", 5), ("B", 2), ("C", 1), ("F", 1), ("G", 1)]),
            "C.OF": rows("C.OF", "2026Q1", [("H", 5), ("I", 4), ("J", 3), ("K", 2), ("L", 1)]),
        }

    def get_holdings_history(self, wind_code):
        return self.histories.get(wind_code, [])


service = FundHoldingSimilarityService(holding_repo=FakeHoldingRepo())
result = service.build(["A.OF", "B.OF"])
pair = result["pairs"][0]

assert result["status"] == "available"
assert result["methodology"] == "same_quarter_top10_normalized_overlap_v1"
assert result["simulation_used"] is False
assert pair["quarter"] == "2026Q2"
assert pair["common_holding_count"] == 3
assert pair["union_holding_count"] == 7
assert pair["overlap_ratio"] == 0.68095238
assert pair["jaccard_score"] == 0.42857143
assert pair["similarity_level"] == "high"
assert [item["stock_code"] for item in pair["common_holdings"]] == ["A", "B", "C"]

missing = service.build(["A.OF", "C.OF"])
assert missing["status"] == "insufficient"
assert missing["pairs"][0]["missing_items"] == ["没有同一报告期的可信前十大持仓"]

print("OK fund holding similarity uses aligned top-10 disclosures and normalized weights")
