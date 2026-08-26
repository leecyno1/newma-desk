#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Versioned Action handler for explainable CN/HK stock candidates."""

from __future__ import annotations

import asyncio
import logging

from instock.core.analysis_snapshot import get_analysis_snapshot_registry
from instock.core.analysis_history import get_analysis_history_registry
from instock.core.market_data_provider import MarketDataError, get_market_data_provider
from instock.core.selection import (
    StockCandidateEngine,
    StockCandidateError,
    enrich_candidate_lifecycle,
)
from instock.web.api_contract import AnalysisApiHandler
from instock.web.result_cache import AsyncTaskCoalescer, BoundedTTLCache


_CACHE_TTL_SECONDS = 300.0
_CACHE_MAX_ENTRIES = 32
_RESULT_CACHE = BoundedTTLCache(
    max_entries=_CACHE_MAX_ENTRIES,
    ttl_seconds=_CACHE_TTL_SECONDS,
)
_INFLIGHT = AsyncTaskCoalescer()


def _cache_get(key):
    return _RESULT_CACHE.get(key)


def _cache_set(key, value):
    _RESULT_CACHE.set(key, value)


def stock_candidate_runtime_stats():
    stats = _RESULT_CACHE.stats()
    stats["inflight"] = len(_INFLIGHT)
    return stats


class StockCandidateSnapshotHandler(AnalysisApiHandler):
    async def get(self) -> None:
        try:
            universe_size = int(self.get_argument("universeSize", "30"))
            output_size = int(self.get_argument("outputSize", "10"))
            bars = int(self.get_argument("bars", "120"))
            market = self.get_argument("market", "CN").strip().upper()
            universe_mode = self.get_argument("universeMode", "broad").strip().lower()
            profile = self.get_argument("profile", "balanced")
            refresh = self.get_argument("refresh", "0") == "1"
            event_flow_snapshot_id = self.get_argument(
                "eventFlowSnapshotId", ""
            ).strip() or None
            filters = {
                "industries": self._list_argument("industries"),
                "min_amount": self._float_argument("minAmount"),
                "min_market_cap": self._float_argument("minMarketCap"),
                "max_market_cap": self._float_argument("maxMarketCap"),
                "max_pe": self._float_argument("maxPE"),
                "max_pb": self._float_argument("maxPB"),
                "min_turnover_pct": self._float_argument("minTurnover"),
                "max_turnover_pct": self._float_argument("maxTurnover"),
                "min_volume_ratio": self._float_argument("minVolumeRatio"),
                "max_volume_ratio": self._float_argument("maxVolumeRatio"),
                "min_momentum_20_pct": self._float_argument("minMomentum20"),
                "max_volatility_pct": self._float_argument("maxVolatility"),
                "min_roe_pct": self._float_argument("minROE"),
                "min_revenue_growth_pct": self._float_argument("minRevenueGrowth"),
                "min_net_profit_growth_pct": self._float_argument("minNetProfitGrowth"),
                "max_valuation_percentile": self._float_argument("maxValuationPercentile"),
                "required_signals": self._list_argument("requiredSignals"),
            }
        except ValueError:
            self.write_error(400, "invalid_parameters", "候选池、输出数量和筛选数值格式不正确")
            return

        try:
            provider = get_market_data_provider()
            cache_key = (
                provider.name,
                universe_size,
                output_size,
                bars,
                market,
                universe_mode,
                profile,
                tuple(
                    sorted(
                        (key, tuple(value) if isinstance(value, list) else value)
                        for key, value in filters.items()
                    )
                ),
                event_flow_snapshot_id,
            )
            result = _cache_get(cache_key)
            cache_hit = not refresh and result is not None
            owns_task = False
            if refresh or result is None:
                task = _INFLIGHT.get(cache_key)
                owns_task = task is None
                if task is None:
                    engine = StockCandidateEngine(provider)
                    task = asyncio.create_task(asyncio.to_thread(
                        engine.analyze,
                        universe_size=universe_size,
                        output_size=output_size,
                        bars=bars,
                        market=market,
                        universe_mode=universe_mode,
                        profile=profile,
                        filters=filters,
                        event_flow_snapshot_id=event_flow_snapshot_id,
                        refresh=refresh,
                    ))
                    _INFLIGHT.set(cache_key, task)
                try:
                    result = dict(await task)
                finally:
                    if owns_task:
                        _INFLIGHT.discard(cache_key, task)
                _cache_set(cache_key, result)
            parameters = {
                "universeSize": universe_size,
                "outputSize": output_size,
                "bars": bars,
                "market": market,
                "universeMode": universe_mode,
                "profile": profile,
                "filters": filters,
                "eventFlowSnapshotId": event_flow_snapshot_id,
            }
            history_registry = get_analysis_history_registry()
            history_records = [
                record
                for item in history_registry.list("stock-candidates", limit=30)
                if (record := history_registry.get(item["history_id"])) is not None
            ]
            result = enrich_candidate_lifecycle(
                result,
                history_records,
                parameters=parameters,
            )
            result["cache_hit"] = cache_hit
            get_analysis_snapshot_registry().register(result["snapshot"])
            if cache_hit or not owns_task:
                self.write_success(result, meta={"cache": stock_candidate_runtime_stats()})
                return
            self.write_analysis_success(
                result,
                module_id="stock-candidates",
                title="A/H 股候选",
                parameters=parameters,
                meta={"cache": stock_candidate_runtime_stats()},
            )
        except StockCandidateError as exc:
            self.write_error(400, "invalid_candidate_request", str(exc))
        except MarketDataError as exc:
            self.write_error(502, "market_data_unavailable", str(exc))
        except Exception:  # noqa: BLE001
            logging.exception("A/H 股候选接口异常")
            self.write_error(500, "internal_error", "A/H 股候选分析异常")

    def _list_argument(self, name):
        values = self.get_arguments(name)
        return [item.strip() for value in values for item in value.split(",") if item.strip()]

    def _float_argument(self, name):
        value = self.get_argument(name, "").strip()
        return None if not value else float(value)
