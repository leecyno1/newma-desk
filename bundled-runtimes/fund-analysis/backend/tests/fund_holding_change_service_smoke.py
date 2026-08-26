from services.fund_holding_change_service import FundHoldingChangeService


class Repo:
    def get_holdings_history(self, wind_code):
        assert wind_code == "TEST.OF"
        return [
            {"quarter": "2026Q2", "stock_code": "A", "stock_name": "甲", "industry": "医药", "equity_portfolio_weight": 0.20, "report_date": "2026-06-30"},
            {"quarter": "2026Q2", "stock_code": "C", "stock_name": "丙", "industry": "医疗", "equity_portfolio_weight": 0.10, "report_date": "2026-06-30"},
            {"quarter": "2026Q1", "stock_code": "A", "stock_name": "甲", "industry": "医药", "equity_portfolio_weight": 0.15, "report_date": "2026-03-31"},
            {"quarter": "2026Q1", "stock_code": "B", "stock_name": "乙", "industry": "医疗", "equity_portfolio_weight": 0.12, "report_date": "2026-03-31"},
        ]


result = FundHoldingChangeService(repo=Repo()).analyze("TEST.OF", refresh_missing=False)
changes = {item["stock_code"]: item for item in result["changes"]}

assert result["status"] == "available"
assert result["latest_quarter"] == "2026Q2"
assert result["previous_quarter"] == "2026Q1"
assert result["weight_basis"] == "equity_portfolio_weight"
assert round(changes["A"]["weight_change"], 4) == 0.05
assert changes["B"]["change_type"] == "exited_top10"
assert changes["C"]["change_type"] == "entered_top10"
assert result["summary"]["entered_top10_count"] == 1
assert result["summary"]["exited_top10_count"] == 1
assert result["summary"]["latest_top3_weight"] == 0.30
assert result["summary"]["top10_weight_change"] == 0.03
assert result["concentration_trend"][0]["top_industry"] == "医药"
assert result["industry_changes"][0]["weight_change"] in {0.05, -0.02}
assert result["stability"]["status"] == "available"
assert result["stability"]["retained_holding_count"] == 1
assert result["stability"]["union_holding_count"] == 3
assert round(result["stability"]["top10_overlap_ratio"], 4) == 0.5556
assert round(result["stability"]["industry_overlap_ratio"], 4) == 0.8889
assert result["stability"]["included_in_score"] is False

print("OK fund holding changes compare two disclosed top-ten lists")
