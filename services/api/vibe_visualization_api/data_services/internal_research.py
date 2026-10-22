"""Server-only dispatch to the mounted Research app, never a browser auth bypass."""
import asyncio

import httpx


class InternalResearch:
    def __init__(self, base_url, capabilities):
        self.base = httpx.URL(base_url.rstrip("/"))
        self.allowed = {(c.method, "/api" + c.path) for c in capabilities}
        self.application = None
        self.api_key = ""

    @staticmethod
    def supports(base_url):
        url = httpx.URL(base_url)
        return (url.scheme == "http" and url.host in {"127.0.0.1", "::1", "localhost"}
                and url.path.rstrip("/") == "/api/research"
                and not url.userinfo and not url.query and not url.fragment)

    def bind(self, application, api_key):
        self.application, self.api_key = application, api_key

    def transport(self):
        return _ResearchTransport(self)


class _ResearchTransport(httpx.AsyncBaseTransport):
    def __init__(self, research):
        self.research = research
        self.network = None

    async def handle_async_request(self, request):
        target, base = request.url, self.research.base
        if ((target.scheme, target.host, target.port) != (base.scheme, base.host, base.port)
                or not (target.path == base.path or target.path.startswith(base.path + "/"))):
            # Other providers retain their normal network transport. No internal
            # credential or account identity is ever added to these requests.
            if self.network is None:
                self.network = httpx.AsyncHTTPTransport(trust_env=False)
            return await self.network.handle_async_request(request)

        path = target.path[len(base.path):]
        path = path if path.startswith("/api/") else "/api" + path
        if (request.method, path) not in self.research.allowed:
            return httpx.Response(403, json={"detail": "Unregistered internal research capability"})
        if self.research.application is None:
            return httpx.Response(503, json={"detail": "Integrated Research is unavailable"})

        # Construct a fresh request: never forward Website cookies, Mod tokens,
        # user/workspace headers, or browser-controlled ASGI identity metadata.
        headers = {"Accept": "application/json"}
        if self.research.api_key:
            headers["Authorization"] = f"Bearer {self.research.api_key}"
        if request.headers.get("content-type"):
            headers["Content-Type"] = request.headers["content-type"]
        inner = httpx.Request(request.method, target.copy_with(path=path),
                             headers=headers, content=await request.aread())
        transport = httpx.ASGITransport(app=self.research.application, raise_app_exceptions=False)
        # ASGITransport does not enforce HTTPX's network timeout itself.
        budget = request.extensions.get("timeout", {}).get("read", 15)
        try:
            async with asyncio.timeout(budget):
                return await transport.handle_async_request(inner)
        except TimeoutError as error:
            raise httpx.ReadTimeout("Internal Research request timed out", request=request) from error

    async def aclose(self):
        if self.network is not None:
            await self.network.aclose()
