"""Async HTTP fetcher with timeout, retry, rate limiting, and circuit breaker integration.

All external HTTP calls in world-intel-mcp go through this module.
Stale-data fallback: when an API call fails, the last-known-good cached
response is returned (marked with _stale=True) so dashboards never go blank.
"""

import asyncio
import contextvars
import hashlib
import logging
import time
from typing import Any

import httpx

from .cache import Cache
from .circuit_breaker import CircuitBreaker

logger = logging.getLogger("world-intel-mcp.fetcher")

_suppress_http_logs = contextvars.ContextVar("world_intel_suppress_http_logs", default=False)


class _ScopedHttpLogFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        return not _suppress_http_logs.get()


_http_log_filter = _ScopedHttpLogFilter()
_http_loggers = ("httpx", "httpcore.connection", "httpcore.http11", "httpcore.http2", "httpcore.proxy", "httpcore.socks")


def _automatic_cache_key(source: str, kind: str, url: str, params: dict | None) -> str:
    digest = hashlib.sha256(f"{url}:{params}".encode()).hexdigest()
    return f"{source}:{kind}:sha256:{digest}"


def _error_summary(error: Exception | None) -> str:
    """Report failure type and HTTP status without logging request credentials."""
    if error is None:
        return "unknown error"
    if isinstance(error, httpx.HTTPStatusError):
        return f"{type(error).__name__} (HTTP {error.response.status_code})"
    return type(error).__name__

# Yahoo Finance requires serialized access (600ms gap)
_yahoo_lock = asyncio.Lock()
_yahoo_last_call: float = 0.0
_YAHOO_MIN_INTERVAL = 0.6  # seconds

# Per-source rate limits (min seconds between calls).
# Sources not listed here have no enforced limit.
_SOURCE_RATE_LIMITS: dict[str, float] = {
    "yahoo-finance": 0.6,  # unofficial — ~100 req/min safe
    "opensky": 6.0,  # free tier: 10 req/min
    "coingecko": 2.0,  # free tier: 30 calls/min
    "cloudflare-radar": 3.0,  # 20 req/min
    "reddit": 1.5,  # ~60 req/min (be conservative)
    "nasa-firms": 2.0,  # API key: ~1000 req/day
    "adsblol": 5.0,  # community API — be very polite
    "polymarket": 1.0,  # be polite
    "faa": 1.0,  # govt API
    "usgs": 1.0,  # generous but be polite
    "acled": 2.0,  # API key based
    "nga": 2.0,  # govt API
    "sec-edgar": 1.0,  # SEC EDGAR — be polite
}
_source_locks: dict[str, asyncio.Lock] = {}
_source_last_call: dict[str, float] = {}


class Fetcher:
    """Centralized HTTP fetcher with caching, retries, and circuit breaking."""

    def __init__(
        self,
        cache: Cache,
        breaker: CircuitBreaker,
        default_timeout: float = 15.0,
        max_retries: int = 2,
        client: httpx.AsyncClient | None = None,
        vector_store: Any = None,
    ):
        self.cache = cache
        self.breaker = breaker
        self.default_timeout = default_timeout
        self.max_retries = max_retries
        self._client: httpx.AsyncClient | None = client
        self.vector_store = vector_store  # VectorStore instance (optional)

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(self.default_timeout),
                follow_redirects=True,
                limits=httpx.Limits(max_connections=200, max_keepalive_connections=40),
                headers={"User-Agent": "PhoenixAGI-WorldIntel/0.1"},
                proxy=None,  # never inherit system SOCKS proxy
            )
        return self._client

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    async def _request(self, client: httpx.AsyncClient, url: str, **kwargs: Any) -> httpx.Response:
        # Logger filters are process-wide, but the suppression flag is task-local.
        for name in _http_loggers:
            http_logger = logging.getLogger(name)
            if _http_log_filter not in http_logger.filters:
                http_logger.addFilter(_http_log_filter)
        token = _suppress_http_logs.set(True)
        try:
            return await client.get(url, **kwargs)
        finally:
            _suppress_http_logs.reset(token)

    async def get_json(
        self,
        url: str,
        source: str,
        cache_key: str | None = None,
        cache_ttl: int = 300,
        headers: dict[str, str] | None = None,
        params: dict[str, Any] | None = None,
        timeout: float | None = None,
        yahoo_rate_limit: bool = False,
    ) -> dict | list | None:
        """Fetch JSON with caching, circuit breaking, and retries.

        Args:
            url: Target URL.
            source: Source name for circuit breaker tracking.
            cache_key: Cache key. If None, uses url+params hash.
            cache_ttl: Cache TTL in seconds.
            headers: Extra HTTP headers.
            params: Query parameters.
            timeout: Per-request timeout override.
            yahoo_rate_limit: If True, enforce Yahoo Finance 600ms serialization.

        Returns:
            Parsed JSON or None on failure.
        """
        # Check cache (live)
        legacy_key = f"{source}:{url}:{params}" if not cache_key else None
        effective_key = cache_key or _automatic_cache_key(source, "json", url, params)
        cached = self.cache.get(effective_key)
        if cached is None and legacy_key is not None:
            cached = self.cache.get(legacy_key)
        if cached is not None:
            return cached

        # Check circuit breaker — fall back to stale data if open
        if not self.breaker.is_available(source):
            logger.debug("Circuit open for %s, trying stale cache", source)
            return self._stale_fallback(effective_key, source, legacy_key)

        # Per-source rate limiting
        if yahoo_rate_limit:
            await self._yahoo_throttle()
        await self._source_throttle(source)

        # Fetch with retries
        client = await self._get_client()
        last_error: Exception | None = None

        for attempt in range(self.max_retries + 1):
            try:
                resp = await self._request(client,
                    url,
                    headers=headers,
                    params=params,
                    timeout=timeout or self.default_timeout,
                )
                resp.raise_for_status()
                content_type = resp.headers.get("content-type", "")
                if "html" in content_type and "json" not in content_type:
                    raise ValueError(
                        f"Expected JSON but got HTML from {source} ({url})"
                    )
                data = resp.json()
                if not isinstance(data, (dict, list)):
                    raise ValueError(
                        f"Expected dict/list from {source}, got {type(data).__name__}"
                    )
                self.breaker.record_success(source)
                self.cache.set(effective_key, data, cache_ttl)
                if self.vector_store:
                    await self.vector_store.store(source, data)
                return data
            except (httpx.HTTPStatusError, httpx.RequestError, Exception) as exc:
                last_error = exc
                if attempt < self.max_retries:
                    wait = min(2 ** attempt, 30)
                    logger.debug(
                        "Retry %d/%d for %s (%s), waiting %.1fs",
                        attempt + 1,
                        self.max_retries,
                        source,
                        _error_summary(exc),
                        wait,
                    )
                    await asyncio.sleep(wait)

        # All retries failed — try stale cache before giving up
        self.breaker.record_failure(source)
        logger.warning("Fetch failed for %s: %s", source, _error_summary(last_error))
        return self._stale_fallback(effective_key, source, legacy_key)

    async def get_text(
        self,
        url: str,
        source: str,
        cache_key: str | None = None,
        cache_ttl: int = 300,
        headers: dict[str, str] | None = None,
        params: dict[str, Any] | None = None,
        timeout: float | None = None,
    ) -> str | None:
        """Fetch raw text with caching and circuit breaking."""
        legacy_key = f"{source}:text:{url}:{params}" if not cache_key else None
        effective_key = cache_key or _automatic_cache_key(source, "text", url, params)
        cached = self.cache.get(effective_key)
        if cached is None and legacy_key is not None:
            cached = self.cache.get(legacy_key)
        if cached is not None:
            return cached

        if not self.breaker.is_available(source):
            return self._stale_fallback(effective_key, source, legacy_key)

        await self._source_throttle(source)

        client = await self._get_client()
        last_error: Exception | None = None

        for attempt in range(self.max_retries + 1):
            try:
                resp = await self._request(client,
                    url,
                    headers=headers,
                    params=params,
                    timeout=timeout or self.default_timeout,
                )
                resp.raise_for_status()
                text = resp.text
                self.breaker.record_success(source)
                self.cache.set(effective_key, text, cache_ttl)
                return text
            except (httpx.HTTPStatusError, httpx.RequestError, Exception) as exc:
                last_error = exc
                if attempt < self.max_retries:
                    await asyncio.sleep(min(2 ** attempt, 30))

        self.breaker.record_failure(source)
        logger.warning("Text fetch failed for %s: %s", source, _error_summary(last_error))
        return self._stale_fallback(effective_key, source, legacy_key)

    async def get_xml(
        self,
        url: str,
        source: str,
        cache_key: str | None = None,
        cache_ttl: int = 300,
        timeout: float | None = None,
    ) -> str | None:
        """Fetch XML content (returns raw text for feedparser/ET parsing)."""
        return await self.get_text(url, source, cache_key, cache_ttl, timeout=timeout)

    def _stale_fallback(self, cache_key: str, source: str, legacy_key: str | None = None) -> Any | None:
        """Return stale (expired) cached data as last-known-good fallback."""
        stale = self.cache.get_stale(cache_key)
        if stale is None and legacy_key is not None:
            stale = self.cache.get_stale(legacy_key)
        if stale is not None:
            logger.info("Serving stale cache for %s", source)
        return stale

    async def _source_throttle(self, source: str) -> None:
        """Enforce per-source rate limit from _SOURCE_RATE_LIMITS."""
        min_interval = _SOURCE_RATE_LIMITS.get(source)
        if min_interval is None:
            return
        if source not in _source_locks:
            _source_locks[source] = asyncio.Lock()
        async with _source_locks[source]:
            now = time.time()
            last = _source_last_call.get(source, 0.0)
            elapsed = now - last
            if elapsed < min_interval:
                await asyncio.sleep(min_interval - elapsed)
            _source_last_call[source] = time.time()

    async def _yahoo_throttle(self) -> None:
        """Enforce Yahoo Finance rate limit (600ms between calls)."""
        global _yahoo_last_call
        async with _yahoo_lock:
            now = time.time()
            elapsed = now - _yahoo_last_call
            if elapsed < _YAHOO_MIN_INTERVAL:
                await asyncio.sleep(_YAHOO_MIN_INTERVAL - elapsed)
            _yahoo_last_call = time.time()
