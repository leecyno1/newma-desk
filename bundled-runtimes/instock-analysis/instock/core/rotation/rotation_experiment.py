#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Point-in-time robustness experiments for the project-local ETF rotation model."""

from __future__ import annotations

import math
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from typing import Any, Dict, Mapping, Optional, Sequence

import numpy as np
import pandas as pd

from instock.core.analysis_snapshot import build_analysis_snapshot, normalize_as_of
from instock.core.market_data_provider import MarketDataError, MarketDataProvider
from instock.core.rotation.etf_universe import DEFAULT_SECTOR_ETFS, SectorETF
from instock.core.rotation.rotation_engine import (
    ROTATION_WEIGHT_PROFILES,
    RotationEngine,
    _round,
)
from instock.core.validation.metrics import calculate_rotation_metrics
from instock.core.validation.execution import round_trip_cost, valid_execution_price
from instock.core.rotation.rotation_risk import daily_rotation_risk
from instock.core.rotation.calendar import align_benchmark_calendar
from instock.core.rotation.execution_audit import RotationExecutionAudit, execution_summary


ROTATION_CONFIRMATION_POLICIES: Dict[str, Dict[str, Any]] = {
    "raw": {
        "label": "原始排序",
        "description": "沿用综合分与前三缓冲，不使用确认层过滤。",
    },
    "exclude_overheated": {
        "label": "排除过热",
        "description": "剔除确认层标记为过热的 ETF，再按综合分与持仓缓冲选择。",
    },
    "confirmed_only": {
        "label": "强确认才持有",
        "description": "只持有确认领先或加速上行的 ETF，没有合格候选时保持现金。",
    },
}


def _metrics(trades: Sequence[Mapping[str, Any]], rebalance_days: int) -> Dict[str, Any]:
    resolved = sum(row.get("net_return") is not None and row.get("benchmark_return") is not None for row in trades)
    if resolved < len(trades):
        # Never compound around unresolved executions as though those periods
        # were cash. The planned decisions remain in the ledger for inspection.
        result = {key: None for key in calculate_rotation_metrics([], period_sessions=rebalance_days)}
        result["trades"] = len(trades)
    else:
        result = calculate_rotation_metrics(trades, period_sessions=rebalance_days)
    return {**result, "execution_state": "unavailable" if not trades else "complete" if resolved == len(trades) else "incomplete",
            "execution_evidence": execution_summary(trades),
            "resolved_periods": resolved, "unresolved_periods": len(trades) - resolved}


def _difference(left, right, digits=2):
    return _round(left - right, digits) if left is not None and right is not None else None


def _unresolved_period(signal_date, entry_date, exit_date, benchmark_return, reason):
    """Keep the scheduled period; an unknown decision is not a cash decision."""
    return {
        "signal_date": pd.Timestamp(signal_date).strftime("%Y-%m-%d"),
        "entry_date": pd.Timestamp(entry_date).strftime("%Y-%m-%d"),
        "exit_date": pd.Timestamp(exit_date).strftime("%Y-%m-%d"),
        "symbol": None, "name": "持仓待核验", "industry": None,
        "signal_code": None, "signal_name": None, "signal_mode": "unresolved",
        "score": None, "switched": None, "transaction_cost": None,
        "gross_return": None, "net_return": None,
        "benchmark_return": benchmark_return, "equal_weight_return": None,
        "decision_issue": reason,
        **{"current_leader_" + key: None for key in (
            "symbol", "name", "industry", "signal_code", "signal_name",
            "signal_mode", "score", "gross_return")},
    }


class RotationExperiment:
    """Stress-test rotation parameters using only data available at each signal date."""

    engine_name = "instock-rotation-experiment"
    engine_version = "2.9.0"
    request_limit = 800
    windows = (40, 60, 120)
    supported_rebalances = (5, 10, 20)
    supported_cost_bps = (10, 25, 50)
    switch_score_gap = RotationEngine.shadow_switch_score_gap
    hold_rank_limit = RotationEngine.shadow_hold_rank_limit
    minimum_cross_section_coverage = 0.75
    evidence_coverage_threshold = 0.90
    primary_prediction_horizon = 10
    prediction_sampling_sessions = 5
    high_confidence_train_quantile = 0.60

    def __init__(
        self,
        provider: MarketDataProvider,
        universe: Sequence[SectorETF] = DEFAULT_SECTOR_ETFS,
        max_workers: int = 8,
    ):
        self.provider = provider
        self.universe = tuple(universe)
        self.max_workers = max(1, min(int(max_workers), 16))

    def _get_kline(self, symbol: str, as_of: Optional[str]) -> pd.DataFrame:
        if as_of:
            return self.provider.get_kline(symbol, "daily", self.request_limit, as_of)
        return self.provider.get_kline(symbol, "daily", self.request_limit)

    def _get_signal_kline(self, symbol: str, as_of: Optional[str]) -> pd.DataFrame:
        if as_of:
            return self.provider.get_signal_kline(
                symbol, "daily", self.request_limit, as_of
            )
        return self.provider.get_signal_kline(symbol, "daily", self.request_limit)

    @classmethod
    def _minimum_cross_section_size(cls, universe_size: int) -> int:
        size = max(int(universe_size), 0)
        if size == 0:
            return 0
        return min(size, max(4, math.ceil(size * cls.minimum_cross_section_coverage)))

    @staticmethod
    def _execution_price(frame: pd.DataFrame, date: pd.Timestamp) -> Optional[float]:
        row = frame[pd.to_datetime(frame["date"]) == pd.Timestamp(date)]
        if row.empty:
            return None
        value = float(row["open"].iloc[-1])
        return value if math.isfinite(value) and value > 0 else None

    @staticmethod
    def _valid_execution_price(value: Any) -> Optional[float]:
        return valid_execution_price(value)

    @classmethod
    def _forward_return(cls, prepared, entry_date, exit_date) -> Optional[float]:
        """Label an already-frozen candidate; missing labels never alter selection."""
        _, dates, opens = prepared
        values = []
        for date in (entry_date, exit_date):
            position = int(dates.searchsorted(date, side="left"))
            if position >= len(dates) or dates[position] != date:
                return None
            value = cls._valid_execution_price(opens[position])
            if value is None:
                return None
            values.append(value)
        return values[1] / values[0] - 1

    @classmethod
    def _select_with_buffer(
        cls,
        rankings: Sequence[Mapping[str, Any]],
        held_symbol: Optional[str],
    ) -> Mapping[str, Any]:
        return RotationEngine._select_with_buffer(rankings, held_symbol)

    @classmethod
    def _select_confirmation_policy(
        cls,
        rankings: Sequence[Mapping[str, Any]],
        held_symbol: Optional[str],
        policy: str,
    ) -> Optional[Mapping[str, Any]]:
        if policy == "raw":
            return cls._select_with_buffer(rankings, held_symbol)
        if policy == "exclude_overheated":
            eligible = [row for row in rankings if not row.get("overheated")]
        elif policy == "confirmed_only":
            eligible = [
                row for row in rankings
                if row.get("rotation_signal") in {"确认领先", "加速上行"}
            ]
        else:
            raise ValueError(f"未知确认策略: {policy}")
        if not eligible:
            return None
        reranked = []
        for index, row in enumerate(eligible, start=1):
            item = dict(row)
            item["source_rank"] = row["rank"]
            item["rank"] = index
            reranked.append(item)
        return cls._select_with_buffer(reranked, held_symbol)

    @classmethod
    def _decision_from_possible_holdings(cls, rankings, held_symbols, policy="raw"):
        """Rejoin after a data gap only when every possible prior holding agrees."""
        choices = [(held, cls._select_confirmation_policy(rankings, held, policy))
                   for held in held_symbols]
        symbols = {row["code"] if row else None for _, row in choices}
        switches = {held != (row["code"] if row else None) for held, row in choices}
        selected = choices[0][1] if len(symbols) == 1 else None
        switched = next(iter(switches)) if len(switches) == 1 else None
        return selected, symbols, switched

    def _load_frames(
        self,
        benchmark: str,
        as_of: Optional[str],
    ) -> tuple[
        pd.DataFrame,
        Dict[str, pd.DataFrame],
        Dict[str, pd.DataFrame],
        list[Dict[str, str]],
        list[Dict[str, str]],
    ]:
        try:
            benchmark_frame = self._get_kline(benchmark, as_of)
        except Exception as exc:
            raise MarketDataError(f"基准 {benchmark} 历史行情不可用: {exc}") from exc
        failures: list[Dict[str, str]] = []
        trade_frames: Dict[str, pd.DataFrame] = {}
        with ThreadPoolExecutor(max_workers=min(self.max_workers, len(self.universe))) as pool:
            future_map = {pool.submit(self._get_kline, item.code, as_of): item for item in self.universe}
            for future in as_completed(future_map):
                item = future_map[future]
                try:
                    frame = future.result()
                    if len(frame) < 180:
                        raise MarketDataError(f"历史 K 线不足 180 根（实际 {len(frame)}）")
                    trade_frames[item.code] = frame.sort_values("date").drop_duplicates("date", keep="last").reset_index(drop=True)
                except Exception as exc:  # noqa: BLE001
                    failures.append({"code": item.code, "name": item.name, "error": str(exc)})
        minimum_symbols = self._minimum_cross_section_size(len(self.universe))
        if len(trade_frames) < minimum_symbols:
            raise MarketDataError(
                f"有效 ETF 仅 {len(trade_frames)}/{len(self.universe)} 个，"
                f"低于稳健性实验最低覆盖 {minimum_symbols} 个"
            )
        benchmark_frame = benchmark_frame.sort_values("date").drop_duplicates("date", keep="last").reset_index(drop=True)
        if len(benchmark_frame) < 260:
            raise MarketDataError(f"基准历史 K 线不足 260 根（实际 {len(benchmark_frame)}）")

        signal_failures: list[Dict[str, str]] = []
        signal_frames: Dict[str, pd.DataFrame] = {}
        signal_candidates = [
            item for item in self.universe
            if (
                item.code in trade_frames
                and item.has_industry_index_signal
                and self.provider.supports_signal_kline(item.resolved_signal_code)
            )
        ]
        loaded_signals: Dict[str, pd.DataFrame] = {}
        if signal_candidates:
            with ThreadPoolExecutor(max_workers=min(self.max_workers, len(signal_candidates))) as pool:
                future_map = {
                    pool.submit(self._get_signal_kline, item.resolved_signal_code, as_of): item
                    for item in signal_candidates
                }
                for future in as_completed(future_map):
                    item = future_map[future]
                    try:
                        frame = future.result()
                        if len(frame) < 180:
                            raise MarketDataError(
                                f"行业指数历史 K 线不足 180 根（实际 {len(frame)}）"
                            )
                        loaded_signals[item.code] = (
                            frame.sort_values("date")
                            .drop_duplicates("date", keep="last")
                            .reset_index(drop=True)
                        )
                    except Exception as exc:  # noqa: BLE001
                        signal_failures.append({
                            "etf_code": item.code,
                            "signal_code": item.resolved_signal_code,
                            "signal_name": item.resolved_signal_name,
                            "error": str(exc),
                        })
        for item in self.universe:
            trade_frame = trade_frames.get(item.code)
            if trade_frame is None:
                continue
            if item.has_industry_index_signal and item.code in loaded_signals:
                signal_frame = loaded_signals[item.code]
                signal_mode = "industry_index"
            else:
                signal_frame = trade_frame.copy()
                signal_mode = "etf_fallback" if item.has_industry_index_signal else "trade_asset"
            signal_frame.attrs.update({
                "rotation_signal_mode": signal_mode,
                "rotation_signal_code": (
                    item.resolved_signal_code if signal_mode == "industry_index" else item.code
                ),
                "rotation_signal_name": (
                    item.resolved_signal_name if signal_mode == "industry_index" else item.name
                ),
            })
            signal_frames[item.code] = signal_frame
        return benchmark_frame, trade_frames, signal_frames, failures, signal_failures

    def _calendar_frame(self, benchmark_frame, trade_frames, as_of):
        return align_benchmark_calendar(self.provider, benchmark_frame, trade_frames, as_of,
                                        limit=self.request_limit, minimum_sessions=260)

    _decision_benchmark_metrics = staticmethod(RotationEngine._decision_benchmark_metrics)

    def _variant_trades(
        self,
        *,
        benchmark_frame: pd.DataFrame,
        trade_frames: Mapping[str, pd.DataFrame],
        signal_frames: Mapping[str, pd.DataFrame],
        weights: Mapping[str, float],
        window: int,
        rebalance_days: int,
        cost_bps: int,
    ) -> list[Dict[str, Any]]:
        profile_key = "variant"
        return self._window_trade_sets(
            benchmark_frame=benchmark_frame,
            trade_frames=trade_frames,
            signal_frames=signal_frames,
            weight_profiles={profile_key: weights},
            window=window,
            rebalance_days=rebalance_days,
            cost_bps=cost_bps,
        )[profile_key]

    def _window_trade_sets(
        self,
        *,
        benchmark_frame: pd.DataFrame,
        trade_frames: Mapping[str, pd.DataFrame],
        signal_frames: Mapping[str, pd.DataFrame],
        weight_profiles: Mapping[str, Mapping[str, float]],
        window: int,
        rebalance_days: int,
        cost_bps: int,
    ) -> Dict[str, list[Dict[str, Any]]]:
        engines = {
            profile: RotationEngine(
                self.provider,
                universe=self.universe,
                max_workers=self.max_workers,
                weights=weights,
            )
            for profile, weights in weight_profiles.items()
        }
        metric_engine = next(iter(engines.values()))
        benchmark_dates = pd.DatetimeIndex(pd.to_datetime(benchmark_frame["date"]))
        benchmark_opens = benchmark_frame["open"].to_numpy()
        prepared_trades: Dict[str, tuple[pd.DataFrame, pd.DatetimeIndex, np.ndarray]] = {}
        for code, source in trade_frames.items():
            prepared_trades[code] = (
                source,
                pd.DatetimeIndex(pd.to_datetime(source["date"])),
                source["open"].to_numpy(),
            )
        prepared_signals: Dict[str, tuple[pd.DataFrame, pd.DatetimeIndex]] = {
            code: (source, pd.DatetimeIndex(pd.to_datetime(source["date"])))
            for code, source in signal_frames.items()
        }

        warmup = max(window + 5, 125)
        trade_sets: Dict[str, list[Dict[str, Any]]] = {profile: [] for profile in engines}
        held_symbols = {profile: {None} for profile in engines}
        for position in range(warmup, len(benchmark_dates) - rebalance_days - 1, rebalance_days):
            signal_date = benchmark_dates[position]
            entry_date = benchmark_dates[position + 1]
            exit_date = benchmark_dates[position + 1 + rebalance_days]
            benchmark_slice = benchmark_frame.iloc[:position + 1]
            benchmark_metrics = self._decision_benchmark_metrics(benchmark_slice, window)
            benchmark_entry = self._valid_execution_price(benchmark_opens[position + 1])
            benchmark_exit = self._valid_execution_price(benchmark_opens[position + 1 + rebalance_days])
            raw_rows = []
            forward_returns: Dict[str, Optional[float]] = {}
            period_returns = []
            for item in self.universe:
                if benchmark_metrics is None:
                    break
                prepared_trade = prepared_trades.get(item.code)
                prepared_signal = prepared_signals.get(item.code)
                if prepared_trade is None or prepared_signal is None:
                    continue
                trade_source, trade_dates, _ = prepared_trade
                signal_source, signal_dates = prepared_signal
                trade_slice_end = int(trade_dates.searchsorted(signal_date, side="right"))
                signal_slice_end = int(signal_dates.searchsorted(signal_date, side="right"))
                if trade_slice_end < window + 1 or signal_slice_end < window + 1:
                    continue
                trade_lag = position + 1 - int(
                    benchmark_dates[:position + 1].searchsorted(
                        trade_dates[trade_slice_end - 1], side="right"
                    )
                )
                signal_lag = position + 1 - int(
                    benchmark_dates[:position + 1].searchsorted(
                        signal_dates[signal_slice_end - 1], side="right"
                    )
                )
                if (
                    trade_lag > metric_engine.max_stale_sessions
                    or signal_lag > metric_engine.max_stale_sessions
                ):
                    continue
                trade_slice = trade_source.iloc[:trade_slice_end].copy()
                trade_slice.attrs.update(trade_source.attrs)
                trade_slice.attrs["data_lag_sessions"] = trade_lag
                signal_slice = signal_source.iloc[:signal_slice_end].copy()
                signal_slice.attrs.update(signal_source.attrs)
                signal_slice.attrs["signal_lag_sessions"] = signal_lag
                raw_rows.append(metric_engine._raw_metrics(
                    item,
                    signal_slice,
                    benchmark_metrics,
                    window,
                    [],
                    trade_frame=trade_slice,
                    signal_mode=str(
                        signal_source.attrs.get("rotation_signal_mode") or "trade_asset"
                    ),
                ))
                forward_returns[item.code] = self._forward_return(prepared_trade, entry_date, exit_date)
                period_returns.append(forward_returns[item.code])
            benchmark_return = benchmark_exit / benchmark_entry - 1 if benchmark_entry is not None and benchmark_exit is not None else None
            if len(raw_rows) < self._minimum_cross_section_size(len(self.universe)):
                for profile in engines:
                    trade_sets[profile].append(_unresolved_period(
                        signal_date, entry_date, exit_date, benchmark_return,
                        "missing_benchmark_signal" if benchmark_metrics is None else "insufficient_signal_coverage"))
                    held_symbols[profile] = {None, *(item.code for item in self.universe)}
                continue

            factor_frame = metric_engine._factor_frame(raw_rows)
            benchmark_return = benchmark_exit / benchmark_entry - 1 if benchmark_entry is not None and benchmark_exit is not None else None
            equal_weight_return = float(np.mean(period_returns)) if all(value is not None for value in period_returns) else None
            for profile, engine in engines.items():
                rankings = engine._score_factor_frame(factor_frame)
                leader = rankings[0]
                selected, possible, switched = self._decision_from_possible_holdings(rankings, held_symbols[profile])
                held_symbols[profile] = possible
                if len(possible) > 1:
                    pending = _unresolved_period(signal_date, entry_date, exit_date,
                                                 benchmark_return, "ambiguous_holding_state")
                    pending.update({"current_leader_" + key: leader[source] for key, source in (
                        ("symbol", "code"), ("name", "name"), ("industry", "industry"),
                        ("signal_code", "signal_code"), ("signal_name", "signal_name"),
                        ("signal_mode", "signal_mode"), ("score", "total_score"))})
                    pending["current_leader_gross_return"] = forward_returns[leader["code"]]
                    pending["equal_weight_return"] = equal_weight_return
                    trade_sets[profile].append(pending)
                    continue
                transaction_cost = round_trip_cost(cost_bps, executed=switched) if switched is not None else None
                gross_return = forward_returns[selected["code"]]
                net_return = gross_return - transaction_cost if gross_return is not None and transaction_cost is not None else None
                trade_sets[profile].append({
                    "signal_date": signal_date.strftime("%Y-%m-%d"),
                    "entry_date": entry_date.strftime("%Y-%m-%d"),
                    "exit_date": exit_date.strftime("%Y-%m-%d"),
                    "symbol": selected["code"],
                    "name": selected["name"],
                    "industry": selected["industry"],
                    "signal_code": selected["signal_code"],
                    "signal_name": selected["signal_name"],
                    "signal_mode": selected["signal_mode"],
                    "score": selected["total_score"],
                    "current_leader_symbol": leader["code"],
                    "current_leader_name": leader["name"],
                    "current_leader_industry": leader["industry"],
                    "current_leader_signal_code": leader["signal_code"],
                    "current_leader_signal_name": leader["signal_name"],
                    "current_leader_signal_mode": leader["signal_mode"],
                    "current_leader_score": leader["total_score"],
                    "current_leader_gross_return": forward_returns[leader["code"]],
                    "switched": switched,
                    "transaction_cost": transaction_cost,
                    "gross_return": gross_return,
                    "net_return": net_return,
                    "benchmark_return": benchmark_return,
                    "equal_weight_return": equal_weight_return,
                    **({"decision_issue": "uncertain_turnover"} if switched is None else {}),
                })
        return trade_sets

    @classmethod
    def _parameter_ensemble_trades(
        cls,
        trade_sets: Mapping[str, Sequence[Mapping[str, Any]]],
        *,
        cost_bps: int,
        vote_source: str = "buffered_selection",
    ) -> list[Dict[str, Any]]:
        """Equal-vote the fixed 3x3 parameter surface without fitting outcomes."""

        if vote_source not in {"buffered_selection", "current_leader"}:
            raise ValueError(f"未知参数集成投票口径: {vote_source}")

        variant_count = len(trade_sets)
        if not variant_count:
            return []
        majority_threshold = variant_count // 2 + 1
        by_date: Dict[str, list[tuple[str, Mapping[str, Any]]]] = defaultdict(list)
        for variant_id, rows in trade_sets.items():
            for row in rows:
                by_date[str(row["signal_date"])].append((variant_id, row))

        held_symbol: Optional[str] = None
        holding_known = True
        output: list[Dict[str, Any]] = []
        for signal_date in sorted(by_date):
            options = by_date[signal_date]
            symbol_key = "current_leader_symbol" if vote_source == "current_leader" else "symbol"
            if len(options) != variant_count or any(row.get(symbol_key) is None for _, row in options):
                reference = options[0][1]
                pending = _unresolved_period(signal_date, reference["entry_date"], reference["exit_date"],
                                             reference["benchmark_return"], "incomplete_parameter_votes")
                pending.update(variant_count=variant_count, vote_count=None, vote_share_pct=None,
                               high_confidence=None, vote_source=vote_source)
                output.append(pending)
                holding_known = False
                continue
            normalized_options = []
            for variant_id, row in options:
                if vote_source == "current_leader":
                    candidate = {
                        "symbol": str(row["current_leader_symbol"]),
                        "name": row["current_leader_name"],
                        "industry": row["current_leader_industry"],
                        "signal_code": row["current_leader_signal_code"],
                        "signal_name": row["current_leader_signal_name"],
                        "signal_mode": row["current_leader_signal_mode"],
                        "score": float(row["current_leader_score"]),
                        "gross_return": row["current_leader_gross_return"],
                    }
                else:
                    candidate = {
                        "symbol": str(row["symbol"]),
                        "name": row["name"],
                        "industry": row["industry"],
                        "signal_code": row["signal_code"],
                        "signal_name": row["signal_name"],
                        "signal_mode": row["signal_mode"],
                        "score": float(row["score"]),
                        "gross_return": row["gross_return"],
                    }
                normalized_options.append((variant_id, row, candidate))
            votes = Counter(candidate["symbol"] for _, _, candidate in normalized_options)
            average_scores = {
                symbol: float(np.mean([
                    candidate["score"]
                    for _, _, candidate in normalized_options
                    if candidate["symbol"] == symbol
                ]))
                for symbol in votes
            }
            selected_symbol = max(
                votes,
                key=lambda symbol: (votes[symbol], average_scores[symbol], symbol),
            )
            selected_variant, selected_row, selected_candidate = next(
                (variant_id, row, candidate)
                for variant_id, row, candidate in normalized_options
                if candidate["symbol"] == selected_symbol
            )
            switched = held_symbol != selected_symbol if holding_known else None
            transaction_cost = round_trip_cost(cost_bps, executed=switched) if switched is not None else None
            vote_count = int(votes[selected_symbol])
            item = dict(selected_row)
            item.update({
                "symbol": selected_symbol,
                "name": selected_candidate["name"],
                "industry": selected_candidate["industry"],
                "signal_code": selected_candidate["signal_code"],
                "signal_name": selected_candidate["signal_name"],
                "signal_mode": selected_candidate["signal_mode"],
                "score": selected_candidate["score"],
                "gross_return": selected_candidate["gross_return"],
                "selection_model": (
                    "equal_vote_3_profiles_x_3_windows_" + vote_source
                ),
                "vote_source": vote_source,
                "source_variant": selected_variant,
                "variant_count": variant_count,
                "vote_count": vote_count,
                "vote_share_pct": _round(vote_count / variant_count * 100),
                "majority_threshold": majority_threshold,
                "high_confidence": vote_count >= majority_threshold,
                "voters": sorted(
                    variant_id
                    for variant_id, _, candidate in normalized_options
                    if candidate["symbol"] == selected_symbol
                ),
                "switched": switched,
                "transaction_cost": transaction_cost,
                "net_return": selected_candidate["gross_return"] - transaction_cost if selected_candidate["gross_return"] is not None and transaction_cost is not None else None,
            })
            # A leader vote is independent of the buffered path copied above.
            item.pop("decision_issue", None)
            if not holding_known:
                item["decision_issue"] = "uncertain_turnover"
            output.append(item)
            held_symbol = selected_symbol
            holding_known = True
        return output

    @classmethod
    def _ensemble_signal_summary(
        cls,
        trades: Sequence[Mapping[str, Any]],
        *,
        high_confidence_only: bool,
    ) -> Dict[str, Any]:
        rows = [
            row for row in trades
            if not high_confidence_only or bool(row.get("high_confidence"))
        ]
        unclassified = sum("high_confidence" in row and row["high_confidence"] is None for row in trades) if high_confidence_only else 0
        unresolved = unclassified + sum(row.get("gross_return") is None or row.get("net_return") is None or row.get("benchmark_return") is None for row in rows)
        if unresolved:
            return {"samples": len(rows), "unresolved_samples": unresolved,
                    "gross_beat_benchmark_rate_pct": None, "gross_beat_benchmark_wilson_95_pct": None,
                    "net_beat_benchmark_rate_pct": None, "mean_gross_excess_pct": None,
                    "unclassified_periods": unclassified,
                    "selection_rate_pct": None if unclassified else _round(len(rows) / len(trades) * 100)}
        if not rows:
            return {"samples": 0, "gross_beat_benchmark_rate_pct": None,
                    "gross_beat_benchmark_wilson_95_pct": None,
                    "net_beat_benchmark_rate_pct": None, "mean_gross_excess_pct": None,
                    "selection_rate_pct": 0.0 if trades else None}
        gross_hits = sum(
            float(row["gross_return"]) > float(row["benchmark_return"])
            for row in rows
        )
        net_hits = sum(
            float(row["net_return"]) > float(row["benchmark_return"])
            for row in rows
        )
        low, high = cls._wilson_interval_pct(gross_hits, len(rows))
        return {
            "samples": len(rows),
            "gross_beat_benchmark_rate_pct": _round(
                gross_hits / len(rows) * 100 if rows else 0.0
            ),
            "gross_beat_benchmark_wilson_95_pct": [low, high],
            "net_beat_benchmark_rate_pct": _round(
                net_hits / len(rows) * 100 if rows else 0.0
            ),
            "mean_gross_excess_pct": _round(
                np.mean([
                    float(row["gross_return"]) - float(row["benchmark_return"])
                    for row in rows
                ]) * 100 if rows else 0.0
            ),
            "selection_rate_pct": _round(
                len(rows) / len(trades) * 100 if trades else 0.0
            ),
        }

    def _confirmation_trade_sets(
        self,
        *,
        benchmark_frame: pd.DataFrame,
        trade_frames: Mapping[str, pd.DataFrame],
        signal_frames: Mapping[str, pd.DataFrame],
        weights: Mapping[str, float],
        window: int,
        rebalance_days: int,
        cost_bps: int,
    ) -> Dict[str, list[Dict[str, Any]]]:
        """Compare confirmation filters on one training-selected score variant."""

        engine = RotationEngine(
            self.provider,
            universe=self.universe,
            max_workers=self.max_workers,
            weights=weights,
        )
        benchmark_dates = pd.DatetimeIndex(pd.to_datetime(benchmark_frame["date"]))
        benchmark_opens = benchmark_frame["open"].to_numpy()
        prepared_trades: Dict[str, tuple[pd.DataFrame, pd.DatetimeIndex, np.ndarray]] = {
            code: (source, pd.DatetimeIndex(pd.to_datetime(source["date"])), source["open"].to_numpy())
            for code, source in trade_frames.items()
        }
        prepared_signals: Dict[str, tuple[pd.DataFrame, pd.DatetimeIndex]] = {
            code: (source, pd.DatetimeIndex(pd.to_datetime(source["date"])))
            for code, source in signal_frames.items()
        }
        ranking_cache: Dict[int, list[Dict[str, Any]]] = {}

        def rankings_at(position: int) -> list[Dict[str, Any]]:
            cached = ranking_cache.get(position)
            if cached is not None:
                return cached
            target_date = benchmark_dates[position]
            benchmark_slice = benchmark_frame.iloc[:position + 1]
            benchmark_metrics = self._decision_benchmark_metrics(benchmark_slice, window)
            if benchmark_metrics is None:
                ranking_cache[position] = []
                return []
            raw_rows = []
            for item in self.universe:
                prepared_trade = prepared_trades.get(item.code)
                prepared_signal = prepared_signals.get(item.code)
                if prepared_trade is None or prepared_signal is None:
                    continue
                trade_source, trade_dates, _ = prepared_trade
                signal_source, signal_dates = prepared_signal
                trade_slice_end = int(trade_dates.searchsorted(target_date, side="right"))
                signal_slice_end = int(signal_dates.searchsorted(target_date, side="right"))
                if trade_slice_end < window + 1 or signal_slice_end < window + 1:
                    continue
                trade_lag = position + 1 - int(
                    benchmark_dates[:position + 1].searchsorted(
                        trade_dates[trade_slice_end - 1], side="right"
                    )
                )
                signal_lag = position + 1 - int(
                    benchmark_dates[:position + 1].searchsorted(
                        signal_dates[signal_slice_end - 1], side="right"
                    )
                )
                if (
                    trade_lag > engine.max_stale_sessions
                    or signal_lag > engine.max_stale_sessions
                ):
                    continue
                trade_slice = trade_source.iloc[:trade_slice_end].copy()
                trade_slice.attrs.update(trade_source.attrs)
                trade_slice.attrs["data_lag_sessions"] = trade_lag
                signal_slice = signal_source.iloc[:signal_slice_end].copy()
                signal_slice.attrs.update(signal_source.attrs)
                signal_slice.attrs["signal_lag_sessions"] = signal_lag
                raw_rows.append(engine._raw_metrics(
                    item,
                    signal_slice,
                    benchmark_metrics,
                    window,
                    [],
                    trade_frame=trade_slice,
                    signal_mode=str(
                        signal_source.attrs.get("rotation_signal_mode") or "trade_asset"
                    ),
                ))
            ranked = engine._score_rows(raw_rows) if raw_rows else []
            ranking_cache[position] = ranked
            return ranked

        warmup = max(window + 5, 125)
        trade_sets: Dict[str, list[Dict[str, Any]]] = {
            policy: [] for policy in ROTATION_CONFIRMATION_POLICIES
        }
        held_symbols = {policy: {None} for policy in ROTATION_CONFIRMATION_POLICIES}
        for position in range(warmup, len(benchmark_dates) - rebalance_days - 1, rebalance_days):
            signal_date = benchmark_dates[position]
            entry_date = benchmark_dates[position + 1]
            exit_date = benchmark_dates[position + 1 + rebalance_days]
            benchmark_entry = self._valid_execution_price(benchmark_opens[position + 1])
            benchmark_exit = self._valid_execution_price(benchmark_opens[position + 1 + rebalance_days])
            current_rankings = [dict(row) for row in rankings_at(position)]
            benchmark_return = benchmark_exit / benchmark_entry - 1 if benchmark_entry is not None and benchmark_exit is not None else None
            if len(current_rankings) < self._minimum_cross_section_size(len(self.universe)):
                for policy in ROTATION_CONFIRMATION_POLICIES:
                    pending = _unresolved_period(signal_date, entry_date, exit_date,
                                                 benchmark_return, "missing_benchmark_signal" if self._decision_benchmark_metrics(benchmark_frame.iloc[:position + 1], window) is None else "insufficient_signal_coverage")
                    pending["selection_policy"] = policy
                    trade_sets[policy].append(pending)
                    held_symbols[policy] = {None, *(item.code for item in self.universe)}
                continue
            forward_returns = {
                row["code"]: self._forward_return(prepared_trades[row["code"]], entry_date, exit_date)
                for row in current_rankings
            }

            history = []
            for history_position in range(max(0, position - 19), position + 1):
                historical_rankings = rankings_at(history_position)
                history.append({"rankings": historical_rankings})
            engine._attach_rotation_confirmation(current_rankings, history)
            benchmark_return = benchmark_exit / benchmark_entry - 1 if benchmark_entry is not None and benchmark_exit is not None else None
            equal_weight_return = float(np.mean(list(forward_returns.values()))) if all(value is not None for value in forward_returns.values()) else None

            for policy in ROTATION_CONFIRMATION_POLICIES:
                selected, possible, switched = self._decision_from_possible_holdings(
                    current_rankings,
                    held_symbols[policy],
                    policy,
                )
                held_symbols[policy] = possible
                if len(possible) > 1:
                    pending = _unresolved_period(signal_date, entry_date, exit_date,
                                                 benchmark_return, "ambiguous_holding_state")
                    pending.update(selection_policy=policy, equal_weight_return=equal_weight_return)
                    trade_sets[policy].append(pending)
                    continue
                selected_symbol = str(selected["code"]) if selected else None
                transaction_cost = round_trip_cost(cost_bps, executed=switched) if switched is not None else None
                if selected:
                    gross_return = forward_returns[selected_symbol]
                    name = selected["name"]
                    industry = selected["industry"]
                    score = selected["total_score"]
                    signal = selected.get("rotation_signal")
                    overheated = bool(selected.get("overheated"))
                    signal_code = selected.get("signal_code")
                    signal_name = selected.get("signal_name")
                    signal_mode = selected.get("signal_mode")
                else:
                    gross_return = 0.0
                    name = "现金"
                    industry = "现金"
                    score = 0.0
                    signal = "等待确认"
                    overheated = False
                    signal_code = ""
                    signal_name = ""
                    signal_mode = "cash"
                trade_sets[policy].append({
                    "signal_date": signal_date.strftime("%Y-%m-%d"),
                    "entry_date": entry_date.strftime("%Y-%m-%d"),
                    "exit_date": exit_date.strftime("%Y-%m-%d"),
                    "symbol": selected_symbol or "CASH",
                    "name": name,
                    "industry": industry,
                    "signal_code": signal_code,
                    "signal_name": signal_name,
                    "signal_mode": signal_mode,
                    "score": score,
                    "rotation_signal": signal,
                    "overheated": overheated,
                    "selection_policy": policy,
                    "invested": selected is not None,
                    "switched": switched,
                    "transaction_cost": transaction_cost,
                    "gross_return": gross_return,
                    "net_return": gross_return - transaction_cost if gross_return is not None and transaction_cost is not None else None,
                    "benchmark_return": benchmark_return,
                    "equal_weight_return": equal_weight_return,
                    **({"decision_issue": "uncertain_turnover"} if switched is None else {}),
                })
        return trade_sets

    @staticmethod
    def _can_score(metrics: Mapping[str, Any]) -> bool:
        return (int(metrics.get("trades") or 0) >= 8
                and metrics.get("execution_state") == "complete"
                and metrics.get("sharpe") is not None
                and metrics.get("information_ratio") is not None)

    @staticmethod
    def _selection_score(metrics: Mapping[str, Any]) -> float:
        if not RotationExperiment._can_score(metrics):
            return -1_000.0
        return (
            float(metrics.get("excess_return_pct") or 0)
            + float(metrics.get("sharpe") or 0) * 4
            + float(metrics.get("information_ratio") or 0) * 3
            - float(metrics.get("max_drawdown_pct") or 0) * 0.35
        )

    @staticmethod
    def _training_stability(
        trades: Sequence[Mapping[str, Any]],
        rebalance_days: int,
        blocks: int = 3,
    ) -> Dict[str, Any]:
        if not trades:
            return {
                "blocks": [],
                "positive_excess_blocks": 0,
                "positive_excess_share_pct": None,
                "latest_block_excess_return_pct": None,
                "worst_block_excess_return_pct": None,
            }
        size = len(trades)
        metrics = []
        for index in range(blocks):
            start = index * size // blocks
            end = (index + 1) * size // blocks
            block = list(trades[start:end])
            if not block:
                continue
            result = _metrics(block, rebalance_days)
            metrics.append({
                "block": index + 1,
                "start": block[0]["entry_date"],
                "end": block[-1]["exit_date"],
                **result,
            })
        positive = sum(row["excess_return_pct"] is not None and row["excess_return_pct"] > 0 for row in metrics)
        complete = all(row["execution_state"] == "complete" for row in metrics)
        return {
            "blocks": metrics,
            "positive_excess_blocks": positive,
            "positive_excess_share_pct": _round(positive / max(len(metrics), 1) * 100) if complete else None,
            "latest_block_excess_return_pct": _round(
                metrics[-1]["excess_return_pct"] if metrics else 0.0
            ) if complete else None,
            "worst_block_excess_return_pct": _round(
                min((row["excess_return_pct"] for row in metrics), default=0.0)
            ) if complete else None,
        }

    @classmethod
    def _robust_selection_score(
        cls,
        metrics: Mapping[str, Any],
        stability: Mapping[str, Any],
    ) -> float:
        base = cls._selection_score(metrics)
        if base <= -1_000:
            return base
        worst = min(float(stability.get("worst_block_excess_return_pct") or 0), 0.0)
        latest = min(float(stability.get("latest_block_excess_return_pct") or 0), 0.0)
        return base + worst * 0.25 + latest * 0.25

    @staticmethod
    def _training_qualification(
        metrics: Mapping[str, Any],
        stability: Optional[Mapping[str, Any]] = None,
    ) -> Dict[str, Any]:
        stability = stability or {}
        block_count = len(stability.get("blocks") or [])
        checks = {
            "complete_execution_evidence": metrics.get("execution_state") == "complete",
            "price_volume_limit_evidence": metrics.get("execution_evidence", {}).get("state") == "checked",
            "defined_risk_ratios": metrics.get("sharpe") is not None and metrics.get("information_ratio") is not None,
            "positive_total_return": float(metrics.get("total_return_pct") or 0) > 0,
            "positive_excess_return": float(metrics.get("excess_return_pct") or 0) > 0,
            "majority_positive_training_blocks": (
                not block_count
                or int(stability.get("positive_excess_blocks") or 0)
                >= math.ceil(block_count / 2)
            ),
            "latest_training_block_not_broken": (
                not block_count
                or float(stability.get("latest_block_excess_return_pct") or 0) >= -5.0
            ),
        }
        return {
            "state": "qualified" if all(checks.values()) else "diagnostic_only",
            "checks": checks,
        }

    @staticmethod
    def _stress_metrics(
        trades: Sequence[Mapping[str, Any]],
        *,
        rebalance_days: int,
        cost_bps: int,
    ) -> Dict[str, Any]:
        stressed = []
        for row in trades:
            item = dict(row)
            transaction_cost = round_trip_cost(
                cost_bps, executed=row.get("switched", True)
            ) if row.get("switched", True) is not None else None
            item["transaction_cost"] = transaction_cost
            item["net_return"] = float(row["gross_return"]) - transaction_cost if row["gross_return"] is not None and transaction_cost is not None else None
            stressed.append(item)
        return {"cost_bps": cost_bps, **_metrics(stressed, rebalance_days)}

    @staticmethod
    def _equity_curve(trades: Sequence[Mapping[str, Any]]) -> list[Dict[str, Any]]:
        strategy_equity = 1.0
        benchmark_equity = 1.0
        equal_weight_equity = 1.0
        points = [{
            "date": trades[0]["entry_date"],
            "strategy": 1.0,
            "benchmark": 1.0,
            "equal_weight": 1.0,
            "symbol": None,
        }] if trades else []
        for row in trades:
            strategy_equity = strategy_equity * (1 + row["net_return"]) if strategy_equity is not None and row["net_return"] is not None else None
            benchmark_equity = benchmark_equity * (1 + row["benchmark_return"]) if benchmark_equity is not None and row["benchmark_return"] is not None else None
            equal_weight_equity = equal_weight_equity * (1 + row["equal_weight_return"]) if equal_weight_equity is not None and row["equal_weight_return"] is not None else None
            points.append({
                "date": row["exit_date"],
                "strategy": _round(strategy_equity, 4) if strategy_equity is not None else None,
                "benchmark": _round(benchmark_equity, 4) if benchmark_equity is not None else None,
                "equal_weight": _round(equal_weight_equity, 4) if equal_weight_equity is not None else None,
                "symbol": row["symbol"],
            })
        return points

    @staticmethod
    def _ranking_effect(
        scores: Sequence[float],
        returns: Sequence[Optional[float]],
        benchmark_return: Optional[float],
    ) -> Dict[str, Any]:
        """Measure one cross-sectional score without using future data in it."""

        frame = pd.DataFrame({"score": scores, "return": returns}).replace(
            [np.inf, -np.inf], np.nan
        )
        if len(frame) < 4 or frame.isna().any().any() or benchmark_return is None:
            # Evaluate only a complete frozen cross-section. Dropping missing
            # labels before top/bottom selection would promote replacement ETFs.
            return {"available": False, "rank_ic": None, "top3_minus_bottom3": None,
                    "leader_beat_median": None, "leader_beat_benchmark": None,
                    "top3_beat_median": None, "top3_beat_benchmark": None}
        rank_ic = (
            frame["score"].rank().corr(frame["return"].rank())
            if frame["score"].nunique() > 1 and frame["return"].nunique() > 1
            else None
        )
        ordered = frame.sort_values("score", ascending=False)
        # No diagnostic tie-break may depend on input order or future returns.
        top_clear = ordered["score"].iloc[2] > ordered["score"].iloc[3]
        bottom_clear = ordered["score"].iloc[-3] < ordered["score"].iloc[-4]
        leader_clear = ordered["score"].iloc[0] > ordered["score"].iloc[1]
        top3 = float(ordered["return"].head(3).mean()) if top_clear else None
        bottom3 = float(ordered["return"].tail(3).mean()) if bottom_clear else None
        leader_return = float(ordered["return"].iloc[0]) if leader_clear else None
        median_return = float(frame["return"].median())
        issues = []
        if frame["score"].nunique() == 1:
            issues.append("constant_scores")
        if frame["return"].nunique() == 1:
            issues.append("constant_returns")
        if not top_clear:
            issues.append("top3_boundary_tie")
        if not bottom_clear:
            issues.append("bottom3_boundary_tie")
        if not leader_clear:
            issues.append("leader_tie")
        if len(frame) < 6:
            issues.append("fewer_than_six_assets")
        return {
            "available": True,
            "metric_issues": issues,
            "rank_ic": float(rank_ic) if rank_ic is not None and math.isfinite(float(rank_ic)) else None,
            "top3_minus_bottom3": top3 - bottom3 if len(frame) >= 6 and top3 is not None and bottom3 is not None else None,
            "leader_beat_median": leader_return > median_return + 1e-12 if leader_return is not None else None,
            "leader_beat_benchmark": leader_return > benchmark_return + 1e-12 if leader_return is not None else None,
            "top3_beat_median": top3 > median_return + 1e-12 if top3 is not None else None,
            "top3_beat_benchmark": top3 > benchmark_return + 1e-12 if top3 is not None else None,
        }

    @staticmethod
    def _wilson_interval_pct(successes: int, samples: int) -> tuple[Optional[float], Optional[float]]:
        """Return a compact 95% Wilson interval for a hit rate."""

        if samples <= 0:
            return None, None
        z = 1.96
        rate = successes / samples
        denominator = 1 + z * z / samples
        center = (rate + z * z / (2 * samples)) / denominator
        margin = z * math.sqrt(
            rate * (1 - rate) / samples + z * z / (4 * samples * samples)
        ) / denominator
        return _round(max(center - margin, 0.0) * 100), _round(
            min(center + margin, 1.0) * 100
        )

    @classmethod
    def _non_overlapping_effect_groups(
        cls,
        effects: Sequence[Mapping[str, Any]],
        *,
        horizon: int,
    ) -> list[list[Mapping[str, Any]]]:
        """Build every sampling phase and keep a conservative interval envelope."""

        available = [row for row in effects if row.get("available")]
        overlap = max(1, math.ceil(horizon / cls.prediction_sampling_sessions))
        dated = []
        for row in available:
            try:
                entry = pd.Timestamp(row["entry_date"])
                exit_date = pd.Timestamp(row["exit_date"])
            except (KeyError, TypeError, ValueError):
                dated = []
                break
            dated.append((entry, exit_date, row))
        ordered = (
            [row for _, _, row in sorted(dated, key=lambda item: item[0])]
            if dated else available
        )
        groups = []
        for phase in range(min(overlap, len(ordered))):
            candidates = ordered[phase::overlap]
            if not dated:
                groups.append(candidates)
                continue
            selected = []
            last_exit: Optional[pd.Timestamp] = None
            for row in candidates:
                entry = pd.Timestamp(row["entry_date"])
                exit_date = pd.Timestamp(row["exit_date"])
                if last_exit is None or entry >= last_exit:
                    selected.append(row)
                    last_exit = exit_date
            if selected:
                groups.append(selected)
        return groups

    @classmethod
    def _effect_summary(
        cls,
        effects: Sequence[Mapping[str, Any]],
        *,
        horizon: int,
    ) -> Dict[str, Any]:
        available = [row for row in effects if row.get("available")]
        rank_ics = [float(row["rank_ic"]) for row in available if row.get("rank_ic") is not None]
        spreads = [float(row["top3_minus_bottom3"]) for row in available if row.get("top3_minus_bottom3") is not None]
        hit_rows = [row for row in available if row.get("top3_beat_benchmark") is not None]
        hits = sum(bool(row["top3_beat_benchmark"]) for row in hit_rows)
        non_overlapping_groups = cls._non_overlapping_effect_groups(
            hit_rows, horizon=horizon
        )
        group_hits = [
            sum(bool(row["top3_beat_benchmark"]) for row in group)
            for group in non_overlapping_groups
        ]
        group_rates = [
            successes / len(group) * 100
            for successes, group in zip(group_hits, non_overlapping_groups)
            if group
        ]
        group_intervals = [
            cls._wilson_interval_pct(successes, len(group))
            for successes, group in zip(group_hits, non_overlapping_groups)
            if group
        ]
        low = min((interval[0] for interval in group_intervals), default=0.0)
        high = max((interval[1] for interval in group_intervals), default=0.0)
        effective_samples = max(
            (len(group) for group in non_overlapping_groups), default=0
        )
        return {
            "samples": len(available),
            "expected_samples": len(effects),
            "missing_samples": len(effects) - len(available),
            "rank_ic_samples": len(rank_ics),
            "spread_samples": len(spreads),
            "top3_hit_samples": len(hit_rows),
            "metric_issue_counts": dict(Counter(issue for row in available for issue in row.get("metric_issues", []))),
            "effective_non_overlapping_samples": effective_samples,
            "rank_ic_mean": _round(np.mean(rank_ics), 4) if rank_ics else None,
            "rank_ic_positive_rate_pct": _round(
                np.mean([value > 0 for value in rank_ics]) * 100
            ) if rank_ics else None,
            "top3_minus_bottom3_mean_pct": _round(
                np.mean(spreads) * 100
            ) if spreads else None,
            "top3_beat_benchmark_rate_pct": _round(
                hits / len(hit_rows) * 100
            ) if hit_rows else None,
            "non_overlapping_top3_beat_benchmark_rate_pct": _round(
                np.mean(group_rates)
            ) if group_rates else None,
            "non_overlapping_top3_beat_benchmark_rate_range_pct": [
                _round(min(group_rates), 2) if group_rates else 0.0,
                _round(max(group_rates), 2) if group_rates else 0.0,
            ] if group_rates else None,
            "top3_beat_benchmark_wilson_95_pct": [low, high] if group_intervals else None,
            "wilson_sample_policy": "all_non_overlapping_phase_cohorts_conservative_envelope",
        }

    @classmethod
    def _summarize_prediction_records(
        cls,
        records: Sequence[Mapping[str, Any]],
    ) -> Dict[str, Any]:
        horizons = []
        for horizon in (5, 10, 20):
            scheduled = [row for row in records if int(row["horizon"]) == horizon]
            effects = [cls._record_effect(row) for row in scheduled]
            summary = cls._effect_summary(effects, horizon=horizon)
            summary["horizon_sessions"] = horizon
            spreads = [row["top3_minus_bottom3"] for row in effects
                       if row["available"] and row.get("top3_minus_bottom3") is not None]
            summary["top3_spread_positive_rate_pct"] = (
                _round(np.mean([value > 0 for value in spreads]) * 100) if spreads else None
            )
            for metric in ("leader_beat_median", "leader_beat_benchmark", "top3_beat_median"):
                values = [row[metric] for row in effects
                          if row["available"] and row.get(metric) is not None]
                summary[f"{metric}_samples"] = len(values)
                summary[f"{metric}_rate_pct"] = _round(np.mean(values) * 100) if values else None
            horizons.append(summary)
        return {"horizons": horizons}

    @staticmethod
    def _record_effect(row: Mapping[str, Any]) -> Dict[str, Any]:
        return {
            **{key: row.get(key) for key in (
                "entry_date", "exit_date", "rank_ic", "top3_minus_bottom3",
                "leader_beat_median", "leader_beat_benchmark",
                "top3_beat_median", "top3_beat_benchmark",
            )},
            "available": row.get("available", True),
            "metric_issues": row.get("metric_issues", []),
        }

    @staticmethod
    def _factor_record_effect(
        row: Mapping[str, Any],
        collection: str,
        factor: str,
    ) -> Dict[str, Any]:
        effect = dict(
            (row.get(collection) or {}).get(factor, {"available": False})
        )
        effect["entry_date"] = row.get("entry_date")
        effect["exit_date"] = row.get("exit_date")
        return effect

    @classmethod
    def _paired_ablation_delta(cls, rows, factor, metric, *, scale=1, digits=4):
        pairs = []
        for row in rows:
            combined = cls._record_effect(row)
            without = cls._factor_record_effect(row, "ablation_effects", factor)
            if combined["available"] and without.get("available"):
                left, right = combined.get(metric), without.get(metric)
                if left is not None and right is not None:
                    pairs.append(float(left) - float(right))
        return {"samples": len(pairs),
                "delta": _round(np.mean(pairs) * scale, digits) if pairs else None}

    @classmethod
    def _factor_effectiveness(
        cls,
        train_records: Sequence[Mapping[str, Any]],
        oos_records: Sequence[Mapping[str, Any]],
        factor_model: Mapping[str, Any],
        *,
        horizon: int,
    ) -> Dict[str, Any]:
        """Report standalone and leave-one-out evidence for all seven factors."""

        active = set(factor_model.get("active_factors") or ())
        configured_weights = factor_model.get("configured_weights") or {}
        effective_weights = factor_model.get("effective_weights") or {}
        train_rows = [row for row in train_records if int(row["horizon"]) == horizon]
        oos_rows = [row for row in oos_records if int(row["horizon"]) == horizon]
        combined_train = cls._effect_summary(
            [cls._record_effect(row) for row in train_rows], horizon=horizon
        )
        combined_oos = cls._effect_summary(
            [cls._record_effect(row) for row in oos_rows], horizon=horizon
        )
        factors = []
        for factor in RotationEngine.factor_keys:
            train = cls._effect_summary(
                [
                    cls._factor_record_effect(row, "factor_effects", factor)
                    for row in train_rows
                ],
                horizon=horizon,
            )
            oos = cls._effect_summary(
                [
                    cls._factor_record_effect(row, "factor_effects", factor)
                    for row in oos_rows
                ],
                horizon=horizon,
            )
            train_without = cls._effect_summary(
                [
                    cls._factor_record_effect(row, "ablation_effects", factor)
                    for row in train_rows
                ],
                horizon=horizon,
            )
            oos_without = cls._effect_summary(
                [
                    cls._factor_record_effect(row, "ablation_effects", factor)
                    for row in oos_rows
                ],
                horizon=horizon,
            )
            is_active = factor in active
            train_rank = cls._paired_ablation_delta(train_rows, factor, "rank_ic")
            oos_rank = cls._paired_ablation_delta(oos_rows, factor, "rank_ic")
            train_hit = cls._paired_ablation_delta(train_rows, factor, "top3_beat_benchmark", scale=100, digits=2)
            oos_hit = cls._paired_ablation_delta(oos_rows, factor, "top3_beat_benchmark", scale=100, digits=2)
            train_rank_delta, oos_rank_delta = train_rank["delta"], oos_rank["delta"]
            train_hit_delta, oos_hit_delta = train_hit["delta"], oos_hit["delta"]
            if not is_active:
                state, label = "unavailable", "缺少点时历史"
            elif train["missing_samples"] or oos["missing_samples"]:
                state, label = "incomplete_labels", "未来标签覆盖不完整"
            elif not train["samples"] or not oos["samples"]:
                state, label = "insufficient_samples", "缺少训练或样本外有效样本"
            elif train["rank_ic_mean"] is None or oos["rank_ic_mean"] is None:
                state, label = "undefined_ic", "分数或收益无差异，IC不可计算"
            elif train["rank_ic_samples"] < train["samples"] or oos["rank_ic_samples"] < oos["samples"]:
                state, label = "partial_ic", "部分截面IC不可计算，需核验覆盖"
            elif train_rank["samples"] < combined_train["samples"] or oos_rank["samples"] < combined_oos["samples"]:
                state, label = "partial_comparison", "去除因子后部分IC不可计算，仅作配对观察"
            elif train["rank_ic_mean"] > 0 and oos["rank_ic_mean"] > 0:
                if train_rank_delta is not None and oos_rank_delta is not None and train_rank_delta >= 0 and oos_rank_delta >= 0:
                    state, label = "stable_positive", "跨区间有效"
                else:
                    state, label = "positive_redundant", "方向有效但存在冗余"
            elif oos["rank_ic_mean"] > 0:
                state, label = "oos_only", "仅样本外转正"
            elif train["rank_ic_mean"] > 0:
                state, label = "train_only", "样本外失效"
            else:
                state, label = "weak", "未见稳定正效应"
            factors.append({
                "factor": factor,
                "active": is_active,
                "configured_weight": _round(configured_weights.get(factor), 4),
                "effective_weight": _round(effective_weights.get(factor), 4),
                "state": state,
                "label": label,
                "train": train,
                "out_of_sample": oos,
                "leave_one_out": {
                    "train": train_without,
                    "out_of_sample": oos_without,
                    "rank_ic_contribution_train": train_rank_delta,
                    "rank_ic_contribution_oos": oos_rank_delta,
                    "top3_hit_contribution_train_pct": train_hit_delta,
                    "top3_hit_contribution_oos_pct": oos_hit_delta,
                    "paired_samples": {"rank_ic_train": train_rank["samples"],
                                       "rank_ic_oos": oos_rank["samples"],
                                       "top3_hit_train": train_hit["samples"],
                                       "top3_hit_oos": oos_hit["samples"]},
                },
            })
        return {
            "method": "standalone_rank_ic_and_leave_one_out_composite",
            "primary_horizon_sessions": horizon,
            "selection_use": "diagnostic_only_no_oos_reweighting",
            "comparison_policy": "paired_valid_sections_per_metric",
            "combined": {"train": combined_train, "out_of_sample": combined_oos},
            "factors": factors,
        }

    @classmethod
    def _confidence_diagnostics(
        cls,
        train_records: Sequence[Mapping[str, Any]],
        oos_records: Sequence[Mapping[str, Any]],
        *,
        horizon: int,
    ) -> Dict[str, Any]:
        """Check whether abstaining on low-consensus signals raises precision."""

        train_rows = [row for row in train_records if int(row["horizon"]) == horizon]
        oos_rows = [row for row in oos_records if int(row["horizon"]) == horizon]
        train_scores = [
            float(row["confidence"]["score"])
            for row in train_rows
            if (row.get("confidence") or {}).get("score") is not None
        ]
        threshold = float(
            np.quantile(train_scores, cls.high_confidence_train_quantile)
        ) if train_scores else 100.0

        def summarize(rows: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
            selected = [
                row for row in rows
                if (row.get("confidence") or {}).get("score") is not None
                and float(row["confidence"]["score"]) >= threshold
            ]
            all_summary = cls._effect_summary(
                [cls._record_effect(row) for row in rows], horizon=horizon
            )
            selected_summary = cls._effect_summary(
                [cls._record_effect(row) for row in selected], horizon=horizon
            )
            selected_summary["selection_rate_pct"] = _round(len(selected) / len(rows) * 100) if rows else None
            selected_summary["top3_hit_delta_pct"] = _difference(
                selected_summary["top3_beat_benchmark_rate_pct"], all_summary["top3_beat_benchmark_rate_pct"])
            selected_summary["rank_ic_delta"] = _difference(
                selected_summary["rank_ic_mean"], all_summary["rank_ic_mean"], 4)
            return {"all": all_summary, "high_confidence": selected_summary}

        train = summarize(train_rows)
        oos = summarize(oos_rows)
        train_delta = train["high_confidence"]["top3_hit_delta_pct"]
        oos_delta = oos["high_confidence"]["top3_hit_delta_pct"]
        oos_effective = oos["high_confidence"]["effective_non_overlapping_samples"]
        interval = oos["high_confidence"]["top3_beat_benchmark_wilson_95_pct"]
        wilson_low = interval[0] if interval else None
        if train_delta is None or oos_delta is None:
            state, label = "insufficient_samples", "缺少有效样本，无法比较过滤效果"
        elif train_delta >= 0 and oos_delta >= 3 and oos_effective >= 10:
            if wilson_low >= 50:
                state, label = "precision_improved", "高共识信号提高命中且通过区间下界"
            else:
                state, label = "observed_improvement", "高共识信号命中改善但统计证据不足"
        elif oos_delta > 0:
            state, label = "oos_only", "样本外有改善，训练段未确认"
        else:
            state, label = "not_improved", "高共识过滤暂未提高命中"
        if any(part["all"]["top3_hit_samples"] < part["all"]["samples"] for part in (train, oos)):
            state, label = "ambiguous_top3", "部分Top3边界并列，过滤效果仅覆盖可判定截面"
        if any(not row.get("available", True) for row in train_rows + oos_rows):
            state, label = "incomplete_labels", "缺少未来标签，不能确认过滤提升"
        return {
            "method": "training_distribution_calibrated_abstention",
            "primary_horizon_sessions": horizon,
            "feature_formula": "70pct_active_factor_consensus_plus_30pct_score_separation",
            "threshold_train_quantile": cls.high_confidence_train_quantile,
            "threshold": _round(threshold, 2) if train_scores else None,
            "train": train,
            "out_of_sample": oos,
            "verdict": {
                "state": state,
                "label": label,
                "deployment": "shadow_only_until_30_new_non_overlapping_signals",
            },
        }

    def _prediction_diagnostics(
        self,
        *,
        benchmark_frame: pd.DataFrame,
        trade_frames: Mapping[str, pd.DataFrame],
        signal_frames: Mapping[str, pd.DataFrame],
        weights: Mapping[str, float],
        window: int,
        split_date: pd.Timestamp,
    ) -> Dict[str, Any]:
        """Measure forward ranking quality without selecting one lucky ETF path."""

        engine = RotationEngine(
            self.provider,
            universe=self.universe,
            max_workers=self.max_workers,
            weights=weights,
        )
        benchmark_dates = pd.DatetimeIndex(pd.to_datetime(benchmark_frame["date"]))
        benchmark_opens = benchmark_frame["open"].to_numpy()
        prepared_trades = {
            code: (
                source,
                pd.DatetimeIndex(pd.to_datetime(source["date"])),
                source["open"].to_numpy(),
            )
            for code, source in trade_frames.items()
        }
        prepared_signals = {
            code: (source, pd.DatetimeIndex(pd.to_datetime(source["date"])))
            for code, source in signal_frames.items()
        }
        records: list[Dict[str, Any]] = []
        factor_model: Dict[str, Any] = {}
        warmup = max(window + 5, 125)
        for position in range(warmup, len(benchmark_dates) - 21, 5):
            signal_date = benchmark_dates[position]
            entry_date = benchmark_dates[position + 1]
            benchmark_slice = benchmark_frame.iloc[:position + 1]
            benchmark_metrics = self._decision_benchmark_metrics(benchmark_slice, window)
            raw_rows = []
            future_returns: Dict[str, Dict[int, Optional[float]]] = {}
            for item in self.universe:
                if benchmark_metrics is None:
                    break
                prepared_trade = prepared_trades.get(item.code)
                prepared_signal = prepared_signals.get(item.code)
                if prepared_trade is None or prepared_signal is None:
                    continue
                trade_source, trade_dates, _ = prepared_trade
                signal_source, signal_dates = prepared_signal
                trade_end = int(trade_dates.searchsorted(signal_date, side="right"))
                signal_end = int(signal_dates.searchsorted(signal_date, side="right"))
                if trade_end < window + 1 or signal_end < window + 1:
                    continue
                trade_lag = position + 1 - int(
                    benchmark_dates[:position + 1].searchsorted(
                        trade_dates[trade_end - 1], side="right"
                    )
                )
                signal_lag = position + 1 - int(
                    benchmark_dates[:position + 1].searchsorted(
                        signal_dates[signal_end - 1], side="right"
                    )
                )
                if trade_lag > engine.max_stale_sessions or signal_lag > engine.max_stale_sessions:
                    continue
                trade_slice = trade_source.iloc[:trade_end].copy()
                trade_slice.attrs.update(trade_source.attrs)
                trade_slice.attrs["data_lag_sessions"] = trade_lag
                signal_slice = signal_source.iloc[:signal_end].copy()
                signal_slice.attrs.update(signal_source.attrs)
                signal_slice.attrs["signal_lag_sessions"] = signal_lag
                raw_rows.append(engine._raw_metrics(
                    item,
                    signal_slice,
                    benchmark_metrics,
                    window,
                    [],
                    trade_frame=trade_slice,
                    signal_mode=str(
                        signal_source.attrs.get("rotation_signal_mode") or "trade_asset"
                    ),
                ))
                future_returns[item.code] = {
                    horizon: self._forward_return(prepared_trade, entry_date, benchmark_dates[position + 1 + horizon])
                    for horizon in (5, 10, 20)
                }
            if len(raw_rows) < self._minimum_cross_section_size(len(self.universe)):
                for horizon in (5, 10, 20):
                    records.append({
                        **self._ranking_effect([], [], None),
                        "signal_date": signal_date.strftime("%Y-%m-%d"),
                        "entry_date": entry_date.strftime("%Y-%m-%d"),
                        "exit_date": benchmark_dates[position + 1 + horizon].strftime("%Y-%m-%d"),
                        "horizon": horizon,
                        "decision_issue": "missing_benchmark_signal" if benchmark_metrics is None else "insufficient_signal_coverage",
                        "factor_effects": {}, "ablation_effects": {}, "confidence": {},
                    })
                continue
            factors = engine._factor_frame(raw_rows)
            current_factor_model = engine._factor_model(factors)
            if not factor_model:
                factor_model = current_factor_model
            rankings = engine._score_factor_frame(
                factors, factor_model=current_factor_model
            )
            factor_lookup = factors.set_index("code")
            active_factors = list(current_factor_model.get("active_factors") or ())
            effective_weights = current_factor_model.get("effective_weights") or {}
            for horizon in (5, 10, 20):
                pairs = [
                    (row, future_returns[row["code"]][horizon])
                    for row in rankings
                ]
                benchmark_entry = self._valid_execution_price(benchmark_opens[position + 1])
                benchmark_exit = self._valid_execution_price(
                    benchmark_opens[position + 1 + horizon]
                )
                benchmark_return = benchmark_exit / benchmark_entry - 1 if benchmark_entry is not None and benchmark_exit is not None else None
                codes = [str(row["code"]) for row, _ in pairs]
                returns = [value for _, value in pairs]
                composite_scores = [float(row["total_score"]) for row, _ in pairs]
                composite = self._ranking_effect(
                    composite_scores, returns, benchmark_return
                )
                factor_effects: Dict[str, Dict[str, Any]] = {}
                ablation_effects: Dict[str, Dict[str, Any]] = {}
                for factor in engine.factor_keys:
                    if factor not in active_factors:
                        factor_effects[factor] = {"available": False}
                        ablation_effects[factor] = {"available": False}
                        continue
                    factor_scores = [
                        float(factor_lookup.at[code, f"{factor}_score"])
                        for code in codes
                    ]
                    factor_effects[factor] = self._ranking_effect(
                        factor_scores, returns, benchmark_return
                    )
                    denominator = sum(
                        float(effective_weights.get(key) or 0)
                        for key in active_factors
                        if key != factor
                    )
                    if denominator <= 0:
                        ablation_effects[factor] = {"available": False}
                        continue
                    without_scores = [
                        sum(
                            float(factor_lookup.at[code, f"{key}_score"])
                            * float(effective_weights.get(key) or 0)
                            for key in active_factors
                            if key != factor
                        ) / denominator
                        for code in codes
                    ]
                    ablation_effects[factor] = self._ranking_effect(
                        without_scores, returns, benchmark_return
                    )

                ordered = sorted(
                    pairs,
                    key=lambda pair: float(pair[0]["total_score"]),
                    reverse=True,
                )
                top3_codes = [str(row["code"]) for row, _ in ordered[:3]]
                consensus_flags = [
                    float(
                        np.mean([
                            float(factor_lookup.at[code, f"{factor}_score"])
                            for code in top3_codes
                        ])
                    ) >= 60.0
                    for factor in active_factors
                ]
                consensus_pct = (
                    sum(consensus_flags) / len(consensus_flags) * 100
                    if consensus_flags else 0.0
                )
                top3_score = float(np.mean([
                    float(row["total_score"]) for row, _ in ordered[:3]
                ]))
                score_edge = max(
                    top3_score - float(np.median(composite_scores)), 0.0
                )
                separation_pct = min(score_edge / 15.0 * 100, 100.0)
                confidence_score = consensus_pct * 0.70 + separation_pct * 0.30
                top3_clear = len(ordered) > 3 and ordered[2][0]["total_score"] > ordered[3][0]["total_score"]
                records.append({
                    **composite,
                    "signal_date": signal_date.strftime("%Y-%m-%d"),
                    "entry_date": entry_date.strftime("%Y-%m-%d"),
                    "exit_date": benchmark_dates[position + 1 + horizon].strftime("%Y-%m-%d"),
                    "horizon": horizon,
                    "factor_effects": factor_effects,
                    "ablation_effects": ablation_effects,
                    "confidence": {
                        "score": _round(confidence_score, 4) if top3_clear else None,
                        "active_factor_consensus_pct": _round(consensus_pct) if top3_clear else None,
                        "top3_score_edge": _round(score_edge, 4) if top3_clear else None,
                        "issue": None if top3_clear else "top3_boundary_tie",
                    },
                })

        train = [row for row in records if pd.Timestamp(row["exit_date"]) <= split_date]
        out_of_sample = [row for row in records if pd.Timestamp(row["entry_date"]) > split_date]
        train_summary = self._summarize_prediction_records(train)
        oos_summary = self._summarize_prediction_records(out_of_sample)
        all_summary = self._summarize_prediction_records(records)
        primary_horizon = self.primary_prediction_horizon
        factor_effectiveness = self._factor_effectiveness(
            train,
            out_of_sample,
            factor_model,
            horizon=primary_horizon,
        )
        confidence_diagnostics = self._confidence_diagnostics(
            train,
            out_of_sample,
            horizon=primary_horizon,
        )
        oos_horizons = oos_summary["horizons"]
        best = max(
            [row for row in oos_horizons if row["rank_ic_mean"] is not None],
            key=lambda row: (
                float(row["rank_ic_mean"]),
                float(row["top3_beat_benchmark_rate_pct"] or 0),
            ),
            default={"horizon_sessions": 0},
        )
        train_by_horizon = {
            row["horizon_sessions"]: row for row in train_summary["horizons"]
        }
        primary_oos = next(
            (
                row for row in oos_horizons
                if int(row["horizon_sessions"]) == primary_horizon
            ),
            {},
        )
        primary_train = train_by_horizon.get(primary_horizon, {})
        if not primary_oos.get("samples") or not primary_train.get("samples"):
            state, label = "insufficient_samples", "缺少训练或样本外有效样本"
            reasons = ["无法确认10日主周期跨区间指示效应"]
        elif primary_oos.get("rank_ic_mean") is None or primary_train.get("rank_ic_mean") is None:
            state, label = "undefined_ic", "主周期IC不可计算，不作为零相关或失效证据"
            reasons = ["分数或收益横截面无差异，相关系数未定义"]
        elif (
            float(primary_oos.get("rank_ic_mean") or 0) > 0
            and float(primary_train.get("rank_ic_mean") or 0) > 0
            and float(primary_oos.get("top3_beat_benchmark_rate_pct") or 0) >= 55
        ):
            state = "stable_positive"
            label = "10日主周期存在跨区间正向指示"
            reasons = ["固定10日主周期 Rank IC 在训练与样本外均为正"]
        elif float(primary_oos.get("rank_ic_mean") or 0) > 0:
            state = "regime_dependent"
            label = "指示效应依赖市场阶段"
            reasons = ["10日主周期样本外排序改善，但训练段 Rank IC 未同步为正"]
        else:
            state = "weak"
            label = "尚无正向预测证据"
            reasons = ["10日主周期样本外 Rank IC 未形成稳定正值"]
        missing_labels = [row for row in records if not row["available"]]
        if any(row.get("rank_ic_samples", 0) < row.get("samples", 0)
               or row.get("top3_hit_samples", 0) < row.get("samples", 0)
               for row in (primary_train, primary_oos)) and state != "undefined_ic":
            state, label = "partial_statistics", "部分截面统计不可定义，仅作局部观察"
            reasons.append("常数截面或Top3边界并列已按指标单独剔除，不计为零或失败")
        if missing_labels:
            state, label = "incomplete_labels", "信号或未来标签不完整，仅展示完整截面统计"
            reasons.append(f"{len(missing_labels)}/{len(records)} 个期限截面缺信号或未来价格，未补位、未算作零收益")
        return {
            "method": "cross_sectional_rank_ic_top3_minus_bottom3_next_open",
            "statistics_policy": {
                "version": 1,
                "rank_ic": "average_ranks_constant_scores_or_returns_undefined",
                "ties": "ambiguous_membership_metric_unavailable_no_order_tiebreak",
                "spread": "at_least_six_assets_disjoint_top3_bottom3",
                "denominators": "valid_sections_per_metric",
                "ablation": "paired_valid_sections_per_metric",
                "beat_return_tolerance": 1e-12,
            },
            "label_coverage": {
                "expected_periods": len(records), "missing_periods": len(missing_labels),
                "policy": "frozen_signal_cross_section_complete_labels_per_horizon_no_replacement",
            },
            "sampling_sessions": self.prediction_sampling_sessions,
            "horizons": [5, 10, 20],
            "primary_horizon_sessions": primary_horizon,
            "train": train_summary,
            "out_of_sample": oos_summary,
            "all": all_summary,
            "best_observed_horizon_sessions": int(best.get("horizon_sessions") or 0),
            "factor_model": factor_model,
            "factor_effectiveness": factor_effectiveness,
            "confidence_diagnostics": confidence_diagnostics,
            "verdict": {"state": state, "label": label, "reasons": reasons},
            "note": "10日为冻结主周期；最佳观察周期只描述样本外现象，不用于反向选择参数。",
        }

    def run(
        self,
        *,
        benchmark: str = "510300",
        rebalance_days: int = 10,
        cost_bps: int = 25,
        as_of: Optional[str] = None,
    ) -> Dict[str, Any]:
        if rebalance_days not in self.supported_rebalances:
            raise ValueError("再平衡周期仅支持 5、10、20 个交易日")
        if cost_bps not in self.supported_cost_bps:
            raise ValueError("单边摩擦成本仅支持 10、25、50 bps")
        normalized_as_of = normalize_as_of(as_of)
        (
            benchmark_frame,
            trade_frames,
            signal_frames,
            failures,
            signal_failures,
        ) = self._load_frames(benchmark, normalized_as_of)
        benchmark_frame, calendar_audit = self._calendar_frame(benchmark_frame, trade_frames, normalized_as_of)
        dates = pd.to_datetime(benchmark_frame["date"])
        execution = RotationExecutionAudit(self.provider, trade_frames,
            dates.iloc[0].strftime("%Y-%m-%d"), dates.iloc[-1].strftime("%Y-%m-%d"))
        split_position = max(180, min(len(dates) - 40, int(len(dates) * 0.65)))
        split_date = pd.Timestamp(dates.iloc[split_position])
        variants = []
        trade_sets: Dict[str, list[Dict[str, Any]]] = {}
        frozen_trade_sets: Dict[str, list[Dict[str, Any]]] = {}
        for window in self.windows:
            window_trade_sets = self._window_trade_sets(
                benchmark_frame=benchmark_frame,
                trade_frames=trade_frames,
                signal_frames=signal_frames,
                weight_profiles=ROTATION_WEIGHT_PROFILES,
                window=window,
                rebalance_days=rebalance_days,
                cost_bps=cost_bps,
            )
            for profile, weights in ROTATION_WEIGHT_PROFILES.items():
                variant_id = f"{profile}-w{window}"
                frozen_trade_sets[variant_id] = window_trade_sets[profile]
                trades = execution.apply(window_trade_sets[profile])
                train = [row for row in trades if pd.Timestamp(row["exit_date"]) <= split_date]
                out_of_sample = [row for row in trades if pd.Timestamp(row["entry_date"]) > split_date]
                train_metrics = _metrics(train, rebalance_days)
                oos_metrics = _metrics(out_of_sample, rebalance_days)
                train_stability = self._training_stability(train, rebalance_days)
                oos_stability = self._training_stability(
                    out_of_sample, rebalance_days, blocks=2
                )
                variants.append({
                    "id": variant_id,
                    "profile": profile,
                    "window": window,
                    "weights": weights,
                    "train": train_metrics,
                    "train_stability": train_stability,
                    "out_of_sample": oos_metrics,
                    "out_of_sample_stability": oos_stability,
                    "selection_score": _round(
                        self._robust_selection_score(train_metrics, train_stability)
                    ) if self._can_score(train_metrics) else None,
                })
                trade_sets[variant_id] = trades
        profile_order = {profile: index for index, profile in enumerate(ROTATION_WEIGHT_PROFILES)}
        window_order = {window: index for index, window in enumerate(self.windows)}
        variants.sort(key=lambda row: (profile_order[row["profile"]], window_order[row["window"]]))
        eligible = [row for row in variants if self._can_score(row["train"])]
        if not eligible:
            raise MarketDataError("训练段缺少至少8个可完整核验的持仓期，或风险比率因零波动无法计算；未使用样本外表现反向选择参数")
        selected = dict(max(eligible, key=lambda row: (row["selection_score"], row["id"])))
        selected["qualification"] = self._training_qualification(
            selected["train"], selected["train_stability"]
        )
        selected_trades = trade_sets[selected["id"]]
        selected_oos_trades = [row for row in selected_trades if pd.Timestamp(row["entry_date"]) > split_date]
        expected_oos_periods = [
            (dates.iloc[position + 1].strftime("%Y-%m-%d"),
             dates.iloc[position + 1 + rebalance_days].strftime("%Y-%m-%d"))
            for position in range(max(selected["window"] + 5, 125), len(dates) - rebalance_days - 1, rebalance_days)
            if dates.iloc[position + 1] > split_date
        ]
        daily_risk = daily_rotation_risk(
            selected_oos_trades, trade_frames=trade_frames,
            benchmark_frame=benchmark_frame, expected_periods=expected_oos_periods,
            sessions=dates,
        )
        selected_train_trades = [
            row for row in selected_trades
            if pd.Timestamp(row["exit_date"]) <= split_date
        ]
        ensemble_trades = self._parameter_ensemble_trades(
            frozen_trade_sets,
            cost_bps=cost_bps,
            vote_source="buffered_selection",
        )
        online_consensus_trades = self._parameter_ensemble_trades(
            frozen_trade_sets,
            cost_bps=cost_bps,
            vote_source="current_leader",
        )
        ensemble_trades = execution.apply(ensemble_trades)
        online_consensus_trades = execution.apply(online_consensus_trades)
        ensemble_train_trades = [
            row for row in ensemble_trades
            if pd.Timestamp(row["exit_date"]) <= split_date
        ]
        ensemble_oos_trades = [
            row for row in ensemble_trades
            if pd.Timestamp(row["entry_date"]) > split_date
        ]
        online_consensus_train_trades = [
            row for row in online_consensus_trades
            if pd.Timestamp(row["exit_date"]) <= split_date
        ]
        online_consensus_oos_trades = [
            row for row in online_consensus_trades
            if pd.Timestamp(row["entry_date"]) > split_date
        ]
        ensemble_train_metrics = _metrics(ensemble_train_trades, rebalance_days)
        ensemble_oos_metrics = _metrics(ensemble_oos_trades, rebalance_days)
        selected_train_signal = self._ensemble_signal_summary(
            selected_train_trades, high_confidence_only=False
        )
        selected_oos_signal = self._ensemble_signal_summary(
            selected_oos_trades, high_confidence_only=False
        )
        ensemble_train_signal = self._ensemble_signal_summary(
            ensemble_train_trades, high_confidence_only=True
        )
        ensemble_oos_signal = self._ensemble_signal_summary(
            ensemble_oos_trades, high_confidence_only=True
        )
        online_consensus_train_metrics = _metrics(
            online_consensus_train_trades, rebalance_days
        )
        online_consensus_oos_metrics = _metrics(
            online_consensus_oos_trades, rebalance_days
        )
        online_consensus_train_all = self._ensemble_signal_summary(
            online_consensus_train_trades, high_confidence_only=False
        )
        online_consensus_train_signal = self._ensemble_signal_summary(
            online_consensus_train_trades, high_confidence_only=True
        )
        online_consensus_oos_all = self._ensemble_signal_summary(
            online_consensus_oos_trades, high_confidence_only=False
        )
        online_consensus_oos_signal = self._ensemble_signal_summary(
            online_consensus_oos_trades, high_confidence_only=True
        )
        ensemble_train_hit_delta = _difference(
            ensemble_train_signal["gross_beat_benchmark_rate_pct"],
            selected_train_signal["gross_beat_benchmark_rate_pct"],
        )
        ensemble_oos_hit_delta = _difference(
            ensemble_oos_signal["gross_beat_benchmark_rate_pct"],
            selected_oos_signal["gross_beat_benchmark_rate_pct"],
        )
        ensemble_training_qualified = (
            ensemble_train_metrics["execution_evidence"]["state"] == "checked"
            and
            (ensemble_train_metrics["excess_return_pct"] or 0) > 0
            and ensemble_train_signal["samples"] >= 20
            and (ensemble_train_signal["gross_beat_benchmark_rate_pct"] or 0) >= 55
            and ensemble_train_hit_delta is not None and ensemble_train_hit_delta >= 0
        )
        if ensemble_training_qualified and ensemble_oos_metrics["execution_evidence"]["state"] == "checked" and ensemble_oos_hit_delta is not None and ensemble_oos_hit_delta >= 3:
            ensemble_state = "observed_improvement"
            ensemble_label = "严格多数集成历史命中改善，仍需前向验证"
        elif ensemble_training_qualified:
            ensemble_state = "train_only"
            ensemble_label = "严格多数集成仅在训练段改善"
        else:
            ensemble_state = "diagnostic_only"
            ensemble_label = "严格多数集成未通过训练门槛"
        online_consensus_training_qualified = (
            online_consensus_train_metrics["execution_evidence"]["state"] == "checked"
            and
            (online_consensus_train_metrics["excess_return_pct"] or 0) > 0
            and online_consensus_train_signal["samples"] >= 20
            and (online_consensus_train_signal["gross_beat_benchmark_rate_pct"] or 0) >= 55
        )
        online_consensus_oos_hit_delta = _difference(
            online_consensus_oos_signal["gross_beat_benchmark_rate_pct"],
            online_consensus_oos_all["gross_beat_benchmark_rate_pct"],
        )
        if (
            online_consensus_training_qualified
            and online_consensus_oos_metrics["execution_evidence"]["state"] == "checked"
            and (online_consensus_oos_signal["gross_beat_benchmark_rate_pct"] or 0) >= 55
            and online_consensus_oos_hit_delta is not None and online_consensus_oos_hit_delta >= 0
        ):
            online_consensus_state = "observed_improvement"
            online_consensus_label = "当日静态投票历史命中改善，仍需前向验证"
        else:
            online_consensus_state = "not_validated"
            online_consensus_label = "当日静态投票未形成有效预测提升"
        if online_consensus_state == "observed_improvement":
            ensemble_verdict_state = "online_shadow_candidate"
            ensemble_verdict_label = online_consensus_label
        elif ensemble_state == "observed_improvement":
            ensemble_verdict_state = "stateful_shadow_only"
            ensemble_verdict_label = "持仓缓冲集成改善，但当日静态投票未验证"
        else:
            ensemble_verdict_state = "diagnostic_only"
            ensemble_verdict_label = "参数集成未形成可部署提升"
        if any(metrics["execution_evidence"]["state"] != "checked" for metrics in (ensemble_train_metrics, ensemble_oos_metrics, online_consensus_train_metrics, online_consensus_oos_metrics)):
            ensemble_verdict_state, ensemble_verdict_label = "execution_unverified", "集成成交依据不完整，仅保留诊断，不确认改善"
        parameter_ensemble = {
            "method": "equal_vote_3_profiles_x_3_windows",
            "variant_count": len(trade_sets),
            "majority_threshold": len(trade_sets) // 2 + 1,
            "selection_policy": "strict_majority_is_high_confidence",
            "stateful_vote_source": "buffered_model_selection",
            "training_qualified": ensemble_training_qualified,
            "train": {
                "strategy": ensemble_train_metrics,
                "all_signals": self._ensemble_signal_summary(
                    ensemble_train_trades, high_confidence_only=False
                ),
                "high_confidence": ensemble_train_signal,
                "selected_variant_baseline": selected_train_signal,
                "high_confidence_hit_delta_pct": ensemble_train_hit_delta,
            },
            "out_of_sample": {
                "strategy": ensemble_oos_metrics,
                "all_signals": self._ensemble_signal_summary(
                    ensemble_oos_trades, high_confidence_only=False
                ),
                "high_confidence": ensemble_oos_signal,
                "selected_variant_baseline": selected_oos_signal,
                "high_confidence_hit_delta_pct": ensemble_oos_hit_delta,
            },
            "cost_sensitivity": [
                self._stress_metrics(
                    ensemble_oos_trades,
                    rebalance_days=rebalance_days,
                    cost_bps=value,
                )
                for value in self.supported_cost_bps
            ],
            "online_current_leader": {
                "method": "current_period_leader_equal_vote_3_profiles_x_3_windows",
                "alignment": "same_as_online_snapshot_parameter_consensus",
                "training_qualified": online_consensus_training_qualified,
                "train": {
                    "strategy": online_consensus_train_metrics,
                    "all_signals": online_consensus_train_all,
                    "high_consensus": online_consensus_train_signal,
                },
                "out_of_sample": {
                    "strategy": online_consensus_oos_metrics,
                    "all_signals": online_consensus_oos_all,
                    "high_consensus": online_consensus_oos_signal,
                    "high_consensus_hit_delta_pct": online_consensus_oos_hit_delta,
                },
                "verdict": {
                    "state": online_consensus_state,
                    "label": online_consensus_label,
                    "deployment": "observation_only_until_forward_validated",
                },
            },
            "verdict": {
                "state": ensemble_verdict_state,
                "label": ensemble_verdict_label,
                "deployment": "shadow_only_because_development_holdout_is_reused",
            },
        }
        confirmation_trade_sets = self._confirmation_trade_sets(
            benchmark_frame=benchmark_frame,
            trade_frames=trade_frames,
            signal_frames=signal_frames,
            weights=selected["weights"],
            window=selected["window"],
            rebalance_days=rebalance_days,
            cost_bps=cost_bps,
        )
        confirmation_policies = []
        for policy, config in ROTATION_CONFIRMATION_POLICIES.items():
            trades = execution.apply(confirmation_trade_sets[policy])
            train = [row for row in trades if pd.Timestamp(row["exit_date"]) <= split_date]
            out_of_sample = [row for row in trades if pd.Timestamp(row["entry_date"]) > split_date]
            train_metrics = _metrics(train, rebalance_days)
            oos_metrics = _metrics(out_of_sample, rebalance_days)
            train_stability = self._training_stability(train, rebalance_days)
            oos_stability = self._training_stability(
                out_of_sample, rebalance_days, blocks=2
            )
            confirmation_policies.append({
                "id": policy,
                "label": config["label"],
                "description": config["description"],
                "train": train_metrics,
                "train_stability": train_stability,
                "out_of_sample": oos_metrics,
                "out_of_sample_stability": oos_stability,
                "selection_score": _round(
                    self._robust_selection_score(train_metrics, train_stability)
                ) if self._can_score(train_metrics) else None,
                "qualification": self._training_qualification(
                    train_metrics, train_stability
                ),
                "cost_sensitivity": [
                    self._stress_metrics(out_of_sample, rebalance_days=rebalance_days, cost_bps=value)
                    for value in self.supported_cost_bps
                ],
            })
        raw_policy = next(row for row in confirmation_policies if row["id"] == "raw")
        raw_oos = raw_policy["out_of_sample"]
        for policy in confirmation_policies:
            oos_metrics = policy["out_of_sample"]
            policy["delta_vs_raw"] = {
                "excess_return_pct": _difference(oos_metrics["excess_return_pct"], raw_oos["excess_return_pct"]),
                "max_drawdown_improvement_pct": _difference(raw_oos["max_drawdown_pct"], oos_metrics["max_drawdown_pct"]),
                "turnover_rate_pct": _difference(oos_metrics["turnover_rate_pct"], raw_oos["turnover_rate_pct"]),
            }
        best_oos_confirmation = max(
            confirmation_policies,
            key=lambda row: (row["out_of_sample"]["excess_return_pct"] if row["out_of_sample"]["excess_return_pct"] is not None else -math.inf, row["id"]),
        )
        qualified_confirmation = [
            row for row in confirmation_policies
            if row["qualification"]["state"] == "qualified"
            and row["train"]["trades"] >= 8
        ]
        selected_confirmation = dict(max(
            qualified_confirmation or [raw_policy],
            key=lambda row: (row["selection_score"], row["id"]),
        ))
        selected_confirmation_oos = selected_confirmation["out_of_sample"]
        confirmation_delta = selected_confirmation["delta_vs_raw"]
        if selected_confirmation_oos["execution_state"] == "incomplete":
            confirmation_state, confirmation_label = "incomplete_execution", "所选确认策略缺成交证据，无法验证改善"
        elif selected_confirmation_oos["execution_evidence"]["state"] != "checked":
            confirmation_state, confirmation_label = "theoretical_only", "确认策略限价依据不完整，仅作理论对照"
        elif raw_oos["execution_state"] != "complete" or raw_oos["execution_evidence"]["state"] != "checked":
            confirmation_state, confirmation_label = "baseline_unverified", "原始对照策略成交依据不完整，不能确认改善"
        elif selected_confirmation["id"] == "raw":
            confirmation_state = "baseline_retained"
            confirmation_label = "训练段继续选择原始排序"
        elif (
            (confirmation_delta["excess_return_pct"] or 0) > 0
            and confirmation_delta["max_drawdown_improvement_pct"] is not None and confirmation_delta["max_drawdown_improvement_pct"] >= 0
        ):
            confirmation_state = "improved"
            confirmation_label = "确认层同时改善收益与回撤"
        elif (
            (confirmation_delta["excess_return_pct"] or 0) > 0
            or (confirmation_delta["max_drawdown_improvement_pct"] or 0) > 0
        ):
            confirmation_state = "mixed"
            confirmation_label = "确认层部分改善"
        else:
            confirmation_state = "not_improved"
            confirmation_label = "确认层暂未改善"
        stress_tests = [
            self._stress_metrics(selected_oos_trades, rebalance_days=rebalance_days, cost_bps=value)
            for value in self.supported_cost_bps
        ]
        prediction_diagnostics = self._prediction_diagnostics(
            benchmark_frame=benchmark_frame,
            trade_frames=trade_frames,
            signal_frames=signal_frames,
            weights=selected["weights"],
            window=selected["window"],
            split_date=split_date,
        )
        best_prediction_horizon = int(
            prediction_diagnostics["best_observed_horizon_sessions"] or 0
        )
        best_prediction_row = next(
            (
                row
                for row in prediction_diagnostics["out_of_sample"]["horizons"]
                if int(row["horizon_sessions"]) == best_prediction_horizon
            ),
            {},
        )
        positive_share = (
            sum(row["out_of_sample"]["excess_return_pct"] > 0 for row in eligible) / len(eligible)
            if all(row["out_of_sample"]["execution_state"] == "complete" for row in eligible) else None
        )
        positive_share_pct = _round(positive_share * 100) if positive_share is not None else None
        start_date = pd.Timestamp(dates.iloc[0])
        end_date = pd.Timestamp(dates.iloc[-1])
        coverage_years = max((end_date - start_date).days / 365.25, 0)
        selected_oos = selected["out_of_sample"]
        index_signal_count = sum(
            frame.attrs.get("rotation_signal_mode") == "industry_index"
            for frame in signal_frames.values()
        )
        signal_fallback_count = sum(
            frame.attrs.get("rotation_signal_mode") == "etf_fallback"
            for frame in signal_frames.values()
        )
        signal_adjust_values = {
            str(frame.attrs.get("adjust") or "unknown")
            for frame in signal_frames.values()
        }
        signal_adjust = (
            next(iter(signal_adjust_values))
            if len(signal_adjust_values) == 1 else "mixed"
        )
        universe_coverage = len(trade_frames) / max(len(self.universe), 1)
        expected_index_signals = sum(
            item.code in signal_frames and item.has_industry_index_signal
            for item in self.universe
        )
        configured_signal_proxy_count = sum(
            item.code in signal_frames
            and item.has_industry_index_signal
            and not self.provider.supports_signal_kline(item.resolved_signal_code)
            for item in self.universe
        )
        index_signal_coverage = (
            index_signal_count / expected_index_signals
            if expected_index_signals else 1.0
        )
        trade_asset_signal_count = sum(
            frame.attrs.get("rotation_signal_mode") == "trade_asset"
            for frame in signal_frames.values()
        )
        effective_signal_count = (
            index_signal_count + signal_fallback_count + trade_asset_signal_count
        )
        effective_signal_coverage = (
            effective_signal_count / max(len(signal_frames), 1)
        )
        if index_signal_count and signal_fallback_count:
            signal_state = "partial"
        elif signal_fallback_count:
            signal_state = "fallback"
        else:
            signal_state = "complete"
        factor_effectiveness = prediction_diagnostics["factor_effectiveness"]
        confidence_diagnostics = prediction_diagnostics["confidence_diagnostics"]
        stable_factor_count = sum(
            row["state"] == "stable_positive"
            for row in factor_effectiveness["factors"]
        )
        limitations = [
            "fixed_current_etf_universe_has_survivorship_bias",
            "historical_industry_breadth_is_confirmation_only",
            "historical_valuation_and_fundamentals_unavailable_excluded",
            "maximum_800_recent_bars_from_current_desk_interface",
            "development_holdout_has_been_reused_not_blind",
            "prediction_samples_overlap_by_horizon_effective_count_reported",
            "stateful_buffered_ensemble_is_not_the_same_as_online_current_leader_vote",
            "round_trip_cost_is_charged_when_selected_etf_changes",
            "daily_risk_uses_close_and_execution_open_not_intraday_extremes",
            "missing_execution_prices_do_not_rewrite_signal_decisions",
            "actual_switch_legs_only_hold_and_terminal_prices_are_marks_not_orders",
            "separate_raw_open_limit_pairs_positive_volume_not_fill_guarantee",
            "missing_limit_pairs_are_theoretical_known_execution_failures_propagate_unknown_capital",
            "round_trip_fee_reservation_is_not_actual_order_cost_or_terminal_liquidation",
            "prediction_statistics_use_complete_frozen_cross_sections_only",
            "scheduled_decision_gaps_retained_and_holding_uncertainty_propagated",
            "empty_statistics_are_null_ratios_require_two_samples_and_nonzero_dispersion",
            "sharpe_assumes_zero_risk_free_rate_and_population_dispersion",
            "sse_calendar_only_not_overseas_underlying_market_calendar",
            "calendar_is_current_source_history_not_point_in_time_announcements",
            "calendar_window_bounded_by_loaded_history_not_full_inception_history",
            "results_are_research_evidence_not_live_trading_advice",
        ]
        if index_signal_count:
            limitations.append(
                "industry_index_signals_use_close_and_etfs_execute_at_next_session_open"
            )
        if signal_fallback_count:
            limitations.append("same_industry_etf_proxy_used_when_index_unavailable")
        reasons = []
        if selected["train"]["execution_evidence"]["state"] != "checked" or selected_oos["execution_evidence"]["state"] != "checked":
            reasons.append("买卖量价或历史限价证据不完整；缺配对仅为理论测算，已知触限或缺量不确认收益")
        if daily_risk["strategy"]["state"] != "complete":
            reasons.append("每日盯市存在行情或持仓区间缺口，无法确认完整样本外回撤")
        if daily_risk["benchmark"]["state"] != "complete":
            reasons.append("基准每日盯市存在行情缺口，无法确认完整基准回撤")
        if universe_coverage < self.evidence_coverage_threshold:
            reasons.append(
                f"有效 ETF 覆盖 {len(trade_frames)}/{len(self.universe)}（{universe_coverage * 100:.1f}%），"
                f"低于 {self.evidence_coverage_threshold * 100:.0f}% 证据门槛"
            )
        if effective_signal_coverage < self.evidence_coverage_threshold:
            reasons.append(
                f"有效价格信号覆盖 {effective_signal_count}/{len(signal_frames)}（{effective_signal_coverage * 100:.1f}%），"
                f"低于 {self.evidence_coverage_threshold * 100:.0f}% 证据门槛"
            )
        if coverage_years < 5:
            reasons.append(f"历史覆盖仅 {coverage_years:.1f} 年，低于五年稳健性门槛")
        if selected_oos["trades"] < 30:
            reasons.append(f"样本外持有期仅 {selected_oos['trades']} 期，低于 30 期最低观察门槛")
        if len(eligible) < len(variants):
            reasons.append(f"训练可评分参数仅 {len(eligible)}/{len(variants)} 组，其余存在成交缺口或统计不足；参数平台比例只覆盖可评分组")
        if positive_share is None:
            reasons.append("部分参数样本外成交证据不完整，不能确认参数平台胜率")
        elif positive_share < 0.6:
            reasons.append(f"训练可评分的 {len(eligible)}/{len(variants)} 组参数中，仅 {positive_share * 100:.0f}% 在样本外跑赢基准，参数平台不足")
        if selected["qualification"]["state"] != "qualified":
            reasons.append(
                "入选候选训练段收益 "
                f"{selected['train']['total_return_pct']:+.2f}%、超额 "
                f"{selected['train']['excess_return_pct']:+.2f}%，但分段稳定性未通过门槛"
            )
        if float(
            selected["out_of_sample_stability"].get("positive_excess_share_pct") or 0
        ) < 100:
            reasons.append(
                "样本外两个时间分段并非全部取得正超额，收益仍可能集中于单一阶段"
            )
        if prediction_diagnostics["verdict"]["state"] != "stable_positive":
            reasons.extend(prediction_diagnostics["verdict"]["reasons"])
        reasons.append("当前开发样本外区间已参与本轮框架评估，后续只能用全新前向信号验证")
        if reasons:
            verdict = "insufficient_evidence"
            verdict_label = "证据不足"
        elif (stress_tests[-1]["excess_return_pct"] or 0) > 0 and positive_share is not None and positive_share >= 0.6:
            verdict = "promising"
            verdict_label = "具备继续验证价值"
        else:
            verdict = "fragile"
            verdict_label = "稳健性偏弱"
        data_quality = {
            "state": "complete" if not failures and not signal_failures and not calendar_audit["missing_benchmark_dates"] else "partial",
            "benchmark_rows": len(benchmark_frame) - len(calendar_audit["missing_benchmark_dates"]),
            "calendar_sessions": len(benchmark_frame),
            "coverage_start": start_date.strftime("%Y-%m-%d"),
            "coverage_end": end_date.strftime("%Y-%m-%d"),
            "coverage_years": _round(coverage_years, 1),
            "universe_size": len(self.universe),
            "successful_symbols": len(trade_frames),
            "failed_symbols": len(failures),
            "minimum_cross_section_symbols": self._minimum_cross_section_size(len(self.universe)),
            "universe_coverage_pct": _round(universe_coverage * 100, 1),
            "evidence_coverage_threshold_pct": _round(self.evidence_coverage_threshold * 100, 1),
            "signal_state": signal_state,
            "signal_policy": "sw_industry_index_preferred_same_industry_etf_proxy_allowed",
            "expected_index_signals": expected_index_signals,
            "index_signal_count": index_signal_count,
            "signal_fallback_count": signal_fallback_count,
            "configured_signal_proxy_count": configured_signal_proxy_count,
            "trade_asset_signal_count": trade_asset_signal_count,
            "effective_signal_count": effective_signal_count,
            "signal_failed_symbols": len(signal_failures),
            "index_signal_coverage_pct": _round(index_signal_coverage * 100, 1),
            "effective_signal_coverage_pct": _round(effective_signal_coverage * 100, 1),
            "signal_adjust": signal_adjust,
            "adjust": benchmark_frame.attrs.get("adjust", "unknown"),
            "data_endpoint": benchmark_frame.attrs.get("data_endpoint", ""),
            "factor_model_state": prediction_diagnostics.get("factor_model", {}).get(
                "state", "fast_factors_only"
            ),
            "active_factor_count": prediction_diagnostics.get("factor_model", {}).get(
                "active_factor_count", 5
            ),
            "configured_factor_count": prediction_diagnostics.get("factor_model", {}).get(
                "configured_factor_count", 7
            ),
        }
        unresolved_decisions = [
            {**{key: row[key] for key in ("signal_date", "entry_date", "exit_date", "symbol", "name")},
             "reason": row.get("decision_issue", "missing_execution_price")}
            for row in selected_oos_trades
            if row["net_return"] is None or row["benchmark_return"] is None
        ]
        execution_audit = {
            "calendar_policy": "independent_exchange_calendar_exact_dates",
            "calendar": calendar_audit,
            "selection_policy": "signal_close_only_no_future_price_filter",
            "planned_oos_periods": len(selected_oos_trades),
            "resolved_oos_periods": selected_oos["resolved_periods"],
            "unresolved_oos_periods": selected_oos["unresolved_periods"],
            "unresolved_decisions": unresolved_decisions,
            "missing_signal_periods": sum(row.get("decision_issue") in {"insufficient_signal_coverage", "missing_benchmark_signal"} for row in selected_oos_trades),
            "uncertain_holding_periods": sum(row.get("decision_issue") in {"ambiguous_holding_state", "uncertain_turnover"} for row in selected_oos_trades),
            "equal_weight_missing_periods": sum(row["equal_weight_return"] is None for row in selected_oos_trades),
            "prediction_label_coverage": prediction_diagnostics["label_coverage"],
            "transition_policy": "initial_buy_switch_sell_old_buy_new_hold_and_terminal_mark_only",
            "trade_evidence": {"train": selected["train"]["execution_evidence"],
                               "out_of_sample": selected_oos["execution_evidence"],
                               "feeds": list(execution.feeds.values()),
                               "checks": [{**check, "partition": "train" if pd.Timestamp(row["exit_date"]) <= split_date
                                           else "out_of_sample" if pd.Timestamp(row["entry_date"]) > split_date else "purged"}
                                          for row in selected_trades for check in row["execution_checks"]]},
        }
        payload = {
            "engine": {"name": self.engine_name, "version": self.engine_version},
            "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
            "as_of": end_date.strftime("%Y-%m-%d"),
            "requested_as_of": normalized_as_of,
            "data_source": self.provider.name,
            "hypothesis": "基于当日收盘可见的动量、相对强弱、趋势质量、成交连续性与拥挤/条件反转排名，在下一交易日开盘执行对应 ETF 后能取得相对基准收益；估值与基本面仅在具备点时证据时启用。",
            "rules": {
                "signal_timing": "signal_at_close_t_execute_next_session_open",
                "execution_calendar": "independent_exchange_calendar_exact_dates",
                "holding_period_sessions": rebalance_days,
                "portfolio": "top_1_equal_notional",
                "cost_bps_per_side": cost_bps,
                "switch_score_gap": self.switch_score_gap,
                "hold_rank_limit": self.hold_rank_limit,
                "minimum_cross_section_coverage_pct": _round(self.minimum_cross_section_coverage * 100, 1),
                "evidence_coverage_threshold_pct": _round(self.evidence_coverage_threshold * 100, 1),
                "transaction_cost": "charged_when_selected_etf_changes",
                "candidate_selection": "signal_date_information_only_before_execution_labels",
                "missing_execution": "retain_planned_decision_no_replacement_no_cash_imputation",
                "missing_decision": "retain_full_calendar_propagate_possible_holdings_until_unambiguous",
                "training_gate": "positive_return_excess_and_training_block_stability",
                "primary_prediction_horizon_sessions": self.primary_prediction_horizon,
                "factor_effectiveness": "standalone_and_leave_one_out_diagnostic_only",
                "confidence_filter": "threshold_from_training_feature_distribution_without_return_optimization",
                "confidence_deployment": "shadow_only_until_30_new_non_overlapping_signals",
                "parameter_ensemble": "equal_vote_across_3_weight_profiles_and_3_windows_with_stateful_and_stateless_results_separated",
                "ensemble_high_confidence": "strict_majority_at_least_5_of_9_votes",
                "online_consensus_validation": "current_period_model_leaders_without_holding_state",
                "historical_industry_factor": "confirmation_only_no_lookahead",
                "historical_slow_factors": "excluded_without_point_in_time_evidence",
                "factor_model": "seven_factor_with_missing_slow_factor_renormalization",
                "price_signal_source": "sw_2021_level_1_index_with_explicit_etf_fallback",
                "etf_signal_proxy": "same_industry_or_declared_proxy_etf_when_index_unavailable",
                "volume_and_execution_source": "tradable_etf",
                "confirmation_history_sessions": 20,
                "confirmation_policies": list(ROTATION_CONFIRMATION_POLICIES),
                "confirmation_policy_selection": "training_selection_score_then_oos_validation",
                "confirmed_only_cash_rule": "hold_cash_when_no_confirmed_candidate",
                "split": {"method": "chronological_holdout", "train_share": 0.65, "split_date": split_date.strftime("%Y-%m-%d")},
            },
            "data_quality": data_quality,
            "execution_audit": execution_audit,
            "selected_variant": selected,
            "baseline_variant_id": "balanced-w60",
            "parameter_surface": variants,
            "parameter_ensemble": parameter_ensemble,
            "confirmation_comparison": {
                "base_variant_id": selected["id"],
                "selected_policy": selected_confirmation,
                "policies": confirmation_policies,
                "verdict": {
                    "state": confirmation_state,
                    "label": confirmation_label,
                    "selected_by": "training_selection_score",
                    "oos_excess_delta_pct": confirmation_delta["excess_return_pct"],
                    "oos_drawdown_improvement_pct": confirmation_delta["max_drawdown_improvement_pct"],
                },
                "oos_observation": {
                    "policy_id": best_oos_confirmation["id"],
                    "policy_label": best_oos_confirmation["label"],
                    "excess_return_pct": best_oos_confirmation["out_of_sample"]["excess_return_pct"],
                    "excess_delta_vs_raw_pct": best_oos_confirmation["delta_vs_raw"]["excess_return_pct"],
                    "post_hoc_only": True,
                },
            },
            "prediction_diagnostics": prediction_diagnostics,
            "stress_tests": stress_tests,
            "equity_curve": self._equity_curve(selected_oos_trades),
            "daily_risk": daily_risk,
            "verdict": {
                "state": verdict,
                "label": verdict_label,
                "reasons": reasons or ["样本外与摩擦压力测试满足当前项目门槛"],
            },
            "summary": {
                "selected_variant_id": selected["id"],
                "selected_profile": selected["profile"],
                "selected_window": selected["window"],
                "candidate_state": selected["qualification"]["state"],
                "oos_return_pct": selected_oos["total_return_pct"],
                "oos_benchmark_return_pct": selected_oos["benchmark_return_pct"],
                "oos_excess_return_pct": selected_oos["excess_return_pct"],
                "oos_max_drawdown_pct": selected_oos["max_drawdown_pct"],
                "oos_trades": selected_oos["trades"],
                "oos_positive_block_share_pct": selected[
                    "out_of_sample_stability"
                ]["positive_excess_share_pct"],
                "positive_variant_share_pct": positive_share_pct,
                "scorable_variant_count": len(eligible),
                "total_variant_count": len(variants),
                "selected_confirmation_policy": selected_confirmation["id"],
                "selected_confirmation_label": selected_confirmation["label"],
                "confirmation_oos_return_pct": selected_confirmation_oos["total_return_pct"],
                "confirmation_oos_excess_return_pct": selected_confirmation_oos["excess_return_pct"],
                "confirmation_oos_max_drawdown_pct": selected_confirmation_oos["max_drawdown_pct"],
                "confirmation_oos_excess_delta_pct": confirmation_delta["excess_return_pct"],
                "prediction_state": prediction_diagnostics["verdict"]["state"],
                "prediction_label": prediction_diagnostics["verdict"]["label"],
                "primary_prediction_horizon_sessions": self.primary_prediction_horizon,
                "primary_oos_rank_ic": factor_effectiveness["combined"]["out_of_sample"]["rank_ic_mean"],
                "primary_oos_top3_beat_benchmark_rate_pct": factor_effectiveness["combined"]["out_of_sample"]["top3_beat_benchmark_rate_pct"],
                "primary_oos_effective_samples": factor_effectiveness["combined"]["out_of_sample"]["effective_non_overlapping_samples"],
                "stable_factor_count": stable_factor_count,
                "high_confidence_state": confidence_diagnostics["verdict"]["state"],
                "high_confidence_label": confidence_diagnostics["verdict"]["label"],
                "high_confidence_oos_samples": confidence_diagnostics["out_of_sample"]["high_confidence"]["samples"],
                "high_confidence_oos_effective_samples": confidence_diagnostics["out_of_sample"]["high_confidence"]["effective_non_overlapping_samples"],
                "high_confidence_oos_top3_beat_benchmark_rate_pct": confidence_diagnostics["out_of_sample"]["high_confidence"]["top3_beat_benchmark_rate_pct"],
                "high_confidence_oos_hit_delta_pct": confidence_diagnostics["out_of_sample"]["high_confidence"]["top3_hit_delta_pct"],
                "ensemble_state": parameter_ensemble["verdict"]["state"],
                "ensemble_label": parameter_ensemble["verdict"]["label"],
                "ensemble_oos_return_pct": ensemble_oos_metrics["total_return_pct"],
                "ensemble_oos_excess_return_pct": ensemble_oos_metrics["excess_return_pct"],
                "ensemble_oos_max_drawdown_pct": ensemble_oos_metrics["max_drawdown_pct"],
                "ensemble_high_confidence_oos_samples": ensemble_oos_signal["samples"],
                "ensemble_high_confidence_oos_hit_rate_pct": ensemble_oos_signal["gross_beat_benchmark_rate_pct"],
                "ensemble_high_confidence_oos_hit_delta_pct": ensemble_oos_hit_delta,
                "online_consensus_oos_return_pct": online_consensus_oos_metrics["total_return_pct"],
                "online_consensus_oos_excess_return_pct": online_consensus_oos_metrics["excess_return_pct"],
                "online_consensus_oos_max_drawdown_pct": online_consensus_oos_metrics["max_drawdown_pct"],
                "online_consensus_oos_samples": online_consensus_oos_signal["samples"],
                "online_consensus_oos_hit_rate_pct": online_consensus_oos_signal["gross_beat_benchmark_rate_pct"],
                "online_consensus_oos_hit_delta_pct": online_consensus_oos_hit_delta,
                "best_observed_horizon_sessions": best_prediction_horizon,
                "best_oos_rank_ic": best_prediction_row.get("rank_ic_mean"),
                "best_oos_top3_beat_benchmark_rate_pct": best_prediction_row.get(
                    "top3_beat_benchmark_rate_pct"
                ),
            },
            "failures": failures,
            "signal_failures": signal_failures,
            "limitations": limitations,
        }
        payload["snapshot"] = build_analysis_snapshot(
            analysis_name=self.engine_name,
            analysis_version=self.engine_version,
            parameters={
                "benchmark": benchmark,
                "rebalanceDays": rebalance_days,
                "costBps": cost_bps,
                "asOf": normalized_as_of,
            },
            frame=benchmark_frame,
            requested_bars=self.request_limit,
            provider_name=self.provider.name,
            input_summary={
                "universe_size": len(self.universe),
                "successful_symbols": len(trade_frames),
                "index_signal_count": index_signal_count,
                "signal_fallback_count": signal_fallback_count,
                "effective_signal_count": effective_signal_count,
                "effective_signal_coverage_pct": _round(effective_signal_coverage * 100, 1),
                "parameter_variants": len(variants),
                "confirmation_policies": len(confirmation_policies),
                "active_factor_count": prediction_diagnostics.get("factor_model", {}).get(
                    "active_factor_count", 0
                ),
            },
            result_summary={
                "verdict": verdict,
                "selected_variant": selected["id"],
                "out_of_sample": selected_oos,
                "execution_audit": execution_audit,
                "daily_risk": {key: daily_risk[key] for key in ("sampling", "strategy", "benchmark")},
                "positive_variant_share_pct": positive_share_pct,
                "selected_confirmation_policy": selected_confirmation["id"],
                "confirmation_verdict": confirmation_state,
                "prediction_verdict": prediction_diagnostics["verdict"]["state"],
                "best_observed_horizon_sessions": best_prediction_horizon,
            },
        )
        return payload
