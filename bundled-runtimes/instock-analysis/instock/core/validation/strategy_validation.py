#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Shared point-in-time validation semantics for InStock research Modules."""

from __future__ import annotations

from typing import Any, Mapping, Sequence

import numpy as np
import pandas as pd

from instock.core.analysis_snapshot import (
    build_analysis_snapshot,
    get_analysis_snapshot_registry,
    normalize_as_of,
)
from instock.core.market_data_provider import MarketDataError, MarketDataProvider
from instock.core.validation.metrics import calculate_return_metrics, round_metric
from instock.core.validation.execution import resolve_next_open_window, round_trip_cost


class StrategyValidationError(ValueError):
    """Raised when a validation packet violates the point-in-time contract."""


def _round(value: float, digits: int = 4) -> float:
    return round_metric(value, digits)


def _metrics(trades: Sequence[Mapping[str, Any]], holding_period: int) -> dict[str, Any]:
    return calculate_return_metrics(trades, period_sessions=holding_period)


class StrategyValidationEngine:
    engine_name = "instock-strategy-validation"
    engine_version = "1.0.0"
    schema_version = "instock-strategy-validation-packet-v1"
    supported_sources = {"stock-candidates", "czsc", "rotation"}
    request_limit = 800

    def __init__(self, provider: MarketDataProvider):
        self.provider = provider

    def validate(self, packet: Mapping[str, Any]) -> dict[str, Any]:
        normalized = self._validate_packet(packet)
        benchmark_frame = self._load_frame(normalized["benchmark"], normalized["as_of"])
        frames = {
            symbol: self._load_frame(symbol, normalized["as_of"])
            for symbol in sorted({symbol for signal in normalized["signals"] for symbol in signal["symbols"]})
        }
        trades, failures = self._execute(normalized, benchmark_frame, frames)
        split_at = max(1, int(len(trades) * 0.65)) if len(trades) > 1 else len(trades)
        train_trades = trades[:split_at]
        test_trades = trades[split_at:]
        holding_period = normalized["holding_period_sessions"]
        train = _metrics(train_trades, holding_period)
        out_of_sample = _metrics(test_trades, holding_period)
        coverage_ratio = len(trades) / len(normalized["signals"])
        evidence_sufficient = len(trades) >= 6 and len(test_trades) >= 2 and coverage_ratio >= 0.8
        coverage = {
            "input_signals": len(normalized["signals"]),
            "executed_signals": len(trades),
            "failed_signals": len(failures),
            "ratio": _round(coverage_ratio),
            "evidence_sufficient": evidence_sufficient,
        }
        limitations = [
            "fixed_holding_period_does_not_model_intraday_stops",
            "latest_800_bar_data_boundary",
            "signals_must_be_point_in_time_and_are_not_reconstructed_by_this_module",
        ]
        if not evidence_sufficient:
            limitations.append("insufficient_out_of_sample_evidence")
        if failures:
            limitations.append("some_signals_could_not_be_executed")

        result_summary = {
            "strategy_id": normalized["strategy"]["id"],
            "source_module": normalized["strategy"]["source_module"],
            "coverage": coverage,
            "out_of_sample": out_of_sample,
        }
        snapshot = build_analysis_snapshot(
            analysis_name=self.engine_name,
            analysis_version=self.engine_version,
            parameters={
                "benchmark": normalized["benchmark"],
                "asOf": normalized["as_of"],
                "holdingPeriodSessions": holding_period,
                "costBpsPerSide": normalized["cost_bps_per_side"],
            },
            frame=benchmark_frame,
            requested_bars=len(benchmark_frame),
            provider_name=self.provider.name,
            input_summary={
                "strategy_id": normalized["strategy"]["id"],
                "source_module": normalized["strategy"]["source_module"],
                "signal_count": len(normalized["signals"]),
                "symbols": sorted(frames),
            },
            result_summary=result_summary,
        )
        get_analysis_snapshot_registry().register(snapshot)
        return {
            "engine": {"name": self.engine_name, "version": self.engine_version},
            "strategy": normalized["strategy"],
            "as_of": normalized["as_of"],
            "benchmark": normalized["benchmark"],
            "rules": {
                "signal_timing": "decision_date_close",
                "execution_timing": "next_trading_session_open",
                "holding_period_sessions": holding_period,
                "cost_bps_per_side": normalized["cost_bps_per_side"],
                "portfolio_weighting": "equal_weight",
                "split_method": "chronological_65_35",
            },
            "coverage": coverage,
            "train": train,
            "out_of_sample": out_of_sample,
            "trades": [self._public_trade(row) for row in trades],
            "failures": failures,
            "limitations": limitations,
            "verdict": "evidence_sufficient" if evidence_sufficient else "insufficient_evidence",
            "data_source": self.provider.name,
            "snapshot": snapshot,
        }

    def _validate_packet(self, packet: Mapping[str, Any]) -> dict[str, Any]:
        if not isinstance(packet, Mapping):
            raise StrategyValidationError("策略验证包必须是 JSON 对象")
        if packet.get("schema_version") != self.schema_version:
            raise StrategyValidationError(f"schema_version 必须是 {self.schema_version}")
        strategy = packet.get("strategy")
        if not isinstance(strategy, Mapping):
            raise StrategyValidationError("strategy 必须是对象")
        source_module = str(strategy.get("source_module") or "")
        if source_module not in self.supported_sources:
            raise StrategyValidationError("source_module 仅支持 stock-candidates、czsc、rotation")
        strategy_id = str(strategy.get("id") or "").strip()
        if not strategy_id:
            raise StrategyValidationError("strategy.id 不能为空")
        benchmark = str(packet.get("benchmark") or "").strip().upper()
        if not benchmark.isdigit() or len(benchmark) != 6:
            raise StrategyValidationError("benchmark 必须是 6 位代码")
        try:
            as_of = normalize_as_of(packet.get("as_of"), reject_future=True)
        except ValueError as exc:
            raise StrategyValidationError(str(exc)) from exc
        if not as_of:
            raise StrategyValidationError("as_of 不能为空")
        try:
            holding_period = int(packet.get("holding_period_sessions"))
            cost_bps = int(packet.get("cost_bps_per_side"))
        except (TypeError, ValueError) as exc:
            raise StrategyValidationError("持有周期与成本必须是整数") from exc
        if not 1 <= holding_period <= 60:
            raise StrategyValidationError("holding_period_sessions 必须在 1 到 60 之间")
        if not 0 <= cost_bps <= 100:
            raise StrategyValidationError("cost_bps_per_side 必须在 0 到 100 之间")
        raw_signals = packet.get("signals")
        if not isinstance(raw_signals, list) or not 2 <= len(raw_signals) <= 200:
            raise StrategyValidationError("signals 数量必须在 2 到 200 之间")
        signals = []
        previous_date = None
        for raw in raw_signals:
            if not isinstance(raw, Mapping):
                raise StrategyValidationError("每条 signal 必须是对象")
            try:
                decision_date = normalize_as_of(raw.get("decision_date"))
            except ValueError as exc:
                raise StrategyValidationError(str(exc)) from exc
            if not decision_date:
                raise StrategyValidationError("signal.decision_date 不能为空")
            if previous_date and decision_date <= previous_date:
                raise StrategyValidationError("决策日期必须严格递增且不能重复")
            if decision_date > as_of:
                raise StrategyValidationError("决策日期不能晚于 as_of")
            symbols = raw.get("symbols")
            if not isinstance(symbols, list) or not 1 <= len(symbols) <= 20:
                raise StrategyValidationError("每条 signal 必须包含 1 到 20 个 symbols")
            normalized_symbols = []
            for symbol in symbols:
                code = str(symbol or "").strip().upper().split(".")[0]
                if not code.isdigit() or len(code) != 6:
                    raise StrategyValidationError("signal symbols 必须是 6 位代码")
                if code not in normalized_symbols:
                    normalized_symbols.append(code)
            signals.append({"decision_date": decision_date, "symbols": normalized_symbols})
            previous_date = decision_date
        return {
            "strategy": {"id": strategy_id, "name": str(strategy.get("name") or strategy_id), "source_module": source_module},
            "as_of": as_of,
            "benchmark": benchmark,
            "holding_period_sessions": holding_period,
            "cost_bps_per_side": cost_bps,
            "signals": signals,
        }

    def _load_frame(self, symbol: str, as_of: str) -> pd.DataFrame:
        try:
            frame = self.provider.get_kline(symbol, "daily", self.request_limit, as_of)
        except Exception as exc:  # noqa: BLE001
            raise MarketDataError(f"{symbol} 历史行情不可用: {exc}") from exc
        frame = frame.sort_values("date").drop_duplicates("date", keep="last").reset_index(drop=True)
        if len(frame) < 4:
            raise MarketDataError(f"{symbol} 历史行情不足 4 根")
        return frame

    def _execute(self, packet, benchmark_frame, frames):
        trades = []
        failures = []
        for signal in packet["signals"]:
            decision_date = pd.Timestamp(signal["decision_date"])
            symbol_returns = []
            execution = None
            missing = []
            for symbol in signal["symbols"]:
                resolved = self._execution_window(frames[symbol], decision_date, packet["holding_period_sessions"])
                if resolved is None:
                    missing.append(symbol)
                    continue
                entry_date, exit_date, entry_price, exit_price = resolved
                execution = execution or (entry_date, exit_date)
                if execution != (entry_date, exit_date):
                    missing.append(symbol)
                    continue
                symbol_returns.append(exit_price / entry_price - 1)
            benchmark_execution = self._execution_window(benchmark_frame, decision_date, packet["holding_period_sessions"])
            if missing or not symbol_returns or benchmark_execution is None or execution is None:
                failures.append({"decision_date": signal["decision_date"], "symbols": signal["symbols"], "reason": "execution_window_unavailable", "missing_symbols": missing})
                continue
            benchmark_entry_date, benchmark_exit_date, benchmark_entry, benchmark_exit = benchmark_execution
            if execution != (benchmark_entry_date, benchmark_exit_date):
                failures.append({"decision_date": signal["decision_date"], "symbols": signal["symbols"], "reason": "benchmark_calendar_mismatch", "missing_symbols": []})
                continue
            gross = float(np.mean(symbol_returns))
            cost = round_trip_cost(packet["cost_bps_per_side"])
            benchmark_return = benchmark_exit / benchmark_entry - 1
            trades.append({
                "decision_date": signal["decision_date"],
                "entry_date": execution[0].strftime("%Y-%m-%d"),
                "exit_date": execution[1].strftime("%Y-%m-%d"),
                "symbols": signal["symbols"],
                "gross_return": gross,
                "transaction_cost": cost,
                "net_return": gross - cost,
                "benchmark_return": benchmark_return,
            })
        return trades, failures

    @staticmethod
    def _execution_window(frame: pd.DataFrame, decision_date: pd.Timestamp, holding_period: int):
        return resolve_next_open_window(
            frame,
            decision_date=decision_date,
            holding_period_sessions=holding_period,
        )

    @staticmethod
    def _public_trade(row: Mapping[str, Any]) -> dict[str, Any]:
        return {
            "decision_date": row["decision_date"],
            "entry_date": row["entry_date"],
            "exit_date": row["exit_date"],
            "symbols": list(row["symbols"]),
            "gross_return_pct": _round(float(row["gross_return"]) * 100),
            "transaction_cost_pct": _round(float(row["transaction_cost"]) * 100),
            "net_return_pct": _round(float(row["net_return"]) * 100),
            "benchmark_return_pct": _round(float(row["benchmark_return"]) * 100),
        }
