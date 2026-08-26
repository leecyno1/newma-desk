#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Bounded, cancellable batch scanning built on the single CZSC interface."""

from __future__ import annotations

from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from datetime import datetime
from threading import Event
from typing import Any, Callable, Iterable, Optional

from instock.core.czsc_analysis import run_czsc_analysis
from instock.core.market_data_provider import MarketDataProvider


ProgressCallback = Callable[[dict[str, Any]], None]


def _candidate_score(payload: dict[str, Any]) -> tuple[float, list[str]]:
    """Return a transparent InStock heuristic score, never an official signal."""

    if payload.get("conclusion_state") == "insufficient_history":
        actual_bars = int(payload.get("actual_bars") or 0)
        return 0.0, [
            f"仅 {actual_bars} 根 K 线，少于 80 根；不进入正式候选排名"
        ]

    summary = payload.get("summary", {})
    insight = payload.get("insight", {})
    evidence = payload.get("evidence", {})
    stability = evidence.get("structure_stability", {})
    input_quality = evidence.get("input_quality", {})
    score = float(stability.get("score") or 0) * 0.45
    reasons = [f"结构稳定性 {stability.get('score', 0)}/100"]

    bias = insight.get("bias")
    if bias == "bullish":
        score += 25
        reasons.append("结构偏多 +25")
    elif bias == "neutral":
        score += 10
        reasons.append("结构中性 +10")
    else:
        reasons.append("结构偏空 +0")

    strength = min(max(float(summary.get("trend_strength") or 0), 0), 100)
    score += strength * 0.20
    reasons.append(f"趋势强度贡献 {strength * 0.20:.1f}")

    latest_signal = str(summary.get("latest_signal") or "无")
    signal_source = summary.get("signal_source")
    if signal_source == "czsc_official" and "买" in latest_signal:
        score += 15
        reasons.append("CZSC 官方买入类信号 +15")
    elif signal_source == "czsc_official" and "卖" in latest_signal:
        score -= 15
        reasons.append("CZSC 官方卖出类信号 -15")
    elif signal_source == "instock_heuristic" and "买" in latest_signal:
        score += 6
        reasons.append("项目启发式买点 +6")
    elif signal_source == "instock_heuristic" and "卖" in latest_signal:
        score -= 6
        reasons.append("项目启发式卖点 -6")

    if input_quality.get("state") == "partial":
        score -= 10
        reasons.append("输入质量 partial -10")
    return round(max(0, min(100, score)), 2), reasons


class CZSCBatchScanner:
    """Scan a bounded symbol list without duplicating CZSC orchestration."""

    engine_name = "instock-czsc-batch"
    engine_version = "1.0.0"
    ranking_method = "instock-czsc-candidate-score-v1"

    def __init__(self, provider: MarketDataProvider, max_workers: int = 4):
        self.provider = provider
        self.max_workers = max(1, min(int(max_workers), 4))

    def _analyze_one(
        self,
        symbol: str,
        period: str,
        bars: int,
        as_of: Optional[str],
    ) -> dict[str, Any]:
        payload = run_czsc_analysis(
            self.provider,
            symbol=symbol,
            period=period,
            bars=bars,
            as_of=as_of,
            include_chart=False,
        )
        candidate_score, score_reasons = _candidate_score(payload)
        summary = payload["summary"]
        evidence = payload["evidence"]
        insight = payload["insight"]
        return {
            "symbol": symbol,
            "end_date": payload["end_date"],
            "latest_close": payload["latest_close"],
            "trend": summary.get("trend"),
            "trend_strength": summary.get("trend_strength"),
            "bias": insight.get("bias"),
            "headline": insight.get("headline"),
            "conclusion_state": payload.get("conclusion_state", "formed"),
            "actual_bars": int(payload.get("actual_bars") or 0),
            "latest_signal": summary.get("latest_signal"),
            "signal_source": summary.get("signal_source"),
            "structure_stability": evidence.get("structure_stability"),
            "latest_structure_change": evidence.get("latest_structure_change"),
            "input_quality": evidence.get("input_quality"),
            "candidate_score": candidate_score,
            "score_reasons": score_reasons,
            "snapshot_id": payload["snapshot"]["snapshot_id"],
            "data_source": payload["data_source"],
        }

    def scan(
        self,
        symbols: Iterable[str],
        *,
        period: str = "daily",
        bars: int = 240,
        as_of: Optional[str] = None,
        cancel_event: Optional[Event] = None,
        on_progress: Optional[ProgressCallback] = None,
    ) -> dict[str, Any]:
        ordered_symbols = tuple(dict.fromkeys(str(item).strip().upper() for item in symbols))
        cancellation = cancel_event or Event()
        total = len(ordered_symbols)
        completed = 0
        results: list[dict[str, Any]] = []
        failures: list[dict[str, str]] = []

        def notify(current_symbol: Optional[str] = None) -> None:
            if on_progress:
                on_progress({
                    "total": total,
                    "completed": completed,
                    "succeeded": len(results),
                    "failed": len(failures),
                    "current_symbol": current_symbol,
                    "cancel_requested": cancellation.is_set(),
                })

        executor = ThreadPoolExecutor(max_workers=min(self.max_workers, max(total, 1)))
        pending: dict[Future, str] = {}
        iterator = iter(ordered_symbols)

        def schedule_one() -> bool:
            if cancellation.is_set():
                return False
            try:
                symbol = next(iterator)
            except StopIteration:
                return False
            future = executor.submit(self._analyze_one, symbol, period, bars, as_of)
            pending[future] = symbol
            return True

        try:
            for _ in range(min(self.max_workers, total)):
                schedule_one()
            notify()
            while pending:
                if cancellation.is_set():
                    for future in pending:
                        future.cancel()
                    # Python threads and urllib calls cannot be forcefully
                    # interrupted. Keep the scan active until every request
                    # already handed to the executor has actually settled.
                    wait(tuple(pending))
                    for future in pending:
                        if not future.cancelled():
                            try:
                                future.result()
                            except Exception:
                                pass
                    pending.clear()
                    notify()
                    break
                finished, _ = wait(tuple(pending), timeout=0.2, return_when=FIRST_COMPLETED)
                if not finished:
                    continue
                for future in finished:
                    symbol = pending.pop(future)
                    completed += 1
                    try:
                        results.append(future.result())
                    except Exception as exc:  # one symbol must not fail the batch
                        failures.append({"symbol": symbol, "error": str(exc)})
                    notify(symbol)
                    schedule_one()
        finally:
            executor.shutdown(wait=True, cancel_futures=cancellation.is_set())

        rankable_results = [
            row for row in results
            if row.get("conclusion_state") != "insufficient_history"
        ]
        short_history_watchlist = [
            row for row in results
            if row.get("conclusion_state") == "insufficient_history"
        ]
        rankable_results.sort(key=lambda item: (-item["candidate_score"], item["symbol"]))
        short_history_watchlist.sort(key=lambda item: item["symbol"])
        for rank, row in enumerate(rankable_results, start=1):
            row["rank"] = rank
        status = "cancelled" if cancellation.is_set() else "completed"
        return {
            "engine": {"name": self.engine_name, "version": self.engine_version},
            "ranking_method": self.ranking_method,
            "ranking_is_official_czsc": False,
            "status": status,
            "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
            "parameters": {
                "symbols": list(ordered_symbols),
                "period": period,
                "bars": bars,
                "asOf": as_of,
                "max_workers": self.max_workers,
            },
            "progress": {
                "total": total,
                "completed": completed,
                "succeeded": len(results),
                "failed": len(failures),
                "cancel_requested": cancellation.is_set(),
            },
            "summary": {
                "bullish": sum(row["bias"] == "bullish" for row in rankable_results),
                "neutral": sum(row["bias"] == "neutral" for row in rankable_results),
                "bearish": sum(row["bias"] == "bearish" for row in rankable_results),
                "partial_input": sum(row["input_quality"].get("state") == "partial" for row in results),
                "short_history_watch": len(short_history_watchlist),
            },
            "candidates": rankable_results,
            "short_history_watchlist": short_history_watchlist,
            "failures": failures,
            "limitations": [
                "candidate_score_is_instock_heuristic_not_official_czsc_signal",
                "cancellation_does_not_interrupt_an_already_running_upstream_http_request",
                *(
                    ["short_history_securities_excluded_from_formal_ranking"]
                    if short_history_watchlist else []
                ),
            ],
        }
