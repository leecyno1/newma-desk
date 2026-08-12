from collections.abc import AsyncIterator

import httpx


class GlobalIntelUnavailable(RuntimeError):
    """Raised when the managed World Intelligence service is unavailable."""


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
        client = self._client or httpx.AsyncClient(
            timeout=httpx.Timeout(None),
            follow_redirects=False,
            trust_env=False,
        )
        owns_client = self._client is None
        try:
            async with client.stream(
                "GET",
                f"{self._base_url}{path}",
                headers={"Accept": "text/event-stream"},
                follow_redirects=False,
            ) as response:
                response.raise_for_status()
                async for chunk in response.aiter_raw():
                    if chunk:
                        yield chunk
        except httpx.HTTPError as error:
            raise GlobalIntelUnavailable(
                "World Intelligence event stream is unavailable"
            ) from error
        finally:
            if owns_client:
                await client.aclose()
