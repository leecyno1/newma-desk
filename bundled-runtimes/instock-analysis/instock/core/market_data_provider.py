#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Market data adapters used by analysis features.

The analysis layer only depends on :class:`MarketDataProvider`.  The default
adapter keeps the upstream InStock application runnable on its own, while the
``newma-desk`` adapter consumes Newma-Desk's unified research data interface
and keeps the older VibeDesk endpoints and names as compatibility fallbacks.
Nothing in this module requires changes to Newma-Desk itself.
"""

from __future__ import annotations

import logging
import math
import os
import time
from abc import ABC, abstractmethod
from collections import OrderedDict
from copy import deepcopy
from datetime import datetime, timedelta
from functools import lru_cache
from threading import RLock
from typing import Any, Dict, Optional
from urllib.parse import urlsplit

import pandas as pd
import requests

from instock.core.analysis_snapshot import normalize_as_of
from instock.runtime import validate_market_services_url


class MarketDataError(RuntimeError):
    """Raised when a configured market-data adapter cannot return valid bars."""

    def __init__(self, message: str, *, code: str = ""):
        super().__init__(message)
        self.code = code


class MarketScanUnavailable(MarketDataError):
    """The scan service failed; sibling sort axes are not a new data source."""


class HistoricalWindowUnavailable(MarketDataError):
    """Raised when the upstream latest-window interface cannot reach ``as_of``."""


def _number(value: Any) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    return number if math.isfinite(number) else 0.0


def _scan_number(value: Any) -> Optional[float]:
    """Missing scan metrics are not zero (especially ascending PE/PB ranks)."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


class MarketDataProvider(ABC):
    """Small, stable boundary between the web/API layer and market data."""

    name = "unknown"

    @abstractmethod
    def get_kline(
        self,
        symbol: str,
        period: str = "daily",
        limit: int = 480,
        as_of: Optional[str] = None,
    ) -> pd.DataFrame:
        """Return normalized OHLCV data sorted from old to new."""

    def get_industry_ranking(self, top: int = 50) -> Dict[str, Any]:
        """Return the optional market-wide industry breadth/ranking snapshot."""

        return {"top": [], "bottom": [], "total": 0}

    def get_signal_kline(
        self,
        symbol: str,
        period: str = "daily",
        limit: int = 480,
        as_of: Optional[str] = None,
    ) -> pd.DataFrame:
        """Return the price series used for ranking signals.

        Providers without a dedicated index endpoint keep the old behavior.
        Rotation callers decide whether a failed industry index should fall
        back to the tradable ETF.
        """

        return self.get_kline(symbol, period, limit, as_of)

    def supports_signal_kline(self, symbol: str) -> bool:
        """Return whether the provider can load the requested signal symbol."""

        return True

    def get_market_overview(self) -> Dict[str, Any]:
        """Return optional aggregate market breadth without affecting rankings."""

        return {"sentiment": {}, "sectors": [], "updated": ""}

    def get_market_structure(self, *, refresh=False) -> Dict[str, Any]:
        raise MarketDataError("当前数据源尚未接入市场结构")

    def get_trading_calendar(self, start: str, end: str) -> Dict[str, Any]:
        raise MarketDataError("当前数据源尚未接入独立交易日历，不能用行情日期推定开休市")

    def get_execution_prices(self, symbol: str, start: str, end: str) -> Dict[str, Any]:
        raise MarketDataError("当前数据源尚未接入历史未复权价与涨跌停价")

    def get_market_evidence(self, code, as_of, industry, aliases, *, refresh=False) -> Dict[str, Any]:
        raise MarketDataError("当前数据源尚未接入复盘交叉证据")

    def get_market_emotion(self) -> Dict[str, Any]:
        """Return the host's objective limit-up and board-ladder snapshot."""

        return {"state": "unavailable", "leaders": [], "ladder": []}

    def health(self) -> Dict[str, Any]:
        """Return a cheap connectivity probe for the configured data boundary."""

        return {
            "status": "unknown",
            "provider": self.name,
            "reason": "health_probe_not_supported",
        }

    def get_stock_scan(
        self,
        *,
        market: str = "CN",
        sort: str = "amount",
        order: str = "desc",
        limit: int = 50,
    ) -> Dict[str, Any]:
        """Return one normalized stock cross-sectional scan."""

        raise MarketDataError(f"{self.name} 行情适配器不支持 {market} 候选扫描")

    def get_market_turnover_top(self, *, limit: int = 20) -> Dict[str, Any]:
        """Return a full-market turnover leaderboard when the host exposes one."""

        raise MarketDataError(f"{self.name} 行情适配器不支持全市场成交额榜")

    def get_security_master_status(self) -> Dict[str, Any]:
        """Return host security-master coverage without assuming enumeration."""

        return {
            "state": "unavailable",
            "enumerable": False,
            "count": 0,
            "exchanges": {},
            "source": self.name,
        }

    def get_liquidity_scan(self, *, limit: int = 50) -> Dict[str, Any]:
        """Return the best available liquidity-ranked A-share universe."""

        return self.get_stock_scan(sort="amount", order="desc", limit=limit)

    def get_candidate_universe(
        self,
        *,
        markets: tuple[str, ...] = ("CN",),
        per_scan_limit: int = 200,
    ) -> Dict[str, Any]:
        """Return the broadest candidate universe exposed by the provider."""

        if markets != ("CN",):
            raise MarketDataError(f"{self.name} 行情适配器不支持跨市场候选池")
        return self.get_liquidity_scan(limit=per_scan_limit)

    def get_equity_snapshot(
        self,
        symbol: str,
        *,
        refresh: bool = False,
    ) -> Dict[str, Any]:
        """Return Desk's point-in-time financial and valuation research packet."""

        raise MarketDataError(f"{self.name} 行情适配器不支持股票研究快照")

    def get_equity_comparison(
        self,
        symbols: list[str],
        *,
        refresh: bool = False,
    ) -> Dict[str, Any]:
        """Return a compact batch of financial factor rows when available."""

        raise MarketDataError(f"{self.name} 行情适配器不支持股票横向比较")

    def get_rotation_slow_factors(
        self,
        universe: list[Dict[str, str]],
        *,
        as_of: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Return optional point-in-time industry valuation and quality scores."""

        return {"as_of": as_of or "", "source": "", "items": {}, "state": "not_configured",
                "reason": "尚未接入行业级、带可用日期与来源的估值和基本面因子；不使用当前个股财务冒充行业点时证据。"}

    def get_security_announcements(self, symbol: str) -> list[Dict[str, Any]]:
        raise MarketDataError(f"{self.name} 行情适配器不支持公告数据")

    def get_statement_evidence(self, symbol: str, announcement_id: str, source: str = "eastmoney") -> Dict[str, Any]:
        raise MarketDataError(f"{self.name} 行情适配器不支持财报原件读取")

    def get_statement_announcements(self, symbol: str) -> Dict[str, Any]:
        raise MarketDataError(f"{self.name} 行情适配器不支持财报原件检索")

    def get_security_reports(self, symbol: str, pages: int = 1) -> list[Dict[str, Any]]:
        raise MarketDataError(f"{self.name} 行情适配器不支持研报数据")

    def get_security_news(self, symbol: str, limit: int = 10) -> list[Dict[str, Any]]:
        raise MarketDataError(f"{self.name} 行情适配器不支持新闻数据")

    def get_security_event_flow(self, symbol: str) -> Dict[str, Any]:
        """Return Desk-hosted capital-flow and corporate-event evidence."""

        raise MarketDataError(f"{self.name} 行情适配器不支持事件与资金数据")

    def get_dragon_tiger_evidence(self, symbol: str) -> Dict[str, Any]:
        """Return security-level dragon-tiger and institutional-seat evidence."""

        raise MarketDataError(f"{self.name} 行情适配器不支持龙虎榜机构证据")


def get_scan_history(provider, item, *, limit: int) -> pd.DataFrame:
    """Keep technical daily bars within the source scan's completed trading date."""
    symbol = str(item["symbol"]).split(".")[0]
    if str(item.get("market") or "CN").upper() == "HK":
        symbol += ".HK"
    if item.get("scan_frequency") != "daily":
        return provider.get_kline(symbol, period="daily", limit=limit)
    cutoff = normalize_as_of(str(item.get("scan_as_of") or "")[:10])
    if not cutoff:
        raise MarketDataError("日频扫描缺少有效截止日，不能混用最新日线")
    frame = provider.get_kline(symbol, period="daily", limit=limit, as_of=cutoff)
    dates = pd.to_datetime(frame["date"], errors="coerce").dt.date
    frame = frame.loc[dates <= pd.Timestamp(cutoff).date()].tail(limit).copy()
    if frame.empty:
        raise MarketDataError(f"日频扫描截止 {cutoff} 没有可用日线")
    return frame.reset_index(drop=True)


def _normalize_kline(
    data: Any,
    *,
    period: str,
    limit: int,
    source: str,
    as_of: Optional[str] = None,
) -> pd.DataFrame:
    if data is None:
        raise MarketDataError("行情接口返回空数据")
    frame = data.copy() if isinstance(data, pd.DataFrame) else pd.DataFrame(data)
    if frame.empty:
        raise MarketDataError("行情接口返回空数据")

    frame = frame.rename(columns={
        "日期": "date", "时间": "date", "datetime": "date", "dt": "date", "timestamp": "date",
        "开盘": "open", "收盘": "close", "最高": "high", "最低": "low",
        "成交量": "volume", "vol": "volume", "成交额": "amount", "turnover": "amount",
        "股票代码": "symbol", "code": "symbol",
    })
    # 某些既有接口会同时返回 vol 和 volume；标准化后保留最后一个
    # 明确的 canonical 字段，避免 pandas 取列时得到二维 DataFrame。
    frame = frame.loc[:, ~frame.columns.duplicated(keep="last")]
    required = ["date", "open", "high", "low", "close", "volume"]
    missing = [column for column in required if column not in frame.columns]
    if missing:
        raise MarketDataError(f"行情字段缺失: {', '.join(missing)}")

    if pd.api.types.is_numeric_dtype(frame["date"]):
        numeric_dates = pd.to_numeric(frame["date"], errors="coerce")
        median_date = numeric_dates.dropna().median() if numeric_dates.notna().any() else 0
        unit = "ms" if median_date > 100_000_000_000 else "s"
        frame["date"] = (
            pd.to_datetime(numeric_dates, unit=unit, errors="coerce", utc=True)
            .dt.tz_convert("Asia/Shanghai")
            .dt.tz_localize(None)
        )
    else:
        frame["date"] = pd.to_datetime(frame["date"], errors="coerce")
    if "amount" not in frame.columns:
        frame["amount"] = 0.0
    for column in ["open", "high", "low", "close", "volume", "amount"]:
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    frame = frame.dropna(subset=required).sort_values("date")
    frame = frame.drop_duplicates(subset=["date"], keep="last").reset_index(drop=True)
    if frame.empty:
        raise MarketDataError("行情清洗后没有有效 K 线")

    source_window_start = frame["date"].iloc[0].strftime("%Y-%m-%d")
    source_window_end = frame["date"].iloc[-1].strftime("%Y-%m-%d")
    normalized_as_of = normalize_as_of(as_of)
    if normalized_as_of:
        frame = frame[frame["date"] <= pd.Timestamp(normalized_as_of)].copy()
        if frame.empty:
            raise HistoricalWindowUnavailable(
                f"上游最近窗口最早从 {source_window_start} 开始，无法回放至 {normalized_as_of}"
            )

    if period != "daily":
        rule = "W-FRI" if period == "weekly" else "ME"
        frame["_actual_date"] = frame["date"]
        frame = (frame.set_index("date").resample(rule).agg({
            "_actual_date": "last",
            "open": "first", "high": "max", "low": "min", "close": "last",
            "volume": "sum", "amount": "sum",
        }).dropna(subset=["open", "close"])
            .rename(columns={"_actual_date": "date"}).reset_index(drop=True))

    frame = frame.tail(limit).reset_index(drop=True)
    frame.attrs["data_source"] = source
    frame.attrs["requested_as_of"] = normalized_as_of
    frame.attrs["as_of_mode"] = "client_filter" if normalized_as_of else "latest"
    frame.attrs["source_window_start"] = source_window_start
    frame.attrs["source_window_end"] = source_window_end
    return frame


class InStockMarketDataProvider(MarketDataProvider):
    """Use the current upstream project's fetch/cache implementation."""

    name = "instock"

    def get_trading_calendar(self, start: str, end: str) -> Dict[str, Any]:
        try:
            from instock.core.crawling.trade_date_hist import tool_trade_date_hist_sina
            frame = tool_trade_date_hist_sina()
            dates = pd.DatetimeIndex(pd.to_datetime(frame["trade_date"])).sort_values().unique()
        except ImportError as exc:
            raise MarketDataError("Sina 日历解码依赖未安装，请使用已配置的 Desk 日历数据源") from exc
        except Exception as exc:
            raise MarketDataError("Sina 独立交易日历读取失败，未用行情日期替代") from exc
        if dates.empty or dates.hasnans or dates[0] > pd.Timestamp(start) or dates[-1] < pd.Timestamp(end):
            raise MarketDataError("Sina 交易日历未覆盖请求区间，不能将区间外日期视为休市")
        return {"status": "ready", "exchange": "SSE", "start": start, "end": end,
                "sessions": dates[(dates >= pd.Timestamp(start)) & (dates <= pd.Timestamp(end))].strftime("%Y-%m-%d").tolist(),
                "source": "Sina 上海交易日列表", "receivedAt": datetime.now().astimezone().isoformat(),
                "coverage": {"sourceStart": dates[0].strftime("%Y-%m-%d"), "sourceEnd": dates[-1].strftime("%Y-%m-%d"),
                             "validation": "source_session_list_bounds_not_daily_open_closed_records"}}

    def get_kline(
        self,
        symbol: str,
        period: str = "daily",
        limit: int = 480,
        as_of: Optional[str] = None,
    ) -> pd.DataFrame:
        from instock.core import stockfetch

        multiplier = {"daily": 2, "weekly": 9, "monthly": 38}.get(period)
        if multiplier is None:
            raise MarketDataError(f"不支持的周期: {period}")
        normalized_as_of = normalize_as_of(as_of)
        anchor = pd.Timestamp(normalized_as_of).to_pydatetime() if normalized_as_of else datetime.now()
        start_date = (anchor - timedelta(days=limit * multiplier)).strftime("%Y%m%d")
        code = symbol.split(".")[0]
        if code.startswith(("1", "5")):
            raw = stockfetch.fetch_etf_hist(
                (anchor.date(), code),
                date_start=start_date,
                date_end=anchor.strftime("%Y%m%d") if normalized_as_of else None,
            )
        else:
            raw = stockfetch.fetch_stock_hist(
                (anchor.date(), code), date_start=start_date, is_cache=True
            )
        frame = _normalize_kline(
            raw, period=period, limit=limit, source=self.name, as_of=normalized_as_of
        )
        frame.attrs["data_endpoint"] = "instock.stockfetch"
        frame.attrs["adjust"] = "qfq"
        frame.attrs["upstream_limit"] = None
        return frame

    def get_signal_kline(
        self,
        symbol: str,
        period: str = "daily",
        limit: int = 480,
        as_of: Optional[str] = None,
    ) -> pd.DataFrame:
        if symbol.upper().endswith(".SI"):
            raise MarketDataError("InStock 原行情源不提供申万行业指数")
        return self.get_kline(symbol, period, limit, as_of)

    def supports_signal_kline(self, symbol: str) -> bool:
        return not str(symbol or "").upper().endswith(".SI")


class NewmaDeskMarketDataProvider(MarketDataProvider):
    """Thin client for Newma-Desk's unified research data API."""

    name = "newma-desk"
    _CATEGORY = {"daily": 4, "weekly": 5, "monthly": 6}
    _TIMEFRAME = {"daily": "1d", "weekly": "1w", "monthly": "1M"}
    _EVENT_FLOW_SOURCES = (
        (
            "fund_flow", "主力资金", "/api/fund-flow",
            {"main_net": "元", "small_net": "元", "mid_net": "元", "large_net": "元", "super_net": "元"},
        ),
        (
            "dragon_tiger", "龙虎榜", "/api/dragon-tiger",
            {"net_buy": "万元", "seat_amount": "万元", "turnover": "%"},
        ),
        (
            "margin", "融资融券", "/api/margin",
            {"rzye": "元", "rzmre": "元", "rzche": "元", "rqye": "元", "rqmcl": "股", "rzrqye": "元"},
        ),
        (
            "block_trade", "大宗交易", "/api/block-trade",
            {"price": "元/股", "premium_pct": "%", "vol": "股", "amount": "元"},
        ),
        (
            "holders", "股东户数", "/api/holders",
            {"holder_num": "户", "change_ratio": "%", "avg_shares": "股/户"},
        ),
        (
            "dividend", "分红送转", "/api/dividend",
            {"bonus_rmb": "元/每10股", "transfer_ratio": "股/每10股", "bonus_ratio": "股/每10股"},
        ),
        (
            "lockup", "限售解禁", "/api/lockup",
            {"shares": "万股", "able_shares": "万股", "ratio": "比例"},
        ),
    )

    def __init__(self, base_url: str, token: str = "", timeout: float = 20.0,
                 *, market_services_url: str = "", market_services_token: str = ""):
        self.base_url = base_url.rstrip("/")
        self.token = token.strip()
        self.timeout = timeout
        parsed_base_url = urlsplit(self.base_url)
        self._use_data_service_gateway = parsed_base_url.path.rstrip("/") == "/api/research"
        self._desk_origin = (
            f"{parsed_base_url.scheme}://{parsed_base_url.netloc}"
            if parsed_base_url.scheme and parsed_base_url.netloc
            else self.base_url
        )
        self.market_services_url = (
            validate_market_services_url(market_services_url) if market_services_url
            else self._desk_origin if self._use_data_service_gateway else ""
        )
        # Only the legacy integrated gateway shares credentials. Explicit
        # services never inherit the Research token, including on the same host.
        self.market_services_token = (
            market_services_token.strip() if market_services_url
            else self.token if self._use_data_service_gateway else ""
        )
        self._equity_snapshot_cache: OrderedDict[str, tuple[float, Dict[str, Any]]] = (
            OrderedDict()
        )
        self._equity_snapshot_cache_lock = RLock()
        self._equity_snapshot_cache_ttl = max(
            0.0,
            float(os.environ.get("INSTOCK_EQUITY_SNAPSHOT_CACHE_TTL_SECONDS", "300")),
        )
        self._equity_snapshot_cache_max_entries = max(
            1,
            int(os.environ.get("INSTOCK_EQUITY_SNAPSHOT_CACHE_MAX_ENTRIES", "256")),
        )
        self._equity_comparison_cache: OrderedDict[
            tuple[str, ...], tuple[float, Dict[str, Any]]
        ] = OrderedDict()
        self._equity_comparison_cache_lock = RLock()
        self._equity_comparison_cache_ttl = max(
            0.0,
            float(os.environ.get("INSTOCK_EQUITY_COMPARISON_CACHE_TTL_SECONDS", "300")),
        )
        self._equity_comparison_cache_max_entries = max(
            1,
            int(os.environ.get("INSTOCK_EQUITY_COMPARISON_CACHE_MAX_ENTRIES", "64")),
        )

    def _get(self, url: str, **kwargs):
        if self._is_loopback(url):
            kwargs["proxies"] = {"http": None, "https": None}
        return requests.get(url, **kwargs)

    def _post(self, url: str, **kwargs):
        if self._is_loopback(url):
            kwargs["proxies"] = {"http": None, "https": None}
        return requests.post(url, **kwargs)

    @staticmethod
    def _is_loopback(url: str) -> bool:
        hostname = (urlsplit(url).hostname or "").lower()
        return hostname == "localhost" or hostname == "::1" or hostname.startswith("127.")

    def _research_url(self, path: str) -> str:
        if self._use_data_service_gateway:
            return f"{self.base_url}{path}"
        # Standalone configuration accepts either the server root or its API
        # prefix. Older callers include /api while newer research calls do not.
        base = self.base_url if urlsplit(self.base_url).path.rstrip("/") else self.base_url + "/api"
        return base + (path[4:] if path.startswith("/api/") else path)

    def _request_capability(
        self,
        capability: str,
        direct_path: str,
        parameters: Dict[str, Any],
        *,
        headers: Dict[str, str],
        timeout: Optional[float] = None,
    ):
        request_timeout = self.timeout if timeout is None else timeout
        if self._use_data_service_gateway:
            return self._post(
                f"{self._desk_origin}/api/data-services/market-data/invoke/{capability}",
                json=parameters,
                headers=headers,
                timeout=request_timeout,
            )
        return self._get(
            self._research_url(direct_path),
            params=parameters,
            headers=headers,
            timeout=request_timeout,
        )

    def _invoke_json_capability(
        self,
        capability: str,
        direct_path: str,
        parameters: Dict[str, Any],
        *,
        timeout: Optional[float] = None,
    ) -> Any:
        headers: Dict[str, str] = {"Accept": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        payload = None
        last_error: Exception | None = None
        error_code = ""
        for attempt in range(2):
            try:
                response = self._request_capability(
                    capability,
                    direct_path,
                    parameters,
                    headers=headers,
                    timeout=timeout,
                )
                response.raise_for_status()
                payload = response.json()
                break
            except (requests.RequestException, ValueError) as exc:
                last_error = exc
                status_code = getattr(getattr(exc, "response", None), "status_code", None)
                error_code = {401: "UPSTREAM_AUTH_REQUIRED", 403: "UPSTREAM_FORBIDDEN"}.get(status_code, "")
                if isinstance(exc, requests.Timeout):
                    error_code = "UPSTREAM_TIMEOUT"
                error_response = getattr(exc, "response", None)
                if error_response is not None:
                    try:
                        body = error_response.json()
                        upstream_code = (body.get("error") or {}).get("code") if isinstance(body, dict) else None
                        if upstream_code in {"UPSTREAM_TIMEOUT", "UPSTREAM_AUTH_REQUIRED", "UPSTREAM_FORBIDDEN"}:
                            error_code = upstream_code
                    except (ValueError, AttributeError, TypeError):
                        pass  # HTTP status still identifies the failure; never expose the raw body.
                if attempt == 0 and not error_code and status_code in {502, 503, 504}:
                    time.sleep(0.1)
                    continue
                break
        if payload is None:
            reason = {
                "UPSTREAM_AUTH_REQUIRED": "数据服务鉴权失败，请检查服务端凭据",
                "UPSTREAM_FORBIDDEN": "数据服务拒绝访问，请检查服务端权限",
                "UPSTREAM_TIMEOUT": "数据服务响应超时，结果未确认；未自动重试",
            }.get(error_code, "数据服务请求失败，未取得有效数据")
            logging.warning("%s capability failed (%s)", capability, error_code or type(last_error).__name__)
            raise MarketDataError(
                f"Newma-Desk {capability}: {reason}", code=error_code
            ) from last_error
        return payload.get("data", payload) if isinstance(payload, dict) else payload

    def _invoke_research_http(
        self,
        direct_path: str,
        parameters: Dict[str, Any],
        *,
        timeout: Optional[float] = None,
        desk_native: bool = False,
    ) -> Any:
        """Call an existing Research HTTP Interface that is not a Data Service capability."""

        if desk_native and not self.market_services_url:
            raise MarketDataError("请配置 INSTOCK_MARKET_SERVICES_URL（或 --market-services-url）；Research 不提供基础市场服务")
        headers: Dict[str, str] = {"Accept": "application/json"}
        token = self.market_services_token if desk_native else self.token
        if token:
            headers["Authorization"] = f"Bearer {token}"
        request_timeout = self.timeout if timeout is None else max(float(timeout), 0.1)
        try:
            response = self._get(
                f"{self.market_services_url}{direct_path}" if desk_native else self._research_url(direct_path),
                params=parameters,
                headers=headers,
                timeout=request_timeout,
            )
            response.raise_for_status()
            payload = response.json()
        except (requests.RequestException, ValueError) as exc:
            if desk_native:
                logging.warning("基础市场服务 %s 请求失败 (%s)", direct_path, type(exc).__name__)
                raise MarketDataError("基础市场数据服务请求失败，请检查服务配置与可用性；未取得数据不等于无风险") from exc
            raise MarketDataError(f"Newma-Desk Research HTTP {direct_path} 请求失败: {exc}") from exc
        return payload.get("data", payload) if isinstance(payload, dict) else payload

    def health(self) -> Dict[str, Any]:
        """Probe the configured service through the same transport as its data."""

        headers: Dict[str, str] = {"Accept": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        try:
            response = self._request_capability(
                "market.health", "/health", {},
                headers=headers,
                timeout=min(max(float(self.timeout), 0.1), 2.0),
            )
            response.raise_for_status()
            payload = response.json()
        except (requests.RequestException, ValueError, TypeError) as exc:
            if self._use_data_service_gateway and getattr(getattr(exc, "response", None), "status_code", None) == 404:
                return {
                    "status": "unavailable",
                    "provider": self.name,
                    "reason": "desk_health_capability_unavailable",
                    "detail": "Desk 未提供 market.health 健康能力，请配套更新宿主数据服务声明；本次未确认数据服务状态。",
                }
            return {
                "status": "unavailable",
                "provider": self.name,
                "reason": "desk_health_unreachable",
                "detail": str(exc),
            }
        ready = isinstance(payload, dict) and payload.get("ok") is True
        return {
            "status": "ready" if ready else "unavailable",
            "provider": self.name,
            "reason": None if ready else "desk_health_invalid",
            "service": str(payload.get("service") or "") if isinstance(payload, dict) else "",
        }

    def get_kline(
        self,
        symbol: str,
        period: str = "daily",
        limit: int = 480,
        as_of: Optional[str] = None,
    ) -> pd.DataFrame:
        category = self._CATEGORY.get(period)
        timeframe = self._TIMEFRAME.get(period)
        if category is None or timeframe is None:
            raise MarketDataError(f"Newma-Desk 现有接口不支持周期: {period}")
        normalized_as_of = normalize_as_of(as_of)
        upstream_limit = 800 if normalized_as_of else min(limit, 800)
        headers: Dict[str, str] = {"Accept": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"

        symbol_code = str(symbol or "").strip().upper()
        market = "HK" if symbol_code.endswith(".HK") or (
            symbol_code.isdigit() and len(symbol_code) == 5
        ) else "CN"
        symbol_code = symbol_code.split(".")[0]
        primary_error = ""
        payload = None
        for attempt in range(3):
            try:
                response = self._request_capability(
                    "market.ohlcv",
                    "/api/market-terminal/ohlcv",
                    {
                        "symbol": symbol_code,
                        "market": market,
                        "timeframe": timeframe,
                        "limit": upstream_limit,
                        "adjust": "qfq",
                        **({"asOf": normalized_as_of} if normalized_as_of and market == "CN" and timeframe == "1d" else {}),
                    },
                    headers=headers,
                )
                response.raise_for_status()
                payload = response.json()
                break
            except (requests.RequestException, ValueError) as exc:
                status_code = getattr(getattr(exc, "response", None), "status_code", None)
                if attempt < 2 and status_code in {502, 503, 504}:
                    time.sleep(0.1 * (attempt + 1))
                    continue
                primary_error = str(exc)
                break

        if payload is not None:
            data = payload.get("data", payload) if isinstance(payload, dict) else payload
            items = data.get("items", data) if isinstance(data, dict) else data
            try:
                frame = _normalize_kline(
                    items,
                    period="daily",
                    limit=limit,
                    source=self.name,
                    as_of=normalized_as_of,
                )
                frame.attrs["data_endpoint"] = "/api/market-terminal/ohlcv"
                actual_adjust = data.get("adjust") if isinstance(data, dict) else None
                frame.attrs["adjust"] = actual_adjust if actual_adjust in ("qfq", "hfq", "none") else "unknown"
                frame.attrs["upstream_limit"] = upstream_limit
                frame.attrs["upstream_has_more"] = (
                    data.get("hasMore") if isinstance(data, dict) else None
                )
                if isinstance(data, dict):
                    # Preserve the data service's own provenance instead of
                    # reducing every successful response to the generic
                    # ``newma-desk`` adapter name.  These fields remain
                    # evidence only; analysis code still depends solely on
                    # the normalized OHLCV columns above.
                    frame.attrs["upstream_source"] = str(data.get("source") or "")
                    frame.attrs["upstream_as_of"] = str(data.get("asOf") or "")
                    frame.attrs["upstream_market"] = str(data.get("market") or market)
                    frame.attrs["upstream_timeframe"] = str(
                        data.get("timeframe") or timeframe
                    )
                if normalized_as_of:
                    frame.attrs["replay_limitations"] = [
                        "upstream_no_historical_anchor",
                        "latest_800_bars_client_filter",
                    ]
                return frame
            except HistoricalWindowUnavailable:
                raise
            except MarketDataError as exc:
                primary_error = str(exc)

        if self._use_data_service_gateway:
            raise MarketDataError(
                f"Newma-Desk market.ohlcv capability 请求失败: {primary_error or '返回无有效行情'}"
            )

        # Compatibility fallback for older VibeDesk installations that expose
        # /api/kline but not the unified adjusted market-terminal endpoint.
        try:
            response = self._get(
                self._research_url("/api/kline"),
                params={"code": symbol_code, "category": category, "offset": upstream_limit},
                headers=headers,
                timeout=self.timeout,
            )
            response.raise_for_status()
            payload = response.json()
        except (requests.RequestException, ValueError) as exc:
            detail = f"；前复权接口异常: {primary_error}" if primary_error else ""
            raise MarketDataError(f"Newma-Desk 行情请求失败: {exc}{detail}") from exc

        items = payload.get("data", payload) if isinstance(payload, dict) else payload
        frame = _normalize_kline(
            items,
            period="daily",
            limit=limit,
            source=self.name,
            as_of=normalized_as_of,
        )
        frame.attrs["data_endpoint"] = "/api/kline"
        frame.attrs["adjust"] = "unknown"
        frame.attrs["upstream_limit"] = upstream_limit
        frame.attrs["upstream_has_more"] = None
        frame.attrs["upstream_source"] = ""
        frame.attrs["upstream_as_of"] = ""
        frame.attrs["upstream_market"] = market
        frame.attrs["upstream_timeframe"] = timeframe
        if normalized_as_of:
            frame.attrs["replay_limitations"] = [
                "upstream_no_historical_anchor",
                "latest_800_bars_client_filter",
                "compatibility_adjustment_unknown",
            ]
        return frame

    def get_signal_kline(
        self,
        symbol: str,
        period: str = "daily",
        limit: int = 480,
        as_of: Optional[str] = None,
    ) -> pd.DataFrame:
        """Fetch an unadjusted index series without using the legacy fallback."""

        timeframe = self._TIMEFRAME.get(period)
        if timeframe is None:
            raise MarketDataError(f"Newma-Desk 现有接口不支持周期: {period}")
        normalized_as_of = normalize_as_of(as_of)
        upstream_limit = 800 if normalized_as_of else min(limit, 800)
        headers: Dict[str, str] = {"Accept": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"

        last_error = ""
        for attempt in range(3):
            try:
                response = self._request_capability(
                    "market.ohlcv",
                    "/api/market-terminal/ohlcv",
                    {
                        "symbol": symbol,
                        "market": "CN",
                        "timeframe": timeframe,
                        "limit": upstream_limit,
                        "adjust": "none",
                        "assetType": "index",
                    },
                    headers=headers,
                )
                response.raise_for_status()
                payload = response.json()
                data = payload.get("data", payload) if isinstance(payload, dict) else payload
                items = data.get("items", data) if isinstance(data, dict) else data
                frame = _normalize_kline(
                    items,
                    period="daily",
                    limit=limit,
                    source=self.name,
                    as_of=normalized_as_of,
                )
                frame.attrs["data_endpoint"] = "/api/market-terminal/ohlcv"
                actual_adjust = data.get("adjust") if isinstance(data, dict) else None
                frame.attrs["adjust"] = actual_adjust if actual_adjust in ("qfq", "hfq", "none") else "unknown"
                frame.attrs["upstream_limit"] = upstream_limit
                frame.attrs["upstream_has_more"] = (
                    data.get("hasMore") if isinstance(data, dict) else None
                )
                if isinstance(data, dict):
                    frame.attrs["upstream_source"] = str(data.get("source") or "")
                    frame.attrs["upstream_as_of"] = str(data.get("asOf") or "")
                    frame.attrs["upstream_market"] = str(data.get("market") or "CN")
                    frame.attrs["upstream_timeframe"] = str(
                        data.get("timeframe") or timeframe
                    )
                if normalized_as_of:
                    frame.attrs["replay_limitations"] = [
                        "upstream_no_historical_anchor",
                        "latest_800_bars_client_filter",
                    ]
                return frame
            except HistoricalWindowUnavailable:
                raise
            except (requests.RequestException, ValueError, MarketDataError) as exc:
                status_code = getattr(getattr(exc, "response", None), "status_code", None)
                if attempt < 2 and status_code in {502, 503, 504}:
                    time.sleep(0.1 * (attempt + 1))
                    continue
                last_error = str(exc)
                break
        raise MarketDataError(f"Newma-Desk 指数信号请求失败: {last_error or '未知错误'}")

    def supports_signal_kline(self, symbol: str) -> bool:
        # Desk 当前的 CN OHLCV 路由面向交易所证券；申万 .SI 指数会落入
        # mootdx 股票路由并返回空集。轮动模块据此直接使用同行业 ETF 代理。
        return not str(symbol or "").upper().endswith(".SI")

    def get_industry_ranking(self, top: int = 50) -> Dict[str, Any]:
        headers: Dict[str, str] = {"Accept": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        primary_error = ""
        payload = None
        if not self._use_data_service_gateway:
            try:
                response = self._get(
                    self._research_url("/api/industry"),
                    params={"top": max(5, min(int(top), 50))},
                    headers=headers,
                    timeout=self.timeout,
                )
                response.raise_for_status()
                payload = response.json()
            except (requests.RequestException, ValueError) as exc:
                primary_error = str(exc)

        if payload is not None:
            data = payload.get("data", payload) if isinstance(payload, dict) else payload
            if isinstance(data, dict):
                result = {
                    **data,
                    "top": data.get("top") or [],
                    "bottom": data.get("bottom") or [],
                    "total": int(data.get("total") or 0),
                }
                if result["top"] or result["bottom"]:
                    return result

        overview = self.get_market_overview()
        breadth = overview.get("industryBreadth")
        if isinstance(breadth, dict):
            if not breadth.get("top") and not breadth.get("bottom"):
                raise MarketDataError("日频行业广度暂不可用，未混用其他分类或时点")
            return breadth
        sectors = [
            item for item in overview.get("sectors", [])
            if isinstance(item, dict) and item.get("name") and _scan_number(item.get("pct")) is not None
        ]
        sectors.sort(key=lambda item: float(item.get("pct") or 0), reverse=True)
        if not sectors:
            detail = f": {primary_error}" if primary_error else ""
            raise MarketDataError(f"Newma-Desk 行业排名暂时为空{detail}")
        size = max(5, min(int(top), 50))
        rows = [
            {
                "rank": index + 1,
                "name": str(item.get("name") or ""),
                "change_pct": float(item.get("pct") or 0),
                "net": _scan_number(item.get("net")),
                "firms": _scan_number(item.get("firms")),
            }
            for index, item in enumerate(sectors)
        ]
        return {"top": rows[:size], "bottom": rows[-size:], "total": len(rows)}

    def get_market_overview(self) -> Dict[str, Any]:
        """Consume Desk's existing aggregate breadth endpoint as evidence only."""

        headers: Dict[str, str] = {"Accept": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        try:
            response = self._request_capability(
                "market.overview",
                "/api/market/overview",
                {},
                headers=headers,
            )
            response.raise_for_status()
            payload = response.json()
        except (requests.RequestException, ValueError) as exc:
            raise MarketDataError(f"Newma-Desk 市场宽度请求失败: {exc}") from exc

        data = payload.get("data", payload) if isinstance(payload, dict) else payload
        if not isinstance(data, dict):
            raise MarketDataError("Newma-Desk 市场宽度返回格式无效")
        sentiment = data.get("sentiment") or {}
        sectors = data.get("sectors") or []
        industry_breadth = data.get("industryBreadth")
        if not sentiment and not sectors and not industry_breadth:
            raise MarketDataError("Newma-Desk 市场宽度暂时为空")
        return {
            "sentiment": sentiment if isinstance(sentiment, dict) else {},
            "sectors": sectors if isinstance(sectors, list) else [],
            "updated": str(data.get("updated") or ""),
            **({"industryBreadth": industry_breadth} if isinstance(industry_breadth, dict) else {}),
        }

    def get_market_structure(self, *, refresh=False) -> Dict[str, Any]:
        data = self._invoke_research_http("/api/capital-flow/market-structure", {"refresh": str(refresh).lower()}, timeout=45, desk_native=True)
        if not isinstance(data, dict) or data.get("schemaVersion") != "newma-desk.market-structure.v1":
            raise MarketDataError("市场结构返回格式无效")
        return data

    def get_trading_calendar(self, start: str, end: str) -> Dict[str, Any]:
        data = self._invoke_research_http("/api/capital-flow/trading-calendar", {"start": start, "end": end}, desk_native=True)
        if not isinstance(data, dict) or data.get("schemaVersion") != "newma-desk.trading-calendar.v1":
            raise MarketDataError("独立交易日历返回格式无效")
        if data.get("status") != "ready":
            raise MarketDataError(data.get("reason") or "独立交易日历不可用，未改用行情日期")
        return data

    def get_market_evidence(self, code, as_of, industry, aliases, *, refresh=False) -> Dict[str, Any]:
        data = self._invoke_research_http("/api/capital-flow/market-evidence", {
            "code": code, "as_of": as_of, "industry": industry, "aliases": list(aliases), "refresh": str(refresh).lower(),
        }, timeout=60, desk_native=True)
        if not isinstance(data, dict) or data.get("schemaVersion") != "newma-desk.market-evidence.v1":
            raise MarketDataError("复盘交叉证据返回格式无效")
        return data

    def get_execution_prices(self, symbol: str, start: str, end: str) -> Dict[str, Any]:
        data = self._invoke_research_http("/api/capital-flow/execution-prices", {
            "symbol": symbol, "start": start, "end": end,
        }, timeout=45, desk_native=True)
        if (not isinstance(data, dict) or data.get("schemaVersion") != "newma-desk.execution-prices.v1"
                or data.get("symbol") != symbol or data.get("start") != start or data.get("end") != end
                or data.get("priceBasis") != "unadjusted"):
            raise MarketDataError("历史限价返回代码、日期或价格口径不匹配")
        return data

    def get_market_emotion(self) -> Dict[str, Any]:
        """Consume Desk's objective limit-up and board-ladder snapshot."""

        data = self._invoke_json_capability(
            "market.emotion", "/api/market/emotion", {}
        )
        if not isinstance(data, dict):
            raise MarketDataError("Newma-Desk 短线市场情绪返回格式无效")
        if not {"zt_count", "dt_count", "zb_count"}.issubset(data):
            raise MarketDataError("Newma-Desk 短线市场情绪缺少涨跌停统计")
        return {
            "state": "available",
            "date": str(data.get("date") or ""),
            "limit_up_count": int(_number(data.get("zt_count"))),
            "limit_down_count": int(_number(data.get("dt_count"))),
            "break_count": int(_number(data.get("zb_count"))),
            "max_boards": int(_number(data.get("max_boards"))),
            "consecutive_count": int(_number(data.get("lianban_count"))),
            "seal_rate": _number(data.get("seal_rate")),
            "break_rate": _number(data.get("break_rate")),
            "promotion_rate": _number(data.get("promotion_rate")),
            "yesterday_limit_up_count": int(_number(data.get("yzt_count"))),
            "ladder": [
                dict(item) for item in (data.get("ladder") or [])
                if isinstance(item, dict)
            ],
            "leaders": [
                dict(item) for item in (data.get("lianban_stocks") or [])
                if isinstance(item, dict)
            ],
            "source": "capability:market.emotion",
        }

    def get_stock_scan(
        self,
        *,
        market: str = "CN",
        sort: str = "amount",
        order: str = "desc",
        limit: int = 50,
    ) -> Dict[str, Any]:
        """Consume Desk's existing ``market.scan`` capability."""

        supported_sorts = {
            "changePct", "amount", "turnoverPct", "volumeRatio", "marketCap", "pe", "pb",
        }
        market = str(market or "CN").strip().upper()
        if market not in {"CN", "HK"}:
            raise MarketDataError(f"股票扫描仅支持 CN、HK，收到: {market}")
        if sort not in supported_sorts:
            raise MarketDataError(f"不支持的股票扫描排序: {sort}")
        if order not in {"asc", "desc"}:
            raise MarketDataError(f"不支持的 A 股扫描顺序: {order}")
        limit = max(20, min(int(limit), 200))
        headers: Dict[str, str] = {"Accept": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"

        def load_scan(scan_sort: str, scan_order: str, scan_limit: int):
            last_error = None
            for attempt in range(3):
                try:
                    response = self._request_capability(
                        "market.scan",
                        "/api/market-terminal/scan",
                        {
                            "market": market,
                            "sort": scan_sort,
                            "order": scan_order,
                            "limit": scan_limit,
                        },
                        headers=headers,
                    )
                    response.raise_for_status()
                    payload = response.json()
                    return payload.get("data", payload) if isinstance(payload, dict) else payload
                except (requests.RequestException, ValueError) as exc:
                    status_code = getattr(getattr(exc, "response", None), "status_code", None)
                    if attempt < 2 and status_code in {502, 503, 504}:
                        time.sleep(0.1 * (attempt + 1))
                        continue
                    last_error = exc
                    break
            logging.warning("股票扫描失败：%s / %s / %s / %s",
                            market, scan_sort, scan_order, type(last_error).__name__)
            raise MarketScanUnavailable(
                f"{market} 股票行情扫描暂不可用，未取得候选池；请检查数据服务或稍后重试。"
            ) from last_error

        data = load_scan(sort, order, limit)
        if not isinstance(data, dict) or not isinstance(data.get("items"), list):
            raise MarketDataError(f"Newma-Desk {market} 股票扫描返回格式无效")
        raw_items = [raw for raw in data["items"] if isinstance(raw, dict)]
        gateway_market_cap_fallback = False
        if (
            self._use_data_service_gateway
            and sort != "marketCap"
            and raw_items
            and not any(_number(raw.get("price")) > 0 for raw in raw_items)
        ):
            data = load_scan("marketCap", "desc", 200)
            if not isinstance(data, dict) or not isinstance(data.get("items"), list):
                raise MarketDataError(f"Newma-Desk {market} 股票扫描返回格式无效")
            raw_items = [raw for raw in data["items"] if isinstance(raw, dict)]
            gateway_market_cap_fallback = True
        source_coverage = data.get("coverage") if isinstance(data.get("coverage"), dict) else {}
        if source_coverage.get("frequency") == "daily":
            # Keep the daily cross-section coherent; never mix in a live quote.
            enriched_items, quote_as_of, quote_source = raw_items, "", ""
        else:
            enriched_items, quote_as_of, quote_source = self._enrich_scan_quotes(
                raw_items, market=market
            )
        raw_items = enriched_items or raw_items
        amount_proxy = source_coverage.get("frequency") != "daily" and sort == "amount" and not any(
            _number(raw.get("amount")) > 0 for raw in raw_items
        )
        sort_field = {
            "changePct": "changePct",
            "amount": "amount",
            "turnoverPct": "turnoverPct",
            "volumeRatio": "volumeRatio",
            "marketCap": "marketCap",
            "pe": "pe",
            "pb": "pb",
        }[sort]
        if not amount_proxy:
            known_items = [raw for raw in raw_items if _scan_number(raw.get(sort_field)) is not None]
            missing_items = [raw for raw in raw_items if _scan_number(raw.get(sort_field)) is None]
            known_items.sort(
                key=lambda raw: _scan_number(raw.get(sort_field)),
                reverse=order == "desc",
            )
            raw_items = known_items + missing_items
        raw_items = raw_items[:limit]
        items = []
        for raw in raw_items:
            symbol = str(raw.get("symbol") or raw.get("code") or "").strip()
            name = str(raw.get("name") or "").strip()
            if not symbol or not name:
                continue
            items.append({
                "symbol": symbol,
                "name": name,
                "market": str(raw.get("market") or market).upper(),
                "exchange": str(raw.get("exchange") or ""),
                "scan_frequency": str(source_coverage.get("frequency") or ""),
                "scan_as_of": str(data.get("asOf") or data.get("as_of") or ""),
                "price": _scan_number(raw.get("price")),
                "change_pct": _scan_number(raw.get("changePct", raw.get("change_pct"))),
                "amount": _scan_number(raw.get("amount")),
                "turnover_pct": _scan_number(raw.get("turnoverPct", raw.get("turnover_pct"))),
                "volume_ratio": _scan_number(raw.get("volumeRatio", raw.get("volume_ratio"))),
                "market_cap": _scan_number(raw.get("marketCap", raw.get("market_cap"))),
                "float_market_cap": _scan_number(raw.get("floatMarketCap", raw.get("float_market_cap"))),
                "pe": _scan_number(raw.get("pe")),
                "pb": _scan_number(raw.get("pb")),
                "industry": str(raw.get("industry") or ""),
                "industry_classification": dict(raw["industryClassification"])
                    if isinstance(raw.get("industryClassification"), dict) else {},
                "industry_l1": str(
                    raw.get("industryL1") or raw.get("industry_l1")
                    or raw.get("l1Industry") or raw.get("l1_industry")
                    or raw.get("l1Name") or raw.get("l1_name") or ""
                ),
                "industry_l2": str(
                    raw.get("industryL2") or raw.get("industry_l2")
                    or raw.get("l2Industry") or raw.get("l2_industry")
                    or raw.get("l2Name") or raw.get("l2_name") or ""
                ),
            })
        coverage = data.get("coverage") if isinstance(data.get("coverage"), dict) else {}
        source = str(data.get("source") or self.name)
        if quote_source:
            source = f"{source}+{quote_source}"
        observations = []
        if coverage.get("frequency"):
            observations.append({
                "market": market, "source": source,
                "as_of": str(data.get("asOf") or ""),
                "received_at": str(data.get("receivedAt") or ""),
                "frequency": coverage["frequency"], "realtime": coverage.get("realtime"),
                "listed_count": coverage.get("listedCount"), "quote_count": coverage.get("quoteCount"),
                "missing_quote_count": coverage.get("missingQuoteCount"),
                "basic_count": coverage.get("basicCount"), "note": str(coverage.get("note") or ""),
            })
        return {
            "items": items,
            "market": str(data.get("market") or market).upper(),
            "sort": sort,
            "order": order,
            "source": source,
            "as_of": quote_as_of or str(data.get("asOf") or data.get("as_of") or ""),
            "coverage": {
                **coverage,
                **({"observations": observations} if observations else {}),
                "requested": int(coverage.get("requested") or limit),
                "returned": int(coverage.get("returned") or len(items)),
                "quote_enriched": bool(quote_source),
                "sort_basis": "marketCap_proxy" if amount_proxy else sort,
                "scope": (
                    "market_cap_pool_local_sort"
                    if gateway_market_cap_fallback
                    else str(
                        coverage.get("scope")
                        or (
                            "full_market_ranked_top"
                            if sort in {"changePct", "marketCap"}
                            else "returned_scan_pool"
                        )
                    )
                ),
            },
        }

    def get_market_turnover_top(self, *, limit: int = 20) -> Dict[str, Any]:
        safe_limit = max(1, min(int(limit), 20))
        data = self._invoke_json_capability(
            "market.turnover-top",
            "/market/turnover-top",
            {},
        )
        if not isinstance(data, dict) or not isinstance(data.get("stocks"), list):
            raise MarketDataError("Newma-Desk 全市场成交额榜返回格式无效")
        rows = []
        for raw in data["stocks"][:safe_limit]:
            if not isinstance(raw, dict):
                continue
            symbol = str(raw.get("code") or raw.get("symbol") or "").strip()
            name = str(raw.get("name") or "").strip()
            if not symbol or not name or _number(raw.get("amount")) <= 0:
                continue
            rows.append({
                "symbol": symbol,
                "name": name,
                "market": "CN",
                "exchange": "",
                "price": _scan_number(raw.get("price")),
                "change_pct": _scan_number(raw.get("pct", raw.get("changePct"))),
                "amount": _number(raw.get("amount")),
                "turnover_pct": _scan_number(raw.get("turnoverPct")),
                "volume_ratio": _scan_number(raw.get("volumeRatio")),
                "market_cap": _scan_number(raw.get("mcap", raw.get("marketCap"))),
                "float_market_cap": _scan_number(
                    raw.get("float_cap", raw.get("floatMarketCap"))
                ),
                "pe": _scan_number(raw.get("pe")),
                "pb": _scan_number(raw.get("pb")),
                "industry": str(raw.get("industry") or ""),
                "industry_l1": str(raw.get("industryL1") or raw.get("industry_l1") or ""),
                "industry_l2": str(raw.get("industryL2") or raw.get("industry_l2") or ""),
            })
        if not rows:
            raise MarketDataError("Newma-Desk 全市场成交额榜暂时为空")
        return {
            "items": rows,
            "market": "CN",
            "sort": "amount",
            "order": "desc",
            "source": "newma-desk-market.turnover-top",
            "as_of": str(data.get("updated") or ""),
            "coverage": {
                "requested": safe_limit,
                "returned": len(rows),
                "quote_enriched": False,
                "sort_basis": "amount",
                "scope": "full_market_top20",
            },
        }

    def get_security_master_status(self) -> Dict[str, Any]:
        """Read Desk's security-master summary; rows are not currently exposed."""

        try:
            data = self._invoke_json_capability(
                "market.security-master",
                "/api/market-terminal/security-master",
                {},
            )
        except MarketDataError as exc:
            return {
                "state": "unavailable",
                "enumerable": False,
                "count": 0,
                "exchanges": {},
                "source": "capability:market.security-master",
                "error": str(exc),
            }
        if not isinstance(data, dict):
            return {
                "state": "partial",
                "enumerable": False,
                "count": 0,
                "exchanges": {},
                "source": "capability:market.security-master",
                "error": "证券主表返回格式无效",
            }
        items = data.get("items")
        count = int(_number(data.get("count")))
        exchanges = data.get("exchanges")
        return {
            "state": "available" if count or isinstance(items, list) else "partial",
            "enumerable": isinstance(items, list),
            "count": count if count else len(items or []),
            "exchanges": exchanges if isinstance(exchanges, dict) else {},
            "source": str(data.get("source") or "capability:market.security-master"),
            "updated_at": str(data.get("updatedAt") or data.get("updated_at") or ""),
        }

    def get_liquidity_scan(self, *, limit: int = 50) -> Dict[str, Any]:
        safe_limit = max(20, min(int(limit), 200))
        try:
            turnover = self.get_market_turnover_top(limit=min(safe_limit, 20))
        except MarketDataError:
            fallback = self.get_stock_scan(sort="marketCap", order="desc", limit=200)
            items = [
                dict(item)
                for item in (fallback.get("items") or [])[:safe_limit]
                if isinstance(item, dict)
            ]
            return {
                **fallback,
                "items": items,
                "sort": "marketCap",
                "order": "desc",
                "coverage": {
                    **(fallback.get("coverage") or {}),
                    "requested": safe_limit,
                    "returned": len(items),
                    "quote_enriched": bool(
                        (fallback.get("coverage") or {}).get("quote_enriched")
                    ),
                    "sort_basis": "marketCap",
                    "scope": "market_cap_pool_only",
                    "full_market_turnover_count": 0,
                },
            }
        if safe_limit <= len(turnover["items"]):
            turnover["items"] = turnover["items"][:safe_limit]
            turnover["coverage"]["requested"] = safe_limit
            turnover["coverage"]["returned"] = len(turnover["items"])
            return turnover

        fallback = self.get_stock_scan(sort="marketCap", order="desc", limit=200)
        combined = []
        seen = set()
        for item in [*turnover["items"], *(fallback.get("items") or [])]:
            symbol = str(item.get("symbol") or "")
            if not symbol or symbol in seen:
                continue
            seen.add(symbol)
            combined.append(dict(item))
            if len(combined) >= safe_limit:
                break
        return {
            **fallback,
            "items": combined,
            "sort": "amount",
            "order": "desc",
            "source": f"{turnover['source']}+{fallback.get('source') or self.name}",
            "as_of": turnover.get("as_of") or fallback.get("as_of") or "",
            "coverage": {
                **(fallback.get("coverage") or {}),
                "requested": safe_limit,
                "returned": len(combined),
                "quote_enriched": bool((fallback.get("coverage") or {}).get("quote_enriched")),
                "sort_basis": "amount_top20_then_marketCap",
                "scope": "full_market_top20_plus_market_cap_pool",
                "full_market_turnover_count": len(turnover["items"]),
            },
        }

    def get_candidate_universe(
        self,
        *,
        markets: tuple[str, ...] = ("CN",),
        per_scan_limit: int = 200,
    ) -> Dict[str, Any]:
        """Build a broad CN/HK pool from every Desk scan axis.

        Desk currently exposes ranked cross-sections rather than a paginated
        security master.  Taking both tails where the hard filters need them
        gives the candidate engine materially broader coverage while keeping
        all data access behind Desk.  Coverage metadata stays explicit: this
        is a multi-scan union, not a claim that every listed security was returned.
        """

        normalized_markets = tuple(dict.fromkeys(
            str(market or "").strip().upper() for market in markets
        ))
        if not normalized_markets or any(
            market not in {"CN", "HK"} for market in normalized_markets
        ):
            raise MarketDataError("候选市场仅支持 CN、HK")
        scan_axes = (
            ("marketCap", "desc"),
            ("marketCap", "asc"),
            ("amount", "desc"),
            ("changePct", "desc"),
            ("changePct", "asc"),
            ("turnoverPct", "desc"),
            ("turnoverPct", "asc"),
            ("volumeRatio", "desc"),
            ("volumeRatio", "asc"),
            ("pe", "asc"),
            ("pb", "asc"),
        )
        items_by_key: OrderedDict[tuple[str, str], Dict[str, Any]] = OrderedDict()
        sources = []
        as_of_values = []
        scans = []
        failures = []
        observations = []
        for market in normalized_markets:
            for axis_index, (sort, order) in enumerate(scan_axes):
                try:
                    scan = self.get_stock_scan(
                        market=market,
                        sort=sort,
                        order=order,
                        limit=per_scan_limit,
                    )
                except MarketDataError as exc:
                    failures.append({
                        "market": market,
                        "sort": sort,
                        "order": order,
                        "error": str(exc),
                    })
                    if isinstance(exc, MarketScanUnavailable):
                        failures[-1]["skipped_axes"] = len(scan_axes) - axis_index - 1
                        break
                    continue
                source = str(scan.get("source") or "")
                if source and source not in sources:
                    sources.append(source)
                as_of = str(scan.get("as_of") or "")
                if as_of:
                    as_of_values.append(as_of)
                rows = scan.get("items") or []
                for observation in (scan.get("coverage") or {}).get("observations") or []:
                    if observation not in observations:
                        observations.append(dict(observation))
                scans.append({
                    "market": market,
                    "sort": sort,
                    "order": order,
                    "returned": len(rows),
                    "coverage": scan.get("coverage") or {},
                })
                row_count = max(len(rows), 1)
                for rank, raw in enumerate(rows, 1):
                    if not isinstance(raw, dict):
                        continue
                    symbol = str(raw.get("symbol") or "").split(".")[0]
                    key = (market, symbol)
                    if not symbol:
                        continue
                    membership = f"{sort}:{order}"
                    rank_score = (row_count - rank + 1) / row_count
                    if key not in items_by_key:
                        items_by_key[key] = {
                            **dict(raw),
                            "market": market,
                            "scan_memberships": [membership],
                            "scan_membership_scores": {
                                membership: round(rank_score, 6),
                            },
                            "scan_rank_score": round(rank_score, 6),
                        }
                    else:
                        item = items_by_key[key]
                        if membership not in item["scan_memberships"]:
                            item["scan_memberships"].append(membership)
                        item.setdefault("scan_membership_scores", {})[membership] = round(
                            rank_score, 6
                        )
                        item["scan_rank_score"] = round(
                            float(item.get("scan_rank_score") or 0) + rank_score,
                            6,
                        )
        if not items_by_key:
            if failures:
                skipped = sum(failure.get("skipped_axes", 0) for failure in failures)
                raise MarketDataError(
                    f"宽覆盖行情扫描未完成（{len(failures)} 项查询失败、{skipped} 项未执行），未取得可分析候选。"
                    "请检查数据服务或稍后重试，不能据此判断没有符合条件的股票。"
                )
            raise MarketDataError("Newma-Desk CN/HK 宽覆盖扫描没有返回候选")
        items = list(items_by_key.values())
        security_master = self.get_security_master_status()
        return {
            "items": items,
            "market": "+".join(normalized_markets),
            "sort": "multi_axis_union",
            "order": "mixed",
            "source": "+".join(sources) or self.name,
            "as_of": max(as_of_values) if as_of_values else "",
            "coverage": {
                "requested": len(normalized_markets) * len(scan_axes) * per_scan_limit,
                "returned": len(items),
                "scope": "desk_multi_scan_union",
                "sort_basis": "eleven_scan_axes",
                "markets": list(normalized_markets),
                "scan_count": len(scans),
                "scan_failures": failures,
                "observations": observations,
                "scans": scans,
                "full_security_master": False,
                "security_master": security_master,
            },
        }

    def _enrich_scan_quotes(
        self, raw_items: list[Dict[str, Any]], *, market: str = "CN"
    ):
        """Fill a scan whose delayed source only returned identities.

        Desk already exposes ``market.quotes`` backed by Tencent.  Combining
        the broad scan identities with that batch quote capability keeps the
        candidate pool usable before the delayed Eastmoney feed publishes
        price and amount fields, without adding a Desk endpoint or direct
        market-data dependency here.
        """

        symbols = [
            str(raw.get("symbol") or raw.get("code") or "").split(".")[0]
            for raw in raw_items
        ]
        symbols = [symbol for symbol in symbols if symbol]
        if not symbols or any(
            _number(raw.get("price")) > 0 and _number(raw.get("amount")) > 0
            for raw in raw_items
        ):
            return raw_items, "", ""

        quote_items = []
        quote_as_of = ""
        for start in range(0, len(symbols), 50):
            data = self._invoke_json_capability(
                "market.quotes",
                "/api/market-terminal/quotes",
                {"symbols": ",".join(
                    f"{market}:{symbol}" for symbol in symbols[start:start + 50]
                )},
            )
            if not isinstance(data, dict) or not isinstance(data.get("items"), list):
                raise MarketDataError(f"Newma-Desk {market} 批量行情返回格式无效")
            quote_items.extend(data["items"])
            quote_as_of = str(data.get("asOf") or data.get("as_of") or quote_as_of)

        quotes = {
            str(item.get("symbol") or "").split(".")[0]: item
            for item in quote_items
            if isinstance(item, dict)
        }
        merged = []
        quote_sources = []
        for raw in raw_items:
            symbol = str(raw.get("symbol") or raw.get("code") or "").split(".")[0]
            quote = quotes.get(symbol)
            if quote:
                item = {
                    **raw,
                    **quote,
                    "industry": raw.get("industry") or quote.get("industry") or "",
                }
                # Desk 的延迟扫描提供正确的总市值/流通市值，腾讯批量行情
                # 当前会把这两个字段对调。价格与成交字段仍取实时行情，市值
                # 则保留扫描口径，避免筛选和前端展示使用错误规模数据。
                for field in ("marketCap", "floatMarketCap"):
                    if _number(raw.get(field)) > 0:
                        item[field] = raw[field]
                merged.append(item)
                source = str(quote.get("source") or "").strip()
                if source and source not in quote_sources:
                    quote_sources.append(source)
            else:
                merged.append(raw)
        return merged, quote_as_of, "+".join(quote_sources)

    def get_equity_snapshot(
        self,
        symbol: str,
        *,
        refresh: bool = False,
    ) -> Dict[str, Any]:
        code = str(symbol or "").split(".")[0]
        now = time.monotonic()
        if not refresh:
            with self._equity_snapshot_cache_lock:
                cached = self._equity_snapshot_cache.pop(code, None)
                if cached and now - cached[0] < self._equity_snapshot_cache_ttl:
                    self._equity_snapshot_cache[code] = cached
                    return deepcopy(cached[1])
        data = self._invoke_json_capability(
            "research.equity-snapshot",
            "/equity-research/snapshot",
            {"symbol": code},
            timeout=max(self.timeout, 50.0),
        )
        if not isinstance(data, dict) or not isinstance(data.get("identity"), dict):
            raise MarketDataError("Newma-Desk 股票研究快照返回格式无效")
        with self._equity_snapshot_cache_lock:
            self._equity_snapshot_cache.pop(code, None)
            self._equity_snapshot_cache[code] = (time.monotonic(), deepcopy(data))
            while len(self._equity_snapshot_cache) > self._equity_snapshot_cache_max_entries:
                self._equity_snapshot_cache.popitem(last=False)
        return deepcopy(data)

    def get_statement_evidence(self, symbol: str, announcement_id: str, source: str = "eastmoney") -> Dict[str, Any]:
        code = str(symbol or "").split(".")[0]
        parameters = {"code": code, "announcementId": announcement_id}
        if source != "eastmoney":
            parameters["source"] = source
        try:
            data = self._invoke_json_capability("research.statement-evidence", "/equity-research/statement-evidence",
                                                parameters)
        except MarketDataError as error:
            logging.warning("财报原件能力调用失败：%s / %s", code, announcement_id)
            response = getattr(error.__cause__, "response", None)
            if getattr(response, "status_code", None) == 422:
                raise MarketDataError(
                    "所选公告未通过证券身份或财报格式校验，未用于核对。"
                    "请查找本公司财报，重新选择年度/半年度全文；不要直接重复核对同一编号。"
                ) from error
            raise MarketDataError("未能读取财报原件，尚未完成核对。请打开原公告确认附件可读，或稍后重试；无需重新生成公司档案。") from error
        if not isinstance(data, dict) or data.get("symbol") != code or data.get("announcementId") != announcement_id or data.get("announcementSource", "eastmoney") != source or data.get("contentOrigin") != "pdf-text":
            raise MarketDataError("财报原件身份或内容类型不匹配，未用于核对")
        return data

    def get_statement_announcements(self, symbol: str) -> Dict[str, Any]:
        code = str(symbol or "").split(".")[0]
        try:
            data = self._invoke_json_capability("research.statement-announcements", "/equity-research/statement-announcements", {"code": code})
        except MarketDataError as error:
            raise MarketDataError("巨潮财报列表暂不可读，可稍后重试或直接粘贴已知公告链接") from error
        if not isinstance(data, dict) or data.get("symbol") != code or data.get("source") != "cninfo":
            raise MarketDataError("财报列表来源或证券不符，未用于本公司核对")
        return data

    def get_equity_comparison(
        self,
        symbols: list[str],
        *,
        refresh: bool = False,
    ) -> Dict[str, Any]:
        codes = list(dict.fromkeys(
            str(symbol or "").split(".")[0]
            for symbol in symbols
            if str(symbol or "").strip()
        ))
        if not codes:
            return {"rows": [], "errors": [], "generatedAt": ""}
        if len(codes) > 8:
            raise MarketDataError("Newma-Desk 单次股票横向比较最多支持 8 只")
        cache_key = tuple(codes)
        now = time.monotonic()
        if not refresh:
            with self._equity_comparison_cache_lock:
                cached = self._equity_comparison_cache.pop(cache_key, None)
                if cached and now - cached[0] < self._equity_comparison_cache_ttl:
                    self._equity_comparison_cache[cache_key] = cached
                    return deepcopy(cached[1])
        data = self._invoke_json_capability(
            "research.equity-comparison",
            "/equity-research/comparison",
            {"symbols": ",".join(codes)},
            timeout=max(self.timeout, 60.0),
        )
        if not isinstance(data, dict) or not isinstance(data.get("rows"), list):
            raise MarketDataError("Newma-Desk 股票横向比较返回格式无效")
        with self._equity_comparison_cache_lock:
            self._equity_comparison_cache.pop(cache_key, None)
            self._equity_comparison_cache[cache_key] = (
                time.monotonic(),
                deepcopy(data),
            )
            while len(self._equity_comparison_cache) > self._equity_comparison_cache_max_entries:
                self._equity_comparison_cache.popitem(last=False)
        return deepcopy(data)

    def get_security_announcements(self, symbol: str) -> list[Dict[str, Any]]:
        data = self._invoke_json_capability(
            "market.announcements",
            "/announcements",
            {"code": str(symbol or "").split(".")[0]},
        )
        if not isinstance(data, list) or any(not isinstance(item, dict) for item in data):
            raise MarketDataError("Newma-Desk 公告返回格式无效")
        return [dict(item) for item in data]

    def get_security_reports(self, symbol: str, pages: int = 1) -> list[Dict[str, Any]]:
        data = self._invoke_json_capability(
            "market.reports",
            "/reports",
            {
                "code": str(symbol or "").split(".")[0],
                "pages": max(1, min(int(pages), 5)),
            },
        )
        if not isinstance(data, list) or any(not isinstance(item, dict) for item in data):
            raise MarketDataError("Newma-Desk 研报返回格式无效")
        return [dict(item) for item in data]

    def get_security_news(self, symbol: str, limit: int = 10) -> list[Dict[str, Any]]:
        data = self._invoke_json_capability(
            "market.news",
            "/news",
            {
                "code": str(symbol or "").split(".")[0],
                "limit": max(1, min(int(limit), 50)),
            },
        )
        if not isinstance(data, list) or any(not isinstance(item, dict) for item in data):
            raise MarketDataError("Newma-Desk 新闻返回格式无效")
        return [dict(item) for item in data]

    def get_dragon_tiger_evidence(self, symbol: str) -> Dict[str, Any]:
        code = str(symbol or "").strip().upper().split(".")[0]
        if len(code) != 6 or not code.isdigit():
            raise MarketDataError("龙虎榜机构证据仅支持 6 位 A 股代码")
        data = self._invoke_json_capability(
            "capital.dragon-tiger", "/api/dragon-tiger", {"code": code}
        )
        if not isinstance(data, dict):
            raise MarketDataError("Newma-Desk 龙虎榜机构证据返回格式无效")
        institution = data.get("institution")
        return {
            "records": [
                dict(item) for item in (data.get("records") or [])
                if isinstance(item, dict)
            ],
            "institution": (
                dict(institution) if isinstance(institution, dict) else {}
            ),
            "source": "capability:capital.dragon-tiger",
        }

    def get_security_event_flow(self, symbol: str) -> Dict[str, Any]:
        """Read Desk's already-hosted A-share event and capital interfaces.

        These endpoints deliberately remain outside the InStock data-service
        descriptor.  The adapter only consumes the Research runtime mounted by
        Desk and records per-source coverage; it never falls back to the old
        InStock crawler or database.
        """

        code = str(symbol or "").strip().upper().split(".")[0]
        if len(code) != 6 or not code.isdigit():
            raise MarketDataError("事件与资金查询仅支持 6 位 A 股代码")

        def record_count(source_id: str, data: Any) -> int:
            if isinstance(data, list):
                return len(data)
            if not isinstance(data, dict):
                return 0
            if source_id == "dragon_tiger":
                return len(data.get("records") or [])
            if source_id == "lockup":
                return len(data.get("history") or []) + len(data.get("upcoming") or [])
            return len(data)

        sources: Dict[str, Any] = {}
        failures = []
        successful = 0
        for source_id, label, endpoint, units in self._EVENT_FLOW_SOURCES:
            exposed_endpoint = urlsplit(self._research_url(endpoint)).path
            try:
                data = self._invoke_research_http(endpoint, {"code": code})
                if not isinstance(data, (list, dict)):
                    raise MarketDataError(f"Newma-Desk {label}返回格式无效")
                count = record_count(source_id, data)
                sources[source_id] = {
                    "id": source_id,
                    "label": label,
                    "state": "available" if count else "empty",
                    "endpoint": exposed_endpoint,
                    "units": dict(units),
                    "records": count,
                    "data": data,
                }
                successful += 1
            except MarketDataError as exc:
                response = getattr(exc.__cause__, "response", None)
                status = getattr(response, "status_code", None)
                status_text = f"（HTTP {status}）" if status is not None else ""
                failures.append({
                    "source": source_id,
                    "label": label,
                    "endpoint": exposed_endpoint,
                    "message": f"数据源暂不可用{status_text}，请稍后刷新；未取得数据不等于没有相关活动",
                })
                sources[source_id] = {
                    "id": source_id,
                    "label": label,
                    "state": "failed",
                    "endpoint": exposed_endpoint,
                    "units": dict(units),
                    "records": 0,
                    "data": None,
                }
        if not successful:
            raise MarketDataError("Newma-Desk 事件与资金接口全部不可用")
        return {
            "symbol": code,
            "source": "newma-desk-research-http",
            "sources": sources,
            "failures": failures,
        }


# Public compatibility alias for integrations that imported the original name.
VibeDeskMarketDataProvider = NewmaDeskMarketDataProvider


@lru_cache(maxsize=4)
def get_market_data_provider() -> MarketDataProvider:
    """Build the configured adapter without coupling callers to environment details."""

    # Select the adapter here, but never infer another local application's URL.
    # The upstream InStock crawler remains an explicit operator choice.
    provider = os.environ.get("INSTOCK_MARKET_DATA_PROVIDER", "newma-desk").strip().lower()
    if provider == "instock":
        return InStockMarketDataProvider()
    if provider in {"http", "newma-desk", "newma", "vibedesk"}:
        base_url = (
            os.environ.get("INSTOCK_DATA_URL")
            or os.environ.get("NEWMA_DESK_DATA_URL")
            or os.environ.get("NEWMA_DOCK_DATA_URL")
            or os.environ.get("VIBEDESK_DATA_URL")
            or ""
        ).strip()
        if not base_url:
            raise MarketDataError("请配置 INSTOCK_DATA_URL 或兼容的 Desk 数据地址；未自动连接本机 Desk")
        token = (
            os.environ.get("INSTOCK_DATA_TOKEN")
            or os.environ.get("NEWMA_DESK_DATA_TOKEN")
            or os.environ.get("NEWMA_DOCK_DATA_TOKEN")
            or os.environ.get("VIBEDESK_DATA_TOKEN")
            or ""
        )
        timeout = (
            os.environ.get("INSTOCK_DATA_TIMEOUT")
            or os.environ.get("NEWMA_DESK_DATA_TIMEOUT")
            or os.environ.get("NEWMA_DOCK_DATA_TIMEOUT")
            or os.environ.get("VIBEDESK_DATA_TIMEOUT")
            or "20"
        )
        return NewmaDeskMarketDataProvider(
            base_url=base_url,
            token=token,
            timeout=float(timeout),
            market_services_url=os.environ.get("INSTOCK_MARKET_SERVICES_URL", "").strip(),
            market_services_token=os.environ.get("INSTOCK_MARKET_SERVICES_TOKEN", ""),
        )
    logging.error("未知行情适配器: %s", provider)
    raise MarketDataError(f"未知行情适配器: {provider}")
