"""普通用户选基首页 Module。"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, Optional
from urllib.parse import quote
from uuid import UUID


class FundHomeService:
    """聚合首页需要的真实摘要，不复制下游基金研究逻辑。"""

    INTERFACE_VERSION = "fund_selection_home_v1"

    def __init__(
        self,
        fund_repo: Optional[Any] = None,
        manager_browser: Optional[Any] = None,
        recommendation_service: Optional[Any] = None,
        report_repo: Optional[Any] = None,
        watchlist_service: Optional[Any] = None,
    ):
        self._fund_repo = fund_repo
        self._manager_browser = manager_browser
        self._recommendation_service = recommendation_service
        self._report_repo = report_repo
        self._watchlist_service = watchlist_service

    def build(self) -> Dict[str, Any]:
        with ThreadPoolExecutor(max_workers=5) as executor:
            fund_future = executor.submit(self.fund_repo.browse_funds, page=1, page_size=1)
            manager_future = executor.submit(self.manager_browser.browse, page=1, page_size=4)
            coverage_future = executor.submit(self.recommendation_service.build_home_coverage_report, limit=100)
            report_future = executor.submit(self.report_repo.list_reports, page=1, page_size=5)
            watchlist_future = executor.submit(self.watchlist_service.list_pools)
            _, fund_count = fund_future.result()
            manager_payload = manager_future.result()
            coverage = coverage_future.result()
            report_payload = report_future.result()
            watchlists = watchlist_future.result()

        coverage_summary = coverage.get("summary") or {}
        ready_groups = [
            group for group in coverage.get("groups", [])
            if group.get("status") == "ready" and int(group.get("recommendation_ready_count") or 0) > 0
        ]
        ready_groups.sort(key=lambda group: (
            -int(group.get("recommendation_ready_count") or 0),
            -int(group.get("classified_count") or 0),
            str(group.get("name") or ""),
        ))

        return self._json_safe({
            "interface_version": self.INTERFACE_VERSION,
            "summary": {
                "fund_share_count": int(fund_count or 0),
                "classified_fund_count": int(coverage_summary.get("database_fund_count") or 0),
                "recommendation_ready_category_count": int(coverage_summary.get("ready_category_count") or 0),
                "recommendation_ready_fund_count": int(coverage_summary.get("recommendation_ready_count") or 0),
                "fund_manager_count": int(manager_payload.get("total") or 0),
                "research_memo_count": int(report_payload.get("total") or 0),
                "watchlist_group_count": len(watchlists),
                "watchlist_fund_count": sum(int(item.get("member_count") or 0) for item in watchlists),
            },
            "featured_peer_groups": [self._peer_group(group) for group in ready_groups[:6]],
            "featured_managers": manager_payload.get("managers", [])[:4],
            "latest_research_memos": [
                self._memo(report) for report in report_payload.get("reports", [])[:5]
            ],
            "watchlist": {
                "groups": [
                    {
                        "id": item.get("id"),
                        "name": item.get("name"),
                        "fund_count": int(item.get("member_count") or 0),
                    }
                    for item in watchlists
                ],
            },
            "source": "local.postgres.funds+classification+metrics+managers+research_reports+watchlists",
            "methodology": {
                "peer_groups": "只展示已具备分类内评价证据的标准同类组",
                "managers": "按专业分类、任期指标和纪要覆盖展示，不按跨类别收益排名",
                "research": "只展示已进入本地调研纪要库的资料",
            },
            "product_scope": {
                "fund_browser": "core",
                "fund_manager_browser": "core",
                "research_library": "core",
                "fund_recommendation": "core",
                "ai_analysis": "on_demand",
                "investment_decision": "excluded",
                "market_timing": "excluded",
                "sales_rules": "excluded",
            },
        })

    @staticmethod
    def _peer_group(group: Dict[str, Any]) -> Dict[str, Any]:
        name = str(group.get("name") or group.get("key") or "").strip()
        return {
            "key": group.get("key") or name,
            "name": name,
            "classified_fund_count": int(group.get("database_fund_count") or 0),
            "recommendation_ready_fund_count": int(group.get("recommendation_ready_count") or 0),
            "style_ready_fund_count": int(group.get("style_ready_count") or 0),
            "href": f"/recommendations?category={quote(name)}",
        }

    @staticmethod
    def _memo(report: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "id": report.get("id"),
            "title": report.get("title"),
            "manager_name": report.get("manager_name"),
            "report_date": report.get("report_date"),
            "report_date_source": report.get("report_date_source"),
            "report_date_precision": report.get("report_date_precision"),
            "source": report.get("source"),
            "summary": str(report.get("summary") or "")[:180],
            "tags": (report.get("tags") or [])[:4],
            "classifications": (report.get("classifications") or [])[:3],
            "style_labels": (report.get("style_labels") or [])[:3],
            "href": f"/research?search={quote(str(report.get('title') or report.get('manager_name') or ''))}",
        }

    @property
    def fund_repo(self):
        if self._fund_repo is None:
            from repositories import get_fund_repo

            self._fund_repo = get_fund_repo()
        return self._fund_repo

    @property
    def manager_browser(self):
        if self._manager_browser is None:
            from services.fund_manager_browser_service import FundManagerBrowserService

            self._manager_browser = FundManagerBrowserService()
        return self._manager_browser

    @property
    def recommendation_service(self):
        if self._recommendation_service is None:
            from services.fund_recommendation_service import FundRecommendationService

            self._recommendation_service = FundRecommendationService()
        return self._recommendation_service

    @property
    def report_repo(self):
        if self._report_repo is None:
            from repositories.local_research_folder_repo import PostgresLocalResearchFolderRepo

            self._report_repo = PostgresLocalResearchFolderRepo()
        return self._report_repo

    @property
    def watchlist_service(self):
        if self._watchlist_service is None:
            from services.fund_watchlist_service import FundWatchlistService

            self._watchlist_service = FundWatchlistService()
        return self._watchlist_service

    @classmethod
    def _json_safe(cls, value: Any) -> Any:
        if isinstance(value, dict):
            return {str(key): cls._json_safe(item) for key, item in value.items()}
        if isinstance(value, (list, tuple)):
            return [cls._json_safe(item) for item in value]
        if isinstance(value, (datetime, date)):
            return value.isoformat()
        if isinstance(value, UUID):
            return str(value)
        if isinstance(value, Decimal):
            return float(value)
        return value
