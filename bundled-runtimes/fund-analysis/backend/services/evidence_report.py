"""
基于本地真实数据生成基金研究报告。

该模块不调用外部 LLM，不产出演示/Mock 文案；只使用传入的 Tushare/数据库字段，
并对缺失证据显式标记，作为 AI 报告不可用时的可验收研究报告兜底。
"""
from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, Dict, Iterable, List, Optional


RISK_LEVEL_SOURCE_MAX_AGE_DAYS = 30


def _pick(source: Dict[str, Any], keys: Iterable[str]) -> Any:
    for key in keys:
        value = source.get(key)
        if value not in (None, "", "None", "nan", "NaN"):
            return value
    return None


def _format_number(value: Any, suffix: str = "", digits: int = 2) -> str:
    if value in (None, "", "None", "nan", "NaN"):
        return "待补"
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)
    return f"{number:.{digits}f}{suffix}"


def _format_percent(value: Any, digits: int = 2) -> str:
    if value in (None, "", "None", "nan", "NaN"):
        return "待补"
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)
    if abs(number) <= 3:
        number *= 100
    return f"{number:.{digits}f}%"


def _format_money_yi(value: Any) -> str:
    if value in (None, "", "None", "nan", "NaN"):
        return "待补"
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)
    if abs(number) >= 100_000_000:
        number = number / 100_000_000
    return f"{number:.2f} 亿"


def _format_amount_yuan(value: Any) -> str:
    if value in (None, "", "None", "nan", "NaN"):
        return "待补"
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)
    if abs(number) >= 10000:
        return f"{number / 10000:.2f} 万元"
    return f"{number:.2f} 元"


def _to_plain(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {key: _to_plain(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_to_plain(item) for item in value]
    return value


def _metric_value(
    fund_data: Dict[str, Any],
    performance_data: Dict[str, Any],
    risk_data: Dict[str, Any],
    keys: Iterable[str],
) -> Any:
    raw_data = fund_data.get("raw_data") or {}
    raw_performance = raw_data.get("performance") or {}
    raw_risk = raw_data.get("risk") or {}
    for source in (performance_data, risk_data, raw_performance, raw_risk):
        value = _pick(source, keys)
        if value is not None:
            return value
    return None


def _interpret_return(value: Any) -> str:
    if value in (None, "", "None", "nan", "NaN"):
        return "近一年收益字段缺失，无法直接判断收益弹性。"
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "收益字段口径非数值，需回到净值序列复核。"
    if number >= 0.10:
        return "近一年收益为正且处于较高区间，后续需确认收益是否来自单一市场风格暴露。"
    if number >= 0.03:
        return "近一年收益为正，具备一定阶段性表现，但仍需结合同类排名判断质量。"
    if number >= 0:
        return "近一年收益为正但幅度有限，研究重点应放在回撤控制和持有体验。"
    return "近一年收益为负，需要优先解释亏损来源、市场环境和基金策略匹配度。"


def _interpret_drawdown(value: Any) -> str:
    if value in (None, "", "None", "nan", "NaN"):
        return "最大回撤字段缺失，风险判断需补充净值回撤序列。"
    try:
        drawdown = abs(float(value))
    except (TypeError, ValueError):
        return "最大回撤字段口径非数值，需复核。"
    if drawdown <= 0.03:
        return "最大回撤较低，短期净值稳定性相对更好。"
    if drawdown <= 0.12:
        return "最大回撤中等，需要结合基金类型判断是否合理。"
    if drawdown <= 0.25:
        return "最大回撤偏高，持有体验和止损压力需要重点跟踪。"
    return "最大回撤显著偏高，不适合仅凭收益指标进入候选池。"


def _interpret_sharpe(value: Any) -> str:
    if value in (None, "", "None", "nan", "NaN"):
        return "夏普比率缺失，风险调整收益暂不能完整评价。"
    try:
        sharpe = float(value)
    except (TypeError, ValueError):
        return "夏普比率字段口径非数值，需复核。"
    if sharpe >= 1.5:
        return "夏普比率较强，说明单位波动获得的收益补偿较好。"
    if sharpe >= 0.8:
        return "夏普比率处于可观察区间，需和同类基金做横向比较。"
    if sharpe >= 0:
        return "夏普比率一般，收益质量需要进一步验证。"
    return "夏普比率为负，风险承担未形成有效收益补偿。"


def _normalize_purchase_plan(value: Any) -> str:
    return "lump_sum" if value == "lump_sum" else "sip"


def _purchase_plan_label(purchase_plan: str) -> str:
    return "一次性买入" if purchase_plan == "lump_sum" else "定投"


def _purchase_plan_evidence_fields(purchase_plan: str) -> str:
    if purchase_plan == "lump_sum":
        return "申购状态、起购金额、限购、赎回规则、费率、销售风险等级（R1-R5 30天来源背书）"
    return "申购状态、定投支持、定投起点、限购、赎回规则、费率、销售风险等级（R1-R5 30天来源背书）"


def _holding_identity(holding: Dict[str, Any]) -> str:
    return str(holding.get("stock_name") or holding.get("name") or holding.get("stock_code") or "名称待补")


def _holding_code(holding: Dict[str, Any]) -> str:
    return str(holding.get("stock_code") or holding.get("symbol") or "代码待补")


def _holding_industry(holding: Dict[str, Any]) -> str:
    return str(holding.get("industry") or "行业待补")


def _holding_weight(holding: Dict[str, Any]) -> Any:
    return holding.get("weight")


def _industry_buckets(holdings: List[Dict[str, Any]]) -> List[tuple[str, float]]:
    buckets: Dict[str, float] = {}
    for holding in holdings:
        weight = _holding_weight(holding)
        try:
            parsed = float(weight)
        except (TypeError, ValueError):
            parsed = 0.0
        buckets[_holding_industry(holding)] = buckets.get(_holding_industry(holding), 0.0) + parsed
    return sorted(buckets.items(), key=lambda item: item[1], reverse=True)


def _format_peer_metric_value(metric: Dict[str, Any]) -> str:
    value = metric.get("value")
    unit = metric.get("unit")
    if unit == "percent":
        return _format_percent(value)
    if unit == "score":
        return _format_number(value, digits=1)
    return _format_number(value)


def build_peer_percentile_report_section(peer_percentiles: Optional[Dict[str, Any]]) -> str:
    peer_percentiles = _to_plain(peer_percentiles or {})
    metrics = peer_percentiles.get("metrics") or {}
    sample_status = peer_percentiles.get("sample_status") or "unavailable"
    metric_gap = peer_percentiles.get("peer_metric_gap") or {}
    required_more_funds = metric_gap.get("required_more_funds") or 0
    suggested_codes = metric_gap.get("suggested_sync_codes") or []

    lines = [
        "## 同类分位与胜负线",
        "",
    ]

    if not metrics:
        lines.extend([
            "- 当前缺少同类分位数据，不能用单只基金绝对收益作买前排序。",
            "- 下一步应先同步同类基金净值并生成滚动指标，再回到同类横评。",
            "",
        ])
        return "\n".join(lines).strip() + "\n"

    if sample_status != "sufficient":
        lines.extend([
            f"- **样本状态**：{sample_status}，当前同类分位证据不足。",
            f"- **补证要求**：至少还要补 {required_more_funds} 只同类基金的净值与滚动指标，才能形成稳定分位。",
            f"- **建议同步代码**：{', '.join(suggested_codes[:8]) if suggested_codes else '待系统生成'}。",
            "",
        ])
    else:
        lines.extend([
            f"- **样本状态**：sufficient，已有 {peer_percentiles.get('usable_metric_count') or 0} 个同类指标可用于横向解释。",
            "",
        ])

    rows = []
    strengths = []
    weaknesses = []
    preferred_order = [
        "annualized_return",
        "max_drawdown",
        "annualized_volatility",
        "sharpe_ratio",
        "calmar_ratio",
        "positive_return_ratio",
        "professional_score",
    ]
    for metric_name in preferred_order:
        metric = metrics.get(metric_name)
        if not isinstance(metric, dict):
            continue
        percentile = metric.get("percentile")
        rank = metric.get("rank")
        peer_count = metric.get("peer_count")
        label = metric.get("label") or metric_name
        status = metric.get("sample_status") or "unknown"
        rows.append(
            f"| {label} | {_format_peer_metric_value(metric)} | "
            f"{_format_number(percentile, digits=2) if percentile is not None else '待补'} | "
            f"{rank or '待补'}/{peer_count or '待补'} | {status} |"
        )
        if isinstance(percentile, (int, float)) and percentile >= 70:
            strengths.append(f"{label}分位{_format_number(percentile, digits=0)}")
        if isinstance(percentile, (int, float)) and percentile < 30:
            weaknesses.append(f"{label}分位{_format_number(percentile, digits=0)}")

    lines.extend([
        "| 指标 | 本基金数值 | 同类分位 | 排名 | 样本状态 |",
        "| --- | --- | --- | --- | --- |",
        *(rows or ["| 同类指标 | 待补 | 待补 | 待补 | unavailable |"]),
        "",
    ])

    if sample_status != "sufficient":
        decision_line = "同类分位证据不足，不能输出同类胜负结论。"
    elif strengths and weaknesses:
        decision_line = f"{'、'.join(strengths[:2])}占优，但{'、'.join(weaknesses[:2])}落后，属于收益弹性强、持有体验压力也高的样本。"
    elif strengths:
        decision_line = f"{'、'.join(strengths[:2])}占优，具备进入同类横评的优势线索。"
    elif weaknesses:
        decision_line = f"{'、'.join(weaknesses[:2])}落后，优先寻找同类替代，不宜单独进入买前候选。"
    else:
        decision_line = "同类优势不突出，应继续与同画像替代基金比较。"

    lines.extend([
        f"- **同类胜负线**：{decision_line}",
        "- **买前含义**：同类分位只能作为研究排序证据；销售规则、风险等级、费率、赎回规则和净值回放仍是正式买前硬门禁。",
        "",
    ])
    return "\n".join(lines).strip() + "\n"


def _metric_panel(metrics: Optional[List[Dict[str, Any]]], window: str) -> Dict[str, Dict[str, Any]]:
    panel: Dict[str, Dict[str, Any]] = {}
    for item in metrics or []:
        if item.get("metric_window") == window and item.get("metric_name"):
            panel[str(item.get("metric_name"))] = item
    return panel


def _snapshot_value(metric: Optional[Dict[str, Any]]) -> Any:
    if not metric:
        return None
    return metric.get("metric_value")


def build_manager_tenure_report_section(
    managers: Optional[List[Dict[str, Any]]],
    tenure_metrics: Optional[List[Dict[str, Any]]],
) -> str:
    managers = _to_plain(managers or [])
    panel = _metric_panel(_to_plain(tenure_metrics or []), "manager_tenure")
    manager_names = "、".join([str(item.get("name") or item.get("manager_id") or "经理待补") for item in managers]) or "待补"
    tenure_days = _snapshot_value(panel.get("tenure_days"))
    annualized_return = _snapshot_value(panel.get("annualized_return"))
    max_drawdown = _snapshot_value(panel.get("max_drawdown"))
    sharpe_ratio = _snapshot_value(panel.get("sharpe_ratio"))
    positive_return_ratio = _snapshot_value(panel.get("positive_return_ratio"))
    observations = _snapshot_value(panel.get("observations"))

    lines = [
        "## 现任经理任期切片",
        "",
        f"- **现任经理**：{manager_names}。",
    ]
    if not panel:
        lines.extend([
            "- **任期指标状态**：待补。当前未取得现任经理任期起点或任期内净值样本，不能把基金历史业绩直接归因给现任经理。",
            "- **买前含义**：需要先同步基金经理任职关系并生成 manager_tenure 指标，再判断经理接手后的收益、回撤和胜率。",
            "",
        ])
        return "\n".join(lines).strip() + "\n"

    lines.extend([
        f"- **任期天数**：{_format_number(tenure_days, digits=0)} 天；有效净值样本 {_format_number(observations, digits=0)} 个。",
        "",
        "| 任期切片指标 | 数值 | 研究含义 |",
        "| --- | --- | --- |",
        f"| 任期年化收益 | {_format_percent(annualized_return)} | 只评价现任经理接手后的收益弹性。 |",
        f"| 任期最大回撤 | {_format_percent(max_drawdown)} | 只评价现任经理接手后的下行体验。 |",
        f"| 任期夏普 | {_format_number(sharpe_ratio)} | 判断任期内风险补偿是否成立。 |",
        f"| 任期正收益占比 | {_format_percent(positive_return_ratio)} | 辅助观察任期内收益连续性。 |",
        "",
        "- **买前含义**：基金经理评价必须落到这只基金的任期切片上；不能把经理历史代表作或前任经理业绩直接外推为本基金买前结论。",
        "",
    ])
    return "\n".join(lines).strip() + "\n"


def _redemption_rules_text(rules: Any) -> str:
    if not isinstance(rules, list) or not rules:
        return "待补"
    parts = []
    for rule in rules[:5]:
        if not isinstance(rule, dict):
            continue
        label = rule.get("label") or "赎回费"
        fee_rate = rule.get("feeRate", rule.get("fee_rate"))
        holding_days = rule.get("holdingDays", rule.get("holding_days"))
        days_text = "持有期待补" if holding_days in (None, "", "None") else f"持有≥{_format_number(holding_days, digits=0)}天"
        parts.append(f"{label} {days_text}：{_format_percent(fee_rate)}")
    return "；".join(parts) if parts else "待补"


def _field(rule: Dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = rule.get(key)
        if value not in (None, "", "None", "nan", "NaN"):
            return value
    return None


def _is_fresh_source_date(value: Any) -> bool:
    if value in (None, "", "None", "nan", "NaN"):
        return False
    text = str(value).strip()[:10]
    try:
        source_date = datetime.fromisoformat(text).date()
    except ValueError:
        return False
    today = datetime.now(UTC).date()
    age_days = (today - source_date).days
    return 0 <= age_days <= RISK_LEVEL_SOURCE_MAX_AGE_DAYS


_PLACEHOLDER_SOURCE_VALUES = {
    "-",
    "--",
    "na",
    "n/a",
    "none",
    "null",
    "unknown",
    "tbd",
    "todo",
    "placeholder",
    "sample",
    "example",
    "demo",
    "mock",
    "test",
    "待补",
    "待核",
    "待确认",
    "暂无",
    "无",
    "示例",
    "样例",
    "测试",
    "占位",
    "来源待补",
    "待补来源",
    "链接待补",
    "待补链接",
    "示例链接",
    "样例链接",
    "测试链接",
    "占位链接",
    "备注待补",
    "待补备注",
}


def _is_placeholder_source_text(value: Any) -> bool:
    if value in (None, "", "None", "nan", "NaN"):
        return False
    text = str(value).strip().lower()
    if text in _PLACEHOLDER_SOURCE_VALUES:
        return True
    return text.startswith(("https://example.", "http://example."))


def _has_source_evidence(rule: Dict[str, Any]) -> bool:
    platform = str(_field(rule, "platform") or "").strip().lower()
    if "tushare" in platform:
        return False
    source_url = str(_field(rule, "source_url", "sourceUrl") or "").strip()
    notes = str(_field(rule, "notes") or "").strip()
    normalized_source_url = source_url.lower()
    return bool(
        (
            source_url
            and "tushare.fund_basic" not in normalized_source_url
            and not _is_placeholder_source_text(source_url)
        )
        or (notes and not _is_placeholder_source_text(notes))
    )


def _has_source_backed_redemption_rules(rule: Dict[str, Any]) -> bool:
    if not _field(rule, "redemption_fee_rules", "redemptionFeeRules"):
        return False
    source_updated_at = _field(rule, "redemption_fee_source_updated_at", "redemptionFeeSourceUpdatedAt", "source_updated_at", "sourceUpdatedAt")
    if not _is_fresh_source_date(source_updated_at):
        return False
    source_rule = {
        "platform": _field(rule, "redemption_fee_platform", "redemptionFeePlatform", "platform"),
        "source_url": _field(rule, "redemption_fee_source_url", "redemptionFeeSourceUrl", "source_url", "sourceUrl"),
        "notes": _field(rule, "redemption_fee_notes", "redemptionFeeNotes", "notes"),
    }
    return _has_source_evidence(source_rule)


def _has_source_backed_sales_risk_level(rule: Dict[str, Any]) -> bool:
    risk_level = str(_field(rule, "risk_level", "riskLevel") or "").strip().upper()
    if risk_level not in {"R1", "R2", "R3", "R4", "R5"}:
        return False
    if not _is_fresh_source_date(_field(rule, "source_updated_at", "sourceUpdatedAt")):
        return False
    return _has_source_evidence(rule)


def _has_field_value(rule: Dict[str, Any], *keys: str) -> bool:
    for key in keys:
        value = rule.get(key)
        if value not in (None, "", "None", "nan", "NaN"):
            return True
    return False


def _has_source_backed_sales_rule_field(rule: Dict[str, Any], snake_flag: str, camel_flag: str, *value_keys: str) -> bool:
    if not _has_field_value(rule, *value_keys):
        return False
    explicit_flag = _field(rule, snake_flag, camel_flag)
    if explicit_flag is True:
        return True
    if explicit_flag is False:
        return False
    if not _is_fresh_source_date(_field(rule, "source_updated_at", "sourceUpdatedAt")):
        return False
    return _has_source_evidence(rule)


def _sales_risk_level_evidence_text(rule: Dict[str, Any]) -> tuple[str, str]:
    risk_level = str(_field(rule, "risk_level", "riskLevel") or "").strip().upper()
    if risk_level not in {"R1", "R2", "R3", "R4", "R5"}:
        return "待补", "未取得销售平台或基金合同 R1-R5，不能用于适当性匹配。"
    source_updated_at = _field(rule, "source_updated_at", "sourceUpdatedAt")
    if not source_updated_at:
        return f"{risk_level}（缺来源日期）", "已填写 R1-R5 但缺少可追溯来源日期，仍按硬缺口处理。"
    if not _is_fresh_source_date(source_updated_at):
        return f"{risk_level}（来源过期）", "来源日期不在 30 天买前复核窗口内，需重新核验销售平台或基金合同。"
    platform = str(_field(rule, "platform") or "").strip().lower()
    if "tushare" in platform:
        return f"{risk_level}（来源不可用）", "Tushare fund_basic 不是 R1-R5 正式来源，不能用于适当性匹配。"
    if not _has_source_evidence(rule):
        return f"{risk_level}（缺来源背书）", "缺少销售平台/基金合同 URL 或人工核验备注，仍按硬缺口处理。"
    return f"{risk_level}（30天内有来源）", "具备 30 天内销售平台/基金合同来源背书；正式买前仍需复核实时页面。"


def _sales_rule_missing_items(rule: Dict[str, Any], purchase_plan: str) -> List[str]:
    missing = []
    if not _has_source_backed_sales_rule_field(rule, "purchase_status_source_backed", "purchaseStatusSourceBacked", "purchase_status", "purchaseStatus"):
        missing.append("申购状态（30天来源背书）")
    if not _has_source_backed_sales_rule_field(rule, "purchase_fee_source_backed", "purchaseFeeSourceBacked", "purchase_fee_rate", "purchaseFeeRate"):
        missing.append("申购费率（30天来源背书）")
    if not _has_source_backed_redemption_rules(rule):
        missing.append("赎回费/持有期（30天来源背书）")
    if not _has_source_backed_sales_rule_field(rule, "min_purchase_source_backed", "minPurchaseSourceBacked", "min_purchase_amount", "minPurchaseAmount"):
        missing.append("起购金额（30天来源背书）")
    if not _has_source_backed_sales_rule_field(rule, "daily_limit_source_backed", "dailyLimitSourceBacked", "daily_limit_amount", "dailyLimitAmount"):
        missing.append("限购金额（30天来源背书）")
    if not _has_source_backed_sales_rule_field(rule, "sales_service_fee_source_backed", "salesServiceFeeSourceBacked", "sales_service_fee_rate", "salesServiceFeeRate"):
        missing.append("销售服务费（30天来源背书）")
    if not _has_source_backed_sales_risk_level(rule):
        missing.append("销售风险等级（R1-R5 30天来源背书）")
    if purchase_plan == "sip":
        supports_sip_backed = _has_source_backed_sales_rule_field(rule, "supports_sip_source_backed", "supportsSipSourceBacked", "supports_sip", "supportsSip")
        supports_sip = _field(rule, "supports_sip", "supportsSip")
        if not supports_sip_backed:
            missing.append("定投支持（30天来源背书）")
        if supports_sip_backed and supports_sip is True and not _has_source_backed_sales_rule_field(rule, "min_sip_source_backed", "minSipSourceBacked", "min_sip_amount", "minSipAmount"):
            missing.append("定投起点（30天来源背书）")
    return missing


def build_sales_rule_cost_report_section(sales_rule_data: Optional[Dict[str, Any]], purchase_plan: str = "sip") -> str:
    snapshot = _to_plain(sales_rule_data or {})
    merged = snapshot.get("merged") or {}
    status = snapshot.get("status") or "unavailable"
    purchase_plan_label = _purchase_plan_label(_normalize_purchase_plan(purchase_plan))

    lines = [
        "## 费用与销售规则快照",
        "",
    ]
    if status != "available" or not merged:
        lines.extend([
            f"- **当前口径**：{purchase_plan_label}。",
            "- **证据状态**：本地未取得销售规则快照；不能判断是否可申购、费率成本、赎回成本、限购或 R1-R5 适当性。",
            "- **买前含义**：销售规则缺失时，报告只能作为研究材料，不能进入正式购买候选。",
            "",
        ])
        return "\n".join(lines).strip() + "\n"

    missing = _sales_rule_missing_items(merged, _normalize_purchase_plan(purchase_plan))
    risk_level_text, risk_level_meaning = _sales_risk_level_evidence_text(merged)
    lines.extend([
        f"- **当前口径**：{purchase_plan_label}。",
        f"- **规则来源**：{snapshot.get('source') or 'local_postgres.fund_sales_rules'}；平台 {merged.get('platform') or '待补'}；来源日期 {merged.get('source_updated_at') or '待补'}。",
        f"- **R1-R5 来源背书**：{risk_level_text}；要求 30 天内销售平台或基金合同来源，Tushare fund_basic 不可作为 R1-R5 来源。",
        f"- **赎回规则来源背书**：要求同一条赎回费分档具备 30 天内销售平台/基金合同来源日期，且有 URL 或人工核验备注；Tushare fund_basic 或无来源分档不参与正式买前回放。",
        "- **交易字段来源背书**：申购状态、申购费、起购/定投、限购和销售服务费同样要求 30 天内销售平台/基金合同来源背书；只有数值没有来源不进入正式买前结论。",
        "",
        "| 字段 | 当前值 | 买前含义 |",
        "| --- | --- | --- |",
        f"| 申购状态 | {merged.get('purchase_status_label') or merged.get('purchase_status') or '待补'} | 未开放或限购时不能进入正式买前结论。 |",
        f"| 起购金额 | {_format_amount_yuan(merged.get('min_purchase_amount'))} | 一次性买入需满足起购和限购约束。 |",
        f"| 定投起点 | {_format_amount_yuan(merged.get('min_sip_amount'))} | 定投口径必须确认支持定投与最低扣款金额。 |",
        f"| 限购金额 | {_format_amount_yuan(merged.get('daily_limit_amount'))} | 限购会影响买入执行和资金安排。 |",
        f"| 申购费率 | {_format_percent(merged.get('purchase_fee_rate'))} | 影响初始成本，需结合销售平台折扣复核。 |",
        f"| 销售服务费 | {_format_percent(merged.get('sales_service_fee_rate'))} | C 类或短持场景需重点核验年化持有成本。 |",
        f"| 赎回规则 | {_redemption_rules_text(merged.get('redemption_fee_rules'))} | 短持赎回成本会改变真实收益体验。 |",
        f"| 销售风险等级 | {risk_level_text} | {risk_level_meaning} |",
        "",
    ])
    lines.append(
        f"- **销售规则缺口**：{', '.join(missing) if missing else '当前快照未发现关键字段缺口；正式买前仍需复核销售平台实时页面。'}"
    )
    lines.append("- **买前含义**：费用、赎回、限购和 R1-R5 是购买前硬门禁；即使研究评分、同类分位和经理任期证据较好，也不能绕过该门禁。")
    lines.append("")
    return "\n".join(lines).strip() + "\n"


def build_buy_before_decision_summary(
    peer_percentiles: Optional[Dict[str, Any]],
    sales_rule_data: Optional[Dict[str, Any]],
    holdings: Optional[List[Dict[str, Any]]],
    manager_tenure_metrics: Optional[List[Dict[str, Any]]],
    purchase_plan: str = "sip",
) -> Dict[str, Any]:
    safe_purchase_plan = _normalize_purchase_plan(purchase_plan)
    sales_rule_snapshot = _to_plain(sales_rule_data or {})
    sales_rule_merged = sales_rule_snapshot.get("merged") or {}
    sales_rule_missing = _sales_rule_missing_items(sales_rule_merged, safe_purchase_plan) if sales_rule_merged else [_purchase_plan_evidence_fields(safe_purchase_plan)]
    peer_status = (peer_percentiles or {}).get("sample_status") or "unavailable"
    peer_metrics = (peer_percentiles or {}).get("metrics") or {}
    tenure_available = bool(_metric_panel(manager_tenure_metrics or [], "manager_tenure"))
    sorted_holdings = sorted(holdings or [], key=lambda item: float(_holding_weight(item) or 0), reverse=True)
    top_ten_weight = sum(float(_holding_weight(holding) or 0) for holding in sorted_holdings[:10])
    top_industry = (_industry_buckets(holdings or []) or [("行业待补", 0.0)])[0]

    hard_blocks = []
    caution_flags = []
    next_actions = []

    if sales_rule_missing:
        hard_blocks.append(f"销售规则缺口：{', '.join(sales_rule_missing[:8])}")
        next_actions.append("先补齐销售平台申购、费率、赎回、限购和 R1-R5 证据")
    if peer_status != "sufficient":
        caution_flags.append("同类分位样本不足，不能做同类胜负排序")
        next_actions.append("同步同类基金净值并重算滚动指标")
    if not tenure_available:
        caution_flags.append("现任经理任期切片缺失，不能把历史业绩归因给当前经理")
        next_actions.append("同步经理任职关系并生成 manager_tenure 指标")
    if top_ten_weight >= 0.70:
        caution_flags.append(f"前十大持仓集中度 {_format_percent(top_ten_weight)}，持有体验依赖少数重仓")
    if top_industry[1] >= 0.50:
        caution_flags.append(f"第一行业 {top_industry[0]} {_format_percent(top_industry[1])}，不能按普通分散型基金理解")

    weak_peer_metrics = [
        metric.get("label") or metric_name
        for metric_name, metric in peer_metrics.items()
        if isinstance(metric, dict) and isinstance(metric.get("percentile"), (int, float)) and metric.get("percentile") < 30
    ]
    if weak_peer_metrics:
        caution_flags.append(f"同类短板：{', '.join(weak_peer_metrics[:4])}落在后 30% 区间")
        next_actions.append("把同类替代基金加入横评，重点比较回撤、波动和赎回成本")

    if hard_blocks:
        status = "blocked_by_hard_gate"
        status_label = "硬阻断：不能进入正式买前结论"
    elif caution_flags:
        status = "verify_first"
        status_label = "先复核：只能作为研究观察样本"
    else:
        status = "research_ready"
        status_label = "研究证据相对完整，仍需完成正式买前复核"

    if not next_actions:
        next_actions.append("生成正式买前报告前复核销售平台实时规则、净值回放和同类替代")

    return {
        "status": status,
        "label": status_label,
        "purchasePlan": safe_purchase_plan,
        "purchasePlanLabel": _purchase_plan_label(safe_purchase_plan),
        "hardBlocks": list(dict.fromkeys(hard_blocks)),
        "cautionFlags": list(dict.fromkeys(caution_flags)),
        "nextActions": list(dict.fromkeys(next_actions)),
    }


def build_buy_before_decision_section(
    peer_percentiles: Optional[Dict[str, Any]],
    sales_rule_data: Optional[Dict[str, Any]],
    holdings: Optional[List[Dict[str, Any]]],
    manager_tenure_metrics: Optional[List[Dict[str, Any]]],
    purchase_plan: str = "sip",
) -> str:
    summary = build_buy_before_decision_summary(
        peer_percentiles,
        sales_rule_data,
        holdings,
        manager_tenure_metrics,
        purchase_plan,
    )
    lines = [
        "## 买前总闸门结论",
        "",
        f"- **状态**：{summary['label']}（{summary['status']}）。",
        f"- **买入方式口径**：{summary['purchasePlanLabel']}。",
        f"- **硬阻断**：{'; '.join(summary['hardBlocks']) if summary['hardBlocks'] else '当前报告输入未发现硬阻断，但仍需复核销售平台实时页面。'}",
        f"- **风险提示**：{'; '.join(summary['cautionFlags']) if summary['cautionFlags'] else '当前报告输入未触发额外风险提示。'}",
        "- **下一步动作**：",
        *[f"  - {action}" for action in summary["nextActions"]],
        "",
        "该结论只用于基金研究流程分流，不构成买卖建议、仓位建议或组合配置建议。",
        "",
    ]
    return "\n".join(lines).strip() + "\n"


def build_fund_research_report(
    fund_data: Dict[str, Any],
    performance_data: Optional[Dict[str, Any]] = None,
    risk_data: Optional[Dict[str, Any]] = None,
    style_data: Optional[Dict[str, Any]] = None,
    scoring_result: Optional[Dict[str, Any]] = None,
    holdings_data: Optional[List[Dict[str, Any]]] = None,
    peer_percentiles: Optional[Dict[str, Any]] = None,
    manager_data: Optional[List[Dict[str, Any]]] = None,
    manager_tenure_metrics: Optional[List[Dict[str, Any]]] = None,
    sales_rule_data: Optional[Dict[str, Any]] = None,
    purchase_plan: str = "sip",
) -> str:
    performance = _to_plain(performance_data or fund_data.get("performance_data") or {})
    risk = _to_plain(risk_data or fund_data.get("risk_metrics") or {})
    style = _to_plain(style_data or {})
    scoring = _to_plain(scoring_result or {})
    holdings = holdings_data or []
    peer_percentiles = peer_percentiles or fund_data.get("peer_percentiles") or {}
    manager_data = manager_data or fund_data.get("managers") or []
    manager_tenure_metrics = manager_tenure_metrics or fund_data.get("manager_tenure_metrics") or []
    sales_rule_data = sales_rule_data or fund_data.get("sales_rule_data") or {}
    raw_data = fund_data.get("raw_data") or {}
    safe_purchase_plan = _normalize_purchase_plan(purchase_plan)
    purchase_plan_label = _purchase_plan_label(safe_purchase_plan)
    purchase_plan_evidence_fields = _purchase_plan_evidence_fields(safe_purchase_plan)

    name = fund_data.get("name") or fund_data.get("fund_name") or fund_data.get("wind_code") or "未知基金"
    code = fund_data.get("wind_code") or fund_data.get("ts_code") or fund_data.get("code") or "未知代码"
    fund_type = fund_data.get("type") or fund_data.get("fund_type") or "待补"
    company = fund_data.get("management_company") or _pick(raw_data.get("info") or {}, ["management_company", "manager", "mgt_name"]) or "待补"
    nav = fund_data.get("nav") or _pick(raw_data.get("info") or {}, ["nav", "unit_nav", "accum_nav"])
    nav_date = fund_data.get("nav_date") or _pick(raw_data.get("info") or {}, ["nav_date", "end_date"])
    total_asset = fund_data.get("total_asset") or _pick(raw_data.get("info") or {}, ["total_asset", "asset"])
    establishment_date = fund_data.get("establishment_date") or _pick(raw_data.get("info") or {}, ["establishment_date", "found_date", "setup_date"])
    synced_at = raw_data.get("synced_at") or fund_data.get("updated_at")

    annual_return_1y = _metric_value(fund_data, performance, risk, ["annualized_return_1y", "return_1y", "yoy", "total_return"])
    annual_return_3y = _metric_value(fund_data, performance, risk, ["annualized_return_3y", "return_3y"])
    volatility = _metric_value(fund_data, performance, risk, ["annualized_volatility_1y", "volatility", "annualized_volatility"])
    max_drawdown = _metric_value(fund_data, performance, risk, ["max_drawdown_1y", "max_drawdown"])
    sharpe = _metric_value(fund_data, performance, risk, ["sharpe_ratio", "sharpe"])
    sortino = _metric_value(fund_data, performance, risk, ["sortino", "sortino_ratio"])
    calmar = _metric_value(fund_data, performance, risk, ["calmar_ratio", "calmar"])
    information_ratio = _metric_value(fund_data, performance, risk, ["information_ratio", "ir"])
    tracking_error = _metric_value(fund_data, performance, risk, ["tracking_error"])
    alpha = _metric_value(fund_data, performance, risk, ["alpha"])
    beta = _metric_value(fund_data, performance, risk, ["beta"])
    var_95 = _metric_value(fund_data, performance, risk, ["var_95", "VaR_95"])
    win_rate = _metric_value(fund_data, performance, risk, ["win_rate_1y", "win_rate"])

    evidence_gaps: List[str] = []
    if nav in (None, "", "None"):
        evidence_gaps.append("最新单位净值/累计净值字段缺失")
    if total_asset in (None, "", "None"):
        evidence_gaps.append("基金规模字段缺失")
    if not holdings:
        evidence_gaps.append("持仓、行业配置与重仓股数据未入库，本报告不做持仓归因")
    if not style or style.get("data_status") == "unavailable":
        evidence_gaps.append("Barra/风格暴露数据不可用，本报告只做净值绩效维度判断")
    elif style.get("style_factors_status") == "unavailable":
        evidence_gaps.append("已取得持仓派生行业暴露，但 Barra 风格因子不可用，不能输出风格稳定性结论")
    if annual_return_1y in (None, "", "None"):
        evidence_gaps.append("近一年收益字段缺失")
    if max_drawdown in (None, "", "None"):
        evidence_gaps.append("最大回撤字段缺失")
    if (peer_percentiles.get("sample_status") or "unavailable") != "sufficient":
        evidence_gaps.append("同类分位样本不足或缺失，不能输出正式同类胜负结论")
    if not _metric_panel(manager_tenure_metrics, "manager_tenure"):
        evidence_gaps.append("现任经理任期切片指标缺失，不能把历史业绩直接归因给现任经理")
    sales_rule_snapshot = _to_plain(sales_rule_data or {})
    sales_rule_merged = sales_rule_snapshot.get("merged") or {}
    sales_rule_missing = _sales_rule_missing_items(sales_rule_merged, safe_purchase_plan) if sales_rule_merged else [purchase_plan_evidence_fields]
    if sales_rule_missing:
        evidence_gaps.append(f"{purchase_plan_label}买前销售证据缺口：{', '.join(sales_rule_missing)}")

    score = scoring.get("overall_score")
    if score is None:
        score_line = "未刷新系统评分；本报告暂不引用综合评分。"
    else:
        score_line = f"系统评分为 {_format_number(score, digits=1)}，需结合评分模型版本和同类分布解释。"
    sorted_holdings = sorted(holdings, key=lambda item: float(_holding_weight(item) or 0), reverse=True)
    industry_buckets = _industry_buckets(holdings)
    top_ten_weight = sum(float(_holding_weight(holding) or 0) for holding in sorted_holdings[:10])
    top_industry = industry_buckets[0] if industry_buckets else ("行业待补", 0.0)
    if holdings:
        top_holding = sorted_holdings[0]
        top_holding_line = f"已取得 {len(holdings)} 条本地持仓，第一重仓为 {_holding_identity(top_holding)}（{_format_percent(_holding_weight(top_holding))}）。"
    else:
        top_holding_line = "当前未取得可靠持仓数据，不对行业、个股或风格暴露作确定性判断。"

    holding_rows = "\n".join(
        f"| {index + 1} | {_holding_identity(holding)} | {_holding_code(holding)} | {_holding_industry(holding)} | {_format_percent(_holding_weight(holding))} |"
        for index, holding in enumerate(sorted_holdings[:10])
    )
    industry_rows = "\n".join(
        f"| {industry} | {_format_percent(weight)} |"
        for industry, weight in industry_buckets[:8]
    )
    top_ten_risk = (
        f"前十大合计 {_format_percent(top_ten_weight)}，持仓集中度显著偏高，单一赛道回撤会直接影响持有体验。"
        if top_ten_weight >= 0.70
        else f"前十大合计 {_format_percent(top_ten_weight)}，仍需和同类基金比较集中度。"
    )
    industry_risk = (
        f"第一行业 {top_industry[0]} {_format_percent(top_industry[1])}，行业主题暴露很高，不能按普通分散型基金理解。"
        if top_industry[1] >= 0.50
        else f"第一行业 {top_industry[0]} {_format_percent(top_industry[1])}，需继续观察行业漂移。"
    )

    generated_at = datetime.now(UTC).isoformat()
    lines = [
        f"# {name}（{code}）基金研究报告",
        "",
        "> 报告模式：deterministic_evidence_backed。本报告由本地 PostgreSQL 中的 Tushare 入库字段生成，不使用演示数据；缺失字段会显式标记为“待补”。",
        "",
        "## 1. 基金概况",
        "",
        "| 字段 | 当前值 |",
        "| --- | --- |",
        f"| 基金代码 | {code} |",
        f"| 基金名称 | {name} |",
        f"| 基金类型 | {fund_type} |",
        f"| 管理人/公司 | {company} |",
        f"| 成立日期 | {establishment_date or '待补'} |",
        f"| 最新净值 | {_format_number(nav, digits=4)} |",
        f"| 净值日期 | {nav_date or '待补'} |",
        f"| 基金规模 | {_format_money_yi(total_asset)} |",
        f"| 买入方式口径 | {purchase_plan_label} |",
        f"| 数据同步时间 | {synced_at or '待补'} |",
        "",
        "## 2. 绩效与风险指标",
        "",
        "| 维度 | 指标 | 数值 | 研究含义 |",
        "| --- | --- | --- | --- |",
        f"| 收益 | 近一年年化收益 | {_format_percent(annual_return_1y)} | {_interpret_return(annual_return_1y)} |",
        f"| 收益 | 近三年年化收益 | {_format_percent(annual_return_3y)} | 用于判断表现是否跨周期稳定；成立时间不足时需谨慎解读。 |",
        f"| 风险 | 年化波动率 | {_format_percent(volatility)} | 波动率越高，对持有人风险承受力要求越高。 |",
        f"| 风险 | 最大回撤 | {_format_percent(max_drawdown)} | {_interpret_drawdown(max_drawdown)} |",
        f"| 风险调整 | 夏普比率 | {_format_number(sharpe)} | {_interpret_sharpe(sharpe)} |",
        f"| 风险调整 | Sortino | {_format_number(sortino)} | 侧重下行波动惩罚，可辅助判断下行风险补偿。 |",
        f"| 风险调整 | Calmar | {_format_number(calmar)} | 收益与最大回撤的关系，适合观察回撤修复能力。 |",
        f"| 主动风险 | 信息比率 | {_format_number(information_ratio)} | 衡量超额收益相对主动风险的效率。 |",
        f"| 主动风险 | 跟踪误差 | {_format_percent(tracking_error)} | 跟踪误差越高，说明相对基准偏离越大。 |",
        f"| 暴露 | Alpha | {_format_percent(alpha)} | Alpha 需结合基准口径确认，不单独作为结论。 |",
        f"| 暴露 | Beta | {_format_number(beta)} | Beta 反映市场敏感度，需与基金合同策略匹配。 |",
        f"| 尾部风险 | VaR 95% | {_format_percent(var_95)} | 用于观察单期潜在损失区间，需补充净值分布验证。 |",
        f"| 胜率 | 近一年胜率 | {_format_percent(win_rate)} | 胜率可辅助观察收益连续性，但不能替代收益风险比。 |",
        "",
        "## 3. 研究判断",
        "",
        f"- **收益质量**：{_interpret_return(annual_return_1y)}",
        f"- **回撤控制**：{_interpret_drawdown(max_drawdown)}",
        f"- **风险补偿**：{_interpret_sharpe(sharpe)}",
        f"- **系统评分**：{score_line}",
        f"- **持仓归因边界**：{top_holding_line}",
        "",
        build_peer_percentile_report_section(peer_percentiles).strip(),
        "",
        build_manager_tenure_report_section(manager_data, manager_tenure_metrics).strip(),
        "",
        build_sales_rule_cost_report_section(sales_rule_data, safe_purchase_plan).strip(),
        "",
        build_buy_before_decision_section(
            peer_percentiles,
            sales_rule_data,
            holdings,
            manager_tenure_metrics,
            safe_purchase_plan,
        ).strip(),
        "",
        "## 4. 持仓与行业暴露",
        "",
    ]

    if holdings:
        lines.extend([
            "| # | 重仓标的 | 代码 | 行业 | 权重 |",
            "| --- | --- | --- | --- | --- |",
            holding_rows,
            "",
            "| 行业 | 合计权重 |",
            "| --- | --- |",
            industry_rows or "| 行业待补 | 待补 |",
            "",
            "### 持仓集中度诊断",
            "",
            f"- **前十大集中度**：{top_ten_risk}",
            f"- **第一行业暴露**：{industry_risk}",
            f"- **第一重仓**：{_holding_identity(sorted_holdings[0])}（{_holding_code(sorted_holdings[0])}）权重 {_format_percent(_holding_weight(sorted_holdings[0]))}。",
            "- **买前含义**：若投资者无法承受该行业或第一重仓的阶段性回撤，应先进入同类替代和份额/主题风险比较，而不是直接进入正式买前结论。",
            "",
            "以上持仓来自本地已入库季度持仓，只用于解释行业/个股暴露；买前仍需复核基金季报与销售平台披露。",
            "Barra 风格因子（如 SIZE/BETA/MOMENTUM）未接入可信因子库时保持待补，不用行业暴露反推风格稳定性。",
            "",
        ])
    else:
        lines.extend([
            "- 持仓、行业配置与重仓股数据未入库，本报告不做行业/个股归因。",
            "- 不能把持仓缺失视为行业分散、个股集中度正常或风格稳定。",
            "",
        ])

    lines.extend([
        "## 5. 买前可买性口径",
        "",
        f"- **当前口径**：{purchase_plan_label}。",
        f"- **硬性证据**：进入正式买前判断前，必须补齐并复核{purchase_plan_evidence_fields}。",
        "- **评分边界**：本报告中的系统评分、收益风险指标和研究判断只用于研究排序，不能替代销售规则、风险等级、费用与赎回规则、净值回放和正式买前报告。",
        "- **缺口处理**：任一硬性证据缺失时，应保持“先补证再判断”，不得把缺失证据视为中性或默认通过。",
        "",
        "## 6. 后续跟踪问题",
        "",
        "- 补齐最新净值序列，复核收益、回撤、波动率的计算窗口和复权口径。",
        f"- 补齐基金规模、{purchase_plan_evidence_fields}和持有人结构，判断基金是否具备真实可买性和容量约束。",
        "- 补齐季报持仓和行业分类，再做行业/个股贡献与风格漂移分析。",
        "- 与同类型基金建立分位数对比，避免单只基金绝对指标误导。",
        "",
        "## 7. 证据缺口",
        "",
    ])

    if evidence_gaps:
        lines.extend([f"- {gap}" for gap in evidence_gaps])
    else:
        lines.append("- 当前基础字段相对完整；仍需按基金类型补充同类分位数和持仓归因。")

    lines.extend([
        "",
        "## 8. 研究边界声明",
        "",
        "本报告仅用于基金研究、筛选和后续跟踪，不构成买卖建议、仓位建议或组合配置建议。",
        "",
        f"---\n生成时间：{generated_at}",
    ])

    return "\n".join(lines).strip() + "\n"
