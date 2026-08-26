"""基金经理浏览器 Module。"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, Optional


class FundManagerBrowserService:
    """用一个窄 Interface 输出经理浏览和研究覆盖事实。"""

    INTERFACE_VERSION = "fund_manager_browser_v2"
    CATEGORIES = (
        ("all", "全部"),
        ("fixed_income", "固收"),
        ("fixed_income_plus", "固收+"),
        ("active_equity", "主动权益"),
        ("passive_equity", "被动权益"),
        ("qdii", "QDII"),
        ("fof", "FOF"),
        ("money_market", "货币"),
        ("other", "其他"),
    )
    CATEGORY_LABELS = dict(CATEGORIES)
    EVIDENCE_FILTERS = (
        ("all", "全部经理"),
        ("with_memo", "有调研纪要"),
        ("with_metrics", "有量化数据"),
        ("research_ready", "调研+量化"),
    )
    EVIDENCE_LABELS = dict(EVIDENCE_FILTERS)

    def __init__(self, manager_repo: Optional[Any] = None):
        self._manager_repo = manager_repo

    def browse(
        self,
        keyword: Optional[str] = None,
        category: str = "all",
        evidence: str = "all",
        page: int = 1,
        page_size: int = 24,
    ) -> Dict[str, Any]:
        normalized_category = str(category or "all").strip().lower()
        if normalized_category not in self.CATEGORY_LABELS:
            normalized_category = "all"
        normalized_evidence = str(evidence or "all").strip().lower()
        if normalized_evidence not in self.EVIDENCE_LABELS:
            normalized_evidence = "all"
        normalized_page = max(1, int(page))
        normalized_page_size = max(1, min(int(page_size), 100))
        result = self.manager_repo.browse_managers(
            keyword=keyword,
            category=normalized_category,
            evidence=normalized_evidence,
            page=normalized_page,
            page_size=normalized_page_size,
        )
        managers = [self._project_manager(row) for row in result.get("managers", [])]
        return self._json_safe({
            "interface_version": self.INTERFACE_VERSION,
            "managers": managers,
            "total": int(result.get("total") or 0),
            "page": normalized_page,
            "page_size": normalized_page_size,
            "keyword": str(keyword or "").strip(),
            "category": normalized_category,
            "evidence": normalized_evidence,
            "categories": [
                {"key": key, "label": label}
                for key, label in self.CATEGORIES
            ],
            "evidence_filters": [
                {"key": key, "label": label}
                for key, label in self.EVIDENCE_FILTERS
            ],
            "source": "local.postgres.managers+standardized_fund_classification+metric_snapshots+research_reports",
            "methodology": {
                "manager_scope": "只展示已关联当前管理基金的经理",
                "fund_count": "按基金实体合并不同份额；份额数另行保留",
                "category": "来自标准基金分类目录，不根据基金或经理名称猜测",
                "style_labels": "只取经理画像和已确认的经理级纪要标签，不使用基金专属标签",
                "quantitative_summary": "优先使用代表基金经理任期指标，缺失时退回近1年；不等同经理全部产品业绩",
                "order": "按纪要、专业分类和量化证据覆盖排序，不按跨类别收益混排",
            },
            "product_scope": {
                "fund_manager_browser": "core",
                "fund_classification": "core",
                "fund_evaluation": "evidence_coverage",
                "research_memos": "core",
                "investment_decision": "excluded",
                "sales_rules": "excluded",
            },
        })

    def _project_manager(self, row: Dict[str, Any]) -> Dict[str, Any]:
        category_keys = self._unique_strings(row.get("category_keys"))
        style_labels = self._unique_strings(row.get("style_labels"))
        current_codes = self._unique_strings(row.get("current_fund_codes"))
        metric_window = str(row.get("representative_metric_window") or "").strip()
        quantitative_evidence = None
        if metric_window:
            quantitative_evidence = {
                "window": metric_window,
                "label": "经理任期" if metric_window == "manager_tenure" else "近1年",
                "as_of_date": row.get("representative_metric_date"),
                "annualized_return": self._number(row.get("representative_annualized_return")),
                "max_drawdown": self._number(row.get("representative_max_drawdown")),
                "sharpe_ratio": self._number(row.get("representative_sharpe_ratio")),
                "annualized_volatility": self._number(row.get("representative_annualized_volatility")),
            }
        latest_memo_id = str(row.get("latest_memo_id") or "").strip()
        latest_memo = None
        if latest_memo_id:
            latest_memo = {
                "id": latest_memo_id,
                "title": row.get("latest_memo_title"),
                "summary": str(row.get("latest_memo_summary") or "")[:260],
                "report_date": row.get("latest_memo_date"),
                "report_date_source": row.get("latest_memo_date_source"),
                "report_date_precision": row.get("latest_memo_date_precision"),
                "viewpoint_topics": self._unique_strings(row.get("latest_memo_topics")),
                "research_domains": self._unique_strings(row.get("latest_memo_domains")),
            }
        return {
            "id": row.get("id"),
            "name": row.get("name"),
            "company": row.get("company"),
            "education": row.get("education"),
            "work_years": self._number(row.get("work_years")),
            "management_years": self._number(row.get("management_years")),
            "current_fund_codes": current_codes,
            "current_share_count": len(current_codes),
            "current_fund_count": int(row.get("current_fund_count") or 0),
            "classified_fund_count": int(row.get("classified_fund_count") or 0),
            "metric_fund_count": int(row.get("evaluated_fund_count") or 0),
            "tenure_metric_fund_count": int(row.get("tenure_metric_fund_count") or 0),
            "memo_count": int(row.get("memo_count") or 0),
            "latest_memo_date": row.get("latest_memo_date"),
            "latest_metric_date": row.get("latest_metric_date"),
            "category_keys": category_keys,
            "category_labels": [self.CATEGORY_LABELS.get(key, "其他") for key in category_keys],
            "strategy_names": self._unique_strings(row.get("strategy_names")),
            "peer_groups": self._unique_strings(row.get("peer_groups")),
            "style_labels": style_labels,
            "focus_industries": self._unique_strings(row.get("focus_industries")),
            "representative_fund": {
                "wind_code": row.get("representative_fund_code"),
                "name": row.get("representative_fund_name"),
                "quantitative_evidence": quantitative_evidence,
            } if row.get("representative_fund_code") else None,
            "latest_memo": latest_memo,
            "updated_at": row.get("updated_at"),
        }

    @staticmethod
    def _unique_strings(value: Any) -> list[str]:
        if not isinstance(value, (list, tuple)):
            return []
        return list(dict.fromkeys(
            str(item).strip()
            for item in value
            if str(item or "").strip()
        ))

    @staticmethod
    def _number(value: Any) -> Optional[float]:
        if value in (None, ""):
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    @classmethod
    def _json_safe(cls, value: Any) -> Any:
        if isinstance(value, dict):
            return {str(key): cls._json_safe(item) for key, item in value.items()}
        if isinstance(value, (list, tuple)):
            return [cls._json_safe(item) for item in value]
        if isinstance(value, (datetime, date)):
            return value.isoformat()
        if isinstance(value, Decimal):
            return float(value)
        return value

    @property
    def manager_repo(self):
        if self._manager_repo is None:
            from repositories import get_manager_repo

            self._manager_repo = get_manager_repo()
        return self._manager_repo
