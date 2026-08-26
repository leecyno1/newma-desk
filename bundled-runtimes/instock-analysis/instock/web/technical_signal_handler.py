#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import asyncio
import logging

from instock.core.analysis_snapshot import get_analysis_snapshot_registry
from instock.core.market_data_provider import MarketDataError, get_market_data_provider
from instock.web.api_contract import AnalysisApiHandler
from instock.web.result_cache import AsyncTaskCoalescer, BoundedTTLCache


_RESULT_CACHE = BoundedTTLCache(max_entries=16, ttl_seconds=300)
_INFLIGHT = AsyncTaskCoalescer()


def technical_signal_runtime_stats():
    stats = _RESULT_CACHE.stats()
    stats["inflight"] = len(_INFLIGHT)
    return stats


class TechnicalSignalSnapshotHandler(AnalysisApiHandler):
    async def get(self) -> None:
        try:
            universe_size = int(self.get_argument("universeSize", "30"))
            bars = int(self.get_argument("bars", "260"))
            max_workers = int(self.get_argument("maxWorkers", "6"))
            market = self.get_argument("market", "CN").strip().upper()
            universe_mode = self.get_argument("universeMode", "broad").strip().lower()
            refresh = self.get_argument("refresh", "0") == "1"
            filters = {
                "industries": self._list_argument("industries"),
                "required_strategies": self._list_argument("requiredStrategies"),
                "required_patterns": self._list_argument("requiredPatterns"),
                "bias": self.get_argument("bias", "all").strip().lower(),
                "min_technical_score": self._float_argument("minTechnicalScore"),
                "min_amount": self._float_argument("minAmount"),
                "min_market_cap": self._float_argument("minMarketCap"),
                "max_market_cap": self._float_argument("maxMarketCap"),
                "max_pe": self._float_argument("maxPE"),
                "max_pb": self._float_argument("maxPB"),
                "min_turnover_pct": self._float_argument("minTurnover"),
                "max_turnover_pct": self._float_argument("maxTurnover"),
                "min_volume_ratio": self._float_argument("minVolumeRatio"),
                "max_volume_ratio": self._float_argument("maxVolumeRatio"),
                "min_roe_pct": self._float_argument("minROE"),
                "min_revenue_growth_pct": self._float_argument("minRevenueGrowth"),
                "min_net_profit_growth_pct": self._float_argument("minNetProfitGrowth"),
            }
        except ValueError:
            self.write_error(400, "invalid_parameters", "选股参数或筛选数值格式不正确")
            return

        # TA-Lib and the signal engine stay outside the attached process import
        # graph until this Action is actually invoked.
        from instock.core.signals import (
            TechnicalSignalCenterEngine,
            TechnicalSignalCenterError,
        )

        try:
            provider = get_market_data_provider()
            cache_key = (
                provider.name,
                universe_size,
                bars,
                max_workers,
                market,
                universe_mode,
                tuple(sorted(
                    (key, tuple(value) if isinstance(value, list) else value)
                    for key, value in filters.items()
                )),
            )
            result = _RESULT_CACHE.get(cache_key)
            cache_hit = not refresh and result is not None
            owns_task = False
            if refresh or result is None:
                task = _INFLIGHT.get(cache_key)
                owns_task = task is None
                if task is None:
                    task = asyncio.create_task(asyncio.to_thread(
                        TechnicalSignalCenterEngine(
                            provider, max_workers=max_workers
                        ).analyze,
                        universe_size=universe_size,
                        bars=bars,
                        market=market,
                        universe_mode=universe_mode,
                        filters=filters,
                        refresh=refresh,
                    ))
                    _INFLIGHT.set(cache_key, task)
                try:
                    result = dict(await task)
                finally:
                    if owns_task:
                        _INFLIGHT.discard(cache_key, task)
                _RESULT_CACHE.set(cache_key, result)
            result["cache_hit"] = cache_hit
            get_analysis_snapshot_registry().register(result["snapshot"])
            parameters = {
                "universeSize": universe_size,
                "bars": bars,
                "maxWorkers": max_workers,
                "market": market,
                "universeMode": universe_mode,
                "filters": filters,
            }
            if cache_hit or not owns_task:
                self.write_success(result, meta={"cache": technical_signal_runtime_stats()})
            else:
                self.write_analysis_success(
                    result,
                    module_id="technical-signals",
                    title="选股中心",
                    parameters=parameters,
                    meta={"cache": technical_signal_runtime_stats()},
                )
        except TechnicalSignalCenterError as exc:
            self.write_error(400, "invalid_technical_signal_request", str(exc))
        except MarketDataError as exc:
            self.write_error(502, "market_data_unavailable", str(exc))
        except Exception:  # noqa: BLE001
            logging.exception("选股中心接口异常")
            self.write_error(500, "internal_error", "选股中心分析异常")

    def _list_argument(self, name: str) -> list[str]:
        values = []
        for raw in self.get_arguments(name):
            values.extend(part.strip() for part in raw.split(","))
        return [value for value in values if value]

    def _float_argument(self, name: str):
        value = self.get_argument(name, "").strip()
        return None if not value else float(value)
