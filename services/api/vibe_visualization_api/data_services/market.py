import asyncio
from typing import Any
from urllib.parse import urlsplit

import httpx

from vibe_visualization_api.data_services.normalizers import (
    normalize_market_snapshot,
)


MARKET_ENDPOINTS = (
    "/api/market/overview",
    "/api/indices",
    "/api/global/indices",
    "/api/market/turnover-top",
)


class MarketUpstreamError(Exception):
    """Raised when a market snapshot cannot be refreshed safely."""


def _validated_base_url(value: str) -> str:
    parsed = urlsplit(value)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.netloc
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("research base URL must be an HTTP origin or path")
    return value.rstrip("/")


class VibeResearchMarketClient:
    def __init__(
        self,
        base_url: str,
        *,
        api_key: str = "",
        timeout_seconds: float = 15.0,
        client: httpx.AsyncClient | None = None,
    ):
        self._base_url = _validated_base_url(base_url)
        self._api_key = api_key
        self._timeout_seconds = timeout_seconds
        self._client = client

    async def fetch_snapshot(self) -> dict[str, Any]:
        timeout = httpx.Timeout(self._timeout_seconds)
        client = self._client or httpx.AsyncClient(
            timeout=timeout,
            follow_redirects=False,
            trust_env=False,
        )
        owns_client = self._client is None
        try:
            async with asyncio.timeout(self._timeout_seconds):
                overview, indices, global_indices, leaders = await asyncio.gather(
                    *(self._fetch(client, path, timeout) for path in MARKET_ENDPOINTS)
                )
        except (TimeoutError, httpx.HTTPError, ValueError, TypeError) as error:
            raise MarketUpstreamError("market data refresh failed") from error
        finally:
            if owns_client:
                await client.aclose()

        return normalize_market_snapshot(
            overview=overview,
            indices=indices,
            global_indices=global_indices,
            leaders=leaders,
            as_of=None,
        )

    async def _fetch(
        self,
        client: httpx.AsyncClient,
        path: str,
        timeout: httpx.Timeout,
    ) -> object:
        if path not in MARKET_ENDPOINTS:
            raise ValueError("market endpoint is not allowlisted")
        headers = (
            {"Authorization": f"Bearer {self._api_key}"}
            if self._api_key
            else {}
        )
        response = await client.get(
            f"{self._base_url}{path}",
            headers=headers,
            timeout=timeout,
            follow_redirects=False,
        )
        response.raise_for_status()
        payload = response.json()
        if isinstance(payload, dict) and "data" in payload:
            return payload["data"]
        return payload
