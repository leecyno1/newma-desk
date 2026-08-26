"""面向选基场景的基金公司浏览服务。"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Dict, List, Optional

from services.fund_browser_service import FundBrowserService


class FundCompanyService:
    EVALUATION_MIN_AGE_DAYS = 430

    def __init__(self, repo: Any = None, manager_repo: Any = None, browser_service: Any = None):
        if repo is None:
            from repositories.fund_company_repo import FundCompanyRepo

            repo = FundCompanyRepo()
        if manager_repo is None:
            from repositories import get_manager_repo

            manager_repo = get_manager_repo()
        self.repo = repo
        self.manager_repo = manager_repo
        self.browser_service = browser_service or FundBrowserService()

    def list_companies(
        self,
        keyword: Optional[str] = None,
        page: int = 1,
        page_size: int = 30,
        sort_by: str = "fund_count",
    ) -> Dict[str, Any]:
        rows, total = self.repo.list_companies(
            keyword=keyword,
            page=page,
            page_size=page_size,
            sort_by=sort_by,
        )
        return {
            "companies": [self._company_summary(row) for row in rows],
            "summary": self.repo.get_market_summary(),
            "total": total,
            "page": page,
            "page_size": page_size,
            "source": "local.postgres.tushare.fund_basic+metric_snapshots",
            "methodology": {
                "fund_count": "按本地基金份额代码计数，不等同于合并份额后的基金产品数",
                "synced_total_asset": "仅汇总已取得规模数据的基金份额，并同时披露样本数",
                "category_coverage": "评价覆盖按标准同类组计数，不用跨类别收益给基金公司排名",
            },
        }

    def get_company(self, company: str) -> Dict[str, Any]:
        summary = self.repo.get_company(company)
        if not summary:
            raise ValueError("基金公司不存在或本地基础数据未同步")

        category_breakdown = self.repo.get_category_breakdown(company)
        representative_funds = self._representative_funds(company)
        representative_map = {
            str(fund.get("peer_group") or ""): fund
            for fund in representative_funds
            if fund.get("peer_group")
        }
        for category in category_breakdown:
            category["representative_fund"] = representative_map.get(
                str(category.get("peer_group_name") or "")
            )

        return {
            "company": self._company_summary(summary),
            "category_breakdown": category_breakdown,
            "category_window_performance": self.repo.get_category_window_performance(company),
            "representative_funds": representative_funds,
            "funds": representative_funds,
            "managers": self.repo.get_company_managers(company),
            "source": "local.postgres.tushare.fund_basic+fund_nav+metric_snapshots",
            "methodology": {
                "scope": "基金评价与基金选择辅助，不构成公司评级或投资建议",
                "fund_count": "按份额代码计数",
                "category_breakdown": "按标准化同类组统计基金实体，不把 A/C 份额当作不同产品",
                "performance": "多周期业绩、回撤和 Sharpe 只按标准同类组聚合，不输出跨类别公司收益",
                "fund_order": "每个专业类别优先展示证据完整且同类专业评分较高的基金",
            },
        }

    def _representative_funds(self, company: str) -> List[Dict[str, Any]]:
        candidates = self.repo.get_company_representative_funds(company, per_category=3, limit=100)
        if not candidates:
            return []

        candidate_map = {
            str(candidate.get("wind_code") or ""): candidate
            for candidate in candidates
            if candidate.get("wind_code")
        }
        enriched = self.browser_service.enrich_rows(candidates)
        by_category: Dict[str, List[Dict[str, Any]]] = {}
        for fund in enriched:
            candidate = candidate_map.get(str(fund.get("wind_code") or "")) or {}
            fund.update({
                "category_fund_count": candidate.get("category_fund_count"),
                "metric_evidence_count": candidate.get("metric_evidence_count"),
                "metric_as_of": candidate.get("metric_as_of"),
                "annualized_return_1y": candidate.get("annualized_return_1y"),
                "max_drawdown_1y": candidate.get("max_drawdown_1y"),
                "sharpe_1y": candidate.get("sharpe_1y"),
            })
            profile = fund.get("research_profile") or {}
            scoring = fund.get("professional_scoring") or {}
            peer_group = str(profile.get("peer_group") or "").strip()
            if not peer_group:
                continue
            score = self._number(scoring.get("overall_score"))
            evidence_count = int(fund.get("metric_evidence_count") or 0)
            evaluation_status = self._evaluation_status(fund, score)
            fund["peer_group"] = peer_group
            fund["professional_score"] = score
            fund["evaluation_status"] = evaluation_status
            fund["selection_reason"] = self._selection_reason(
                fund,
                score,
                evidence_count,
                evaluation_status,
            )
            by_category.setdefault(peer_group, []).append(fund)

        selected = []
        for peer_group, funds in by_category.items():
            funds.sort(key=self._representative_sort_key)
            selected.append(funds[0])
        selected.sort(key=lambda fund: (
            -int(fund.get("category_fund_count") or 0),
            str(fund.get("peer_group") or ""),
        ))
        return selected

    @classmethod
    def _representative_sort_key(cls, fund: Dict[str, Any]):
        score = cls._number(fund.get("professional_score"))
        return (
            score is None,
            -(score or 0),
            -int(fund.get("metric_evidence_count") or 0),
            -(cls._number(fund.get("total_asset")) or 0),
            str(fund.get("wind_code") or ""),
        )

    @classmethod
    def _selection_reason(
        cls,
        fund: Dict[str, Any],
        score: Optional[float],
        evidence_count: int,
        evaluation_status: str,
    ) -> str:
        if evaluation_status == "observation_period":
            return "成立时间不足 430 天，先观察净值与持仓表现，暂不做一年期专业评分"
        if score is not None:
            return f"同类专业评分 {score:.1f}，且一年量化证据较完整"
        if evidence_count >= 2:
            return "已具备一年收益、回撤或 Sharpe 指标，等待补齐类别评价证据"
        if cls._number(fund.get("total_asset")) is not None:
            return "当前作为该类别的规模样本，专业评分待补数"
        return "当前作为该类别的数据入口，专业评价证据待补齐"

    @classmethod
    def _evaluation_status(cls, fund: Dict[str, Any], score: Optional[float]) -> str:
        if score is not None:
            return "evaluated"
        establishment_date = cls._date(fund.get("establishment_date"))
        if establishment_date and (date.today() - establishment_date).days < cls.EVALUATION_MIN_AGE_DAYS:
            return "observation_period"
        return "pending"

    @staticmethod
    def _date(value: Any) -> Optional[date]:
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, date):
            return value
        text = str(value or "").strip()
        if not text:
            return None
        try:
            return date.fromisoformat(text[:10])
        except ValueError:
            return None

    @classmethod
    def _company_summary(cls, row: Dict[str, Any]) -> Dict[str, Any]:
        return {
            **row,
            "short_name": cls.short_name(str(row.get("company") or "")),
            "asset_coverage": cls._ratio(row.get("asset_sample_count"), row.get("fund_count")),
            "classification_coverage": cls._ratio(row.get("classified_count"), row.get("fund_count")),
            "metric_coverage": cls._ratio(row.get("metric_ready_count"), row.get("fund_count")),
        }

    @staticmethod
    def short_name(company: str) -> str:
        name = company.strip()
        for suffix in ("基金管理股份有限公司", "基金管理有限公司", "资产管理有限公司", "管理有限公司"):
            if name.endswith(suffix):
                return name[: -len(suffix)] or name
        return name

    @staticmethod
    def _ratio(numerator: Any, denominator: Any) -> float:
        try:
            denominator_value = float(denominator or 0)
            if denominator_value <= 0:
                return 0.0
            return round(float(numerator or 0) / denominator_value, 4)
        except (TypeError, ValueError):
            return 0.0

    @staticmethod
    def _number(value: Any) -> Optional[float]:
        try:
            if value is None or value == "":
                return None
            return float(value)
        except (TypeError, ValueError):
            return None
