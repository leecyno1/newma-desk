from collections.abc import AsyncIterator
import logging
from time import monotonic

import httpx

logger = logging.getLogger(__name__)


class GlobalIntelUnavailable(RuntimeError):
    """Raised when the managed World Intelligence service is unavailable."""

    def __init__(self, message: str, *, code: str = "world_unavailable"):
        super().__init__(message)
        self.code = code


class GlobalIntelClient:
    def __init__(
        self,
        base_url: str,
        *,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._client = client

    async def get_json(self, path: str, *, timeout_seconds: float = 120.0) -> dict:
        client = self._client or httpx.AsyncClient(
            timeout=httpx.Timeout(timeout_seconds),
            follow_redirects=False,
            trust_env=False,
        )
        owns_client = self._client is None
        try:
            response = await client.get(
                f"{self._base_url}{path}",
                timeout=httpx.Timeout(timeout_seconds),
                follow_redirects=False,
            )
            response.raise_for_status()
            payload = response.json()
            if not isinstance(payload, dict):
                raise GlobalIntelUnavailable(
                    "World Intelligence returned an invalid JSON payload"
                )
            return payload
        except (httpx.HTTPError, ValueError) as error:
            raise GlobalIntelUnavailable(
                "World Intelligence service is unavailable"
            ) from error
        finally:
            if owns_client:
                await client.aclose()

    async def stream(self, path: str) -> AsyncIterator[bytes]:
        # Sources may take 90s for the first event; subsequent heartbeats arrive
        # every 15s. Bound inactivity, not the lifetime of a healthy live feed.
        timeout = httpx.Timeout(120.0, connect=5.0, write=5.0, pool=5.0)
        client = self._client or httpx.AsyncClient(
            timeout=timeout,
            follow_redirects=False,
            trust_env=False,
        )
        owns_client = self._client is None
        started, received = monotonic(), 0
        try:
            async with client.stream(
                "GET",
                f"{self._base_url}{path}",
                headers={"Accept": "text/event-stream"},
                follow_redirects=False,
                timeout=timeout,
            ) as response:
                response.raise_for_status()
                content_type = response.headers.get("content-type", "").split(";", 1)[0].strip().lower()
                if content_type != "text/event-stream":
                    logger.warning("World stream stopped: code=world_invalid_stream")
                    raise GlobalIntelUnavailable("World Intelligence returned an invalid event stream", code="world_invalid_stream")
                # Our route does not forward upstream Content-Encoding headers.
                # Decode compression before forwarding the SSE bytes.
                async for chunk in response.aiter_bytes():
                    if chunk:
                        received += 1
                        yield chunk
        except httpx.HTTPError as error:
            code = (
                "world_stream_idle_timeout" if isinstance(error, httpx.ReadTimeout) else
                "world_connection_failed" if isinstance(error, (httpx.ConnectError, httpx.ConnectTimeout)) else
                "world_http_rejected" if isinstance(error, httpx.HTTPStatusError) else
                "world_stream_disconnected"
            )
            # Exception messages/URLs/headers can contain private data. Record
            # only the classification and transport progress, not their text.
            logger.warning("World stream stopped: code=%s cause=%s chunks=%d elapsed=%.2fs",
                           code, type(error).__name__, received, monotonic() - started)
            raise GlobalIntelUnavailable(
                "World Intelligence event stream is unavailable", code=code,
            ) from error
        finally:
            if owns_client:
                await client.aclose()
