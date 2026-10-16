#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import asyncio
import logging

from instock.core.analysis_snapshot import get_analysis_snapshot_registry, normalize_as_of
from instock.core.rotation.etf_universe import DEFAULT_SECTOR_ETFS
from instock.core.market_data_provider import MarketDataError, get_market_data_provider
from instock.core.workbench import MarketWorkbenchEngine, MarketWorkbenchError
from instock.web.api_contract import AnalysisApiHandler
from instock.web.result_cache import AsyncTaskCoalescer, BoundedTTLCache


_RESULT_CACHE = BoundedTTLCache(max_entries=8, ttl_seconds=60)
_INFLIGHT = AsyncTaskCoalescer()


class MarketStructureHandler(AnalysisApiHandler):
    async def get(self):
        try:
            result = await asyncio.to_thread(get_market_data_provider().get_market_structure,
                                             refresh=self.get_argument("refresh", "0") == "1")
            self.write_success(result)
        except MarketDataError:
            self.write_error(502, "market_structure_unavailable", "市场结构来源暂不可用，请刷新重试")


class MarketEvidenceHandler(AnalysisApiHandler):
    async def get(self):
        item = next((item for item in DEFAULT_SECTOR_ETFS if item.code == self.get_argument("code", "")), None)
        try:
            as_of = normalize_as_of(self.get_argument("asOf", ""), reject_future=True)
            if not item or not as_of:
                raise ValueError("请选择轮动候选和复盘日期")
        except ValueError:
            self.write_error(400, "invalid_market_evidence", "请选择有效的轮动候选和复盘日期")
            return
        try:
            code = item.code + (".SZ" if item.code.startswith("1") else ".SH")
            result = await asyncio.to_thread(get_market_data_provider().get_market_evidence,
                code, as_of, item.industry, item.industry_aliases, refresh=self.get_argument("refresh", "0") == "1")
            result["mapping"] = {"industry": item.industry, "configuredName": item.name, "proxyType": item.proxy_type,
                                 "proxyNote": item.proxy_note, "basis": "轮动候选配置与显式行业别名，不按ETF名称模糊匹配"}
            self.write_success(result)
        except MarketDataError:
            self.write_error(502, "market_evidence_unavailable", "交叉证据暂不可用，请重试")


def market_workbench_runtime_stats():
    stats = _RESULT_CACHE.stats()
    stats["inflight"] = len(_INFLIGHT)
    return stats


class MarketWorkbenchSnapshotHandler(AnalysisApiHandler):
    async def get(self) -> None:
        try:
            scan_limit = int(self.get_argument("scanLimit", "100"))
            refresh = self.get_argument("refresh", "0") == "1"
        except ValueError:
            self.write_error(400, "invalid_parameters", "市场扫描数量格式不正确")
            return
        try:
            provider = get_market_data_provider()
            cache_key = (provider.name, scan_limit)
            result = _RESULT_CACHE.get(cache_key)
            cache_hit = not refresh and result is not None
            owns_task = False
            if refresh or result is None:
                task = _INFLIGHT.get(cache_key)
                owns_task = task is None
                if task is None:
                    task = asyncio.create_task(asyncio.to_thread(
                        MarketWorkbenchEngine(provider).analyze,
                        scan_limit=scan_limit,
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
            if cache_hit or not owns_task:
                self.write_success(result, meta={"cache": market_workbench_runtime_stats()})
            else:
                self.write_analysis_success(
                    result,
                    module_id="market-workbench",
                    title="市场复盘",
                    parameters={"scanLimit": scan_limit},
                    meta={"cache": market_workbench_runtime_stats()},
                )
        except MarketWorkbenchError as exc:
            self.write_error(400, "invalid_market_workbench_request", str(exc))
        except MarketDataError as exc:
            self.write_error(502, "market_data_unavailable", str(exc))
        except Exception:  # noqa: BLE001
            logging.exception("市场复盘接口异常")
            self.write_error(500, "internal_error", "市场复盘分析异常")
