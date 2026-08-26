"""面向普通用户的分类内候选基金组。"""
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

from services.fund_evaluation_service import FundEvaluationService
from services.fund_research_snapshot_service import FundResearchSnapshotService
from services.manager_tenure_coverage import build_manager_tenure_coverage
from services.professional_scoring_service import ProfessionalScoringService


class FundRecommendationService:
    """扫描完整同类组，返回不超过十只证据充分的候选基金。"""

    METHODOLOGY_VERSION = "fund_candidate_group_v6"
    MAX_CANDIDATES = 10
    PEER_UNIVERSE_LIMIT = 10000

    STYLE_ALIASES: Dict[str, Tuple[str, ...]] = FundResearchSnapshotService.STYLE_LABEL_ALIASES

    STYLE_DISPLAY_ORDER = (
        "大盘", "中盘", "小盘", "中小盘", "宽基", "大盘成长", "成长", "价值", "均衡",
        "质量", "红利", "低波稳健", "行业主题", "行业轮动", "量化", "指数增强", "固收+",
        "底层高集中", "底层中等集中", "底层较分散",
        "底层权益基金主导", "底层固收基金主导", "底层混合基金主导",
        "底层货币基金主导", "底层 FOF 主导", "底层跨市场基金主导",
        "底层 REITs 主导", "底层商品基金主导", "底层指数基金主导",
        "利率债", "金融债", "信用债", "可转债", "地方政府债", "信用利率均衡",
        "高等级信用", "中低等级信用", "信用", "利率", "低换手", "高换手",
    )

    PEER_GROUP_STYLE_RULES: Dict[str, Tuple[str, ...]] = FundResearchSnapshotService.PEER_GROUP_STYLE_RULES
    BENCHMARK_STYLE_RULES: Dict[str, Tuple[str, ...]] = FundResearchSnapshotService.BENCHMARK_STYLE_RULES

    def __init__(
        self,
        classification_repo: Optional[Any] = None,
        metric_repo: Optional[Any] = None,
        profile_repo: Optional[Any] = None,
        holding_style_repo: Optional[Any] = None,
        bond_holding_repo: Optional[Any] = None,
        fof_holding_repo: Optional[Any] = None,
        scoring_service: Optional[ProfessionalScoringService] = None,
        evaluation_service: Optional[FundEvaluationService] = None,
        manager_repo: Optional[Any] = None,
    ):
        self._classification_repo = classification_repo
        self._metric_repo = metric_repo
        self._profile_repo = profile_repo
        self._holding_style_repo = holding_style_repo
        self._bond_holding_repo = bond_holding_repo
        self._fof_holding_repo = fof_holding_repo
        self.scoring_service = scoring_service or (
            evaluation_service.scoring_service if evaluation_service is not None else ProfessionalScoringService()
        )
        self.evaluation_service = evaluation_service or FundEvaluationService(
            scoring_service=self.scoring_service,
            manager_repo=manager_repo,
        )

    def build_candidate_group(
        self,
        peer_group: str,
        style: Optional[str] = None,
        limit: int = MAX_CANDIDATES,
    ) -> Dict[str, Any]:
        normalized_group = str(peer_group or "").strip()
        normalized_style = str(style or "").strip()
        if not normalized_group:
            raise ValueError("请先选择基金类别")

        rows = self.classification_repo.list_recommendation_funds(
            normalized_group,
            limit=self.PEER_UNIVERSE_LIMIT,
        )
        exact_rows = [row for row in rows if self._belongs_to_group(row, normalized_group)]
        minimum_peer_count = self._minimum_peer_count(exact_rows)
        if minimum_peer_count and len(exact_rows) < minimum_peer_count:
            return {
                "peer_group": normalized_group,
                "style": normalized_style or None,
                "peer_universe_count": len(exact_rows),
                "minimum_peer_count": minimum_peer_count,
                "evidence_eligible_count": 0,
                "long_term_ready_count": 0,
                "style_matched_count": 0,
                "excluded_count": len(exact_rows),
                "excluded_reason_counts": {"peer_sample_insufficient": len(exact_rows)},
                "available_styles": [],
                "available_style_options": [],
                "limit": max(1, min(int(limit), self.MAX_CANDIDATES)),
                "returned": 0,
                "candidates": [],
                "methodology_version": self.METHODOLOGY_VERSION,
                "source": "full_peer_group_category_evaluation",
                "scope": {
                    "fund_classification": "required",
                    "category_evaluation": "required",
                    "explanatory_attribution": "optional",
                },
            }
        codes = [str(row.get("wind_code") or "").strip() for row in exact_rows]
        codes = [code for code in codes if code]
        panels = self.metric_repo.get_latest_panels("fund", codes)
        profiles = self._profiles_with_style_suggestions(codes, exact_rows)
        evaluations = self.evaluation_service.evaluate_peer_group_from_inputs(
            exact_rows,
            profiles,
            panels,
            window="1y",
        )

        eligible: List[Dict[str, Any]] = []
        excluded_reason_counts: Dict[str, int] = {}
        for row in exact_rows:
            code = str(row.get("wind_code") or "").strip()
            profile = profiles.get(code) or {}
            panel = panels.get(code) or []
            candidate, reason = self._candidate_from_evaluation(
                row,
                profile,
                panel,
                evaluations.get(code) or {},
            )
            if candidate is None:
                excluded_reason_counts[reason] = excluded_reason_counts.get(reason, 0) + 1
                continue
            eligible.append(candidate)

        if minimum_peer_count and len(eligible) < minimum_peer_count:
            excluded_reason_counts["peer_evaluation_sample_insufficient"] = (
                minimum_peer_count - len(eligible)
            )
            return {
                "peer_group": normalized_group,
                "style": normalized_style or None,
                "peer_universe_count": len(exact_rows),
                "minimum_peer_count": minimum_peer_count,
                "evidence_eligible_count": len(eligible),
                "long_term_ready_count": 0,
                "style_matched_count": 0,
                "excluded_count": len(exact_rows),
                "excluded_reason_counts": excluded_reason_counts,
                "available_styles": [],
                "available_style_options": [],
                "limit": max(1, min(int(limit), self.MAX_CANDIDATES)),
                "returned": 0,
                "candidates": [],
                "methodology_version": self.METHODOLOGY_VERSION,
                "source": "full_peer_group_category_evaluation",
                "scope": {
                    "fund_classification": "required",
                    "category_evaluation": "required",
                    "explanatory_attribution": "optional",
                },
            }

        available_style_options = self._available_style_options(eligible)
        available_styles = [item["value"] for item in available_style_options]
        styled = [
            candidate
            for candidate in eligible
            if self._matches_style(candidate, normalized_style)
        ]
        styled.sort(key=self._candidate_sort_key)
        long_term_ready_count = sum(
            1
            for candidate in styled
            if FundResearchSnapshotService.project_multi_period_evidence(
                candidate.get("rolling_metrics") or {},
                str(candidate.get("_candidate_profile_key") or ""),
            ).get("status") == "long_term_ready"
        )

        candidate_limit = max(1, min(int(limit), self.MAX_CANDIDATES))
        candidates = styled[:candidate_limit]
        for candidate in candidates:
            candidate["_selected_style"] = normalized_style
            alternatives = self._alternative_candidates(candidate, styled)
            candidate["recommendation_evidence"] = {
                **self._recommendation_evidence(candidate),
                "alternatives": alternatives,
            }

        return {
            "peer_group": normalized_group,
            "style": normalized_style or None,
            "peer_universe_count": len(exact_rows),
            "evidence_eligible_count": len(eligible),
            "long_term_ready_count": long_term_ready_count,
            "style_matched_count": len(styled),
            "excluded_count": len(exact_rows) - len(eligible),
            "excluded_reason_counts": excluded_reason_counts,
            "available_styles": available_styles,
            "available_style_options": available_style_options,
            "limit": candidate_limit,
            "returned": len(candidates),
            "candidates": candidates,
            "methodology_version": self.METHODOLOGY_VERSION,
            "source": "full_peer_group_category_evaluation",
            "scope": {
                "fund_classification": "required",
                "category_evaluation": "required",
                "explanatory_attribution": "optional",
            },
        }

    def build_coverage_report(self, limit: int = 100) -> Dict[str, Any]:
        """按标准同类组检查分类、评价指标、风格标签和推荐准备度。"""
        if hasattr(self.classification_repo, "list_recommendation_coverage_summary"):
            return self._build_aggregated_coverage_report(limit)

        inventory = self.classification_repo.list_peer_group_coverage_inventory(limit=limit)
        group_rows: Dict[str, List[Dict[str, Any]]] = {}
        all_codes: List[str] = []
        for group in inventory:
            group_key = str(group.get("key") or group.get("name") or "").strip()
            rows = self.classification_repo.list_recommendation_funds(
                group_key,
                limit=self.PEER_UNIVERSE_LIMIT,
            ) if group_key else []
            exact_rows = [row for row in rows if self._belongs_to_group(row, group_key)]
            group_rows[group_key] = exact_rows
            all_codes.extend(str(row.get("wind_code") or "").strip() for row in exact_rows)

        normalized_codes = list(dict.fromkeys(code for code in all_codes if code))
        panels = self.metric_repo.get_latest_panels("fund", normalized_codes)
        all_rows = [row for rows in group_rows.values() for row in rows]
        profiles = self._profiles_with_style_suggestions(normalized_codes, all_rows)
        group_evaluations = {
            group_key: self.evaluation_service.evaluate_peer_group_from_inputs(
                rows,
                profiles,
                panels,
                window="1y",
            )
            for group_key, rows in group_rows.items()
            if rows
        }
        groups: List[Dict[str, Any]] = []
        for group in inventory:
            group_key = str(group.get("key") or group.get("name") or "").strip()
            rows = group_rows.get(group_key) or []
            minimum_peer_count = max(1, int(group.get("minimum_peer_count") or self._minimum_peer_count(rows) or 1))
            method_ready_count = 0
            metric_ready_count = 0
            style_ready_count = 0
            reason_counts: Dict[str, int] = {}
            suggested_sync_codes: List[str] = []

            for row in rows:
                code = str(row.get("wind_code") or "").strip()
                profile = profiles.get(code) or {}
                evaluation_item = (group_evaluations.get(group_key) or {}).get(code) or {}
                scoring = evaluation_item.get("scoring") or {}
                profile_key = str(scoring.get("fund_type_profile") or "")
                metric_configs = self.scoring_service.methodology.peer_metric_configs(profile_key) if profile_key else []
                if profile_key and metric_configs:
                    method_ready_count += 1
                candidate, reason = self._candidate_from_evaluation(
                    row,
                    profile,
                    panels.get(code) or [],
                    evaluation_item,
                )
                if candidate is None:
                    reason_counts[reason] = reason_counts.get(reason, 0) + 1
                    if reason == "required_category_evidence_missing" and code:
                        suggested_sync_codes.append(code)
                    continue
                metric_ready_count += 1
                if self._style_items(profile):
                    style_ready_count += 1

            database_fund_count = len(rows)
            classified_sample_ready = database_fund_count >= minimum_peer_count
            sample_ready = classified_sample_ready and metric_ready_count >= minimum_peer_count
            recommendation_ready_count = metric_ready_count if sample_ready else 0
            if not classified_sample_ready and database_fund_count:
                reason_counts["peer_sample_insufficient"] = database_fund_count
            elif not sample_ready and database_fund_count:
                reason_counts["peer_evaluation_sample_insufficient"] = (
                    minimum_peer_count - metric_ready_count
                )
            status = "ready" if recommendation_ready_count > 0 else "partial" if database_fund_count > 0 else "blocked"
            groups.append({
                "id": group.get("id"),
                "key": group_key,
                "name": group.get("name") or group_key,
                "status": status,
                "minimum_peer_count": minimum_peer_count,
                "classified_count": int(group.get("classified_count") or 0),
                "database_fund_count": database_fund_count,
                "evaluation_method_ready_count": method_ready_count,
                "metric_ready_count": metric_ready_count,
                "style_ready_count": style_ready_count,
                "recommendation_ready_count": recommendation_ready_count,
                "missing_reason_counts": reason_counts,
                "suggested_sync_codes": suggested_sync_codes[:10],
            })

        summary = {
            "category_count": len(groups),
            "ready_category_count": sum(1 for group in groups if group["status"] == "ready"),
            "classified_count": sum(group["classified_count"] for group in groups),
            "database_fund_count": sum(group["database_fund_count"] for group in groups),
            "evaluation_method_ready_count": sum(group["evaluation_method_ready_count"] for group in groups),
            "metric_ready_count": sum(group["metric_ready_count"] for group in groups),
            "style_ready_count": sum(group["style_ready_count"] for group in groups),
            "recommendation_ready_count": sum(group["recommendation_ready_count"] for group in groups),
        }
        return {
            "summary": summary,
            "groups": groups,
            "metric_backfill": {
                "command": "npm run funds:backfill-peer-evaluation",
                "source": "tushare.fund_nav",
                "mock_data_allowed": False,
            },
            "methodology_version": self.METHODOLOGY_VERSION,
            "source": "standardized_peer_group_coverage",
        }

    def _build_aggregated_coverage_report(self, limit: int) -> Dict[str, Any]:
        aggregate = self.classification_repo.list_recommendation_coverage_summary(limit=limit)
        groups: List[Dict[str, Any]] = []
        for item in aggregate:
            key = str(item.get("key") or item.get("name") or "").strip()
            database_count = int(item.get("database_fund_count") or 0)
            minimum_peer_count = max(1, int(item.get("minimum_peer_count") or 1))
            evaluated_count = int(item.get("evaluated_fund_count") or 0)
            style_ready_count = int(item.get("style_ready_count") or 0)
            sample_ready = database_count >= minimum_peer_count and evaluated_count >= minimum_peer_count
            missing_reasons: Dict[str, int] = {}
            if database_count < minimum_peer_count and database_count:
                missing_reasons["peer_sample_insufficient"] = minimum_peer_count - database_count
            elif evaluated_count < minimum_peer_count and database_count:
                missing_reasons["peer_evaluation_sample_insufficient"] = minimum_peer_count - evaluated_count
            if database_count > evaluated_count:
                missing_reasons["required_category_evidence_missing"] = database_count - evaluated_count
            groups.append({
                "id": item.get("id"),
                "key": key,
                "name": item.get("name") or key,
                "status": "ready" if sample_ready else "partial" if database_count else "blocked",
                "minimum_peer_count": minimum_peer_count,
                "classified_count": int(item.get("classified_count") or database_count),
                "database_fund_count": database_count,
                "evaluation_method_ready_count": database_count,
                "metric_ready_count": evaluated_count,
                "style_ready_count": style_ready_count,
                "recommendation_ready_count": evaluated_count if sample_ready else 0,
                "missing_reason_counts": missing_reasons,
                "suggested_sync_codes": [],
            })
        summary = {
            "category_count": len(groups),
            "ready_category_count": sum(1 for group in groups if group["status"] == "ready"),
            "classified_count": sum(group["classified_count"] for group in groups),
            "database_fund_count": sum(group["database_fund_count"] for group in groups),
            "evaluation_method_ready_count": sum(group["evaluation_method_ready_count"] for group in groups),
            "metric_ready_count": sum(group["metric_ready_count"] for group in groups),
            "style_ready_count": sum(group["style_ready_count"] for group in groups),
            "recommendation_ready_count": sum(group["recommendation_ready_count"] for group in groups),
        }
        return {
            "summary": summary,
            "groups": groups,
            "metric_backfill": {
                "command": "npm run funds:backfill-peer-evaluation",
                "source": "tushare.fund_nav",
                "mock_data_allowed": False,
            },
            "methodology_version": self.METHODOLOGY_VERSION,
            "source": "standardized_peer_group_coverage_aggregate",
        }

    def build_home_coverage_report(self, limit: int = 100) -> Dict[str, Any]:
        """首页只取数据库聚合结果，避免每次请求重新评价全部基金。"""
        if hasattr(self.classification_repo, "list_recommendation_coverage_summary"):
            evaluation_inventory = self.classification_repo.list_recommendation_coverage_summary(limit=limit)
            coverage_inventory = evaluation_inventory
        else:
            coverage_inventory = self.classification_repo.list_peer_group_coverage_inventory(limit=limit)
            evaluation_inventory = self.classification_repo.list_peer_group_inventory(limit=limit)
        evaluation_by_key = {
            str(item.get("key") or item.get("name") or "").strip(): item
            for item in evaluation_inventory
        }

        groups: List[Dict[str, Any]] = []
        for item in coverage_inventory:
            key = str(item.get("key") or item.get("name") or "").strip()
            evaluation = evaluation_by_key.get(key) or {}
            fund_count = int(item.get("database_fund_count") or 0)
            minimum_peer_count = max(1, int(item.get("minimum_peer_count") or 1))
            evaluated_count = int(evaluation.get("evaluated_fund_count") or 0)
            style_ready_count = int(evaluation.get("style_ready_count") or 0)
            ready = fund_count >= minimum_peer_count and evaluated_count >= minimum_peer_count
            groups.append({
                "id": item.get("id"),
                "key": key,
                "name": item.get("name") or key,
                "status": "ready" if ready else "partial" if fund_count else "blocked",
                "minimum_peer_count": minimum_peer_count,
                "classified_count": int(item.get("classified_count") or fund_count),
                "database_fund_count": fund_count,
                "evaluation_method_ready_count": fund_count,
                "metric_ready_count": evaluated_count,
                "style_ready_count": style_ready_count,
                "recommendation_ready_count": evaluated_count if ready else 0,
            })

        return {
            "summary": {
                "category_count": len(groups),
                "ready_category_count": sum(1 for group in groups if group["status"] == "ready"),
                "classified_count": sum(group["classified_count"] for group in groups),
                "database_fund_count": sum(group["database_fund_count"] for group in groups),
                "evaluation_method_ready_count": sum(group["evaluation_method_ready_count"] for group in groups),
                "metric_ready_count": sum(group["metric_ready_count"] for group in groups),
                "style_ready_count": sum(group["style_ready_count"] for group in groups),
                "recommendation_ready_count": sum(group["recommendation_ready_count"] for group in groups),
            },
            "groups": groups,
            "methodology_version": self.METHODOLOGY_VERSION,
            "source": "standardized_peer_group_inventory",
        }

    @property
    def classification_repo(self):
        if self._classification_repo is None:
            from repositories import get_fund_classification_repo

            self._classification_repo = get_fund_classification_repo()
        return self._classification_repo

    @property
    def metric_repo(self):
        if self._metric_repo is None:
            from repositories import get_metric_snapshot_repo

            self._metric_repo = get_metric_snapshot_repo()
        return self._metric_repo

    @property
    def profile_repo(self):
        if self._profile_repo is None:
            from repositories import get_research_profile_repo

            self._profile_repo = get_research_profile_repo()
        return self._profile_repo

    @property
    def holding_style_repo(self):
        if self._holding_style_repo is None:
            from repositories import get_holding_style_snapshot_repo

            self._holding_style_repo = get_holding_style_snapshot_repo()
        return self._holding_style_repo

    @property
    def bond_holding_repo(self):
        if self._bond_holding_repo is None:
            from repositories import get_fund_bond_holding_repo

            self._bond_holding_repo = get_fund_bond_holding_repo()
        return self._bond_holding_repo

    @property
    def fof_holding_repo(self):
        if self._fof_holding_repo is None:
            from repositories import get_fund_underlying_holding_repo

            self._fof_holding_repo = get_fund_underlying_holding_repo()
        return self._fof_holding_repo

    def _profiles_with_style_suggestions(
        self,
        codes: List[str],
        rows: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Dict[str, Any]]:
        profiles = self.profile_repo.list_profiles(codes)
        suggestions = self.profile_repo.list_memo_style_suggestions(codes)
        holding_styles = self.holding_style_repo.get_latest_map(codes)
        row_map = {
            str(row.get("wind_code") or "").strip(): row
            for row in (rows or [])
            if str(row.get("wind_code") or "").strip()
        }
        bond_codes = [
            code
            for code in codes
            if str((row_map.get(code) or {}).get("asset_class") or "") == "fixed_income"
            or "债" in str((row_map.get(code) or {}).get("type") or "")
        ]
        bond_profiles: Dict[str, Dict[str, Any]] = {}
        if bond_codes:
            from services.fund_bond_holding_service import FundBondHoldingService

            bond_profiles = FundBondHoldingService.professional_profiles_from_rows(
                self.bond_holding_repo.list_latest_periods_map(bond_codes, limit=4)
            )
        fof_codes = [
            code
            for code in codes
            if str((row_map.get(code) or {}).get("strategy_family_key") or "") in {
                "fof_equity", "fof_balanced", "fof_bond",
            }
            or str((row_map.get(code) or {}).get("standardized_peer_group_name") or "").startswith("FOF-")
        ]
        fof_profiles: Dict[str, Dict[str, Any]] = {}
        if fof_codes:
            from services.fund_fof_holding_service import FundFofHoldingService

            fof_rows_map = self.fof_holding_repo.list_latest_periods_map(fof_codes, limit=1)
            underlying_codes = list(dict.fromkeys(
                str(item.get("underlying_fund_code") or "").strip()
                for items in fof_rows_map.values()
                for item in items
                if str(item.get("underlying_fund_code") or "").strip()
            ))
            fof_profiles = FundFofHoldingService.professional_profiles_from_rows(
                fof_rows_map,
                FundFofHoldingService.build_classification_map(
                    self.classification_repo,
                    underlying_codes,
                ),
            )
        return {
            code: {
                **(profiles.get(code) or {}),
                "memo_style_suggestions": suggestions.get(code) or [],
                "holding_style_evidence": self._holding_style_evidence(holding_styles.get(code) or {}),
                "bond_holding_style_profile": bond_profiles.get(code) or {},
                "bond_holding_style_evidence": (
                    FundBondHoldingService.style_evidence(bond_profiles.get(code) or {})
                    if bond_codes else []
                ),
                "fof_holding_style_profile": fof_profiles.get(code) or {},
                "fof_holding_style_evidence": (
                    FundFofHoldingService.style_evidence(fof_profiles.get(code) or {})
                    if fof_codes else []
                ),
                "derived_style_evidence": self._derived_style_evidence(row_map.get(code) or {}),
            }
            for code in codes
        }

    def _candidate_from_evaluation(
        self,
        row: Dict[str, Any],
        profile: Dict[str, Any],
        panel: List[Dict[str, Any]],
        evaluation_item: Dict[str, Any],
    ) -> Tuple[Optional[Dict[str, Any]], str]:
        professional_scoring = evaluation_item.get("scoring") or {}
        peer = evaluation_item.get("peer") or {}
        fund_evaluation = evaluation_item.get("evaluation") or {}
        score = professional_scoring.get("overall_score")
        if score is None:
            return None, self._evaluation_exclusion_reason(professional_scoring, peer)

        code = str(row.get("wind_code") or "")
        evaluation = fund_evaluation.get("evaluation") or {}
        classification = fund_evaluation.get("classification") or professional_scoring.get("classification") or {}
        peer_metrics = peer.get("metrics") or {}
        metric_evidence = {
            name: metric.get("value")
            for name, metric in peer_metrics.items()
            if name != "professional_score" and isinstance(metric, dict)
        }
        research_profile = {
            **profile,
            "peer_group": classification.get("peer_group") or profile.get("peer_group"),
            "peer_group_id": classification.get("peer_group_id"),
            "peer_group_key": classification.get("peer_group_key"),
        }
        evaluation_status = str(fund_evaluation.get("status") or "")
        candidate = {
            **row,
            "wind_code": code,
            "classification_ready": bool(
                classification.get("status") == "classified"
                and (classification.get("peer_group_id") or classification.get("peer_group_key"))
            ),
            "evaluation_ready": bool(
                evaluation_status in {"ok", "partial"}
                and evaluation.get("overall_score") is not None
            ),
            "research_profile": research_profile,
            "style_profile": FundResearchSnapshotService.project_style_profile(research_profile),
            "rolling_metrics": self._rolling_metric_panel(panel),
            "professional_scoring": {
                **professional_scoring,
                "overall_score": evaluation.get("overall_score"),
                "overall_grade": evaluation.get("overall_grade"),
            },
            "peer_percentiles": {"metrics": evaluation.get("peer_percentiles") or {}},
            "fund_evaluation": fund_evaluation,
            "fund_evaluation_status": fund_evaluation.get("status"),
            "fund_evaluation_missing_items": fund_evaluation.get("missing_items") or [],
            "_candidate_manager_tenure": self._manager_tenure_evidence(panel, professional_scoring),
            "_candidate_metrics": metric_evidence,
            "_candidate_profile_key": professional_scoring.get("fund_type_profile"),
            "_candidate_data_as_of": (fund_evaluation.get("target") or {}).get("as_of_date"),
        }
        return candidate, ""

    @staticmethod
    def _evaluation_exclusion_reason(
        professional_scoring: Dict[str, Any],
        peer: Dict[str, Any],
    ) -> str:
        classification = professional_scoring.get("classification") or {}
        if classification.get("status") != "classified":
            return "evaluation_method_missing"
        if peer.get("sample_status") == "target_metric_missing":
            return "required_category_evidence_missing"
        missing_text = " ".join(str(item) for item in professional_scoring.get("missing_data") or [])
        if any(token in missing_text for token in ("指标", "跟踪", "收益", "回撤", "Sharpe", "波动", "规模", "费率")):
            return "required_category_evidence_missing"
        return "category_score_unavailable"

    def _recommendation_evidence(self, candidate: Dict[str, Any]) -> Dict[str, Any]:
        metrics = candidate.pop("_candidate_metrics", {})
        profile_key = candidate.pop("_candidate_profile_key", "")
        data_as_of = candidate.pop("_candidate_data_as_of", None)
        selected_style = candidate.pop("_selected_style", "")
        manager_tenure = candidate.pop("_candidate_manager_tenure", {})
        multi_period = FundResearchSnapshotService.project_multi_period_evidence(
            candidate.get("rolling_metrics") or {},
            profile_key,
        )
        reasons: List[str] = []
        risks: List[str] = []

        if profile_key in {"index_fund", "qdii_index"}:
            reasons.extend(self._metric_reason(metrics, "tracking_error", "1 年跟踪误差", "percent"))
            reasons.extend(self._metric_reason(metrics, "absolute_tracking_difference", "1 年跟踪差异", "percent"))
            reasons.extend(self._metric_reason(metrics, "expense_ratio", "基础费率", "percent"))
            reasons.extend(self._metric_reason(metrics, "aum", "基金规模", "asset"))
            risks.append("指数基金净值会随所跟踪指数波动，当前跟踪表现不代表未来持续。")
            if profile_key == "qdii_index":
                risks.append("QDII 指数基金还受汇率、海外交易时区和跨境费用影响。")
        elif profile_key == "index_enhanced":
            reasons.extend(self._metric_reason(metrics, "excess_return", "近 1 年超额收益", "percent"))
            reasons.extend(self._metric_reason(metrics, "information_ratio", "近 1 年信息比率", "number"))
            reasons.extend(self._metric_reason(metrics, "tracking_error", "近 1 年跟踪误差", "percent"))
            reasons.extend(self._metric_reason(metrics, "max_drawdown", "近 1 年最大回撤", "percent"))
            risks.append("指数增强依赖主动模型和组合偏离，历史超额收益可能衰减或反转。")
        elif profile_key == "money_market":
            reasons.extend(self._metric_reason(metrics, "seven_day_annualized_yield", "七日年化", "percent"))
            reasons.extend(self._metric_reason(metrics, "annualized_return", "近 1 年年化收益", "percent"))
            reasons.extend(self._metric_reason(metrics, "aum", "基金规模", "asset"))
            risks.append("货币基金收益率会随市场利率变化，也不等同于银行存款。")
        else:
            reasons.extend(self._metric_reason(metrics, "annualized_return", "近 1 年年化收益", "percent"))
            reasons.extend(self._metric_reason(metrics, "max_drawdown", "近 1 年最大回撤", "percent"))
            reasons.extend(self._metric_reason(metrics, "sharpe_ratio", "近 1 年 Sharpe", "number"))
            reasons.extend(self._metric_reason(multi_period, "annualized_return_3y", "近 3 年年化收益", "percent"))
            risks.append("历史业绩和同类位置可能随市场风格变化，短期领先不代表长期持续。")

        if multi_period.get("status") != "long_term_ready":
            risks.append("近 3 年完整收益风险证据不足，不能把短期领先视为长期持续。")
        elif multi_period.get("consistency_status") == "divergent":
            gap = self._number(multi_period.get("annualized_return_gap"))
            if gap is not None:
                risks.append(f"近 1 年与近 3 年年化收益相差 {gap * 100:.1f} 个百分点，短长期表现分化较大。")

        if not reasons:
            reasons.append("已满足当前类别的核心评价证据门槛。")
        profile = candidate.get("research_profile", {})
        if selected_style:
            matched_style = self._matching_style_evidence(candidate, selected_style)
            if matched_style:
                source_label = {
                    "confirmed": "已确认画像",
                    "quantitative": "真实持仓同类分位",
                    "derived": "标准分类或基准",
                    "llm_suggested": "纪要推断",
                }.get(str(matched_style.get("status") or ""), "风格证据")
                basis = str(matched_style.get("basis") or "").strip()
                reasons.insert(0, f"匹配“{selected_style}”（{source_label}{f'：{basis}' if basis else ''}）")

        derived_styles = profile.get("derived_style_evidence") or []
        memo_suggestions = profile.get("memo_style_suggestions") or []
        has_confirmed_memo = any(item.get("status") == "confirmed" for item in memo_suggestions)
        has_llm_suggestion = any(item.get("status") != "confirmed" for item in memo_suggestions)
        if not profile.get("style_label") and has_llm_suggestion:
            risks.append("风格标签来自 LLM 对调研纪要的证据提取，尚待人工确认。")
        if not profile.get("style_label") and derived_styles:
            risks.append("风格标签来自标准同类组或可核验基准，不等同于实际持仓风格。")
        elif not profile.get("style_label") and not has_confirmed_memo and not memo_suggestions:
            risks.append("风格标签证据仍待补充，当前候选主要依据量化与分类证据。")
        if manager_tenure.get("applicable"):
            if manager_tenure.get("coverage_status") == "partial_since_data_start":
                coverage_ratio = self._number(manager_tenure.get("coverage_ratio"))
                coverage_text = f"{coverage_ratio * 100:.0f}%" if coverage_ratio is not None else "不完整"
                risks.insert(0, f"现任经理任期净值仅覆盖 {coverage_text}，该维度不计分，也不生成任期同类排名。")
            elif manager_tenure.get("status") == "unavailable":
                risks.append("现任经理任期表现待补，不能把基金完整历史业绩归因给当前经理。")
        return {
            "reasons": reasons[:4],
            "risks": risks[:3],
            "multi_period": multi_period,
            "manager_tenure": manager_tenure,
            "data_as_of": data_as_of,
            "methodology_version": self.METHODOLOGY_VERSION,
            "score_scope": "category_relative",
        }

    @classmethod
    def _manager_tenure_evidence(
        cls,
        panel: List[Dict[str, Any]],
        professional_scoring: Dict[str, Any],
    ) -> Dict[str, Any]:
        dimensions = professional_scoring.get("dimension_scores") or {}
        dimension = dimensions.get("manager_tenure") or {}
        applicable = "manager_tenure" in dimensions
        rows = [item for item in panel if item.get("metric_window") == "manager_tenure"]
        if not rows:
            return {
                "status": "unavailable",
                "coverage_status": "unavailable",
                "applicable": applicable,
                "included_in_score": False,
                "note": "现任经理任期净值指标待补。",
            }

        details = next((item.get("details") for item in rows if isinstance(item.get("details"), dict)), {}) or {}
        coverage = build_manager_tenure_coverage(
            details.get("requested_start_date") or details.get("manager_tenure_start"),
            details.get("actual_start_date") or details.get("window_start_date"),
            details.get("actual_end_date") or details.get("window_end_date") or rows[0].get("as_of_date"),
            details.get("actual_observations") or details.get("observations") or 0,
        )
        coverage_status = coverage.get("tenure_coverage_status") or "unavailable"
        metrics = {
            str(item.get("metric_name")): cls._number(item.get("metric_value"))
            for item in rows
            if item.get("metric_name")
        }
        coverage_ratio = cls._number(coverage.get("tenure_coverage_ratio"))
        if coverage_status == "full_tenure":
            note = "净值覆盖现任团队完整任期。"
            if applicable and dimension.get("included_in_score"):
                note = "净值覆盖现任团队完整任期，经理任期维度已按当前类别方法参与评分。"
            elif not applicable:
                note = "净值覆盖现任团队完整任期；当前基金类别评分不使用经理任期维度。"
        elif coverage_status == "partial_since_data_start":
            note = (
                f"本地净值仅覆盖现任团队任期 {coverage_ratio * 100:.0f}%，该维度不计分。"
                if coverage_ratio is not None
                else "本地净值未完整覆盖现任团队任期，该维度不计分。"
            )
        else:
            note = "现任经理任期净值覆盖待确认。"
        return {
            "status": "available" if coverage_status == "full_tenure" else "partial" if coverage_status == "partial_since_data_start" else "unavailable",
            "coverage_status": coverage_status,
            "coverage_ratio": coverage_ratio,
            "requested_start_date": coverage.get("requested_start_date"),
            "actual_start_date": coverage.get("actual_start_date"),
            "actual_end_date": coverage.get("actual_end_date"),
            "total_return": metrics.get("total_return"),
            "annualized_return": metrics.get("annualized_return"),
            "max_drawdown": metrics.get("max_drawdown"),
            "sharpe_ratio": metrics.get("sharpe_ratio"),
            "applicable": applicable,
            "included_in_score": bool(dimension.get("included_in_score")),
            "dimension_score": cls._number(dimension.get("score")),
            "note": note,
        }

    def _alternative_candidates(
        self,
        candidate: Dict[str, Any],
        peer_candidates: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        target_code = str(candidate.get("wind_code") or "")
        target_style_label = self._primary_style(candidate)
        target_style = self._normalize_style(target_style_label)
        same_style: List[Dict[str, Any]] = []
        other_style: List[Dict[str, Any]] = []
        for option in peer_candidates:
            code = str(option.get("wind_code") or "")
            if not code or code == target_code:
                continue
            option_style_label = self._primary_style(option)
            alternative = {
                "wind_code": code,
                "name": option.get("name") or code,
                "style_label": option_style_label or None,
                "overall_score": option.get("professional_scoring", {}).get("overall_score"),
                "reason": "同类别、同风格候选"
                if target_style and self._normalize_style(option_style_label) == target_style
                else "同类别其他高分候选",
            }
            if target_style and self._normalize_style(option_style_label) == target_style:
                same_style.append(alternative)
            else:
                other_style.append(alternative)
        return (same_style + other_style)[:2]

    @staticmethod
    def _belongs_to_group(row: Dict[str, Any], peer_group: str) -> bool:
        return peer_group in {
            str(row.get("standardized_peer_group_name") or "").strip(),
            str(row.get("standardized_peer_group_key") or "").strip(),
            str(row.get("standardized_peer_group_id") or "").strip(),
        }

    @staticmethod
    def _minimum_peer_count(rows: List[Dict[str, Any]]) -> int:
        values = [
            int(row.get("minimum_peer_count") or 0)
            for row in rows
            if str(row.get("minimum_peer_count") or "").isdigit()
        ]
        return max(values, default=0)

    def _matches_style(self, candidate: Dict[str, Any], style: str) -> bool:
        if not style:
            return True
        style_text = " ".join(str(item.get("value") or "") for item in self._candidate_style_items(candidate))
        normalized_text = self._normalize_style(style_text)
        aliases = self.STYLE_ALIASES.get(style, (style,))
        return any(self._normalize_style(alias) in normalized_text for alias in aliases)

    @classmethod
    def _available_styles(cls, profiles: Dict[str, Dict[str, Any]]) -> List[str]:
        candidates = [
            {"wind_code": code, "research_profile": profile}
            for code, profile in profiles.items()
        ]
        return [item["value"] for item in cls._available_style_options(candidates)]

    @classmethod
    def _available_style_options(cls, candidates: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        options: Dict[str, Dict[str, Any]] = {}
        for candidate in candidates:
            code = str(candidate.get("wind_code") or "")
            seen_values = set()
            seen_evidence_layers = set()
            for item in cls._candidate_style_items(candidate):
                value = cls._canonical_style(item.get("value"))
                if not value:
                    continue
                option = options.setdefault(value, {
                    "value": value,
                    "matched_count": 0,
                    "confirmed_count": 0,
                    "derived_count": 0,
                    "suggested_count": 0,
                    "quantitative_count": 0,
                    "sample_fund_codes": [],
                })
                if value not in seen_values:
                    seen_values.add(value)
                    option["matched_count"] += 1
                    if code and len(option["sample_fund_codes"]) < 3:
                        option["sample_fund_codes"].append(code)

                status = str(item.get("status") or "")
                count_key = {
                    "confirmed": "confirmed_count",
                    "derived": "derived_count",
                    "llm_suggested": "suggested_count",
                    "quantitative": "quantitative_count",
                }.get(status, "suggested_count")
                evidence_layer = (value, count_key)
                if evidence_layer not in seen_evidence_layers:
                    seen_evidence_layers.add(evidence_layer)
                    option[count_key] += 1

        display_index = {value: index for index, value in enumerate(cls.STYLE_DISPLAY_ORDER)}
        ordered = sorted(
            options.values(),
            key=lambda item: (
                display_index.get(item["value"], len(display_index)),
                -int(item["matched_count"]),
                item["value"],
            ),
        )
        return ordered[:50]

    @classmethod
    def _style_items(cls, profile: Dict[str, Any]) -> List[Dict[str, Any]]:
        projected = FundResearchSnapshotService.project_style_profile(profile)
        return [dict(item) for item in projected.get("label_evidence") or []]

    @classmethod
    def _candidate_style_items(cls, candidate: Dict[str, Any]) -> List[Dict[str, Any]]:
        style_profile = candidate.get("style_profile") or {}
        items = style_profile.get("label_evidence") or []
        return [dict(item) for item in items] if items else cls._style_items(candidate.get("research_profile") or {})

    @classmethod
    def _holding_style_evidence(cls, snapshot: Dict[str, Any]) -> List[Dict[str, Any]]:
        import json

        percentiles = snapshot.get("peer_percentiles") or []
        if isinstance(percentiles, str):
            try:
                percentiles = json.loads(percentiles)
            except json.JSONDecodeError:
                percentiles = []
        labels = snapshot.get("style_labels") or []
        sample_size = int(snapshot.get("peer_sample_size") or 0)
        minimum_peer_count = int(snapshot.get("minimum_peer_count") or 5)
        if sample_size < minimum_peer_count or not percentiles:
            return []
        return [
            {
                "value": cls._canonical_style(value),
                "status": "quantitative",
                "source": "holding_style_peer_percentile",
                "basis": (
                    f"{snapshot.get('quarter')} · {snapshot.get('peer_group_name')} · "
                    f"同类样本 {sample_size} 只"
                ),
                "quarter": snapshot.get("quarter"),
                "peer_group_id": snapshot.get("peer_group_id"),
                "peer_group_name": snapshot.get("peer_group_name"),
                "sample_size": sample_size,
                "minimum_peer_count": minimum_peer_count,
                "percentiles": percentiles,
                "data_source": snapshot.get("source"),
                "caveat": "基于公开持仓描述子的同类分位，不是完整 Barra 风险模型。",
            }
            for value in labels
            if cls._canonical_style(value)
        ]

    @classmethod
    def _primary_style(cls, candidate: Dict[str, Any]) -> str:
        style_profile = candidate.get("style_profile") or {}
        if style_profile.get("primary_label"):
            return str(style_profile.get("primary_label"))
        items = cls._candidate_style_items(candidate)
        return str(items[0].get("value") or "") if items else ""

    @classmethod
    def _matching_style_evidence(cls, candidate: Dict[str, Any], style: str) -> Optional[Dict[str, Any]]:
        normalized_style = cls._normalize_style(style)
        aliases = cls.STYLE_ALIASES.get(style, (style,))
        normalized_aliases = [cls._normalize_style(alias) for alias in aliases]
        for item in cls._candidate_style_items(candidate):
            item_text = cls._normalize_style(str(item.get("value") or ""))
            if normalized_style in item_text or any(alias in item_text for alias in normalized_aliases):
                return item
        return None

    @classmethod
    def _derived_style_evidence(cls, row: Dict[str, Any]) -> List[Dict[str, Any]]:
        return FundResearchSnapshotService.project_product_positioning_style(
            row,
            {
                "peer_group_name": row.get("standardized_peer_group_name"),
                "peer_group": row.get("standardized_peer_group_name"),
                "strategy_family_key": row.get("strategy_family_key"),
                "active_passive": row.get("active_passive"),
                "benchmark_mapping": {"benchmark_name": row.get("benchmark_name")},
            },
        )

    @classmethod
    def _canonical_style(cls, value: Any) -> str:
        return FundResearchSnapshotService.canonical_style(value)

    @classmethod
    def _is_known_style(cls, value: Any) -> bool:
        normalized = cls._normalize_style(str(value or ""))
        return any(
            normalized == cls._normalize_style(alias)
            for canonical, aliases in cls.STYLE_ALIASES.items()
            for alias in (canonical, *aliases)
        )

    @staticmethod
    def _normalize_style(value: str) -> str:
        return FundResearchSnapshotService.normalize_style(value)

    @staticmethod
    def _rolling_metric_panel(panel: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
        result: Dict[str, Dict[str, Any]] = {}
        for item in panel:
            window = item.get("metric_window")
            name = item.get("metric_name")
            if not window or not name:
                continue
            result.setdefault(str(window), {})[str(name)] = item.get("metric_value")
            result[str(window)]["as_of_date"] = item.get("as_of_date")
        return result

    @classmethod
    def _candidate_sort_key(cls, candidate: Dict[str, Any]) -> Tuple[int, float, str]:
        score = float(candidate.get("professional_scoring", {}).get("overall_score") or 0)
        multi_period = FundResearchSnapshotService.project_multi_period_evidence(
            candidate.get("rolling_metrics") or {},
            str(candidate.get("_candidate_profile_key") or ""),
        )
        return (
            0 if multi_period.get("status") == "long_term_ready" else 1,
            -score,
            str(candidate.get("wind_code") or ""),
        )

    @staticmethod
    def _metric_reason(metrics: Dict[str, Any], key: str, label: str, unit: str) -> List[str]:
        value = FundRecommendationService._number(metrics.get(key))
        if value is None:
            return []
        if unit == "percent":
            display = f"{value * 100:.2f}%"
        elif unit == "asset":
            display = f"{value:.1f} 亿元"
        else:
            display = f"{value:.2f}"
        return [f"{label} {display}"]

    @staticmethod
    def _number(value: Any) -> Optional[float]:
        if value is None or value == "":
            return None
        try:
            return float(Decimal(str(value)))
        except Exception:
            return None
