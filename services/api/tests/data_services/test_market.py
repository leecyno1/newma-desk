import asyncio

import httpx
import pytest
from pydantic import ValidationError

from vibe_visualization_api.config import Settings
from vibe_visualization_api.data_services.market import (
    MarketUpstreamError,
    VibeResearchMarketClient,
)
from vibe_visualization_api.data_services.normalizers import (
    normalize_market_snapshot,
)


def test_market_snapshot_has_stable_shape() -> None:
    snapshot = normalize_market_snapshot(
        overview={"rise": 3120, "fall": 1800, "flat": 120},
        indices=[
            {
                "code": "000001",
                "name": "上证指数",
                "price": 3520.1,
                "pct": 0.8,
                "rawResponse": {"secret": True},
            }
        ],
        global_indices=[],
        leaders=[
            {
                "code": "600519",
                "name": "贵州茅台",
                "price": 1488.0,
                "pct": 3.2,
                "amount": 120_000_000,
                "industry": "白酒",
            }
        ],
        as_of="2026-07-18T15:00:00+08:00",
    )

    assert snapshot["breadth"] == {"up": 3120, "down": 1800, "flat": 120}
    assert snapshot["indices"] == [
        {
            "symbol": "000001",
            "name": "上证指数",
            "price": 3520.1,
            "changePct": 0.8,
        }
    ]
    assert snapshot["leaders"][0]["symbol"] == "600519"
    assert snapshot["leaders"][0]["market"] == "CN"
    assert "rawResponse" not in str(snapshot)
    assert snapshot["charts"]["indexTrend"]["series"][0]["data"] == [0.8]


def test_research_base_url_is_server_configuration_without_credentials() -> None:
    settings = Settings(research_base_url="http://127.0.0.1:8900")

    assert settings.research_base_url == "http://127.0.0.1:8900"
    with pytest.raises(ValidationError):
        Settings(research_base_url="http://user:secret@127.0.0.1:8900")


def test_normalizer_accepts_the_real_vibe_research_response_shape() -> None:
    snapshot = normalize_market_snapshot(
        overview={
            "sentiment": {"up": 3000, "down": 1800, "flat": 100},
            "updated": "2026-07-18 15:00",
        },
        indices=[
            {"name": "上证指数", "price": 3520.1, "change_pct": 0.8},
            {"name": "创业板指", "price": 2300.2, "change_pct": -0.3},
        ],
        global_indices=[
            {
                "key": "spx",
                "name": "标普500",
                "region": "美股",
                "price": 6300.0,
                "change_pct": 0.5,
            }
        ],
        leaders={
            "stocks": [
                {
                    "code": "600519",
                    "name": "贵州茅台",
                    "price": 1488.0,
                    "pct": 3.2,
                    "amount": 120_000_000,
                    "industry": "白酒",
                }
            ],
            "updated": "2026-07-18 15:01",
        },
        as_of=None,
    )

    assert snapshot["asOf"] == "2026-07-18T15:00:00+08:00"
    assert [item["symbol"] for item in snapshot["indices"]] == [
        "000001",
        "399006",
    ]
    assert snapshot["globalIndices"][0] == {
        "symbol": "spx",
        "name": "标普500",
        "region": "美股",
        "price": 6300.0,
        "changePct": 0.5,
    }


@pytest.mark.asyncio
async def test_market_client_fetches_only_the_four_allowlisted_endpoints_concurrently(
) -> None:
    active = 0
    max_active = 0
    all_started = asyncio.Event()
    paths: list[str] = []

    payloads = {
        "/api/market/overview": {
            "data": {
                "sentiment": {"up": 3, "down": 2, "flat": 1},
                "updated": "2026-07-18 15:00",
            }
        },
        "/api/indices": {
            "data": [
                {"name": "上证指数", "price": 3520.1, "change_pct": 0.8}
            ]
        },
        "/api/global/indices": {"data": []},
        "/api/market/turnover-top": {"data": {"stocks": [], "updated": "x"}},
    }

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal active, max_active
        paths.append(request.url.path)
        assert request.headers["authorization"] == "Bearer research-secret"
        active += 1
        max_active = max(max_active, active)
        if active == 4:
            all_started.set()
        await asyncio.wait_for(all_started.wait(), timeout=1)
        active -= 1
        return httpx.Response(200, json=payloads[request.url.path])

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as http_client:
        client = VibeResearchMarketClient(
            "http://127.0.0.1:8900",
            api_key="research-secret",
            client=http_client,
        )
        snapshot = await client.fetch_snapshot()

    assert set(paths) == set(payloads)
    assert max_active == 4
    assert snapshot["breadth"] == {"up": 3, "down": 2, "flat": 1}


@pytest.mark.asyncio
async def test_market_client_raises_a_safe_error_for_upstream_failure() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"detail": "private upstream stack trace"})

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as http_client:
        client = VibeResearchMarketClient(
            "http://127.0.0.1:8900",
            client=http_client,
        )
        with pytest.raises(MarketUpstreamError, match="market data refresh failed") as error:
            await client.fetch_snapshot()

    assert "private upstream stack trace" not in str(error.value)
