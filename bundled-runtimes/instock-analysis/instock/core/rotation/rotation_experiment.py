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
    return calculate_rotation_metrics(trades, period_sessions=rebalance_days)


class RotationExperiment:
    """Stress-test rotation parameters using only data available at each signal date."""

    engine_name = "instock-rotation-experiment"
    engine_version = "2.1.1"
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
        held_symbols: Dict[str, Optional[str]] = {profile: None for profile in engines}
        for position in range(warmup, len(benchmark_dates) - rebalance_days - 1, rebalance_days):
            signal_date = benchmark_dates[position]
            entry_date = benchmark_dates[position + 1]
            exit_date = benchmark_dates[position + 1 + rebalance_days]
            benchmark_slice = benchmark_frame.iloc[:position + 1]
            benchmark_metrics = metric_engine._benchmark_metrics(benchmark_slice, window)
            benchmark_entry = self._valid_execution_price(benchmark_opens[position + 1])
            benchmark_exit = self._valid_execution_price(benchmark_opens[position + 1 + rebalance_days])
            if benchmark_entry is None or benchmark_exit is None:
                continue

            raw_rows = []
            executable: Dict[str, tuple[float, float]] = {}
            period_returns = []
            for item in self.universe:
                prepared_trade = prepared_trades.get(item.code)
                prepared_signal = prepared_signals.get(item.code)
                if prepared_trade is None or prepared_signal is None:
                    continue
                trade_source, trade_dates, trade_opens = prepared_trade
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
                entry_position = int(trade_dates.searchsorted(entry_date, side="left"))
                exit_position = int(trade_dates.searchsorted(exit_date, side="left"))
                if entry_position >= len(trade_dates) or trade_dates[entry_position] != entry_date:
                    continue
                if exit_position >= len(trade_dates) or trade_dates[exit_position] != exit_date:
                    continue
                entry_price = self._valid_execution_price(trade_opens[entry_position])
                exit_price = self._valid_execution_price(trade_opens[exit_position])
                if entry_price is None or exit_price is None:
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
                executable[item.code] = (entry_price, exit_price)
                period_returns.append(exit_price / entry_price - 1)
            if len(raw_rows) < self._minimum_cross_section_size(len(self.universe)):
                continue

            factor_frame = metric_engine._factor_frame(raw_rows)
            benchmark_return = benchmark_exit / benchmark_entry - 1
            equal_weight_return = float(np.mean(period_returns))
            for profile, engine in engines.items():
                rankings = engine._score_factor_frame(factor_frame)
                leader = rankings[0]
                selected = self._select_with_buffer(rankings, held_symbols[profile])
                switched = held_symbols[profile] != selected["code"]
                transaction_cost = round_trip_cost(cost_bps, executed=switched)
                entry_price, exit_price = executable[selected["code"]]
                leader_entry_price, leader_exit_price = executable[leader["code"]]
                gross_return = exit_price / entry_price - 1
                net_return = gross_return - transaction_cost
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
                    "current_leader_gross_return": (
                        leader_exit_price / leader_entry_price - 1
                    ),
                    "switched": switched,
                    "transaction_cost": transaction_cost,
                    "gross_return": gross_return,
                    "net_return": net_return,
                    "benchmark_return": benchmark_return,
                    "equal_weight_return": equal_weight_return,
                })
                held_symbols[profile] = selected["code"]
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
        output: list[Dict[str, Any]] = []
        for signal_date in sorted(by_date):
            options = by_date[signal_date]
            if len(options) != variant_count:
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
                        "gross_return": float(row["current_leader_gross_return"]),
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
                        "gross_return": float(row["gross_return"]),
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
            switched = held_symbol != selected_symbol
            transaction_cost = round_trip_cost(cost_bps, executed=switched)
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
                "net_return": selected_candidate["gross_return"] - transaction_cost,
            })
            output.append(item)
            held_symbol = selected_symbol
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
            benchmark_metrics = engine._benchmark_metrics(benchmark_slice, window)
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
        held_symbols: Dict[str, Optional[str]] = {
            policy: None for policy in ROTATION_CONFIRMATION_POLICIES
        }
        for position in range(warmup, len(benchmark_dates) - rebalance_days - 1, rebalance_days):
            signal_date = benchmark_dates[position]
            entry_date = benchmark_dates[position + 1]
            exit_date = benchmark_dates[position + 1 + rebalance_days]
            benchmark_entry = self._valid_execution_price(benchmark_opens[position + 1])
            benchmark_exit = self._valid_execution_price(benchmark_opens[position + 1 + rebalance_days])
            if benchmark_entry is None or benchmark_exit is None:
                continue

            executable: Dict[str, tuple[float, float]] = {}
            period_returns = []
            executable_codes = set()
            for item in self.universe:
                prepared = prepared_trades.get(item.code)
                if prepared is None:
                    continue
                _, source_dates, source_opens = prepared
                entry_position = int(source_dates.searchsorted(entry_date, side="left"))
                exit_position = int(source_dates.searchsorted(exit_date, side="left"))
                if entry_position >= len(source_dates) or source_dates[entry_position] != entry_date:
                    continue
                if exit_position >= len(source_dates) or source_dates[exit_position] != exit_date:
                    continue
                entry_price = self._valid_execution_price(source_opens[entry_position])
                exit_price = self._valid_execution_price(source_opens[exit_position])
                if entry_price is None or exit_price is None:
                    continue
                executable[item.code] = (entry_price, exit_price)
                executable_codes.add(item.code)
                period_returns.append(exit_price / entry_price - 1)
            current_rankings = [
                dict(row) for row in rankings_at(position)
                if row["code"] in executable_codes
            ]
            for index, row in enumerate(current_rankings, start=1):
                row["rank"] = index
            if len(current_rankings) < self._minimum_cross_section_size(len(self.universe)):
                continue

            history = []
            for history_position in range(max(0, position - 19), position + 1):
                historical_rankings = rankings_at(history_position)
                if historical_rankings:
                    history.append({"rankings": historical_rankings})
            engine._attach_rotation_confirmation(current_rankings, history)
            benchmark_return = benchmark_exit / benchmark_entry - 1
            equal_weight_return = float(np.mean(period_returns))

            for policy in ROTATION_CONFIRMATION_POLICIES:
                selected = self._select_confirmation_policy(
                    current_rankings,
                    held_symbols[policy],
                    policy,
                )
                selected_symbol = str(selected["code"]) if selected else None
                switched = held_symbols[policy] != selected_symbol
                transaction_cost = round_trip_cost(cost_bps, executed=switched)
                if selected:
                    entry_price, exit_price = executable[selected_symbol]
                    gross_return = exit_price / entry_price - 1
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
                    "net_return": gross_return - transaction_cost,
                    "benchmark_return": benchmark_return,
                    "equal_weight_return": equal_weight_return,
                })
                held_symbols[policy] = selected_symbol
        return trade_sets

    @staticmethod
    def _selection_score(metrics: Mapping[str, Any]) -> float:
        if int(metrics.get("trades") or 0) < 8:
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
                "positive_excess_share_pct": 0.0,
                "latest_block_excess_return_pct": 0.0,
                "worst_block_excess_return_pct": 0.0,
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
        positive = sum(float(row["excess_return_pct"]) > 0 for row in metrics)
        return {
            "blocks": metrics,
            "positive_excess_blocks": positive,
            "positive_excess_share_pct": _round(positive / max(len(metrics), 1) * 100),
            "latest_block_excess_return_pct": _round(
                metrics[-1]["excess_return_pct"] if metrics else 0.0
            ),
            "worst_block_excess_return_pct": _round(
                min((row["excess_return_pct"] for row in metrics), default=0.0)
            ),
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
            )
            item["transaction_cost"] = transaction_cost
            item["net_return"] = float(row["gross_return"]) - transaction_cost
            stressed.append(item)
        return {"cost_bps": cost_bps, **_metrics(stressed, rebalance_days)}

    @staticmethod
    def _equity_curve(trades: Sequence[Mapping[str, Any]]) -> list[Dict[str, Any]]:
        strategy_equity = 1.0
        benchmark_equity = 1.0
        equal_weight_equity = 1.0
        points = []
        for row in trades:
            strategy_equity *= 1 + float(row["net_return"])
            benchmark_equity *= 1 + float(row["benchmark_return"])
            equal_weight_equity *= 1 + float(row["equal_weight_return"])
            points.append({
                "date": row["exit_date"],
                "strategy": _round(strategy_equity, 4),
                "benchmark": _round(benchmark_equity, 4),
                "equal_weight": _round(equal_weight_equity, 4),
                "symbol": row["symbol"],
            })
        return points

    @staticmethod
    def _ranking_effect(
        scores: Sequence[float],
        returns: Sequence[float],
        benchmark_return: float,
    ) -> Dict[str, Any]:
        """Measure one cross-sectional score without using future data in it."""

        frame = pd.DataFrame({"score": scores, "return": returns}).replace(
            [np.inf, -np.inf], np.nan
        ).dropna()
        if len(frame) < 4:
            return {"available": False}
        rank_ic = (
            frame["score"].rank().corr(frame["return"].rank())
            if frame["score"].nunique() > 1 and frame["return"].nunique() > 1
            else 0.0
        )
        ordered = frame.sort_values("score", ascending=False)
        top3 = float(ordered["return"].head(3).mean())
        bottom3 = float(ordered["return"].tail(3).mean())
        leader_return = float(ordered["return"].iloc[0])
        median_return = float(frame["return"].median())
        return {
            "available": True,
            "rank_ic": float(rank_ic) if math.isfinite(float(rank_ic)) else 0.0,
            "top3_minus_bottom3": top3 - bottom3,
            "leader_beat_median": leader_return > median_return,
            "leader_beat_benchmark": leader_return > benchmark_return,
            "top3_beat_median": top3 > median_return,
            "top3_beat_benchmark": top3 > benchmark_return,
        }

    @staticmethod
    def _wilson_interval_pct(successes: int, samples: int) -> tuple[float, float]:
        """Return a compact 95% Wilson interval for a hit rate."""

        if samples <= 0:
            return 0.0, 0.0
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
        rank_ics = [float(row["rank_ic"]) for row in available]
        hits = sum(bool(row["top3_beat_benchmark"]) for row in available)
        non_overlapping_groups = cls._non_overlapping_effect_groups(
            available, horizon=horizon
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
            "effective_non_overlapping_samples": effective_samples,
            "rank_ic_mean": _round(np.mean(rank_ics) if rank_ics else 0.0, 4),
            "rank_ic_positive_rate_pct": _round(
                np.mean([value > 0 for value in rank_ics]) * 100 if rank_ics else 0.0
            ),
            "top3_minus_bottom3_mean_pct": _round(
                np.mean([float(row["top3_minus_bottom3"]) for row in available]) * 100
                if available else 0.0
            ),
            "top3_beat_benchmark_rate_pct": _round(
                hits / len(available) * 100 if available else 0.0
            ),
            "non_overlapping_top3_beat_benchmark_rate_pct": _round(
                np.mean(group_rates) if group_rates else 0.0
            ),
            "non_overlapping_top3_beat_benchmark_rate_range_pct": [
                _round(min(group_rates), 2) if group_rates else 0.0,
                _round(max(group_rates), 2) if group_rates else 0.0,
            ],
            "top3_beat_benchmark_wilson_95_pct": [low, high],
            "wilson_sample_policy": "all_non_overlapping_phase_cohorts_conservative_envelope",
        }

    @classmethod
    def _summarize_prediction_records(
        cls,
        records: Sequence[Mapping[str, Any]],
    ) -> Dict[str, Any]:
        horizons = []
        for horizon in (5, 10, 20):
            rows = [row for row in records if int(row["horizon"]) == horizon]
            rank_ics = [
                float(row["rank_ic"])
                for row in rows
                if math.isfinite(float(row["rank_ic"]))
            ]
            benchmark_hits = sum(bool(row["top3_beat_benchmark"]) for row in rows)
            non_overlapping_groups = cls._non_overlapping_effect_groups(
                [cls._record_effect(row) for row in rows], horizon=horizon
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
            wilson_low = min(
                (interval[0] for interval in group_intervals), default=0.0
            )
            wilson_high = max(
                (interval[1] for interval in group_intervals), default=0.0
            )
            effective_samples = max(
                (len(group) for group in non_overlapping_groups), default=0
            )
            horizons.append({
                "horizon_sessions": horizon,
                "samples": len(rows),
                "effective_non_overlapping_samples": effective_samples,
                "rank_ic_mean": _round(np.mean(rank_ics) if rank_ics else 0.0, 4),
                "rank_ic_positive_rate_pct": _round(
                    np.mean([value > 0 for value in rank_ics]) * 100
                    if rank_ics else 0.0
                ),
                "top3_minus_bottom3_mean_pct": _round(
                    np.mean([float(row["top3_minus_bottom3"]) for row in rows]) * 100
                    if rows else 0.0
                ),
                "top3_spread_positive_rate_pct": _round(
                    np.mean([float(row["top3_minus_bottom3"]) > 0 for row in rows]) * 100
                    if rows else 0.0
                ),
                "leader_beat_median_rate_pct": _round(
                    np.mean([bool(row["leader_beat_median"]) for row in rows]) * 100
                    if rows else 0.0
                ),
                "leader_beat_benchmark_rate_pct": _round(
                    np.mean([bool(row["leader_beat_benchmark"]) for row in rows]) * 100
                    if rows else 0.0
                ),
                "top3_beat_median_rate_pct": _round(
                    np.mean([bool(row["top3_beat_median"]) for row in rows]) * 100
                    if rows else 0.0
                ),
                "top3_beat_benchmark_rate_pct": _round(
                    benchmark_hits / len(rows) * 100 if rows else 0.0
                ),
                "non_overlapping_top3_beat_benchmark_rate_pct": _round(
                    np.mean(group_rates) if group_rates else 0.0
                ),
                "non_overlapping_top3_beat_benchmark_rate_range_pct": [
                    _round(min(group_rates), 2) if group_rates else 0.0,
                    _round(max(group_rates), 2) if group_rates else 0.0,
                ],
                "top3_beat_benchmark_wilson_95_pct": [wilson_low, wilson_high],
                "wilson_sample_policy": "all_non_overlapping_phase_cohorts_conservative_envelope",
            })
        return {"horizons": horizons}

    @staticmethod
    def _record_effect(row: Mapping[str, Any]) -> Dict[str, Any]:
        return {
            "available": True,
            "entry_date": row.get("entry_date"),
            "exit_date": row.get("exit_date"),
            "rank_ic": row["rank_ic"],
            "top3_minus_bottom3": row["top3_minus_bottom3"],
            "top3_beat_benchmark": row["top3_beat_benchmark"],
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
            train_rank_delta = _round(
                combined_train["rank_ic_mean"] - train_without["rank_ic_mean"], 4
            ) if train_without["samples"] else 0.0
            oos_rank_delta = _round(
                combined_oos["rank_ic_mean"] - oos_without["rank_ic_mean"], 4
            ) if oos_without["samples"] else 0.0
            train_hit_delta = _round(
                combined_train["top3_beat_benchmark_rate_pct"]
                - train_without["top3_beat_benchmark_rate_pct"]
            ) if train_without["samples"] else 0.0
            oos_hit_delta = _round(
                combined_oos["top3_beat_benchmark_rate_pct"]
                - oos_without["top3_beat_benchmark_rate_pct"]
            ) if oos_without["samples"] else 0.0
            if not is_active:
                state, label = "unavailable", "缺少点时历史"
            elif train["rank_ic_mean"] > 0 and oos["rank_ic_mean"] > 0:
                if train_rank_delta >= 0 and oos_rank_delta >= 0:
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
                },
            })
        return {
            "method": "standalone_rank_ic_and_leave_one_out_composite",
            "primary_horizon_sessions": horizon,
            "selection_use": "diagnostic_only_no_oos_reweighting",
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
            float((row.get("confidence") or {}).get("score") or 0)
            for row in train_rows
        ]
        threshold = float(
            np.quantile(train_scores, cls.high_confidence_train_quantile)
        ) if train_scores else 100.0

        def summarize(rows: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
            selected = [
                row for row in rows
                if float((row.get("confidence") or {}).get("score") or 0) >= threshold
            ]
            all_summary = cls._effect_summary(
                [cls._record_effect(row) for row in rows], horizon=horizon
            )
            selected_summary = cls._effect_summary(
                [cls._record_effect(row) for row in selected], horizon=horizon
            )
            selected_summary["selection_rate_pct"] = _round(
                len(selected) / len(rows) * 100 if rows else 0.0
            )
            selected_summary["top3_hit_delta_pct"] = _round(
                selected_summary["top3_beat_benchmark_rate_pct"]
                - all_summary["top3_beat_benchmark_rate_pct"]
            )
            selected_summary["rank_ic_delta"] = _round(
                selected_summary["rank_ic_mean"] - all_summary["rank_ic_mean"], 4
            )
            return {"all": all_summary, "high_confidence": selected_summary}

        train = summarize(train_rows)
        oos = summarize(oos_rows)
        train_delta = train["high_confidence"]["top3_hit_delta_pct"]
        oos_delta = oos["high_confidence"]["top3_hit_delta_pct"]
        oos_effective = oos["high_confidence"]["effective_non_overlapping_samples"]
        wilson_low = oos["high_confidence"]["top3_beat_benchmark_wilson_95_pct"][0]
        if train_delta >= 0 and oos_delta >= 3 and oos_effective >= 10:
            if wilson_low >= 50:
                state, label = "precision_improved", "高共识信号提高命中且通过区间下界"
            else:
                state, label = "observed_improvement", "高共识信号命中改善但统计证据不足"
        elif oos_delta > 0:
            state, label = "oos_only", "样本外有改善，训练段未确认"
        else:
            state, label = "not_improved", "高共识过滤暂未提高命中"
        return {
            "method": "training_distribution_calibrated_abstention",
            "primary_horizon_sessions": horizon,
            "feature_formula": "70pct_active_factor_consensus_plus_30pct_score_separation",
            "threshold_train_quantile": cls.high_confidence_train_quantile,
            "threshold": _round(threshold, 2),
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
            benchmark_metrics = engine._benchmark_metrics(benchmark_slice, window)
            raw_rows = []
            future_returns: Dict[str, Dict[int, float]] = {}
            for item in self.universe:
                prepared_trade = prepared_trades.get(item.code)
                prepared_signal = prepared_signals.get(item.code)
                if prepared_trade is None or prepared_signal is None:
                    continue
                trade_source, trade_dates, trade_opens = prepared_trade
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
                entry_position = int(trade_dates.searchsorted(entry_date, side="left"))
                if (
                    entry_position >= len(trade_dates)
                    or trade_dates[entry_position] != entry_date
                    or self._valid_execution_price(trade_opens[entry_position]) is None
                ):
                    continue
                returns: Dict[int, float] = {}
                for horizon in (5, 10, 20):
                    exit_date = benchmark_dates[position + 1 + horizon]
                    exit_position = int(trade_dates.searchsorted(exit_date, side="left"))
                    if exit_position >= len(trade_dates) or trade_dates[exit_position] != exit_date:
                        break
                    exit_price = self._valid_execution_price(trade_opens[exit_position])
                    if exit_price is None:
                        break
                    returns[horizon] = exit_price / float(trade_opens[entry_position]) - 1
                if len(returns) != 3:
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
                future_returns[item.code] = returns
            if len(raw_rows) < self._minimum_cross_section_size(len(self.universe)):
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
                    if row["code"] in future_returns
                ]
                if len(pairs) < self._minimum_cross_section_size(len(self.universe)):
                    continue
                benchmark_entry = self._valid_execution_price(benchmark_opens[position + 1])
                benchmark_exit = self._valid_execution_price(
                    benchmark_opens[position + 1 + horizon]
                )
                if benchmark_entry is None or benchmark_exit is None:
                    continue
                benchmark_return = benchmark_exit / benchmark_entry - 1
                codes = [str(row["code"]) for row, _ in pairs]
                returns = [float(value) for _, value in pairs]
                composite_scores = [float(row["total_score"]) for row, _ in pairs]
                composite = self._ranking_effect(
                    composite_scores, returns, benchmark_return
                )
                if not composite.get("available"):
                    continue
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
                records.append({
                    "signal_date": signal_date.strftime("%Y-%m-%d"),
                    "entry_date": entry_date.strftime("%Y-%m-%d"),
                    "exit_date": benchmark_dates[position + 1 + horizon].strftime("%Y-%m-%d"),
                    "horizon": horizon,
                    "rank_ic": composite["rank_ic"],
                    "top3_minus_bottom3": composite["top3_minus_bottom3"],
                    "leader_beat_median": composite["leader_beat_median"],
                    "leader_beat_benchmark": composite["leader_beat_benchmark"],
                    "top3_beat_median": composite["top3_beat_median"],
                    "top3_beat_benchmark": composite["top3_beat_benchmark"],
                    "factor_effects": factor_effects,
                    "ablation_effects": ablation_effects,
                    "confidence": {
                        "score": _round(confidence_score, 4),
                        "active_factor_consensus_pct": _round(consensus_pct),
                        "top3_score_edge": _round(score_edge, 4),
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
            oos_horizons,
            key=lambda row: (
                float(row["rank_ic_mean"]),
                float(row["top3_beat_benchmark_rate_pct"]),
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
        if (
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
        return {
            "method": "cross_sectional_rank_ic_top3_minus_bottom3_next_open",
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
        dates = pd.to_datetime(benchmark_frame["date"])
        split_position = max(180, min(len(dates) - 40, int(len(dates) * 0.65)))
        split_date = pd.Timestamp(dates.iloc[split_position])
        variants = []
        trade_sets: Dict[str, list[Dict[str, Any]]] = {}
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
                trades = window_trade_sets[profile]
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
                    ),
                })
                trade_sets[variant_id] = trades
        profile_order = {profile: index for index, profile in enumerate(ROTATION_WEIGHT_PROFILES)}
        window_order = {window: index for index, window in enumerate(self.windows)}
        variants.sort(key=lambda row: (profile_order[row["profile"]], window_order[row["window"]]))
        eligible = [row for row in variants if row["train"]["trades"] >= 8 and row["out_of_sample"]["trades"] >= 4]
        if not eligible:
            raise MarketDataError("历史样本不足以形成训练段和样本外段")
        selected = dict(max(eligible, key=lambda row: (row["selection_score"], row["id"])))
        selected["qualification"] = self._training_qualification(
            selected["train"], selected["train_stability"]
        )
        selected_trades = trade_sets[selected["id"]]
        selected_oos_trades = [row for row in selected_trades if pd.Timestamp(row["entry_date"]) > split_date]
        selected_train_trades = [
            row for row in selected_trades
            if pd.Timestamp(row["exit_date"]) <= split_date
        ]
        ensemble_trades = self._parameter_ensemble_trades(
            trade_sets,
            cost_bps=cost_bps,
            vote_source="buffered_selection",
        )
        online_consensus_trades = self._parameter_ensemble_trades(
            trade_sets,
            cost_bps=cost_bps,
            vote_source="current_leader",
        )
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
        ensemble_train_hit_delta = _round(
            ensemble_train_signal["gross_beat_benchmark_rate_pct"]
            - selected_train_signal["gross_beat_benchmark_rate_pct"]
        )
        ensemble_oos_hit_delta = _round(
            ensemble_oos_signal["gross_beat_benchmark_rate_pct"]
            - selected_oos_signal["gross_beat_benchmark_rate_pct"]
        )
        ensemble_training_qualified = (
            ensemble_train_metrics["excess_return_pct"] > 0
            and ensemble_train_signal["samples"] >= 20
            and ensemble_train_signal["gross_beat_benchmark_rate_pct"] >= 55
            and ensemble_train_hit_delta >= 0
        )
        if ensemble_training_qualified and ensemble_oos_hit_delta >= 3:
            ensemble_state = "observed_improvement"
            ensemble_label = "严格多数集成历史命中改善，仍需前向验证"
        elif ensemble_training_qualified:
            ensemble_state = "train_only"
            ensemble_label = "严格多数集成仅在训练段改善"
        else:
            ensemble_state = "diagnostic_only"
            ensemble_label = "严格多数集成未通过训练门槛"
        online_consensus_training_qualified = (
            online_consensus_train_metrics["excess_return_pct"] > 0
            and online_consensus_train_signal["samples"] >= 20
            and online_consensus_train_signal["gross_beat_benchmark_rate_pct"] >= 55
        )
        online_consensus_oos_hit_delta = _round(
            online_consensus_oos_signal["gross_beat_benchmark_rate_pct"]
            - online_consensus_oos_all["gross_beat_benchmark_rate_pct"]
        )
        if (
            online_consensus_training_qualified
            and online_consensus_oos_signal["gross_beat_benchmark_rate_pct"] >= 55
            and online_consensus_oos_hit_delta >= 0
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
            trades = confirmation_trade_sets[policy]
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
                ),
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
                "excess_return_pct": _round(oos_metrics["excess_return_pct"] - raw_oos["excess_return_pct"]),
                "max_drawdown_improvement_pct": _round(raw_oos["max_drawdown_pct"] - oos_metrics["max_drawdown_pct"]),
                "turnover_rate_pct": _round(oos_metrics["turnover_rate_pct"] - raw_oos["turnover_rate_pct"]),
            }
        best_oos_confirmation = max(
            confirmation_policies,
            key=lambda row: (row["out_of_sample"]["excess_return_pct"], row["id"]),
        )
        qualified_confirmation = [
            row for row in confirmation_policies
            if row["qualification"]["state"] == "qualified"
            and row["train"]["trades"] >= 8
            and row["out_of_sample"]["trades"] >= 4
        ]
        selected_confirmation = dict(max(
            qualified_confirmation or [raw_policy],
            key=lambda row: (row["selection_score"], row["id"]),
        ))
        selected_confirmation_oos = selected_confirmation["out_of_sample"]
        confirmation_delta = selected_confirmation["delta_vs_raw"]
        if selected_confirmation["id"] == "raw":
            confirmation_state = "baseline_retained"
            confirmation_label = "训练段继续选择原始排序"
        elif (
            confirmation_delta["excess_return_pct"] > 0
            and confirmation_delta["max_drawdown_improvement_pct"] >= 0
        ):
            confirmation_state = "improved"
            confirmation_label = "确认层同时改善收益与回撤"
        elif (
            confirmation_delta["excess_return_pct"] > 0
            or confirmation_delta["max_drawdown_improvement_pct"] > 0
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
        positive_share = sum(row["out_of_sample"]["excess_return_pct"] > 0 for row in eligible) / len(eligible)
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
            "results_are_research_evidence_not_live_trading_advice",
        ]
        if index_signal_count:
            limitations.append(
                "industry_index_signals_use_close_and_etfs_execute_at_next_session_open"
            )
        if signal_fallback_count:
            limitations.append("same_industry_etf_proxy_used_when_index_unavailable")
        reasons = []
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
            reasons.append(f"样本外交易仅 {selected_oos['trades']} 次，低于 30 次最低观察门槛")
        if positive_share < 0.6:
            reasons.append(f"仅 {positive_share * 100:.0f}% 参数组合在样本外跑赢基准，参数平台不足")
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
        elif stress_tests[-1]["excess_return_pct"] > 0 and positive_share >= 0.6:
            verdict = "promising"
            verdict_label = "具备继续验证价值"
        else:
            verdict = "fragile"
            verdict_label = "稳健性偏弱"
        data_quality = {
            "state": "complete" if not failures and not signal_failures else "partial",
            "benchmark_rows": len(benchmark_frame),
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
        payload = {
            "engine": {"name": self.engine_name, "version": self.engine_version},
            "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
            "as_of": end_date.strftime("%Y-%m-%d"),
            "requested_as_of": normalized_as_of,
            "data_source": self.provider.name,
            "hypothesis": "基于当日收盘可见的动量、相对强弱、趋势质量、成交连续性与拥挤/条件反转排名，在下一交易日开盘执行对应 ETF 后能取得相对基准收益；估值与基本面仅在具备点时证据时启用。",
            "rules": {
                "signal_timing": "signal_at_close_t_execute_next_session_open",
                "holding_period_sessions": rebalance_days,
                "portfolio": "top_1_equal_notional",
                "cost_bps_per_side": cost_bps,
                "switch_score_gap": self.switch_score_gap,
                "hold_rank_limit": self.hold_rank_limit,
                "minimum_cross_section_coverage_pct": _round(self.minimum_cross_section_coverage * 100, 1),
                "evidence_coverage_threshold_pct": _round(self.evidence_coverage_threshold * 100, 1),
                "transaction_cost": "charged_when_selected_etf_changes",
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
                "positive_variant_share_pct": _round(positive_share * 100),
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
                "best_oos_rank_ic": best_prediction_row.get("rank_ic_mean", 0.0),
                "best_oos_top3_beat_benchmark_rate_pct": best_prediction_row.get(
                    "top3_beat_benchmark_rate_pct", 0.0
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
                "positive_variant_share_pct": _round(positive_share * 100),
                "selected_confirmation_policy": selected_confirmation["id"],
                "confirmation_verdict": confirmation_state,
                "prediction_verdict": prediction_diagnostics["verdict"]["state"],
                "best_observed_horizon_sessions": best_prediction_horizon,
            },
        )
        return payload
