"""
同类分位与基金对比矩阵服务

面向投研筛选场景，把“绝对指标”翻译成“同类相对位置”和“横向优劣矩阵”。
"""
from datetime import date
from decimal import Decimal
from statistics import median
from typing import Any, Dict, List, Optional, Tuple

from services.fund_classification_service import FundClassificationService
from services.professional_scoring_service import ProfessionalScoringService
from services.scoring_contract import grade_for_score

try:
    from backend.lib.fund_status import active_fund_sql
except ModuleNotFoundError:
    from lib.fund_status import active_fund_sql


class PeerComparisonService:
    """同类分位与多基金对比入口。"""

    MIN_VALID_PEERS = 5
    PEER_UNIVERSE_LIMIT = 10000

    METRIC_CONFIGS = [
        {"metric_name": "annualized_return", "label": "1Y 年化收益", "unit": "percent", "higher_is_better": True},
        {"metric_name": "max_drawdown", "label": "1Y 最大回撤", "unit": "percent", "higher_is_better": True},
        {"metric_name": "annualized_volatility", "label": "1Y 年化波动", "unit": "percent", "higher_is_better": False},
        {"metric_name": "sharpe_ratio", "label": "1Y 夏普比率", "unit": "number", "higher_is_better": True},
        {"metric_name": "calmar_ratio", "label": "1Y Calmar", "unit": "number", "higher_is_better": True},
        {"metric_name": "positive_return_ratio", "label": "1Y 正收益占比", "unit": "percent", "higher_is_better": True},
    ]

    def __init__(
        self,
        scoring_service: Optional[ProfessionalScoringService] = None,
        classification_service: Optional[FundClassificationService] = None,
        classification_adapter: Optional[Any] = None,
        fund_repo: Optional[Any] = None,
        profile_repo: Optional[Any] = None,
    ):
        self.scoring_service = scoring_service or ProfessionalScoringService()
        self.classification_service = classification_service or FundClassificationService()
        self._classification_adapter = classification_adapter
        self._fund_repo_adapter = fund_repo
        self._profile_repo_adapter = profile_repo

    def build_peer_percentiles(
        self,
        wind_code: str,
        window: str = "1y",
        target_context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        if target_context is None:
            target, peer_funds, peer_group_source = self._peer_universe(wind_code)
        else:
            target, peer_funds, peer_group_source = self._peer_universe(wind_code, target_context)
        target_id = target.get("wind_code") or wind_code
        peer_codes = [fund["wind_code"] for fund in peer_funds if fund.get("wind_code")]
        if target_context and target_context.get("metric_panel") is not None:
            metric_map = self._metric_map(
                peer_codes,
                peer_funds,
                {target_id: target_context["metric_panel"]},
            )
        else:
            metric_map = self._metric_map(peer_codes, peer_funds)
        target_profile = target.get("research_profile") or {}
        classification = target.get("classification") or self.classification_service.classify(target, target_profile)
        evaluation_profile_key = classification.get("evaluation_profile_key")
        metric_configs = self._peer_metric_configs(evaluation_profile_key)
        minimum_peer_count = self._minimum_peer_count(classification.get("minimum_peer_count"))
        scoring_map = self._fast_peer_score_map(
            peer_codes,
            metric_map,
            window,
            evaluation_profile_key,
            peer_funds,
        )
        peer_fund_map = {
            str(fund.get("wind_code") or ""): fund
            for fund in peer_funds
            if fund.get("wind_code")
        }

        metrics: Dict[str, Any] = {}
        for config in metric_configs:
            metric_name = config["metric_name"]
            values = [
                (
                    code,
                    None
                    if self._requires_selected_window(config)
                    and not self._window_history_ready(peer_fund_map.get(code, {}), window)
                    else self._peer_metric_value(metric_map.get(code, {}), config, window),
                )
                for code in peer_codes
            ]
            metrics[metric_name] = self._rank_metric(
                target_id=target_id,
                values=values,
                higher_is_better=config["higher_is_better"],
                metric_name=metric_name,
                label=self._window_metric_label(config["label"], window),
                unit=config["unit"],
                minimum_peer_count=minimum_peer_count,
                metric_window=self._metric_window_label(config, window),
                required_for_sample=bool(config.get("required_for_sample", True)),
                source_metric_names=[path[1] for path in config.get("paths") or []],
            )

        professional_values = [
            (code, self._to_float(scoring_map.get(code, {}).get("overall_score")))
            for code in peer_codes
        ]
        metrics["professional_score"] = self._rank_metric(
            target_id=target_id,
            values=professional_values,
            higher_is_better=True,
            metric_name="professional_score",
            label=f"{self._window_label(window)}同类综合位置",
            unit="score",
            minimum_peer_count=minimum_peer_count,
            metric_window=window,
            required_for_sample=False,
            source_metric_names=["category_specific_peer_metric_proxy"],
        )

        metric_coverage = self._metric_coverage(metrics)
        valid_metric_peer_count = self._valid_metric_peer_count(metrics)

        return {
            "target_id": target_id,
            "name": target.get("name"),
            "fund_type": target.get("type"),
            "peer_group": classification.get("peer_group") or target_profile.get("peer_group"),
            "primary_benchmark": classification.get("primary_benchmark") or target_profile.get("primary_benchmark"),
            "peer_group_source": peer_group_source,
            "classification": classification,
            "evaluation_scope": "category_relative",
            "peer_count": len(peer_codes),
            "classified_peer_count": len(peer_codes),
            "valid_metric_peer_count": valid_metric_peer_count,
            "minimum_valid_peer_count": minimum_peer_count,
            "peer_metric_profile": evaluation_profile_key,
            "peer_methodology_version": getattr(
                getattr(self.scoring_service, "methodology", None),
                "PEER_METHODOLOGY_VERSION",
                "category_peer_percentiles_v4",
            ),
            "metric_coverage": metric_coverage,
            "usable_metric_count": self._usable_metric_count(metrics),
            "insufficient_metric_count": self._insufficient_metric_count(metrics),
            "peer_metric_gap": self._peer_metric_gap(
                metrics,
                peer_funds,
                metric_map,
                window,
                target_id,
                minimum_peer_count,
                metric_configs,
            ),
            "sample_status": self._sample_status(metrics),
            "metric_window": window,
            "professional_score_source": "category_specific_peer_metric_proxy",
            "product_scope": {
                "fund_classification": "core",
                "fund_evaluation": "core",
                "investment_decision": "excluded",
            },
            "metrics": metrics,
        }

    def build_peer_percentiles_from_contexts(
        self,
        contexts: List[Dict[str, Any]],
        scorings: Dict[str, Dict[str, Any]],
        window: str = "1y",
    ) -> Dict[str, Dict[str, Any]]:
        """对已批量读取的同类基金事实生成分位，不再逐只查库和重复评分。"""
        grouped: Dict[Tuple[str, str], List[Dict[str, Any]]] = {}
        for context in contexts:
            fund = context.get("fund") or {}
            code = str(fund.get("wind_code") or "").strip()
            if not code:
                continue
            classification = (scorings.get(code) or {}).get("classification") or {}
            group_key = str(
                classification.get("peer_group_id")
                or classification.get("peer_group_key")
                or classification.get("peer_group")
                or code
            )
            profile_key = str(classification.get("evaluation_profile_key") or "")
            grouped.setdefault((group_key, profile_key), []).append(context)

        results: Dict[str, Dict[str, Any]] = {}
        for (_, profile_key), peer_contexts in grouped.items():
            peer_funds = []
            preloaded_panels = {}
            classifications = {}
            for context in peer_contexts:
                fund = dict(context.get("fund") or {})
                code = str(fund.get("wind_code") or "").strip()
                if not code:
                    continue
                fund["research_profile"] = context.get("profile") or {}
                peer_funds.append(fund)
                preloaded_panels[code] = context.get("metric_panel") or []
                classifications[code] = (scorings.get(code) or {}).get("classification") or {}

            peer_codes = [str(fund.get("wind_code")) for fund in peer_funds if fund.get("wind_code")]
            if not peer_codes:
                continue
            metric_map = self._metric_map(peer_codes, peer_funds, preloaded_panels)
            peer_fund_map = {str(fund.get("wind_code")): fund for fund in peer_funds}
            metric_configs = self._peer_metric_configs(profile_key)
            minimum_peer_count = max(
                (
                    self._minimum_peer_count(classifications.get(code, {}).get("minimum_peer_count"))
                    for code in peer_codes
                ),
                default=self.MIN_VALID_PEERS,
            )
            professional_values = [
                (code, self._to_float((scorings.get(code) or {}).get("overall_score")))
                for code in peer_codes
            ]
            ranked_metrics: Dict[str, Dict[str, Dict[str, Any]]] = {}
            for config in metric_configs:
                metric_name = config["metric_name"]
                values = [
                    (
                        code,
                        None
                        if self._requires_selected_window(config)
                        and not self._window_history_ready(peer_fund_map.get(code, {}), window)
                        else self._peer_metric_value(metric_map.get(code, {}), config, window),
                    )
                    for code in peer_codes
                ]
                ranked_metrics[metric_name] = self._rank_metric_map(
                    values=values,
                    higher_is_better=config["higher_is_better"],
                    metric_name=metric_name,
                    label=self._window_metric_label(config["label"], window),
                    unit=config["unit"],
                    minimum_peer_count=minimum_peer_count,
                    metric_window=self._metric_window_label(config, window),
                    required_for_sample=bool(config.get("required_for_sample", True)),
                    source_metric_names=[path[1] for path in config.get("paths") or []],
                )
            professional_ranked = self._rank_metric_map(
                values=professional_values,
                higher_is_better=True,
                metric_name="professional_score",
                label=f"{self._window_label(window)}同类综合位置",
                unit="score",
                minimum_peer_count=minimum_peer_count,
                metric_window=window,
                required_for_sample=False,
                source_metric_names=["fund_evaluation_batch_score"],
            )

            for target_id in peer_codes:
                classification = classifications.get(target_id) or {}
                metrics = {
                    metric_name: result_map[target_id]
                    for metric_name, result_map in ranked_metrics.items()
                }
                metrics["professional_score"] = professional_ranked[target_id]
                metric_coverage = self._metric_coverage(metrics)
                fund = peer_fund_map[target_id]
                results[target_id] = {
                    "target_id": target_id,
                    "name": fund.get("name"),
                    "fund_type": fund.get("type"),
                    "peer_group": classification.get("peer_group"),
                    "primary_benchmark": classification.get("primary_benchmark"),
                    "peer_group_source": "preloaded_standardized_peer_group",
                    "classification": classification,
                    "evaluation_scope": "category_relative",
                    "peer_count": len(peer_codes),
                    "classified_peer_count": len(peer_codes),
                    "valid_metric_peer_count": self._valid_metric_peer_count(metrics),
                    "minimum_valid_peer_count": minimum_peer_count,
                    "peer_metric_profile": profile_key,
                    "peer_methodology_version": getattr(
                        getattr(self.scoring_service, "methodology", None),
                        "PEER_METHODOLOGY_VERSION",
                        "category_peer_percentiles_v4",
                    ),
                    "metric_coverage": metric_coverage,
                    "usable_metric_count": self._usable_metric_count(metrics),
                    "insufficient_metric_count": self._insufficient_metric_count(metrics),
                    "peer_metric_gap": self._peer_metric_gap(
                        metrics,
                        peer_funds,
                        metric_map,
                        window,
                        target_id,
                        minimum_peer_count,
                        metric_configs,
                    ),
                    "sample_status": self._sample_status(metrics),
                    "metric_window": window,
                    "professional_score_source": "fund_evaluation_batch_score",
                    "metrics": metrics,
                }
        return results

    def build_peer_statistics(
        self,
        wind_code: str,
        window: str = "1y",
        target_context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """统计同类可比分和维度分布，只在已确认的同类组内横向比较。"""
        target, peer_funds, peer_group_source = self._peer_universe(wind_code, target_context)
        target_id = target.get("wind_code") or wind_code
        peer_codes = [fund["wind_code"] for fund in peer_funds if fund.get("wind_code")]
        preloaded_panels = None
        if target_context and target_context.get("metric_panel") is not None:
            preloaded_panels = {target_id: target_context["metric_panel"]}
        metric_map = self._metric_map(peer_codes, peer_funds, preloaded_panels)
        target_profile = target.get("research_profile") or {}
        classification = target.get("classification") or self.classification_service.classify(target, target_profile)
        profile_key = classification.get("evaluation_profile_key")
        minimum = self._minimum_peer_count(classification.get("minimum_peer_count"))
        detail_map = self._fast_peer_score_detail_map(
            peer_codes,
            metric_map,
            window,
            profile_key,
            peer_funds,
        )
        valid_scores = [
            (code, self._to_float(detail.get("overall_score")))
            for code, detail in detail_map.items()
            if self._to_float(detail.get("overall_score")) is not None
        ]
        score_values = [value for _, value in valid_scores]
        ranking, unscored = self._score_ranking(
            peer_funds,
            detail_map,
            metric_map,
            metric_configs=self._peer_metric_configs(profile_key),
            window=window,
            target_id=target_id,
        )
        current_position = self._rank_metric(
            target_id=target_id,
            values=valid_scores,
            higher_is_better=True,
            metric_name="professional_score",
            label=f"{self._window_label(window)}同类可比评分",
            unit="score",
            minimum_peer_count=minimum,
            metric_window=window,
            required_for_sample=False,
            source_metric_names=["category_specific_peer_metric_proxy"],
        )
        status = "sufficient" if len(score_values) >= minimum else (
            "insufficient_peer_sample" if score_values else "unavailable"
        )
        return {
            "status": status,
            "target_id": target_id,
            "metric_window": window,
            "peer_group": classification.get("peer_group") or target_profile.get("peer_group"),
            "peer_group_id": classification.get("peer_group_id"),
            "primary_benchmark": classification.get("primary_benchmark") or target_profile.get("primary_benchmark"),
            "peer_group_source": peer_group_source,
            "evaluation_profile_key": profile_key,
            "methodology_version": getattr(
                getattr(self.scoring_service, "methodology", None),
                "PEER_METHODOLOGY_VERSION",
                "category_peer_percentiles_v4",
            ),
            "score_basis": "category_specific_peer_metric_proxy",
            "classified_peer_count": len(peer_codes),
            "scored_peer_count": len(score_values),
            "minimum_peer_count": minimum,
            "coverage_rate": round(len(score_values) / len(peer_codes) * 100, 2) if peer_codes else 0.0,
            "summary": self._score_summary(score_values),
            "distribution": self._score_distribution(score_values),
            "dimensions": self._dimension_statistics(detail_map, target_id, minimum),
            "ranking": ranking,
            "unscored_peer_count": len(unscored),
            "unscored_summary": self._unscored_summary(unscored),
            "unscored": unscored[:20],
            "current": {
                "score": current_position.get("value"),
                "rank": current_position.get("rank"),
                "peer_count": current_position.get("peer_count"),
                "percentile": current_position.get("percentile"),
                "sample_status": current_position.get("sample_status"),
            },
            "boundary": "仅比较同一分类、同一评价窗口下的可比量化指标；不跨类别排名，不构成投资建议。",
        }

    def build_comparison_matrix(self, wind_codes: List[str], window: str = "1y") -> Dict[str, Any]:
        codes = []
        for code in wind_codes:
            normalized = str(code).strip()
            if normalized and normalized not in codes:
                codes.append(normalized)
        if len(codes) < 2:
            raise ValueError("至少需要两只基金进行对比")
        if len(codes) > 10:
            raise ValueError("单次最多对比 10 只基金")

        from repositories import get_metric_snapshot_repo

        fund_repo = self._get_fund_repo()
        profile_repo = self._get_profile_repo()
        metric_repo = get_metric_snapshot_repo()

        funds = []
        percentile_map = {}
        for code in codes:
            fund = fund_repo.get_fund_by_identifier(code)
            if not fund:
                continue
            wind_code = fund.get("wind_code")
            profile = profile_repo.get_profile(wind_code) or {}
            panel = self._metrics_by_window(metric_repo.get_latest_panel("fund", wind_code))
            scoring = self._safe_score(wind_code)
            percentiles = self.build_peer_percentiles(wind_code, window=window)
            classification = percentiles.get("classification") or scoring.get("classification") or {}
            percentile_map[wind_code] = percentiles
            funds.append({
                "wind_code": wind_code,
                "name": fund.get("name"),
                "type": fund.get("type"),
                "peer_group": classification.get("peer_group") or profile.get("peer_group"),
                "primary_benchmark": classification.get("primary_benchmark") or profile.get("primary_benchmark"),
                "peer_count": percentiles.get("peer_count"),
                "metrics": panel.get(window, {}),
                "professional_score": scoring.get("overall_score"),
                "professional_grade": scoring.get("overall_grade"),
                "peer_percentiles": percentiles.get("metrics", {}),
            })

        if len(funds) < 2:
            raise ValueError("可用基金少于两只，无法生成对比矩阵")

        rows = [self._matrix_row(config, funds, window) for config in self.METRIC_CONFIGS]
        rows.append(self._matrix_row({
            "metric_name": "professional_score",
            "label": "专业综合评分",
            "unit": "score",
            "higher_is_better": True,
            "source": "professional_scoring",
        }, funds, window))
        observations = self._evaluation_observations(funds, rows)

        return {
            "metric_window": window,
            "funds": [
                {
                    "wind_code": fund["wind_code"],
                    "name": fund["name"],
                    "type": fund["type"],
                    "peer_group": fund["peer_group"],
                    "primary_benchmark": fund["primary_benchmark"],
                    "peer_count": fund["peer_count"],
                    "professional_score": fund["professional_score"],
                    "professional_grade": fund["professional_grade"],
                }
                for fund in funds
            ],
            "matrix_rows": rows,
            "evaluation_observations": observations,
            # 兼容旧前端字段；内容只描述评价事实，不输出候选、观察池或尽调处置。
            "recommendations": observations,
            "product_scope": {
                "fund_evaluation": "core",
                "investment_decision": "excluded",
            },
        }

    def _peer_universe(
        self,
        wind_code: str,
        target_context: Optional[Dict[str, Any]] = None,
    ) -> Tuple[Dict[str, Any], List[Dict[str, Any]], str]:
        fund_repo = self._get_fund_repo()
        profile_repo = self._get_profile_repo()
        context = target_context or {}
        target = dict(context.get("fund") or fund_repo.get_fund_by_identifier(wind_code) or {"wind_code": wind_code})
        target_code = target.get("wind_code") or wind_code
        target_profile = context.get("profile") or profile_repo.get_profile(target_code) or {}
        target["research_profile"] = target_profile
        standardized_context = context.get("standardized_classification")
        if standardized_context is None:
            standardized_context = self._get_classification_adapter().get_classification_context(target_code)
        target["standardized_classification"] = standardized_context
        classification = context.get("classification") or self.classification_service.classify(
            target,
            target_profile,
            standardized_context,
        )
        target["classification"] = classification

        if standardized_context.get("status") == "resolved":
            peer_group_id = classification.get("peer_group_id")
            if classification.get("status") == "classified" and peer_group_id:
                peers = self._get_classification_adapter().list_peer_funds(
                    peer_group_id,
                    target_wind_code=target_code,
                    limit=self.PEER_UNIVERSE_LIMIT,
                )
                source = "standardized_peer_group_membership"
            else:
                peers = []
                source = "standardized_peer_group_missing"
        else:
            peer_group = target_profile.get("peer_group")
            peers = self._query_peer_funds_by_profile(peer_group) if peer_group else []
            source = "research_profile_peer_group"

            if len(peers) < self.MIN_VALID_PEERS:
                compatible_types = classification.get("compatible_fund_types") or []
                if classification.get("status") == "classified" and compatible_types:
                    peers = self._query_peer_funds_by_types(compatible_types)
                    source = "classification_fund_type_fallback"
                else:
                    peers = []
                    source = "classification_insufficient_evidence"

        if not any(fund.get("wind_code") == target_code for fund in peers):
            peers.append(target)

        profile_map = profile_repo.list_profiles([fund.get("wind_code") for fund in peers if fund.get("wind_code")])
        for fund in peers:
            fund["research_profile"] = profile_map.get(fund.get("wind_code"), {})

        return target, peers, source

    def _get_classification_adapter(self):
        if self._classification_adapter is None:
            from repositories import get_fund_classification_repo

            self._classification_adapter = get_fund_classification_repo()
        return self._classification_adapter

    def _query_peer_funds_by_profile(self, peer_group: str) -> List[Dict[str, Any]]:
        if not peer_group:
            return []
        from sqlalchemy import text

        sql = f"""
            SELECT f.*
            FROM funds f
            JOIN fund_research_profiles p ON p.wind_code = f.wind_code
            WHERE p.peer_group = :peer_group
              AND ({active_fund_sql('f')})
            ORDER BY f.wind_code ASC
            LIMIT 10000
        """
        with self._get_fund_repo().engine.connect() as conn:
            rows = conn.execute(text(sql), {"peer_group": peer_group}).fetchall()
        return [dict(row._mapping) for row in rows]

    def _query_peer_funds_by_types(self, fund_types: List[str]) -> List[Dict[str, Any]]:
        normalized_types = [str(item).strip() for item in fund_types if str(item or "").strip()]
        if not normalized_types:
            return []
        from sqlalchemy import text

        sql = f"""
            SELECT f.*
            FROM funds f
            WHERE f.type = ANY(:fund_types)
              AND ({active_fund_sql('f')})
            ORDER BY f.wind_code ASC
            LIMIT 10000
        """
        with self._get_fund_repo().engine.connect() as conn:
            rows = conn.execute(text(sql), {"fund_types": normalized_types}).fetchall()
        return [dict(row._mapping) for row in rows]

    def _get_fund_repo(self):
        if self._fund_repo_adapter is None:
            from repositories import get_fund_repo

            self._fund_repo_adapter = get_fund_repo()
        return self._fund_repo_adapter

    def _get_profile_repo(self):
        if self._profile_repo_adapter is None:
            from repositories import get_research_profile_repo

            self._profile_repo_adapter = get_research_profile_repo()
        return self._profile_repo_adapter

    def _metric_map(
        self,
        wind_codes: List[str],
        fund_rows: Optional[List[Dict[str, Any]]] = None,
        preloaded_panels: Optional[Dict[str, List[Dict[str, Any]]]] = None,
    ) -> Dict[str, Dict[str, Dict[str, float]]]:
        from repositories import get_metric_snapshot_repo

        repo = get_metric_snapshot_repo()
        loaded_panels = preloaded_panels or {}
        missing_codes = [code for code in wind_codes if code not in loaded_panels]
        batch_panels = repo.get_latest_panels("fund", missing_codes) if missing_codes else {}
        funds_by_code = {
            fund.get("wind_code"): fund
            for fund in (fund_rows or [])
            if fund.get("wind_code")
        }
        metric_map = {}
        for code in wind_codes:
            metrics = self._metrics_by_window(loaded_panels.get(code, batch_panels.get(code, [])))
            fund = funds_by_code.get(code)
            if fund and hasattr(self.scoring_service, "metric_facts_from_fund"):
                for window, fallback_metrics in self.scoring_service.metric_facts_from_fund(fund).items():
                    target = metrics.setdefault(window, {})
                    for metric_name, value in fallback_metrics.items():
                        if target.get(metric_name) is None and value is not None:
                            target[metric_name] = value
            metric_map[code] = metrics
        return metric_map

    def _metrics_by_window(self, panel: List[Dict[str, Any]]) -> Dict[str, Dict[str, float]]:
        metrics: Dict[str, Dict[str, float]] = {}
        for item in panel:
            window = item.get("metric_window") or "latest"
            metric_name = item.get("metric_name")
            value = self._to_float(item.get("metric_value"))
            if metric_name and value is not None:
                metrics.setdefault(window, {})[metric_name] = value
        return metrics

    def _scoring_map(self, wind_codes: List[str]) -> Dict[str, Dict[str, Any]]:
        return {code: self._safe_score(code) for code in wind_codes}

    def _fast_peer_score_map(
        self,
        peer_codes: List[str],
        metric_map: Dict[str, Dict[str, Dict[str, float]]],
        window: str,
        evaluation_profile_key: Optional[str],
        peer_funds: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Dict[str, Any]]:
        return {
            code: {"overall_score": detail.get("overall_score")}
            for code, detail in self._fast_peer_score_detail_map(
                peer_codes,
                metric_map,
                window,
                evaluation_profile_key,
                peer_funds,
            ).items()
        }

    def _fast_peer_score_detail_map(
        self,
        peer_codes: List[str],
        metric_map: Dict[str, Dict[str, Dict[str, float]]],
        window: str,
        evaluation_profile_key: Optional[str],
        peer_funds: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Dict[str, Any]]:
        results = {}
        fund_map = {
            str(fund.get("wind_code") or ""): fund
            for fund in (peer_funds or [])
            if fund.get("wind_code")
        }
        for code in peer_codes:
            if not self._window_history_ready(fund_map.get(code, {}), window):
                results[code] = {
                    "status": "insufficient_history",
                    "overall_score": None,
                    "dimension_scores": {},
                }
                continue
            metrics = {
                **metric_map.get(code, {}).get("latest", {}),
                **metric_map.get(code, {}).get(window, {}),
            }
            if hasattr(self.scoring_service, "score_peer_details"):
                results[code] = self.scoring_service.score_peer_details(
                    evaluation_profile_key or "",
                    metrics,
                )
            else:
                results[code] = {
                    "overall_score": self._fast_peer_score(metrics, evaluation_profile_key),
                    "dimension_scores": {},
                }
        return results

    @staticmethod
    def _window_history_ready(fund: Dict[str, Any], window: str) -> bool:
        establishment = fund.get("establishment_date")
        if not establishment:
            return True
        try:
            established_on = date.fromisoformat(str(establishment)[:10])
        except ValueError:
            return True
        required_days = {"6m": 183, "1y": 365, "3y": 1095}.get(window)
        return required_days is None or (date.today() - established_on).days >= required_days

    @staticmethod
    def _requires_selected_window(config: Dict[str, Any]) -> bool:
        return any(window == "selected" for window, _ in (config.get("paths") or []))

    def _fast_peer_score(
        self,
        metrics: Dict[str, Any],
        evaluation_profile_key: Optional[str],
    ) -> Optional[float]:
        return self.scoring_service.score_peer_metrics(evaluation_profile_key or "", metrics)

    def _peer_metric_configs(self, evaluation_profile_key: Optional[str]) -> List[Dict[str, Any]]:
        methodology = getattr(self.scoring_service, "methodology", None)
        if methodology is None or not hasattr(methodology, "peer_metric_configs"):
            return [
                {
                    **config,
                    "paths": [("selected", config["metric_name"])],
                    "required_for_sample": True,
                }
                for config in self.METRIC_CONFIGS
            ]
        return methodology.peer_metric_configs(evaluation_profile_key or "")

    def _peer_metric_value(
        self,
        panel: Dict[str, Dict[str, float]],
        config: Dict[str, Any],
        selected_window: str,
    ) -> Optional[float]:
        value = None
        for configured_window, metric_name in config.get("paths") or []:
            effective_window = selected_window if configured_window == "selected" else configured_window
            value = self._to_float(panel.get(effective_window, {}).get(metric_name))
            if value is not None:
                break
        if value is not None and config.get("transform") == "absolute":
            value = abs(value)
        valid_range = config.get("valid_range")
        if value is not None and valid_range:
            lower, upper = valid_range
            if value < lower or value > upper:
                return None
        return value

    @staticmethod
    def _metric_window_label(config: Dict[str, Any], selected_window: str) -> str:
        windows = []
        for configured_window, _ in config.get("paths") or []:
            effective_window = selected_window if configured_window == "selected" else configured_window
            if effective_window not in windows:
                windows.append(effective_window)
        return "/".join(windows) if windows else selected_window

    @staticmethod
    def _window_metric_label(label: str, selected_window: str) -> str:
        window_label = PeerComparisonService._window_label(selected_window)
        normalized = str(label or "")
        return f"{window_label}{normalized[3:]}" if normalized.startswith("1Y ") else normalized

    @staticmethod
    def _window_label(selected_window: str) -> str:
        return {"6m": "近 6 月", "1y": "近 1 年", "3y": "近 3 年"}.get(
            selected_window,
            selected_window,
        )

    def _safe_score(self, wind_code: str) -> Dict[str, Any]:
        try:
            return self.scoring_service.score_fund(wind_code)
        except Exception:
            return {"overall_score": None, "overall_grade": None}

    def _rank_metric_map(
        self,
        values: List[Tuple[str, Optional[float]]],
        higher_is_better: bool,
        metric_name: str,
        label: str,
        unit: str,
        minimum_peer_count: Optional[int] = None,
        metric_window: Optional[str] = None,
        required_for_sample: bool = True,
        source_metric_names: Optional[List[str]] = None,
    ) -> Dict[str, Dict[str, Any]]:
        """一次排序生成整组分位，避免为每只基金重复排序。"""
        minimum = self._minimum_peer_count(minimum_peer_count)
        valid = [(code, value) for code, value in values if value is not None]
        shared = {
            "metric_name": metric_name,
            "label": label,
            "minimum_peer_count": minimum,
            "unit": unit,
            "direction": "higher" if higher_is_better else "lower",
            "metric_window": metric_window,
            "required_for_sample": required_for_sample,
            "source_metric_names": source_metric_names or [metric_name],
        }
        if len(valid) < minimum:
            return {
                code: {
                    **shared,
                    "value": None if value is None else round(value, 6),
                    "percentile": None,
                    "rank": None,
                    "peer_count": len(valid),
                    "sample_status": "insufficient_peer_sample",
                }
                for code, value in values
            }

        ordered = sorted(valid, key=lambda item: item[1], reverse=higher_is_better)
        peer_count = len(ordered)
        ranks = {code: rank for rank, (code, _) in enumerate(ordered, start=1)}
        return {
            code: {
                **shared,
                "value": None if value is None else round(value, 6),
                "percentile": (
                    None
                    if value is None
                    else round((peer_count - ranks[code]) / (peer_count - 1) * 100, 2)
                ),
                "rank": None if value is None else ranks[code],
                "peer_count": peer_count,
                "sample_status": "target_metric_missing" if value is None else "sufficient",
            }
            for code, value in values
        }

    def _rank_metric(
        self,
        target_id: str,
        values: List[Tuple[str, Optional[float]]],
        higher_is_better: bool,
        metric_name: str,
        label: str,
        unit: str,
        minimum_peer_count: Optional[int] = None,
        metric_window: Optional[str] = None,
        required_for_sample: bool = True,
        source_metric_names: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        minimum = self._minimum_peer_count(minimum_peer_count)
        valid = [(code, value) for code, value in values if value is not None]
        target_value = next((value for code, value in valid if code == target_id), None)
        if len(valid) < minimum:
            return {
                "metric_name": metric_name,
                "label": label,
                "value": None if target_value is None else round(target_value, 6),
                "percentile": None,
                "rank": None,
                "peer_count": len(valid),
                "minimum_peer_count": minimum,
                "sample_status": "insufficient_peer_sample",
                "unit": unit,
                "direction": "higher" if higher_is_better else "lower",
                "metric_window": metric_window,
                "required_for_sample": required_for_sample,
                "source_metric_names": source_metric_names or [metric_name],
            }
        if target_value is None:
            return {
                "metric_name": metric_name,
                "label": label,
                "value": None,
                "percentile": None,
                "rank": None,
                "peer_count": len(valid),
                "minimum_peer_count": minimum,
                "sample_status": "target_metric_missing",
                "unit": unit,
                "direction": "higher" if higher_is_better else "lower",
                "metric_window": metric_window,
                "required_for_sample": required_for_sample,
                "source_metric_names": source_metric_names or [metric_name],
            }
        sorted_values = sorted(valid, key=lambda item: item[1], reverse=higher_is_better)
        rank = next(index + 1 for index, item in enumerate(sorted_values) if item[0] == target_id)
        peer_count = len(sorted_values)
        percentile = (peer_count - rank) / (peer_count - 1) * 100
        return {
            "metric_name": metric_name,
            "label": label,
            "value": round(target_value, 6),
            "percentile": round(percentile, 2),
            "rank": rank,
            "peer_count": peer_count,
            "minimum_peer_count": minimum,
            "sample_status": "sufficient",
            "unit": unit,
            "direction": "higher" if higher_is_better else "lower",
            "metric_window": metric_window,
            "required_for_sample": required_for_sample,
            "source_metric_names": source_metric_names or [metric_name],
        }

    def _sample_status(self, metrics: Dict[str, Any]) -> str:
        required_metrics = [
            metric
            for metric in metrics.values()
            if isinstance(metric, dict) and metric.get("required_for_sample", True)
        ]
        if not required_metrics:
            return "unavailable"
        metric_statuses = {metric.get("sample_status") for metric in required_metrics}
        if "insufficient_peer_sample" in metric_statuses:
            return "insufficient_peer_sample"
        if "target_metric_missing" in metric_statuses:
            return "target_metric_missing"
        if metric_statuses == {"sufficient"}:
            return "sufficient"
        return "unavailable"

    def _metric_coverage(self, metrics: Dict[str, Any]) -> Dict[str, int]:
        return {
            metric_name: int(metric.get("peer_count") or 0)
            for metric_name, metric in metrics.items()
            if isinstance(metric, dict)
        }

    def _valid_metric_peer_count(self, metrics: Dict[str, Any]) -> int:
        counts = [
            int(metric.get("peer_count") or 0)
            for metric in metrics.values()
            if isinstance(metric, dict) and metric.get("required_for_sample", True)
        ]
        return min(counts) if counts else 0

    def _usable_metric_count(self, metrics: Dict[str, Any]) -> int:
        return sum(
            1
            for metric in metrics.values()
            if isinstance(metric, dict)
            and metric.get("sample_status") == "sufficient"
            and metric.get("percentile") is not None
        )

    def _insufficient_metric_count(self, metrics: Dict[str, Any]) -> int:
        return sum(
            1
            for metric in metrics.values()
            if isinstance(metric, dict)
            and metric.get("sample_status") in {"insufficient_peer_sample", "target_metric_missing"}
        )

    def _peer_metric_gap(
        self,
        metrics: Dict[str, Any],
        peer_funds: Optional[List[Dict[str, Any]]] = None,
        metric_map: Optional[Dict[str, Dict[str, Dict[str, float]]]] = None,
        window: str = "1y",
        target_id: Optional[str] = None,
        minimum_peer_count: Optional[int] = None,
        metric_configs: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        minimum = self._minimum_peer_count(minimum_peer_count)
        blocking_metrics = []
        required_more_funds = 0
        for metric_name, metric in metrics.items():
            if (
                not isinstance(metric, dict)
                or not metric.get("required_for_sample", True)
                or metric.get("sample_status") != "insufficient_peer_sample"
            ):
                continue
            peer_count = int(metric.get("peer_count") or 0)
            missing_count = max(0, minimum - peer_count)
            required_more_funds = max(required_more_funds, missing_count)
            blocking_metrics.append({
                "metric_name": metric_name,
                "label": metric.get("label") or metric_name,
                "peer_count": peer_count,
                "missing_count": missing_count,
            })
        suggested_funds = self._suggest_metric_sync_funds(
            blocking_metrics,
            peer_funds or [],
            metric_map or {},
            window,
            target_id,
            max(required_more_funds, 5),
            metric_configs or [],
        )
        return {
            "required_more_funds": required_more_funds,
            "blocking_metrics": blocking_metrics,
            "suggested_sync_codes": [fund["wind_code"] for fund in suggested_funds],
            "suggested_sync_funds": suggested_funds,
            "next_action": "sync_peer_nav_and_rolling_metrics" if blocking_metrics else "none",
        }

    def _minimum_peer_count(self, value: Any) -> int:
        try:
            return max(2, int(value))
        except (TypeError, ValueError):
            return self.MIN_VALID_PEERS

    @staticmethod
    def _score_summary(values: List[float]) -> Dict[str, Optional[float]]:
        if not values:
            return {"average": None, "median": None, "highest": None, "lowest": None}
        return {
            "average": round(sum(values) / len(values), 2),
            "median": round(float(median(values)), 2),
            "highest": round(max(values), 2),
            "lowest": round(min(values), 2),
        }

    @staticmethod
    def _score_distribution(values: List[float]) -> List[Dict[str, Any]]:
        ranges = [(0, 20), (20, 40), (40, 60), (60, 80), (80, 100)]
        total = len(values)
        result = []
        for index, (lower, upper) in enumerate(ranges):
            is_last = index == len(ranges) - 1
            count = sum(1 for value in values if lower <= value and (value <= upper if is_last else value < upper))
            result.append({
                "key": f"{lower}_{upper}",
                "label": f"{lower}-{upper}",
                "lower": lower,
                "upper": upper,
                "count": count,
                "percentage": round(count / total * 100, 2) if total else 0.0,
            })
        return result

    def _score_ranking(
        self,
        peer_funds: List[Dict[str, Any]],
        detail_map: Dict[str, Dict[str, Any]],
        metric_map: Dict[str, Dict[str, Dict[str, float]]],
        metric_configs: List[Dict[str, Any]],
        window: str,
        target_id: str,
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """组装同分类、同窗口的评分结果榜单，并显式保留未评分原因。"""
        required_configs = [
            config for config in metric_configs if config.get("required_for_sample", True)
        ]
        fund_map = {
            str(fund.get("wind_code") or ""): fund
            for fund in peer_funds
            if fund.get("wind_code")
        }
        scored: List[Dict[str, Any]] = []
        unscored: List[Dict[str, Any]] = []

        for code, fund in fund_map.items():
            detail = detail_map.get(code) or {}
            score = self._to_float(detail.get("overall_score"))
            evidence = [
                self._metric_evidence(metric_map.get(code, {}), config, window)
                for config in required_configs
            ]
            available_count = sum(1 for item in evidence if item["status"] == "available")
            required_count = len(required_configs)
            coverage = {
                "available_metric_count": available_count,
                "required_metric_count": required_count,
                "coverage_rate": round(available_count / required_count * 100, 2) if required_count else 0.0,
            }
            missing_metrics = [item for item in evidence if item["status"] == "missing"]
            invalid_metrics = [item for item in evidence if item["status"] == "invalid"]
            dimensions = {
                key: round(value, 2)
                for key, item in (detail.get("dimension_scores") or {}).items()
                if (value := self._to_float((item or {}).get("score"))) is not None
            }

            if score is None:
                reason = self._unscored_reason(fund, window, missing_metrics, invalid_metrics)
                unscored.append({
                    "wind_code": code,
                    "name": fund.get("name"),
                    "fund_type": fund.get("type"),
                    "reason": reason,
                    "data_coverage": coverage,
                    "missing_metrics": [item["label"] for item in missing_metrics],
                    "invalid_metrics": [item["label"] for item in invalid_metrics],
                })
                continue

            scored.append({
                "wind_code": code,
                "name": fund.get("name"),
                "fund_type": fund.get("type"),
                "score": round(score, 2),
                "grade": grade_for_score(score),
                "dimension_scores": dimensions,
                "data_coverage": coverage,
                "is_current": code == target_id,
            })

        scored.sort(key=lambda item: (-item["score"], item["wind_code"]))
        peer_count = len(scored)
        for index, item in enumerate(scored, start=1):
            item["rank"] = index
            item["percentile"] = round((peer_count - index) / (peer_count - 1) * 100, 2) if peer_count > 1 else 100.0
        unscored.sort(key=lambda item: (item["reason"], item["wind_code"]))
        return scored, unscored

    def _metric_evidence(
        self,
        panel: Dict[str, Dict[str, float]],
        config: Dict[str, Any],
        selected_window: str,
    ) -> Dict[str, Any]:
        label = str(config.get("label") or config.get("metric_name") or "指标")
        for configured_window, metric_name in config.get("paths") or []:
            effective_window = selected_window if configured_window == "selected" else configured_window
            value = self._to_float(panel.get(effective_window, {}).get(metric_name))
            if value is None:
                continue
            effective_value = abs(value) if config.get("transform") == "absolute" else value
            valid_range = config.get("valid_range")
            if valid_range and not (valid_range[0] <= effective_value <= valid_range[1]):
                return {"status": "invalid", "label": label, "value": effective_value}
            return {"status": "available", "label": label, "value": effective_value}
        return {"status": "missing", "label": label, "value": None}

    @staticmethod
    def _unscored_reason(
        fund: Dict[str, Any],
        window: str,
        missing_metrics: List[Dict[str, Any]],
        invalid_metrics: List[Dict[str, Any]],
    ) -> str:
        establishment = fund.get("establishment_date")
        if establishment:
            try:
                established_on = date.fromisoformat(str(establishment)[:10])
                required_days = {"6m": 183, "1y": 365, "3y": 1095}.get(window, 365)
                if (date.today() - established_on).days < required_days:
                    return "insufficient_history"
            except ValueError:
                pass
        if invalid_metrics:
            return "invalid_metric_range"
        if missing_metrics:
            return "missing_required_metrics"
        return "insufficient_evidence"

    @staticmethod
    def _unscored_summary(items: List[Dict[str, Any]]) -> Dict[str, int]:
        result: Dict[str, int] = {}
        for item in items:
            reason = str(item.get("reason") or "insufficient_evidence")
            result[reason] = result.get(reason, 0) + 1
        return result

    @staticmethod
    def _dimension_statistics(
        detail_map: Dict[str, Dict[str, Any]],
        target_id: str,
        minimum_peer_count: int,
    ) -> List[Dict[str, Any]]:
        dimension_keys = []
        for detail in detail_map.values():
            for key in (detail.get("dimension_scores") or {}).keys():
                if key not in dimension_keys:
                    dimension_keys.append(key)

        result = []
        for key in dimension_keys:
            values = []
            target_score = None
            for code, detail in detail_map.items():
                dimension = (detail.get("dimension_scores") or {}).get(key) or {}
                score = PeerComparisonService._to_float_static(dimension.get("score"))
                if score is None:
                    continue
                values.append(score)
                if code == target_id:
                    target_score = score
            result.append({
                "key": key,
                "average": round(sum(values) / len(values), 2) if values else None,
                "median": round(float(median(values)), 2) if values else None,
                "current_score": round(target_score, 2) if target_score is not None else None,
                "sample_count": len(values),
                "minimum_peer_count": minimum_peer_count,
                "sample_status": "sufficient" if len(values) >= minimum_peer_count else "insufficient_peer_sample",
            })
        return result

    @staticmethod
    def _to_float_static(value: Any) -> Optional[float]:
        try:
            return float(Decimal(str(value))) if value is not None else None
        except Exception:
            return None

    def _suggest_metric_sync_funds(
        self,
        blocking_metrics: List[Dict[str, Any]],
        peer_funds: List[Dict[str, Any]],
        metric_map: Dict[str, Dict[str, Dict[str, float]]],
        window: str,
        target_id: Optional[str],
        limit: int,
        metric_configs: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        if not blocking_metrics:
            return []
        blocking_metric_names = [item["metric_name"] for item in blocking_metrics]
        config_map = {config.get("metric_name"): config for config in metric_configs}
        candidates = []
        for fund in peer_funds:
            code = fund.get("wind_code")
            if not code or code == target_id:
                continue
            raw_data = fund.get("raw_data") if isinstance(fund.get("raw_data"), dict) else {}
            ranking_status = (
                raw_data.get("ranking_metrics", {}).get("status")
                if isinstance(raw_data.get("ranking_metrics"), dict)
                else None
            )
            if ranking_status in {"nav_unavailable", "invalid_nav", "insufficient_metric_history"}:
                continue
            if ranking_status == "synced" and int(
                raw_data.get("ranking_metrics", {}).get("nav_points") or 0
            ) < 151:
                continue
            missing_metrics = [
                metric_name
                for metric_name in blocking_metric_names
                if self._peer_metric_value(
                    metric_map.get(code, {}),
                    config_map.get(metric_name, {
                        "metric_name": metric_name,
                        "paths": [("selected", metric_name)],
                    }),
                    window,
                ) is None
            ]
            if not missing_metrics:
                continue
            candidates.append({
                "wind_code": code,
                "name": fund.get("name"),
                "missing_metric_count": len(missing_metrics),
                "missing_metrics": missing_metrics,
            })
        candidates.sort(key=lambda item: (-item["missing_metric_count"], item["wind_code"]))
        return candidates[: max(0, min(limit, 10))]

    def _matrix_row(self, config: Dict[str, Any], funds: List[Dict[str, Any]], window: str) -> Dict[str, Any]:
        metric_name = config["metric_name"]
        values = {}
        ranking_values = []
        for fund in funds:
            if metric_name == "professional_score":
                raw_value = self._to_float(fund.get("professional_score"))
            else:
                raw_value = self._to_float(fund.get("metrics", {}).get(metric_name))
            percentile = fund.get("peer_percentiles", {}).get(metric_name, {}).get("percentile")
            values[fund["wind_code"]] = {
                "value": None if raw_value is None else round(raw_value, 6),
                "display": self._display_value(raw_value, config["unit"]),
                "peer_percentile": percentile,
            }
            ranking_score = percentile if percentile is not None else raw_value
            if ranking_score is not None:
                ranking_values.append((fund["wind_code"], ranking_score))

        best_code = None
        if ranking_values:
            best_code = sorted(ranking_values, key=lambda item: item[1], reverse=True)[0][0]

        return {
            "metric_name": metric_name,
            "label": config["label"],
            "unit": config["unit"],
            "direction": "higher" if config["higher_is_better"] else "lower",
            "window": window if metric_name != "professional_score" else None,
            "best_code": best_code,
            "values": values,
        }

    def _evaluation_observations(self, funds: List[Dict[str, Any]], rows: List[Dict[str, Any]]) -> List[str]:
        observations = []
        score_row = next((row for row in rows if row["metric_name"] == "professional_score"), None)
        if score_row and score_row.get("best_code"):
            winner = next((fund for fund in funds if fund["wind_code"] == score_row["best_code"]), None)
            if winner:
                observations.append(f"{winner['name']} 在当前分类口径的专业综合评分中相对较高。")
        drawdown_row = next((row for row in rows if row["metric_name"] == "max_drawdown"), None)
        if drawdown_row and drawdown_row.get("best_code"):
            winner = next((fund for fund in funds if fund["wind_code"] == drawdown_row["best_code"]), None)
            if winner:
                observations.append(f"{winner['name']} 的回撤控制在本次同类对比中相对较优。")
        peer_groups = {fund.get("peer_group") for fund in funds if fund.get("peer_group")}
        if len(peer_groups) > 1:
            observations.append("本次对比跨越多个同类组，绝对指标不应被解释为同一评价口径下的排名。")
        if not observations:
            observations.append("本次同类评价没有形成明显的单项相对优势。")
        return observations

    def _display_value(self, value: Optional[float], unit: str) -> str:
        if value is None:
            return "暂无"
        if unit == "percent":
            return f"{value * 100:.2f}%"
        if unit == "score":
            return f"{value:.1f}"
        return f"{value:.2f}"

    def _to_float(self, value: Any) -> Optional[float]:
        if value is None:
            return None
        try:
            return float(Decimal(str(value)))
        except Exception:
            return None
