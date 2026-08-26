"""基金经理浏览器核心聚合冒烟测试。"""

from datetime import date
from decimal import Decimal
from pathlib import Path
import sys


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from services.fund_manager_browser_service import FundManagerBrowserService  # noqa: E402


class ManagerRepo:
    def browse_managers(self, **kwargs):
        assert kwargs["category"] == "fixed_income"
        assert kwargs["evidence"] == "research_ready"
        return {
            "total": 1,
            "managers": [{
                "id": "张三|M|硕士",
                "name": "张三",
                "company": "示例基金管理有限公司",
                "education": "硕士",
                "management_years": Decimal("6.25"),
                "current_fund_codes": ["000001.OF", "000002.OF"],
                "current_fund_count": 1,
                "classified_fund_count": 1,
                "evaluated_fund_count": 1,
                "tenure_metric_fund_count": 1,
                "memo_count": 2,
                "latest_memo_date": date(2026, 8, 1),
                "latest_memo_date_source": "filename",
                "latest_memo_date_precision": "month",
                "category_keys": ["fixed_income", "fixed_income"],
                "strategy_names": ["固收-综合债券"],
                "peer_groups": ["固收-中证全债参考"],
                "style_labels": ["价值", "价值"],
                "focus_industries": ["信用债", "利率债"],
                "representative_fund_code": "000001.OF",
                "representative_fund_name": "示例债券A",
                "representative_metric_window": "manager_tenure",
                "representative_metric_date": date(2026, 8, 10),
                "representative_annualized_return": Decimal("0.0825"),
                "representative_max_drawdown": Decimal("-0.0312"),
                "representative_sharpe_ratio": Decimal("1.42"),
                "representative_annualized_volatility": Decimal("0.052"),
                "latest_memo_id": "memo-1",
                "latest_memo_title": "示例经理固收交流纪要",
                "latest_memo_summary": "关注信用债票息与利率债久期机会。",
                "latest_memo_topics": ["信用债", "利率债"],
                "latest_memo_domains": ["fixed_income"],
            }],
        }


def main():
    result = FundManagerBrowserService(manager_repo=ManagerRepo()).browse(
        category="fixed_income",
        evidence="research_ready",
        page=1,
        page_size=20,
    )
    manager = result["managers"][0]
    assert result["interface_version"] == "fund_manager_browser_v2"
    assert result["evidence"] == "research_ready"
    assert result["product_scope"]["investment_decision"] == "excluded"
    assert result["product_scope"]["sales_rules"] == "excluded"
    assert manager["category_labels"] == ["固收"]
    assert manager["current_fund_count"] == 1
    assert manager["current_share_count"] == 2
    assert manager["memo_count"] == 2
    assert manager["style_labels"] == ["价值"]
    assert manager["focus_industries"] == ["信用债", "利率债"]
    assert manager["latest_memo_date"] == "2026-08-01"
    assert manager["latest_memo"]["title"] == "示例经理固收交流纪要"
    assert manager["latest_memo"]["report_date_precision"] == "month"
    assert manager["latest_memo"]["viewpoint_topics"] == ["信用债", "利率债"]
    assert result["methodology"]["style_labels"] == "只取经理画像和已确认的经理级纪要标签，不使用基金专属标签"
    assert manager["representative_fund"]["wind_code"] == "000001.OF"
    assert manager["representative_fund"]["quantitative_evidence"]["label"] == "经理任期"
    assert manager["representative_fund"]["quantitative_evidence"]["annualized_return"] == 0.0825
    print("fund manager browser service smoke passed")


if __name__ == "__main__":
    main()
