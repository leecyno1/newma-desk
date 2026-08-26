"""基金公司浏览器核心聚合冒烟测试。"""

from pathlib import Path
import sys


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from services.fund_company_service import FundCompanyService  # noqa: E402


class FakeCompanyRepo:
    company = "示例基金管理有限公司"

    def list_companies(self, **_kwargs):
        return [{
            "company": self.company,
            "fund_count": 100,
            "manager_count": 1,
            "classified_count": 30,
            "asset_sample_count": 20,
            "synced_total_asset": 600,
            "metric_ready_count": 15,
            "equity_return_1y": 0.12,
            "equity_sample_count": 10,
            "bond_return_1y": 0.03,
            "bond_sample_count": 5,
            "peer_group_count": 2,
            "evaluated_peer_group_count": 1,
        }], 1

    def get_market_summary(self):
        return {"company_count": 1, "fund_count": 100, "metric_ready_count": 15}

    def get_company(self, company):
        return self.list_companies()[0][0] if company == self.company else None

    def get_category_breakdown(self, _company):
        return [
            {"peer_group_name": "混合-偏股", "fund_count": 10, "share_count": 20, "mature_fund_count": 10},
            {"peer_group_name": "指数增强-中证A500", "fund_count": 1, "share_count": 2, "mature_fund_count": 0},
        ]

    def get_company_representative_funds(self, _company, **_kwargs):
        return [{
            "wind_code": "000001.OF",
            "name": "示例基金-A",
            "manager_ids": ["manager-1"],
            "standardized_peer_group_name": "混合-偏股",
            "category_fund_count": 10,
            "metric_evidence_count": 3,
            "metric_as_of": "2026-08-11",
            "annualized_return_1y": 0.12,
            "max_drawdown_1y": -0.08,
            "sharpe_1y": 1.2,
            "establishment_date": "2020-01-01",
        }, {
            "wind_code": "000002.OF",
            "name": "示例新基金-A",
            "manager_ids": [],
            "standardized_peer_group_name": "指数增强-中证A500",
            "category_fund_count": 1,
            "metric_evidence_count": 0,
            "establishment_date": "2026-06-01",
        }]

    def get_category_window_performance(self, _company):
        return [{
            "peer_group_id": "peer-1",
            "peer_group_name": "混合-偏股",
            "metric_window": "1y",
            "total_return": 0.12,
            "max_drawdown": -0.08,
            "sharpe_ratio": 1.2,
            "return_sample_count": 3,
        }]

    def get_company_managers(self, _company):
        return [{
            "wind_code": "manager-1",
            "name": "示例经理",
            "representative_fund_code": "000001.OF",
            "representative_fund_name": "示例基金-A",
        }]


class FakeBrowserService:
    def enrich_rows(self, rows):
        return [
            {
                **rows[0],
                "research_profile": {"peer_group": "混合-偏股"},
                "professional_scoring": {"overall_score": 82.5},
                "managers": [{"wind_code": "manager-1", "name": "示例经理"}],
            },
            {
                **rows[1],
                "research_profile": {"peer_group": "指数增强-中证A500"},
                "professional_scoring": None,
                "managers": [],
            },
        ]


def main():
    service = FundCompanyService(repo=FakeCompanyRepo(), browser_service=FakeBrowserService())
    listing = service.list_companies()
    company = listing["companies"][0]
    assert company["short_name"] == "示例"
    assert company["classification_coverage"] == 0.3
    assert company["metric_coverage"] == 0.15

    detail = service.get_company(FakeCompanyRepo.company)
    representative = detail["representative_funds"][0]
    assert representative["peer_group"] == "混合-偏股"
    assert representative["professional_score"] == 82.5
    assert representative["evaluation_status"] == "evaluated"
    observation = next(fund for fund in detail["representative_funds"] if fund["wind_code"] == "000002.OF")
    assert observation["evaluation_status"] == "observation_period"
    assert "成立时间不足 430 天" in observation["selection_reason"]
    assert detail["category_breakdown"][0]["representative_fund"]["wind_code"] == "000001.OF"
    assert detail["category_breakdown"][1]["representative_fund"]["wind_code"] == "000002.OF"
    assert detail["managers"][0]["representative_fund_name"] == "示例基金-A"
    assert detail["category_window_performance"][0]["metric_window"] == "1y"
    assert "window_performance" not in detail
    assert detail["methodology"]["fund_count"] == "按份额代码计数"
    print("OK company detail exposes professional categories, representative funds and linked managers")


if __name__ == "__main__":
    main()
