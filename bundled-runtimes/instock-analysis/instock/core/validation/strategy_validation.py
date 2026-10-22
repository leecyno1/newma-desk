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
from instock.core.validation.execution import audit_open_bar, resolve_next_open_window, round_trip_cost, valid_execution_price
from instock.core.validation.capital_book import simulate_sleeves


class StrategyValidationError(ValueError):
    """Raised when a validation packet violates the point-in-time contract."""


def _round(value: float, digits: int = 4) -> float:
    return round_metric(value, digits)


def _metrics(trades: Sequence[Mapping[str, Any]], holding_period: int) -> dict[str, Any]:
    return calculate_return_metrics(trades, period_sessions=holding_period)


def _segment_metrics(rows, holding_period):
    """Separate independent signal outcomes from an investable capital path."""
    resolved = [row for row in rows if row["execution_state"] == "resolved"]
    last_exit = None
    overlap_dates = []
    for row in rows:
        if row["entry_index"] is None or row["exit_index"] is None:
            continue
        if last_exit is not None and row["entry_index"] < last_exit:
            overlap_dates.append(row["decision_date"])
        last_exit = max(last_exit or 0, row["exit_index"])
    state = ("unavailable" if not rows else "incomplete" if len(resolved) < len(rows)
             else "overlapping" if overlap_dates else "complete")
    result = _metrics(resolved if state == "complete" else [], holding_period)
    result["trades"] = len(resolved)
    idle_sessions = None
    if state == "complete":
        span = rows[-1]["exit_index"] - rows[0]["entry_index"]
        idle_sessions = span - len(rows) * holding_period
        total = float(np.prod([1 + row["net_return"] for row in rows]) - 1)
        result["annualized_return_pct"] = _round(((1 + total) ** (252 / span) - 1) * 100) if total > -1 else -100.0
        if idle_sessions:
            # Irregular holding-window returns are not equally spaced daily
            # observations. Do not annualize their dispersion as if contiguous.
            for key in ("annualized_volatility_pct", "sharpe", "information_ratio"):
                result[key] = None
    return {
        **result,
        "planned_signals": len(rows), "unresolved_signals": len(rows) - len(resolved),
        "portfolio_state": state, "overlap_decision_dates": overlap_dates,
        "idle_sessions": idle_sessions,
        "signal_diagnostics": {
            "samples": len(resolved), "expected_samples": len(rows),
            "sample_policy": "resolved_signals_only_not_portfolio_or_independent_trials",
            "mean_return_pct": _round(np.mean([row["net_return"] for row in resolved]) * 100) if resolved else None,
            "mean_excess_pct": _round(np.mean([row["net_return"] - row["benchmark_return"] for row in resolved]) * 100) if resolved else None,
            "win_rate_pct": _round(np.mean([row["net_return"] > 0 for row in resolved]) * 100) if resolved else None,
            "beat_benchmark_rate_pct": _round(np.mean([row["net_return"] > row["benchmark_return"] for row in resolved]) * 100) if resolved else None,
        },
    }


class StrategyValidationEngine:
    engine_name = "instock-strategy-validation"
    engine_version = "1.6.0"
    schema_version = "instock-strategy-validation-packet-v1"
    supported_sources = {"stock-candidates", "czsc", "rotation"}
    request_limit = 800

    def __init__(self, provider: MarketDataProvider):
        self.provider = provider

    def validate(self, packet: Mapping[str, Any]) -> dict[str, Any]:
        normalized = self._validate_packet(packet)
        calendar = self.provider.get_trading_calendar(normalized["signals"][0]["decision_date"], normalized["as_of"])
        if (calendar.get("status") != "ready" or calendar.get("start") != normalized["signals"][0]["decision_date"]
                or calendar.get("end") != normalized["as_of"] or calendar.get("exchange") != "SSE"):
            raise MarketDataError("独立交易日历未完整覆盖验证区间")
        sessions = pd.DatetimeIndex(pd.to_datetime(calendar["sessions"]))
        if (not sessions.is_unique or not sessions.is_monotonic_increasing or sessions.hasnans
                or any(day < pd.Timestamp(calendar["start"]) or day > pd.Timestamp(calendar["end"]) for day in sessions)):
            raise MarketDataError("独立交易日历日期无效")
        benchmark_frame = self._load_frame(normalized["benchmark"], normalized["as_of"])
        frames = {}
        for symbol in sorted({symbol for signal in normalized["signals"] for symbol in signal["symbols"]}):
            try:
                frames[symbol] = self._load_frame(symbol, normalized["as_of"])
            except MarketDataError:
                # One unavailable constituent does not erase the submitted ledger.
                frames[symbol] = pd.DataFrame()
        execution_limits, limit_feeds = {}, []
        for symbol in frames:
            try:
                loader = getattr(self.provider, "get_execution_prices", None)
                feed = (loader(symbol, calendar["start"], calendar["end"]) if loader else
                        {"status": "unavailable", "reason": "当前数据源尚未接入历史限价"})
            except MarketDataError:
                feed = {"status": "unavailable", "reason": "历史限价请求失败，未用复权行情替代"}
            execution_limits[symbol] = {pd.Timestamp(row["date"]): row for row in feed.get("rows", [])} if feed.get("status") in {"ready", "partial"} else {}
            limit_feeds.append({"symbol": symbol, **{key: feed.get(key) for key in ("status", "reason", "feeds")}})
        trades, failures = self._execute(normalized, benchmark_frame, frames, sessions, execution_limits)
        limit_checks = [check for row in trades for check in row["price_limit_checks"]]
        limit_summary = {
            "policy": "unadjusted_open_vs_same_day_limits_no_adverse_side_fill_assumed",
            "dated_legs": len(limit_checks),
            "paired_legs": sum(check["state"] != "unverified" for check in limit_checks),
            "adverse_legs": sum(check["state"] == "adverse" for check in limit_checks),
            "unverified_legs": sum(check["state"] == "unverified" for check in limit_checks),
            "feeds": limit_feeds,
        }
        split_at = max(1, int(len(normalized["signals"]) * 0.65))
        split_date = normalized["signals"][split_at]["decision_date"]
        for row in trades:
            row["partition"] = ("out_of_sample" if row["decision_date"] >= split_date else
                                "purged" if row["exit_date"] is None or row["exit_date"] > split_date else "train")
        train_trades = [row for row in trades if row["partition"] == "train"]
        test_trades = [row for row in trades if row["partition"] == "out_of_sample"]
        purged = [row["decision_date"] for row in trades if row["partition"] == "purged"]
        holding_period = normalized["holding_period_sessions"]
        train = _segment_metrics(train_trades, holding_period)
        out_of_sample = _segment_metrics(test_trades, holding_period)
        capital = None
        if "capital_model" in normalized:
            capital = {
                **normalized["capital_model"],
                "partition_policy": "train_excludes_purged_signals_oos_restarts_equal_capital_no_carry",
                "rules": {
                    "funding": "equal_initial_sleeves_reinvest_own_proceeds_no_transfer_no_leverage",
                    "capacity": "reserve_by_planned_dates_skip_when_full_exit_before_entry",
                    "basket": "equal_entry_notional_fractional_units_no_rebalancing",
                    "cost": "buy_cost_included_in_budget_sell_cost_on_exit_value",
                    "sampling": "daily_open_before_and_after_trades_and_close_not_intraday_extremes",
                    "benchmark": "gross_buy_and_hold_from_first_entry_open_to_last_valuation_close",
                },
                **{name: simulate_sleeves(partition, frames, benchmark_frame, sessions,
                                         slots=normalized["capital_model"]["slots"],
                                         cost_bps=normalized["cost_bps_per_side"], execution_limits=execution_limits)
                   for name, partition in (("train", train_trades), ("out_of_sample", test_trades))},
            }
        resolved_count = len(trades) - len(failures)
        coverage_ratio = resolved_count / len(normalized["signals"])
        evidence_sufficient = (resolved_count >= 6 and out_of_sample["trades"] >= 2
                               and train["portfolio_state"] == "complete"
                               and out_of_sample["portfolio_state"] == "complete"
                               and not failures)
        if capital:
            evidence_sufficient = (resolved_count >= 6 and capital["out_of_sample"]["allocated_signals"] >= 2
                                   and all(capital[key]["state"] == "complete" and capital[key]["benchmark_state"] == "complete"
                                           and not capital[key]["open_sleeves"] for key in ("train", "out_of_sample"))
                                   and not failures)
        evidence_sufficient = evidence_sufficient and not limit_summary["unverified_legs"] and not limit_summary["adverse_legs"]
        coverage = {
            "input_signals": len(normalized["signals"]),
            "executed_signals": resolved_count,
            "failed_signals": len(failures),
            "ratio": _round(coverage_ratio),
            "evidence_sufficient": evidence_sufficient,
        }
        limitations = [
            "fixed_holding_period_does_not_model_intraday_stops",
            "latest_800_bar_data_boundary",
            "signals_must_be_point_in_time_and_are_not_reconstructed_by_this_module",
            "empty_statistics_are_null_ratios_require_two_samples_and_nonzero_dispersion",
            "sharpe_assumes_zero_risk_free_rate_and_population_dispersion",
            "fixed_sleeves_are_explicit_hypothetical_capital_not_actual_account" if capital else "overlapping_signals_are_diagnostics_not_a_capital_allocation_model",
            "nonoverlapping_portfolio_assumes_idle_cash_zero_return",
            "capital_path_samples_open_and_close_not_intraday_extremes" if capital else "endpoint_drawdown_is_not_daily_or_intraday_drawdown",
            "resolved_only_signal_statistics_may_have_selection_bias_and_dependence",
            "diagnostic_readiness_is_not_strategy_profitability_or_deployment_approval",
            "sse_calendar_only_not_overseas_underlying_market_calendar",
            "calendar_is_current_source_history_not_point_in_time_announcements",
            "positive_daily_volume_is_ex_post_evidence_not_open_auction_fill_or_capacity",
            "price_limits_use_separate_unadjusted_open_never_adjusted_return_prices",
            "adverse_price_limit_open_is_unresolved_not_proof_of_zero_actual_fills",
            "suspension_status_auction_depth_and_order_queue_not_verified",
        ]
        if limit_summary["unverified_legs"]:
            limitations.append("historical_price_limit_pairs_incomplete_returns_are_theoretical")
        if not evidence_sufficient:
            limitations.append("insufficient_out_of_sample_evidence")
        if failures:
            limitations.append("some_signals_could_not_be_executed")
        if capital:
            limitations.extend(["sleeve_nav_uses_fractional_units_no_lot_liquidity_limit_or_tax_model",
                                "train_and_oos_are_independent_capital_books_not_continuous_account",
                                "missing_marks_break_risk_path_missing_execution_propagates_unknown_capital",
                                "signal_diagnostics_use_simple_roundtrip_cost_sleeves_use_actual_buy_sell_notional"])
        execution_issues = [issue for row in trades for issue in row["execution_issues"]]
        planned_legs = sum(len(row["symbols"]) * 2 for row in trades)
        dated_legs = sum(len(row["symbols"]) * sum(row[key] is not None for key in ("entry_date", "exit_date"))
                         for row in trades)
        audit = {"split_decision_date": split_date, "split_signal_index": split_at,
                 "train_signals": len(train_trades), "out_of_sample_signals": len(test_trades),
                 "purged_decision_dates": purged,
                 "calendar_policy": "independent_exchange_calendar_exact_dates",
                 "calendar": {key: calendar.get(key) for key in ("source", "exchange", "start", "end", "receivedAt", "coverage")},
                 "execution_evidence": {
                     "policy": "positive_daily_volume_required_for_open_price_diagnostic",
                     "scope": "all_planned_asset_legs_not_capital_fills_including_purged_and_capacity_skips",
                     "planned_legs": planned_legs, "dated_legs": dated_legs,
                     "price_volume_verified_legs": dated_legs - sum(issue["reason"] in {"missing_open", "missing_volume", "zero_volume"} for issue in execution_issues),
                     "zero_volume_legs": sum(issue["reason"] == "zero_volume" for issue in execution_issues),
                     "missing_evidence_legs": sum(issue["reason"] in {"missing_open", "missing_volume"} for issue in execution_issues),
                     "pending_legs": planned_legs - dated_legs,
                     "fill_guaranteed": False,
                     "price_limits": limit_summary,
                     "unverified_checks": (["historical_price_limits"] if limit_summary["unverified_legs"] else []) + ["suspension_status", "opening_auction_liquidity",
                                           "order_queue", "lot_size", "volume_participation"],
                 },
                 "split_policy": "original_signal_order_65_35_purge_train_labels_crossing_oos"}

        result_summary = {
            "strategy_id": normalized["strategy"]["id"],
            "source_module": normalized["strategy"]["source_module"],
            "coverage": coverage,
            "out_of_sample": out_of_sample,
            "validation_audit": audit,
            **({"capital_backtest": {key: {field: value for field, value in capital[key].items()
                                          if field not in {"curve", "ledger", "issues"}}
                                     for key in ("train", "out_of_sample")}} if capital else {}),
        }
        snapshot = build_analysis_snapshot(
            analysis_name=self.engine_name,
            analysis_version=self.engine_version,
            parameters={
                "benchmark": normalized["benchmark"],
                "asOf": normalized["as_of"],
                "holdingPeriodSessions": holding_period,
                "costBpsPerSide": normalized["cost_bps_per_side"],
                **({"capitalModel": normalized["capital_model"]} if capital else {}),
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
            "input_packet": {"schema_version": self.schema_version, **normalized},
            **({"capital_backtest": capital} if capital else {}),
            "strategy": normalized["strategy"],
            "as_of": normalized["as_of"],
            "benchmark": normalized["benchmark"],
            "rules": {
                "signal_timing": "decision_date_close",
                "execution_timing": "next_trading_session_open",
                "holding_period_sessions": holding_period,
                "cost_bps_per_side": normalized["cost_bps_per_side"],
                "portfolio_weighting": "equal_weight",
                "split_method": "original_signals_65_35_with_label_purge",
                "execution_calendar": "independent_exchange_calendar_exact_dates",
                "overlap_policy": "explicit_fixed_sleeves_separate_from_signal_diagnostics" if capital else "signal_diagnostics_only_no_portfolio_compounding",
                "idle_cash_return": 0.0,
            },
            "coverage": coverage,
            "validation_audit": audit,
            "train": train,
            "out_of_sample": out_of_sample,
            "trades": [self._public_trade(row) for row in trades],
            "failures": failures,
            "limitations": limitations,
            "verdict": "diagnostic_ready" if evidence_sufficient else "insufficient_evidence",
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
        capital = packet.get("capital_model")
        if "capital_model" in packet:
            if (not isinstance(capital, Mapping) or capital.get("mode") != "fixed_sleeves"
                    or type(capital.get("slots")) is not int or not 1 <= capital["slots"] <= 20):
                raise StrategyValidationError("capital_model 须为 fixed_sleeves，slots 为1—20的整数")
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
            **({"capital_model": {"mode": "fixed_sleeves", "slots": capital["slots"]}} if capital else {}),
        }

    def _load_frame(self, symbol: str, as_of: str) -> pd.DataFrame:
        try:
            frame = self.provider.get_kline(symbol, "daily", self.request_limit, as_of)
        except Exception as exc:  # noqa: BLE001
            raise MarketDataError(f"{symbol} 历史行情不可用: {exc}") from exc
        frame = frame.sort_values("date").drop_duplicates("date", keep="last").reset_index(drop=True)
        frame = frame[pd.to_datetime(frame["date"]) <= pd.Timestamp(as_of)].reset_index(drop=True)
        if len(frame) < 4:
            raise MarketDataError(f"{symbol} 历史行情不足 4 根")
        return frame

    def _execute(self, packet, benchmark_frame, frames, dates, execution_limits):
        trades, failures = [], []
        benchmark_prices = {pd.Timestamp(row["date"]): valid_execution_price(row["open"]) for row in benchmark_frame.to_dict("records")}
        prices = {code: {pd.Timestamp(row["date"]): row
                         for row in frame.to_dict("records")} for code, frame in frames.items()}
        for signal in packet["signals"]:
            decision_date = pd.Timestamp(signal["decision_date"])
            entry_index = int(dates.searchsorted(decision_date, side="right"))
            exit_index = entry_index + packet["holding_period_sessions"]
            entry = dates[entry_index] if entry_index < len(dates) else None
            exit_date = dates[exit_index] if entry is not None and exit_index < len(dates) else None
            missing, returns, execution_issues, price_limit_checks = [], [], [], []
            evidence = {}
            for side, date in (("buy", entry), ("sell", exit_date)):
                if date is not None:
                    for symbol in signal["symbols"]:
                        bar = audit_open_bar(prices[symbol].get(date, {}),
                                             limit=execution_limits.get(symbol, {}).get(date), side=side)
                        price_limit_checks.append({"symbol": symbol, "date": date.strftime("%Y-%m-%d"),
                                                   "side": side, **bar["limit_check"]})
                        evidence[(symbol, side)] = bar
                        if bar["reason"]:
                            execution_issues.append({"symbol": symbol, "date": date.strftime("%Y-%m-%d"),
                                                     "side": side, "reason": bar["reason"]})
            reason, benchmark_return, gross, cost = None, None, None, None
            if entry is None or exit_date is None:
                reason = "holding_window_incomplete"
            else:
                for symbol in signal["symbols"]:
                    first, last = evidence[(symbol, "buy")]["price"], evidence[(symbol, "sell")]["price"]
                    if first is None or last is None:
                        missing.append(symbol)
                    else:
                        returns.append(last / first - 1)
                first = benchmark_prices.get(entry)
                last = benchmark_prices.get(exit_date)
                if first is not None and last is not None:
                    benchmark_return = last / first - 1
                if not missing:
                    gross = float(np.mean(returns))
                    cost = round_trip_cost(packet["cost_bps_per_side"])
                reason = ("missing_asset_open" if any(issue["reason"] == "missing_open" for issue in execution_issues)
                          else "unverified_asset_volume" if any(issue["reason"] in {"missing_volume", "zero_volume"} for issue in execution_issues)
                          else "adverse_price_limit" if missing
                          else "missing_benchmark_open" if benchmark_return is None else None)
            row = {
                "decision_date": signal["decision_date"],
                "entry_date": entry.strftime("%Y-%m-%d") if entry is not None else None,
                "exit_date": exit_date.strftime("%Y-%m-%d") if exit_date is not None else None,
                "entry_index": entry_index if entry is not None else None,
                "exit_index": exit_index if exit_date is not None else None,
                "symbols": signal["symbols"],
                "execution_state": "unresolved" if reason else "resolved",
                "reason": reason, "missing_symbols": missing, "execution_issues": execution_issues,
                "price_limit_checks": price_limit_checks,
                "gross_return": gross,
                "transaction_cost": cost,
                "net_return": gross - cost if gross is not None else None,
                "benchmark_return": benchmark_return,
            }
            trades.append(row)
            if reason:
                failures.append({key: row[key] for key in ("decision_date", "symbols", "reason", "missing_symbols", "entry_date", "exit_date", "execution_issues")})
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
            "execution_state": row["execution_state"], "reason": row["reason"],
            "missing_symbols": row["missing_symbols"], "partition": row["partition"],
            "execution_issues": row["execution_issues"],
            "price_limit_checks": row["price_limit_checks"],
            **{public: _round(row[key] * 100) if row[key] is not None else None
               for public, key in (("gross_return_pct", "gross_return"), ("transaction_cost_pct", "transaction_cost"),
                                   ("net_return_pct", "net_return"), ("benchmark_return_pct", "benchmark_return"))},
        }
