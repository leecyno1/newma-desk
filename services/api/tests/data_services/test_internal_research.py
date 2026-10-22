import asyncio
import json
from pathlib import Path

from fastapi import FastAPI, Request
import httpx
import pytest

from vibe_visualization_api.data_services.internal_research import InternalResearch
from vibe_visualization_api.data_services.models import DataServiceDescriptor
from vibe_visualization_api.data_services.client import DataServiceClient, UpstreamServiceError
from vibe_visualization_api.data_services.market import VibeResearchMarketClient
from vibe_visualization_api.portfolio_center.quotes import ResearchPortfolioQuoteProvider, SecurityIdentity
from vibe_visualization_api.capital_flow.service import CapitalFlowService

BASE = "http://127.0.0.1:8911/api/research"


def descriptor():
    path = Path(__file__).resolve().parents[4] / "integrations/vibe-research/data-service.json"
    return DataServiceDescriptor.model_validate(json.loads(path.read_text()))


def upstream():
    app = FastAPI()
    app.state.calls = []

    @app.api_route("/api/{path:path}", methods=["GET", "POST"])
    async def handle(path: str, request: Request):
        assert request.headers.get("authorization") == "Bearer synthetic-internal-key"
        assert not any(name in request.headers for name in ("cookie", "x-user-id", "x-workspace-id", "x-newma-desk-instance-id"))
        app.state.calls.append((request.method, path, dict(request.query_params)))
        data = {
            "market/overview": {"sentiment": {"up": 3, "down": 2, "flat": 1}},
            "indices": [], "global/indices": [], "market/turnover-top": {"stocks": []},
            "macro-monitor": {"synthetic": True},
            "market-terminal/quotes": {"items": [{"market": "CN", "symbol": "600519", "price": 100}]},
            "market-terminal/search": {"items": [{"market": "CN", "symbol": "600519", "assetType": "stock", "exchange": "SH"}]},
        }.get(path, {})
        return {"data": data}

    return app


@pytest.mark.asyncio
async def test_gateway_scheduler_quotes_and_capital_use_internal_dispatch():
    service = descriptor()
    bridge = InternalResearch(BASE, service.capabilities.values())
    app = upstream()
    bridge.bind(app, "synthetic-internal-key")
    data = DataServiceClient(public_mode=False, transport_factory=bridge.transport)
    assert await data.invoke(service, "research.macro-monitor", {"days": 7}) == {"data": {"synthetic": True}}
    snapshot = await VibeResearchMarketClient(BASE, transport_factory=bridge.transport).fetch_snapshot()
    assert snapshot["breadth"] == {"up": 3, "down": 2, "flat": 1}
    security = SecurityIdentity("CN", "600519")
    quotes = await ResearchPortfolioQuoteProvider(BASE, transport_factory=bridge.transport).get_quotes([security])
    assert quotes[security].price == 100
    search = await CapitalFlowService(BASE, transport_factory=bridge.transport).search_securities("茅台")
    assert search["items"][0]["symbol"] == "600519"
    assert ("GET", "macro-monitor", {"days": "7"}) in app.state.calls
    assert ("GET", "market-terminal/quotes", {"symbols": "CN:600519"}) in app.state.calls


@pytest.mark.asyncio
async def test_internal_dispatch_does_not_grant_private_or_undeclared_writes():
    bridge = InternalResearch(BASE, descriptor().capabilities.values())
    app = upstream()
    bridge.bind(app, "synthetic-internal-key")
    async with httpx.AsyncClient(transport=bridge.transport(), follow_redirects=False) as client:
        for path, method in [("/portfolio", "GET"), ("/api/myreports", "GET"), ("/macro-monitor", "POST")]:
            assert (await client.request(method, BASE + path)).status_code == 403
        response = await client.get(BASE + "/api/macro-monitor?days=2", headers={
            "Cookie": "account=private", "Authorization": "Bearer browser-token",
            "X-User-Id": "forged", "X-Workspace-Id": "forged", "X-Newma-Desk-Instance-Id": "forged",
        })
        assert response.status_code == 200
    assert app.state.calls == [("GET", "macro-monitor", {"days": "2"})]


@pytest.mark.asyncio
async def test_missing_mount_and_timeout_are_failures_not_anonymous_network_fallback():
    service = descriptor()
    bridge = InternalResearch(BASE, service.capabilities.values())
    data = DataServiceClient(public_mode=False, transport_factory=bridge.transport)
    with pytest.raises(UpstreamServiceError) as missing:
        await data.invoke(service, "research.macro-monitor", {})
    assert missing.value.code == "UPSTREAM_FAILURE"
    app = FastAPI()

    @app.get("/api/macro-monitor")
    async def slow():
        await asyncio.sleep(0.1)
        return {"data": {}}

    bridge.bind(app, "")
    service.capabilities["research.macro-monitor"].timeout_seconds = 0.01
    with pytest.raises(UpstreamServiceError) as timeout:
        await data.invoke(service, "research.macro-monitor", {})
    assert timeout.value.code == "UPSTREAM_TIMEOUT"


@pytest.mark.asyncio
async def test_other_origins_keep_network_transport_without_internal_key(monkeypatch):
    seen = []

    async def network(request):
        seen.append(str(request.url))
        assert "authorization" not in request.headers
        return httpx.Response(200, json={"external": True})

    monkeypatch.setattr(httpx, "AsyncHTTPTransport", lambda **kwargs: httpx.MockTransport(network))
    bridge = InternalResearch(BASE, descriptor().capabilities.values())
    bridge.bind(upstream(), "synthetic-internal-key")
    async with httpx.AsyncClient(transport=bridge.transport()) as client:
        for target in ["https://research.example/api/research/macro-monitor", "http://127.0.0.1:8912/api/research/macro-monitor", "http://127.0.0.1:8911/api/another"]:
            assert (await client.get(target)).json() == {"external": True}
    assert len(seen) == 3
    assert InternalResearch.supports(BASE)
    assert not InternalResearch.supports("https://research.example/api/research")
