"""基金经理同类产品对比服务。"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, Iterable, List, Optional
from uuid import UUID

from services.fund_manager_research_service import FundManagerResearchService
from services.metric_factory import MetricFactory


class FundManagerComparisonService:
    """并排展示经理事实，并只在同类、同区间下高亮量化差异。"""

    INTERFACE_VERSION = "fund_manager_comparison_v2"
    MAX_MANAGERS = 4
    MIN_COMMON_OBSERVATIONS = 20
    MIN_COMMON_COVERAGE = 0.80
    METRIC_META = {
        "total_return": {"label": "共同区间收益", "direction": "higher"},
        "record_breaking_days_ratio": {"label": "创新高天数占比", "direction": "higher"},
        "annualized_return": {"label": "年化收益", "direction": "higher"},
        "max_drawdown": {"label": "最大回撤", "direction": "higher"},
        "annualized_volatility": {"label": "年化波动", "direction": "lower"},
        "downside_risk": {"label": "下行风险", "direction": "lower"},
        "sharpe_ratio": {"label": "Sharpe", "direction": "higher"},
        "sortino_ratio": {"label": "Sortino", "direction": "higher"},
    }

    def __init__(
        self,
        research_service: Optional[Any] = None,
        nav_repo: Optional[Any] = None,
        metric_factory: Optional[MetricFactory] = None,
    ):
        self.research_service = research_service or FundManagerResearchService()
        self._nav_repo = nav_repo
        self.metric_factory = metric_factory or MetricFactory()

    def build(
        self,
        manager_ids: Iterable[str],
        category: Optional[str] = None,
        product_codes: Optional[Iterable[str]] = None,
    ) -> Dict[str, Any]:
        normalized_ids = list(dict.fromkeys(
            str(manager_id or "").strip()
            for manager_id in manager_ids
            if str(manager_id or "").strip()
        ))
        if len(normalized_ids) < 2:
            raise ValueError("At least two managers are required")
        if len(normalized_ids) > self.MAX_MANAGERS:
            raise ValueError(f"At most {self.MAX_MANAGERS} managers can be compared")

        snapshots = [self.research_service.build(manager_id, research_limit=50) for manager_id in normalized_ids]
        manager_rows = [self._manager_row(snapshot) for snapshot in snapshots]
        categories = self._categories(manager_rows)
        if not categories:
            return self._safe({
                "interface_version": self.INTERFACE_VERSION,
                "status": "empty",
                "reason": "no_current_classified_products",
                "managers": manager_rows,
                "categories": [],
                "source": "local.postgres.manager_fund_tenures+fund_nav+research_reports",
            })

        requested_category = str(category or "").strip()
        category_by_key = {item["key"]: item for item in categories}
        if requested_category and requested_category not in category_by_key:
            raise ValueError(f"Category is not available for selected managers: {requested_category}")
        if requested_category and category_by_key[requested_category]["manager_count"] != len(manager_rows):
            raise ValueError(f"Category must be available for every selected manager: {requested_category}")

        common_categories = [item for item in categories if item["manager_count"] == len(manager_rows)]
        if not common_categories:
            for manager in manager_rows:
                manager["selected_category_products"] = []
                manager["selected_product"] = None
            return self._safe({
                "interface_version": self.INTERFACE_VERSION,
                "status": "no_common_category",
                "reason": "selected_managers_have_no_exact_common_category",
                "selected_category": None,
                "categories": categories,
                "managers": manager_rows,
                "common_period": {
                    "status": "no_common_category",
                    "observation_count": 0,
                    "metrics": {},
                    "leaders": {},
                    "highlight_eligible": False,
                    "highlight_reason": "no_exact_common_category",
                },
                "source": "local.postgres.manager_fund_tenures+fund_nav+research_reports",
                "simulation_used": False,
            })

        selected_category = requested_category or common_categories[0]["key"]
        requested_products = list(product_codes or [])
        selected_products: Dict[str, Dict[str, Any]] = {}
        for index, manager in enumerate(manager_rows):
            products = [item for item in manager["current_products"] if item.get("category") == selected_category]
            manager["selected_category_products"] = products
            requested_product = str(requested_products[index] or "").strip().upper() if index < len(requested_products) else ""
            selected = self._select_product(products, requested_product)
            if selected:
                selected_products[manager["id"]] = selected
                manager["selected_product"] = selected
            else:
                manager["selected_product"] = None

        common_period = self._common_period(manager_rows, selected_products)
        comparison_summary = self._comparison_summary(manager_rows, common_period)
        return self._safe({
            "interface_version": self.INTERFACE_VERSION,
            "status": "available",
            "selected_category": selected_category,
            "categories": categories,
            "managers": manager_rows,
            "common_period": common_period,
            "comparison_summary": comparison_summary,
            "comparison_gate": {
                "category_status": "exact_common_category",
                "selected_category": selected_category,
                "selected_manager_count": len(manager_rows),
                "selected_product_count": len(selected_products),
                "common_period_status": common_period.get("status"),
                "highlight_eligible": bool(common_period.get("highlight_eligible")),
            },
            "methodology": {
                "basic_facts": "经理基本信息只并排展示，不生成跨类别经理总分",
                "product_tenure": "产品表保留每只基金自己的真实任职区间",
                "advantage_highlight": "仅在相同专业同类组、相同交易日期交集、每位经理一只真实净值产品时启用",
                "record_breaking_days_ratio": "创新高天数占比 = 所选区间内净值严格刷新此前最高值的日期数 / 区间净值观察数",
                "representative_product": "默认选择该类别中真实净值观察数最多的现任基金实体",
                "share_classes": "同一基金实体的不同份额合并展示，代码仍可追溯",
                "manager_assessment": "经理评价只汇总具体产品任期指标、同区间同类排名和纪要证据覆盖",
            },
            "source": "local.postgres.manager_fund_tenures+fund_nav+research_reports",
            "simulation_used": False,
            "product_scope": {
                "fund_manager_comparison": "core",
                "fund_classification": "required_gate",
                "fund_evaluation": "same_category_same_period_evidence",
                "research_memos": "core",
                "investment_decision": "excluded",
            },
        })

    def _manager_row(self, snapshot: Dict[str, Any]) -> Dict[str, Any]:
        manager = snapshot.get("manager") or {}
        profile = snapshot.get("profile") or {}
        memo_block = snapshot.get("research_memos") or {}
        assessment = snapshot.get("manager_assessment") or {}
        snapshot_evidence = snapshot.get("evidence") or {}
        all_tenures = [
            dict(item)
            for item in (snapshot.get("product_tenures") or {}).get("items") or []
            if isinstance(item, dict)
        ]
        all_products = [item for item in all_tenures if item.get("is_current")]
        reports = [dict(item) for item in memo_block.get("items") or [] if isinstance(item, dict)]
        start_dates = [
            self._date(item.get("start_date"))
            for item in all_tenures
            if self._date(item.get("start_date"))
        ]
        asset_values = [
            value
            for value in (self._number(item.get("total_asset")) for item in all_products)
            if value is not None and value >= 0
        ]
        profile_evidence = self._profile_evidence_coverage(profile)
        return {
            "id": str(manager.get("manager_id") or manager.get("id") or ""),
            "name": manager.get("name"),
            "company": manager.get("company"),
            "education": manager.get("education"),
            "work_years": manager.get("work_years"),
            "management_years": manager.get("management_years"),
            "management_start_date": min(start_dates) if start_dates else None,
            "current_fund_count": int((snapshot.get("product_tenures") or {}).get("current_product_count") or 0),
            "current_share_count": int((snapshot.get("product_tenures") or {}).get("current_share_count") or 0),
            "managed_asset": round(sum(asset_values), 4) if asset_values else None,
            "managed_asset_product_count": len(asset_values),
            "managed_asset_scope": "仅汇总本地已同步规模的在管基金实体，不代表基金公司官方披露口径",
            "memo_count": int(memo_block.get("count") or 0),
            "latest_memo_date": reports[0].get("report_date") if reports else None,
            "manager_assessment": dict(assessment) if isinstance(assessment, dict) else {},
            "representative_product": dict(assessment.get("representative_product") or {})
            if isinstance(assessment, dict) else {},
            "evidence": {
                "fund_metric_latest_date": snapshot_evidence.get("fund_metric_latest_date"),
                "research_latest_date": snapshot_evidence.get("research_latest_date"),
                "missing_items": snapshot_evidence.get("missing_items") or [],
                **profile_evidence,
            },
            "profile": {
                "status": profile.get("status"),
                "product_positioning": profile.get("product_positioning"),
                "investment_objective": profile.get("investment_objective"),
                "investment_method": profile.get("investment_method"),
                "holding_style": profile.get("holding_style"),
                "excess_return_source": profile.get("excess_return_source"),
                "core_philosophy": profile.get("core_philosophy"),
                "risk_philosophy": profile.get("risk_philosophy"),
                "focus_industries": profile.get("focus_industries") or [],
                "style_label": profile.get("style_label"),
                "memo_style_labels": profile.get("style_labels_from_memos") or [],
                "memo_classifications": profile.get("classifications_from_memos") or [],
            },
            "current_products": all_products,
            "product_tenures": all_tenures,
            "history": [{
                "id": report.get("id"),
                "date": report.get("report_date"),
                "title": report.get("title"),
                "summary": str(report.get("summary") or "")[:260],
                "source": report.get("source"),
                "tags": report.get("tags") or [],
            } for report in reports],
        }

    @staticmethod
    def _categories(managers: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        catalog: Dict[str, Dict[str, Any]] = {}
        for manager in managers:
            manager_categories = set()
            for product in manager.get("current_products") or []:
                category = str(product.get("category") or "").strip()
                if not category:
                    continue
                manager_categories.add(category)
                item = catalog.setdefault(category, {
                    "key": category,
                    "label": category,
                    "manager_count": 0,
                    "product_count": 0,
                })
                item["product_count"] += 1
            for category in manager_categories:
                catalog[category]["manager_count"] += 1
        return sorted(catalog.values(), key=lambda item: (
            item["manager_count"] >= 2,
            item["manager_count"],
            item["product_count"],
            item["label"],
        ), reverse=True)

    def _select_product(self, products: List[Dict[str, Any]], requested_code: str) -> Optional[Dict[str, Any]]:
        if requested_code:
            selected = next((
                item for item in products
                if requested_code == str(item.get("fund_code") or "").upper()
                or requested_code in [str(code or "").upper() for code in item.get("share_codes") or []]
            ), None)
            if not selected:
                raise ValueError(f"Product is not available in selected category: {requested_code}")
            return dict(selected)
        ranked: List[tuple[int, bool, int, bool, str, Dict[str, Any]]] = []
        for item in products:
            start_date = self._date(item.get("start_date"))
            end_date = self._date(item.get("end_date")) or date.today()
            nav_observations = 0
            if start_date and end_date > start_date:
                _, points = self._load_product_nav(item, start_date, end_date)
                nav_observations = len(points)
            ranked.append((
                nav_observations,
                item.get("metric_status") == "manager_product_tenure",
                int(item.get("metric_observations") or 0),
                bool(item.get("is_primary_share")),
                str(item.get("fund_code") or ""),
                item,
            ))
        if not ranked:
            return None
        selected = dict(max(ranked, key=lambda item: item[:-1])[-1])
        selected["comparison_nav_observations"] = max(ranked, key=lambda item: item[:-1])[0]
        return selected

    def _common_period(
        self,
        managers: List[Dict[str, Any]],
        selected_products: Dict[str, Dict[str, Any]],
    ) -> Dict[str, Any]:
        if len(selected_products) != len(managers):
            return {
                "status": "insufficient_managers_in_category",
                "observation_count": 0,
                "metrics": {},
                "leaders": {},
                "highlight_eligible": False,
                "highlight_reason": "not_every_manager_has_selected_product",
            }

        nav_by_manager: Dict[str, Dict[date, float]] = {}
        actual_codes: Dict[str, str] = {}
        for manager in managers:
            manager_id = manager["id"]
            product = selected_products.get(manager_id)
            if not product:
                continue
            start_date = self._date(product.get("metric_start_date") or product.get("start_date"))
            end_date = self._date(product.get("metric_as_of_date") or product.get("end_date")) or date.today()
            if not start_date or end_date <= start_date:
                continue
            actual_code, points = self._load_product_nav(product, start_date, end_date)
            if len(points) < self.MIN_COMMON_OBSERVATIONS:
                continue
            nav_by_manager[manager_id] = points
            actual_codes[manager_id] = actual_code

        if len(nav_by_manager) != len(managers):
            return {
                "status": "insufficient_local_nav",
                "observation_count": 0,
                "metrics": {},
                "leaders": {},
                "required_manager_count": len(managers),
                "available_manager_count": len(nav_by_manager),
                "missing_manager_ids": [
                    manager["id"] for manager in managers
                    if manager["id"] not in nav_by_manager
                ],
                "highlight_eligible": False,
                "highlight_reason": "not_every_selected_product_has_real_nav",
            }
        shared_dates = sorted(set.intersection(*(set(points) for points in nav_by_manager.values())))
        if len(shared_dates) < self.MIN_COMMON_OBSERVATIONS:
            return {
                "status": "insufficient_common_period",
                "observation_count": len(shared_dates),
                "metrics": {},
                "leaders": {},
                "highlight_eligible": False,
                "highlight_reason": "insufficient_same_trade_date_intersection",
            }

        calendar_days = max(1, (shared_dates[-1] - shared_dates[0]).days)
        expected_observations = max(2, round(calendar_days / 365.25 * 252) + 1)
        observation_coverage = min(1.0, len(shared_dates) / expected_observations)
        if observation_coverage < self.MIN_COMMON_COVERAGE:
            return {
                "status": "insufficient_common_coverage",
                "period_start": shared_dates[0],
                "period_end": shared_dates[-1],
                "observation_count": len(shared_dates),
                "expected_observations": expected_observations,
                "observation_coverage": round(observation_coverage, 4),
                "minimum_observation_coverage": self.MIN_COMMON_COVERAGE,
                "metrics": {},
                "leaders": {},
                "highlight_eligible": False,
                "highlight_reason": "common_trade_date_coverage_below_threshold",
            }

        metrics_by_manager: Dict[str, Dict[str, Any]] = {}
        for manager_id, points in nav_by_manager.items():
            series = [{"date": item_date, "nav": points[item_date]} for item_date in shared_dates]
            metrics: Dict[str, Any] = {}
            metrics.update(self.metric_factory.calculate_return_metrics(series))
            metrics.update(self.metric_factory.calculate_risk_metrics(series))
            metrics_by_manager[manager_id] = {
                **metrics,
                "fund_code": actual_codes[manager_id],
                "fund_name": selected_products[manager_id].get("fund_name"),
                "category": selected_products[manager_id].get("category"),
            }
        leaders = self._leaders(metrics_by_manager)
        return {
            "status": "available",
            "period_start": shared_dates[0],
            "period_end": shared_dates[-1],
            "observation_count": len(shared_dates),
            "expected_observations": expected_observations,
            "observation_coverage": round(observation_coverage, 4),
            "minimum_observation_coverage": self.MIN_COMMON_COVERAGE,
            "sample_status": "sufficient",
            "metrics": metrics_by_manager,
            "leaders": leaders,
            "metric_meta": self.METRIC_META,
            "highlight_eligible": True,
            "highlight_reason": "exact_category_same_trade_dates_real_nav",
            "source": "local.postgres.fund_nav.same_trade_date_intersection",
        }

    def _comparison_summary(
        self,
        managers: List[Dict[str, Any]],
        common_period: Dict[str, Any],
    ) -> Dict[str, Any]:
        if common_period.get("status") != "available":
            return {
                "status": "unavailable",
                "headline": "共同区间证据不足，暂不下结论。",
                "points": [],
                "scope_note": "不使用跨类别数据或模拟数据补足结论。",
            }

        names = {manager["id"]: str(manager.get("name") or manager["id"]) for manager in managers}
        leaders = common_period.get("leaders") or {}

        def leader_names(metric_names: List[str]) -> List[str]:
            votes: Dict[str, int] = {}
            for metric_name in metric_names:
                for manager_id in leaders.get(metric_name) or []:
                    votes[manager_id] = votes.get(manager_id, 0) + 1
            if not votes:
                return []
            best = max(votes.values())
            return [manager_id for manager_id, count in votes.items() if count == best]

        def display(manager_ids: List[str]) -> str:
            return "、".join(names.get(manager_id, manager_id) for manager_id in manager_ids)

        return_leaders = list(leaders.get("total_return") or [])
        experience_leaders = list(leaders.get("record_breaking_days_ratio") or [])
        risk_leaders = leader_names(["max_drawdown", "annualized_volatility", "downside_risk"])
        adjusted_leaders = leader_names(["sharpe_ratio", "sortino_ratio"])

        if len(return_leaders) == 1 and return_leaders == risk_leaders:
            headline = f"{display(return_leaders)}的代表产品在本次共同区间同时取得更高收益和更好的风险控制。"
        elif return_leaders and risk_leaders:
            headline = f"{display(return_leaders)}的代表产品收益更高；{display(risk_leaders)}的代表产品风险控制更稳。"
        else:
            headline = "本次共同区间各项指标各有侧重。"

        point_specs = [
            ("收益表现", return_leaders, "共同区间收益更高"),
            ("持有体验", experience_leaders, "创新高天数占比更高"),
            ("风险控制", risk_leaders, "在回撤、波动和下行风险三项中领先更多"),
            ("风险调整后收益", adjusted_leaders, "在 Sharpe 与 Sortino 两项中领先更多"),
        ]
        return {
            "status": "available",
            "headline": headline,
            "points": [
                {
                    "dimension": dimension,
                    "leader_manager_ids": manager_ids,
                    "statement": f"{display(manager_ids)}：{statement}。",
                }
                for dimension, manager_ids, statement in point_specs
                if manager_ids
            ],
            "scope_note": "结论只针对所选同类代表产品和共同交易日期，不等同于经理综合排名，也不构成投资建议。",
        }

    @staticmethod
    def _profile_evidence_coverage(profile: Dict[str, Any]) -> Dict[str, int]:
        evidence = profile.get("evidence") if isinstance(profile.get("evidence"), dict) else {}
        sections = [
            evidence.get("fields") if isinstance(evidence.get("fields"), dict) else {},
            evidence.get("framework") if isinstance(evidence.get("framework"), dict) else {},
        ]
        field_count = 0
        item_count = 0
        report_ids = set()
        for section in sections:
            for items in section.values():
                if not isinstance(items, list) or not items:
                    continue
                field_count += 1
                item_count += len(items)
                for item in items:
                    if not isinstance(item, dict):
                        continue
                    report_id = str(item.get("report_id") or item.get("source_report_id") or "").strip()
                    if report_id:
                        report_ids.add(report_id)
        return {
            "profile_evidence_field_count": field_count,
            "profile_evidence_item_count": item_count,
            "profile_evidence_report_count": len(report_ids),
        }

    def _load_product_nav(
        self,
        product: Dict[str, Any],
        start_date: date,
        end_date: date,
    ) -> tuple[str, Dict[date, float]]:
        candidates = list(dict.fromkeys([
            str(product.get("fund_code") or "").strip().upper(),
            *[str(code or "").strip().upper() for code in product.get("share_codes") or []],
        ]))
        fallback: tuple[str, Dict[date, float]] = (candidates[0] if candidates else "", {})
        for code in candidates:
            rows = self.nav_repo.get_nav_series(code, start_date.isoformat(), end_date.isoformat())
            points = self._points(rows)
            if points and not fallback[1]:
                fallback = (code, points)
            if len(points) >= self.MIN_COMMON_OBSERVATIONS:
                return code, points
        return fallback

    @staticmethod
    def _points(rows: List[Dict[str, Any]]) -> Dict[date, float]:
        points: Dict[date, float] = {}
        for row in rows:
            item_date = FundManagerComparisonService._date(row.get("date") or row.get("trade_date"))
            value = FundManagerComparisonService._positive_number(
                row.get("accum_nav") or row.get("adj_nav") or row.get("nav") or row.get("unit_nav")
            )
            if item_date and value is not None:
                points[item_date] = value
        return points

    def _leaders(self, metrics_by_manager: Dict[str, Dict[str, Any]]) -> Dict[str, List[str]]:
        leaders: Dict[str, List[str]] = {}
        for metric_name, meta in self.METRIC_META.items():
            values = {
                manager_id: self._number(metrics.get(metric_name))
                for manager_id, metrics in metrics_by_manager.items()
            }
            values = {key: value for key, value in values.items() if value is not None}
            if len(values) < 2:
                continue
            best = min(values.values()) if meta["direction"] == "lower" else max(values.values())
            leaders[metric_name] = [
                manager_id for manager_id, value in values.items()
                if abs(value - best) <= 1e-12
            ]
        return leaders

    @staticmethod
    def _date(value: Any) -> Optional[date]:
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, date):
            return value
        try:
            return date.fromisoformat(str(value or "")[:10])
        except ValueError:
            return None

    @staticmethod
    def _positive_number(value: Any) -> Optional[float]:
        try:
            parsed = float(value)
        except (TypeError, ValueError):
            return None
        return parsed if parsed > 0 else None

    @staticmethod
    def _number(value: Any) -> Optional[float]:
        try:
            parsed = float(value)
        except (TypeError, ValueError):
            return None
        return parsed if parsed == parsed else None

    @classmethod
    def _safe(cls, value: Any) -> Any:
        if isinstance(value, dict):
            return {str(key): cls._safe(item) for key, item in value.items()}
        if isinstance(value, (list, tuple)):
            return [cls._safe(item) for item in value]
        if isinstance(value, (date, datetime, UUID, Decimal)):
            return str(value)
        return value

    @property
    def nav_repo(self):
        if self._nav_repo is None:
            from repositories import get_nav_repo
            self._nav_repo = get_nav_repo()
        return self._nav_repo
