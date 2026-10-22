#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Versioned HTTP handler for the single-stock research dossier."""

from __future__ import annotations

import asyncio
import logging
import re

from instock.core.analysis_snapshot import get_analysis_snapshot_registry
from instock.core.market_data_provider import MarketDataError, get_market_data_provider
from instock.core.research import StockResearchDossier, StockResearchError
from instock.web.api_contract import AnalysisApiHandler
from instock.web.result_cache import AsyncTaskCoalescer, BoundedTTLCache


_RESULT_CACHE = BoundedTTLCache(max_entries=64, ttl_seconds=300)
_INFLIGHT = AsyncTaskCoalescer()
_STATEMENT_INFLIGHT = AsyncTaskCoalescer()


def stock_research_runtime_stats():
    stats = _RESULT_CACHE.stats()
    stats["inflight"] = len(_INFLIGHT) + len(_STATEMENT_INFLIGHT)
    return stats


class StockStatementAnnouncementsHandler(AnalysisApiHandler):
    async def get(self) -> None:
        symbol = self.get_argument("symbol", "").strip().split(".")[0]
        if not re.fullmatch(r"\d{6}", symbol):
            self.write_error(400, "invalid_statement_request", "请输入六位证券代码")
            return
        key = ("list", symbol)
        task = _STATEMENT_INFLIGHT.get(key)
        owns_task = task is None
        if task is None:
            task = asyncio.create_task(asyncio.to_thread(get_market_data_provider().get_statement_announcements, symbol))
            _STATEMENT_INFLIGHT.set(key, task)
        try:
            self.write_success(await task)
        except MarketDataError as error:
            self.write_error(502, "statement_announcements_unavailable", str(error))
        except Exception:
            logging.exception("财报原件列表读取异常")
            self.write_error(500, "statement_announcements_failed", "财报列表读取失败，可直接粘贴已知公告链接")
        finally:
            if owns_task:
                _STATEMENT_INFLIGHT.discard(key, task)


class StockStatementEvidenceHandler(AnalysisApiHandler):
    async def get(self) -> None:
        symbol = self.get_argument("symbol", "").strip().split(".")[0]
        announcement = self.get_argument("announcementId", "").strip()
        source = self.get_argument("source", "eastmoney").strip()
        pattern = r"\d{10,20}" if source == "cninfo" else r"AN\d{10,30}"
        if source not in {"eastmoney", "cninfo"} or not re.fullmatch(r"\d{6}", symbol) or not re.fullmatch(pattern, announcement):
            self.write_error(400, "invalid_statement_request", "请输入六位证券代码及有效公告编号")
            return
        key = (source, symbol, announcement)
        task = _STATEMENT_INFLIGHT.get(key)
        owns_task = task is None
        if task is None:
            kwargs = {"source": source} if source != "eastmoney" else {}
            task = asyncio.create_task(asyncio.to_thread(get_market_data_provider().get_statement_evidence, symbol, announcement, **kwargs))
            _STATEMENT_INFLIGHT.set(key, task)
        try:
            self.write_success(await task)
        except MarketDataError as error:
            self.write_error(502, "statement_evidence_unavailable", str(error))
        except Exception:
            logging.exception("财报原件读取异常")
            self.write_error(500, "statement_evidence_failed", "财报原件读取失败，未完成核对")
        finally:
            if owns_task:
                _STATEMENT_INFLIGHT.discard(key, task)


class StockResearchDossierHandler(AnalysisApiHandler):
    async def get(self) -> None:
        symbol = self.get_argument("symbol", "").strip()
        period = self.get_argument("period", "daily").strip()
        as_of = self.get_argument("asOf", "").strip() or None
        industry_chain_snapshot_id = (
            self.get_argument("industryChainSnapshotId", "").strip() or None
        )
        event_flow_snapshot_id = (
            self.get_argument("eventFlowSnapshotId", "").strip() or None
        )
        refresh = self.get_argument("refresh", "0") == "1"
        try:
            bars = int(self.get_argument("bars", "240"))
        except ValueError:
            self.write_error(400, "invalid_parameters", "历史窗口必须是整数")
            return

        try:
            provider = get_market_data_provider()
            cache_key = (
                provider.name,
                symbol.upper(),
                period,
                bars,
                as_of or "latest",
                industry_chain_snapshot_id,
                event_flow_snapshot_id,
            )
            result = _RESULT_CACHE.get(cache_key)
            cache_hit = not refresh and result is not None
            owns_task = False
            if refresh or result is None:
                task = _INFLIGHT.get(cache_key)
                owns_task = task is None
                if task is None:
                    task = asyncio.create_task(asyncio.to_thread(
                        StockResearchDossier(provider).analyze,
                        symbol=symbol,
                        period=period,
                        bars=bars,
                        as_of=as_of,
                        industry_chain_snapshot_id=industry_chain_snapshot_id,
                        event_flow_snapshot_id=event_flow_snapshot_id,
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
            identity = result.get("identity") or {}
            title = "公司档案"
            if identity.get("name") or identity.get("symbol"):
                title = f"{identity.get('name') or identity.get('symbol')} · 公司档案"
            parameters = {
                "symbol": symbol,
                "period": period,
                "bars": bars,
                "asOf": as_of,
                "industryChainSnapshotId": industry_chain_snapshot_id,
                "eventFlowSnapshotId": event_flow_snapshot_id,
            }
            if cache_hit or not owns_task:
                self.write_success(result, meta={"cache": stock_research_runtime_stats()})
            else:
                self.write_analysis_success(
                    result,
                    module_id="stock-research",
                    title=title,
                    parameters=parameters,
                    meta={"cache": stock_research_runtime_stats()},
                )
        except StockResearchError as exc:
            self.write_error(400, "invalid_stock_research_request", str(exc))
        except MarketDataError:
            logging.exception("公司档案市场数据读取失败")
            self.write_error(502, "market_data_unavailable", "行情或财务数据暂不可用，本次档案未生成。请检查数据服务连接后重试。")
        except Exception:  # noqa: BLE001
            logging.exception("公司档案接口异常")
            self.write_error(500, "internal_error", "公司档案生成异常")
