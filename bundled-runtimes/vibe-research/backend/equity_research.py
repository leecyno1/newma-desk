"""Cross-market equity research framework with an auditable evidence ledger.

The framework is intentionally market-neutral.  A/H/US equities share the same
research dimensions; market adapters only decide how facts are collected and
normalised.  SEC EDGAR is an optional US disclosure adapter, never a required
dependency for the common research view.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
import os
import time
from typing import Any, Callable, Protocol

import requests

import astock
import financial_analytics
import gstock


FRAMEWORK_VERSION = "1.2"


@dataclass(frozen=True)
class Evidence:
    id: str
    dimension: str
    label: str
    value: Any
    source: str
    source_type: str
    field: str
    as_of: str | None = None
    unit: str | None = None
    currency: str | None = None
    confidence: str = "medium"
    url: str | None = None
    note: str | None = None
    depends_on: tuple[str, ...] = ()
    method: str | None = None


@dataclass
class ResearchInputs:
    symbol: str
    market: str
    name: str
    currency: str
    evidence: list[Evidence] = field(default_factory=list)
    sources: list[str] = field(default_factory=list)
    gaps: list[str] = field(default_factory=list)
    source_status: list[ResearchSourceStatus] = field(default_factory=list)


@dataclass(frozen=True)
class ResearchSourceStatus:
    id: str
    title: str
    status: str
    source: str
    blocks: tuple[str, ...]
    as_of: str | None = None
    message: str | None = None


class MarketResearchAdapter(Protocol):
    def supports(self, symbol: str) -> bool: ...

    def load(self, symbol: str) -> ResearchInputs: ...


class ResearchEnricher(Protocol):
    def supports(self, inputs: ResearchInputs) -> bool: ...

    def enrich(self, inputs: ResearchInputs) -> None: ...


DIMENSIONS = (
    ("valuation", "估值与预期", ("valuation",)),
    ("growth", "增长质量", ("growth",)),
    ("profitability", "盈利与资本效率", ("profitability",)),
    ("cash_flow", "现金流质量", ("cash_flow",)),
    ("balance_sheet", "资产负债与韧性", ("balance_sheet",)),
    ("disclosure", "披露与可追溯证据", ("disclosure",)),
)


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _clean(value: Any) -> Any:
    if value is None or value is False or value in ("", "false", "-"):
        return None
    return value


def _normalize_value(value: Any, unit: str | None) -> Any:
    value = _clean(value)
    if not isinstance(value, str) or not unit:
        return value
    numeric_unit = unit in {"%", "x", "count", "percentile"} or unit.endswith("/share")
    if not numeric_unit:
        return value
    text = value.strip().replace(",", "")
    for suffix in ("%", "倍", "元", "股"):
        text = text.removesuffix(suffix).strip()
    try:
        return float(text)
    except ValueError:
        return value


def _append(
    target: list[Evidence],
    *,
    evidence_id: str,
    dimension: str,
    label: str,
    value: Any,
    source: str,
    source_type: str,
    field_name: str,
    as_of: str | None = None,
    unit: str | None = None,
    currency: str | None = None,
    confidence: str = "medium",
    url: str | None = None,
    note: str | None = None,
) -> None:
    value = _normalize_value(value, unit)
    if value is None:
        return
    target.append(
        Evidence(
            id=evidence_id,
            dimension=dimension,
            label=label,
            value=value,
            source=source,
            source_type=source_type,
            field=field_name,
            as_of=as_of,
            unit=unit,
            currency=currency,
            confidence=confidence,
            url=url,
            note=note,
        )
    )


class ChinaEquityResearchAdapter:
    def __init__(
        self,
        *,
        valuation_loader: Callable[[str], dict] = astock.full_valuation,
        financial_loader: Callable[[str], dict] = astock.financials,
        percentile_loader: Callable[[str], dict] = astock.valuation_percentile,
    ):
        self._valuation_loader = valuation_loader
        self._financial_loader = financial_loader
        self._percentile_loader = percentile_loader

    def supports(self, symbol: str) -> bool:
        return symbol.isdigit() and len(symbol) == 6

    def load(self, symbol: str) -> ResearchInputs:
        valuation: dict = {}
        financials: dict = {}
        percentile: dict = {}
        gaps: list[str] = []
        source_status: list[ResearchSourceStatus] = []
        try:
            valuation = self._valuation_loader(symbol) or {}
            source_status.append(ResearchSourceStatus(
                id="cn-quote-valuation",
                title="行情与估值",
                status="available" if valuation else "missing",
                source="Tencent quote / THS consensus",
                blocks=("valuation",),
                as_of=_now_iso(),
                message=None if valuation else "数据源返回空结果",
            ))
        except Exception as exc:  # noqa: BLE001 - source failures become explicit gaps
            gaps.append(f"A股行情与估值暂不可用：{exc}")
            source_status.append(ResearchSourceStatus(
                id="cn-quote-valuation",
                title="行情与估值",
                status="fetch_failed",
                source="Tencent quote / THS consensus",
                blocks=("valuation",),
                message=str(exc),
            ))
        try:
            financials = self._financial_loader(symbol) or {}
            source_status.append(ResearchSourceStatus(
                id="cn-financial-summary",
                title="财务摘要",
                status="available" if financials else "missing",
                source="THS financial abstract",
                blocks=("growth", "profitability", "cash_flow", "balance_sheet"),
                as_of=str(financials.get("period") or "") or None,
                message=None if financials else "数据源返回空结果",
            ))
        except Exception as exc:  # noqa: BLE001
            gaps.append(f"A股财务摘要暂不可用：{exc}")
            source_status.append(ResearchSourceStatus(
                id="cn-financial-summary",
                title="财务摘要",
                status="fetch_failed",
                source="THS financial abstract",
                blocks=("growth", "profitability", "cash_flow", "balance_sheet"),
                message=str(exc),
            ))
        try:
            percentile = self._percentile_loader(symbol) or {}
            source_status.append(ResearchSourceStatus(
                id="cn-valuation-history",
                title="历史估值分位",
                status="available" if percentile.get("metrics") else "missing",
                source="Baidu valuation history",
                blocks=("valuation",),
                as_of=str(percentile.get("period") or "") or None,
                message=None if percentile.get("metrics") else "历史分位数据为空",
            ))
        except Exception as exc:  # noqa: BLE001
            gaps.append(f"A股历史估值分位暂不可用：{exc}")
            source_status.append(ResearchSourceStatus(
                id="cn-valuation-history",
                title="历史估值分位",
                status="fetch_failed",
                source="Baidu valuation history",
                blocks=("valuation",),
                message=str(exc),
            ))

        name = str(valuation.get("name") or symbol)
        inputs = ResearchInputs(
            symbol=symbol,
            market="CN",
            name=name,
            currency="CNY",
            sources=["Tencent quote", "THS financial abstract", "Baidu valuation history"],
            gaps=gaps,
            source_status=source_status,
        )
        quote_as_of = _now_iso()
        for key, label, unit in (
            ("price", "现价", "CNY/share"),
            ("mcap_yi", "总市值", "CNY 100m"),
            ("pe_ttm", "PE(TTM)", "x"),
            ("pb", "PB", "x"),
            ("pe_26e", "前向 PE", "x"),
            ("peg", "PEG", "x"),
            ("analyst_count", "一致预期覆盖机构", "count"),
        ):
            _append(
                inputs.evidence,
                evidence_id=f"valuation.{key}",
                dimension="valuation",
                label=label,
                value=valuation.get(key),
                source="Tencent quote / THS consensus",
                source_type="structured",
                field_name=key,
                as_of=quote_as_of,
                unit=unit,
                currency="CNY" if key in {"price", "mcap_yi"} else None,
                confidence="high" if key in {"price", "mcap_yi", "pe_ttm", "pb"} else "medium",
            )

        metrics = percentile.get("metrics") or {}
        for key, label in (("pe_ttm", "PE 历史分位"), ("pb", "PB 历史分位")):
            item = metrics.get(key) or {}
            _append(
                inputs.evidence,
                evidence_id=f"valuation.{key}_percentile",
                dimension="valuation",
                label=label,
                value=item.get("percentile"),
                source="Baidu valuation history",
                source_type="structured",
                field_name="percentile",
                as_of=quote_as_of,
                unit="percentile",
                note=str(percentile.get("period") or "historical window"),
            )

        period = str(financials.get("period") or "") or None
        financial_mapping = (
            ("revenue", "营业收入", "growth", "CNY"),
            ("revenue_yoy", "营业收入同比", "growth", "%"),
            ("net_profit", "净利润", "growth", "CNY"),
            ("net_profit_yoy", "净利润同比", "growth", "%"),
            ("roe", "ROE", "profitability", "%"),
            ("gross_margin", "毛利率", "profitability", "%"),
            ("net_margin", "净利率", "profitability", "%"),
            ("eps", "基本每股收益", "profitability", "CNY/share"),
            ("bvps", "每股净资产", "balance_sheet", "CNY/share"),
            ("op_cf_ps", "每股经营现金流", "cash_flow", "CNY/share"),
        )
        for key, label, dimension, unit in financial_mapping:
            _append(
                inputs.evidence,
                evidence_id=f"{dimension}.{key}",
                dimension=dimension,
                label=label,
                value=financials.get(key),
                source="THS financial abstract",
                source_type="structured",
                field_name=key,
                as_of=period,
                unit=unit,
                currency="CNY" if unit.startswith("CNY") else None,
                confidence="high",
            )
        if not any(item.dimension == "balance_sheet" for item in inputs.evidence):
            inputs.gaps.append("当前 A 股摘要未提供统一资产负债率口径")
        return inputs


class GlobalEquityResearchAdapter:
    def __init__(self, *, stock_loader: Callable[[str], dict] = gstock.us_hk_stock):
        self._stock_loader = stock_loader

    def supports(self, symbol: str) -> bool:
        return not (symbol.isdigit() and len(symbol) == 6)

    def load(self, symbol: str) -> ResearchInputs:
        payload = self._stock_loader(symbol) or {}
        if not payload:
            raise LookupError(f"未找到证券 {symbol}")
        raw_market = str(payload.get("market") or "US").upper()
        market = "US" if raw_market in {"NASDAQ", "NYSE", "AMEX", "US"} else raw_market
        quote = payload.get("quote") or {}
        metrics = payload.get("metrics") or {}
        currency = "HKD" if market == "HK" else "KRW" if market == "KR" else "USD"
        sources = list(dict.fromkeys(payload.get("data_sources") or quote.get("sources") or []))
        expected_primary = "tencent" if market == "HK" else "eastmoney" if market == "KR" else "sina"
        actual_primary = str(quote.get("source") or (sources[0] if sources else ""))
        quote_status = (
            "missing"
            if not quote
            else "fallback"
            if actual_primary and actual_primary != expected_primary
            else "available"
        )
        quote_message = (
            f"主源 {expected_primary} 不可用，已降级到 {actual_primary}"
            if quote_status == "fallback"
            else " → ".join(sources)
            if sources
            else "统一海外数据路由未返回来源明细"
        )
        inputs = ResearchInputs(
            symbol=str(payload.get("code") or symbol).upper(),
            market=market,
            name=str(payload.get("name") or quote.get("name") or symbol),
            currency=currency,
            sources=sources or ["global-stock-data"],
            source_status=[
                ResearchSourceStatus(
                    id="global-quote-route",
                    title="海外行情路由",
                    status=quote_status,
                    source="global-stock-data",
                    blocks=("valuation",),
                    as_of=str(quote.get("as_of") or "") or None,
                    message=quote_message,
                ),
                ResearchSourceStatus(
                    id="global-financial-summary",
                    title="海外财务摘要",
                    status="available" if metrics else "missing",
                    source="Eastmoney GMAININDICATOR",
                    blocks=("growth", "profitability", "balance_sheet"),
                    as_of=str(metrics.get("report_date") or "") or None,
                    message=None if metrics else "关键财务指标暂不可用",
                ),
            ],
        )
        quote_source = str(quote.get("source") or (sources[0] if sources else "global-stock-data"))
        quote_as_of = str(quote.get("as_of") or "") or _now_iso()
        for key, label, unit in (
            ("price", "现价", f"{currency}/share"),
            ("mcap", "总市值", currency),
            ("pe", "PE", "x"),
            ("pb", "PB", "x"),
        ):
            _append(
                inputs.evidence,
                evidence_id=f"valuation.{key}",
                dimension="valuation",
                label=label,
                value=quote.get(key),
                source=quote_source,
                source_type="structured",
                field_name=key,
                as_of=quote_as_of,
                unit=unit,
                currency=currency if key in {"price", "mcap"} else None,
                confidence="high",
            )

        period = str(metrics.get("report_date") or "") or None
        mapping = (
            ("revenue", "营业收入", "growth", currency),
            ("revenue_yoy", "营业收入同比", "growth", "%"),
            ("net_profit", "净利润", "growth", currency),
            ("roe", "ROE", "profitability", "%"),
            ("gross_margin", "毛利率", "profitability", "%"),
            ("net_margin", "净利率", "profitability", "%"),
            ("eps", "基本每股收益", "profitability", f"{currency}/share"),
            ("debt_ratio", "资产负债率", "balance_sheet", "%"),
        )
        for key, label, dimension, unit in mapping:
            _append(
                inputs.evidence,
                evidence_id=f"{dimension}.{key}",
                dimension=dimension,
                label=label,
                value=metrics.get(key),
                source="Eastmoney GMAININDICATOR",
                source_type="structured",
                field_name=key,
                as_of=period,
                unit=unit,
                currency=currency if unit == currency else None,
                confidence="medium",
            )
        if market == "KR":
            inputs.gaps.append("韩股当前仅提供行情，不在本轮 A/H/US 财务研究覆盖范围")
        if not metrics:
            inputs.gaps.append("关键财务指标暂不可用")
        inputs.gaps.extend(["历史估值分位尚未接入", "统一经营现金流证据尚未接入"])
        return inputs


_SEC_TICKER_CACHE: tuple[float, dict[str, int]] | None = None


class EdgarEvidenceAdapter:
    """Optional SEC Company Facts adapter for US disclosure evidence."""

    def __init__(
        self,
        user_agent: str = "",
        *,
        timeout_seconds: float = 4.0,
        session: requests.Session | None = None,
    ):
        self._user_agent = user_agent.strip()
        self._timeout_seconds = timeout_seconds
        self._session = session or requests.Session()

    @property
    def enabled(self) -> bool:
        return bool(self._user_agent)

    def supports(self, inputs: ResearchInputs) -> bool:
        return self.enabled and inputs.market == "US"

    def _headers(self) -> dict[str, str]:
        return {"User-Agent": self._user_agent, "Accept-Encoding": "gzip, deflate"}

    def _ticker_map(self) -> dict[str, int]:
        global _SEC_TICKER_CACHE
        now = time.time()
        if _SEC_TICKER_CACHE and now - _SEC_TICKER_CACHE[0] < 86400:
            return _SEC_TICKER_CACHE[1]
        response = self._session.get(
            "https://www.sec.gov/files/company_tickers.json",
            headers=self._headers(),
            timeout=self._timeout_seconds,
        )
        response.raise_for_status()
        payload = response.json()
        mapping = {
            str(row.get("ticker") or "").upper(): int(row["cik_str"])
            for row in payload.values()
            if isinstance(row, dict) and row.get("ticker") and row.get("cik_str") is not None
        }
        _SEC_TICKER_CACHE = (now, mapping)
        return mapping

    @staticmethod
    def _latest_fact(facts: dict, concepts: tuple[str, ...]) -> tuple[Any, str | None, str | None]:
        us_gaap = facts.get("us-gaap") or {}
        candidates: list[dict] = []
        for concept in concepts:
            entry = us_gaap.get(concept) or {}
            for rows in (entry.get("units") or {}).values():
                if isinstance(rows, list):
                    candidates.extend(row for row in rows if isinstance(row, dict) and row.get("val") is not None)
        if not candidates:
            return None, None, None
        candidates.sort(key=lambda row: (str(row.get("filed") or ""), str(row.get("end") or "")))
        latest = candidates[-1]
        return latest.get("val"), str(latest.get("end") or "") or None, str(latest.get("form") or "") or None

    def enrich(self, inputs: ResearchInputs) -> None:
        evidence_before = len(inputs.evidence)
        try:
            cik = self._ticker_map().get(inputs.symbol.upper())
            if cik is None:
                inputs.gaps.append("SEC EDGAR 未找到对应 CIK")
                inputs.source_status.append(ResearchSourceStatus(
                    id="sec-edgar-company-facts",
                    title="SEC 原始披露",
                    status="missing",
                    source="SEC EDGAR Company Facts",
                    blocks=("disclosure", "growth", "cash_flow", "balance_sheet"),
                    message="未找到对应 CIK",
                ))
                return
            response = self._session.get(
                f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json",
                headers=self._headers(),
                timeout=self._timeout_seconds,
            )
            response.raise_for_status()
            payload = response.json()
            facts = payload.get("facts") or {}
            source_url = f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json"
            mapping = (
                ("revenue", "SEC 营业收入", "growth", ("RevenueFromContractWithCustomerExcludingAssessedTax", "Revenues")),
                ("net_income", "SEC 净利润", "growth", ("NetIncomeLoss",)),
                ("operating_cash_flow", "SEC 经营现金流", "cash_flow", ("NetCashProvidedByUsedInOperatingActivities",)),
                ("assets", "SEC 总资产", "balance_sheet", ("Assets",)),
                ("liabilities", "SEC 总负债", "balance_sheet", ("Liabilities",)),
            )
            for key, label, dimension, concepts in mapping:
                value, as_of, form = self._latest_fact(facts, concepts)
                _append(
                    inputs.evidence,
                    evidence_id=f"disclosure.edgar_{key}",
                    dimension=dimension,
                    label=label,
                    value=value,
                    source="SEC EDGAR Company Facts",
                    source_type="filing",
                    field_name=" / ".join(concepts),
                    as_of=as_of,
                    unit="USD",
                    currency="USD",
                    confidence="high",
                    url=source_url,
                    note=form,
                )
            inputs.sources.append("SEC EDGAR Company Facts")
            inputs.source_status.append(ResearchSourceStatus(
                id="sec-edgar-company-facts",
                title="SEC 原始披露",
                status=(
                    "available"
                    if len(inputs.evidence) > evidence_before
                    else "missing"
                ),
                source="SEC EDGAR Company Facts",
                blocks=("disclosure", "growth", "cash_flow", "balance_sheet"),
                message=(
                    None
                    if len(inputs.evidence) > evidence_before
                    else "Company Facts 未返回可用字段"
                ),
            ))
        except Exception as exc:  # noqa: BLE001
            inputs.gaps.append(f"SEC EDGAR 可选证据暂不可用：{exc}")
            inputs.source_status.append(ResearchSourceStatus(
                id="sec-edgar-company-facts",
                title="SEC 原始披露",
                status="fetch_failed",
                source="SEC EDGAR Company Facts",
                blocks=("disclosure", "growth", "cash_flow", "balance_sheet"),
                message=str(exc),
            ))


def _research_block_quality(
    inputs: ResearchInputs,
    sections: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    blocks: list[dict[str, Any]] = []
    block_scores: dict[str, int] = {}
    failed_sources = [
        item for item in inputs.source_status if item.status == "fetch_failed"
    ]
    fallback_sources = [
        item for item in inputs.source_status if item.status == "fallback"
    ]

    for section in sections:
        block_id = str(section["id"])
        evidence = [
            item
            for item in inputs.evidence
            if (
                item.source_type == "filing"
                if block_id == "disclosure"
                else item.dimension == block_id
            )
        ]
        source_evidence = [item for item in evidence if item.source_type != "derived"]
        attempts = [
            item for item in inputs.source_status if block_id in item.blocks
        ]
        failed_attempts = [item for item in attempts if item.status == "fetch_failed"]
        missing_attempts = [item for item in attempts if item.status == "missing"]
        unsupported_attempts = [
            item for item in attempts if item.status == "not_supported"
        ]
        fallback_attempts = [item for item in attempts if item.status == "fallback"]

        if not evidence:
            if failed_attempts:
                status = "fetch_failed"
            elif attempts and len(unsupported_attempts) == len(attempts):
                status = "not_supported"
            else:
                status = "missing"
            score = 0
        elif not source_evidence:
            status = "estimated"
            score = min(45, 25 + len(evidence) * 5)
        else:
            status = (
                "fallback"
                if fallback_attempts
                else "partial"
                if failed_attempts or missing_attempts
                else "available"
            )
            high_confidence = sum(
                1 for item in source_evidence if item.confidence == "high"
            )
            dated = sum(1 for item in source_evidence if item.as_of)
            source_types = len({item.source_type for item in source_evidence})
            score = min(
                100,
                45
                + min(len(source_evidence), 5) * 6
                + round(15 * high_confidence / len(source_evidence))
                + round(10 * dated / len(source_evidence))
                + min(6, max(0, source_types - 1) * 3),
            )
            if status == "partial":
                score = max(20, score - 15)
            elif status == "fallback":
                score = max(25, score - 8)

        sources = list(dict.fromkeys(item.source for item in source_evidence))
        as_of_values = [item.as_of for item in evidence if item.as_of]
        warnings = list(dict.fromkeys(
            item.message
            for item in failed_attempts + fallback_attempts
            if item.message
        ))
        gaps = [
            gap
            for gap in inputs.gaps
            if (
                block_id.replace("_", "") in gap.lower().replace("_", "")
                or any(token in gap for token in {
                    "valuation": ("估值",),
                    "growth": ("收入", "净利润", "增长", "财务"),
                    "profitability": ("盈利", "ROE", "毛利率", "财务"),
                    "cash_flow": ("现金流",),
                    "balance_sheet": ("资产负债", "负债率"),
                    "disclosure": ("披露", "SEC", "CIK"),
                }.get(block_id, ()))
            )
        ]
        block_scores[block_id] = score
        blocks.append({
            "id": block_id,
            "title": section["title"],
            "status": status,
            "qualityScore": score,
            "evidenceCount": len(evidence),
            "sources": sources,
            "asOf": max(as_of_values) if as_of_values else None,
            "warnings": warnings,
            "gaps": list(dict.fromkeys(gaps)),
        })

    overall_score = round(
        sum(block_scores.values()) / max(1, len(block_scores))
    )
    level = (
        "good"
        if overall_score >= 80
        else "usable"
        if overall_score >= 60
        else "limited"
        if overall_score >= 35
        else "poor"
    )
    warnings = list(dict.fromkeys(
        item.message or f"{item.title}请求失败"
        for item in failed_sources + fallback_sources
    ))
    quality = {
        "score": overall_score,
        "level": level,
        "blockScores": block_scores,
        "limitations": list(dict.fromkeys(inputs.gaps))[:20],
        "warnings": warnings[:20],
    }
    return blocks, quality


def _research_workflow(
    inputs: ResearchInputs,
    sections: list[dict[str, Any]],
    *,
    generated_at: str,
    timings: dict[str, int],
) -> dict[str, Any]:
    blocks, quality = _research_block_quality(inputs, sections)
    failed_sources = [
        item for item in inputs.source_status if item.status == "fetch_failed"
    ]
    fallback_sources = [
        item for item in inputs.source_status if item.status == "fallback"
    ]
    missing_blocks = [
        item["id"]
        for item in blocks
        if item["status"] in {"missing", "not_supported", "fetch_failed"}
    ]
    partial = bool(failed_sources or missing_blocks or quality["level"] in {"limited", "poor"})
    task_status = "partial" if partial else "completed"
    collection_status = "partial" if failed_sources or missing_blocks else "completed"
    return {
        "schemaVersion": "newma-desk.research-workflow.v1",
        "task": {
            "id": f"equity-research:{inputs.market}:{inputs.symbol}:{generated_at}",
            "status": task_status,
            "stage": "quality-review",
            "progress": 1,
            "updatedAt": generated_at,
        },
        "stages": [
            {
                "id": "collect",
                "title": "采集市场与财务证据",
                "status": collection_status,
                "progress": 1,
                "durationMs": timings.get("collect", 0),
            },
            {
                "id": "enrich",
                "title": "补充披露与跨源证据",
                "status": "partial" if failed_sources else "completed",
                "progress": 1,
                "durationMs": timings.get("enrich", 0),
            },
            {
                "id": "analyze",
                "title": "计算标准化财务指标",
                "status": "completed",
                "progress": 1,
                "durationMs": timings.get("analyze", 0),
            },
            {
                "id": "quality-review",
                "title": "检查质量与数据缺口",
                "status": task_status,
                "progress": 1,
                "durationMs": timings.get("quality", 0),
            },
        ],
        "blocks": blocks,
        "dataQuality": quality,
        "sourceStatus": [
            {
                "id": item.id,
                "title": item.title,
                "status": item.status,
                "source": item.source,
                "blocks": list(item.blocks),
                "asOf": item.as_of,
                "message": item.message,
            }
            for item in inputs.source_status
        ],
        "diagnostics": {
            "missingBlocks": missing_blocks,
            "failedSources": [item.id for item in failed_sources],
            "fallbackSources": [item.id for item in fallback_sources],
            "gapCount": len(set(inputs.gaps)),
        },
        "history": {
            "mode": "desk-managed",
            "namespace": "research-history",
            "state": "pending",
            "lastGoodAt": None,
        },
    }


class EquityResearchService:
    def __init__(
        self,
        adapters: list[MarketResearchAdapter],
        *,
        enrichers: list[ResearchEnricher] | None = None,
    ):
        self._adapters = adapters
        self._enrichers = enrichers or []

    def snapshot(self, symbol: str) -> dict:
        normalized = symbol.strip().upper()
        if not normalized:
            raise ValueError("证券代码不能为空")
        adapter = next((item for item in self._adapters if item.supports(normalized)), None)
        if adapter is None:
            raise LookupError(f"没有适用于 {normalized} 的研究 Adapter")
        started = time.perf_counter()
        inputs = adapter.load(normalized)
        collected = time.perf_counter()
        for enricher in self._enrichers:
            if enricher.supports(inputs):
                enricher.enrich(inputs)
            elif (
                isinstance(enricher, EdgarEvidenceAdapter)
                and inputs.market == "US"
                and not enricher.enabled
            ):
                inputs.source_status.append(ResearchSourceStatus(
                    id="sec-edgar-company-facts",
                    title="SEC 原始披露",
                    status="not_supported",
                    source="SEC EDGAR Company Facts",
                    blocks=("disclosure",),
                    message="未配置 VR_SEC_USER_AGENT，可选披露证据未启用",
                ))
        enriched = time.perf_counter()

        analysis = financial_analytics.analyze_financials(inputs.evidence)
        for metric in analysis.metrics:
            inputs.evidence.append(Evidence(
                id=metric.id,
                dimension=metric.dimension,
                label=metric.label,
                value=metric.value,
                source="Newma Financial Analytics",
                source_type="derived",
                field=" / ".join(metric.depends_on),
                as_of=metric.as_of,
                unit=metric.unit,
                confidence=metric.confidence,
                note=metric.interpretation,
                depends_on=metric.depends_on,
                method=metric.method,
            ))
        inputs.gaps.extend(analysis.gaps)
        analyzed = time.perf_counter()

        evidence_by_id = {item.id: item for item in inputs.evidence}

        def comparison_value(*evidence_ids: str) -> Any:
            for evidence_id in evidence_ids:
                item = evidence_by_id.get(evidence_id)
                if item is not None:
                    return item.value
            return None

        comparison_profile = {
            "metrics": {
                "pe": comparison_value("valuation.pe_ttm", "valuation.pe"),
                "pb": comparison_value("valuation.pb"),
                "valuationPercentile": comparison_value("derived.valuation_percentile_midpoint"),
                "revenueGrowthPct": comparison_value("growth.revenue_yoy"),
                "netProfitGrowthPct": comparison_value("growth.net_profit_yoy"),
                "roePct": comparison_value("profitability.roe"),
                "grossMarginPct": comparison_value("profitability.gross_margin"),
                "netMarginPct": comparison_value("profitability.net_margin"),
                "cashConversionPct": comparison_value("derived.cash_conversion"),
                "debtRatioPct": comparison_value("balance_sheet.debt_ratio", "derived.debt_ratio"),
            },
            "scores": {axis.id: axis.score for axis in analysis.scorecard},
        }

        ledger = [
            {
                "id": item.id,
                "dimension": item.dimension,
                "label": item.label,
                "value": item.value,
                "source": item.source,
                "sourceType": item.source_type,
                "field": item.field,
                "asOf": item.as_of,
                "unit": item.unit,
                "currency": item.currency,
                "confidence": item.confidence,
                "url": item.url,
                "note": item.note,
                "dependsOn": list(item.depends_on),
                "method": item.method,
            }
            for item in inputs.evidence
        ]
        sections = []
        for dimension_id, title, aliases in DIMENSIONS:
            evidence_ids = [
                item.id
                for item in inputs.evidence
                if (
                    item.source_type == "filing"
                    if dimension_id == "disclosure"
                    else item.dimension in aliases
                )
            ]
            sections.append(
                {
                    "id": dimension_id,
                    "title": title,
                    "status": "covered" if evidence_ids else "gap",
                    "evidenceIds": evidence_ids,
                }
            )
        covered = sum(1 for section in sections if section["status"] == "covered")
        generated_at = _now_iso()
        quality_started = time.perf_counter()
        workflow = _research_workflow(
            inputs,
            sections,
            generated_at=generated_at,
            timings={
                "collect": round((collected - started) * 1000),
                "enrich": round((enriched - collected) * 1000),
                "analyze": round((analyzed - enriched) * 1000),
            },
        )
        workflow["stages"][-1]["durationMs"] = round(
            (time.perf_counter() - quality_started) * 1000
        )
        return {
            "schemaVersion": "newma-dock.equity-research.v1",
            "frameworkVersion": FRAMEWORK_VERSION,
            "methodology": [
                "cross-market-normalization",
                "evidence-ledger",
                "source-provenance",
                "explicit-data-gaps",
                "research-workflow",
                "data-quality-diagnostics",
            ],
            "identity": {
                "symbol": inputs.symbol,
                "name": inputs.name,
                "market": inputs.market,
                "currency": inputs.currency,
            },
            "coverage": {
                "coveredDimensions": covered,
                "totalDimensions": len(sections),
                "ratio": round(covered / len(sections), 4),
            },
            "sections": sections,
            "analytics": {
                "version": "1.0",
                "metrics": [
                    {
                        "id": metric.id,
                        "dimension": metric.dimension,
                        "label": metric.label,
                        "value": metric.value,
                        "unit": metric.unit,
                        "dependsOn": list(metric.depends_on),
                        "method": metric.method,
                        "interpretation": metric.interpretation,
                        "asOf": metric.as_of,
                        "confidence": metric.confidence,
                    }
                    for metric in analysis.metrics
                ],
                "limitations": [
                    "所有派生指标仅使用当前 Evidence Ledger，不额外请求数据",
                    "结构评分用于统一研究口径，不构成评级、目标价或买卖建议",
                    "单期现金流与资产回报可能受报告期和营运资本变化影响",
                ],
            },
            "scorecard": [
                {
                    "id": axis.id,
                    "title": axis.title,
                    "score": axis.score,
                    "status": axis.status,
                    "summary": axis.summary,
                    "evidenceIds": list(axis.evidence_ids),
                    "signalCount": axis.signal_count,
                    "method": axis.method,
                }
                for axis in analysis.scorecard
            ],
            "comparisonProfile": comparison_profile,
            "derivedEvidence": [metric.id for metric in analysis.metrics],
            "workflow": workflow,
            "reportHistory": [],
            "evidenceLedger": ledger,
            "sources": list(dict.fromkeys(inputs.sources)),
            "gaps": list(dict.fromkeys(inputs.gaps)),
            "generatedAt": generated_at,
        }

    def comparison(self, symbols: list[str]) -> dict:
        normalized = list(dict.fromkeys(item.strip().upper() for item in symbols if item.strip()))
        if len(normalized) < 2:
            raise ValueError("横向比较至少需要 2 个证券代码")
        if len(normalized) > 8:
            raise ValueError("单次横向比较最多支持 8 个证券代码")

        rows: list[dict] = []
        errors: list[dict] = []
        for symbol in normalized:
            try:
                snapshot = self.snapshot(symbol)
                rows.append({
                    "identity": snapshot["identity"],
                    "coverage": snapshot["coverage"],
                    **snapshot["comparisonProfile"],
                })
            except Exception as exc:  # noqa: BLE001 - one failed symbol must not abort peers
                errors.append({"symbol": symbol, "message": str(exc)})
        return {
            "schemaVersion": "newma-dock.equity-comparison.v1",
            "rows": rows,
            "errors": errors,
            "generatedAt": _now_iso(),
        }


def build_default_service() -> EquityResearchService:
    edgar = EdgarEvidenceAdapter(os.environ.get("VR_SEC_USER_AGENT", ""))
    return EquityResearchService(
        [ChinaEquityResearchAdapter(), GlobalEquityResearchAdapter()],
        enrichers=[edgar],
    )


default_service = build_default_service()
