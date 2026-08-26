"""分类内基金评价 Module。"""
from typing import Any, Dict, List, Optional

from services.peer_comparison_service import PeerComparisonService
from services.professional_scoring_service import ProfessionalScoringService
from services.cross_market_peer_comparison_service import CrossMarketPeerComparisonService
from services.fund_manager_tenure_context import (
    enrich_profile_with_manager_tenure,
    resolve_manager_tenure_context,
)


class FundEvaluationService:
    """通过一个 Interface 汇合分类、同类组、基准、评分和同类分位。"""

    METHODOLOGY_VERSION = "fund_evaluation_v3"

    def __init__(
        self,
        scoring_service: Optional[ProfessionalScoringService] = None,
        peer_comparison_service: Optional[PeerComparisonService] = None,
        cross_market_peer_service: Optional[CrossMarketPeerComparisonService] = None,
        holding_change_service: Optional[Any] = None,
        manager_repo: Optional[Any] = None,
    ):
        self.scoring_service = scoring_service or ProfessionalScoringService()
        self.peer_comparison_service = peer_comparison_service or PeerComparisonService(
            scoring_service=self.scoring_service
        )
        self.cross_market_peer_service = cross_market_peer_service or CrossMarketPeerComparisonService()
        self.holding_change_service = holding_change_service
        self._manager_repo = manager_repo

    def evaluate_fund(self, wind_code: str, window: str = "1y") -> Dict[str, Any]:
        if not hasattr(self.scoring_service, "score_from_inputs"):
            return self._assemble(
                self.scoring_service.score_fund(wind_code),
                self.peer_comparison_service.build_peer_percentiles(wind_code, window=window),
                wind_code,
                window,
            )
        return self.evaluate_from_context(self.load_context(wind_code), window=window)

    def load_context(self, wind_code: str) -> Dict[str, Any]:
        """一次读取基金评价所需事实，供详情、推荐和 AI 共用。"""
        from repositories import (
            get_fund_classification_repo,
            get_fund_repo,
            get_manager_repo,
            get_metric_snapshot_repo,
            get_nav_repo,
            get_research_profile_repo,
        )

        fund = get_fund_repo().get_fund_by_identifier(wind_code) or {}
        resolved_code = fund.get("wind_code") or wind_code
        stored_profile = get_research_profile_repo().get_profile(resolved_code) or {}
        panel = get_metric_snapshot_repo().get_latest_panel("fund", resolved_code)
        standardized_classification = get_fund_classification_repo().get_classification_context(resolved_code)
        manager_tenure_context = resolve_manager_tenure_context(
            fund,
            stored_profile,
            get_manager_repo().get_current_fund_tenure_context(resolved_code),
        )
        profile = enrich_profile_with_manager_tenure(stored_profile, manager_tenure_context)
        quality = self.scoring_service.data_quality_service.evaluate_from_inputs(
            fund,
            profile,
            panel,
            standardized_classification,
            nav_series=get_nav_repo().get_nav_series(resolved_code),
            manager_tenure_context=manager_tenure_context,
        )
        return {
            "found": bool(fund),
            "fund": fund or {"wind_code": resolved_code},
            "profile": profile,
            "metric_panel": panel,
            "data_quality": quality,
            "standardized_classification": standardized_classification,
            "manager_tenure": manager_tenure_context,
        }

    def evaluate_from_context(self, context: Dict[str, Any], window: str = "1y") -> Dict[str, Any]:
        return self.evaluate_windows_from_context(context, [window])[window]

    def evaluate_windows_from_context(
        self,
        context: Dict[str, Any],
        windows: List[str],
    ) -> Dict[str, Dict[str, Any]]:
        """同一基金只计算一次分类评分，再生成多个同类评价窗口。"""
        fund = context.get("fund") or {}
        wind_code = fund.get("wind_code") or "unknown"
        cross_market_evidence = (
            self._cross_market_evidence(
                wind_code,
                context.get("standardized_classification") or {},
            )
            if context.get("found") is True
            else self._not_requested_cross_market_evidence()
        )
        holding_stability_evidence = (
            self._holding_stability_evidence(wind_code)
            if context.get("found") is True
            else self._unavailable_holding_stability()
        )
        results = {}
        for window in dict.fromkeys(str(item) for item in windows if str(item)):
            scoring = self.scoring_service.score_from_inputs(
                fund,
                context.get("profile") or {},
                context.get("metric_panel") or [],
                context.get("data_quality") or {},
                context.get("standardized_classification") or {},
                evaluation_window=window,
            )
            peer = self.peer_comparison_service.build_peer_percentiles(
                wind_code,
                window=window,
                target_context={
                    **context,
                    "classification": scoring.get("classification") or {},
                },
            )
            results[window] = self._assemble(
                scoring,
                peer,
                wind_code,
                window,
                cross_market_evidence=cross_market_evidence,
                holding_stability_evidence=holding_stability_evidence,
            )
        return results

    def evaluate_peer_group_from_inputs(
        self,
        funds: List[Dict[str, Any]],
        profiles: Dict[str, Dict[str, Any]],
        panels: Dict[str, List[Dict[str, Any]]],
        window: str = "1y",
    ) -> Dict[str, Dict[str, Any]]:
        """批量评价同类基金，供详情、推荐和 AI 复用同一评分口径。"""
        normalized_funds = [fund for fund in funds if str(fund.get("wind_code") or "").strip()]
        codes = [str(fund.get("wind_code")) for fund in normalized_funds]
        manager_tenures = self._manager_tenure_contexts(codes)
        contexts: List[Dict[str, Any]] = []

        for fund in normalized_funds:
            code = str(fund.get("wind_code"))
            stored_profile = profiles.get(code) or {}
            manager_tenure = resolve_manager_tenure_context(
                fund,
                stored_profile,
                manager_tenures.get(code),
            )
            profile = enrich_profile_with_manager_tenure(stored_profile, manager_tenure)
            panel = panels.get(code) or []
            classification = self._standardized_classification_from_fund(fund)
            quality = self.scoring_service.data_quality_service.evaluate_from_inputs(
                fund,
                profile,
                panel,
                classification,
                manager_tenure_context=manager_tenure,
            )
            contexts.append({
                "found": True,
                "fund": fund,
                "profile": profile,
                "metric_panel": panel,
                "data_quality": quality,
                "standardized_classification": classification,
                "manager_tenure": manager_tenure,
            })

        scorings = {
            str(context["fund"]["wind_code"]): self.scoring_service.score_from_inputs(
                context["fund"],
                context["profile"],
                context["metric_panel"],
                context["data_quality"],
                context["standardized_classification"],
                evaluation_window=window,
            )
            for context in contexts
        }
        peers = self.peer_comparison_service.build_peer_percentiles_from_contexts(
            contexts,
            scorings,
            window=window,
        )
        return {
            code: {
                "scoring": scoring,
                "peer": peers.get(code) or {},
                "evaluation": self._assemble(
                    scoring,
                    peers.get(code) or {},
                    code,
                    window,
                ),
            }
            for code, scoring in scorings.items()
        }

    def _manager_tenure_contexts(self, codes: List[str]) -> Dict[str, Dict[str, Any]]:
        if self._manager_repo is None:
            from repositories import get_manager_repo

            self._manager_repo = get_manager_repo()
        return self._manager_repo.list_current_fund_tenure_contexts(codes)

    @staticmethod
    def _standardized_classification_from_fund(fund: Dict[str, Any]) -> Dict[str, Any]:
        peer_group_id = fund.get("standardized_peer_group_id")
        peer_group_key = fund.get("standardized_peer_group_key")
        peer_group_name = fund.get("standardized_peer_group_name")
        strategy_family_key = fund.get("strategy_family_key")
        benchmark_code = fund.get("benchmark_code")
        benchmark_name = fund.get("benchmark_name")
        missing_items = []
        if not strategy_family_key:
            missing_items.append("缺少标准化策略族谱")
        if not (peer_group_id or peer_group_key or peer_group_name):
            missing_items.append("缺少标准化同类组")
        if not benchmark_code:
            missing_items.append("缺少可核验基准代码")
        return {
            "status": "resolved" if not missing_items else "insufficient_evidence",
            "fund_code": fund.get("wind_code"),
            "entity_id": fund.get("entity_id"),
            "canonical_code": fund.get("canonical_code") or fund.get("wind_code"),
            "canonical_name": fund.get("canonical_name") or fund.get("name"),
            "asset_class": fund.get("asset_class"),
            "active_passive": fund.get("active_passive"),
            "strategy_family_key": strategy_family_key,
            "strategy_family_name": fund.get("strategy_family_name"),
            "peer_group_id": peer_group_id,
            "peer_group_key": peer_group_key,
            "peer_group_name": peer_group_name,
            "minimum_peer_count": fund.get("minimum_peer_count"),
            "benchmark_mapping": {
                "benchmark_code": benchmark_code,
                "benchmark_name": benchmark_name,
            },
            "classification_confidence": fund.get("classification_confidence") or 0.95,
            "classification_evidence": [{
                "source": "fund_classification_repo.list_recommendation_funds",
                "field": "peer_group_members.peer_group_id",
            }],
            "missing_items": missing_items,
        }

    def _assemble(
        self,
        scoring: Dict[str, Any],
        peer: Dict[str, Any],
        wind_code: str,
        window: str,
        cross_market_evidence: Optional[Dict[str, Any]] = None,
        holding_stability_evidence: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        classification = scoring.get("classification") or peer.get("classification") or {
            "status": "insufficient_evidence",
            "missing_items": ["基金分类结果缺失"],
        }

        missing_items = self._missing_items(scoring, peer, classification)
        status = self._status(scoring, peer, classification)
        evaluation_blocked = status == "insufficient_evidence"
        composite_score_blocked = (
            evaluation_blocked
            or peer.get("sample_status") != "sufficient"
        )

        profile_key = scoring.get("fund_type_profile") or classification.get("evaluation_profile_key")
        methodology = {
            "status": "unavailable",
            "profile_key": profile_key,
            "evaluation_window": window,
            "dimensions": [],
        }
        methodology_service = getattr(self.scoring_service, "methodology", None)
        if methodology_service is not None and hasattr(methodology_service, "describe"):
            methodology = methodology_service.describe(profile_key or "", window)

        return {
            "status": status,
            "methodology_version": self.METHODOLOGY_VERSION,
            "evaluation_scope": "category_relative",
            "target": {
                "wind_code": scoring.get("target_id") or peer.get("target_id") or wind_code,
                "name": peer.get("name"),
                "fund_type": peer.get("fund_type"),
                "as_of_date": scoring.get("as_of_date"),
            },
            "classification": classification,
            "peer_context": {
                "peer_group": peer.get("peer_group") or classification.get("peer_group"),
                "peer_group_id": classification.get("peer_group_id"),
                "peer_group_key": classification.get("peer_group_key"),
                "primary_benchmark": peer.get("primary_benchmark") or classification.get("primary_benchmark"),
                "benchmark_code": classification.get("benchmark_code"),
                "benchmark_mapping": classification.get("benchmark_mapping"),
                "source": peer.get("peer_group_source"),
                "peer_count": peer.get("peer_count", 0),
                "classified_peer_count": peer.get("classified_peer_count", peer.get("peer_count", 0)),
                "valid_metric_peer_count": peer.get("valid_metric_peer_count", 0),
                "minimum_peer_count": peer.get("minimum_valid_peer_count"),
                "sample_status": peer.get("sample_status"),
                "metric_window": peer.get("metric_window") or window,
                "metric_coverage": peer.get("metric_coverage", {}),
                "peer_metric_profile": peer.get("peer_metric_profile"),
                "peer_methodology_version": peer.get("peer_methodology_version"),
            },
            "evaluation": {
                "overall_score": None if composite_score_blocked else scoring.get("overall_score"),
                "overall_grade": "insufficient_evidence" if composite_score_blocked else scoring.get("overall_grade"),
                "dimension_scores": {} if evaluation_blocked else scoring.get("dimension_scores", {}),
                "metric_scores": {} if evaluation_blocked else scoring.get("metric_scores", {}),
                "peer_percentiles": {} if composite_score_blocked else peer.get("metrics", {}),
                "positive_factors": scoring.get("positive_factors", []),
                "negative_factors": scoring.get("negative_factors", []),
                "calculation_method": scoring.get("calculation_method"),
                "data_quality": scoring.get("data_quality", {}),
                "source_snapshot_ids": scoring.get("source_snapshot_ids", []),
            },
            "methodology": methodology,
            "explanatory_evidence": {
                "cross_market_holding": cross_market_evidence or self._not_requested_cross_market_evidence(),
                "holding_stability": holding_stability_evidence or self._unavailable_holding_stability(),
                "fof_lookthrough": scoring.get("fof_lookthrough") or {
                    "status": "not_applicable",
                    "included_in_score": False,
                    "missing_items": [],
                },
                "barra": {
                    "role": "optional",
                    "status": "not_requested",
                    "included_in_score": False,
                },
                "brinson": {
                    "role": "optional",
                    "status": "not_requested",
                    "included_in_score": False,
                },
            },
            "missing_items": missing_items,
            "product_scope": {
                "fund_classification": "core",
                "fund_evaluation": "core",
                "explanatory_attribution": "optional",
                "reporting": "projection_only",
                "investment_decision": "excluded",
            },
        }

    def _holding_stability_evidence(self, wind_code: str) -> Dict[str, Any]:
        try:
            if self.holding_change_service is None:
                from services.fund_holding_change_service import FundHoldingChangeService

                self.holding_change_service = FundHoldingChangeService()
            result = self.holding_change_service.analyze(wind_code, refresh_missing=False)
            stability = result.get("stability") or {}
            if result.get("status") != "available" or stability.get("status") != "available":
                return self._unavailable_holding_stability(result.get("missing_items") or [])
            return {
                **stability,
                "latest_quarter": result.get("latest_quarter"),
                "previous_quarter": result.get("previous_quarter"),
                "source": result.get("source"),
            }
        except Exception as exc:
            return self._unavailable_holding_stability([f"公开持仓稳定性暂不可用：{exc}"])

    @staticmethod
    def _unavailable_holding_stability(missing_items: Optional[List[str]] = None) -> Dict[str, Any]:
        return {
            "status": "insufficient_evidence",
            "methodology": "consecutive_quarter_top10_normalized_overlap_v1",
            "included_in_score": False,
            "missing_items": missing_items or ["至少需要相邻两个季度的公开前十大持仓"],
            "boundary": "公开持仓稳定性只作解释，不参与基金综合评分。",
        }

    def _cross_market_evidence(
        self,
        wind_code: str,
        classification: Dict[str, Any],
    ) -> Dict[str, Any]:
        try:
            return self.cross_market_peer_service.build(
                wind_code,
                classification=classification,
            )
        except Exception as exc:
            return {
                **self._not_requested_cross_market_evidence(),
                "status": "unavailable",
                "missing_items": [f"跨市场持仓同类比较暂不可用：{exc}"],
            }

    @staticmethod
    def _not_requested_cross_market_evidence() -> Dict[str, Any]:
        return {
            "status": "not_requested",
            "method": "cross_market_holding_peer_comparison_v1",
            "included_in_score": False,
            "comparisons": [],
            "labels": [],
            "missing_items": [],
            "boundary": "跨市场持仓同类比较属于解释证据，不参与基金评分。",
        }

    def _status(
        self,
        scoring: Dict[str, Any],
        peer: Dict[str, Any],
        classification: Dict[str, Any],
    ) -> str:
        if classification.get("status") != "classified" or scoring.get("status") == "insufficient_evidence":
            return "insufficient_evidence"
        if not self._core_context_ready(peer, classification):
            return "insufficient_evidence"
        if scoring.get("status") != "ok" or peer.get("sample_status") != "sufficient":
            return "partial"
        return "ok"

    def _missing_items(
        self,
        scoring: Dict[str, Any],
        peer: Dict[str, Any],
        classification: Dict[str, Any],
    ) -> List[str]:
        items: List[str] = []
        items.extend(str(item) for item in classification.get("missing_items", []) if item)
        items.extend(str(item) for item in scoring.get("missing_data", []) if item)
        if not (peer.get("peer_group") or classification.get("peer_group")):
            items.append("缺少显式同类组，不能形成分类内基金评价")
        if not (peer.get("primary_benchmark") or classification.get("primary_benchmark")):
            items.append("缺少有效基准映射，不能形成分类内基金评价")

        sample_status = peer.get("sample_status")
        if sample_status not in {None, "sufficient"}:
            classified_count = peer.get("classified_peer_count", peer.get("peer_count", 0))
            valid_count = peer.get("valid_metric_peer_count", 0)
            minimum = peer.get("minimum_valid_peer_count")
            status_label = {
                "insufficient_peer_sample": "同类有效样本不足",
                "target_metric_missing": "本基金核心指标缺失",
                "unavailable": "同类评价数据不可用",
            }.get(sample_status, "同类评价暂不可用")
            items.append(
                f"{status_label}：已分类产品 {classified_count} 只，"
                f"具备完整指标 {valid_count} 只，最低需要 {minimum} 只"
            )

        gap = peer.get("peer_metric_gap") or {}
        blocking_metrics = gap.get("blocking_metrics") or []
        if blocking_metrics:
            metric_gaps = []
            for metric in blocking_metrics:
                if isinstance(metric, dict):
                    label = metric.get("label") or metric.get("metric_name") or "指标"
                    peer_count = int(metric.get("peer_count") or 0)
                    missing_count = int(metric.get("missing_count") or 0)
                    metric_gaps.append(f"{label} {peer_count}/{peer_count + missing_count} 只")
                else:
                    metric_gaps.append(str(metric))
            items.append(f"同类分位尚不可用：{'；'.join(metric_gaps)}")

        return list(dict.fromkeys(item for item in items if item))

    def _core_context_ready(
        self,
        peer: Dict[str, Any],
        classification: Dict[str, Any],
    ) -> bool:
        peer_group = peer.get("peer_group") or classification.get("peer_group")
        benchmark = peer.get("primary_benchmark") or classification.get("primary_benchmark")
        return bool(peer_group and benchmark)
