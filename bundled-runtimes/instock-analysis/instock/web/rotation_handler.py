#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Tornado API for the project-local industry and ETF rotation surface."""

from __future__ import annotations

import asyncio
import logging
import os
import re
import time
from collections import OrderedDict
from copy import deepcopy
from threading import RLock
from typing import Any, Dict, Tuple

from instock.core.analysis_snapshot import get_analysis_snapshot_registry, normalize_as_of
from instock.core.market_data_provider import (
    HistoricalWindowUnavailable,
    MarketDataError,
    get_market_data_provider,
)
from instock.core.rotation import RotationEngine, RotationExperiment
from instock.core.rotation.rotation_shadow_state import get_rotation_shadow_state
from instock.core.rotation.sector_fund_flow_history import get_sector_fund_flow_history
from instock.web.api_contract import AnalysisApiHandler
from instock.web.result_cache import AsyncTaskCoalescer


_SYMBOL_PATTERN = re.compile(r"^\d{6}$")
_WINDOWS = {40, 60, 120}
_CACHE_TTL_SECONDS = 300


def _int_setting(name: str, default: int, minimum: int, maximum: int) -> int:
    try:
        value = int(os.environ.get(name, str(default)))
    except (TypeError, ValueError):
        return default
    return min(max(value, minimum), maximum)


class _BoundedTTLCache:
    """Small copy-isolated LRU cache for process-local analysis payloads."""

    def __init__(self, *, max_entries: int, ttl_seconds: float, clock=time.monotonic):
        self.max_entries = max(1, int(max_entries))
        self.ttl_seconds = max(1.0, float(ttl_seconds))
        self._clock = clock
        self._lock = RLock()
        self._entries: OrderedDict[Any, Tuple[float, Dict[str, Any]]] = OrderedDict()

    def _purge_expired(self, now: float) -> None:
        expired = [
            key for key, (stored_at, _) in self._entries.items()
            if now - stored_at >= self.ttl_seconds
        ]
        for key in expired:
            self._entries.pop(key, None)

    def get(self, key: Any) -> Dict[str, Any] | None:
        now = self._clock()
        with self._lock:
            self._purge_expired(now)
            entry = self._entries.pop(key, None)
            if entry is None:
                return None
            self._entries[key] = entry
            return deepcopy(entry[1])

    def set(self, key: Any, value: Dict[str, Any]) -> None:
        now = self._clock()
        with self._lock:
            self._purge_expired(now)
            self._entries.pop(key, None)
            self._entries[key] = (now, deepcopy(value))
            while len(self._entries) > self.max_entries:
                self._entries.popitem(last=False)

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()

    def __len__(self) -> int:
        now = self._clock()
        with self._lock:
            self._purge_expired(now)
            return len(self._entries)

    def stats(self) -> dict[str, Any]:
        now = self._clock()
        with self._lock:
            self._purge_expired(now)
            return {
                "storage": "process_memory",
                "volatile": True,
                "entries": len(self._entries),
                "max_entries": self.max_entries,
                "ttl_seconds": self.ttl_seconds,
            }


_SNAPSHOT_CACHE = _BoundedTTLCache(
    max_entries=_int_setting("INSTOCK_ROTATION_CACHE_MAX_ENTRIES", 64, 8, 512),
    ttl_seconds=_CACHE_TTL_SECONDS,
)
_SNAPSHOT_INFLIGHT = AsyncTaskCoalescer()
_EXPERIMENT_CACHE_TTL_SECONDS = 900
_EXPERIMENT_CACHE = _BoundedTTLCache(
    max_entries=_int_setting("INSTOCK_ROTATION_EXPERIMENT_CACHE_MAX_ENTRIES", 32, 4, 256),
    ttl_seconds=_EXPERIMENT_CACHE_TTL_SECONDS,
)
_EXPERIMENT_INFLIGHT = AsyncTaskCoalescer()


def rotation_runtime_stats() -> dict[str, dict[str, Any]]:
    snapshot = _SNAPSHOT_CACHE.stats()
    snapshot["inflight"] = len(_SNAPSHOT_INFLIGHT)
    experiment = _EXPERIMENT_CACHE.stats()
    experiment["inflight"] = len(_EXPERIMENT_INFLIGHT)
    return {
        "snapshots": snapshot,
        "experiments": experiment,
        "shadow_state": get_rotation_shadow_state().stats(),
    }


class RotationSnapshotHandler(AnalysisApiHandler):
    """Return a frontend-oriented deterministic rotation snapshot."""

    async def get(self):
        try:
            window = int(self.get_argument("window", "60"))
        except (TypeError, ValueError):
            self.write_error(400, "invalid_window", "分析窗口必须是整数")
            return
        benchmark = self.get_argument("benchmark", "510300").strip()
        refresh = self.get_argument("refresh", "0") == "1"
        as_of_text = self.get_argument("asOf", self.get_argument("as_of", "")).strip()

        if window not in _WINDOWS:
            self.write_error(400, "invalid_window", "分析窗口仅支持 40、60、120 个交易日")
            return
        if not _SYMBOL_PATTERN.fullmatch(benchmark):
            self.write_error(400, "invalid_benchmark", "基准代码须为6位数字")
            return
        try:
            as_of = normalize_as_of(as_of_text, reject_future=True)
        except ValueError as exc:
            self.write_error(400, "invalid_as_of", str(exc))
            return

        try:
            provider = get_market_data_provider()
            shadow_ledger = get_rotation_shadow_state()
            cache_key = (provider.name, window, benchmark, as_of or "latest")
            cached = _SNAPSHOT_CACHE.get(cache_key)
            cache_hit = not refresh and cached is not None
            owns_task = False
            if cache_hit:
                payload = cached
                payload["cache_hit"] = True
            else:
                task = _SNAPSHOT_INFLIGHT.get(cache_key)
                owns_task = task is None
                if task is None:
                    engine = RotationEngine(provider)
                    fund_flow_history = (
                        get_sector_fund_flow_history().recent(before="9999-12-31", limit=5)
                        if not as_of else ()
                    )
                    previous_shadow_state = (
                        shadow_ledger.latest(benchmark) if not as_of else None
                    )
                    task = asyncio.create_task(
                        asyncio.to_thread(
                            engine.analyze,
                            window,
                            benchmark,
                            as_of,
                            fund_flow_history=fund_flow_history,
                            shadow_state=previous_shadow_state,
                        )
                    )
                    _SNAPSHOT_INFLIGHT.set(cache_key, task)
                try:
                    payload = dict(await task)
                finally:
                    if owns_task:
                        _SNAPSHOT_INFLIGHT.discard(cache_key, task)
                payload["cache_hit"] = False
                if not as_of:
                    get_sector_fund_flow_history().upsert(
                        payload.get("as_of", ""), payload.get("etfs") or ()
                    )
                    shadow_state = (
                        (payload.get("parameter_consensus") or {}).get("shadow_state")
                        or {}
                    )
                    recorded = shadow_ledger.record(benchmark, shadow_state)
                    payload["shadow_ledger"] = {
                        "state": "recorded" if recorded else "unchanged",
                        "benchmark": benchmark,
                        "storage": "sqlite",
                    }
                else:
                    payload["shadow_ledger"] = {
                        "state": "historical_disabled",
                        "benchmark": benchmark,
                        "storage": "sqlite",
                    }
                _SNAPSHOT_CACHE.set(cache_key, payload)
            snapshot = payload.get("snapshot")
            if snapshot:
                get_analysis_snapshot_registry().register(snapshot)
            parameters = {
                "window": window,
                "benchmark": benchmark,
                "asOf": as_of,
                "refresh": "1" if refresh else "0",
            }
            if cache_hit or not owns_task:
                self.write_success(payload, meta={"cache": rotation_runtime_stats()["snapshots"]})
            else:
                self.write_analysis_success(
                    payload,
                    module_id="rotation",
                    title="行业与 ETF 轮动",
                    parameters=parameters,
                    meta={"cache": rotation_runtime_stats()["snapshots"]},
                )
        except HistoricalWindowUnavailable as exc:
            self.write_error(422, "historical_window_unavailable", str(exc))
        except (MarketDataError, ValueError) as exc:
            self.write_error(502, "market_data_unavailable", str(exc))
        except Exception:  # noqa: BLE001
            logging.exception("行业与 ETF 轮动接口异常")
            self.write_error(500, "internal_error", "轮动分析服务异常")


class RotationExperimentHandler(AnalysisApiHandler):
    """Return a cached point-in-time robustness experiment resource."""

    async def get(self):
        benchmark = self.get_argument("benchmark", "510300").strip()
        as_of_text = self.get_argument("asOf", self.get_argument("as_of", "")).strip()
        refresh = self.get_argument("refresh", "0") == "1"
        try:
            rebalance_days = int(self.get_argument("rebalanceDays", "10"))
            cost_bps = int(self.get_argument("costBps", "25"))
        except (TypeError, ValueError):
            self.write_error(400, "invalid_experiment_parameters", "再平衡周期与摩擦成本必须是整数")
            return
        if not _SYMBOL_PATTERN.fullmatch(benchmark):
            self.write_error(400, "invalid_benchmark", "基准代码须为6位数字")
            return
        if rebalance_days not in RotationExperiment.supported_rebalances:
            self.write_error(400, "invalid_rebalance_days", "再平衡周期仅支持 5、10、20 个交易日")
            return
        if cost_bps not in RotationExperiment.supported_cost_bps:
            self.write_error(400, "invalid_cost_bps", "单边摩擦成本仅支持 10、25、50 bps")
            return
        try:
            as_of = normalize_as_of(as_of_text, reject_future=True)
        except ValueError as exc:
            self.write_error(400, "invalid_as_of", str(exc))
            return

        try:
            provider = get_market_data_provider()
            cache_key = (provider.name, benchmark, rebalance_days, cost_bps, as_of or "latest")
            cached = _EXPERIMENT_CACHE.get(cache_key)
            cache_hit = not refresh and cached is not None
            owns_task = False
            if cache_hit:
                payload = cached
                payload["cache_hit"] = True
            else:
                task = _EXPERIMENT_INFLIGHT.get(cache_key)
                owns_task = task is None
                if task is None:
                    experiment = RotationExperiment(provider)
                    task = asyncio.create_task(asyncio.to_thread(
                        experiment.run,
                        benchmark=benchmark,
                        rebalance_days=rebalance_days,
                        cost_bps=cost_bps,
                        as_of=as_of,
                    ))
                    _EXPERIMENT_INFLIGHT.set(cache_key, task)
                try:
                    payload = dict(await task)
                finally:
                    if owns_task:
                        _EXPERIMENT_INFLIGHT.discard(cache_key, task)
                payload["cache_hit"] = False
                _EXPERIMENT_CACHE.set(cache_key, payload)
            snapshot = payload.get("snapshot")
            if snapshot:
                get_analysis_snapshot_registry().register(snapshot)
            parameters = {
                "benchmark": benchmark,
                "rebalanceDays": rebalance_days,
                "costBps": cost_bps,
                "asOf": as_of,
                "refresh": "1" if refresh else "0",
            }
            if cache_hit or not owns_task:
                self.write_success(payload, meta={"cache": rotation_runtime_stats()["experiments"]})
            else:
                self.write_analysis_success(
                    payload,
                    module_id="rotation",
                    record_type="experiment",
                    title="轮动稳健性实验",
                    parameters=parameters,
                    meta={"cache": rotation_runtime_stats()["experiments"]},
                )
        except HistoricalWindowUnavailable as exc:
            self.write_error(422, "historical_window_unavailable", str(exc))
        except (MarketDataError, ValueError) as exc:
            self.write_error(422, "experiment_unavailable", str(exc))
        except Exception:  # noqa: BLE001
            logging.exception("行业与 ETF 轮动稳健性实验异常")
            self.write_error(500, "internal_error", "轮动稳健性实验服务异常")
