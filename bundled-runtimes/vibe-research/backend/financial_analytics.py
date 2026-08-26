"""Lightweight, auditable financial analytics for the equity research view.

This module deliberately avoids pandas/scipy and never fetches data itself. It
only derives ratios and bounded structural scores from the existing evidence
ledger, keeping every result traceable to its source evidence IDs.
"""

from __future__ import annotations

from dataclasses import dataclass
from statistics import fmean
from typing import Any, Iterable, Protocol


class EvidenceLike(Protocol):
    id: str
    value: Any
    as_of: str | None
    confidence: str


@dataclass(frozen=True)
class DerivedMetric:
    id: str
    dimension: str
    label: str
    value: float
    unit: str
    depends_on: tuple[str, ...]
    method: str
    interpretation: str
    as_of: str | None = None
    confidence: str = "medium"


@dataclass(frozen=True)
class AxisScore:
    id: str
    title: str
    score: float | None
    status: str
    summary: str
    evidence_ids: tuple[str, ...]
    signal_count: int
    method: str


@dataclass(frozen=True)
class AnalysisResult:
    metrics: tuple[DerivedMetric, ...]
    scorecard: tuple[AxisScore, ...]
    gaps: tuple[str, ...]


def _number(value: Any) -> float | None:
    if isinstance(value, str):
        value = value.strip().replace(",", "").removesuffix("%").strip()
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number != number or number in (float("inf"), float("-inf")):
        return None
    return number


def _interpolate(value: float, points: tuple[tuple[float, float], ...]) -> float:
    if value <= points[0][0]:
        return points[0][1]
    if value >= points[-1][0]:
        return points[-1][1]
    for (left_x, left_y), (right_x, right_y) in zip(points, points[1:]):
        if left_x <= value <= right_x:
            ratio = (value - left_x) / (right_x - left_x)
            return left_y + ratio * (right_y - left_y)
    return points[-1][1]


def _status(score: float | None) -> str:
    if score is None:
        return "unavailable"
    if score >= 75:
        return "strong"
    if score >= 55:
        return "balanced"
    if score >= 35:
        return "watch"
    return "weak"


def _axis(
    axis_id: str,
    title: str,
    signals: list[tuple[float, str]],
    method: str,
) -> AxisScore:
    if not signals:
        return AxisScore(
            id=axis_id,
            title=title,
            score=None,
            status="unavailable",
            summary="证据不足，暂不生成结构评分",
            evidence_ids=(),
            signal_count=0,
            method=method,
        )
    score = round(fmean(item[0] for item in signals), 1)
    status = _status(score)
    summaries = {
        "strong": "现有证据显示该维度结构较强",
        "balanced": "现有证据显示该维度处于中性区间",
        "watch": "现有证据提示该维度需要持续观察",
        "weak": "现有证据提示该维度承压",
    }
    return AxisScore(
        id=axis_id,
        title=title,
        score=score,
        status=status,
        summary=summaries[status],
        evidence_ids=tuple(dict.fromkeys(item[1] for item in signals)),
        signal_count=len(signals),
        method=method,
    )


def analyze_financials(evidence: Iterable[EvidenceLike]) -> AnalysisResult:
    items = {item.id: item for item in evidence}
    metrics: list[DerivedMetric] = []
    gaps: list[str] = []

    def pick(*ids: str) -> tuple[EvidenceLike | None, float | None]:
        for evidence_id in ids:
            item = items.get(evidence_id)
            value = _number(item.value) if item else None
            if value is not None:
                return item, value
        return None, None

    def add_ratio(
        *,
        metric_id: str,
        dimension: str,
        label: str,
        numerator: tuple[EvidenceLike, float],
        denominator: tuple[EvidenceLike, float],
        scale: float,
        unit: str,
        method: str,
        interpretation: str,
        require_matching_period: bool = False,
    ) -> DerivedMetric | None:
        numerator_item, numerator_value = numerator
        denominator_item, denominator_value = denominator
        if denominator_value == 0:
            return None
        if require_matching_period and (
            not numerator_item.as_of
            or numerator_item.as_of != denominator_item.as_of
        ):
            gaps.append(f"{label}所需证据报告期不一致，已停止计算")
            return None
        metric = DerivedMetric(
            id=metric_id,
            dimension=dimension,
            label=label,
            value=round(numerator_value / denominator_value * scale, 4),
            unit=unit,
            depends_on=(numerator_item.id, denominator_item.id),
            method=method,
            interpretation=interpretation,
            as_of=numerator_item.as_of if numerator_item.as_of == denominator_item.as_of else None,
            confidence="high" if numerator_item.confidence == denominator_item.confidence == "high" else "medium",
        )
        metrics.append(metric)
        return metric

    pe_item, pe = pick("valuation.pe_ttm", "valuation.pe")
    if pe_item and pe and pe > 0:
        metrics.append(DerivedMetric(
            id="derived.earnings_yield",
            dimension="valuation",
            label="盈利收益率",
            value=round(100 / pe, 4),
            unit="%",
            depends_on=(pe_item.id,),
            method="100 / PE",
            interpretation="以当前市盈率折算的盈利收益率，仅用于估值结构比较",
            as_of=pe_item.as_of,
            confidence=pe_item.confidence,
        ))

    pb_item, pb = pick("valuation.pb")
    if pb_item and pb and pb > 0:
        metrics.append(DerivedMetric(
            id="derived.book_yield",
            dimension="valuation",
            label="账面价值收益率",
            value=round(100 / pb, 4),
            unit="%",
            depends_on=(pb_item.id,),
            method="100 / PB",
            interpretation="每单位市值对应的账面价值比例，不代表清算价值",
            as_of=pb_item.as_of,
            confidence=pb_item.confidence,
        ))

    percentile_values: list[tuple[EvidenceLike, float]] = []
    for evidence_id in ("valuation.pe_ttm_percentile", "valuation.pb_percentile"):
        item, value = pick(evidence_id)
        if item and value is not None:
            percentile_values.append((item, value))
    if percentile_values:
        metrics.append(DerivedMetric(
            id="derived.valuation_percentile_midpoint",
            dimension="valuation",
            label="综合估值历史位置",
            value=round(fmean(value for _, value in percentile_values), 2),
            unit="percentile",
            depends_on=tuple(item.id for item, _ in percentile_values),
            method="可用 PE/PB 历史分位的算术平均",
            interpretation="越高表示当前估值越接近自身历史高位，不用于跨行业绝对比较",
            confidence="medium",
        ))

    op_cf_item, op_cf = pick("cash_flow.op_cf_ps")
    earnings_item, earnings = pick("profitability.eps")
    if not (op_cf_item and earnings_item):
        op_cf_item, op_cf = pick("disclosure.edgar_operating_cash_flow")
        earnings_item, earnings = pick("disclosure.edgar_net_income")
    cash_conversion: DerivedMetric | None = None
    if op_cf_item and earnings_item and op_cf is not None and earnings is not None and earnings > 0:
        cash_conversion = add_ratio(
            metric_id="derived.cash_conversion",
            dimension="cash_flow",
            label="盈利现金转化率",
            numerator=(op_cf_item, op_cf),
            denominator=(earnings_item, earnings),
            scale=100,
            unit="%",
            method="经营现金流 / 净利润；A 股使用每股口径",
            interpretation="衡量账面盈利转化为经营现金的程度，单期结果可能受营运资本扰动",
            require_matching_period=True,
        )
    elif op_cf_item and earnings_item and earnings is not None and earnings <= 0:
        gaps.append("净利润非正，盈利现金转化率不具可比意义")

    assets_item, assets = pick("disclosure.edgar_assets")
    liabilities_item, liabilities = pick("disclosure.edgar_liabilities")
    debt_ratio: DerivedMetric | None = None
    equity_multiplier: DerivedMetric | None = None
    if assets_item and liabilities_item and assets and assets > 0 and liabilities is not None:
        debt_ratio = add_ratio(
            metric_id="derived.debt_ratio",
            dimension="balance_sheet",
            label="资产负债率（申报推导）",
            numerator=(liabilities_item, liabilities),
            denominator=(assets_item, assets),
            scale=100,
            unit="%",
            method="总负债 / 总资产",
            interpretation="基于同报告期 SEC 申报值推导的财务杠杆水平",
            require_matching_period=True,
        )
        equity = assets - liabilities
        if (
            equity > 0
            and assets_item.as_of
            and assets_item.as_of == liabilities_item.as_of
        ):
            equity_multiplier = DerivedMetric(
                id="derived.equity_multiplier",
                dimension="profitability",
                label="权益乘数",
                value=round(assets / equity, 4),
                unit="x",
                depends_on=(assets_item.id, liabilities_item.id),
                method="总资产 / (总资产 - 总负债)",
                interpretation="杜邦框架中的财务杠杆因子；越高表示权益承载的资产规模越大",
                as_of=assets_item.as_of,
                confidence="high" if assets_item.confidence == liabilities_item.confidence == "high" else "medium",
            )
            metrics.append(equity_multiplier)

    net_income_item, net_income = pick("disclosure.edgar_net_income")
    if net_income_item and assets_item and net_income is not None and assets and assets > 0:
        add_ratio(
            metric_id="derived.roa_approx",
            dimension="profitability",
            label="期末资产回报近似",
            numerator=(net_income_item, net_income),
            denominator=(assets_item, assets),
            scale=100,
            unit="%",
            method="净利润 / 期末总资产",
            interpretation="未使用平均资产，仅用于快速观察资本效率，不替代标准 ROA",
            require_matching_period=True,
        )

    pe_percentile_item, pe_percentile = pick("valuation.pe_ttm_percentile")
    valuation_signals: list[tuple[float, str]] = []
    if pe_item and pe and pe > 0:
        valuation_signals.append((_interpolate(pe, ((8, 95), (15, 80), (25, 60), (40, 35), (70, 10))), pe_item.id))
    if pe_percentile_item and pe_percentile is not None:
        valuation_signals.append((max(0, min(100, 100 - pe_percentile)), pe_percentile_item.id))

    growth_signals: list[tuple[float, str]] = []
    for evidence_id in ("growth.revenue_yoy", "growth.net_profit_yoy"):
        item, value = pick(evidence_id)
        if item and value is not None:
            growth_signals.append((_interpolate(value, ((-20, 10), (0, 40), (10, 60), (25, 80), (50, 95))), item.id))

    quality_signals: list[tuple[float, str]] = []
    roe_item, roe = pick("profitability.roe")
    if roe_item and roe is not None:
        quality_signals.append((_interpolate(roe, ((0, 10), (5, 35), (10, 55), (15, 70), (25, 90), (35, 100))), roe_item.id))
    margin_item, margin = pick("profitability.net_margin")
    if margin_item and margin is not None:
        quality_signals.append((_interpolate(margin, ((0, 10), (5, 45), (10, 60), (20, 80), (30, 90), (50, 100))), margin_item.id))
    if cash_conversion:
        quality_signals.append((_interpolate(cash_conversion.value, ((0, 5), (50, 40), (80, 65), (100, 85), (150, 100))), cash_conversion.id))

    resilience_signals: list[tuple[float, str]] = []
    debt_item, debt = pick("balance_sheet.debt_ratio")
    if debt_item and debt is not None:
        resilience_signals.append((_interpolate(debt, ((10, 95), (30, 85), (50, 65), (70, 35), (90, 10))), debt_item.id))
    elif debt_ratio:
        resilience_signals.append((_interpolate(debt_ratio.value, ((10, 95), (30, 85), (50, 65), (70, 35), (90, 10))), debt_ratio.id))

    scorecard = (
        _axis("quality", "盈利质量", quality_signals, "ROE、净利率与现金转化率的等权结构评分"),
        _axis("growth", "增长动能", growth_signals, "营收与净利润同比增速的等权结构评分"),
        _axis("valuation", "估值位置", valuation_signals, "PE 绝对区间与历史分位的等权结构评分"),
        _axis("resilience", "财务韧性", resilience_signals, "资产负债率的反向结构评分"),
    )

    if not any(metric.id == "derived.cash_conversion" for metric in metrics):
        gaps.append("盈利现金转化率所需的同口径经营现金流与净利润证据不足")
    if not any(metric.id == "derived.roa_approx" for metric in metrics):
        gaps.append("标准 ROA/ROIC 所需的利润、平均资产、投入资本证据尚不完整")

    return AnalysisResult(
        metrics=tuple(metrics),
        scorecard=scorecard,
        gaps=tuple(dict.fromkeys(gaps)),
    )
