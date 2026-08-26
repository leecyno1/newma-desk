#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Tornado handlers for the project-local CZSC analysis page and API."""

from __future__ import annotations

import asyncio
import logging
import os

from instock.core.analysis_snapshot import normalize_as_of
from instock.core.czsc_analysis import (
    CZSC_BAR_LIMITS,
    CZSC_PERIODS,
    CZSC_SYMBOL_PATTERN,
    CZSCAnalysisFailed,
    run_czsc_analysis,
)
from instock.core.market_data_provider import (
    HistoricalWindowUnavailable,
    MarketDataError,
    get_market_data_provider,
)
from instock.web.api_contract import AnalysisApiHandler
from instock.web.result_cache import AsyncTaskCoalescer, BoundedTTLCache


def _int_setting(name: str, default: int, minimum: int, maximum: int) -> int:
    try:
        value = int(os.environ.get(name, str(default)))
    except (TypeError, ValueError):
        return default
    return min(max(value, minimum), maximum)


_RESULT_CACHE = BoundedTTLCache(
    max_entries=_int_setting("INSTOCK_CZSC_CACHE_MAX_ENTRIES", 64, 8, 512),
    ttl_seconds=_int_setting("INSTOCK_CZSC_CACHE_TTL_SECONDS", 300, 30, 3600),
)
_INFLIGHT = AsyncTaskCoalescer()


def czsc_analysis_runtime_stats():
    stats = _RESULT_CACHE.stats()
    stats["inflight"] = len(_INFLIGHT)
    return stats


class CZSCAnalysisHandler(AnalysisApiHandler):
    """Return a stable, frontend-oriented CZSC analysis contract."""

    async def get(self):
        symbol = self.get_argument("code", "300502").strip().upper()
        period = self.get_argument("period", "daily").strip().lower()
        bars_text = self.get_argument("bars", self.get_argument("days", "480"))
        as_of_text = self.get_argument("asOf", self.get_argument("as_of", "")).strip()
        refresh = self.get_argument("refresh", "0") == "1"

        if not CZSC_SYMBOL_PATTERN.fullmatch(symbol):
            self.write_error(400, "invalid_symbol", "股票代码须为6位数字，可带 .SH/.SZ/.BJ 后缀")
            return
        if period not in CZSC_PERIODS:
            self.write_error(400, "invalid_period", "周期仅支持 daily、weekly、monthly")
            return
        try:
            bars = int(bars_text)
        except (TypeError, ValueError):
            self.write_error(400, "invalid_bar_limit", "K线数量必须是整数")
            return
        if bars not in CZSC_BAR_LIMITS:
            self.write_error(400, "invalid_bar_limit", "K线数量仅支持 120、240、480、800")
            return
        try:
            as_of = normalize_as_of(as_of_text, reject_future=True)
        except ValueError as exc:
            self.write_error(400, "invalid_as_of", str(exc))
            return

        try:
            provider = get_market_data_provider()
            cache_key = (provider.name, symbol, period, bars, as_of or "latest")
            payload = _RESULT_CACHE.get(cache_key)
            cache_hit = not refresh and payload is not None
            owns_task = False
            if refresh or payload is None:
                task = _INFLIGHT.get(cache_key)
                owns_task = task is None
                if task is None:
                    task = asyncio.create_task(asyncio.to_thread(
                        run_czsc_analysis,
                        provider,
                        symbol=symbol,
                        period=period,
                        bars=bars,
                        as_of=as_of,
                        include_chart=True,
                    ))
                    _INFLIGHT.set(cache_key, task)
                try:
                    payload = dict(await task)
                finally:
                    if owns_task:
                        _INFLIGHT.discard(cache_key, task)
                _RESULT_CACHE.set(cache_key, payload)
            payload["cache_hit"] = cache_hit
            snapshot = payload.get("snapshot")
            if snapshot:
                from instock.core.analysis_snapshot import get_analysis_snapshot_registry

                get_analysis_snapshot_registry().register(snapshot)
            parameters = {
                "code": symbol,
                "period": period,
                "bars": bars,
                "asOf": as_of,
            }
            meta = {"cache": czsc_analysis_runtime_stats()}
            if cache_hit or not owns_task:
                self.write_success(payload, meta=meta)
            else:
                self.write_analysis_success(
                    payload,
                    module_id="czsc",
                    title=f"{symbol.split('.')[0]} · 缠论结构分析",
                    parameters=parameters,
                    meta=meta,
                )
        except CZSCAnalysisFailed as exc:
            self.write_error(422, "analysis_failed", str(exc))
        except HistoricalWindowUnavailable as exc:
            self.write_error(422, "historical_window_unavailable", str(exc))
        except MarketDataError as exc:
            self.write_error(502, "market_data_unavailable", str(exc))
        except Exception:  # noqa: BLE001
            logging.exception("CZSC 分析接口异常")
            self.write_error(500, "internal_error", "缠论分析服务异常")


class CZSCChartHandler(CZSCAnalysisHandler):
    """Compatibility endpoint returning the ECharts option directly."""

    async def get(self):
        await super().get()
        # The historical endpoint is kept as a route alias.  New clients should
        # consume /api/czsc/analysis so metadata and insights are not discarded.
