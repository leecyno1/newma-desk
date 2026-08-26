"""
证据型研究备忘录服务

把基金基础信息、研究画像、滚动指标、专业评分和数据质量组织成可追溯基金研究 memo。
"""
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional

from services.data_quality_service import DataQualityService
from services.professional_scoring_service import ProfessionalScoringService


class ResearchMemoService:
    """生成可追溯证据、事实、推断、反证和观察清单。"""

    def __init__(
        self,
        data_quality_service: Optional[DataQualityService] = None,
        scoring_service: Optional[ProfessionalScoringService] = None,
    ):
        self.data_quality_service = data_quality_service or DataQualityService()
        self.scoring_service = scoring_service or ProfessionalScoringService(data_quality_service=self.data_quality_service)

    def build_fund_memo(self, fund_code: str) -> Dict[str, Any]:
        from repositories import get_fund_repo, get_metric_snapshot_repo, get_research_profile_repo

        fund_repo = get_fund_repo()
        metric_repo = get_metric_snapshot_repo()
        profile_repo = get_research_profile_repo()

        fund = fund_repo.get_fund_by_identifier(fund_code) or {}
        wind_code = fund.get("wind_code") or fund_code
        profile = profile_repo.get_profile(wind_code) or {}
        metric_panel = metric_repo.get_latest_panel("fund", wind_code)
        metrics = self._metrics_by_window(metric_panel)
        quality = self._safe_quality(wind_code)
        scoring = self._safe_scoring(wind_code)

        evidence_table: List[Dict[str, Any]] = []

        def add_evidence(source: str, field: str, value: Any, as_of_date: Any = None, confidence: str = "high") -> str:
            evidence_id = f"E{len(evidence_table) + 1:03d}"
            evidence_table.append({
                "id": evidence_id,
                "source": source,
                "field": field,
                "value": self._json_safe(value),
                "as_of_date": self._json_safe(as_of_date),
                "confidence": confidence,
            })
            return evidence_id

        fund_name_id = add_evidence("funds", "name", fund.get("name") or wind_code, fund.get("updated_at"))
        fund_type_id = add_evidence("funds", "type", fund.get("type") or "未分类", fund.get("updated_at"))
        nav_id = add_evidence("funds", "nav", fund.get("nav"), fund.get("nav_date"), "medium" if fund.get("nav") is None else "high")
        asset_id = add_evidence("funds", "total_asset", fund.get("total_asset"), fund.get("updated_at"), "medium")

        benchmark_id = add_evidence("fund_research_profiles", "primary_benchmark", profile.get("primary_benchmark") or "待映射", profile.get("updated_at"))
        peer_id = add_evidence("fund_research_profiles", "peer_group", profile.get("peer_group") or "待分类", profile.get("updated_at"))
        style_id = add_evidence("fund_research_profiles", "style_label", profile.get("style_label") or "待识别", profile.get("updated_at"))
        tenure_start_id = add_evidence(
            "fund_research_profiles",
            "manager_tenure_start",
            profile.get("manager_tenure_start") or "待补齐",
            profile.get("updated_at"),
            "medium" if not profile.get("manager_tenure_start") else "high",
        )

        one_year = metrics.get("1y", {})
        three_year = metrics.get("3y", {})
        tenure = metrics.get("manager_tenure", {})
        one_year_return_id = add_evidence("metric_snapshots", "1y.annualized_return", one_year.get("annualized_return"), one_year.get("as_of_date"), self._metric_confidence(one_year))
        one_year_drawdown_id = add_evidence("metric_snapshots", "1y.max_drawdown", one_year.get("max_drawdown"), one_year.get("as_of_date"), self._metric_confidence(one_year))
        three_year_return_id = add_evidence("metric_snapshots", "3y.annualized_return", three_year.get("annualized_return"), three_year.get("as_of_date"), self._metric_confidence(three_year))
        tenure_return_id = add_evidence("metric_snapshots", "manager_tenure.annualized_return", tenure.get("annualized_return"), tenure.get("as_of_date"), self._metric_confidence(tenure))
        tenure_days_id = add_evidence("metric_snapshots", "manager_tenure.tenure_days", tenure.get("tenure_days"), tenure.get("as_of_date"), self._metric_confidence(tenure))

        quality_id = add_evidence("data_quality_service", "score_status", {"score": quality.get("score"), "status": quality.get("status")}, None)
        quality_issues_id = add_evidence("data_quality_service", "issues", quality.get("issues", []), None, "medium")
        score_id = add_evidence(
            "professional_scoring_service",
            "overall_score",
            {"score": scoring.get("overall_score"), "grade": scoring.get("overall_grade")},
            scoring.get("as_of_date"),
            "medium" if scoring.get("missing_data") else "high",
        )

        facts = [
            {
                "statement": f"{fund.get('name') or wind_code}（{wind_code}）当前归类为 {fund.get('type') or '未分类'} 基金。",
                "evidence_ids": [fund_name_id, fund_type_id],
            },
            {
                "statement": f"研究画像将其放入 {profile.get('peer_group') or '待分类'}，主基准为 {profile.get('primary_benchmark') or '待映射'}。",
                "evidence_ids": [peer_id, benchmark_id, style_id],
            },
            {
                "statement": f"近一年年化收益 {self._format_percent(one_year.get('annualized_return'))}，最大回撤 {self._format_percent(one_year.get('max_drawdown'))}。",
                "evidence_ids": [one_year_return_id, one_year_drawdown_id],
            },
            {
                "statement": f"现任经理任期样本 {self._format_number(tenure.get('tenure_days'))} 天，任期年化收益 {self._format_percent(tenure.get('annualized_return'))}。",
                "evidence_ids": [tenure_days_id, tenure_return_id, tenure_start_id],
            },
            {
                "statement": f"专业评分为 {self._format_number(scoring.get('overall_score'))}，等级 {scoring.get('overall_grade') or '暂无'}；数据质量状态为 {quality.get('status') or 'unknown'}。",
                "evidence_ids": [score_id, quality_id],
            },
        ]

        inferences = self._build_inferences(
            scoring=scoring,
            quality=quality,
            one_year=one_year,
            three_year=three_year,
            evidence_ids={
                "score": score_id,
                "quality": quality_id,
                "one_year_return": one_year_return_id,
                "one_year_drawdown": one_year_drawdown_id,
                "three_year_return": three_year_return_id,
                "tenure_return": tenure_return_id,
            },
        )
        counter_thesis = self._build_counter_thesis(quality, scoring, one_year, profile, {
            "quality_issues": quality_issues_id,
            "one_year_drawdown": one_year_drawdown_id,
            "benchmark": benchmark_id,
            "asset": asset_id,
            "nav": nav_id,
        })
        watchlist = self._build_watchlist(quality, scoring, profile, one_year)
        executive_summary = self._executive_summary(scoring, quality, inferences, counter_thesis)
        markdown = self._markdown(
            wind_code=wind_code,
            fund=fund,
            executive_summary=executive_summary,
            facts=facts,
            inferences=inferences,
            counter_thesis=counter_thesis,
            watchlist=watchlist,
            evidence_table=evidence_table,
        )

        return {
            "memo_type": "fund_research",
            "target_type": "fund",
            "target_id": wind_code,
            "title": f"{fund.get('name') or wind_code} 基金研究备忘录",
            "executive_summary": executive_summary,
            "evidence_table": evidence_table,
            "facts": facts,
            "inferences": inferences,
            "counter_thesis": counter_thesis,
            "watchlist": watchlist,
            "research_memo_markdown": markdown,
            "audit": {
                "source_count": len({item["source"] for item in evidence_table}),
                "evidence_count": len(evidence_table),
                "generated_mode": "deterministic_evidence_backed",
                "data_quality_score": quality.get("score"),
                "data_quality_status": quality.get("status"),
                "scoring_method": scoring.get("calculation_method"),
                "generated_at": datetime.utcnow().isoformat(),
            },
        }

    def _safe_quality(self, wind_code: str) -> Dict[str, Any]:
        try:
            return self.data_quality_service.evaluate_fund(wind_code)
        except Exception as exc:
            return {"score": 0, "status": "unknown", "issues": [f"数据质量评估失败：{exc}"]}

    def _safe_scoring(self, wind_code: str) -> Dict[str, Any]:
        try:
            return self.scoring_service.score_fund(wind_code)
        except Exception as exc:
            return {
                "overall_score": 50,
                "overall_grade": "D",
                "missing_data": [f"专业评分失败：{exc}"],
                "calculation_method": "professional_metric_snapshot_v1_fallback",
            }

    def _metrics_by_window(self, panel: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
        metrics: Dict[str, Dict[str, Any]] = {}
        for item in panel:
            window = item.get("metric_window") or "latest"
            metric_name = item.get("metric_name")
            if not metric_name:
                continue
            window_metrics = metrics.setdefault(window, {})
            window_metrics[metric_name] = self._to_float(item.get("metric_value"))
            if item.get("as_of_date"):
                window_metrics["as_of_date"] = item.get("as_of_date")
        return metrics

    def _build_inferences(
        self,
        scoring: Dict[str, Any],
        quality: Dict[str, Any],
        one_year: Dict[str, Any],
        three_year: Dict[str, Any],
        evidence_ids: Dict[str, str],
    ) -> List[Dict[str, Any]]:
        overall_score = self._to_float(scoring.get("overall_score")) or 50
        quality_score = self._to_float(quality.get("score")) or 0
        one_year_return = self._to_float(one_year.get("annualized_return"))
        three_year_return = self._to_float(three_year.get("annualized_return"))
        drawdown = self._to_float(one_year.get("max_drawdown"))

        investability = "可进入候选池复核" if overall_score >= 70 and quality_score >= 70 else "仅适合观察或补数后复核"
        return_gap = None
        if one_year_return is not None and three_year_return is not None:
            return_gap = abs(one_year_return - three_year_return)

        inferences = [
            {
                "statement": f"综合评分和数据质量共同指向：当前结论为“{investability}”。",
                "basis_evidence_ids": [evidence_ids["score"], evidence_ids["quality"]],
                "confidence": "medium" if quality_score < 85 else "high",
                "assumption": "专业评分权重已按基金类型、滚动窗口和经理任期切片调整。",
            },
            {
                "statement": "若近一年收益与三年收益差异较小，则风格和收益持续性证据更强；反之需要解释阶段性行情暴露。",
                "basis_evidence_ids": [evidence_ids["one_year_return"], evidence_ids["three_year_return"]],
                "confidence": "medium" if return_gap is not None else "low",
                "assumption": f"当前收益差异为 {self._format_percent(return_gap)}。",
            },
            {
                "statement": "回撤是进入组合前的主要约束，需要与持仓集中度、行业暴露和组合已有风险源联动评估。",
                "basis_evidence_ids": [evidence_ids["one_year_drawdown"], evidence_ids["score"]],
                "confidence": "medium" if drawdown is not None else "low",
                "assumption": "当前 memo 尚未替代完整组合层压力测试。",
            },
        ]
        return inferences

    def _build_counter_thesis(
        self,
        quality: Dict[str, Any],
        scoring: Dict[str, Any],
        one_year: Dict[str, Any],
        profile: Dict[str, Any],
        evidence_ids: Dict[str, str],
    ) -> List[Dict[str, Any]]:
        counter_thesis = []
        if quality.get("issues"):
            counter_thesis.append({
                "statement": "若关键数据缺失或净值覆盖不足，当前评分可能高估投资可行性。",
                "evidence_ids": [evidence_ids["quality_issues"]],
                "severity": "high",
            })
        if not profile.get("primary_benchmark"):
            counter_thesis.append({
                "statement": "缺少明确主基准时，超额收益和信息比率难以形成高置信研究结论。",
                "evidence_ids": [evidence_ids["benchmark"]],
                "severity": "medium",
            })
        if (self._to_float(one_year.get("max_drawdown")) or 0) < -0.2:
            counter_thesis.append({
                "statement": "近一年回撤较深，若不能解释回撤来源和恢复路径，应降低配置优先级。",
                "evidence_ids": [evidence_ids["one_year_drawdown"]],
                "severity": "high",
            })
        if scoring.get("missing_data"):
            counter_thesis.append({
                "statement": "专业评分仍存在缺失输入，研究结论应保留人工复核门槛。",
                "evidence_ids": [evidence_ids["quality_issues"]],
                "severity": "medium",
            })
        if not counter_thesis:
            counter_thesis.append({
                "statement": "即便结构化证据较完整，仍需警惕规模变化、风格漂移和组合持仓拥挤度。",
                "evidence_ids": [evidence_ids["asset"], evidence_ids["nav"]],
                "severity": "medium",
            })
        return counter_thesis

    def _build_watchlist(
        self,
        quality: Dict[str, Any],
        scoring: Dict[str, Any],
        profile: Dict[str, Any],
        one_year: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        items = [
            {
                "item": "补齐或复核数据质量问题",
                "trigger": "data_quality.status != complete",
                "current": quality.get("status"),
                "action": "补净值、研究画像、任期起点或指标快照后再更新 memo。",
            },
            {
                "item": "跟踪专业评分下滑",
                "trigger": "overall_score < 70 或等级低于 B",
                "current": scoring.get("overall_score"),
                "action": "进入观察池，不直接进入核心池。",
            },
            {
                "item": "核对基准和同类分组",
                "trigger": "primary_benchmark 或 peer_group 缺失",
                "current": profile.get("primary_benchmark") or profile.get("peer_group"),
                "action": "由研究员确认基准、策略标签和同类池。",
            },
            {
                "item": "解释回撤来源",
                "trigger": "1Y 最大回撤低于 -20%",
                "current": one_year.get("max_drawdown"),
                "action": "拆解行业、风格、仓位和个股贡献。",
            },
        ]
        return items

    def _executive_summary(
        self,
        scoring: Dict[str, Any],
        quality: Dict[str, Any],
        inferences: List[Dict[str, Any]],
        counter_thesis: List[Dict[str, Any]],
    ) -> str:
        return (
            f"专业评分 {self._format_number(scoring.get('overall_score'))}（{scoring.get('overall_grade') or '暂无'}），"
            f"数据质量 {quality.get('status') or 'unknown'} / {self._format_number(quality.get('score'))}。"
            f"核心判断：{inferences[0]['statement']}主要反证：{counter_thesis[0]['statement']}"
        )

    def _markdown(
        self,
        wind_code: str,
        fund: Dict[str, Any],
        executive_summary: str,
        facts: List[Dict[str, Any]],
        inferences: List[Dict[str, Any]],
        counter_thesis: List[Dict[str, Any]],
        watchlist: List[Dict[str, Any]],
        evidence_table: List[Dict[str, Any]],
    ) -> str:
        lines = [
            f"# 基金研究备忘录：{fund.get('name') or wind_code}",
            "",
            "## 执行摘要",
            executive_summary,
            "",
            "## 事实",
        ]
        lines.extend([f"- {item['statement']}（证据：{', '.join(item['evidence_ids'])}）" for item in facts])
        lines.extend(["", "## 推断"])
        lines.extend([
            f"- {item['statement']}（置信度：{item['confidence']}；依据：{', '.join(item['basis_evidence_ids'])}）"
            for item in inferences
        ])
        lines.extend(["", "## 反证"])
        lines.extend([f"- {item['statement']}（强度：{item['severity']}；证据：{', '.join(item['evidence_ids'])}）" for item in counter_thesis])
        lines.extend(["", "## 研究观察清单"])
        lines.extend([f"- {item['item']}：{item['action']} 当前值：{item.get('current')}" for item in watchlist])
        lines.extend(["", "## 证据表"])
        lines.extend([
            f"- {item['id']} | {item['source']}.{item['field']} | {item['value']} | as_of={item['as_of_date']} | confidence={item['confidence']}"
            for item in evidence_table
        ])
        lines.extend(["", "## 风险提示", "本 memo 为结构化基金研究底稿，不构成投资建议；后续模块如需使用，应自行结合组合约束、流动性和适当性要求。"])
        return "\n".join(lines)

    def _metric_confidence(self, metric_window: Dict[str, Any]) -> str:
        return "high" if metric_window else "low"

    def _format_percent(self, value: Any) -> str:
        number = self._to_float(value)
        if number is None:
            return "暂无"
        return f"{number * 100:.2f}%"

    def _format_number(self, value: Any) -> str:
        number = self._to_float(value)
        if number is None:
            return "暂无"
        return f"{number:.2f}".rstrip("0").rstrip(".")

    def _to_float(self, value: Any) -> Optional[float]:
        if value is None:
            return None
        try:
            return float(Decimal(str(value)))
        except Exception:
            return None

    def _json_safe(self, value: Any) -> Any:
        if isinstance(value, Decimal):
            return float(value)
        if isinstance(value, (datetime, date)):
            return value.isoformat()
        if isinstance(value, dict):
            return {str(key): self._json_safe(item) for key, item in value.items()}
        if isinstance(value, list):
            return [self._json_safe(item) for item in value]
        return value
