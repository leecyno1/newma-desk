from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import httpx


@dataclass(frozen=True)
class SecurityIdentity:
    market: str
    symbol: str


@dataclass(frozen=True)
class PortfolioQuote:
    price: float
    name: str | None = None
    currency: str | None = None
    source: str | None = None
    as_of: str | None = None


class PortfolioQuoteProvider(Protocol):
    async def get_quotes(
        self,
        securities: list[SecurityIdentity],
    ) -> dict[SecurityIdentity, PortfolioQuote]: ...


class NullPortfolioQuoteProvider:
    async def get_quotes(
        self,
        securities: list[SecurityIdentity],
    ) -> dict[SecurityIdentity, PortfolioQuote]:
        return {}


class ResearchPortfolioQuoteProvider:
    def __init__(
        self,
        base_url: str,
        *,
        api_key: str = "",
        timeout_seconds: float = 12,
        client: httpx.AsyncClient | None = None,
    ):
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._timeout_seconds = timeout_seconds
        self._client = client

    async def get_quotes(
        self,
        securities: list[SecurityIdentity],
    ) -> dict[SecurityIdentity, PortfolioQuote]:
        if not securities:
            return {}
        symbols = ",".join(
            f"{security.market}:{security.symbol}" for security in securities
        )
        headers = {"Accept": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        client = self._client or httpx.AsyncClient(
            timeout=self._timeout_seconds,
            follow_redirects=False,
            trust_env=False,
        )
        owns_client = self._client is None
        try:
            response = await client.get(
                f"{self._base_url}/api/market-terminal/quotes",
                params={"symbols": symbols},
                headers=headers,
                timeout=self._timeout_seconds,
                follow_redirects=False,
            )
            response.raise_for_status()
            body = response.json()
        except (httpx.HTTPError, ValueError):
            return {}
        finally:
            if owns_client:
                await client.aclose()
        payload = body.get("data", body) if isinstance(body, dict) else {}
        items = payload.get("items", []) if isinstance(payload, dict) else []
        result: dict[SecurityIdentity, PortfolioQuote] = {}
        for item in items:
            if not isinstance(item, dict):
                continue
            try:
                identity = SecurityIdentity(
                    market=str(item["market"]).upper(),
                    symbol=str(item["symbol"]).upper(),
                )
                price = float(item["price"])
            except (KeyError, TypeError, ValueError):
                continue
            result[identity] = PortfolioQuote(
                price=price,
                name=str(item.get("name") or "") or None,
                currency=str(item.get("currency") or "") or None,
                source=str(item.get("source") or "") or None,
                as_of=str(item.get("asOf") or payload.get("asOf") or "") or None,
            )
        return result
