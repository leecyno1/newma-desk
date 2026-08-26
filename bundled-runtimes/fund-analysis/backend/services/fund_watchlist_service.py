"""普通用户自选基金服务。"""
from typing import Any, Dict, List, Optional

from services.fund_browser_service import FundBrowserService


class FundWatchlistService:
    def __init__(self):
        from repositories import get_fund_pool_repo

        self.repo = get_fund_pool_repo()

    def list_pools(self) -> List[Dict[str, Any]]:
        self.repo.ensure_default_watchlist()
        return self.repo.list_watchlists()

    def list_members(self, pool_id: str, status: Optional[str] = None) -> List[Dict[str, Any]]:
        members = self.repo.list_members(pool_id=pool_id, status=status)
        rows = [self._fund_row(member) for member in members if member.get("fund_wind_code")]
        funds = FundBrowserService().enrich_rows(rows)
        fund_map = {str(fund.get("wind_code") or ""): fund for fund in funds}
        return [
            {
                **(fund_map.get(str(member.get("fund_wind_code") or "")) or {}),
                "member_id": member.get("id"),
                "pool_id": member.get("pool_id"),
                "status": member.get("status"),
                "reason": member.get("reason"),
                "latest_conclusion": member.get("latest_conclusion"),
                "risk_notes": member.get("risk_notes"),
                "next_review_date": member.get("next_review_date"),
                "member_created_at": member.get("created_at"),
                "member_updated_at": member.get("updated_at"),
            }
            for member in members
        ]

    @staticmethod
    def _fund_row(member: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "id": member.get("fund_database_id"),
            "wind_code": member.get("fund_wind_code"),
            "name": member.get("fund_name"),
            "type": member.get("fund_type"),
            "manager_ids": member.get("fund_manager_ids") or [],
            "nav": member.get("fund_nav"),
            "nav_date": member.get("fund_nav_date"),
            "total_asset": member.get("fund_total_asset"),
            "establishment_date": member.get("fund_establishment_date"),
            "performance_data": member.get("fund_performance_data") or {},
            "risk_metrics": member.get("fund_risk_metrics") or {},
            "raw_data": member.get("fund_raw_data") or {},
            "updated_at": member.get("fund_updated_at"),
        }
