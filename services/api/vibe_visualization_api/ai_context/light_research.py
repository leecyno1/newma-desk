import asyncio
import json
import math
import re
from datetime import UTC, datetime
from typing import Any

from vibe_visualization_api.agent_gateway.models import AgentTaskCreate
from vibe_visualization_api.data_services.client import DataServiceClient
from vibe_visualization_api.data_services.registry import DataServiceRegistry


MAX_RESEARCH_CONTEXT_CHARACTERS = 30_000
MAX_EVIDENCE_ITEMS = 20
MAX_EVENT_ITEMS = 8

_TECHNICAL_TERMS = (
    "k线",
    "走势",
    "趋势",
    "支撑",
    "压力",
    "均线",
    "量价",
    "技术面",
    "波动",
    "回撤",
)
_FUNDAMENTAL_TERMS = (
    "财务",
    "估值",
    "宏观面",
    "业绩",
    "盈利",
    "现金流",
    "负债",
    "成长",
    "长期逻辑",
)
_ANNOUNCEMENT_TERMS = ("公告", "财报", "年报", "季报", "业绩预告")
_REPORT_TERMS = ("研报", "评级", "机构观点")
_NEWS_TERMS = (
    "新闻",
    "消息",
    "异动",
    "催化",
    "原因",
    "事件",
    "利好",
    "利空",
)
_COMPARISON_TERMS = ("同行", "同业", "横向", "对比", "比较")
_SYMBOL_TOKEN_EXCLUSIONS = {
    "AI", "CN", "HK", "US", "PE", "PB", "ROE", "ROA", "ROIC", "EPS",
    "ETF", "KLINE", "K线",
}


def _mapping(value: object) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _text(value: object, limit: int = 240) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        result = value.strip()
    elif isinstance(value, (int, float, bool)):
        result = str(value)
    else:
        result = json.dumps(value, ensure_ascii=False, default=str)
    if not result:
        return None
    return result[:limit]


def _first_text(value: dict[str, Any], keys: tuple[str, ...], limit: int = 240):
    for key in keys:
        candidate = _text(value.get(key), limit)
        if candidate:
            return candidate
    return None


def _normalize_subject(context: dict[str, Any]) -> dict[str, str] | None:
    vibedesk = _mapping(context.get("vibedesk"))
    page = _mapping(vibedesk.get("page"))
    selection = _mapping(page.get("selection"))
    symbol = _text(selection.get("symbol") or selection.get("code"), 24)
    market = (_text(selection.get("market"), 8) or "").upper()
    if not symbol or market not in {"CN", "HK", "US"}:
        return None
    symbol = symbol.upper()
    if symbol.startswith(f"{market}:"):
        symbol = symbol.split(":", 1)[1]
    if market == "CN" and symbol.endswith((".SH", ".SZ", ".BJ")):
        symbol = symbol.rsplit(".", 1)[0]
    return {
        "symbol": symbol,
        "market": market,
        "name": _text(selection.get("name"), 120) or symbol,
    }


def _adjustment(context: dict[str, Any], market: str) -> str:
    if market != "CN":
        return "none"
    page = _mapping(_mapping(context.get("vibedesk")).get("page"))
    filters = _mapping(page.get("filters"))
    value = _text(filters.get("adjustment") or filters.get("adjust"), 8)
    return value if value in {"none", "qfq", "hfq"} else "qfq"


def _planned_capabilities(
    prompt: str,
    subject: dict[str, str],
    adjustment: str,
) -> list[tuple[str, dict[str, Any]]]:
    normalized = prompt.casefold()
    market = subject["market"]
    symbol = subject["symbol"]
    plan: list[tuple[str, dict[str, Any]]] = [
        (
            "market.ohlcv",
            {
                "symbol": symbol,
                "market": market,
                "timeframe": "1w",
                "limit": 156,
                "adjust": adjustment,
            },
        )
    ]
    if any(term in normalized for term in _COMPARISON_TERMS):
        candidates = re.findall(
            r"(?<![A-Z0-9])(?:\d{5,6}|[A-Z][A-Z0-9.-]{1,9})(?![A-Z0-9])",
            prompt.upper(),
        )
        peers = [
            item
            for item in dict.fromkeys(candidates)
            if item not in _SYMBOL_TOKEN_EXCLUSIONS and item != symbol
        ]
        if peers:
            plan.append((
                "research.equity-comparison",
                {"symbols": ",".join([symbol, *peers][:8])},
            ))
            return plan[:2]
    if market == "CN" and any(term in normalized for term in _ANNOUNCEMENT_TERMS):
        plan.append(("market.announcements", {"code": symbol}))
    elif market == "CN" and any(term in normalized for term in _REPORT_TERMS):
        plan.append(("market.reports", {"code": symbol, "pages": 1}))
    elif market == "CN" and any(term in normalized for term in _NEWS_TERMS):
        plan.append(("market.news", {"code": symbol, "limit": 12}))
    elif any(term in normalized for term in _FUNDAMENTAL_TERMS) or not any(
        term in normalized for term in _TECHNICAL_TERMS
    ):
        plan.append(("research.equity-snapshot", {"symbol": symbol}))
    return plan[:2]


def _number(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)) and math.isfinite(float(value)):
        return float(value)
    return None


def _round(value: float | None) -> float | None:
    return round(value, 4) if value is not None and math.isfinite(value) else None


def _period_return(closes: list[float], periods: int) -> float | None:
    if len(closes) <= periods or closes[-periods - 1] == 0:
        return None
    return _round((closes[-1] / closes[-periods - 1] - 1) * 100)


def _max_drawdown(closes: list[float]) -> float | None:
    peak: float | None = None
    drawdown = 0.0
    for close in closes:
        peak = close if peak is None else max(peak, close)
        if peak:
            drawdown = min(drawdown, (close / peak - 1) * 100)
    return _round(drawdown)


def _iso_timestamp(value: object) -> str | None:
    timestamp = _number(value)
    if timestamp is None:
        return None
    try:
        return datetime.fromtimestamp(timestamp / 1000, UTC).isoformat()
    except (OSError, OverflowError, ValueError):
        return None


def _project_ohlcv(payload: object) -> dict[str, Any]:
    data = _mapping(_mapping(payload).get("data"))
    raw_items = data.get("items")
    items = (
        [item for item in raw_items if isinstance(item, dict)]
        if isinstance(raw_items, list)
        else []
    )
    closes = [close for item in items if (close := _number(item.get("close"))) is not None]
    highs = [high for item in items if (high := _number(item.get("high"))) is not None]
    lows = [low for item in items if (low := _number(item.get("low"))) is not None]
    recent_bars = []
    for item in items[-26:]:
        recent_bars.append(
            {
                "time": _iso_timestamp(item.get("timestamp")),
                "open": _round(_number(item.get("open"))),
                "high": _round(_number(item.get("high"))),
                "low": _round(_number(item.get("low"))),
                "close": _round(_number(item.get("close"))),
                "volume": _round(_number(item.get("volume"))),
            }
        )
    return {
        "source": _text(data.get("source"), 80),
        "asOf": _text(data.get("asOf"), 80),
        "timeframe": _text(data.get("timeframe"), 12),
        "adjust": _text(data.get("adjust"), 12),
        "barCount": len(items),
        "periodStart": _iso_timestamp(items[0].get("timestamp")) if items else None,
        "periodEnd": _iso_timestamp(items[-1].get("timestamp")) if items else None,
        "firstClose": _round(closes[0]) if closes else None,
        "lastClose": _round(closes[-1]) if closes else None,
        "periodReturnPct": (
            _round((closes[-1] / closes[0] - 1) * 100)
            if len(closes) > 1 and closes[0]
            else None
        ),
        "returnsPct": {
            "13w": _period_return(closes, 13),
            "26w": _period_return(closes, 26),
            "52w": _period_return(closes, 52),
            "104w": _period_return(closes, 104),
        },
        "periodHigh": _round(max(highs)) if highs else None,
        "periodLow": _round(min(lows)) if lows else None,
        "maxDrawdownPct": _max_drawdown(closes),
        "recentBars": recent_bars,
    }


def _project_snapshot(payload: object) -> dict[str, Any]:
    data = _mapping(_mapping(payload).get("data"))
    raw_identity = _mapping(data.get("identity"))
    raw_coverage = _mapping(data.get("coverage"))
    evidence = []
    raw_evidence = data.get("evidenceLedger")
    if isinstance(raw_evidence, list):
        for raw in raw_evidence[:MAX_EVIDENCE_ITEMS]:
            item = _mapping(raw)
            evidence.append(
                {
                    key: value
                    for key, value in {
                        "id": _text(item.get("id"), 120),
                        "dimension": _text(item.get("dimension"), 80),
                        "label": _text(item.get("label"), 120),
                        "value": _text(item.get("value"), 300),
                        "source": _text(item.get("source"), 160),
                        "asOf": _text(item.get("asOf"), 80),
                        "unit": _text(item.get("unit"), 80),
                        "currency": _text(item.get("currency"), 16),
                        "confidence": _text(item.get("confidence"), 24),
                    }.items()
                    if value is not None
                }
            )
    covered: list[str] = []
    missing: list[str] = []
    raw_sections = data.get("sections")
    if isinstance(raw_sections, list):
        for raw in raw_sections:
            section = _mapping(raw)
            title = _text(section.get("title") or section.get("id"), 100)
            if not title:
                continue
            (covered if section.get("status") == "covered" else missing).append(title)
    raw_analytics = _mapping(data.get("analytics"))
    analytics_metrics = []
    if isinstance(raw_analytics.get("metrics"), list):
        for raw in raw_analytics["metrics"][:10]:
            item = _mapping(raw)
            analytics_metrics.append({
                key: value
                for key, value in {
                    "id": _text(item.get("id"), 120),
                    "label": _text(item.get("label"), 120),
                    "value": _number(item.get("value")),
                    "unit": _text(item.get("unit"), 40),
                    "method": _text(item.get("method"), 180),
                    "dependsOn": item.get("dependsOn") if isinstance(item.get("dependsOn"), list) else None,
                }.items()
                if value is not None
            })
    scorecard = []
    if isinstance(data.get("scorecard"), list):
        for raw in data["scorecard"][:4]:
            item = _mapping(raw)
            scorecard.append({
                key: value
                for key, value in {
                    "id": _text(item.get("id"), 40),
                    "title": _text(item.get("title"), 80),
                    "score": _number(item.get("score")),
                    "status": _text(item.get("status"), 24),
                    "signalCount": _number(item.get("signalCount")),
                    "evidenceIds": item.get("evidenceIds") if isinstance(item.get("evidenceIds"), list) else None,
                }.items()
                if value is not None
            })
    raw_workflow = _mapping(data.get("workflow"))
    raw_task = _mapping(raw_workflow.get("task"))
    raw_quality = _mapping(raw_workflow.get("dataQuality"))
    raw_diagnostics = _mapping(raw_workflow.get("diagnostics"))
    raw_history_state = _mapping(raw_workflow.get("history"))
    workflow_blocks = []
    if isinstance(raw_workflow.get("blocks"), list):
        for raw in raw_workflow["blocks"][:8]:
            item = _mapping(raw)
            workflow_blocks.append({
                key: value
                for key, value in {
                    "id": _text(item.get("id"), 80),
                    "title": _text(item.get("title"), 100),
                    "status": _text(item.get("status"), 32),
                    "qualityScore": _number(item.get("qualityScore")),
                    "evidenceCount": _number(item.get("evidenceCount")),
                    "sources": item.get("sources") if isinstance(item.get("sources"), list) else None,
                    "asOf": _text(item.get("asOf"), 80),
                    "warnings": item.get("warnings") if isinstance(item.get("warnings"), list) else None,
                    "gaps": item.get("gaps") if isinstance(item.get("gaps"), list) else None,
                }.items()
                if value is not None
            })
    source_status = []
    if isinstance(raw_workflow.get("sourceStatus"), list):
        for raw in raw_workflow["sourceStatus"][:10]:
            item = _mapping(raw)
            source_status.append({
                key: value
                for key, value in {
                    "id": _text(item.get("id"), 100),
                    "title": _text(item.get("title"), 100),
                    "status": _text(item.get("status"), 32),
                    "source": _text(item.get("source"), 140),
                    "asOf": _text(item.get("asOf"), 80),
                    "message": _text(item.get("message"), 200),
                }.items()
                if value is not None
            })
    report_history = []
    if isinstance(data.get("reportHistory"), list):
        for raw in data["reportHistory"][:6]:
            item = _mapping(raw)
            report_history.append({
                key: value
                for key, value in {
                    "id": _text(item.get("id"), 140),
                    "status": _text(item.get("status"), 32),
                    "qualityScore": _number(item.get("qualityScore")),
                    "qualityLevel": _text(item.get("qualityLevel"), 24),
                    "coverageRatio": _number(item.get("coverageRatio")),
                    "gapCount": _number(item.get("gapCount")),
                    "createdAt": _text(item.get("createdAt"), 80),
                }.items()
                if value is not None
            })
    workflow = {
        "task": {
            key: value
            for key, value in {
                "status": _text(raw_task.get("status"), 32),
                "stage": _text(raw_task.get("stage"), 80),
                "progress": _number(raw_task.get("progress")),
                "updatedAt": _text(raw_task.get("updatedAt"), 80),
            }.items()
            if value is not None
        },
        "dataQuality": {
            key: value
            for key, value in {
                "score": _number(raw_quality.get("score")),
                "level": _text(raw_quality.get("level"), 24),
                "blockScores": _mapping(raw_quality.get("blockScores")),
                "limitations": raw_quality.get("limitations") if isinstance(raw_quality.get("limitations"), list) else None,
                "warnings": raw_quality.get("warnings") if isinstance(raw_quality.get("warnings"), list) else None,
            }.items()
            if value is not None
        },
        "blocks": workflow_blocks,
        "sourceStatus": source_status,
        "diagnostics": {
            key: value
            for key, value in {
                "missingBlocks": raw_diagnostics.get("missingBlocks") if isinstance(raw_diagnostics.get("missingBlocks"), list) else None,
                "failedSources": raw_diagnostics.get("failedSources") if isinstance(raw_diagnostics.get("failedSources"), list) else None,
                "fallbackSources": raw_diagnostics.get("fallbackSources") if isinstance(raw_diagnostics.get("fallbackSources"), list) else None,
                "gapCount": _number(raw_diagnostics.get("gapCount")),
            }.items()
            if value is not None
        },
        "history": {
            key: value
            for key, value in {
                "state": _text(raw_history_state.get("state"), 32),
                "lastGoodAt": _text(raw_history_state.get("lastGoodAt"), 80),
                "items": report_history,
            }.items()
            if value is not None
        },
    }
    return {
        "identity": {
            key: value
            for key, value in {
                "symbol": _text(raw_identity.get("symbol"), 24),
                "name": _text(raw_identity.get("name"), 120),
                "market": _text(raw_identity.get("market"), 16),
                "currency": _text(raw_identity.get("currency"), 16),
            }.items()
            if value is not None
        },
        "coverage": {
            key: value
            for key, value in {
                "coveredDimensions": _number(
                    raw_coverage.get("coveredDimensions")
                ),
                "totalDimensions": _number(raw_coverage.get("totalDimensions")),
                "ratio": _number(raw_coverage.get("ratio")),
            }.items()
            if value is not None
        },
        "coveredSections": covered,
        "gapSections": missing,
        "analytics": analytics_metrics,
        "scorecard": scorecard,
        "comparisonProfile": _mapping(data.get("comparisonProfile")),
        "workflow": workflow,
        "evidenceLedger": evidence,
        "sources": [
            text
            for item in (data.get("sources") if isinstance(data.get("sources"), list) else [])[:12]
            if (text := _text(item, 160))
        ],
        "gaps": [
            text
            for item in (data.get("gaps") if isinstance(data.get("gaps"), list) else [])[:12]
            if (text := _text(item, 240))
        ],
        "generatedAt": _text(data.get("generatedAt"), 80),
    }


def _project_comparison(payload: object) -> dict[str, Any]:
    data = _mapping(_mapping(payload).get("data"))
    rows = []
    if isinstance(data.get("rows"), list):
        for raw in data["rows"][:8]:
            row = _mapping(raw)
            rows.append({
                "identity": _mapping(row.get("identity")),
                "coverage": _mapping(row.get("coverage")),
                "metrics": _mapping(row.get("metrics")),
                "scores": _mapping(row.get("scores")),
            })
    errors = []
    if isinstance(data.get("errors"), list):
        for raw in data["errors"][:8]:
            item = _mapping(raw)
            errors.append({
                "symbol": _text(item.get("symbol"), 24),
                "message": _text(item.get("message"), 160),
            })
    return {"rows": rows, "errors": errors, "generatedAt": _text(data.get("generatedAt"), 80)}


def _project_events(payload: object) -> dict[str, Any]:
    raw_data = _mapping(payload).get("data")
    rows = raw_data if isinstance(raw_data, list) else []
    items: list[dict[str, str]] = []
    for raw in rows[:MAX_EVENT_ITEMS]:
        row = _mapping(raw)
        projected = {
            "title": _first_text(
                row,
                ("title", "新闻标题", "报告名称", "reportTitle"),
                180,
            ),
            "date": _first_text(row, ("date", "发布时间", "publishDate", "publish_time"), 80),
            "source": _first_text(
                row,
                ("文章来源", "source", "orgSName", "orgName", "type"),
                120,
            ),
            "url": _first_text(row, ("新闻链接", "url", "pdfUrl"), 320),
        }
        items.append({key: value for key, value in projected.items() if value})
    return {"items": items, "untrustedExternalText": True}


def _project(capability: str, payload: object) -> dict[str, Any]:
    if capability == "market.ohlcv":
        return _project_ohlcv(payload)
    if capability == "research.equity-snapshot":
        return _project_snapshot(payload)
    if capability == "research.equity-comparison":
        return _project_comparison(payload)
    return _project_events(payload)


def _fit_context(research: dict[str, Any]) -> dict[str, Any]:
    if (
        len(json.dumps(research, ensure_ascii=False, default=str))
        <= MAX_RESEARCH_CONTEXT_CHARACTERS
    ):
        return research
    evidence = research.get("evidence")
    if not isinstance(evidence, dict):
        return research
    long_term = evidence.get("market.ohlcv")
    if not isinstance(long_term, dict):
        long_term = {}
    if isinstance(long_term.get("recentBars"), list):
        long_term["recentBars"] = long_term["recentBars"][-12:]
    snapshot = evidence.get("research.equity-snapshot")
    if not isinstance(snapshot, dict):
        snapshot = {}
    if isinstance(snapshot.get("evidenceLedger"), list):
        snapshot["evidenceLedger"] = snapshot["evidenceLedger"][:10]
    for key, value in evidence.items():
        if (
            key.startswith("market.")
            and isinstance(value, dict)
            and isinstance(value.get("items"), list)
        ):
            value["items"] = value["items"][:5]
    if (
        len(json.dumps(research, ensure_ascii=False, default=str))
        <= MAX_RESEARCH_CONTEXT_CHARACTERS
    ):
        return research
    for value in evidence.values():
        if not isinstance(value, dict):
            continue
        value.pop("recentBars", None)
        value.pop("evidenceLedger", None)
        value.pop("items", None)
    if (
        len(json.dumps(research, ensure_ascii=False, default=str))
        <= MAX_RESEARCH_CONTEXT_CHARACTERS
    ):
        return research
    research["evidence"] = {}
    research["usedCapabilities"] = []
    research["gaps"] = [
        *research.get("gaps", []),
        {"capability": "research.context", "reason": "trimmed_for_size"},
    ]
    return research


class LightResearchContextEnricher:
    def __init__(
        self,
        registry: DataServiceRegistry,
        client: DataServiceClient,
        *,
        timeout_seconds: float = 8.0,
    ):
        self._registry = registry
        self._client = client
        self._timeout_seconds = timeout_seconds

    async def enrich(self, request: AgentTaskCreate) -> AgentTaskCreate:
        if request.capability != "module.explain":
            return request
        subject = _normalize_subject(request.context)
        if subject is None:
            return request
        plan = _planned_capabilities(
            request.prompt,
            subject,
            _adjustment(request.context, subject["market"]),
        )
        results = await asyncio.gather(
            *(self._invoke(capability, input_data) for capability, input_data in plan)
        )
        evidence: dict[str, Any] = {}
        gaps: list[dict[str, str]] = []
        for capability, payload in results:
            if payload is None:
                gaps.append({"capability": capability, "reason": "temporarily_unavailable"})
            else:
                evidence[capability] = _project(capability, payload)
        research = _fit_context(
            {
                "mode": "light",
                "subject": subject,
                "asOf": datetime.now(UTC).isoformat(),
                "usedCapabilities": list(evidence),
                "evidence": evidence,
                "gaps": gaps,
            }
        )
        context = dict(request.context)
        vibedesk = dict(_mapping(context.get("vibedesk")))
        vibedesk["research"] = research
        context["vibedesk"] = vibedesk
        return request.model_copy(update={"context": context})

    async def _invoke(
        self,
        capability: str,
        input_data: dict[str, Any],
    ) -> tuple[str, object | None]:
        try:
            service = self._registry.resolve(capability)
            result = await asyncio.wait_for(
                self._client.invoke(service, capability, input_data),
                timeout=self._timeout_seconds,
            )
            return capability, result
        except Exception:
            return capability, None
