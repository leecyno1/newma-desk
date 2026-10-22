"""The installed descriptor must work without Desk's legacy path adapter."""

from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI, Request

from vibe_visualization_api.data_services.client import DataServiceClient
from vibe_visualization_api.data_services.discovery import discover_data_services
from vibe_visualization_api.domain_suites import ResearchApiAdapter


@pytest.mark.asyncio
@pytest.mark.parametrize("prefix", ["/api", "/api/research", "/proxy/research/api"])
@pytest.mark.parametrize("capability, path, inputs", [
    ("market.health", "/health", {}),
    ("market.ohlcv", "/market-terminal/ohlcv", {"symbol": "512800", "market": "CN", "timeframe": "1w", "limit": 156, "adjust": "qfq", "assetType": "etf"}),
    ("market.ohlcv", "/market-terminal/ohlcv", {"symbol": "920096", "market": "CN", "timeframe": "1d", "limit": 800, "asOf": "2026-10-20"}),
    ("market.scan", "/market-terminal/scan", {"market": "CN", "sort": "amount", "order": "desc", "limit": 20}),
    ("market.indices", "/indices", {}),
    ("research.financials", "/financials", {"code": "600519", "basis": "annual"}),
    ("research.equity-snapshot", "/equity-research/snapshot", {"symbol": "600519"}),
    ("research.equity-comparison", "/equity-research/comparison", {"symbols": "600519,300502"}),
])
async def test_research_descriptor_supports_standalone_and_desk(prefix, capability, path, inputs):
    research = FastAPI()
    calls = []

    @research.get(f"/api{path}")
    async def endpoint(request: Request):
        calls.append(dict(request.query_params))
        if capability == "market.health":
            return {"ok": True, "service": "vibe-research-api"}
        data = [] if capability == "market.indices" else {}
        if capability == "research.financials":
            data = {"basis": "annual", "period": "2025-12-31", "revenue": "0亿元", "net_profit": None}
        return {"data": data}

    app = research
    if prefix == "/api/research":
        app = FastAPI()
        app.mount(prefix, ResearchApiAdapter(research))
    elif prefix == "/proxy/research/api":
        app = FastAPI()
        app.mount("/proxy/research", research)

    root = Path(__file__).resolve().parents[4]
    service, = discover_data_services(
        [root / "integrations/vibe-research"],
        base_url_overrides={"market-data": f"http://127.0.0.1:8992{prefix}"},
    )
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app)) as http:
        client = DataServiceClient(public_mode=False, client=http)
        result = await client.invoke(service, capability, inputs)
    if capability == "market.health":
        assert result == {"ok": True, "service": "vibe-research-api"}
    else:
        assert "data" in result
    assert calls == [{key: str(value) for key, value in inputs.items()}]
