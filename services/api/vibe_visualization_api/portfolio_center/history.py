from __future__ import annotations

import asyncio
import math
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo
from dataclasses import dataclass
from typing import Any, Protocol

from vibe_visualization_api.data_services.client import DataServiceClient
from vibe_visualization_api.data_services.registry import DataServiceRegistry
from vibe_visualization_api.portfolio_center.quotes import SecurityIdentity


@dataclass(frozen=True)
class PortfolioPriceHistory:
    closes: tuple[float, ...]
    timestamps: tuple[float, ...] = ()
    source: str | None = None
    as_of: str | None = None


class PortfolioHistoryProvider(Protocol):
    async def get_histories(
        self,
        securities: list[SecurityIdentity],
        *,
        limit: int,
    ) -> dict[SecurityIdentity, PortfolioPriceHistory]: ...


def align_weekly_histories(histories: list[PortfolioPriceHistory], limit: int, timezones: list[str] | None = None):
    """Use common calendar weeks, retaining the latest contiguous segment only."""
    weekly = []
    for index, history in enumerate(histories):
        zone = ZoneInfo(timezones[index]) if timezones else UTC
        points = {}
        for timestamp, close in sorted(zip(history.timestamps, history.closes)):
            seconds = timestamp / 1000 if timestamp > 1e11 else timestamp
            if not 946684800 <= seconds <= datetime.now(UTC).timestamp() + 86400:
                continue
            if close <= 0 or not math.isfinite(close):
                continue
            day = datetime.fromtimestamp(seconds, zone).date()
            week = day - timedelta(days=day.weekday())
            points[week] = (close, day.isoformat())
        weekly.append(points)
    common = sorted(set.intersection(*(set(points) for points in weekly))) if weekly else []
    start = len(common) - 1
    while start > 0 and (common[start] - common[start - 1]).days == 7:
        start -= 1
    dates = common[max(0, start):][-limit:]
    return (
        [[points[day][0] for day in dates] for points in weekly],
        [day.isoformat() for day in dates],
        min(points[dates[-1]][1] for points in weekly) if dates else None,
    )


class NullPortfolioHistoryProvider:
    async def get_histories(
        self,
        securities: list[SecurityIdentity],
        *,
        limit: int,
    ) -> dict[SecurityIdentity, PortfolioPriceHistory]:
        return {}


class DataServicePortfolioHistoryProvider:
    """Read weekly price history through the Desk data-service contract."""

    def __init__(
        self,
        registry: DataServiceRegistry,
        client: DataServiceClient,
    ):
        self._registry = registry
        self._client = client

    async def get_histories(
        self,
        securities: list[SecurityIdentity],
        *,
        limit: int,
    ) -> dict[SecurityIdentity, PortfolioPriceHistory]:
        try:
            service = self._registry.resolve("market.ohlcv")
        except Exception:
            return {}
        results = await asyncio.gather(
            *(
                self._load_one(service, security, limit=limit)
                for security in securities
            )
        )
        return {
            security: history
            for security, history in results
            if history is not None
        }

    async def _load_one(
        self,
        service,
        security: SecurityIdentity,
        *,
        limit: int,
    ) -> tuple[SecurityIdentity, PortfolioPriceHistory | None]:
        try:
            payload = await self._client.invoke(
                service,
                "market.ohlcv",
                {
                    "symbol": security.symbol,
                    "market": security.market,
                    "timeframe": "1w",
                    "limit": limit,
                    "adjust": "qfq" if security.market == "CN" else "none",
                },
            )
            history = self._parse(payload)
        except Exception:
            history = None
        return security, history

    @staticmethod
    def _parse(payload: object) -> PortfolioPriceHistory | None:
        if not isinstance(payload, dict):
            return None
        raw_data = payload.get("data", payload)
        if not isinstance(raw_data, dict):
            return None
        raw_items = raw_data.get("items")
        if not isinstance(raw_items, list):
            return None
        ordered: list[tuple[float, float]] = []
        for item in raw_items:
            if not isinstance(item, dict):
                continue
            try:
                close = float(item["close"])
                timestamp = float(item["timestamp"])
            except (KeyError, TypeError, ValueError):
                continue
            if close <= 0 or not math.isfinite(close) or not math.isfinite(timestamp):
                continue
            ordered.append((timestamp, close))
        ordered.sort(key=lambda item: item[0])
        closes = tuple(close for _, close in ordered)
        if len(closes) < 2:
            return None
        return PortfolioPriceHistory(
            closes=closes,
            timestamps=tuple(timestamp for timestamp, _ in ordered),
            source=str(raw_data.get("source") or "") or None,
            as_of=str(raw_data.get("asOf") or "") or None,
        )
