"""选基首页聚合服务冒烟测试。"""

from datetime import date
from pathlib import Path
import sys


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from services.fund_home_service import FundHomeService  # noqa: E402


class FundRepo:
    def browse_funds(self, **kwargs):
        assert kwargs == {"page": 1, "page_size": 1}
        return [], 1486


class ManagerBrowser:
    def browse(self, **kwargs):
        assert kwargs == {"page": 1, "page_size": 4}
        return {"total": 210, "managers": [{"id": "张三", "name": "张三"}]}


class RecommendationService:
    def build_home_coverage_report(self, limit):
        assert limit == 100
        return {
            "summary": {
                "database_fund_count": 1200,
                "ready_category_count": 12,
                "recommendation_ready_count": 180,
            },
            "groups": [{
                "key": "active_equity",
                "name": "主动权益-沪深300参考",
                "status": "ready",
                "database_fund_count": 80,
                "recommendation_ready_count": 10,
                "style_ready_count": 4,
                "classified_count": 80,
            }],
        }


class ReportRepo:
    def list_reports(self, **kwargs):
        assert kwargs == {"page": 1, "page_size": 5}
        return {
            "total": 225,
            "reports": [{
                "id": "report-1",
                "title": "张三调研纪要",
                "manager_name": "张三",
                "report_date": date(2026, 8, 1),
                "summary": "坚持可核验的研究框架。",
                "tags": ["价值"],
            }],
        }


class WatchlistService:
    def list_pools(self):
        return [{"id": "watch-1", "name": "我的自选", "member_count": 3}]


def main():
    result = FundHomeService(
        fund_repo=FundRepo(),
        manager_browser=ManagerBrowser(),
        recommendation_service=RecommendationService(),
        report_repo=ReportRepo(),
        watchlist_service=WatchlistService(),
    ).build()
    assert result["interface_version"] == "fund_selection_home_v1"
    assert result["summary"]["fund_share_count"] == 1486
    assert result["summary"]["fund_manager_count"] == 210
    assert result["summary"]["research_memo_count"] == 225
    assert result["summary"]["watchlist_fund_count"] == 3
    assert result["featured_peer_groups"][0]["href"].startswith("/recommendations?category=")
    assert result["latest_research_memos"][0]["report_date"] == "2026-08-01"
    assert result["product_scope"]["investment_decision"] == "excluded"
    assert result["product_scope"]["market_timing"] == "excluded"
    assert result["product_scope"]["sales_rules"] == "excluded"
    print("fund home service smoke passed")


if __name__ == "__main__":
    main()
