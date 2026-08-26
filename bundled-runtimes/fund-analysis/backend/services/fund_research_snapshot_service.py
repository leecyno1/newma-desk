"""统一基金研究快照 Module。"""
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional
from uuid import UUID

from services.fund_evaluation_service import FundEvaluationService
from services.fund_drawdown_recovery_service import FundDrawdownRecoveryService
from services.fund_holding_experience_service import FundHoldingExperienceService
from services.holding_style_drift_service import HoldingStyleDriftService
from services.fund_manager_history_service import FundManagerHistoryService
from services.manager_tenure_coverage import (
    build_manager_tenure_coverage,
    metric_details_coverage_status,
)
from services.fund_scale_trend_service import FundScaleTrendService
from services.performance_attribution_service import PerformanceAttributionService


class FundResearchSnapshotService:
    """一次输出详情、推荐和 AI 共用的基金研究事实。"""

    INTERFACE_VERSION = "fund_research_snapshot_v4"
    EVALUATION_WINDOWS = ("6m", "1y", "3y")
    MULTI_PERIOD_SCORE_PROFILES = {
        "active_equity",
        "fixed_income",
        "fixed_income_plus",
        "multi_asset_equity",
        "multi_asset_balanced",
        "multi_asset_bond",
        "fof_equity",
        "fof_balanced",
        "fof_bond",
    }
    STYLE_LABEL_ALIASES = {
        "大盘成长": ("大盘成长", "large growth", "large_growth"),
        "成长": ("成长", "growth"),
        "价值": ("价值", "value"),
        "均衡": ("均衡", "平衡", "混合", "blend", "balanced"),
        "质量": ("质量", "品质", "quality"),
        "红利": ("红利", "股息", "dividend"),
        "大盘": ("大盘", "large cap", "large_cap"),
        "中盘": ("中盘", "mid cap", "mid_cap"),
        "小盘": ("小盘", "small cap", "small_cap", "small"),
        "中小盘": ("中小盘", "mid small", "mid_small"),
        "宽基": ("宽基", "broad market", "broad_market"),
        "低换手": ("低换手", "low turnover", "low_turnover"),
        "高换手": ("高换手", "high turnover", "high_turnover"),
        "行业主题": ("行业", "主题", "sector", "thematic"),
        "低波稳健": ("低波", "稳健", "low volatility", "low_volatility", "defensive"),
        "行业轮动": ("行业轮动", "sector rotation", "sector_rotation"),
        "量化": ("量化", "quant", "quantitative"),
        "指数增强": ("指数增强", "enhanced index", "index enhancement"),
        "固收+": ("固收+", "fixed income plus"),
        "信用": ("信用", "credit"),
        "利率": ("利率", "rates"),
        "高等级信用": ("高等级信用", "high grade credit", "high_grade_credit"),
        "中低等级信用": ("中低等级信用", "lower grade credit", "lower_grade_credit"),
        "利率债": ("利率债", "rate bond", "rates bond"),
        "金融债": ("金融债", "financial bond"),
        "信用债": ("信用债", "credit bond"),
        "可转债": ("可转债", "convertible bond"),
        "地方政府债": ("地方政府债", "local government bond"),
        "信用利率均衡": ("信用利率均衡", "credit rates balanced"),
        "底层高集中": ("底层高集中", "high underlying concentration"),
        "底层中等集中": ("底层中等集中", "medium underlying concentration"),
        "底层较分散": ("底层较分散", "diversified underlying funds"),
        "底层权益基金主导": ("底层权益基金主导", "equity fund dominated lookthrough"),
        "底层固收基金主导": ("底层固收基金主导", "fixed income fund dominated lookthrough"),
        "底层混合基金主导": ("底层混合基金主导", "mixed fund dominated lookthrough"),
        "底层货币基金主导": ("底层货币基金主导", "money fund dominated lookthrough"),
        "底层 FOF 主导": ("底层 FOF 主导", "fof dominated lookthrough"),
        "底层跨市场基金主导": ("底层跨市场基金主导", "cross-market fund dominated lookthrough"),
        "底层 REITs 主导": ("底层 REITs 主导", "reit dominated lookthrough"),
        "底层商品基金主导": ("底层商品基金主导", "commodity fund dominated lookthrough"),
        "底层指数基金主导": ("底层指数基金主导", "generic index fund dominated lookthrough"),
    }
    PEER_GROUP_STYLE_RULES = {
        "指数-沪深300": ("大盘",),
        "指数-上证50": ("大盘",),
        "指数-上证180": ("大盘",),
        "指数-中证A50": ("大盘",),
        "指数-中证500": ("中盘",),
        "指数-中证1000": ("小盘",),
        "指数-中证2000": ("小盘",),
        "指数-中证A500": ("宽基",),
        "指数-中证800": ("宽基",),
        "指数-科创50": ("成长", "行业主题"),
        "指数-创业板指": ("成长",),
        "混合型-偏债配置": ("固收+",),
        "债券型-含权益配置": ("固收+",),
        "混合型-平衡配置": ("均衡",),
        "指数-中证同业存单AAA": ("高等级信用",),
        "指数增强-沪深300": ("指数增强", "大盘"),
        "指数增强-中证500": ("指数增强", "中盘"),
        "指数增强-中证1000": ("指数增强", "小盘"),
        "指数增强-中证A500": ("指数增强", "宽基"),
        "指数增强-中证800": ("指数增强", "宽基"),
        "指数增强-中证2000": ("指数增强", "小盘"),
        "指数增强-中证A50": ("指数增强", "大盘"),
        "指数增强-创业板指": ("指数增强", "成长"),
        "指数增强-科创50": ("指数增强", "成长", "行业主题"),
        "指数增强-上证50": ("指数增强", "大盘"),
    }
    BENCHMARK_STYLE_RULES = {
        "沪深300": ("大盘",),
        "上证50": ("大盘",),
        "上证180": ("大盘",),
        "中证A50": ("大盘",),
        "中证500": ("中盘",),
        "中证1000": ("小盘",),
        "中证2000": ("小盘",),
        "中证A500": ("宽基",),
        "中证800": ("宽基",),
        "科创50": ("成长", "行业主题"),
        "创业板指": ("成长",),
        "中证同业存单AAA": ("高等级信用",),
    }

    def __init__(
        self,
        evaluation_service: Optional[FundEvaluationService] = None,
        attribution_service: Optional[PerformanceAttributionService] = None,
        attribution_repo: Optional[Any] = None,
        holding_style_repo: Optional[Any] = None,
        holding_experience_service: Optional[FundHoldingExperienceService] = None,
        manager_history_service: Optional[FundManagerHistoryService] = None,
        scale_trend_service: Optional[FundScaleTrendService] = None,
        drawdown_recovery_service: Optional[FundDrawdownRecoveryService] = None,
        period_performance_service: Optional[Any] = None,
        manager_tenure_peer_ranking_service: Optional[Any] = None,
    ):
        self.evaluation_service = evaluation_service or FundEvaluationService()
        self.attribution_service = attribution_service or PerformanceAttributionService()
        self.attribution_repo = attribution_repo
        self.holding_style_repo = holding_style_repo
        self.holding_experience_service = holding_experience_service or FundHoldingExperienceService()
        self.manager_history_service = manager_history_service or FundManagerHistoryService()
        self.scale_trend_service = scale_trend_service or FundScaleTrendService()
        self.drawdown_recovery_service = drawdown_recovery_service or FundDrawdownRecoveryService()
        self._period_performance_service = period_performance_service
        self._manager_tenure_peer_ranking_service = manager_tenure_peer_ranking_service

    def build(
        self,
        wind_code: str,
        window: str = "1y",
        include_research: bool = True,
        include_attribution: bool = False,
        research_limit: int = 6,
        live_attribution: bool = True,
    ) -> Dict[str, Any]:
        context = self.evaluation_service.load_context(wind_code)
        if not context.get("found"):
            raise ValueError(f"Fund not found: {wind_code}")

        fund = context["fund"]
        resolved_code = str(fund.get("wind_code") or wind_code)
        selected_window = window if window in self.EVALUATION_WINDOWS else "1y"
        evaluation_windows = self.evaluation_service.evaluate_windows_from_context(
            context,
            list(self.EVALUATION_WINDOWS),
        )
        evaluation = evaluation_windows[selected_window]
        managers = self._load_managers(fund.get("manager_ids") or [])
        research_reports = self._load_research_reports(
            resolved_code,
            fund.get("manager_ids") or [],
            research_limit,
        ) if include_research else []
        attribution = (
            self._load_attribution(resolved_code, live_attribution=live_attribution)
            if include_attribution else self._not_requested_attribution()
        )
        research_profile = dict(context.get("profile") or {})
        classification = evaluation.get("classification") or context.get("standardized_classification") or {}
        rolling_metrics = self.project_rolling_metrics(context.get("metric_panel") or [])
        multi_period_evidence = self.project_multi_period_evidence(
            rolling_metrics,
            str(
                classification.get("evaluation_profile_key")
                or (evaluation.get("methodology") or {}).get("profile_key")
                or ""
            ),
        )
        derived_styles = self.project_product_positioning_style(fund, classification)
        existing_derived_styles = research_profile.get("derived_style_evidence") or []
        fof_lookthrough = ((evaluation.get("explanatory_evidence") or {}).get("fof_lookthrough") or {})
        fof_style_profile: Dict[str, Any] = {}
        fof_style_evidence: List[Dict[str, Any]] = []
        if fof_lookthrough.get("status") == "available":
            from services.fund_fof_holding_service import FundFofHoldingService

            fof_style_profile = FundFofHoldingService.profile_from_snapshot(fof_lookthrough)
            fof_style_evidence = FundFofHoldingService.style_evidence(fof_style_profile)
        research_profile.update({
            "peer_group": classification.get("peer_group") or classification.get("peer_group_name") or research_profile.get("peer_group"),
            "peer_group_id": classification.get("peer_group_id") or research_profile.get("peer_group_id"),
            "peer_group_key": classification.get("peer_group_key") or research_profile.get("peer_group_key"),
            "primary_benchmark": classification.get("primary_benchmark") or research_profile.get("primary_benchmark"),
            "derived_style_evidence": self._merge_style_evidence(existing_derived_styles, derived_styles),
            "fof_holding_style_profile": fof_style_profile,
            "fof_holding_style_evidence": fof_style_evidence,
        })
        holding_style = self._load_holding_style(resolved_code)
        holding_style_drift = self._load_holding_style_drift(resolved_code)
        holding_experience = self.holding_experience_service.analyze(resolved_code)
        manager_history = self._load_manager_history(resolved_code)
        manager_stability = manager_history.get("stability_evidence") or {}
        scale_trend = self._load_scale_trend(resolved_code)
        drawdown_recovery = self._load_drawdown_recovery(resolved_code)
        period_performance = self._load_period_performance(resolved_code)
        manager_tenure_performance = self._manager_tenure_performance(
            resolved_code,
            context.get("manager_tenure") or {},
            rolling_metrics.get("manager_tenure") or {},
            classification or context.get("standardized_classification") or {},
        )
        style_profile = self.project_style_profile(research_profile, research_reports, holding_style)
        fund_memo_count, manager_memo_count = self._research_scope_counts(research_reports)
        missing_items = list(evaluation.get("missing_items") or [])
        if include_research and not research_reports:
            missing_items.append("没有找到已关联到该基金的调研纪要")
        elif include_research and not fund_memo_count and manager_memo_count:
            missing_items.append("当前只有已复核的基金经理层纪要，没有基金专属纪要")
        if include_attribution:
            missing_items.extend(self._attribution_missing_items(attribution))
        assessment_summary = self._assessment_summary(
            evaluation=evaluation,
            style_profile=style_profile,
            research_reports=research_reports,
            attribution=attribution,
            include_attribution=include_attribution,
            manager_stability=manager_stability,
            manager_tenure_performance=manager_tenure_performance,
            scale_trend=scale_trend,
            drawdown_recovery=drawdown_recovery,
            multi_period_evidence=multi_period_evidence,
            holding_style_drift=holding_style_drift,
        )
        detail_highlights = self._detail_highlights(
            evaluation=evaluation,
            holding_experience=holding_experience,
            fallback_as_of=fund.get("nav_date") or fund.get("updated_at"),
        )
        plain_language_brief = self._plain_language_brief(
            fund=fund,
            assessment_summary=assessment_summary,
            detail_highlights=detail_highlights,
            holding_experience=holding_experience,
        )

        core_snapshot = self.project_core_snapshot(
            mode="full",
            fund=fund,
            managers=managers,
            research_profile=research_profile,
            style_profile=style_profile,
            rolling_metrics=rolling_metrics,
            data_quality=context.get("data_quality") or {},
            evaluation=evaluation,
            multi_period_evidence=multi_period_evidence,
            evidence={
                "as_of_date": (evaluation.get("target") or {}).get("as_of_date") or fund.get("nav_date"),
                "fund_data_as_of": fund.get("nav_date") or fund.get("updated_at"),
                "profile_as_of": research_profile.get("updated_at"),
                "research_latest_date": research_reports[0].get("report_date") if research_reports else None,
                "missing_items": list(dict.fromkeys(str(item) for item in missing_items if item)),
            },
        )

        return self._json_safe({
            **core_snapshot,
            "holding_style_drift": holding_style_drift,
            "holding_experience": holding_experience,
            "manager_stability": manager_stability,
            "scale_trend": scale_trend,
            "drawdown_recovery": drawdown_recovery,
            "period_performance": period_performance,
            "manager_tenure_performance": manager_tenure_performance,
            "evaluation_windows": evaluation_windows,
            "assessment_summary": assessment_summary,
            "detail_highlights": detail_highlights,
            "plain_language_brief": plain_language_brief,
            "research_memos": {
                "status": "available" if research_reports else "empty",
                "count": len(research_reports),
                "fund_level_count": fund_memo_count,
                "fund_specific_count": fund_memo_count,
                "manager_level_count": manager_memo_count,
                "items": research_reports,
            },
            "attribution": attribution,
            "analysis_evidence": self.project_analysis_evidence(
                attribution,
                style_profile,
                holding_style_drift,
            ),
            "product_scope": {
                "fund_classification": "core",
                "fund_evaluation": "core",
                "fund_recommendation": "projection",
                "performance_attribution": "on_demand_evidence",
                "ai_analysis": "on_demand_projection",
                "investment_decision": "excluded",
            },
        })

    def _load_manager_history(self, wind_code: str) -> Dict[str, Any]:
        try:
            return self.manager_history_service.get(wind_code)
        except Exception:
            return {
                "status": "unavailable",
                "stability_evidence": {
                    "status": "unavailable",
                    "label": "经理任职历史待补",
                    "included_in_score": False,
                    "note": "经理任职历史暂时不可用。",
                },
            }

    def _manager_tenure_performance(
        self,
        wind_code: str,
        tenure_context: Dict[str, Any],
        metrics: Dict[str, Any],
        classification: Dict[str, Any],
    ) -> Dict[str, Any]:
        profile_key = str(classification.get("evaluation_profile_key") or "").strip()
        if profile_key in {"index_fund", "qdii_index", "money_market"}:
            return {
                "status": "not_applicable",
                "coverage_status": "not_applicable",
                "peer_ranking": {"status": "not_applicable", "metrics": {}},
                "included_in_score": False,
                "scope_note": "该类别评价不使用基金经理任期指标，不构成评价缺口。",
            }
        requested_start = metrics.get("requested_start_date") or tenure_context.get("start_date")
        actual_start = metrics.get("actual_start_date") or metrics.get("window_start_date")
        actual_end = metrics.get("actual_end_date") or metrics.get("window_end_date") or metrics.get("as_of_date")
        coverage_status = str(metrics.get("tenure_coverage_status") or "").strip()
        if not metrics or not actual_start or not actual_end:
            return {
                "status": "unavailable",
                "requested_start_date": requested_start,
                "actual_start_date": actual_start,
                "actual_end_date": actual_end,
                "peer_ranking": {"status": "target_metric_unavailable", "metrics": {}},
                "scope_note": "当前没有可用的现任经理任期净值指标。",
            }
        if not coverage_status:
            coverage_status = "full_tenure" if requested_start == actual_start else "partial_since_data_start"

        ranking = self.manager_tenure_peer_ranking_service.rank({
            "fund_code": wind_code,
            "entity_id": classification.get("entity_id"),
            "category": classification.get("peer_group_name") or classification.get("peer_group"),
            "tenure_return": metrics.get("total_return"),
            "annualized_return": metrics.get("annualized_return"),
            "record_breaking_days_ratio": metrics.get("record_breaking_days_ratio"),
            "max_drawdown": metrics.get("max_drawdown"),
            "sharpe_ratio": metrics.get("sharpe_ratio"),
            "metric_observations": metrics.get("actual_observations") or metrics.get("observations"),
            "metric_start_date": actual_start,
            "metric_as_of_date": actual_end,
            "tenure_coverage_status": coverage_status,
            "tenure_coverage_ratio": metrics.get("tenure_coverage_ratio"),
        })
        return {
            "status": "available" if coverage_status == "full_tenure" else "partial",
            "coverage_status": coverage_status,
            "requested_start_date": requested_start,
            "actual_start_date": actual_start,
            "actual_end_date": actual_end,
            "requested_tenure_days": metrics.get("requested_tenure_days") or metrics.get("tenure_days"),
            "metric_coverage_days": metrics.get("metric_coverage_days"),
            "coverage_ratio": metrics.get("tenure_coverage_ratio"),
            "observations": metrics.get("actual_observations") or metrics.get("observations"),
            "total_return": metrics.get("total_return"),
            "annualized_return": metrics.get("annualized_return"),
            "max_drawdown": metrics.get("max_drawdown"),
            "sharpe_ratio": metrics.get("sharpe_ratio"),
            "peer_ranking": ranking,
            "scope_note": (
                "净值覆盖现任团队完整任期，可进行同区间同类排名。"
                if coverage_status == "full_tenure"
                else "净值只覆盖本地数据起始日之后，不冒充完整经理任期，不生成同类排名。"
            ),
            "included_in_score": coverage_status == "full_tenure",
        }

    def _load_period_performance(self, wind_code: str) -> Dict[str, Any]:
        try:
            if self._period_performance_service is None:
                from services.fund_period_performance_service import FundPeriodPerformanceService

                self._period_performance_service = FundPeriodPerformanceService()
            return self._period_performance_service.get(wind_code, years=5)
        except Exception:
            return {
                "wind_code": wind_code,
                "status": "insufficient_evidence",
                "periods": [],
                "summary": {},
                "missing_items": ["年度业绩证据暂时不可用"],
                "included_in_score": False,
            }

    def _load_scale_trend(self, wind_code: str) -> Dict[str, Any]:
        try:
            return self.scale_trend_service.get(wind_code)
        except Exception:
            return {
                "status": "insufficient_evidence",
                "label": "规模趋势待补",
                "included_in_score": False,
                "note": "至少需要两个报告期的净资产数据。",
            }

    def _load_drawdown_recovery(self, wind_code: str) -> Dict[str, Any]:
        try:
            return self.drawdown_recovery_service.get(wind_code)
        except Exception:
            return {
                "status": "insufficient_evidence",
                "label": "回撤修复待补",
                "included_in_score": False,
                "note": "至少需要两个可用净值日。",
            }

    @classmethod
    def candidate_snapshot(cls, candidate: Dict[str, Any]) -> Dict[str, Any]:
        """把候选基金投影为与完整快照同口径的摘要。"""
        profile = candidate.get("research_profile") or {}
        evaluation = candidate.get("fund_evaluation") or {}
        style_profile = candidate.get("style_profile") or cls.project_style_profile(profile)
        evidence = candidate.get("recommendation_evidence") or {}
        classification = evaluation.get("classification") or {}
        multi_period_evidence = (
            evidence.get("multi_period")
            or cls.project_multi_period_evidence(
                candidate.get("rolling_metrics") or {},
                str(
                    classification.get("evaluation_profile_key")
                    or (evaluation.get("methodology") or {}).get("profile_key")
                    or ""
                ),
            )
        )
        return cls.project_core_snapshot(
            mode="candidate_summary",
            fund=candidate,
            managers=candidate.get("managers") or [],
            research_profile=profile,
            style_profile=style_profile,
            rolling_metrics=candidate.get("rolling_metrics") or {},
            data_quality=(evaluation.get("evaluation") or {}).get("data_quality") or {},
            evaluation=evaluation,
            multi_period_evidence=multi_period_evidence,
            recommendation_evidence=evidence,
            evidence={
                "as_of_date": evidence.get("data_as_of")
                or (evaluation.get("target") or {}).get("as_of_date")
                or candidate.get("nav_date"),
                "fund_data_as_of": candidate.get("nav_date") or candidate.get("updated_at"),
                "profile_as_of": profile.get("updated_at"),
                "research_latest_date": None,
                "missing_items": evaluation.get("missing_items") or [],
            },
        )

    @classmethod
    def project_core_snapshot(
        cls,
        *,
        mode: str,
        fund: Dict[str, Any],
        managers: List[Dict[str, Any]],
        research_profile: Dict[str, Any],
        style_profile: Dict[str, Any],
        rolling_metrics: Dict[str, Any],
        data_quality: Dict[str, Any],
        evaluation: Dict[str, Any],
        evidence: Dict[str, Any],
        multi_period_evidence: Optional[Dict[str, Any]] = None,
        recommendation_evidence: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """详情、推荐和 AI 共用的核心事实投影 Interface。"""
        return {
            "interface_version": cls.INTERFACE_VERSION,
            "mode": mode,
            "status": evaluation.get("status"),
            "fund": cls.project_fund(fund),
            "managers": managers,
            "research_profile": research_profile,
            "style_profile": style_profile,
            "rolling_metrics": rolling_metrics,
            "multi_period_evidence": multi_period_evidence or {},
            "data_quality": data_quality,
            "evaluation": evaluation,
            "recommendation_evidence": recommendation_evidence,
            "evidence": evidence,
        }

    @classmethod
    def project_multi_period_evidence(
        cls,
        rolling_metrics: Dict[str, Any],
        profile_key: str = "",
    ) -> Dict[str, Any]:
        """统一输出推荐、比较和 AI 共用的多周期收益风险证据。"""
        six_month = rolling_metrics.get("6m") or {}
        one_year = rolling_metrics.get("1y") or {}
        three_year = rolling_metrics.get("3y") or {}
        annualized_return_1y = cls._number(one_year.get("annualized_return"))
        annualized_return_3y = cls._number(three_year.get("annualized_return"))
        return_gap = (
            abs(annualized_return_1y - annualized_return_3y)
            if annualized_return_1y is not None and annualized_return_3y is not None
            else None
        )
        if return_gap is None:
            consistency_status = "unavailable"
            consistency_label = "短长期一致性待补"
        elif return_gap <= 0.05:
            consistency_status = "stable"
            consistency_label = "短长期表现较一致"
        elif return_gap <= 0.12:
            consistency_status = "mixed"
            consistency_label = "短长期表现存在分化"
        else:
            consistency_status = "divergent"
            consistency_label = "短长期表现分化较大"

        long_term_ready = all(
            cls._number(three_year.get(metric_name)) is not None
            for metric_name in ("annualized_return", "max_drawdown", "sharpe_ratio")
        )
        return {
            "status": "long_term_ready" if long_term_ready else "short_term_only",
            "return_6m": cls._number(six_month.get("total_return")),
            "return_1y": cls._number(one_year.get("total_return")),
            "annualized_return_1y": annualized_return_1y,
            "annualized_return_3y": annualized_return_3y,
            "max_drawdown_1y": cls._number(one_year.get("max_drawdown")),
            "max_drawdown_3y": cls._number(three_year.get("max_drawdown")),
            "sharpe_ratio_3y": cls._number(three_year.get("sharpe_ratio")),
            "annualized_return_gap": return_gap,
            "consistency_status": consistency_status,
            "consistency_label": consistency_label,
            "used_in_score": long_term_ready and profile_key in cls.MULTI_PERIOD_SCORE_PROFILES,
            "data_as_of": three_year.get("as_of_date") or one_year.get("as_of_date"),
        }

    @staticmethod
    def project_fund(fund: Dict[str, Any]) -> Dict[str, Any]:
        raw_data = fund.get("raw_data") if isinstance(fund.get("raw_data"), dict) else {}
        info = raw_data.get("info") if isinstance(raw_data.get("info"), dict) else {}
        universe = raw_data.get("universe") if isinstance(raw_data.get("universe"), dict) else {}
        product_profile = raw_data.get("product_profile") if isinstance(raw_data.get("product_profile"), dict) else None
        contract_benchmark = (
            fund.get("contract_benchmark")
            or info.get("benchmark")
            or universe.get("benchmark")
            or fund.get("benchmark")
        )
        peer_return_metrics = {
            window: {
                "value": fund.get(f"return_{window}_metric"),
                "percentile": fund.get(f"return_{window}_peer_percentile"),
                "rank": fund.get(f"return_{window}_peer_rank"),
                "peer_count": fund.get(f"return_{window}_peer_count"),
            }
            for window in ("6m", "1y", "3y")
            if fund.get(f"return_{window}_metric") is not None
            or fund.get(f"return_{window}_peer_percentile") is not None
        }
        return {
            "id": fund.get("id") or fund.get("wind_code"),
            "wind_code": fund.get("wind_code"),
            "name": fund.get("name"),
            "type": fund.get("type"),
            "manager_ids": fund.get("manager_ids") or [],
            "total_asset": fund.get("total_asset"),
            "nav": fund.get("nav"),
            "nav_date": fund.get("nav_date"),
            "establishment_date": (
                fund.get("establishment_date")
                or info.get("establishment_date")
                or universe.get("establishment_date")
            ),
            "updated_at": fund.get("updated_at"),
            "benchmark": contract_benchmark,
            "contract_benchmark": contract_benchmark,
            "company": fund.get("company") or universe.get("company") or info.get("company") or raw_data.get("company"),
            "custodian": fund.get("custodian") or universe.get("custodian") or info.get("custodian"),
            "invest_type": fund.get("invest_type") or universe.get("invest_type") or info.get("invest_type"),
            "contract_type": fund.get("contract_type") or universe.get("contract_type") or info.get("contract_type"),
            "management_fee": fund.get("management_fee") or universe.get("management_fee") or info.get("management_fee"),
            "custodian_fee": fund.get("custodian_fee") or universe.get("custodian_fee") or info.get("custodian_fee"),
            "product_profile": product_profile,
            "purchase_start_date": universe.get("purchase_start_date") or info.get("purchase_start_date"),
            "redeem_start_date": universe.get("redeem_start_date") or info.get("redeem_start_date"),
            "performance_data": fund.get("performance_data") or fund.get("performance") or {},
            "risk_metrics": fund.get("risk_metrics") or {},
            "peer_return_metrics": peer_return_metrics,
            "holding_count": fund.get("holding_count"),
            "classification_ready": bool(fund.get("classification_ready")),
            "evaluation_ready": bool(fund.get("evaluation_ready")),
        }

    def _load_managers(self, manager_ids: List[str]) -> List[Dict[str, Any]]:
        from repositories import get_manager_repo

        manager_map = get_manager_repo().get_managers_by_ids(manager_ids)
        managers = []
        for manager_id in manager_ids:
            row = manager_map.get(manager_id)
            if not row:
                continue
            raw_data = row.get("raw_data") if isinstance(row.get("raw_data"), dict) else {}
            managers.append({
                "manager_id": row.get("wind_code"),
                "wind_code": row.get("wind_code"),
                "name": row.get("name"),
                "company": row.get("company"),
                "education": row.get("education"),
                "work_years": row.get("work_years"),
                "management_years": row.get("management_years"),
                "current_funds": row.get("current_funds") or [],
                "begin_date": raw_data.get("begin_date"),
                "end_date": raw_data.get("end_date"),
                "source": "tushare.fund_manager",
            })
        return managers

    def _load_research_reports(
        self,
        wind_code: str,
        manager_ids: List[str],
        limit: int,
    ) -> List[Dict[str, Any]]:
        reports = self._mongo_research_reports(wind_code, limit)
        if len(reports) < limit:
            reports.extend(self._postgres_research_reports(wind_code, limit - len(reports)))
        if len(reports) < limit and manager_ids:
            reports.extend(self._postgres_manager_research_reports(
                wind_code,
                manager_ids,
                limit - len(reports),
            ))
        deduplicated = {}
        for report in reports:
            key = str(report.get("id") or f"{report.get('title')}:{report.get('report_date')}")
            deduplicated.setdefault(key, report)
        return sorted(
            deduplicated.values(),
            key=lambda item: str(item.get("report_date") or ""),
            reverse=True,
        )[:limit]

    def _mongo_research_reports(self, wind_code: str, limit: int) -> List[Dict[str, Any]]:
        from service_registry import get_db

        db = get_db()
        if db is None:
            return []
        rows = []
        for doc in db.research_reports.find({"fund_ids": wind_code}).sort("report_date", -1).limit(limit):
            rows.append({
                "id": str(doc.get("_id", "")),
                "title": doc.get("title"),
                "report_date": doc.get("report_date"),
                "manager_id": doc.get("manager_id"),
                "manager_name": doc.get("manager_name"),
                "source": doc.get("source"),
                "summary": doc.get("summary", ""),
                "key_points": doc.get("key_points", []),
                "classifications": doc.get("classifications", []),
                "style_labels": doc.get("style_labels", []),
                "fund_classifications": doc.get("classifications", []),
                "fund_style_labels": doc.get("style_labels", []),
                "manager_classifications": [],
                "manager_style_labels": [],
                "evidence_scope": "fund_specific",
            })
        return rows

    def _postgres_research_reports(self, wind_code: str, limit: int) -> List[Dict[str, Any]]:
        from database import get_engine
        from sqlalchemy import text

        sql = text("""
            SELECT id, manager_id, manager_name, title, report_date, source, summary,
                   key_points, classifications, style_labels, tags, review_proposals
            FROM research_reports
            WHERE :wind_code = ANY(COALESCE(fund_ids, ARRAY[]::TEXT[]))
            ORDER BY report_date DESC NULLS LAST, updated_at DESC
            LIMIT :limit
        """)
        with get_engine().connect() as conn:
            rows = conn.execute(sql, {"wind_code": wind_code, "limit": max(1, limit)}).fetchall()
        reports = []
        for row in rows:
            proposals = self._json_proposals(row._mapping.get("review_proposals"))
            evidence_scope = self._research_evidence_scope(wind_code, proposals)
            classifications = row._mapping.get("classifications") or []
            style_labels = row._mapping.get("style_labels") or row._mapping.get("tags") or []
            scoped_labels = self._scoped_research_labels(
                wind_code,
                proposals,
                classifications,
                style_labels,
                evidence_scope,
            )
            reports.append({
                "id": str(row._mapping.get("id")),
                "title": row._mapping.get("title"),
                "report_date": row._mapping.get("report_date"),
                "manager_id": row._mapping.get("manager_id"),
                "manager_name": row._mapping.get("manager_name"),
                "source": row._mapping.get("source"),
                "summary": row._mapping.get("summary") or "",
                "key_points": row._mapping.get("key_points") or [],
                "classifications": classifications,
                "style_labels": style_labels,
                "evidence_scope": evidence_scope,
                **scoped_labels,
            })
        return reports

    @staticmethod
    def _json_proposals(value: Any) -> List[Dict[str, Any]]:
        if isinstance(value, list):
            return value
        if isinstance(value, str):
            import json

            try:
                parsed = json.loads(value)
                return parsed if isinstance(parsed, list) else []
            except json.JSONDecodeError:
                return []
        return []

    @staticmethod
    def _research_evidence_scope(wind_code: str, proposals: List[Dict[str, Any]]) -> str:
        target_code = str(wind_code or "").strip().upper()
        confirmed = [
            proposal
            for proposal in proposals
            if proposal.get("review_status") == "confirmed"
        ]

        for proposal in confirmed:
            target_fund_ids = {
                str(code or "").strip().upper()
                for code in proposal.get("target_fund_ids") or []
                if str(code or "").strip()
            }
            if proposal.get("scope") == "fund" and target_code in target_fund_ids:
                return "fund_specific"

        matching_fund_proposals = [
            proposal
            for proposal in confirmed
            if proposal.get("kind") == "fund"
            and str(proposal.get("value") or "").strip().upper() == target_code
        ]
        if any(
            proposal.get("extraction_source") != "tushare.fund_manager"
            for proposal in matching_fund_proposals
        ):
            return "fund_specific"

        return "manager_level"

    @staticmethod
    def _research_scope_counts(reports: List[Dict[str, Any]]) -> tuple[int, int]:
        fund_level_count = sum(
            1 for report in reports if report.get("evidence_scope") == "fund_specific"
        )
        return fund_level_count, len(reports) - fund_level_count

    @staticmethod
    def _scoped_research_labels(
        wind_code: str,
        proposals: List[Dict[str, Any]],
        classifications: List[str],
        style_labels: List[str],
        default_scope: str,
    ) -> Dict[str, List[str]]:
        target_code = str(wind_code or "").strip().upper()
        source_values = {
            "classification": [str(item) for item in classifications if item],
            "style_label": [str(item) for item in style_labels if item],
        }
        buckets = {
            "fund_classifications": [],
            "fund_style_labels": [],
            "manager_classifications": [],
            "manager_style_labels": [],
        }
        bucket_keys = {
            ("fund", "classification"): "fund_classifications",
            ("fund", "style_label"): "fund_style_labels",
            ("manager", "classification"): "manager_classifications",
            ("manager", "style_label"): "manager_style_labels",
        }
        explicitly_scoped = {"classification": set(), "style_label": set()}

        for proposal in proposals:
            kind = proposal.get("kind")
            value = str(proposal.get("value") or "").strip()
            scope = proposal.get("scope")
            if (
                proposal.get("review_status") != "confirmed"
                or kind not in source_values
                or value not in source_values[kind]
                or scope not in {"fund", "manager"}
            ):
                continue
            explicitly_scoped[kind].add(value)
            if scope == "fund":
                targets = proposal.get("target_fund_ids") or []
                if isinstance(targets, str):
                    targets = [targets]
                if target_code not in {
                    str(code or "").strip().upper() for code in targets
                }:
                    continue
            buckets[bucket_keys[(scope, kind)]].append(value)

        fallback_scope = "fund" if default_scope == "fund_specific" else "manager"
        for kind, values in source_values.items():
            key = bucket_keys[(fallback_scope, kind)]
            buckets[key].extend(
                value for value in values if value not in explicitly_scoped[kind]
            )
        return {
            key: list(dict.fromkeys(values))
            for key, values in buckets.items()
        }

    def _postgres_manager_research_reports(
        self,
        wind_code: str,
        manager_ids: List[str],
        limit: int,
    ) -> List[Dict[str, Any]]:
        from database import get_engine
        from sqlalchemy import bindparam, text

        unique_manager_ids = list(dict.fromkeys(
            str(manager_id).strip() for manager_id in manager_ids if str(manager_id).strip()
        ))
        if not unique_manager_ids or limit <= 0:
            return []
        sql = text("""
            SELECT *
            FROM (
                SELECT DISTINCT ON (report.id)
                       report.id,
                       COALESCE(report.manager_id, link.manager_id) AS manager_id,
                       COALESCE(report.manager_name, link.manager_name) AS manager_name,
                       report.title, report.report_date, report.source, report.summary,
                       report.key_points, report.classifications, report.style_labels,
                       report.tags, report.review_proposals, report.updated_at
                FROM research_reports report
                JOIN research_report_managers link ON link.report_id = report.id
                WHERE link.manager_id IN :manager_ids
                  AND report.review_status = 'reviewed'
                  AND NOT (:wind_code = ANY(COALESCE(report.fund_ids, ARRAY[]::TEXT[])))
                ORDER BY report.id, report.report_date DESC NULLS LAST, report.updated_at DESC
            ) linked_reports
            ORDER BY report_date DESC NULLS LAST, updated_at DESC
            LIMIT :limit
        """).bindparams(bindparam("manager_ids", expanding=True))
        with get_engine().connect() as conn:
            rows = conn.execute(sql, {
                "wind_code": wind_code,
                "manager_ids": unique_manager_ids,
                "limit": max(1, limit),
            }).fetchall()
        reports = []
        for row in rows:
            classifications = row._mapping.get("classifications") or []
            style_labels = row._mapping.get("style_labels") or row._mapping.get("tags") or []
            reports.append({
                "id": str(row._mapping.get("id")),
                "title": row._mapping.get("title"),
                "report_date": row._mapping.get("report_date"),
                "manager_id": row._mapping.get("manager_id"),
                "manager_name": row._mapping.get("manager_name"),
                "source": row._mapping.get("source"),
                "summary": row._mapping.get("summary") or "",
                "key_points": row._mapping.get("key_points") or [],
                "classifications": classifications,
                "style_labels": style_labels,
                "evidence_scope": "manager_level",
                **self._scoped_research_labels(
                    wind_code,
                    self._json_proposals(row._mapping.get("review_proposals")),
                    classifications,
                    style_labels,
                    "manager_level",
                ),
            })
        return reports

    def _load_attribution(self, wind_code: str, live_attribution: bool = True) -> Dict[str, Any]:
        quarter = self.attribution_service.latest_completed_quarter()
        try:
            from repositories import get_attribution_repo

            repo = self.attribution_repo or get_attribution_repo()
            saved = repo.get_bundle(wind_code, quarter)
        except Exception:
            saved = None

        if saved:
            bundle = dict(saved["bundle"])
            bundle["history_reused"] = True
            bundle["evidence_origin"] = {
                "mode": "saved_history",
                "label": "已保存归因历史",
                "quarter": bundle.get("quarter") or quarter,
                "updated_at": saved.get("updated_at"),
            }
            return bundle

        if not live_attribution:
            return self._unavailable_attribution(
                quarter,
                "当前季度没有已保存归因；本次基金评价未启动现场归因计算。",
                mode="not_run",
                label="本次未运行现场归因",
            )

        try:
            bundle = self.attribution_service.analyze(wind_code, quarter=quarter)
            bundle["history_reused"] = False
            bundle["evidence_origin"] = {
                "mode": "live_calculation",
                "label": "本次现场计算",
                "quarter": bundle.get("quarter") or quarter,
                "updated_at": None,
            }
            return bundle
        except Exception as exc:
            return self._unavailable_attribution(
                quarter,
                f"业绩归因输入不可用：{exc.__class__.__name__}",
            )

    @staticmethod
    def _unavailable_attribution(
        quarter: str,
        reason: str,
        mode: str = "unavailable",
        label: str = "归因证据不可用",
    ) -> Dict[str, Any]:
        return {
            "status": "insufficient_evidence",
            "history_reused": False,
            "evidence_origin": {
                "mode": mode,
                "label": label,
                "quarter": quarter,
                "updated_at": None,
            },
            "barra": {
                "status": "insufficient_evidence",
                "method": "barra_style_risk_model",
                "missing_items": [reason],
            },
            "cross_market_holding_profile": {
                "status": "insufficient_evidence",
                "method": "cross_market_disclosed_holding_profile",
                "markets": [],
                "missing_items": [reason],
            },
            "brinson": {
                "status": "insufficient_evidence",
                "method": "brinson_fachler",
                "missing_items": [reason],
                "effects": [],
            },
            "nav_factor_lens": {"status": "insufficient_evidence", "missing_items": [reason]},
            "nav_return_attribution": {"status": "insufficient_evidence", "missing_items": [reason]},
        }

    @staticmethod
    def _not_requested_attribution() -> Dict[str, Any]:
        return {
            "status": "not_requested",
            "barra": {"status": "not_requested", "method": "barra_style_risk_model"},
            "cross_market_holding_profile": {"status": "not_requested", "method": "cross_market_disclosed_holding_profile", "markets": []},
            "brinson": {"status": "not_requested", "method": "brinson_fachler"},
            "nav_factor_lens": {"status": "not_requested", "method": "nav_behavior_factor_lens"},
            "nav_return_attribution": {"status": "not_requested", "method": "nav_return_attribution"},
        }

    @staticmethod
    def _attribution_missing_items(attribution: Dict[str, Any]) -> List[str]:
        items = []
        for key in ("barra", "cross_market_holding_profile", "brinson", "nav_factor_lens", "nav_return_attribution"):
            block = attribution.get(key) or {}
            items.extend(block.get("missing_items") or [])
        return items

    @classmethod
    def _assessment_summary(
        cls,
        evaluation: Dict[str, Any],
        style_profile: Dict[str, Any],
        research_reports: List[Dict[str, Any]],
        attribution: Dict[str, Any],
        include_attribution: bool,
        manager_stability: Optional[Dict[str, Any]] = None,
        manager_tenure_performance: Optional[Dict[str, Any]] = None,
        scale_trend: Optional[Dict[str, Any]] = None,
        drawdown_recovery: Optional[Dict[str, Any]] = None,
        multi_period_evidence: Optional[Dict[str, Any]] = None,
        holding_style_drift: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """把量化、纪要和归因压缩成详情页与 AI 共用的可读事实。"""
        evaluation_result = evaluation.get("evaluation") or {}
        peer_context = evaluation.get("peer_context") or {}
        classification = evaluation.get("classification") or {}
        score = evaluation_result.get("overall_score")
        professional_metric = (evaluation_result.get("peer_percentiles") or {}).get("professional_score") or {}
        evaluation_window = str(peer_context.get("metric_window") or "1y")
        window_label = {"6m": "近 6 月", "1y": "近 1 年", "3y": "近 3 年"}.get(
            evaluation_window,
            evaluation_window,
        )
        rank = professional_metric.get("rank")
        peer_count = professional_metric.get("peer_count")
        percentile = professional_metric.get("percentile")

        if peer_context.get("sample_status") not in {None, "sufficient"}:
            valid_peer_count = int(peer_context.get("valid_metric_peer_count") or 0)
            minimum_peer_count = int(peer_context.get("minimum_peer_count") or 5)
            if valid_peer_count < minimum_peer_count:
                verdict = (
                    f"已完成专业分类，但同类有效样本只有 {valid_peer_count} 只，"
                    f"低于 {minimum_peer_count} 只门槛，暂不输出综合分和同类排名。"
                )
            else:
                verdict = "已完成专业分类，但本基金核心指标不足，暂不输出综合分和同类排名。"
        elif evaluation.get("status") == "insufficient_evidence" or score is None:
            verdict = "已完成专业分类，但核心指标不足，暂不输出综合分和同类排名。"
        else:
            verdict = f"{window_label}专业评分 {float(score):.1f} 分"
            if rank is not None and peer_count:
                verdict += f"，同类综合第 {int(rank)} / {int(peer_count)} 名"
            elif percentile is not None:
                verdict += f"，同类有利分位 {float(percentile):.0f}%"
            verdict += "。"

        positive_factors = [str(item) for item in evaluation_result.get("positive_factors") or [] if item]
        negative_factors = [str(item) for item in evaluation_result.get("negative_factors") or [] if item]
        advantages = positive_factors[:3]
        risks = negative_factors[:3]
        if not advantages and score is not None:
            advantages.append("分类内专业评价已达到可用证据门槛")

        holding_style = style_profile.get("holding_style") or {}
        quantitative_labels = [str(item) for item in style_profile.get("quantitative_labels") or [] if item]
        fund_memo_labels = list(dict.fromkeys(
            str(item)
            for key in ("memo_classifications", "memo_style_labels")
            for item in style_profile.get(key) or []
            if item
        ))
        manager_memo_labels = list(dict.fromkeys(
            str(item)
            for key in ("manager_memo_classifications", "manager_memo_style_labels")
            for item in style_profile.get(key) or []
            if item
        ))
        memo_labels = list(dict.fromkeys([*fund_memo_labels, *manager_memo_labels]))
        style_labels = quantitative_labels if holding_style.get("status") == "peer_percentile_ready" else []
        holding_style_status = holding_style.get("status") or "unavailable"
        if style_labels:
            style_scope = "fund_holding_quantitative"
            style_note = "标签来自同季度公开持仓的同类分位。"
        elif holding_style_status == "peer_percentile_neutral":
            style_scope = "fund_holding_quantitative_neutral"
            style_note = "同类样本达到门槛，但横截面差异不显著，因此不强行贴风格标签。"
        elif holding_style_status == "descriptor_ready":
            style_scope = "fund_holding_descriptor_only"
            style_note = "已有公开持仓描述子，但同类样本不足，只展示原始数值。"
        elif fund_memo_labels:
            style_scope = "fund_memo_context"
            style_note = "标签来自基金专属纪要语境，尚未获得持仓量化确认。"
        elif manager_memo_labels:
            style_scope = "manager_memo_context"
            style_note = "当前只有经理纪要语境，不能当作本基金持仓标签。"
        else:
            style_scope = "unavailable"
            style_note = "暂无可核验风格标签。"
        style_evidence = {
            "status": holding_style_status,
            "labels": style_labels,
            "memo_labels": memo_labels,
            "quarter": holding_style.get("quarter"),
            "sample_size": holding_style.get("sample_size") or 0,
            "scope": style_scope,
            "note": style_note,
        }

        holding_style_drift = holding_style_drift or {}
        style_drift_evidence = {
            "status": holding_style_drift.get("status") or "insufficient_evidence",
            "level": holding_style_drift.get("level") or "unavailable",
            "label": holding_style_drift.get("label") or "公开持仓风格变化待补",
            "previous_quarter": holding_style_drift.get("previous_quarter"),
            "latest_quarter": holding_style_drift.get("latest_quarter"),
            "peer_group_name": holding_style_drift.get("peer_group_name"),
            "factor_count": int(holding_style_drift.get("factor_count") or 0),
            "changed_factor_count": int(holding_style_drift.get("changed_factor_count") or 0),
            "max_percentile_change": holding_style_drift.get("max_percentile_change"),
            "factor_changes": holding_style_drift.get("factor_changes") or [],
            "added_labels": holding_style_drift.get("added_labels") or [],
            "removed_labels": holding_style_drift.get("removed_labels") or [],
            "included_in_score": False,
            "source": holding_style_drift.get("source") or "local.postgres.holding_style_snapshots",
            "note": holding_style_drift.get("note") or "至少需要两个可比较的公开持仓期。",
            "boundary": holding_style_drift.get("boundary") or "相邻公开持仓期风格变化只作解释，不直接改变基金评分。",
        }
        if style_drift_evidence["level"] == "high":
            risks.insert(0, "公开持仓风格变化较明显，需核对产品定位与经理表述是否同步变化")

        fund_specific_count, manager_level_count = cls._research_scope_counts(research_reports)
        latest_research = research_reports[0] if research_reports else {}
        research_evidence = {
            "status": "fund_specific" if fund_specific_count else "manager_level" if manager_level_count else "empty",
            "count": len(research_reports),
            "fund_level_count": fund_specific_count,
            "fund_specific_count": fund_specific_count,
            "manager_level_count": manager_level_count,
            "latest_title": latest_research.get("title"),
            "latest_date": latest_research.get("report_date"),
            "note": (
                f"有 {fund_specific_count} 份基金专属纪要，可作为产品层证据。"
                if fund_specific_count
                else f"有 {manager_level_count} 份经理层纪要，只用于理解经理方法，不能外推为本基金持仓。"
                if manager_level_count
                else "暂无已关联纪要。"
            ),
        }

        attribution_summary = cls._assessment_attribution_summary(attribution, include_attribution)
        if attribution_summary.get("status") == "partial_evidence":
            risks.append("归因只覆盖公开披露持仓，不能视为全组合解释")

        cross_market = (
            (evaluation.get("explanatory_evidence") or {}).get("cross_market_holding")
            or {}
        )
        cross_market_labels = [str(item) for item in cross_market.get("labels") or [] if item]
        profile_peer_count = int(cross_market.get("profile_peer_count") or 0)
        minimum_peer_count = int(cross_market.get("minimum_peer_count") or 5)
        holding_comparison_evidence = {
            "status": cross_market.get("status") or "unavailable",
            "quarter": cross_market.get("quarter"),
            "peer_group": cross_market.get("peer_group_name"),
            "sample_size": profile_peer_count,
            "minimum_peer_count": minimum_peer_count,
            "labels": cross_market_labels,
            "comparisons": cross_market.get("comparisons") or [],
            "included_in_score": False,
            "note": (
                "；".join(cross_market_labels[:3]) + "。"
                if cross_market_labels
                else f"同季度同类公开持仓样本 {profile_peer_count}/{minimum_peer_count} 只，只展示本基金证据。"
                if cross_market.get("status") == "insufficient_peer_sample"
                else (cross_market.get("missing_items") or ["暂无可用跨市场持仓比较。"])[0]
            ),
        }

        holding_stability = (
            (evaluation.get("explanatory_evidence") or {}).get("holding_stability")
            or {}
        )
        stability_status = holding_stability.get("status") or "insufficient_evidence"
        if stability_status == "available":
            stability_note = (
                f"{holding_stability.get('previous_quarter') or '上一期'} 至 "
                f"{holding_stability.get('latest_quarter') or '最新一期'}，"
                f"前十大权重重合度 {float(holding_stability.get('top10_overlap_ratio') or 0) * 100:.1f}%，"
                f"延续 {int(holding_stability.get('retained_holding_count') or 0)} 只重仓，"
                f"行业权重重合度 {float(holding_stability.get('industry_overlap_ratio') or 0) * 100:.1f}%。"
                "这不是完整组合换手率。"
            )
        else:
            stability_note = (holding_stability.get("missing_items") or ["至少需要相邻两个季度的公开前十大持仓。"])[0]
        holding_stability_evidence = {
            "status": stability_status,
            "label": holding_stability.get("label"),
            "latest_quarter": holding_stability.get("latest_quarter"),
            "previous_quarter": holding_stability.get("previous_quarter"),
            "top10_overlap_ratio": holding_stability.get("top10_overlap_ratio"),
            "industry_overlap_ratio": holding_stability.get("industry_overlap_ratio"),
            "retained_holding_count": holding_stability.get("retained_holding_count"),
            "included_in_score": False,
            "note": stability_note,
        }

        manager_stability = manager_stability or {}
        manager_stability_evidence = {
            "status": manager_stability.get("status") or "unavailable",
            "label": manager_stability.get("label") or "经理任职历史待补",
            "current_manager_count": int(manager_stability.get("current_manager_count") or 0),
            "current_manager_names": manager_stability.get("current_manager_names") or [],
            "team_mode": manager_stability.get("team_mode") or "unavailable",
            "current_team_start": manager_stability.get("current_team_start"),
            "current_team_days": int(manager_stability.get("current_team_days") or 0),
            "latest_change_date": manager_stability.get("latest_change_date"),
            "changes_last_year": int(manager_stability.get("changes_last_year") or 0),
            "changes_last_three_years": int(manager_stability.get("changes_last_three_years") or 0),
            "as_of_date": manager_stability.get("as_of_date"),
            "included_in_score": False,
            "source": manager_stability.get("source") or "local.postgres.manager_fund_tenures",
            "note": manager_stability.get("note") or "经理任职历史暂时不可用。",
        }

        manager_tenure_performance = manager_tenure_performance or {}
        tenure_coverage_status = manager_tenure_performance.get("coverage_status")
        tenure_coverage_ratio = cls._number(manager_tenure_performance.get("coverage_ratio"))
        tenure_total_return = cls._number(manager_tenure_performance.get("total_return"))
        tenure_annualized_return = cls._number(manager_tenure_performance.get("annualized_return"))
        tenure_max_drawdown = cls._number(manager_tenure_performance.get("max_drawdown"))
        tenure_peer_metric = (
            ((manager_tenure_performance.get("peer_ranking") or {}).get("metrics") or {}).get("total_return")
            or {}
        )
        if manager_tenure_performance.get("status") == "not_applicable":
            tenure_performance_note = manager_tenure_performance.get("scope_note") or "该类别评价不使用基金经理任期指标。"
        elif tenure_coverage_status == "full_tenure":
            tenure_parts = [
                f"现任团队自 {manager_tenure_performance.get('requested_start_date') or '日期待补'} 上任，"
                f"净值完整覆盖至 {manager_tenure_performance.get('actual_end_date') or '最新日期'}"
            ]
            if tenure_total_return is not None:
                tenure_parts.append(f"任期收益 {tenure_total_return * 100:.2f}%")
            if tenure_annualized_return is not None:
                tenure_parts.append(f"年化收益 {tenure_annualized_return * 100:.2f}%")
            if tenure_max_drawdown is not None:
                tenure_parts.append(f"最大回撤 {tenure_max_drawdown * 100:.2f}%")
            if tenure_peer_metric.get("rank") is not None and tenure_peer_metric.get("peer_count"):
                tenure_parts.append(
                    f"同区间同类任期收益第 {int(tenure_peer_metric['rank'])} / "
                    f"{int(tenure_peer_metric['peer_count'])} 名"
                )
            tenure_performance_note = "；".join(tenure_parts) + "。"
        elif manager_tenure_performance.get("status") in {"partial", "available"}:
            tenure_parts = [
                f"现任团队自 {manager_tenure_performance.get('requested_start_date') or '日期待补'} 上任，"
                f"本地净值从 {manager_tenure_performance.get('actual_start_date') or '数据起点待补'} 开始"
            ]
            if tenure_coverage_ratio is not None:
                tenure_parts.append(f"仅覆盖 {tenure_coverage_ratio * 100:.0f}%")
            if tenure_total_return is not None:
                tenure_parts.append(f"本地可见期收益 {tenure_total_return * 100:.2f}%")
            tenure_performance_note = "；".join(tenure_parts) + "；不能冒充完整任期，不生成同类排名。"
        else:
            tenure_performance_note = manager_tenure_performance.get("scope_note") or "当前没有可用的现任经理任期净值指标。"
        manager_tenure_performance_evidence = {
            "status": manager_tenure_performance.get("status") or "unavailable",
            "coverage_status": tenure_coverage_status,
            "requested_start_date": manager_tenure_performance.get("requested_start_date"),
            "actual_start_date": manager_tenure_performance.get("actual_start_date"),
            "actual_end_date": manager_tenure_performance.get("actual_end_date"),
            "coverage_ratio": tenure_coverage_ratio,
            "total_return": tenure_total_return,
            "annualized_return": tenure_annualized_return,
            "max_drawdown": tenure_max_drawdown,
            "sharpe_ratio": cls._number(manager_tenure_performance.get("sharpe_ratio")),
            "peer_ranking": manager_tenure_performance.get("peer_ranking") or {},
            "included_in_score": bool(manager_tenure_performance.get("included_in_score")),
            "source": "local.postgres.metric_snapshots.manager_tenure",
            "note": tenure_performance_note,
        }

        scale_trend = scale_trend or {}
        scale_trend_evidence = {
            "status": scale_trend.get("status") or "insufficient_evidence",
            "label": scale_trend.get("label") or "规模趋势待补",
            "latest_report_date": scale_trend.get("latest_report_date"),
            "latest_asset_yi": scale_trend.get("latest_asset_yi"),
            "one_year_change": scale_trend.get("one_year_change"),
            "three_year_change": scale_trend.get("three_year_change"),
            "peak_asset_yi": scale_trend.get("peak_asset_yi"),
            "peak_date": scale_trend.get("peak_date"),
            "latest_from_peak": scale_trend.get("latest_from_peak"),
            "observations": int(scale_trend.get("observations") or 0),
            "included_in_score": False,
            "source": scale_trend.get("source") or "local.postgres.fund_asset_allocations",
            "note": scale_trend.get("note") or "至少需要两个报告期的净资产数据。",
        }

        drawdown_recovery = drawdown_recovery or {}
        drawdown_recovery_evidence = {
            "status": drawdown_recovery.get("status") or "insufficient_evidence",
            "label": drawdown_recovery.get("label") or "回撤修复待补",
            "history_start": drawdown_recovery.get("history_start"),
            "history_end": drawdown_recovery.get("history_end"),
            "nav_basis": drawdown_recovery.get("nav_basis"),
            "observations": int(drawdown_recovery.get("observations") or 0),
            "current_drawdown": drawdown_recovery.get("current_drawdown"),
            "current_underwater_days": int(drawdown_recovery.get("current_underwater_days") or 0),
            "worst_drawdown": drawdown_recovery.get("worst_drawdown"),
            "worst_peak_date": drawdown_recovery.get("worst_peak_date"),
            "worst_trough_date": drawdown_recovery.get("worst_trough_date"),
            "worst_recovery_date": drawdown_recovery.get("worst_recovery_date"),
            "worst_decline_days": int(drawdown_recovery.get("worst_decline_days") or 0),
            "worst_recovery_days": drawdown_recovery.get("worst_recovery_days"),
            "longest_underwater_days": int(drawdown_recovery.get("longest_underwater_days") or 0),
            "material_episode_count": int(drawdown_recovery.get("material_episode_count") or 0),
            "recovered_material_episode_count": int(drawdown_recovery.get("recovered_material_episode_count") or 0),
            "included_in_score": False,
            "source": drawdown_recovery.get("source") or "local.postgres.fund_nav",
            "note": drawdown_recovery.get("note") or "至少需要两个可用净值日。",
        }

        return {
            "status": evaluation.get("status") or "unavailable",
            "evaluation_window": evaluation_window,
            "evaluation_window_label": window_label,
            "verdict": verdict,
            "peer_group": peer_context.get("peer_group") or classification.get("peer_group"),
            "score": score,
            "grade": evaluation_result.get("overall_grade") if score is not None else None,
            "peer_rank": rank,
            "peer_count": peer_count,
            "peer_percentile": percentile,
            "multi_period_evidence": multi_period_evidence or {},
            "advantages": list(dict.fromkeys(advantages))[:3],
            "risks": list(dict.fromkeys(risks))[:3],
            "style_evidence": style_evidence,
            "style_drift_evidence": style_drift_evidence,
            "holding_comparison_evidence": holding_comparison_evidence,
            "holding_stability_evidence": holding_stability_evidence,
            "manager_stability_evidence": manager_stability_evidence,
            "manager_tenure_performance_evidence": manager_tenure_performance_evidence,
            "scale_trend_evidence": scale_trend_evidence,
            "drawdown_recovery_evidence": drawdown_recovery_evidence,
            "research_evidence": research_evidence,
            "attribution_evidence": attribution_summary,
            "boundary": "基金评价结论；不提供买卖建议。Barra/Brinson 只解释，不改变评分。",
        }

    @classmethod
    def _detail_highlights(
        cls,
        evaluation: Dict[str, Any],
        holding_experience: Dict[str, Any],
        fallback_as_of: Any = None,
    ) -> List[Dict[str, Any]]:
        """生成详情页与 AI 共用的亮点/风险证据，不把弱样本强行解读成结论。"""
        evaluation_result = evaluation.get("evaluation") or {}
        peer_metrics = evaluation_result.get("peer_percentiles") or {}
        peer_context = evaluation.get("peer_context") or {}
        evaluation_window = str(peer_context.get("metric_window") or "1y")
        window_label = {"6m": "近 6 月", "1y": "近 1 年", "3y": "近 3 年"}.get(
            evaluation_window,
            evaluation_window,
        )
        as_of_date = (evaluation.get("target") or {}).get("as_of_date") or fallback_as_of
        highlights: List[Dict[str, Any]] = []

        metric_specs = (
            ("annualized_return", "收益同类位置", "收益", "年化收益"),
            ("excess_return", "超额收益同类位置", "超额收益", "超额收益"),
            ("max_drawdown", "回撤控制同类位置", "回撤控制", "最大回撤"),
            ("sharpe_ratio", "Sharpe 同类位置", "风险调整后收益", "Sharpe"),
            ("information_ratio", "信息比率同类位置", "超额效率", "信息比率"),
            ("tracking_error", "跟踪误差同类位置", "跟踪稳定性", "跟踪误差"),
            ("absolute_tracking_difference", "跟踪差异同类位置", "跟踪偏离", "跟踪差异绝对值"),
            ("expense_ratio", "基础费率同类位置", "基础费率", "管理费与托管费等基础费率之和"),
            ("aum", "规模同类位置", "基金规模", "基金规模"),
        )
        for metric_name, label, _, value_name in metric_specs:
            metric = peer_metrics.get(metric_name) or {}
            percentile = cls._number(metric.get("percentile"))
            if metric.get("sample_status") != "sufficient" or percentile is None:
                continue
            tone = "strength" if percentile >= 80 else "risk" if percentile <= 20 else None
            if tone is None:
                continue
            value = cls._highlight_metric_value(metric)
            rank = metric.get("rank")
            peer_count = metric.get("peer_count")
            position = (
                f"同类第 {int(rank)} / {int(peer_count)} 名（有利分位 {percentile:.0f}%）"
                if rank is not None and peer_count
                else f"同类有利分位 {percentile:.0f}%"
            )
            metric_period = "最新" if metric_name in {"expense_ratio", "aum"} else window_label
            detail = f"{metric_period}{value_name}{f' {value}' if value else ''}，{position}。"
            if metric_name == "expense_ratio":
                detail += " 仅包含已披露基础费率，不代表完整持有成本。"
            elif metric_name == "aum":
                detail += " 规模只是产品承载与流动性的代理证据，不等于业绩保证。"
            highlights.append({
                "id": f"peer_{metric_name}",
                "tone": tone,
                "label": label,
                "value": value or f"{percentile:.0f}%",
                "detail": detail,
                "source": "category_peer_percentile",
                "as_of_date": as_of_date,
                "metric_name": metric_name,
            })

        period = next(
            (
                item for item in holding_experience.get("periods") or []
                if int(item.get("months") or 0) == 12
                and item.get("status") == "sufficient"
                and int(item.get("sample_count") or 0) >= 20
            ),
            None,
        )
        if period:
            probability = cls._number(period.get("positive_probability"))
            worst_return = cls._number(period.get("worst_return"))
            if probability is not None:
                holding_detail = f"将每个历史净值日当作买入日，回放 {int(period.get('sample_count') or 0)} 次。"
                if worst_return is not None:
                    holding_detail = (
                        f"将每个历史净值日当作买入日，回放 {int(period.get('sample_count') or 0)} 次；"
                        f"最差一次 {worst_return * 100:.1f}%。"
                    )
                highlights.append({
                    "id": "holding_experience_12m",
                    "tone": "neutral",
                    "label": "12 个月历史持有体验",
                    "value": f"{probability * 100:.0f}% 正收益概率",
                    "detail": holding_detail + " 这是历史回放，不是未来预测。",
                    "source": holding_experience.get("source") or "local.postgres.fund_nav",
                    "as_of_date": holding_experience.get("sample_end") or as_of_date,
                    "metric_name": "holding_positive_probability_12m",
                })

        strengths = [item for item in highlights if item["tone"] == "strength"]
        risks = [item for item in highlights if item["tone"] == "risk"]
        neutral = [item for item in highlights if item["tone"] == "neutral"]
        selected = [*strengths[:3], *risks[:2], *neutral[:1]]
        for item in [*strengths[3:], *risks[2:], *neutral[1:]]:
            if len(selected) >= 6:
                break
            selected.append(item)
        return selected

    @classmethod
    def _plain_language_brief(
        cls,
        fund: Dict[str, Any],
        assessment_summary: Dict[str, Any],
        detail_highlights: List[Dict[str, Any]],
        holding_experience: Dict[str, Any],
    ) -> Dict[str, Any]:
        """把已有证据压缩为普通用户可读、可复制的基金速览。"""
        fund_name = str(fund.get("name") or fund.get("wind_code") or "该基金")
        as_of_date = fund.get("nav_date") or fund.get("updated_at")
        sections: List[Dict[str, Any]] = []

        verdict = str(assessment_summary.get("verdict") or "").strip()
        peer_group = str(assessment_summary.get("peer_group") or "").strip()
        evaluation_text = f"归入{peer_group}。{verdict}" if peer_group else verdict
        if evaluation_text:
            sections.append({
                "key": "evaluation",
                "label": "同类评价",
                "text": evaluation_text,
                "status": "available" if assessment_summary.get("score") is not None else "partial_evidence",
                "source": "professional_classification_evaluation",
                "as_of_date": as_of_date,
            })

        strength = next((item for item in detail_highlights if item.get("tone") == "strength"), None)
        sections.append({
            "key": "strength",
            "label": "主要亮点",
            "text": (
                f"{strength.get('label')}：{strength.get('detail')}"
                if strength
                else "当前没有达到同类有利分位 80% 的明确优势，暂不强行总结亮点。"
            ),
            "status": "available" if strength else "insufficient_evidence",
            "source": strength.get("source") if strength else "category_peer_percentile",
            "as_of_date": strength.get("as_of_date") if strength else as_of_date,
            "evidence_id": strength.get("id") if strength else None,
        })

        risk = next((item for item in detail_highlights if item.get("tone") == "risk"), None)
        sections.append({
            "key": "risk",
            "label": "需要留意",
            "text": (
                f"{risk.get('label')}：{risk.get('detail')}"
                if risk
                else "当前没有落入同类有利分位 20% 以下的明显短板，但这不代表基金没有风险。"
            ),
            "status": "available" if risk else "insufficient_evidence",
            "source": risk.get("source") if risk else "category_peer_percentile",
            "as_of_date": risk.get("as_of_date") if risk else as_of_date,
            "evidence_id": risk.get("id") if risk else None,
        })

        style_evidence = assessment_summary.get("style_evidence") or {}
        holding_comparison = assessment_summary.get("holding_comparison_evidence") or {}
        research_evidence = assessment_summary.get("research_evidence") or {}
        style_labels = [str(item) for item in style_evidence.get("labels") or [] if item]
        style_note = str(style_evidence.get("note") or "").strip()
        research_note = str(research_evidence.get("note") or "").strip()
        style_research_parts = []
        if style_labels:
            style_research_parts.append(f"公开持仓风格标签为{'、'.join(style_labels[:4])}。")
        elif style_note:
            style_research_parts.append(style_note)
        if research_note:
            style_research_parts.append(research_note)
        if style_research_parts:
            sections.append({
                "key": "style_research",
                "label": "风格与调研",
                "text": "".join(style_research_parts),
                "status": (
                    "available"
                    if style_labels or int(research_evidence.get("count") or 0) > 0
                    else "partial_evidence"
                ),
                "source": "holding_style_and_research_memos",
                "as_of_date": research_evidence.get("latest_date") or as_of_date,
            })

        style_drift = assessment_summary.get("style_drift_evidence") or {}
        style_drift_note = str(style_drift.get("note") or "").strip()
        if style_drift_note:
            sections.append({
                "key": "style_drift",
                "label": "风格变化",
                "text": style_drift_note,
                "status": (
                    "available"
                    if style_drift.get("status") == "available"
                    else "partial_evidence"
                ),
                "source": style_drift.get("source") or "local.postgres.holding_style_snapshots",
                "as_of_date": style_drift.get("latest_quarter") or as_of_date,
            })

        holding_comparison_note = str(holding_comparison.get("note") or "").strip()
        if holding_comparison_note:
            sections.append({
                "key": "holding_comparison",
                "label": "持仓同类画像",
                "text": holding_comparison_note,
                "status": (
                    "available"
                    if holding_comparison.get("status") == "peer_comparison_ready"
                    else "partial_evidence"
                ),
                "source": "cross_market_holding_peer_comparison_v1",
                "as_of_date": holding_comparison.get("quarter") or as_of_date,
            })

        holding_stability = assessment_summary.get("holding_stability_evidence") or {}
        holding_stability_note = str(holding_stability.get("note") or "").strip()
        if holding_stability_note:
            sections.append({
                "key": "holding_stability",
                "label": "持仓延续性",
                "text": holding_stability_note,
                "status": (
                    "available"
                    if holding_stability.get("status") == "available"
                    else "partial_evidence"
                ),
                "source": "consecutive_quarter_top10_normalized_overlap_v1",
                "as_of_date": holding_stability.get("latest_quarter") or as_of_date,
            })

        manager_stability = assessment_summary.get("manager_stability_evidence") or {}
        manager_stability_note = str(manager_stability.get("note") or "").strip()
        if manager_stability_note:
            sections.append({
                "key": "manager_stability",
                "label": "经理团队",
                "text": manager_stability_note,
                "status": (
                    "available"
                    if manager_stability.get("status") != "unavailable"
                    else "partial_evidence"
                ),
                "source": manager_stability.get("source") or "local.postgres.manager_fund_tenures",
                "as_of_date": manager_stability.get("as_of_date") or as_of_date,
            })

        manager_tenure_performance = assessment_summary.get("manager_tenure_performance_evidence") or {}
        manager_tenure_note = str(manager_tenure_performance.get("note") or "").strip()
        if manager_tenure_note and manager_tenure_performance.get("status") != "not_applicable":
            sections.append({
                "key": "manager_tenure_performance",
                "label": "现任经理表现",
                "text": manager_tenure_note,
                "status": (
                    "available"
                    if manager_tenure_performance.get("coverage_status") == "full_tenure"
                    else "partial_evidence"
                ),
                "source": manager_tenure_performance.get("source") or "local.postgres.metric_snapshots.manager_tenure",
                "as_of_date": manager_tenure_performance.get("actual_end_date") or as_of_date,
            })

        scale_trend = assessment_summary.get("scale_trend_evidence") or {}
        scale_trend_note = str(scale_trend.get("note") or "").strip()
        if scale_trend_note:
            sections.append({
                "key": "scale_trend",
                "label": "规模变化",
                "text": scale_trend_note,
                "status": (
                    "available"
                    if scale_trend.get("status") != "insufficient_evidence"
                    else "partial_evidence"
                ),
                "source": scale_trend.get("source") or "local.postgres.fund_asset_allocations",
                "as_of_date": scale_trend.get("latest_report_date") or as_of_date,
            })

        drawdown_recovery = assessment_summary.get("drawdown_recovery_evidence") or {}
        drawdown_recovery_note = str(drawdown_recovery.get("note") or "").strip()
        if drawdown_recovery_note:
            sections.append({
                "key": "drawdown_recovery",
                "label": "回撤修复",
                "text": drawdown_recovery_note,
                "status": (
                    "available"
                    if drawdown_recovery.get("status") != "insufficient_evidence"
                    else "partial_evidence"
                ),
                "source": drawdown_recovery.get("source") or "local.postgres.fund_nav",
                "as_of_date": drawdown_recovery.get("history_end") or as_of_date,
            })

        period = next(
            (
                item for item in holding_experience.get("periods") or []
                if int(item.get("months") or 0) == 12 and item.get("status") == "sufficient"
            ),
            None,
        )
        if period:
            sample_count = int(period.get("sample_count") or 0)
            positive_probability = cls._number(period.get("positive_probability"))
            worst_return = cls._number(period.get("worst_return"))
            target_probability = next(
                (
                    cls._number(item.get("probability"))
                    for item in period.get("return_threshold_probabilities") or []
                    if abs(float(item.get("threshold") or 0) - 0.03) < 1e-9
                ),
                None,
            )
            holding_parts = [f"历史回放 {sample_count} 次"]
            if positive_probability is not None:
                holding_parts.append(f"持有 12 个月正收益概率 {positive_probability * 100:.0f}%")
            if target_probability is not None:
                holding_parts.append(f"收益超过 3% 的概率 {target_probability * 100:.0f}%")
            if worst_return is not None:
                holding_parts.append(f"最差一次 {worst_return * 100:.1f}%")
            sections.append({
                "key": "holding",
                "label": "历史持有体验",
                "text": "，".join(holding_parts) + "。历史结果不代表未来。",
                "status": "available",
                "source": holding_experience.get("source") or "local.postgres.fund_nav",
                "as_of_date": holding_experience.get("sample_end") or as_of_date,
            })

        evidence_count = sum(1 for item in sections if item.get("status") == "available")
        boundary = "基金速览基于专业分类、同类评价、公开持仓、调研纪要和真实净值；用于基金研究，不构成投资建议。"
        copy_lines = [fund_name]
        copy_lines.extend(f"{item['label']}：{item['text']}" for item in sections)
        copy_lines.append(boundary)
        return {
            "status": "available" if evidence_count >= 3 else "partial_evidence" if sections else "insufficient_evidence",
            "title": "一分钟看懂这只基金",
            "fund_name": fund_name,
            "evidence_count": evidence_count,
            "items": sections,
            "copy_text": "\n".join(copy_lines),
            "boundary": boundary,
        }

    @classmethod
    def _highlight_metric_value(cls, metric: Dict[str, Any]) -> str:
        value = cls._number(metric.get("value"))
        if value is None:
            return ""
        unit = metric.get("unit")
        if unit == "percent":
            return f"{value * 100:.2f}%"
        if unit == "cny_100m":
            return f"{value:.2f} 亿元"
        if unit == "score":
            return f"{value:.1f} 分"
        return f"{value:.2f}"

    @staticmethod
    def _number(value: Any) -> Optional[float]:
        try:
            result = float(value)
        except (TypeError, ValueError):
            return None
        return result if result == result else None

    @staticmethod
    def _assessment_attribution_summary(
        attribution: Dict[str, Any],
        include_attribution: bool,
    ) -> Dict[str, Any]:
        if not include_attribution or attribution.get("status") in {None, "not_requested"}:
            return {
                "status": "not_run",
                "mode": "on_demand",
                "headline": "尚未运行现场归因",
                "detail": "运行后再把 Barra 持仓画像和 Brinson 收益来源纳入解释。",
                "quarter": None,
                "active_return": None,
                "coverage": None,
                "formal_barra_ready": False,
            }

        brinson = attribution.get("brinson") or {}
        barra = attribution.get("barra") or {}
        cross_market = attribution.get("cross_market_holding_profile") or {}
        origin = attribution.get("evidence_origin") or {}
        if origin.get("mode") == "not_run":
            return {
                "status": "not_run",
                "mode": "on_demand",
                "headline": "尚未运行现场归因",
                "detail": "点击现场分析后，再把 Barra 持仓画像和 Brinson 收益来源纳入解释。",
                "quarter": origin.get("quarter"),
                "active_return": None,
                "coverage": None,
                "formal_barra_ready": False,
                "barra_descriptor_ready": False,
            }
        returns = brinson.get("returns") or {}
        coverage = brinson.get("coverage") or {}
        market_map = {
            str(item.get("market_code")): item
            for item in cross_market.get("markets") or []
            if item.get("market_code")
        }
        effects = [item for item in brinson.get("effects") or [] if item.get("value") is not None]
        residual = next((item for item in effects if item.get("name") == "residual"), None)
        explanatory_effects = [item for item in effects if item.get("name") != "residual"]
        strongest = max(
            explanatory_effects,
            key=lambda item: abs(float(item.get("value") or 0)),
            default=None,
        )
        status = brinson.get("status") or attribution.get("status") or "insufficient_evidence"

        if status == "not_applicable":
            headline = "股票行业归因不适用于当前基金"
            detail = (brinson.get("missing_items") or ["当前基金不适用股票行业归因。"])[:1][0]
        elif status == "insufficient_evidence":
            headline = "归因证据不足"
            detail = (brinson.get("missing_items") or ["公开持仓、基准或同期收益不足。"])[:1][0]
        else:
            active_return = returns.get("active")
            headline = (
                f"相对基准 {float(active_return) * 100:+.2f}%"
                if active_return is not None
                else "已生成部分归因证据"
            )
            if residual and (
                strongest is None
                or abs(float(residual.get("value") or 0)) > abs(float(strongest.get("value") or 0))
            ):
                detail = "未披露持仓与残差影响最大，结论只能解释公开披露部分。"
            elif strongest:
                detail = f"已披露部分中，{strongest.get('label')}影响最大。"
            else:
                detail = "已生成行业配置与选择效应。"

        return {
            "status": status,
            "mode": origin.get("mode") or "available",
            "headline": headline,
            "detail": detail,
            "quarter": attribution.get("quarter") or origin.get("quarter"),
            "active_return": returns.get("active"),
            "coverage": coverage.get("portfolio_holdings"),
            "formal_barra_ready": bool(barra.get("formal_model_ready")),
            "barra_descriptor_ready": bool(barra.get("descriptor_model_ready")),
            "a_share_disclosed_weight": (market_map.get("CN_A") or {}).get("disclosed_weight"),
            "hong_kong_disclosed_weight": (market_map.get("HK") or {}).get("disclosed_weight"),
            "cross_market_labels": cross_market.get("labels") or [],
        }

    @classmethod
    def project_product_positioning_style(
        cls,
        fund: Dict[str, Any],
        classification: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        """从标准同类组和可核验基准生成产品定位标签，不读取基金名称。"""
        evidence: List[Dict[str, Any]] = []
        seen = set()

        def append(value: str, source: str, basis: str, confidence: float, scope: str, caveat: str) -> None:
            canonical = cls.canonical_style(value)
            if not canonical or canonical in seen:
                return
            seen.add(canonical)
            evidence.append({
                "value": canonical,
                "status": "derived",
                "source": source,
                "basis": basis,
                "confidence": confidence,
                "evidence_scope": scope,
                "caveat": caveat,
            })

        peer_group = str(
            classification.get("peer_group_name")
            or classification.get("peer_group")
            or fund.get("standardized_peer_group_name")
            or ""
        ).strip()
        peer_styles = list(cls.PEER_GROUP_STYLE_RULES.get(peer_group) or [])
        if peer_group.startswith("主动权益-行业/"):
            peer_styles.append("行业主题")
        if peer_group.startswith("指数-") and str(
            classification.get("strategy_family_key") or fund.get("strategy_family_key") or ""
        ) == "index_sector":
            peer_styles.append("行业主题")
        for value in peer_styles:
            append(
                value,
                "standardized_peer_group",
                peer_group,
                0.95,
                "product_classification",
                "标准同类组反映产品分类定位，不等同于实际持仓风格。",
            )

        benchmark_mapping = classification.get("benchmark_mapping") or {}
        benchmark_name = str(
            benchmark_mapping.get("benchmark_name")
            or classification.get("primary_benchmark")
            or fund.get("benchmark_name")
            or ""
        ).strip()
        strategy_family = str(
            classification.get("strategy_family_key")
            or fund.get("strategy_family_key")
            or ""
        ).lower()
        active_passive = str(
            classification.get("active_passive")
            or fund.get("active_passive")
            or ""
        ).lower()
        is_index_product = (
            active_passive == "passive"
            or strategy_family.startswith("index")
            or peer_group.startswith("指数-")
            or peer_group.startswith("指数增强-")
        )
        if not is_index_product or not benchmark_name:
            return evidence
        matched_rule = next(
            (
                (benchmark, values)
                for benchmark, values in sorted(
                    cls.BENCHMARK_STYLE_RULES.items(),
                    key=lambda item: len(item[0]),
                    reverse=True,
                )
                if benchmark.lower() in benchmark_name.lower()
            ),
            None,
        )
        if matched_rule is None:
            return evidence
        _, values = matched_rule
        for value in values:
            append(
                value,
                "standardized_benchmark",
                benchmark_name,
                0.94,
                "tracked_benchmark",
                "跟踪基准反映指数产品的主要暴露。",
            )
        return evidence

    @classmethod
    def _merge_style_evidence(cls, *groups: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        result: List[Dict[str, Any]] = []
        seen = set()
        for group in groups:
            for item in group or []:
                key = (cls.normalize_style(str(item.get("value") or "")), str(item.get("source") or ""))
                if not key[0] or key in seen:
                    continue
                seen.add(key)
                result.append(dict(item))
        return result

    @classmethod
    def canonical_style(cls, value: Any) -> str:
        raw = str(value or "").strip()
        normalized = cls.normalize_style(raw)
        if not normalized:
            return ""
        quantitative_aliases = {
            "偏大盘": "大盘",
            "偏小盘": "小盘",
            "偏成长": "成长",
            "偏价值": "价值",
            "价值成长均衡": "均衡",
            "低波": "低波稳健",
        }
        if raw in quantitative_aliases:
            return quantitative_aliases[raw]
        for canonical, aliases in cls.STYLE_LABEL_ALIASES.items():
            if normalized in {cls.normalize_style(item) for item in (canonical, *aliases)}:
                return canonical
        return raw

    @staticmethod
    def normalize_style(value: str) -> str:
        return " ".join(str(value or "").lower().replace("型", "").replace("_", " ").replace("-", " ").split())

    @classmethod
    def project_style_profile(
        cls,
        profile: Dict[str, Any],
        reports: Optional[List[Dict[str, Any]]] = None,
        holding_style: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """按统一证据优先级输出主风格与全部来源，不从基金名称推断。"""
        reports = reports or []
        memo_classifications = []
        memo_style_labels = []
        manager_memo_classifications = []
        manager_memo_style_labels = []
        for report in reports:
            if "fund_classifications" in report:
                memo_classifications.extend(report.get("fund_classifications") or [])
                memo_style_labels.extend(report.get("fund_style_labels") or [])
                manager_memo_classifications.extend(report.get("manager_classifications") or [])
                manager_memo_style_labels.extend(report.get("manager_style_labels") or [])
            elif report.get("evidence_scope") == "manager_level":
                manager_memo_classifications.extend(report.get("classifications") or [])
                manager_memo_style_labels.extend(report.get("style_labels") or [])
            else:
                memo_classifications.extend(report.get("classifications") or [])
                memo_style_labels.extend(report.get("style_labels") or [])
        quantitative_evidence = profile.get("holding_style_evidence") or []
        bond_quantitative_evidence = profile.get("bond_holding_style_evidence") or []
        fof_quantitative_evidence = profile.get("fof_holding_style_evidence") or []
        quantitative_style = (
            cls._holding_style_projection(holding_style)
            if holding_style
            else cls._candidate_holding_style(quantitative_evidence)
        )
        suggestions = profile.get("memo_style_suggestions") or []
        derived = profile.get("derived_style_evidence") or []
        label_evidence: List[Dict[str, Any]] = []
        seen = set()

        def append_label(
            value: Any,
            status: str,
            source: str,
            basis: str = "",
            caveat: str = "",
            extra: Optional[Dict[str, Any]] = None,
        ) -> None:
            label = cls.canonical_style(value)
            if not label:
                return
            key = (" ".join(label.lower().replace("型", "").replace("_", " ").split()), status)
            if key in seen:
                return
            seen.add(key)
            label_evidence.append({
                "value": label,
                "status": status,
                "source": source,
                "basis": basis,
                "caveat": caveat,
                **(extra or {}),
            })

        append_label(profile.get("style_label"), "confirmed", "fund_research_profile")
        for item in ((profile.get("evidence") or {}).get("research_memos") or []):
            if item.get("kind") == "style_label" and item.get("review_status") == "confirmed":
                append_label(
                    item.get("value"),
                    "confirmed",
                    "confirmed_fund_memo",
                    str(item.get("excerpt") or ""),
                )
        for item in profile.get("style_tag_evidence") or []:
            if item.get("value") and str(item.get("evidence_level") or item.get("status") or "").lower() in {
                "confirmed", "manual", "reviewed",
            }:
                append_label(
                    item.get("value"),
                    "confirmed",
                    str(item.get("source_key") or item.get("source") or "style_tag_evidence"),
                    str(item.get("source_label") or ""),
                )
        known_styles = {
            " ".join(str(alias).lower().replace("型", "").replace("_", " ").split())
            for canonical, aliases in cls.STYLE_LABEL_ALIASES.items()
            for alias in (canonical, *aliases)
        }
        for value in profile.get("filter_style_tags") or profile.get("strategy_tags") or []:
            normalized = " ".join(str(value).lower().replace("型", "").replace("_", " ").split())
            if normalized in known_styles:
                append_label(value, "confirmed", "fund_research_profile_strategy_tag")
        for value in memo_style_labels:
            append_label(value, "confirmed", "reviewed_fund_memo")
        for item in quantitative_evidence:
            append_label(
                item.get("value"),
                "quantitative",
                "holding_style_peer_percentile",
                str(item.get("basis") or ""),
                str(item.get("caveat") or ""),
                {key: item.get(key) for key in (
                    "quarter", "peer_group_id", "peer_group_name", "sample_size",
                    "minimum_peer_count", "percentiles", "data_source",
                ) if item.get(key) is not None},
            )
        for item in bond_quantitative_evidence:
            append_label(
                item.get("value"),
                "quantitative",
                "public_bond_holding_profile",
                str(item.get("basis") or ""),
                str(item.get("caveat") or ""),
                {key: item.get(key) for key in ("period_count", "data_source") if item.get(key) is not None},
            )
        for item in fof_quantitative_evidence:
            append_label(
                item.get("value"),
                "quantitative",
                "public_fof_underlying_holdings",
                str(item.get("basis") or ""),
                str(item.get("caveat") or ""),
                {key: item.get(key) for key in (
                    "report_date", "disclosed_fund_count", "disclosed_nav_ratio",
                    "top5_nav_ratio", "classification_coverage",
                    "classification_distribution", "data_source",
                ) if item.get(key) is not None},
            )
        if holding_style:
            for value in quantitative_style.get("labels") or []:
                append_label(
                    value,
                    "quantitative",
                    "holding_style_peer_percentile",
                    " · ".join(str(item) for item in (
                        quantitative_style.get("quarter"),
                        quantitative_style.get("peer_group_name"),
                    ) if item),
                    str(quantitative_style.get("model_scope") or ""),
                    {"data_source": quantitative_style.get("source")},
                )
        for item in suggestions:
            append_label(
                item.get("value"),
                "confirmed" if item.get("status") == "confirmed" else "llm_suggested",
                "fund_specific_research_memo",
                "、".join(str(title) for title in (item.get("report_titles") or [])[:2]),
            )
        for item in derived:
            append_label(
                item.get("value"),
                "derived",
                str(item.get("source") or "product_positioning"),
                str(item.get("basis") or ""),
                str(item.get("caveat") or ""),
            )

        priority = {"confirmed": 0, "quantitative": 1, "llm_suggested": 2, "derived": 3}
        label_evidence.sort(key=lambda item: priority.get(str(item.get("status") or ""), 9))
        primary = label_evidence[0] if label_evidence else None
        return {
            "primary_label": primary.get("value") if primary else None,
            "status": primary.get("status") if primary else "unavailable",
            "primary_evidence": primary,
            "label_evidence": label_evidence,
            "style_label": profile.get("style_label"),
            "strategy_tags": profile.get("strategy_tags") or [],
            "memo_classifications": list(dict.fromkeys(str(item) for item in memo_classifications if item)),
            "memo_style_labels": list(dict.fromkeys(str(item) for item in memo_style_labels if item)),
            "manager_memo_classifications": list(dict.fromkeys(str(item) for item in manager_memo_classifications if item)),
            "manager_memo_style_labels": list(dict.fromkeys(str(item) for item in manager_memo_style_labels if item)),
            "quantitative_labels": list(dict.fromkeys([
                *(quantitative_style.get("labels") or []),
                *(str(item.get("value") or "") for item in bond_quantitative_evidence if item.get("value")),
                *(str(item.get("value") or "") for item in fof_quantitative_evidence if item.get("value")),
            ])),
            "bond_holding_style": profile.get("bond_holding_style_profile") or {},
            "fof_holding_style": profile.get("fof_holding_style_profile") or {},
            "suggested_labels": suggestions,
            "derived_labels": derived,
            "holding_style": quantitative_style,
            "source": "fund_research_profile+holding_style_peer_percentile+public_bond_holding_profile+public_fof_underlying_holdings+scoped_research_memos+product_positioning",
        }

    @classmethod
    def _style_profile(
        cls,
        profile: Dict[str, Any],
        reports: List[Dict[str, Any]],
        holding_style: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """兼容旧调用；风格规则只保留在统一投影 Interface。"""
        return cls.project_style_profile(profile, reports, holding_style)

    @staticmethod
    def project_analysis_evidence(
        attribution: Dict[str, Any],
        style_profile: Dict[str, Any],
        holding_style_drift: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """把 Barra、Brinson 与补充证据投影为 AI 可直接消费的事实。"""
        origin = attribution.get("evidence_origin") or {}
        common = {
            "evidence_origin": origin,
            "benchmark": attribution.get("benchmark"),
            "benchmark_source": attribution.get("benchmark_source"),
            "benchmark_detail": attribution.get("benchmark_detail") or {},
        }
        return {
            "factor_evidence": {
                **(attribution.get("barra") or {}),
                "holding_style_peer_evidence": style_profile.get("holding_style") or {},
                "holding_style_drift_evidence": holding_style_drift or {},
                "supplementary_nav_factor": attribution.get("nav_factor_lens") or {},
                **common,
            },
            "attribution_evidence": {
                **(attribution.get("brinson") or {}),
                "supplementary_nav_return": attribution.get("nav_return_attribution") or {},
                **common,
            },
        }

    def _load_holding_style(self, wind_code: str) -> Dict[str, Any]:
        repo = self.holding_style_repo
        if repo is None:
            from repositories import get_holding_style_snapshot_repo

            repo = get_holding_style_snapshot_repo()
            self.holding_style_repo = repo
        return (repo.get_latest_map([wind_code]) or {}).get(wind_code) or {}

    def _load_holding_style_drift(self, wind_code: str) -> Dict[str, Any]:
        repo = self.holding_style_repo
        if repo is None:
            from repositories import get_holding_style_snapshot_repo

            repo = get_holding_style_snapshot_repo()
            self.holding_style_repo = repo
        rows = repo.list_history(wind_code, limit=6) if hasattr(repo, "list_history") else []
        return HoldingStyleDriftService.analyze(wind_code, rows)

    @classmethod
    def _candidate_holding_style(cls, evidence: List[Dict[str, Any]]) -> Dict[str, Any]:
        if not evidence:
            return cls._holding_style_projection({})
        first = evidence[0]
        return cls._holding_style_projection({
            "status": "peer_percentile_ready",
            "quarter": first.get("quarter"),
            "peer_group_id": first.get("peer_group_id"),
            "peer_group_name": first.get("peer_group_name"),
            "peer_sample_size": first.get("sample_size"),
            "minimum_peer_count": first.get("minimum_peer_count"),
            "peer_percentiles": first.get("percentiles") or [],
            "style_labels": [item.get("value") for item in evidence if item.get("value")],
            "source": first.get("source") or "holding_style_peer_percentile",
        })

    @staticmethod
    def _holding_style_projection(snapshot: Dict[str, Any]) -> Dict[str, Any]:
        import json

        def json_list(value: Any) -> List[Any]:
            if isinstance(value, str):
                try:
                    value = json.loads(value)
                except json.JSONDecodeError:
                    return []
            return value if isinstance(value, list) else []

        descriptors = json_list(snapshot.get("descriptors"))
        percentiles = json_list(snapshot.get("peer_percentiles"))
        labels = [str(item) for item in (snapshot.get("style_labels") or []) if item]
        sample_size = int(snapshot.get("peer_sample_size") or 0)
        minimum_peer_count = int(snapshot.get("minimum_peer_count") or 5)
        ready = bool(percentiles) and sample_size >= minimum_peer_count
        missing_items = [str(item) for item in json_list(snapshot.get("missing_items")) if item]
        if snapshot and not ready and not missing_items:
            missing_items.append(
                f"同季度同类描述子样本未达到 {minimum_peer_count} 只，只展示原始持仓描述子，不贴风格标签。"
            )
        snapshot_status = str(snapshot.get("status") or "")
        return {
            "status": "peer_percentile_ready" if ready and labels else "peer_percentile_neutral" if ready else "descriptor_ready" if descriptors else "insufficient_evidence" if snapshot_status == "insufficient_evidence" else "unavailable",
            "quarter": snapshot.get("quarter"),
            "peer_group_id": snapshot.get("peer_group_id"),
            "peer_group_key": snapshot.get("peer_group_key"),
            "peer_group_name": snapshot.get("peer_group_name"),
            "sample_size": sample_size,
            "minimum_peer_count": minimum_peer_count,
            "holdings_disclosed_weight": snapshot.get("holdings_disclosed_weight"),
            "descriptors": descriptors,
            "peer_percentiles": percentiles,
            "labels": labels if ready else [],
            "source": snapshot.get("source") or None,
            "model_scope": "公开持仓风格描述子与同类分位，不是完整 Barra 风险模型。",
            "missing_items": missing_items,
        }

    @property
    def manager_tenure_peer_ranking_service(self):
        if self._manager_tenure_peer_ranking_service is None:
            from services.manager_tenure_peer_ranking_service import ManagerTenurePeerRankingService

            self._manager_tenure_peer_ranking_service = ManagerTenurePeerRankingService()
        return self._manager_tenure_peer_ranking_service

    @staticmethod
    def project_rolling_metrics(panel: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
        result: Dict[str, Dict[str, Any]] = {}
        for item in panel:
            window = item.get("metric_window")
            metric_name = item.get("metric_name")
            if not window or not metric_name:
                continue
            result.setdefault(window, {})[metric_name] = item.get("metric_value")
            if item.get("as_of_date"):
                result[window]["as_of_date"] = item.get("as_of_date")
            if item.get("benchmark_code"):
                result[window]["benchmark_code"] = item.get("benchmark_code")
            details = item.get("details") if isinstance(item.get("details"), dict) else {}
            if window == "manager_tenure" and not result[window].get("tenure_coverage_status"):
                inferred_coverage_status = metric_details_coverage_status(details)
                if inferred_coverage_status:
                    result[window]["tenure_coverage_status"] = inferred_coverage_status
                inferred_coverage = build_manager_tenure_coverage(
                    details.get("requested_start_date") or details.get("manager_tenure_start"),
                    details.get("actual_start_date") or details.get("window_start_date"),
                    details.get("actual_end_date") or details.get("window_end_date"),
                    int(details.get("actual_observations") or 0),
                )
                if inferred_coverage.get("tenure_coverage_status") != "unavailable":
                    for coverage_key, coverage_value in inferred_coverage.items():
                        result[window].setdefault(coverage_key, coverage_value)
            for key in (
                "window_start_date",
                "window_end_date",
                "actual_observations",
                "expected_observations",
                "benchmark_observations",
                "requested_start_date",
                "actual_start_date",
                "actual_end_date",
                "requested_tenure_days",
                "metric_coverage_days",
                "start_lag_days",
                "tenure_coverage_ratio",
                "tenure_coverage_status",
                "peer_ranking_eligible",
            ):
                if details.get(key) is not None:
                    result[window][key] = details.get(key)
        return result

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
