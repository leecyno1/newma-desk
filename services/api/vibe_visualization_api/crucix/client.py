"""Explicit standalone connection to a Crucix engine, using the same contract."""
import httpx

from .adapter import adapt_crucix_response


class CrucixUnavailable(RuntimeError):
    pass


class CrucixClient:
    def __init__(self, base_url: str, *, client: httpx.AsyncClient | None = None):
        self.base_url = base_url.rstrip("/")
        self.client = client

    async def read(self, capability_id: str) -> dict:
        paths = {"crucix.health": "/api/health", "crucix.snapshot": "/api/data"}
        path = paths[capability_id]
        if not self.base_url:
            raise CrucixUnavailable("Crucix 数据源未配置")
        client = self.client or httpx.AsyncClient(timeout=30, follow_redirects=False, trust_env=False)
        try:
            response = await client.get(f"{self.base_url}{path}")
            response.raise_for_status()
            payload = response.json()
            if not isinstance(payload, dict):
                raise ValueError("invalid Crucix payload")
            return adapt_crucix_response(capability_id, payload)
        except (httpx.HTTPError, ValueError) as error:
            raise CrucixUnavailable("Crucix 数据源暂不可用") from error
        finally:
            if self.client is None:
                await client.aclose()
