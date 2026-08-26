"""统一基金经理研究快照 Module。"""

from __future__ import annotations

import re
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, Iterable, List, Optional
from uuid import UUID

from services.fund_browser_service import FundBrowserService
from services.fund_product_identity import fund_product_identity
from services.fund_research_snapshot_service import FundResearchSnapshotService


class FundManagerResearchService:
    """一次输出经理详情页和 AI 分析共用的研究事实。"""

    INTERFACE_VERSION = "fund_manager_research_snapshot_v1"

    def __init__(
        self,
        manager_repo: Optional[Any] = None,
        fund_repo: Optional[Any] = None,
        report_repo: Optional[Any] = None,
        metric_repo: Optional[Any] = None,
        fund_browser: Optional[FundBrowserService] = None,
        tenure_peer_ranking_service: Optional[Any] = None,
    ):
        self._manager_repo = manager_repo
        self._fund_repo = fund_repo
        self._report_repo = report_repo
        self._metric_repo = metric_repo
        self.fund_browser = fund_browser or FundBrowserService()
        self._tenure_peer_ranking_service = tenure_peer_ranking_service

    def build(self, manager_id: str, research_limit: int = 12) -> Dict[str, Any]:
        requested_id = str(manager_id or "").strip()
        manager = self.manager_repo.get_manager(requested_id)
        if not manager:
            raise ValueError(f"Manager not found: {requested_id}")

        resolved_id = str(manager.get("wind_code") or requested_id)
        manager_name = str(manager.get("name") or resolved_id.split("|")[0]).strip()
        fund_codes = list(dict.fromkeys(
            str(code).strip().upper()
            for code in (manager.get("current_funds") or [])
            if str(code or "").strip()
        ))
        share_funds = self._load_current_funds(fund_codes)
        product_tenures = self._load_product_tenures(resolved_id, share_funds)
        funds = self._canonical_current_funds(share_funds, product_tenures)
        manager = {
            **manager,
            "current_share_codes": fund_codes,
            "current_funds": [str(fund.get("wind_code") or "") for fund in funds if fund.get("wind_code")],
        }
        if not str(manager.get("company") or "").strip():
            manager = {**manager, "company": self._company_from_funds(funds)}
        reports = self._load_research_reports(resolved_id, research_limit)
        profile = self._profile(manager, reports)
        manager_assessment = self._manager_assessment(product_tenures, reports)
        portfolio_summary = self._portfolio_summary(product_tenures, funds)
        missing_items = []
        if not funds:
            missing_items.append("没有找到已关联到该经理的当前基金")
        if not reports:
            missing_items.append("尚未关联调研纪要")
        if profile.get("status") == "empty":
            missing_items.append("经理画像待从纪要确认")
        if manager_assessment.get("tenure_evaluated_product_count") == 0:
            missing_items.append("暂无可核验的单产品经理任期评价")
        elif manager_assessment.get("peer_ranked_product_count") == 0:
            missing_items.append("暂无达到样本门槛的同区间同类任期排名")
        if portfolio_summary.get("managed_asset_product_count", 0) < portfolio_summary.get("current_product_count", 0):
            missing_items.append(
                f"在管规模仅覆盖 {portfolio_summary.get('managed_asset_product_count', 0)} / "
                f"{portfolio_summary.get('current_product_count', 0)} 个产品"
            )

        return self._json_safe({
            "interface_version": self.INTERFACE_VERSION,
            "status": "available",
            "manager": self._project_manager(manager),
            "coverage": self._coverage(funds),
            "portfolio_summary": portfolio_summary,
            "current_funds": funds,
            "product_tenures": product_tenures,
            "manager_assessment": manager_assessment,
            "profile": profile,
            "research_memos": {
                "status": "available" if reports else "empty",
                "count": len(reports),
                "items": reports,
            },
            "historical_viewpoints": self._historical_viewpoints(reports, profile),
            "evidence": {
                "manager_updated_at": manager.get("updated_at"),
                "fund_metric_latest_date": self._latest_metric_date(funds),
                "research_latest_date": reports[0].get("report_date") if reports else None,
                "missing_items": missing_items,
            },
            "product_scope": {
                "fund_manager_research": "core",
                "fund_classification": "core",
                "fund_evaluation": "core",
                "performance_attribution": "fund_level_on_demand_evidence",
                "investment_decision": "excluded",
            },
        })

    def _load_current_funds(self, fund_codes: List[str]) -> List[Dict[str, Any]]:
        rows = [self.fund_repo.get_fund(code) for code in fund_codes]
        rows = [row for row in rows if row]
        enriched = self.fund_browser.enrich_rows(rows)
        return [self._project_fund(row) for row in enriched]

    def _load_product_tenures(
        self,
        manager_id: str,
        current_funds: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        rows = self.manager_repo.list_fund_tenures(manager_id) if hasattr(self.manager_repo, "list_fund_tenures") else []
        if not rows:
            rows = [{
                "fund_code": fund.get("wind_code"),
                "fund_name": fund.get("name"),
                "type": fund.get("type"),
                "total_asset": fund.get("total_asset"),
                "start_date": None,
                "end_date": None,
                "is_current": True,
                "peer_group_name": fund.get("peer_group"),
                "strategy_name": None,
                "manager_tenure": (fund.get("rolling_metrics") or {}).get("manager_tenure") or {},
                "one_year": (fund.get("rolling_metrics") or {}).get("1y") or {},
                "source": "managers.current_funds",
            } for fund in current_funds]

        projected = [self._project_tenure(row) for row in rows]
        items = self._canonical_tenures(projected)
        for item in items:
            if item.get("metric_status") == "manager_product_tenure":
                item["peer_ranking"] = self.tenure_peer_ranking_service.rank(item)
            else:
                item["peer_ranking"] = {
                    "status": "manager_product_tenure_unavailable",
                    "target_code": item.get("fund_code"),
                    "metrics": {},
                    "methodology_version": "manager_tenure_same_period_peer_rank_v3",
                }
        entity_keys = set()
        current_entity_keys = set()
        historical_entity_keys = set()
        for item in items:
            entity_key = str(item.get("entity_id") or item.get("fund_code") or "")
            if not entity_key:
                continue
            entity_keys.add(entity_key)
            (current_entity_keys if item.get("is_current") else historical_entity_keys).add(entity_key)
        return {
            "status": "available" if items else "empty",
            "share_count": len(projected),
            "product_count": len(entity_keys),
            "current_share_count": sum(bool(item.get("is_current")) for item in projected),
            "current_product_count": len(current_entity_keys),
            "historical_share_count": sum(not bool(item.get("is_current")) for item in projected),
            "historical_product_count": len(historical_entity_keys),
            "items": items,
            "source": "postgres.manager_fund_tenures",
        }

    @staticmethod
    def _canonical_current_funds(
        share_funds: List[Dict[str, Any]],
        product_tenures: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        """经理详情按基金实体展示，保留同一产品的全部份额代码。"""
        funds_by_code = {
            str(fund.get("wind_code") or "").strip().upper(): fund
            for fund in share_funds
            if str(fund.get("wind_code") or "").strip()
        }
        current_tenures = [
            item for item in (product_tenures.get("items") or [])
            if isinstance(item, dict) and item.get("is_current")
        ]
        if not current_tenures:
            return share_funds

        products: List[Dict[str, Any]] = []
        covered_codes = set()
        for tenure in current_tenures:
            share_codes = list(dict.fromkeys(
                str(code or "").strip().upper()
                for code in (tenure.get("share_codes") or [tenure.get("fund_code")])
                if str(code or "").strip()
            ))
            covered_codes.update(share_codes)
            representative_code = str(tenure.get("fund_code") or "").strip().upper()
            base = funds_by_code.get(representative_code)
            if not base:
                base = next((funds_by_code[code] for code in share_codes if code in funds_by_code), None)
            if not base:
                base = {
                    "wind_code": representative_code,
                    "name": tenure.get("fund_name") or representative_code,
                    "type": tenure.get("type"),
                    "peer_group": tenure.get("category"),
                    "total_asset": tenure.get("total_asset"),
                    "rolling_metrics": {},
                }

            manager_product_tenure = {
                "status": tenure.get("metric_status"),
                "start_date": tenure.get("start_date"),
                "end_date": tenure.get("end_date"),
                "as_of_date": tenure.get("metric_as_of_date") or tenure.get("end_date"),
                "observations": tenure.get("metric_observations"),
                "total_return": tenure.get("tenure_return"),
                "annualized_return": tenure.get("annualized_return"),
                "record_breaking_days_ratio": tenure.get("record_breaking_days_ratio"),
                "max_drawdown": tenure.get("max_drawdown"),
                "annualized_volatility": tenure.get("annualized_volatility"),
                "downside_risk": tenure.get("downside_risk"),
                "sharpe_ratio": tenure.get("sharpe_ratio"),
                "sortino_ratio": tenure.get("sortino_ratio"),
                "requested_start_date": tenure.get("requested_start_date"),
                "actual_start_date": tenure.get("actual_start_date"),
                "actual_end_date": tenure.get("actual_end_date"),
                "metric_coverage_days": tenure.get("metric_coverage_days"),
                "tenure_coverage_ratio": tenure.get("tenure_coverage_ratio"),
                "tenure_coverage_status": tenure.get("tenure_coverage_status"),
                "peer_ranking": tenure.get("peer_ranking") or {},
                "source": tenure.get("source"),
            }
            products.append({
                **base,
                "entity_id": tenure.get("entity_id"),
                "share_count": len(share_codes) or 1,
                "share_codes": share_codes or [representative_code],
                "total_asset": tenure.get("total_asset") if tenure.get("total_asset") is not None else base.get("total_asset"),
                "manager_product_tenure": manager_product_tenure,
            })

        for fund in share_funds:
            code = str(fund.get("wind_code") or "").strip().upper()
            if code and code not in covered_codes:
                products.append({
                    **fund,
                    "share_count": 1,
                    "share_codes": [code],
                })
        return products

    @classmethod
    def _manager_assessment(
        cls,
        product_tenures: Dict[str, Any],
        reports: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        current_items = [
            item for item in (product_tenures.get("items") or [])
            if isinstance(item, dict) and item.get("is_current")
        ]
        evaluated_items = [
            item for item in current_items
            if item.get("metric_status") in {"manager_product_tenure", "manager_tenure"}
        ]
        peer_ranked_items = [
            item for item in current_items
            if (item.get("peer_ranking") or {}).get("status") == "sufficient"
        ]
        representative = cls._representative_tenure(evaluated_items)
        evidence_items = cls._assessment_evidence(current_items)
        strengths = [item for item in evidence_items if item["direction"] == "strength"][:3]
        risks = [item for item in evidence_items if item["direction"] == "risk"][:3]
        product_count = len(current_items)
        evaluated_count = len(evaluated_items)
        peer_ranked_count = len(peer_ranked_items)

        if not current_items:
            status = "empty"
            summary = "当前没有可核验的在管产品，暂不形成经理评价。"
        elif evaluated_count == 0:
            status = "insufficient_evidence"
            summary = f"当前关联 {product_count} 个在管产品，但任期净值证据不足，暂不评价经理表现。"
        else:
            status = "available" if peer_ranked_count == product_count else "partial"
            summary = (
                f"当前关联 {product_count} 个在管产品，其中 {evaluated_count} 个已有单产品任期指标，"
                f"{peer_ranked_count} 个达到同区间同类排名门槛。"
            )

        return {
            "status": status,
            "summary": summary,
            "current_product_count": product_count,
            "tenure_evaluated_product_count": evaluated_count,
            "peer_ranked_product_count": peer_ranked_count,
            "memo_count": len(reports),
            "representative_product": representative,
            "strengths": strengths,
            "risks": risks,
            "scope_note": "不生成经理综合收益、综合净值或综合分；所有判断均落到具体产品、任期区间和同类样本。",
            "methodology_version": "manager_product_evidence_assessment_v1",
        }

    @classmethod
    def _representative_tenure(cls, items: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        if not items:
            return None

        def metric_count(item: Dict[str, Any]) -> int:
            return sum(
                cls._number(item.get(metric)) is not None
                for metric in (
                    "tenure_return", "annualized_return", "record_breaking_days_ratio",
                    "max_drawdown", "sharpe_ratio",
                )
            )

        selected = sorted(
            items,
            key=lambda item: (
                int(item.get("benchmark_nav_observations") or 0) >= 2,
                (item.get("peer_ranking") or {}).get("status") == "sufficient",
                metric_count(item),
                cls._number(item.get("total_asset")) or 0,
                int(item.get("tenure_days") or 0),
                str(item.get("fund_code") or ""),
            ),
            reverse=True,
        )[0]
        return {
            "fund_code": selected.get("fund_code"),
            "fund_name": selected.get("fund_name"),
            "category": selected.get("category"),
            "start_date": selected.get("start_date"),
            "end_date": selected.get("end_date"),
            "tenure_days": selected.get("tenure_days"),
            "tenure_return": selected.get("tenure_return"),
            "annualized_return": selected.get("annualized_return"),
            "record_breaking_days_ratio": selected.get("record_breaking_days_ratio"),
            "max_drawdown": selected.get("max_drawdown"),
            "sharpe_ratio": selected.get("sharpe_ratio"),
            "requested_start_date": selected.get("requested_start_date"),
            "actual_start_date": selected.get("actual_start_date"),
            "actual_end_date": selected.get("actual_end_date"),
            "metric_coverage_days": selected.get("metric_coverage_days"),
            "tenure_coverage_ratio": selected.get("tenure_coverage_ratio"),
            "tenure_coverage_status": selected.get("tenure_coverage_status"),
            "peer_ranking": selected.get("peer_ranking") or {},
            "benchmark": {
                "code": selected.get("benchmark_code"),
                "name": selected.get("benchmark_name"),
                "type": selected.get("benchmark_type"),
                "observations": int(selected.get("benchmark_nav_observations") or 0),
                "status": (
                    "available"
                    if int(selected.get("benchmark_nav_observations") or 0) >= 2
                    else "unavailable"
                ),
            },
            "selection_reason": "优先选择真实基准曲线可核验、同类排名可用、任期指标完整的当前产品；它是证据展示样本，不代表经理全部产品。",
        }

    @classmethod
    def _assessment_evidence(cls, items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        metric_labels = {
            "total_return": "任期收益",
            "record_breaking_days_ratio": "创新高天数占比",
            "max_drawdown": "回撤控制",
            "sharpe_ratio": "风险调整后收益",
        }
        evidence: List[Dict[str, Any]] = []
        for item in items:
            ranking = item.get("peer_ranking") if isinstance(item.get("peer_ranking"), dict) else {}
            peer_group_name = str(ranking.get("peer_group_name") or item.get("category") or "标准同类组")
            metrics = ranking.get("metrics") if isinstance(ranking.get("metrics"), dict) else {}
            for metric_name, label in metric_labels.items():
                metric = metrics.get(metric_name) if isinstance(metrics.get(metric_name), dict) else {}
                if metric.get("sample_status") != "sufficient":
                    continue
                percentile = cls._number(metric.get("percentile"))
                rank = int(metric.get("rank") or 0)
                peer_count = int(metric.get("peer_count") or 0)
                if percentile is None or rank <= 0 or peer_count <= 0:
                    continue
                if percentile >= 80:
                    direction = "strength"
                    conclusion = f"{label}处于同类前列"
                elif percentile <= 20:
                    direction = "risk"
                    conclusion = f"{label}处于同类后列"
                else:
                    continue
                fund_name = str(item.get("fund_name") or item.get("fund_code") or "该产品")
                evidence.append({
                    "direction": direction,
                    "label": conclusion,
                    "statement": f"{fund_name}在该经理任期内的{label}排名 {rank}/{peer_count}，仅与{peer_group_name}同区间产品比较。",
                    "fund_code": item.get("fund_code"),
                    "fund_name": fund_name,
                    "category": peer_group_name,
                    "metric_name": metric_name,
                    "rank": rank,
                    "peer_count": peer_count,
                    "percentile": percentile,
                    "period_start": ranking.get("period_start"),
                    "period_end": ranking.get("period_end"),
                })
        return sorted(
            evidence,
            key=lambda item: (
                0 if item["direction"] == "strength" else 1,
                -item["percentile"] if item["direction"] == "strength" else item["percentile"],
                str(item.get("fund_code") or ""),
            ),
        )

    @classmethod
    def _canonical_tenures(cls, items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        grouped: Dict[str, List[Dict[str, Any]]] = {}
        for item in items:
            key = ":".join([
                fund_product_identity(item),
                "current" if item.get("is_current") else "historical",
                str(item.get("end_date") or ""),
            ])
            grouped.setdefault(key, []).append(item)
        canonical = []
        for group in grouped.values():
            representative = sorted(
                group,
                key=lambda item: (
                    not bool(item.get("is_primary_share")),
                    item.get("metric_status") == "unavailable",
                    str(item.get("fund_code") or ""),
                ),
            )[0]
            start_dates = [item.get("start_date") for item in group if item.get("start_date")]
            asset_values = [
                cls._number(item.get("total_asset"))
                for item in group
                if cls._number(item.get("total_asset")) is not None
            ]
            share_codes = list(dict.fromkeys([
                str(representative.get("fund_code") or ""),
                *[str(item.get("fund_code") or "") for item in group],
            ]))
            canonical.append({
                **representative,
                "start_date": min(start_dates) if start_dates else representative.get("start_date"),
                "total_asset": max(asset_values) if asset_values else None,
                "share_count": len(group),
                "share_codes": [code for code in share_codes if code],
            })
        return sorted(
            canonical,
            key=lambda item: (
                bool(item.get("is_current")),
                str(item.get("start_date") or ""),
                str(item.get("fund_code") or ""),
            ),
            reverse=True,
        )

    @staticmethod
    def _project_tenure(row: Dict[str, Any]) -> Dict[str, Any]:
        start_date = row.get("start_date")
        end_date = row.get("end_date")
        effective_end = end_date or date.today()
        if isinstance(start_date, str):
            try:
                start_date = date.fromisoformat(start_date[:10])
            except ValueError:
                start_date = None
        if isinstance(effective_end, str):
            try:
                effective_end = date.fromisoformat(effective_end[:10])
            except ValueError:
                effective_end = None
        tenure_days = (effective_end - start_date).days + 1 if start_date and effective_end else None
        performance = row.get("performance_snapshot") if isinstance(row.get("performance_snapshot"), dict) else {}
        metrics = performance if performance.get("status") == "available" else {}
        return {
            "fund_code": row.get("fund_code"),
            "fund_name": row.get("fund_name") or row.get("fund_code"),
            "type": row.get("type"),
            "category": row.get("peer_group_name") or row.get("strategy_name") or row.get("type"),
            "classification_status": "classified" if row.get("peer_group_name") else "pending",
            "strategy_key": row.get("strategy_key"),
            "strategy_name": row.get("strategy_name"),
            "benchmark_code": row.get("benchmark_code"),
            "benchmark_name": row.get("benchmark_name"),
            "benchmark_type": row.get("benchmark_type"),
            "benchmark_nav_observations": int(row.get("benchmark_nav_observations") or 0),
            "total_asset": row.get("total_asset"),
            "start_date": start_date,
            "end_date": end_date,
            "tenure_days": tenure_days,
            "is_current": bool(row.get("is_current")),
            "entity_id": row.get("entity_id"),
            "is_primary_share": row.get("is_primary"),
            "tenure_return": metrics.get("total_return"),
            "annualized_return": metrics.get("annualized_return"),
            "record_breaking_days_ratio": metrics.get("record_breaking_days_ratio"),
            "max_drawdown": metrics.get("max_drawdown"),
            "annualized_volatility": metrics.get("annualized_volatility"),
            "downside_risk": metrics.get("downside_risk"),
            "sharpe_ratio": metrics.get("sharpe_ratio"),
            "sortino_ratio": metrics.get("sortino_ratio"),
            "metric_as_of_date": metrics.get("end_date") or row.get("nav_date"),
            "metric_start_date": metrics.get("start_date") or start_date,
            "metric_observations": metrics.get("observations"),
            "requested_start_date": metrics.get("requested_start_date") or start_date,
            "actual_start_date": metrics.get("actual_start_date") or metrics.get("start_date"),
            "actual_end_date": metrics.get("actual_end_date") or metrics.get("end_date"),
            "metric_coverage_days": metrics.get("metric_coverage_days"),
            "tenure_coverage_ratio": metrics.get("tenure_coverage_ratio"),
            "tenure_coverage_status": metrics.get("tenure_coverage_status"),
            "peer_ranking_eligible": metrics.get("peer_ranking_eligible"),
            "metric_status": "manager_product_tenure" if performance.get("status") == "available" else "unavailable",
            "source": row.get("source") or "tushare.fund_manager",
        }

    @classmethod
    def _portfolio_summary(
        cls,
        product_tenures: Dict[str, Any],
        funds: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        current_items = [
            item for item in (product_tenures.get("items") or [])
            if isinstance(item, dict) and item.get("is_current")
        ]
        buckets: Dict[str, Dict[str, Any]] = {}
        asset_values: List[float] = []
        for item in current_items:
            key, label = cls._manager_category(item)
            bucket = buckets.setdefault(key, {
                "key": key,
                "label": label,
                "product_count": 0,
                "classified_product_count": 0,
                "managed_asset": 0.0,
                "managed_asset_product_count": 0,
            })
            bucket["product_count"] += 1
            if item.get("classification_status") == "classified":
                bucket["classified_product_count"] += 1
            asset = cls._number(item.get("total_asset"))
            if asset is not None and asset >= 0:
                asset_values.append(asset)
                bucket["managed_asset"] += asset
                bucket["managed_asset_product_count"] += 1

        distribution = sorted(
            buckets.values(),
            key=lambda item: (-int(item["product_count"]), str(item["label"])),
        )
        for item in distribution:
            item["managed_asset"] = round(float(item["managed_asset"]), 4) if item["managed_asset_product_count"] else None
        product_count = len(current_items)
        asset_count = len(asset_values)
        return {
            "manager_type_labels": [item["label"] for item in distribution],
            "category_distribution": distribution,
            "current_product_count": product_count,
            "current_share_count": int(product_tenures.get("current_share_count") or 0),
            "classified_product_count": sum(item.get("classification_status") == "classified" for item in current_items),
            "evaluated_product_count": sum(
                fund.get("professional_score") is not None for fund in funds
            ),
            "managed_asset": round(sum(asset_values), 4) if asset_values else None,
            "managed_asset_product_count": asset_count,
            "managed_asset_coverage": round(asset_count / product_count, 4) if product_count else 0.0,
            "managed_asset_scope": "按基金产品合并 A/C/Y 等份额，每个产品只取一个本地已同步规模；不代表基金公司官方披露口径。",
            "institutional_holding_ratio": None,
            "institutional_holding_status": "holder_structure_not_connected",
            "institutional_holding_scope": "持有人结构数据尚未接入，不根据基金规模或名称推测机构占比。",
        }

    @staticmethod
    def _manager_category(item: Dict[str, Any]) -> tuple[str, str]:
        strategy = str(item.get("strategy_key") or "").lower()
        fund_type = str(item.get("type") or "").lower()
        category = str(item.get("category") or "").lower()
        if strategy.startswith("qdii") or "qdii" in fund_type or "qdii" in category:
            return "qdii", "QDII"
        if strategy.startswith("index_") or "指数" in fund_type or category.startswith("指数-"):
            return "passive_equity", "被动权益"
        if strategy in {"fixed_income_equity_allocation", "mixed_bond_allocation", "mixed_balanced_allocation"}:
            return "fixed_income_plus", "固收+"
        if strategy.startswith("fixed_income") or "债券" in fund_type:
            return "fixed_income", "固收"
        if strategy.startswith("active_equity") or strategy == "mixed_equity_allocation":
            return "active_equity", "主动权益"
        if "货币" in fund_type:
            return "money_market", "货币"
        return "other", str(item.get("type") or "待分类")

    @staticmethod
    def _project_fund(row: Dict[str, Any]) -> Dict[str, Any]:
        profile = row.get("research_profile") if isinstance(row.get("research_profile"), dict) else {}
        scoring = row.get("professional_scoring") if isinstance(row.get("professional_scoring"), dict) else {}
        rolling = row.get("rolling_metrics") if isinstance(row.get("rolling_metrics"), dict) else {}
        raw_data = row.get("raw_data") if isinstance(row.get("raw_data"), dict) else {}
        universe = raw_data.get("universe") if isinstance(raw_data.get("universe"), dict) else {}
        info = raw_data.get("info") if isinstance(raw_data.get("info"), dict) else {}
        return {
            **FundResearchSnapshotService.project_fund(row),
            "company": row.get("company") or universe.get("company") or info.get("company"),
            "peer_group": profile.get("peer_group"),
            "peer_group_id": profile.get("peer_group_id"),
            "style_label": profile.get("style_label"),
            "classification_status": "classified" if profile.get("peer_group") else "pending",
            "professional_score": scoring.get("overall_score"),
            "professional_grade": scoring.get("overall_grade"),
            "evaluation_status": scoring.get("status") or ("available" if scoring.get("overall_score") is not None else "pending"),
            "evaluation_summary": FundManagerResearchService._evaluation_summary(scoring),
            "evaluation_missing_data": scoring.get("missing_data") or [],
            "evaluation_quality_score": (scoring.get("data_quality") or {}).get("score"),
            "evaluation_as_of_date": scoring.get("as_of_date"),
            "rolling_metrics": rolling,
        }

    @staticmethod
    def _evaluation_summary(scoring: Dict[str, Any]) -> str:
        if scoring.get("overall_score") is not None:
            return "评价完整" if scoring.get("status") == "ok" else "评价部分可用"
        missing = [str(item) for item in scoring.get("missing_data") or []]
        if any(item.startswith("core_metric:1y.") for item in missing):
            return "缺少近1年净值评价指标"
        if any("classification" in item or "分类" in item for item in missing):
            return "专业分类证据不足"
        return "评价证据不足" if missing else "评价待计算"

    @staticmethod
    def _company_from_funds(funds: List[Dict[str, Any]]) -> str:
        for fund in funds:
            company = str(fund.get("company") or "").strip()
            if company:
                return company
        return ""

    def _load_research_reports(self, manager_id: str, limit: int) -> List[Dict[str, Any]]:
        if hasattr(self.report_repo, "list_reports_for_manager_exact"):
            reports = self.report_repo.list_reports_for_manager_exact(manager_id, limit=limit)
        else:
            reports = self.report_repo.list_reports(
                manager_id=manager_id,
                page=1,
                page_size=max(1, min(limit, 50)),
            ).get("reports", [])
        return self._deduplicate_reports(reports, limit)

    def _deduplicate_reports(self, reports: Iterable[Dict[str, Any]], limit: int) -> List[Dict[str, Any]]:
        deduplicated: Dict[str, Dict[str, Any]] = {}
        for row in reports:
            item = self._project_report(row)
            key = str(item.get("source_hash") or item.get("id") or f"{item.get('title')}:{item.get('report_date')}")
            deduplicated.setdefault(key, item)
        return sorted(
            deduplicated.values(),
            key=lambda item: str(item.get("report_date") or ""),
            reverse=True,
        )[:limit]

    @staticmethod
    def _historical_viewpoints(reports: List[Dict[str, Any]], profile: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        years = sorted({
            str(report.get("report_date") or "")[:4]
            for report in reports
            if len(str(report.get("report_date") or "")) >= 4
        }, reverse=True)
        sources = list(dict.fromkeys(
            str(report.get("source") or "本地调研纪要").strip()
            for report in reports
        ))
        items = []
        for report in reports:
            summary = str(report.get("summary") or "").strip()
            key_points = [
                str(point).strip()
                for point in (report.get("key_points") or [])
                if str(point or "").strip()
            ]
            evidence_points, evidence_fields = FundManagerResearchService._viewpoint_evidence(
                str(report.get("id") or ""),
                profile or {},
            )
            selected_points = [point.rstrip("；;") for point in evidence_points[:3]]
            viewpoint = " ".join(selected_points)
            viewpoint_source = "manager_profile_evidence"
            if not viewpoint:
                viewpoint = key_points[0] if key_points else FundManagerResearchService._viewpoint_excerpt(summary)
                viewpoint_source = "memo_key_point" if key_points else "memo_summary"
            items.append({
                "id": report.get("id"),
                "date": report.get("report_date"),
                "date_source": report.get("report_date_source"),
                "date_precision": report.get("report_date_precision"),
                "identity_verifications": report.get("identity_verifications") or [],
                "year": str(report.get("report_date") or "")[:4] or None,
                "source_type": "manager_memo",
                "source_label": report.get("source") or "本地调研纪要",
                "title": report.get("title"),
                "viewpoint": viewpoint[:720],
                "viewpoint_source": viewpoint_source,
                "evidence_fields": evidence_fields[:len(selected_points)],
                "summary": summary,
                "key_points": key_points,
                "tags": list(dict.fromkeys([
                    str(tag).strip()
                    for tag in [
                        *(report.get("tags") or []),
                        *(report.get("manager_classifications") or []),
                        *(report.get("manager_style_labels") or []),
                    ]
                    if str(tag or "").strip()
                ])),
                "viewpoint_topics": report.get("viewpoint_topics") or [],
                "research_domains": report.get("research_domains") or [],
                "review_status": report.get("review_status"),
                "relative_path": report.get("local_relative_path"),
            })
        return {
            "status": "available" if items else "empty",
            "count": len(items),
            "years": years,
            "sources": sources,
            "items": items,
            "source_scope": ["manager_memo"],
            "unavailable_sources": ["quarterly_report", "annual_report", "other_public_source"],
            "methodology": "confirmed_manager_memo_timeline_v1",
        }

    @staticmethod
    def _viewpoint_evidence(report_id: str, profile: Dict[str, Any]) -> tuple[List[str], List[str]]:
        evidence = profile.get("evidence") if isinstance(profile.get("evidence"), dict) else {}
        fields = evidence.get("fields") if isinstance(evidence.get("fields"), dict) else {}
        priorities = (
            "investment_objective", "product_positioning", "investment_method",
            "core_philosophy", "holding_style", "risk_philosophy",
            "stock_selection_logic", "excess_return_source",
        )
        values: List[str] = []
        matched_fields: List[str] = []
        for field in priorities:
            items = fields.get(field) if isinstance(fields.get(field), list) else []
            for item in items:
                if not isinstance(item, dict) or str(item.get("report_id") or "") != report_id:
                    continue
                value = str(item.get("value") or "").strip()
                if value and value not in values:
                    values.append(value)
                    matched_fields.append(field)
                    break
        return values, matched_fields

    @staticmethod
    def _viewpoint_excerpt(summary: str) -> str:
        normalized = re.sub(r"\s+", " ", str(summary or "")).strip()
        if not normalized:
            return ""
        headings = (
            "市场观点及投资方向", "核心投资理念", "投资理念", "市场动态",
            "行业观点", "投资策略", "组合配置及投资思路",
        )
        starts = [normalized.find(heading) for heading in headings if normalized.find(heading) >= 0]
        start = min(starts) if starts else 0
        excerpt = normalized[start:start + 360].strip(" ：:一二三四五六七八九十、.．")
        return excerpt or normalized[:360]

    @staticmethod
    def _project_report(row: Dict[str, Any]) -> Dict[str, Any]:
        manager_style_labels = FundManagerResearchService._manager_level_labels(row, "style_label", "style_labels")
        manager_classifications = FundManagerResearchService._manager_level_labels(row, "classification", "classifications")
        identity_verifications = [
            proposal.get("identity_verification") or {}
            for proposal in row.get("review_proposals") or []
            if proposal.get("kind") == "manager" and proposal.get("review_status") == "confirmed"
        ]
        return {
            "id": str(row.get("id") or row.get("_id") or ""),
            "title": row.get("title"),
            "report_date": row.get("report_date"),
            "report_date_source": row.get("report_date_source"),
            "report_date_precision": row.get("report_date_precision"),
            "source": row.get("source"),
            "summary": row.get("summary") or "",
            "key_points": row.get("key_points") or [],
            "tags": row.get("tags") or [],
            "viewpoint_topics": row.get("viewpoint_topics") or [],
            "research_domains": row.get("research_domains") or [],
            "classifications": manager_classifications,
            "style_labels": manager_style_labels,
            "manager_classifications": manager_classifications,
            "manager_style_labels": manager_style_labels,
            "review_status": row.get("review_status"),
            "local_relative_path": row.get("local_relative_path"),
            "local_source_path": row.get("local_source_path"),
            "source_hash": row.get("source_hash"),
            "manager_ids": row.get("manager_ids") or [],
            "manager_names": row.get("manager_names") or [],
            "manager_links": row.get("manager_links") or [],
            "identity_verifications": identity_verifications,
        }

    @staticmethod
    def _manager_level_labels(row: Dict[str, Any], kind: str, field_name: str) -> List[str]:
        confirmed_values = {
            str(value or "").strip()
            for value in row.get(field_name) or []
            if str(value or "").strip()
        }
        if not confirmed_values:
            return []
        values = []
        for proposal in row.get("review_proposals") or []:
            value = str(proposal.get("value") or "").strip()
            if (
                proposal.get("kind") == kind
                and proposal.get("review_status") == "confirmed"
                and proposal.get("scope") == "manager"
                and value in confirmed_values
            ):
                values.append(value)
        return list(dict.fromkeys(values))

    def _profile(self, manager: Dict[str, Any], reports: List[Dict[str, Any]]) -> Dict[str, Any]:
        manager_id = str(manager.get("wind_code") or manager.get("name") or "")
        profile = self.manager_repo.get_profile(manager_id) or {}
        confirmed_style = str(profile.get("style_label") or "").strip()
        report_styles = list(dict.fromkeys(
            str(label).strip()
            for report in reports
            for label in (report.get("manager_style_labels") or [])
            if str(label or "").strip()
        ))
        report_classifications = list(dict.fromkeys(
            str(label).strip()
            for report in reports
            for label in (report.get("manager_classifications") or [])
            if str(label or "").strip()
        ))
        has_profile = bool(profile or confirmed_style or report_styles or report_classifications)
        return {
            "status": "available" if has_profile else "empty",
            "product_positioning": self._profile_field(profile, "product_positioning"),
            "investment_objective": self._profile_field(profile, "investment_objective"),
            "investment_method": self._profile_field(profile, "investment_method"),
            "core_philosophy": profile.get("core_philosophy"),
            "stock_selection_logic": profile.get("stock_selection_logic"),
            "risk_philosophy": profile.get("risk_philosophy"),
            "focus_industries": profile.get("focus_industries") or [],
            "competence_advantages": profile.get("competence_advantages"),
            "competence_boundaries": profile.get("competence_boundaries"),
            "style_label": confirmed_style or None,
            "style_labels_from_memos": report_styles,
            "classifications_from_memos": report_classifications,
            "key_insights": profile.get("key_insights") or [],
            "red_flags": profile.get("red_flags") or [],
            "interviews_analyzed": profile.get("interviews_analyzed") or 0,
            "last_interview_date": profile.get("last_interview_date"),
            "concentration": profile.get("concentration"),
            "turnover": profile.get("turnover"),
            "excess_return_source": self._profile_field(profile, "excess_return_source"),
            "holding_style": self._profile_field(profile, "holding_style"),
            "evidence": profile.get("evidence") or {},
            "updated_by": profile.get("updated_by"),
            "source": "postgres.manager_profiles+confirmed_research_reports",
        }

    @staticmethod
    def _profile_field(profile: Dict[str, Any], field: str) -> Optional[str]:
        value = str(profile.get(field) or "").strip()
        if value:
            return value
        evidence = profile.get("evidence") if isinstance(profile.get("evidence"), dict) else {}
        fields = evidence.get("fields") if isinstance(evidence.get("fields"), dict) else {}
        framework = evidence.get("framework") if isinstance(evidence.get("framework"), dict) else {}
        items = fields.get(field) or framework.get(field) or []
        if not isinstance(items, list) or not items:
            return None
        first = items[0] if isinstance(items[0], dict) else {}
        return str(first.get("value") or "").strip() or None

    @staticmethod
    def _project_manager(manager: Dict[str, Any]) -> Dict[str, Any]:
        raw = manager.get("raw_data") if isinstance(manager.get("raw_data"), dict) else {}
        manager_row = raw.get("fund_manager_row") if isinstance(raw.get("fund_manager_row"), dict) else {}
        return {
            "id": manager.get("wind_code"),
            "manager_id": manager.get("wind_code"),
            "name": manager.get("name"),
            "company": manager.get("company"),
            "education": manager.get("education"),
            "gender": manager_row.get("gender"),
            "birth_year": manager_row.get("birth_year"),
            "work_years": manager.get("work_years"),
            "management_years": manager.get("management_years"),
            "current_funds": manager.get("current_funds") or [],
            "current_share_codes": manager.get("current_share_codes") or manager.get("current_funds") or [],
            "historical_performance": manager.get("historical_performance") or {},
            "updated_at": manager.get("updated_at"),
            "source": "postgres.managers+tushare.fund_manager",
        }

    @staticmethod
    def _coverage(funds: List[Dict[str, Any]]) -> Dict[str, Any]:
        classified = sum(bool(fund.get("peer_group")) for fund in funds)
        evaluated = sum(fund.get("professional_score") is not None for fund in funds)
        complete = sum(fund.get("evaluation_status") == "ok" for fund in funds)
        partial = sum(fund.get("evaluation_status") == "partial" for fund in funds)
        tenure = sum(
            (fund.get("manager_product_tenure") or {}).get("status") == "manager_product_tenure"
            for fund in funds
        )
        return {
            "current_fund_count": len(funds),
            "classified_fund_count": classified,
            "evaluated_fund_count": evaluated,
            "evaluation_complete_fund_count": complete,
            "evaluation_partial_fund_count": partial,
            "evaluation_missing_fund_count": max(0, len(funds) - evaluated),
            "tenure_metric_fund_count": tenure,
        }

    @staticmethod
    def _latest_metric_date(funds: List[Dict[str, Any]]) -> Optional[str]:
        dates = [
            str(metrics.get("as_of_date"))
            for fund in funds
            for metrics in (fund.get("rolling_metrics") or {}).values()
            if isinstance(metrics, dict) and metrics.get("as_of_date")
        ]
        dates.extend(
            str((fund.get("manager_product_tenure") or {}).get("as_of_date"))
            for fund in funds
            if (fund.get("manager_product_tenure") or {}).get("as_of_date")
        )
        return max(dates) if dates else None

    @staticmethod
    def _number(value: Any) -> Optional[float]:
        try:
            number = float(value)
            return number if number == number else None
        except (TypeError, ValueError):
            return None

    @property
    def manager_repo(self):
        if self._manager_repo is None:
            from repositories import get_manager_repo
            self._manager_repo = get_manager_repo()
        return self._manager_repo

    @property
    def fund_repo(self):
        if self._fund_repo is None:
            from repositories import get_fund_repo
            self._fund_repo = get_fund_repo()
        return self._fund_repo

    @property
    def report_repo(self):
        if self._report_repo is None:
            from repositories.local_research_folder_repo import PostgresLocalResearchFolderRepo
            self._report_repo = PostgresLocalResearchFolderRepo()
        return self._report_repo

    @property
    def metric_repo(self):
        if self._metric_repo is None:
            from repositories import get_metric_snapshot_repo
            self._metric_repo = get_metric_snapshot_repo()
        return self._metric_repo

    @property
    def tenure_peer_ranking_service(self):
        if self._tenure_peer_ranking_service is None:
            from services.manager_tenure_peer_ranking_service import ManagerTenurePeerRankingService

            self._tenure_peer_ranking_service = ManagerTenurePeerRankingService()
        return self._tenure_peer_ranking_service

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
