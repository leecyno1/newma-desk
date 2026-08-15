import httpx
import pytest

from vibe_visualization_api.capital_flow.service import CapitalFlowService


@pytest.mark.asyncio
async def test_capital_flow_aggregates_market_and_security_data():
    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/api/market/overview"):
            return httpx.Response(200, json={"data": {"sentiment": {"active": "45%", "date": "2026-08-14"}, "sectors": [{"name": "通信", "net": 10, "inflow": 30, "outflow": 20}, {"name": "医药", "net": -3, "inflow": 7, "outflow": 10}]}})
        if path.endswith("/api/market/turnover-top"):
            return httpx.Response(200, json={"data": {"stocks": [{"code": "300308", "amount": 2_000_000_000}]}})
        if path.endswith("/api/fund-flow"):
            return httpx.Response(200, json={"data": [{"date": "2026-08-14", "main_net": 10}]})
        return httpx.Response(200, json={"data": [{"date": "2026-08-14", "rzye": 20}]})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="http://research") as client:
        payload = await CapitalFlowService("http://research", client=client).dashboard("300308")
    assert payload["summary"]["sectorNetYi"] == 7
    assert payload["summary"]["top20TurnoverYi"] == 20
    assert payload["sectors"][0]["name"] == "通信"
    assert payload["security"]["fundFlow"]
