from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any, Protocol

from vibe_visualization_api.finance_pilots.models import (
    AttributionItem,
    BacktestDataset,
    BacktestMetrics,
    DailyStockAnalysisContext,
    EquityPoint,
    ResearchContextBlock,
    ResearchDataQuality,
    ResearchHistoryItem,
    ResearchSubject,
    ResearchTaskProgress,
    StrategyIdentity,
    StrategyLedgerRecord,
)


class PilotPayloadError(ValueError):
    """Raised when an upstream payload violates the extraction contract."""


class PilotExtractionAdapter(Protocol):
    pilot_id: str

    def adapt(self, payload: Mapping[str, Any]) -> DailyStockAnalysisContext | StrategyLedgerRecord: ...


_RESEARCH_STATUSES = {
    "available",
    "missing",
    "not_supported",
    "fallback",
    "stale",
    "estimated",
    "partial",
    "fetch_failed",
}
_QUALITY_LEVELS = {"good", "usable", "limited", "poor"}
_DANGEROUS_QUANT_KEYS = {
    "agent",
    "api_key",
    "broker",
    "broker_account",
    "credentials",
    "live_trading",
    "mcp",
    "orders",
    "password",
    "quick_trade",
    "script",
    "secret",
    "source_code",
    "token",
}
_SENSITIVE_KEY_MARKERS = (
    "api_key",
    "apikey",
    "authorization",
    "bearer",
    "broker_account",
    "credential",
    "password",
    "secret",
    "token",
)
_METRIC_KEYS = {
    "total_return": ("total_return", "totalReturn", "return"),
    "annualized_return": ("annualized_return", "annualizedReturn", "annual_return"),
    "max_drawdown": ("max_drawdown", "maxDrawdown", "drawdown"),
    "volatility": ("volatility",),
    "sharpe": ("sharpe", "sharpe_ratio", "sharpeRatio"),
    "sortino": ("sortino", "sortino_ratio", "sortinoRatio"),
    "win_rate": ("win_rate", "winRate"),
    "turnover": ("turnover",),
    "fees": ("fees", "total_fees", "totalFees"),
    "trade_count": ("trade_count", "tradeCount", "trades"),
}


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _pick(value: Mapping[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in value and value[key] is not None:
            return value[key]
    return None


def _text(value: Any, *, limit: int = 500) -> str | None:
    if value is None:
        return None
    result = str(value).strip()
    if not result:
        return None
    lowered = result.casefold()
    if any(marker in lowered for marker in _SENSITIVE_KEY_MARKERS):
        return "[REDACTED]"
    return result[:limit]


def _float(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _integer(value: Any) -> int | None:
    number = _float(value)
    if number is None or not number.is_integer():
        return None
    return int(number)


def _strings(value: Any, *, limit: int = 20) -> list[str]:
    if not isinstance(value, list):
        return []
    result: list[str] = []
    for item in value:
        text = _text(item, limit=240)
        if text and text not in result:
            result.append(text)
    return result[:limit]


def _simple_parameters(value: Any) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, item in list(_mapping(value).items())[:100]:
        name = _text(key, limit=80)
        if not name or name == "[REDACTED]":
            continue
        if isinstance(item, (str, int, float, bool)) or item is None:
            result[name] = item
        elif isinstance(item, list) and len(item) <= 50 and all(
            isinstance(entry, (str, int, float, bool)) or entry is None
            for entry in item
        ):
            result[name] = item
    return result


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


class DailyStockAnalysisAdapter:
    """Extract low-sensitivity analysis context without investment advice."""

    pilot_id = "daily-stock-analysis"

    @staticmethod
    def _blocks(context: Mapping[str, Any]) -> list[ResearchContextBlock]:
        raw_blocks = context.get("blocks")
        entries: list[tuple[str, Mapping[str, Any]]] = []
        if isinstance(raw_blocks, Mapping):
            entries = [
                (str(key), _mapping(value)) for key, value in raw_blocks.items()
            ]
        elif isinstance(raw_blocks, list):
            entries = [
                (
                    _text(_pick(_mapping(value), "key", "id"), limit=80)
                    or f"block-{index + 1}",
                    _mapping(value),
                )
                for index, value in enumerate(raw_blocks)
                if isinstance(value, Mapping)
            ]

        result: list[ResearchContextBlock] = []
        for block_id, block in entries[:50]:
            status = _text(block.get("status"), limit=40) or "missing"
            if status not in _RESEARCH_STATUSES:
                status = "partial"
            items = _mapping(block.get("items"))
            first_item = next(
                (_mapping(item) for item in items.values() if isinstance(item, Mapping)),
                {},
            )
            source = _text(_pick(block, "source")) or _text(first_item.get("source"))
            as_of = _text(_pick(block, "timestamp", "as_of", "asOf"), limit=80)
            gaps = _strings(_pick(block, "missing_reasons", "missingReasons"), limit=10)
            if not gaps:
                gaps = [
                    reason
                    for item in items.values()
                    if isinstance(item, Mapping)
                    if (reason := _text(_pick(item, "missing_reason", "missingReason"), limit=240))
                ][:10]
            result.append(
                ResearchContextBlock(
                    id=block_id[:80],
                    title=_text(_pick(block, "label", "title"), limit=120) or block_id[:120],
                    status=status,
                    source=source,
                    as_of=as_of,
                    warnings=_strings(block.get("warnings"), limit=10),
                    gaps=list(dict.fromkeys(gaps)),
                )
            )
        return result

    @staticmethod
    def _quality(context: Mapping[str, Any]) -> ResearchDataQuality:
        raw = _mapping(_pick(context, "data_quality", "dataQuality"))
        score = _integer(_pick(raw, "overall_score", "overallScore", "score"))
        if score is not None and not 0 <= score <= 100:
            score = None
        level = _text(raw.get("level"), limit=20)
        if level not in _QUALITY_LEVELS:
            level = None
        block_scores: dict[str, int] = {}
        for key, value in list(
            _mapping(_pick(raw, "block_scores", "blockScores")).items()
        )[:50]:
            number = _integer(value)
            name = _text(key, limit=80)
            if name and number is not None and 0 <= number <= 100:
                block_scores[name] = number
        return ResearchDataQuality(
            score=score,
            level=level,
            block_scores=block_scores,
            limitations=_strings(raw.get("limitations"), limit=20),
            warnings=_strings(raw.get("warnings"), limit=20),
        )

    @staticmethod
    def _history(payload: Mapping[str, Any]) -> list[ResearchHistoryItem]:
        raw = _pick(payload, "report_history", "reportHistory", "history")
        if not isinstance(raw, list):
            return []
        result: list[ResearchHistoryItem] = []
        for index, value in enumerate(raw[:100]):
            item = _mapping(value)
            item_id = _text(_pick(item, "id", "report_id", "reportId"), limit=120)
            status = _text(item.get("status"), limit=40)
            if not item_id or not status:
                continue
            result.append(
                ResearchHistoryItem(
                    id=item_id,
                    status=status,
                    created_at=_text(
                        _pick(item, "created_at", "createdAt", "timestamp"), limit=80
                    ),
                    title=_text(_pick(item, "title", "name"), limit=160),
                )
            )
        return result

    @staticmethod
    def _progress(payload: Mapping[str, Any]) -> ResearchTaskProgress | None:
        item = _mapping(_pick(payload, "task_progress", "taskProgress", "task"))
        status = _text(item.get("status"), limit=40)
        if not status:
            return None
        progress = _float(_pick(item, "progress", "ratio"))
        if progress is not None and progress > 1 and progress <= 100:
            progress /= 100
        if progress is not None and not 0 <= progress <= 1:
            progress = None
        return ResearchTaskProgress(
            task_id=_text(_pick(item, "task_id", "taskId", "id"), limit=120),
            status=status,
            stage=_text(_pick(item, "stage", "phase"), limit=120),
            progress=progress,
            updated_at=_text(_pick(item, "updated_at", "updatedAt"), limit=80),
        )

    def adapt(self, payload: Mapping[str, Any]) -> DailyStockAnalysisContext:
        context = _mapping(
            _pick(payload, "analysis_context", "analysisContext", "analysis_context_pack")
        )
        if not context:
            context = payload
        data_policy = _text(
            _pick(payload, "data_policy", "dataPolicy")
            or _pick(context, "data_policy", "dataPolicy"),
            limit=40,
        )
        if data_policy not in {"desk-only", "newma-desk", "dock-only", "newma-dock"}:
            raise PilotPayloadError(
                "daily-stock-analysis extraction requires Desk-only data"
            )
        subject = _mapping(context.get("subject"))
        symbol = _text(_pick(subject, "code", "symbol"), limit=24)
        if not symbol:
            raise PilotPayloadError("daily-stock-analysis payload requires a subject symbol")
        blocks = self._blocks(context)
        if not blocks:
            raise PilotPayloadError("daily-stock-analysis payload requires context blocks")
        quality = self._quality(context)
        sources = list(
            dict.fromkeys(block.source for block in blocks if block.source)
        )
        available_blocks = [block.id for block in blocks if block.status == "available"]
        gap_blocks = [block.id for block in blocks if block.status != "available"]
        market = _text(subject.get("market"), limit=40)
        return DailyStockAnalysisContext(
            subject=ResearchSubject(
                symbol=symbol.upper(),
                name=_text(_pick(subject, "stock_name", "stockName", "name"), limit=160),
                market=market,
            ),
            blocks=blocks,
            data_quality=quality,
            report_history=self._history(payload),
            task_progress=self._progress(payload),
            sources=sources,
            generated_at=_text(
                _pick(context, "created_at", "createdAt", "generated_at", "generatedAt"),
                limit=80,
            ),
            agent_context={
                "type": "research-analysis-context",
                "subject": {"symbol": symbol.upper(), "market": market},
                "availableBlocks": available_blocks,
                "gapBlocks": gap_blocks,
                "dataQuality": quality.model_dump(mode="json", by_alias=True),
                "sources": sources,
            },
        )


class QuantDingerAdapter:
    """Extract paper backtests into Desk's Strategy Ledger contract."""

    pilot_id = "quantdinger"

    @staticmethod
    def _reject_dangerous_fields(payload: Mapping[str, Any]) -> None:
        execution_mode = _text(
            _pick(payload, "execution_mode", "executionMode", "mode"), limit=40
        )
        if not execution_mode or execution_mode.casefold() not in {
            "paper",
            "paper-only",
            "backtest",
            "simulation",
        }:
            raise PilotPayloadError("QuantDinger extraction only accepts paper backtests")
        for scope_name, scope in (
            ("payload", payload),
            ("strategy", _mapping(payload.get("strategy"))),
            ("result", _mapping(payload.get("result"))),
        ):
            dangerous = {
                str(key).casefold()
                for key in scope
                if str(key).casefold() in _DANGEROUS_QUANT_KEYS
            }
            if dangerous:
                fields = ", ".join(sorted(dangerous))
                raise PilotPayloadError(
                    f"QuantDinger {scope_name} contains forbidden fields: {fields}"
                )

    @staticmethod
    def _metrics(result: Mapping[str, Any]) -> BacktestMetrics:
        raw = _mapping(result.get("metrics")) or result
        values: dict[str, Any] = {}
        for normalized, aliases in _METRIC_KEYS.items():
            value = _pick(raw, *aliases)
            values[normalized] = _integer(value) if normalized == "trade_count" else _float(value)
        return BacktestMetrics(**values)

    @staticmethod
    def _equity_curve(result: Mapping[str, Any]) -> list[EquityPoint]:
        raw = _pick(result, "equity_curve", "equityCurve", "curve")
        if not isinstance(raw, list):
            return []
        points: list[EquityPoint] = []
        for value in raw[:5000]:
            item = _mapping(value)
            timestamp = _text(_pick(item, "timestamp", "date", "time"), limit=80)
            equity = _float(_pick(item, "equity", "value", "nav"))
            if timestamp and equity is not None:
                points.append(EquityPoint(timestamp=timestamp, equity=equity))
        return points

    @staticmethod
    def _attribution(result: Mapping[str, Any]) -> list[AttributionItem]:
        raw = _pick(result, "attribution", "performance_attribution", "performanceAttribution")
        if not isinstance(raw, list):
            return []
        items: list[AttributionItem] = []
        for value in raw[:100]:
            item = _mapping(value)
            factor = _text(_pick(item, "factor", "name", "source"), limit=120)
            contribution = _float(_pick(item, "contribution", "value"))
            if factor and contribution is not None:
                items.append(
                    AttributionItem(
                        factor=factor,
                        contribution=contribution,
                        unit=_text(item.get("unit"), limit=20) or "%",
                        note=_text(item.get("note"), limit=300),
                    )
                )
        return items

    def adapt(self, payload: Mapping[str, Any]) -> StrategyLedgerRecord:
        self._reject_dangerous_fields(payload)
        strategy = _mapping(payload.get("strategy"))
        dataset = _mapping(payload.get("dataset"))
        result = _mapping(payload.get("result"))
        data_source = _text(
            _pick(dataset, "source", "data_source", "dataSource"), limit=40
        )
        if data_source not in {
            "desk",
            "desk-only",
            "newma-desk",
            "dock",
            "dock-only",
            "newma-dock",
        }:
            raise PilotPayloadError("QuantDinger extraction requires Desk-only data")
        strategy_id = _text(_pick(strategy, "id", "strategy_id", "strategyId"), limit=120)
        strategy_name = _text(_pick(strategy, "name", "title"), limit=160)
        symbols_raw = _pick(dataset, "symbols", "securities")
        symbols = (
            [symbol.upper() for value in symbols_raw if (symbol := _text(value, limit=24))]
            if isinstance(symbols_raw, list)
            else []
        )
        start_date = _text(_pick(dataset, "start_date", "startDate"), limit=40)
        end_date = _text(_pick(dataset, "end_date", "endDate"), limit=40)
        if not strategy_id or not strategy_name:
            raise PilotPayloadError("QuantDinger payload requires strategy identity")
        if not symbols or not start_date or not end_date:
            raise PilotPayloadError("QuantDinger payload requires a Desk dataset window")
        status = (_text(result.get("status"), limit=40) or "completed").casefold()
        if status not in {"completed", "failed", "partial"}:
            status = "partial"
        metrics = self._metrics(result)
        attribution = self._attribution(result)
        canonical = {
            "strategy": {
                "id": strategy_id,
                "version": _text(strategy.get("version"), limit=80),
                "parameters": _simple_parameters(
                    _pick(strategy, "parameters", "params")
                ),
            },
            "dataset": {
                "symbols": symbols,
                "startDate": start_date,
                "endDate": end_date,
                "timeframe": _text(_pick(dataset, "timeframe", "interval"), limit=40),
            },
            "metrics": metrics.model_dump(mode="json", by_alias=True),
            "attribution": [item.model_dump(mode="json", by_alias=True) for item in attribution],
        }
        ledger_id = hashlib.sha256(
            json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()[:24]
        generated_at = _text(
            _pick(payload, "generated_at", "generatedAt", "created_at", "createdAt"),
            limit=80,
        ) or _now_iso()
        return StrategyLedgerRecord(
            ledger_id=f"quantdinger-{ledger_id}",
            status=status,
            strategy=StrategyIdentity(
                id=strategy_id,
                name=strategy_name,
                version=_text(strategy.get("version"), limit=80),
                template_id=_text(
                    _pick(strategy, "template_id", "templateId"), limit=120
                ),
                parameters=_simple_parameters(_pick(strategy, "parameters", "params")),
            ),
            dataset=BacktestDataset(
                symbols=list(dict.fromkeys(symbols))[:500],
                market=_text(dataset.get("market"), limit=40),
                start_date=start_date,
                end_date=end_date,
                timeframe=_text(_pick(dataset, "timeframe", "interval"), limit=40),
            ),
            metrics=metrics,
            equity_curve=self._equity_curve(result),
            attribution=attribution,
            generated_at=generated_at,
            provenance={
                "pilotId": self.pilot_id,
                "dataPolicy": "desk-only",
                "executionPolicy": "paper-only",
            },
            agent_context={
                "type": "strategy-ledger",
                "ledgerId": f"quantdinger-{ledger_id}",
                "strategy": {"id": strategy_id, "name": strategy_name},
                "dataset": {
                    "symbols": list(dict.fromkeys(symbols))[:500],
                    "startDate": start_date,
                    "endDate": end_date,
                },
                "metrics": metrics.model_dump(mode="json", by_alias=True),
                "attribution": [
                    item.model_dump(mode="json", by_alias=True) for item in attribution
                ],
            },
        )
