"""
基金研究报告路由 - 报告生成、查询
"""
from fastapi import APIRouter, HTTPException, Query, BackgroundTasks, Body
from pydantic import BaseModel
from typing import List, Optional
from datetime import date, datetime
from decimal import Decimal
from uuid import UUID
import anyio
import logging
import os

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/reports", tags=["基金研究报告"])


class FundEvaluationAnalysisRequest(BaseModel):
    question: str = ""
    include_research: bool = True


def _json_safe(value):
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, Decimal):
        return float(value)
    return value


def _save_report_to_postgres(report_record: dict) -> Optional[str]:
    """保存 AI 研究报告到 PostgreSQL，返回报告 UUID。"""
    import json
    from sqlalchemy import text
    from database import get_engine

    sql = text(
        """
        INSERT INTO ai_analysis_reports (
            target_type, target_id, report_type, content, data_sources,
            research_reports_used, generation_params, created_at
        ) VALUES (
            :target_type, :target_id, :report_type, :content,
            CAST(:data_sources AS jsonb), :research_reports_used,
            CAST(:generation_params AS jsonb), NOW()
        )
        RETURNING id
        """
    )
    with get_engine().begin() as conn:
        row = conn.execute(
            sql,
            {
                "target_type": report_record["target_type"],
                "target_id": report_record["target_id"],
                "report_type": report_record.get("report_type"),
                "content": report_record.get("content"),
                "data_sources": json.dumps(_json_safe(report_record.get("data_sources") or {}), ensure_ascii=False),
                "research_reports_used": report_record.get("research_reports_used") or [],
                "generation_params": json.dumps(_json_safe(report_record.get("generation_params") or {}), ensure_ascii=False),
            },
        ).fetchone()
    return str(row[0]) if row else None


def _is_unusable_llm_report(content: str) -> bool:
    stripped = content.lstrip()
    return (
        stripped.startswith("## 报告生成失败")
        or "当前使用模拟数据" in content
        or "配置模型 API Key 后" in content
    )


def _brief_memo_summary(memo: dict, limit: int = 220) -> str:
    key_points = [
        str(item).strip()
        for item in memo.get("key_points") or []
        if str(item or "").strip()
    ]
    value = key_points[0] if key_points else str(memo.get("summary") or "").strip()
    if not value:
        return "暂无摘要"
    value = " ".join(value.split())
    return value if len(value) <= limit else f"{value[:limit].rstrip()}…"


def _compact_research_reports(reports: list) -> list:
    return [{
        "id": item.get("id"),
        "title": item.get("title"),
        "report_date": item.get("report_date"),
        "manager_name": item.get("manager_name"),
        "evidence_scope": item.get("evidence_scope"),
        "summary": _brief_memo_summary(item, limit=500),
        "key_points": [
            " ".join(str(point).split())[:300]
            for point in (item.get("key_points") or [])[:3]
            if str(point or "").strip()
        ],
        "classifications": (item.get("classifications") or [])[:8],
        "style_labels": (item.get("style_labels") or [])[:8],
    } for item in reports]


async def _build_evaluation_snapshot(wind_code: str, include_research: bool) -> dict:
    from services.fund_research_snapshot_service import FundResearchSnapshotService

    service = FundResearchSnapshotService()
    timeout_seconds = max(
        5,
        min(int(os.environ.get("FUND_EVALUATION_ATTRIBUTION_TIMEOUT_SECONDS", "25")), 60),
    )

    def build(live_attribution: bool) -> dict:
        return service.build(
            wind_code,
            window="1y",
            include_research=include_research,
            include_attribution=True,
            research_limit=5,
            live_attribution=live_attribution,
        )

    try:
        with anyio.fail_after(timeout_seconds):
            return await anyio.to_thread.run_sync(
                lambda: build(True),
                abandon_on_cancel=True,
            )
    except TimeoutError:
        logger.warning("Live attribution timed out for %s after %ss", wind_code, timeout_seconds)
        snapshot = await anyio.to_thread.run_sync(lambda: build(False))
        reason = f"现场归因计算超过 {timeout_seconds} 秒，本次先基于基金评价与纪要生成结果；可稍后单独运行归因。"
        attribution = snapshot.get("attribution") or {}
        attribution["evidence_origin"] = {
            "mode": "timed_out",
            "label": "现场归因超时",
            "quarter": (attribution.get("evidence_origin") or {}).get("quarter"),
            "updated_at": None,
        }
        for key in ("barra", "brinson", "nav_factor_lens", "nav_return_attribution"):
            block = attribution.setdefault(key, {"status": "insufficient_evidence"})
            block["missing_items"] = list(dict.fromkeys([
                reason,
                *(block.get("missing_items") or []),
            ]))
        snapshot["attribution"] = attribution
        evidence = snapshot.setdefault("evidence", {})
        evidence["missing_items"] = list(dict.fromkeys([
            *(evidence.get("missing_items") or []),
            reason,
        ]))
        return snapshot


def _evaluation_analysis_fallback(
    fund_data: dict,
    evaluation: dict,
    factor_evidence: dict,
    attribution_evidence: dict,
    managers: list,
    research_reports: list,
    question: str,
) -> str:
    target = evaluation.get("target") or {}
    classification = evaluation.get("classification") or {}
    peer_context = evaluation.get("peer_context") or {}
    result = evaluation.get("evaluation") or {}
    metric_scores = result.get("metric_scores") or {}
    attribution_benchmark_detail = attribution_evidence.get("benchmark_detail") or {}
    attribution_origin = attribution_evidence.get("evidence_origin") or {}
    score = result.get("overall_score")
    multi_period = evaluation.get("multi_period_evidence") or {}
    missing = list(dict.fromkeys(str(item) for item in evaluation.get("missing_items", []) if item))
    lines = [
        f"# {fund_data.get('name') or target.get('name') or fund_data.get('wind_code')} 基金评价",
        "",
        "## 一句话结论",
    ]
    if evaluation.get("status") == "insufficient_evidence":
        lines.append("当前分类或同类评价证据不足，暂不输出基金优劣结论。")
    else:
        lines.append(
            f"该基金已按“{peer_context.get('peer_group') or classification.get('peer_group') or '已确认同类组'}”口径评价"
            + (f"，专业综合评分为 {float(score):.1f}" if score is not None else "")
            + "；这是分类内研究结果，不是买卖建议。"
        )

    lines.extend([
        "",
        "## 基金定位",
        f"- 基金类别：{classification.get('fund_type') or fund_data.get('type') or '待补'}",
        f"- 同类组：{peer_context.get('peer_group') or classification.get('peer_group') or '待补'}",
        f"- 主要基准：{peer_context.get('primary_benchmark') or classification.get('primary_benchmark') or '待补'}",
        (
            f"- Brinson 权益参照：{attribution_benchmark_detail.get('benchmark_name')}"
            + (
                f"（合同权重 {float(attribution_benchmark_detail.get('declared_weight')):.0%}）"
                if attribution_benchmark_detail.get("declared_weight") is not None
                else ""
            )
            if attribution_benchmark_detail.get("benchmark_name")
            else (
                "- Brinson 权益参照：当前基金不适用股票行业归因"
                if attribution_evidence.get("status") == "not_applicable"
                else "- Brinson 权益参照：待补"
            )
        ),
        f"- 同类有效样本：{peer_context.get('valid_metric_peer_count') or 0} 只",
        "",
        "## 同类表现",
    ])
    percentiles = result.get("peer_percentiles") or {}
    if percentiles:
        for item in list(percentiles.values())[:8]:
            if not isinstance(item, dict):
                continue
            label = item.get("label") or item.get("metric_name")
            percentile = item.get("percentile")
            raw_value = item.get("value")
            unit = item.get("unit")
            if raw_value is None:
                display_value = "待补"
            elif unit == "percent":
                display_value = f"{float(raw_value) * 100:.2f}%"
            elif unit == "cny_100m":
                display_value = f"{float(raw_value):.2f} 亿元"
            elif unit == "score":
                display_value = f"{float(raw_value):.1f} 分"
            else:
                display_value = str(raw_value)
            rank = item.get("rank")
            peer_count = item.get("peer_count")
            comparison = (
                f"同类有利分位 {float(percentile):.1f}，排名 {rank}/{peer_count}"
                if percentile is not None and rank is not None and peer_count
                else "同类排序待补"
            )
            lines.append(f"- {label}：{display_value}；{comparison}")
    else:
        lines.append("- 当前没有可用的同类分位数据。")
    period_performance = evaluation.get("period_performance") or {}
    period_rows = period_performance.get("periods") or []
    if period_rows:
        lines.append("- 自然年度业绩：")
        for period in period_rows[:5]:
            period_return = period.get("return")
            if period_return is None:
                continue
            detail = f"{float(period_return) * 100:.2f}%"
            if period.get("rank") is not None and period.get("peer_count"):
                detail += (
                    f"；同类中位数 {float(period.get('peer_median_return') or 0) * 100:.2f}%"
                    f"；同类排名 {period.get('rank')}/{period.get('peer_count')}"
                )
            elif period.get("coverage_status") != "complete":
                detail += "；区间不完整，不参与年度同类排名"
            else:
                detail += "；同类样本不足"
            lines.append(f"  - {period.get('label') or period.get('year')}：{detail}")

    lines.extend(["", "## 多周期表现"])
    if multi_period.get("status") == "long_term_ready":
        lines.append("- 长期证据：近 3 年收益、最大回撤和 Sharpe 数据完整。")
        for label, key, is_percent in (
            ("近 6 月收益", "return_6m", True),
            ("近 1 年收益", "return_1y", True),
            ("近 1 年年化收益", "annualized_return_1y", True),
            ("近 3 年年化收益", "annualized_return_3y", True),
            ("近 1 年最大回撤", "max_drawdown_1y", True),
            ("近 3 年最大回撤", "max_drawdown_3y", True),
            ("近 3 年 Sharpe", "sharpe_ratio_3y", False),
        ):
            value = multi_period.get(key)
            if value is None:
                continue
            display = f"{float(value) * 100:.2f}%" if is_percent else f"{float(value):.2f}"
            lines.append(f"- {label}：{display}")
        consistency_label = multi_period.get("consistency_label") or "短长期一致性待补"
        return_gap = multi_period.get("annualized_return_gap")
        gap_text = f"，相差 {float(return_gap) * 100:.1f} 个百分点" if return_gap is not None else ""
        lines.append(f"- 短长期一致性：{consistency_label}{gap_text}。")
    else:
        lines.append("- 长期证据：近 3 年完整收益风险证据不足，不能把短期领先视为长期持续。")
        for label, key in (("近 6 月收益", "return_6m"), ("近 1 年收益", "return_1y")):
            value = multi_period.get(key)
            if value is not None:
                lines.append(f"- {label}：{float(value) * 100:.2f}%")

    lines.extend(["", "## 风险与归因"])
    if attribution_origin.get("mode") == "saved_history":
        lines.append(
            f"- 归因证据来源：复用 {attribution_origin.get('quarter') or '当前季度'} 已保存结果"
            + (f"（更新于 {attribution_origin.get('updated_at')}）" if attribution_origin.get("updated_at") else "")
            + "。"
        )
    elif attribution_origin.get("mode") == "live_calculation":
        lines.append(f"- 归因证据来源：本次现场计算（{attribution_origin.get('quarter') or '当前季度'}）。")
    risk_rows = [
        ("近 1 年最大回撤", metric_scores.get("1y.max_drawdown"), True),
        ("近 1 年年化波动", metric_scores.get("1y.annualized_volatility"), True),
        ("近 1 年夏普比率", metric_scores.get("1y.sharpe_ratio"), False),
    ]
    for label, value, is_percent in risk_rows:
        if value is not None:
            display = f"{float(value) * 100:.2f}%" if is_percent else f"{float(value):.2f}"
            lines.append(f"- {label}：{display}")
    holding_stability = (
        (evaluation.get("explanatory_evidence") or {}).get("holding_stability")
        or {}
    )
    if holding_stability.get("status") == "available":
        lines.append(
            f"- 公开持仓延续性：{holding_stability.get('previous_quarter') or '上一期'} 至 "
            f"{holding_stability.get('latest_quarter') or '最新一期'}，"
            f"前十大权重重合度 {float(holding_stability.get('top10_overlap_ratio') or 0) * 100:.1f}%，"
            f"延续 {int(holding_stability.get('retained_holding_count') or 0)} 只重仓，"
            f"行业权重重合度 {float(holding_stability.get('industry_overlap_ratio') or 0) * 100:.1f}%。"
        )
        lines.append("- 上述只比较相邻两期公开前十大持仓，不等于完整组合换手率，也不参与基金评分。")
    elif holding_stability.get("missing_items"):
        lines.append(f"- 公开持仓延续性证据不足：{holding_stability['missing_items'][0]}")
    holding_style_drift = (
        evaluation.get("holding_style_drift")
        or factor_evidence.get("holding_style_drift_evidence")
        or {}
    )
    if holding_style_drift.get("status") == "available":
        lines.append(f"- 公开持仓风格变化：{holding_style_drift.get('note')}")
        lines.append("- 上述只比较同一专业同类组内相邻公开持仓期，不是完整组合、RBSA 或 Barra，也不参与基金评分。")
    elif holding_style_drift.get("missing_items"):
        lines.append(f"- 公开持仓风格变化证据不足：{holding_style_drift['missing_items'][0]}")
    if factor_evidence.get("status") == "ok":
        for item in (factor_evidence.get("risk_contributions") or [])[:4]:
            lines.append(f"- {item.get('label') or item.get('factor')}风险贡献：{float(item.get('risk_contribution') or 0) * 100:.1f}%")
    elif factor_evidence.get("industry_exposures"):
        lines.append("- 已取得持仓行业暴露，但正式 Barra 风格因子仍不可用。")
        for industry, weight in list((factor_evidence.get("industry_exposures") or {}).items())[:5]:
            lines.append(f"- 已披露持仓中的{industry}暴露：{float(weight) * 100:.1f}%")
    else:
        lines.append("- Barra 因子风险解释证据不足，不对正式风格暴露作强结论。")
    holding_style = factor_evidence.get("holding_style_peer_evidence") or {}
    if holding_style.get("status") == "peer_percentile_ready":
        labels = "、".join(str(item) for item in holding_style.get("labels") or [])
        lines.append(
            f"- 公开持仓同类风格：{labels or '同类分位已就绪'}；"
            f"{holding_style.get('quarter') or '季度待补'}，"
            f"{holding_style.get('peer_group_name') or '同类组待补'} {holding_style.get('sample_size') or 0} 只样本。"
        )
        lines.append("- 上述是公开持仓描述子的同类分位，不是完整 Barra 风险模型。")
    elif holding_style.get("status") == "descriptor_ready":
        lines.append("- 已取得公开持仓风格描述子，但同季度同类样本不足，当前不贴量化风格标签。")
    if attribution_evidence.get("status") in {"ok", "partial_evidence"}:
        returns = attribution_evidence.get("returns") or {}
        lines.append(f"- Brinson 归因区间主动收益：{float(returns.get('active') or 0) * 100:.2f}%")
        for item in attribution_evidence.get("effects") or []:
            if item.get("value") is not None:
                lines.append(f"- {item.get('label')}：{float(item.get('value')) * 100:.2f}%")
        if attribution_evidence.get("status") == "partial_evidence":
            lines.append("- 当前 Brinson 仅覆盖公开披露持仓，未披露部分进入残差，不作完整持仓结论。")
    else:
        lines.append("- 正式 Brinson 行业归因证据不足，不输出配置与选择效应结论。")
    nav_attribution = attribution_evidence.get("supplementary_nav_return") or {}
    if nav_attribution.get("status") == "ok":
        nav_returns = nav_attribution.get("returns") or {}
        lines.append(f"- 补充净值行为解释：主动收益 {float(nav_returns.get('active') or 0) * 100:.2f}%（不是 Brinson）。")

    lines.extend(["", "## 经理与纪要证据"])
    manager_tenure_performance = evaluation.get("manager_tenure_performance") or {}
    manager_tenure_not_applicable = manager_tenure_performance.get("status") == "not_applicable"
    if manager_tenure_not_applicable:
        lines.append("- 基金经理任期：该类别评价不使用经理任期指标，不构成评价缺口。")
    elif manager_tenure_performance.get("status") in {"available", "partial"}:
        coverage_status = manager_tenure_performance.get("coverage_status")
        requested_start = manager_tenure_performance.get("requested_start_date") or "上任日待补"
        actual_start = manager_tenure_performance.get("actual_start_date") or "净值起点待补"
        total_return = manager_tenure_performance.get("total_return")
        if coverage_status == "full_tenure":
            detail = f"现任团队自 {requested_start} 上任，净值完整覆盖"
            if total_return is not None:
                detail += f"；任期收益 {float(total_return) * 100:.2f}%"
            peer_metric = (
                ((manager_tenure_performance.get("peer_ranking") or {}).get("metrics") or {}).get("total_return")
                or {}
            )
            if peer_metric.get("rank") is not None and peer_metric.get("peer_count"):
                detail += f"；同区间同类第 {peer_metric['rank']}/{peer_metric['peer_count']} 名"
            lines.append(f"- 现任经理任期：{detail}。")
        else:
            coverage_ratio = manager_tenure_performance.get("coverage_ratio")
            detail = f"现任团队自 {requested_start} 上任，但本地净值从 {actual_start} 才开始"
            if coverage_ratio is not None:
                detail += f"，仅覆盖 {float(coverage_ratio) * 100:.0f}%"
            if total_return is not None:
                detail += f"；本地可见期收益 {float(total_return) * 100:.2f}%"
            lines.append(f"- 现任经理任期：{detail}；不冒充完整任期，不生成同类排名，也不计入经理任期评分。")
    else:
        lines.append("- 现任经理任期表现待补，不能把基金历史业绩直接归因给当前经理。")
    if managers:
        for manager in managers:
            manager_name = manager.get("name") or manager.get("manager_id") or "姓名待补"
            management_years = manager.get("management_years")
            tenure = f"，管理年限约 {float(management_years):.1f} 年" if management_years is not None else ""
            lines.append(f"- 当前基金经理：{manager_name}{tenure}；来源为 Tushare 基金经理任职记录。")
    elif not manager_tenure_not_applicable:
        lines.append("- 当前基金经理资料待补。")
    if research_reports:
        for memo in research_reports[:5]:
            scope = "经理层证据，不代表该基金专属表述；" if memo.get("evidence_scope") == "manager_level" else "基金关联证据；"
            lines.append(f"- 《{memo.get('title') or '无标题纪要'}》（{memo.get('report_date') or '日期待补'}）：{scope}{_brief_memo_summary(memo)}")
    else:
        lines.append("- 没有找到已关联到该基金的调研纪要。")

    lines.extend([
        "",
        "## 需要继续核查的信号",
        "- 同类分位是否在多个滚动窗口持续，而非仅近期领先。",
        "- 风格标签与净值因子、持仓和经理表述是否一致。",
        "- 超额收益来源是否稳定，以及未解释残差是否过高。",
        "",
        "## 数据缺口",
    ])
    combined_missing = (
        missing
        + list(factor_evidence.get("missing_items") or [])
        + list(attribution_evidence.get("missing_items") or [])
        + list((factor_evidence.get("supplementary_nav_factor") or {}).get("missing_items") or [])
        + list((attribution_evidence.get("supplementary_nav_return") or {}).get("missing_items") or [])
    )
    if combined_missing:
        lines.extend(f"- {item}" for item in list(dict.fromkeys(combined_missing))[:12])
    else:
        lines.append("- 当前核心评价数据已可用，仍需持续更新净值、基准和调研纪要。")
    if question:
        lines.extend(["", "## 本次关注问题", question])
    return "\n".join(lines)


def _reject_mock_data_source(data_svc, report_scope: str) -> None:
    if getattr(data_svc, "mock_mode", False):
        raise HTTPException(
            status_code=409,
            detail=f"{report_scope}报告需要真实 Tushare 入库/同步数据；当前数据服务为 mock_mode，已阻止生成研究报告。",
        )


def _ensure_peer_percentile_section(content: str, peer_percentiles: dict) -> str:
    if "## 同类分位与胜负线" in content:
        return content
    try:
        from services.evidence_report import build_peer_percentile_report_section

        return content.rstrip() + "\n\n" + build_peer_percentile_report_section(peer_percentiles)
    except Exception as exc:
        logger.warning(f"Failed to append peer percentile section: {exc}")
        return content


def _ensure_manager_tenure_section(content: str, managers: list, tenure_metrics: list) -> str:
    if "## 现任经理任期切片" in content:
        return content
    try:
        from services.evidence_report import build_manager_tenure_report_section

        return content.rstrip() + "\n\n" + build_manager_tenure_report_section(managers, tenure_metrics)
    except Exception as exc:
        logger.warning(f"Failed to append manager tenure section: {exc}")
        return content


def _ensure_sales_rule_cost_section(content: str, sales_rule_data: dict, purchase_plan: str) -> str:
    if "## 费用与销售规则快照" in content:
        return content
    try:
        from services.evidence_report import build_sales_rule_cost_report_section

        return content.rstrip() + "\n\n" + build_sales_rule_cost_report_section(sales_rule_data, purchase_plan)
    except Exception as exc:
        logger.warning(f"Failed to append sales rule cost section: {exc}")
        return content


def _ensure_buy_before_decision_section(
    content: str,
    peer_percentiles: dict,
    sales_rule_data: dict,
    holdings: list,
    manager_tenure_metrics: list,
    purchase_plan: str,
) -> str:
    if "## 买前总闸门结论" in content:
        return content
    try:
        from services.evidence_report import build_buy_before_decision_section

        section = build_buy_before_decision_section(
            peer_percentiles,
            sales_rule_data,
            holdings,
            manager_tenure_metrics,
            purchase_plan,
        )
        return content.rstrip() + "\n\n" + section
    except Exception as exc:
        logger.warning(f"Failed to append buy-before decision section: {exc}")
        return content


def _purchase_plan_label(purchase_plan: str) -> str:
    return "一次性买入" if purchase_plan == "lump_sum" else "定投"


def _normalize_planned_amount(value, purchase_plan: str):
    try:
        amount = float(value)
    except (TypeError, ValueError):
        amount = 10000.0 if purchase_plan == "lump_sum" else 1000.0
    if amount <= 0:
        amount = 10000.0 if purchase_plan == "lump_sum" else 1000.0
    return int(amount) if amount.is_integer() else amount


def _purchase_plan_evidence_fields(purchase_plan: str) -> str:
    if purchase_plan == "lump_sum":
        return "申购状态、起购金额、限购、赎回规则、费率、销售风险等级（R1-R5）"
    return "申购状态、定投支持、定投起点、限购、赎回规则、费率、销售风险等级（R1-R5）"


def _ensure_purchase_plan_notice(content: str, purchase_plan: str, planned_amount=None) -> str:
    if "买入方式口径" in content and "计划金额" in content:
        return content
    label = _purchase_plan_label(purchase_plan)
    fields = _purchase_plan_evidence_fields(purchase_plan)
    amount = _normalize_planned_amount(planned_amount, purchase_plan)
    notice = (
        f"> 买入方式口径：{label}；计划金额：{amount:,} 元。正式买前判断前必须补齐并复核{fields}；"
        "评分和研究报告不能替代销售规则、适当性、费用与净值回放门禁。"
    )
    return f"{notice}\n\n{content}"


def _load_latest_local_holdings(wind_code: str) -> dict:
    try:
        from repositories import get_holding_repo
        rows = get_holding_repo().get_holdings_history(wind_code)
    except Exception as error:
        logger.warning(f"Failed to load local holdings for {wind_code}: {error}")
        return {
            "status": "unavailable",
            "source": "local_postgres.holdings",
            "quarter": None,
            "holdings": [],
            "note": "读取本地持仓表失败，报告不做行业/个股暴露判断。",
        }

    by_quarter = {}
    for row in rows:
        quarter = str(row.get("quarter") or "").upper()
        stock_code = str(row.get("stock_code") or "").strip()
        stock_name = str(row.get("stock_name") or "").strip()
        if not quarter or not (stock_code or stock_name):
            continue
        by_quarter.setdefault(quarter, []).append(row)

    for quarter in sorted(by_quarter.keys(), reverse=True):
        holdings = by_quarter[quarter]
        if len(holdings) >= 5:
            return {
                "status": "available",
                "source": "local_postgres.holdings",
                "quarter": quarter,
                "holdings": holdings,
                "note": "使用本地 PostgreSQL 已入库持仓；买前仍需以基金季报/销售平台披露为准。",
            }

    return {
        "status": "unavailable",
        "source": "local_postgres.holdings",
        "quarter": None,
        "holdings": [],
        "note": "本地持仓表无 >=5 条的可信季度持仓，报告不做行业/个股暴露判断。",
    }


def _load_local_sales_rules(wind_code: str) -> dict:
    try:
        import json
        from sqlalchemy import text
        from database import get_engine

        sql = text("""
            SELECT *
            FROM fund_sales_rules
            WHERE wind_code = :wind_code
            ORDER BY source_updated_at DESC NULLS LAST, updated_at DESC NULLS LAST
            LIMIT 20
        """)
        with get_engine().connect() as conn:
            rows = [dict(row._mapping) for row in conn.execute(sql, {"wind_code": wind_code}).fetchall()]
    except Exception as error:
        logger.warning(f"Failed to load local sales rules for {wind_code}: {error}")
        return {
            "status": "unavailable",
            "source": "local_postgres.fund_sales_rules",
            "rules": [],
            "merged": {},
            "note": "读取本地销售规则失败，报告不做费用/申赎判断。",
        }

    def normalize_rule(row: dict) -> dict:
        rule = _json_safe(row)
        redemption_rules = rule.get("redemption_fee_rules") or []
        if isinstance(redemption_rules, str):
            try:
                redemption_rules = json.loads(redemption_rules)
            except Exception:
                redemption_rules = []
        rule["redemption_fee_rules"] = redemption_rules if isinstance(redemption_rules, list) else []
        return rule

    rules = [normalize_rule(row) for row in rows]
    if not rules:
        return {
            "status": "unavailable",
            "source": "local_postgres.fund_sales_rules",
            "rules": [],
            "merged": {},
            "note": "本地销售规则表无该基金记录；报告不做费用/申赎通过判断。",
        }

    def first_value(key: str):
        for rule in rules:
            value = rule.get(key)
            if value not in (None, "", "unknown", []):
                return value
        return None

    def valid_risk_level(rule: dict) -> bool:
        value = str(rule.get("risk_level") or "").strip().upper()
        return value in {"R1", "R2", "R3", "R4", "R5"}

    def tushare_risk_source(rule: dict) -> bool:
        platform = str(rule.get("platform") or "").strip().lower()
        source_url = str(rule.get("source_url") or "").strip().lower()
        return "tushare" in platform or "tushare.fund_basic" in source_url

    def same_row_risk_source_evidence(rule: dict) -> bool:
        if not valid_risk_level(rule) or tushare_risk_source(rule):
            return False
        return bool(rule.get("source_updated_at") and (rule.get("source_url") or rule.get("notes")))

    def same_row_redemption_source_evidence(rule: dict) -> bool:
        return bool(rule.get("redemption_fee_rules") and rule.get("source_updated_at") and (rule.get("source_url") or rule.get("notes")))

    status_rule = next((rule for rule in rules if rule.get("purchase_status") not in (None, "", "unknown")), rules[0])
    redemption_rule = (
        next((rule for rule in rules if same_row_redemption_source_evidence(rule)), None)
        or next((rule for rule in rules if rule.get("redemption_fee_rules")), None)
        or {}
    )
    risk_rule = (
        next((rule for rule in rules if same_row_risk_source_evidence(rule)), None)
        or next((rule for rule in rules if valid_risk_level(rule) and not tushare_risk_source(rule)), None)
        or next((rule for rule in rules if valid_risk_level(rule)), None)
        or {}
    )
    merged = {
        "platform": first_value("platform"),
        "purchase_status": status_rule.get("purchase_status") or "unknown",
        "purchase_status_label": status_rule.get("purchase_status_label") or "申购待核",
        "min_purchase_amount": first_value("min_purchase_amount"),
        "min_sip_amount": first_value("min_sip_amount"),
        "daily_limit_amount": first_value("daily_limit_amount"),
        "purchase_fee_rate": first_value("purchase_fee_rate"),
        "redemption_fee_rules": redemption_rule.get("redemption_fee_rules") or [],
        "redemption_fee_source_updated_at": redemption_rule.get("source_updated_at"),
        "redemption_fee_source_url": redemption_rule.get("source_url"),
        "redemption_fee_platform": redemption_rule.get("platform"),
        "redemption_fee_notes": redemption_rule.get("notes"),
        "sales_service_fee_rate": first_value("sales_service_fee_rate"),
        "risk_level": risk_rule.get("risk_level"),
        "supports_sip": first_value("supports_sip"),
        "source_updated_at": risk_rule.get("source_updated_at") if risk_rule.get("risk_level") else first_value("source_updated_at"),
        "source_url": risk_rule.get("source_url") if risk_rule.get("risk_level") else first_value("source_url"),
        "notes": risk_rule.get("notes") if risk_rule.get("risk_level") else first_value("notes"),
    }
    return {
        "status": "available",
        "source": "local_postgres.fund_sales_rules",
        "rules": rules,
        "merged": merged,
        "note": "使用本地 PostgreSQL 销售规则快照；买前仍需以销售平台实时页面为准。",
    }


@router.post("/fund/{wind_code}/evaluation-analysis")
async def generate_fund_evaluation_analysis(
    wind_code: str,
    payload: FundEvaluationAnalysisRequest = Body(default=FundEvaluationAnalysisRequest()),
):
    """按需生成基金评价分析：分类内评价为主，归因与纪要为证据。"""
    from service_registry import get_data_service, get_db
    from services.ai_report import get_report_generator
    data_svc = get_data_service()
    _reject_mock_data_source(data_svc, "基金评价")
    db = get_db()

    try:
        snapshot = await _build_evaluation_snapshot(wind_code, payload.include_research)
        fund_data = snapshot.get("fund") or {}
        managers = snapshot.get("managers") or []
        evaluation = snapshot.get("evaluation") or {}
        period_performance = snapshot.get("period_performance") or {}
        manager_tenure_performance = snapshot.get("manager_tenure_performance") or {}
        multi_period_evidence = snapshot.get("multi_period_evidence") or {}
        holding_style_drift = snapshot.get("holding_style_drift") or {}
        evaluation_with_periods = {
            **evaluation,
            "period_performance": period_performance,
            "manager_tenure_performance": manager_tenure_performance,
            "multi_period_evidence": multi_period_evidence,
            "holding_style_drift": holding_style_drift,
        }
        attribution_bundle = snapshot.get("attribution") or {}
        assessment_summary = snapshot.get("assessment_summary") or {}
        style_evidence_summary = assessment_summary.get("style_evidence") or {}
        research_evidence_summary = assessment_summary.get("research_evidence") or {}
        attribution_evidence_summary = assessment_summary.get("attribution_evidence") or {}
        attribution_origin = attribution_bundle.get("evidence_origin") or {}
        analysis_evidence = snapshot.get("analysis_evidence") or {}
        factor_evidence = analysis_evidence.get("factor_evidence") or {}
        attribution_evidence = analysis_evidence.get("attribution_evidence") or {}
        research_reports = (snapshot.get("research_memos") or {}).get("items") or []
        fund_specific_research_count = sum(
            1 for item in research_reports if item.get("evidence_scope") != "manager_level"
        )
        manager_level_research_count = len(research_reports) - fund_specific_research_count
        compact_research_reports = _compact_research_reports(research_reports)

        generator = get_report_generator()
        generation_mode = "llm_evaluation_evidence"
        report_content = ""
        if generator.api_key:
            report_content = await anyio.to_thread.run_sync(
                lambda: generator.generate_fund_evaluation_analysis(
                    fund_data=fund_data,
                    evaluation_data=evaluation_with_periods,
                    factor_evidence=factor_evidence,
                    attribution_evidence=attribution_evidence,
                    managers=managers,
                    research_reports=compact_research_reports,
                    user_question=payload.question,
                    assessment_summary=assessment_summary,
                )
            )
        if not report_content or _is_unusable_llm_report(report_content):
            report_content = _evaluation_analysis_fallback(
                fund_data=fund_data,
                evaluation=evaluation_with_periods,
                factor_evidence=factor_evidence,
                attribution_evidence=attribution_evidence,
                managers=managers,
                research_reports=research_reports,
                question=payload.question,
            )
            generation_mode = "deterministic_evaluation_evidence"

        report_record = {
            "target_type": "fund",
            "target_id": wind_code,
            "report_type": "fund_evaluation_analysis",
            "content": report_content,
            "data_sources": {
                "source": "fund_research_snapshot",
                "research_snapshot": snapshot,
                "assessment_summary": assessment_summary,
                "generation_mode": generation_mode,
                "research_reports_count": len(research_reports),
                "fund_specific_research_count": fund_specific_research_count,
                "manager_level_research_count": manager_level_research_count,
            },
            "research_reports_used": [item["id"] for item in research_reports],
            "generation_params": {
                "mode": generation_mode,
                "include_research": payload.include_research,
                "question": payload.question,
                "fund_name": fund_data.get("name"),
                "fund_type": fund_data.get("type"),
                "peer_group": (evaluation.get("peer_context") or {}).get("peer_group"),
                "provider": generator.provider,
                "model": generator.model,
                "research_reports_count": len(research_reports),
                "fund_specific_research_count": fund_specific_research_count,
                "manager_level_research_count": manager_level_research_count,
                "attribution_evidence_mode": attribution_origin.get("mode"),
                "attribution_quarter": attribution_origin.get("quarter") or attribution_bundle.get("quarter"),
                "attribution_evidence_updated_at": attribution_origin.get("updated_at"),
                "manager_tenure_coverage_status": manager_tenure_performance.get("coverage_status"),
                "manager_tenure_coverage_ratio": manager_tenure_performance.get("coverage_ratio"),
                "multi_period_status": multi_period_evidence.get("status"),
                "multi_period_consistency_status": multi_period_evidence.get("consistency_status"),
                "multi_period_consistency_label": multi_period_evidence.get("consistency_label"),
                "multi_period_data_as_of": multi_period_evidence.get("data_as_of"),
                "holding_style_drift_status": holding_style_drift.get("status"),
                "holding_style_drift_level": holding_style_drift.get("level"),
                "holding_style_drift_previous_quarter": holding_style_drift.get("previous_quarter"),
                "holding_style_drift_latest_quarter": holding_style_drift.get("latest_quarter"),
                "evaluation_score": assessment_summary.get("score"),
                "evaluation_grade": assessment_summary.get("grade"),
                "peer_rank": assessment_summary.get("peer_rank"),
                "peer_count": assessment_summary.get("peer_count"),
                "evaluation_verdict": assessment_summary.get("verdict"),
                "style_evidence_status": style_evidence_summary.get("status"),
                "style_evidence_scope": style_evidence_summary.get("scope"),
                "style_evidence_quarter": style_evidence_summary.get("quarter"),
                "style_labels": style_evidence_summary.get("labels") or [],
                "memo_style_labels": style_evidence_summary.get("memo_labels") or [],
                "research_evidence_status": research_evidence_summary.get("status"),
                "research_evidence_note": research_evidence_summary.get("note"),
                "attribution_evidence_status": attribution_evidence_summary.get("status"),
                "attribution_evidence_headline": attribution_evidence_summary.get("headline"),
                "attribution_evidence_detail": attribution_evidence_summary.get("detail"),
                "attribution_disclosure_coverage": attribution_evidence_summary.get("coverage"),
                "formal_barra_ready": attribution_evidence_summary.get("formal_barra_ready"),
                "barra_descriptor_ready": attribution_evidence_summary.get("barra_descriptor_ready"),
            },
            "created_at": datetime.utcnow(),
        }
        report_id = _save_report_to_postgres(report_record)
        try:
            if db is not None:
                db.ai_analysis_reports.insert_one(report_record)
        except Exception as mongo_error:
            logger.debug(f"Mongo evaluation analysis save skipped: {mongo_error}")

        return {
            "id": report_id,
            "report": report_content,
            "metadata": {
                "target_type": "fund",
                "target_id": wind_code,
                "report_type": "fund_evaluation_analysis",
                "report_id": report_id,
                "mode": generation_mode,
                "provider": generator.provider,
                "model": generator.model,
                "fund_name": fund_data.get("name"),
                "fund_type": fund_data.get("type"),
                "peer_group": (evaluation.get("peer_context") or {}).get("peer_group"),
                "research_reports_count": len(research_reports),
                "fund_specific_research_count": fund_specific_research_count,
                "manager_level_research_count": manager_level_research_count,
                "manager_count": len(managers),
                "evaluation_status": evaluation.get("status"),
                "factor_status": factor_evidence.get("status"),
                "attribution_status": attribution_evidence.get("status"),
                "attribution_benchmark": attribution_bundle.get("benchmark"),
                "attribution_benchmark_source": attribution_bundle.get("benchmark_source"),
                "attribution_evidence_mode": attribution_origin.get("mode"),
                "attribution_quarter": attribution_origin.get("quarter") or attribution_bundle.get("quarter"),
                "attribution_evidence_updated_at": attribution_origin.get("updated_at"),
                "manager_tenure_coverage_status": manager_tenure_performance.get("coverage_status"),
                "manager_tenure_coverage_ratio": manager_tenure_performance.get("coverage_ratio"),
                "multi_period_status": multi_period_evidence.get("status"),
                "multi_period_consistency_status": multi_period_evidence.get("consistency_status"),
                "multi_period_consistency_label": multi_period_evidence.get("consistency_label"),
                "multi_period_data_as_of": multi_period_evidence.get("data_as_of"),
                "holding_style_drift_status": holding_style_drift.get("status"),
                "holding_style_drift_level": holding_style_drift.get("level"),
                "holding_style_drift_previous_quarter": holding_style_drift.get("previous_quarter"),
                "holding_style_drift_latest_quarter": holding_style_drift.get("latest_quarter"),
                "evaluation_score": assessment_summary.get("score"),
                "evaluation_grade": assessment_summary.get("grade"),
                "peer_rank": assessment_summary.get("peer_rank"),
                "peer_count": assessment_summary.get("peer_count"),
                "evaluation_verdict": assessment_summary.get("verdict"),
                "style_evidence_status": style_evidence_summary.get("status"),
                "style_evidence_scope": style_evidence_summary.get("scope"),
                "style_evidence_quarter": style_evidence_summary.get("quarter"),
                "style_labels": style_evidence_summary.get("labels") or [],
                "memo_style_labels": style_evidence_summary.get("memo_labels") or [],
                "research_evidence_status": research_evidence_summary.get("status"),
                "research_evidence_note": research_evidence_summary.get("note"),
                "attribution_evidence_status": attribution_evidence_summary.get("status"),
                "attribution_evidence_headline": attribution_evidence_summary.get("headline"),
                "attribution_evidence_detail": attribution_evidence_summary.get("detail"),
                "attribution_disclosure_coverage": attribution_evidence_summary.get("coverage"),
                "formal_barra_ready": attribution_evidence_summary.get("formal_barra_ready"),
                "barra_descriptor_ready": attribution_evidence_summary.get("barra_descriptor_ready"),
            },
        }
    except HTTPException:
        raise
    except Exception as error:
        logger.error(f"Generate fund evaluation analysis error for {wind_code}: {error}")
        raise HTTPException(status_code=500, detail=str(error))


@router.post("/fund/{wind_code}")
async def generate_fund_report(
    wind_code: str,
    background_tasks: BackgroundTasks = None,
    include_research: bool = True,
    report_depth: str = Query("standard", description="standard/deep/brief"),
    purchase_plan: str = Query("sip", description="sip/lump_sum"),
    planned_amount: Optional[float] = Query(None, description="本次买前计划金额"),
):
    """生成基金分析报告"""
    from service_registry import get_data_service, get_scoring_engine, get_db
    data_svc = get_data_service(); scoring_engine = get_scoring_engine(); db = get_db()
    _reject_mock_data_source(data_svc, "基金")
    from services.ai_report import get_report_generator
    from services.evidence_report import build_buy_before_decision_summary, build_fund_research_report
    from services.peer_comparison_service import PeerComparisonService
    from services.search_service import get_search_service

    try:
        safe_purchase_plan = "lump_sum" if purchase_plan == "lump_sum" else "sip"
        safe_planned_amount = _normalize_planned_amount(planned_amount, safe_purchase_plan)
        # 收集数据
        fund_data = data_svc.get_fund_info(wind_code)
        perf = data_svc.get_fund_performance(wind_code)
        risk = data_svc.get_fund_risk_metrics(wind_code)
        style = data_svc.get_fund_style(wind_code)
        scoring = scoring_engine.score_fund(perf, risk, style)
        try:
            peer_percentiles = PeerComparisonService().build_peer_percentiles(wind_code, window="1y")
        except Exception as peer_err:
            logger.warning(f"Peer percentile unavailable for report {wind_code}: {peer_err}")
            peer_percentiles = {
                "target_id": wind_code,
                "sample_status": "unavailable",
                "metrics": {},
                "peer_metric_gap": {
                    "required_more_funds": 0,
                    "suggested_sync_codes": [],
                    "next_action": "none",
                },
            }
        try:
            from repositories import get_manager_repo, get_metric_snapshot_repo

            manager_repo = get_manager_repo()
            manager_ids = fund_data.get("manager_ids") or []
            managers = []
            for manager_id in manager_ids:
                manager = manager_repo.get_manager(manager_id) or {"manager_id": manager_id, "name": manager_id}
                managers.append(manager)
            manager_tenure_metrics = [
                item
                for item in get_metric_snapshot_repo().get_latest_panel("fund", wind_code)
                if item.get("metric_window") == "manager_tenure"
            ]
        except Exception as manager_err:
            logger.warning(f"Manager tenure evidence unavailable for report {wind_code}: {manager_err}")
            managers = []
            manager_tenure_metrics = []

        # 报告只使用已入库并达到最小数量门槛的持仓；不在报告链路临时调用易失败接口，不编造持仓结论。
        current_q = f"{datetime.now().year}Q{(datetime.now().month-1)//3+1}"
        holding_snapshot = _load_latest_local_holdings(wind_code)
        holdings = holding_snapshot["holdings"]
        sales_rule_snapshot = _load_local_sales_rules(wind_code)

        # 获取相关调研报告
        research_reports = []
        if include_research:
            try:
                query = {"fund_ids": wind_code}
                reports_cursor = db.research_reports.find(query).sort("report_date", -1).limit(5)
                for doc in reports_cursor:
                    research_reports.append({
                        "id": str(doc.get("_id", "")),
                        "title": doc.get("title"),
                        "report_date": doc.get("report_date"),
                        "summary": doc.get("summary", ""),
                        "content": doc.get("content", ""),
                        "tags": doc.get("tags", []),
                    })
            except:
                pass

        # 生成报告
        generator = get_report_generator()
        generation_mode = "llm"
        if generator.api_key:
            report_content = generator.generate_fund_analysis(
                fund_data=fund_data,
                performance_data=perf,
                risk_data=risk,
                holdings_data=holdings,
                style_data=style,
                scoring_result=scoring,
                research_reports=research_reports,
                purchase_plan=safe_purchase_plan,
            )
        else:
            report_content = ""
        if not report_content or _is_unusable_llm_report(report_content):
            report_content = build_fund_research_report(
                fund_data=fund_data,
                performance_data=perf,
                risk_data=risk,
                style_data=style,
                scoring_result=scoring,
                holdings_data=holdings,
                peer_percentiles=peer_percentiles,
                manager_data=managers,
                manager_tenure_metrics=manager_tenure_metrics,
                sales_rule_data=sales_rule_snapshot,
                purchase_plan=safe_purchase_plan,
            )
            generation_mode = "deterministic_evidence_backed"
        report_content = _ensure_peer_percentile_section(report_content, peer_percentiles)
        report_content = _ensure_manager_tenure_section(report_content, managers, manager_tenure_metrics)
        report_content = _ensure_sales_rule_cost_section(report_content, sales_rule_snapshot, safe_purchase_plan)
        report_content = _ensure_buy_before_decision_section(
            report_content,
            peer_percentiles,
            sales_rule_snapshot,
            holdings,
            manager_tenure_metrics,
            safe_purchase_plan,
        )
        report_content = _ensure_purchase_plan_notice(report_content, safe_purchase_plan, safe_planned_amount)
        buy_before_decision = build_buy_before_decision_summary(
            peer_percentiles,
            sales_rule_snapshot,
            holdings,
            manager_tenure_metrics,
            safe_purchase_plan,
        )

        # 保存报告
        report_record = {
            "target_type": "fund",
            "target_id": wind_code,
            "report_type": f"fund_{report_depth}_analysis",
            "content": report_content,
            "data_sources": {
                "wind_code": wind_code,
                "performance": perf,
                "risk": risk,
                "style": style,
                "scoring": scoring,
                "holdings_quarter": holding_snapshot["quarter"] or current_q,
                "holdings_status": holding_snapshot["status"],
                "holdings_source": holding_snapshot["source"],
                "holdings_note": holding_snapshot["note"],
                "holdings_count": len(holdings),
                "peer_percentiles": peer_percentiles,
                "peer_percentile_status": peer_percentiles.get("sample_status"),
                "peer_usable_metric_count": peer_percentiles.get("usable_metric_count"),
                "manager_tenure_metrics_count": len(manager_tenure_metrics),
                "manager_tenure_status": "available" if manager_tenure_metrics else "unavailable",
                "managers": managers,
                "sales_rule_status": sales_rule_snapshot.get("status"),
                "sales_rule_source": sales_rule_snapshot.get("source"),
                "sales_rule_merged": sales_rule_snapshot.get("merged"),
                "buy_before_decision": buy_before_decision,
                "generation_mode": generation_mode,
                "research_reports_count": len(research_reports),
                "summary": {
                    "purchasePlan": safe_purchase_plan,
                    "plannedAmount": safe_planned_amount,
                    "buyBeforeGateStatus": buy_before_decision.get("status"),
                    "buyBeforeGateLabel": buy_before_decision.get("label"),
                },
            },
            "research_reports_used": [r["id"] for r in research_reports],
            "generation_params": {
                "depth": report_depth,
                "include_research": include_research,
                "purchasePlan": safe_purchase_plan,
                "plannedAmount": safe_planned_amount,
                "provider": generator.provider,
                "model": generator.model,
                "base_url": generator.base_url,
                "mode": generation_mode,
            },
            "created_at": datetime.utcnow(),
        }

        report_id = None
        try:
            report_id = _save_report_to_postgres(report_record)
        except Exception as pg_err:
            logger.warning(f"Failed to save report to PostgreSQL: {pg_err}")

        try:
            if db is not None:
                result = db.ai_analysis_reports.insert_one(report_record)
                report_record["mongo_id"] = str(result.inserted_id)
        except Exception as db_err:
            logger.debug(f"Mongo report save skipped: {db_err}")

        return {
            "id": report_id,
            "report": report_content,
            "metadata": {
                "target_type": "fund",
                "target_id": wind_code,
                "report_type": f"fund_{report_depth}_analysis",
                "report_id": report_id,
                "data_sources": report_record["data_sources"],
                "word_count": len(report_content),
                "purchasePlan": safe_purchase_plan,
                "plannedAmount": safe_planned_amount,
                "provider": generator.provider,
                "model": generator.model,
                "mode": generation_mode,
            },
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Generate fund report error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/manager/{manager_id}")
async def generate_manager_report(
    manager_id: str,
    include_profile: bool = True,
    depth: str = Query("standard", description="standard/deep/brief"),
):
    """生成基金经理分析报告"""
    from service_registry import get_data_service, get_scoring_engine, get_db
    data_svc = get_data_service(); scoring_engine = get_scoring_engine(); db = get_db()
    _reject_mock_data_source(data_svc, "基金经理")
    from services.ai_report import get_report_generator
    from services.search_service import get_search_service

    try:
        manager_data = data_svc.get_manager_info(manager_id)
        funds = data_svc.get_manager_funds(manager_id)

        # 汇总代表基金的业绩
        fund_details = []
        for fund in funds[:3]:
            code = fund.get("wind_code", "")
            if not code:
                continue
            p = data_svc.get_fund_performance(code)
            r = data_svc.get_fund_risk_metrics(code)
            s = data_svc.get_fund_style(code)
            score = scoring_engine.score_fund(p, r, s)
            fund_details.append({**fund, "performance": p, "risk": r, "style": s, "scoring": score})

        avg_perf = {
            "overall_score": sum(f["scoring"]["overall_score"] for f in fund_details) / len(fund_details)
            if fund_details
            else None,
        }
        manager_score = scoring_engine.score_manager(manager_data, avg_perf, {}, [])

        # 获取调研报告
        try:
            reports_cursor = db.research_reports.find({"manager_id": manager_id}).sort("report_date", -1).limit(10)
            reports = []
            for doc in reports_cursor:
                reports.append({
                    "id": str(doc.get("_id", "")),
                    "title": doc.get("title"),
                    "report_date": doc.get("report_date"),
                    "summary": doc.get("summary", ""),
                    "content": doc.get("content", ""),
                    "tags": doc.get("tags", []),
                })
        except:
            reports = []

        # 获取经理画像
        manager_profile = None
        if include_profile:
            try:
                profile = db.manager_profiles.find_one({"manager_id": manager_id})
                if profile:
                    manager_profile = {
                        "core_philosophy": profile.get("core_philosophy"),
                        "stock_selection_logic": profile.get("stock_selection_logic"),
                        "risk_philosophy": profile.get("risk_philosophy"),
                        "competence_advantages": profile.get("competence_advantages"),
                        "competence_boundaries": profile.get("competence_boundaries"),
                        "style_label": profile.get("style_label"),
                        "philosophy_behavior_consistency": profile.get("philosophy_behavior_consistency"),
                    }
            except:
                pass

        # 生成报告
        generator = get_report_generator()
        report_content = generator.generate_manager_analysis(
            manager_data=manager_data,
            fund_data={"funds": fund_details, "summary": avg_perf},
            performance_data=avg_perf,
            style_data=fund_details[0]["style"] if fund_details else {},
            scoring_result=manager_score,
            research_reports=reports,
            manager_profile=manager_profile,
        )
        if report_content.lstrip().startswith("## 报告生成失败") or "当前使用模拟数据" in report_content:
            raise HTTPException(status_code=503, detail="LLM 报告生成不可用，请检查 SiliconFlow API Key、模型名或供应商配额。")

        # 保存报告
        report_record = {
            "target_type": "manager",
            "target_id": manager_id,
            "report_type": f"manager_{depth}_analysis",
            "content": report_content,
            "data_sources": {
                "manager_data": manager_data,
                "funds_count": len(funds),
                "research_reports_count": len(reports),
                "profile_available": manager_profile is not None,
            },
            "research_reports_used": [r["id"] for r in reports],
            "generation_params": {
                "depth": depth,
                "include_profile": include_profile,
                "provider": generator.provider,
                "model": generator.model,
                "base_url": generator.base_url,
            },
            "created_at": datetime.utcnow(),
        }

        report_id = None
        try:
            report_id = _save_report_to_postgres(report_record)
        except Exception as pg_err:
            logger.warning(f"Failed to save manager report to PostgreSQL: {pg_err}")

        try:
            if db is not None:
                result = db.ai_analysis_reports.insert_one(report_record)
                report_record["mongo_id"] = str(result.inserted_id)
        except Exception as db_err:
            logger.debug(f"Mongo manager report save skipped: {db_err}")

        return {
            "id": report_id,
            "report": report_content,
            "metadata": {
                "target_type": "manager",
                "target_id": manager_id,
                "report_type": f"manager_{depth}_analysis",
                "report_id": report_id,
                "data_sources": report_record["data_sources"],
                "word_count": len(report_content),
                "provider": generator.provider,
                "model": generator.model,
            },
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Generate manager report error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/history")
async def get_report_history(
    target_type: str = Query(..., description="fund/manager"),
    target_id: str = Query(...),
    limit: int = Query(10, ge=1, le=50),
):
    """获取历史生成的报告列表"""
    from service_registry import get_db
    db = get_db()

    if db is None:
        return {"total": 0, "reports": []}

    try:
        cursor = db.ai_analysis_reports.find(
            {"target_type": target_type, "target_id": target_id}
        ).sort("created_at", -1).limit(limit)

        reports = []
        for doc in cursor:
            reports.append({
                "id": str(doc.get("_id", "")),
                "report_type": doc.get("report_type"),
                "content_preview": doc.get("content", "")[:200],
                "data_sources": doc.get("data_sources"),
                "created_at": doc.get("created_at"),
            })

        return {"total": len(reports), "reports": reports}
    except Exception as e:
        logger.error(f"Get report history error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("")
@router.get("/")
async def list_analysis_reports(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    target_type: Optional[str] = Query(None, description="fund/manager"),
    report_type: Optional[str] = Query(None),
):
    """获取 PostgreSQL 中已生成的研究报告列表"""
    from sqlalchemy import text
    from database import get_engine

    conditions = []
    params = {
        "limit": limit,
        "offset": (page - 1) * limit,
    }
    if target_type:
        conditions.append("target_type = :target_type")
        params["target_type"] = target_type
    if report_type:
        conditions.append("report_type = :report_type")
        params["report_type"] = report_type

    where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    try:
        with get_engine().connect() as conn:
            total = conn.execute(text(f"SELECT COUNT(*) FROM ai_analysis_reports {where_clause}"), params).scalar()
            rows = conn.execute(
                text(
                    f"""
                    SELECT id, target_type, target_id, report_type, content,
                           data_sources, generation_params, created_at
                    FROM ai_analysis_reports
                    {where_clause}
                    ORDER BY created_at DESC
                    LIMIT :limit OFFSET :offset
                    """
                ),
                params,
            ).fetchall()

        reports = []
        for row in rows:
            data = dict(row._mapping)
            reports.append({
                "id": _json_safe(data.get("id")),
                "report_type": data.get("report_type"),
                "target_type": data.get("target_type"),
                "target_id": data.get("target_id"),
                "content": data.get("content"),
                "content_preview": (data.get("content") or "")[:240],
                "data_sources": _json_safe(data.get("data_sources")),
                "generation_params": _json_safe(data.get("generation_params")),
                "created_at": _json_safe(data.get("created_at")),
            })

        return {
            "total": total,
            "page": page,
            "limit": limit,
            "reports": reports,
        }
    except Exception as error:
        logger.error(f"List analysis reports error: {error}")
        raise HTTPException(status_code=500, detail=str(error))


@router.get("/ai-health")
async def get_ai_health():
    """Return configuration and circuit state without spending a model request."""
    from services.ai_report import get_report_generator

    return get_report_generator().health()


@router.get("/{report_id}/timeline")
async def get_report_timeline(report_id: UUID, limit: int = Query(50, ge=1, le=100)):
    """Build a version timeline from immutable analyses of the same target and type."""
    from services.analysis_history_service import AnalysisHistoryService

    try:
        return AnalysisHistoryService().timeline_for_report(str(report_id), limit=limit)
    except ValueError as error:
        if str(error) == "analysis_report_not_found":
            raise HTTPException(status_code=404, detail="分析报告不存在") from error
        raise


@router.get("/{report_id}")
async def get_report_detail(report_id: str):
    """获取报告详情"""
    try:
        from sqlalchemy import text
        from database import get_engine

        sql = """
            SELECT id, target_type, target_id, report_type, content, data_sources,
                   research_reports_used, generation_params, created_at
            FROM ai_analysis_reports
            WHERE id = CAST(:report_id AS UUID)
            LIMIT 1
        """
        with get_engine().connect() as conn:
            row = conn.execute(text(sql), {"report_id": report_id}).fetchone()
        if row:
            data = dict(row._mapping)
            return {
                "id": _json_safe(data.get("id")),
                "target_type": data.get("target_type"),
                "target_id": data.get("target_id"),
                "report_type": data.get("report_type"),
                "content": data.get("content"),
                "data_sources": _json_safe(data.get("data_sources")),
                "research_reports_used": _json_safe(data.get("research_reports_used") or []),
                "generation_params": _json_safe(data.get("generation_params")),
                "created_at": _json_safe(data.get("created_at")),
            }
    except Exception as pg_error:
        logger.debug(f"PostgreSQL report lookup skipped for {report_id}: {pg_error}")

    from bson import ObjectId
    from service_registry import get_db
    db = get_db()

    if db is None:
        raise HTTPException(status_code=503, detail="数据库不可用")

    try:
        doc = db.ai_analysis_reports.find_one({"_id": ObjectId(report_id)})
        if not doc:
            raise HTTPException(status_code=404, detail="报告不存在")

        return {
            "id": str(doc["_id"]),
            "target_type": doc.get("target_type"),
            "target_id": doc.get("target_id"),
            "report_type": doc.get("report_type"),
            "content": doc.get("content"),
            "data_sources": doc.get("data_sources"),
            "created_at": doc.get("created_at"),
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get report detail error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
