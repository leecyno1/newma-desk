import asyncio
import json
import time
from types import SimpleNamespace
from unittest.mock import patch

import tornado.web
from tornado.testing import AsyncHTTPTestCase, gen_test

import instock.web.market_map_handler as market_map_handler
from instock.core.analysis_history import get_analysis_history_registry
from instock.core.analysis_snapshot import get_analysis_snapshot_registry
from instock.web.market_map_handler import MarketMapSnapshotHandler


class CountingMarketMapEngine:
    calls = 0

    def __init__(self, provider):
        self.provider = provider

    def analyze(self, *, capacity):
        type(self).calls += 1
        time.sleep(0.06)
        return {
            "engine": {"name": "instock-market-map", "version": "fixture"},
            "as_of": "2026-08-13",
            "data_source": "fixture",
            "data_state": "complete",
            "size_basis": "market_cap",
            "color_basis": "change_pct",
            "groups": [],
            "coverage": {"requested_capacity": capacity, "displayed_securities": 0},
            "summary": {},
            "failures": [],
            "limitations": [],
            "snapshot": {
                "schema_version": "1.0",
                "snapshot_id": f"instock-market-map:fixture-{capacity}",
                "analysis": {"name": "instock-market-map", "version": "fixture"},
            },
        }


class MarketMapHandlerTest(AsyncHTTPTestCase):
    def setUp(self):
        self.provider_patch = patch.object(
            market_map_handler,
            "get_market_data_provider",
            return_value=SimpleNamespace(name="fixture"),
        )
        self.engine_patch = patch.object(
            market_map_handler,
            "MarketMapEngine",
            CountingMarketMapEngine,
        )
        self.provider_patch.start()
        self.engine_patch.start()
        CountingMarketMapEngine.calls = 0
        market_map_handler._RESULT_CACHE.clear()
        market_map_handler._INFLIGHT.clear()
        get_analysis_snapshot_registry().clear()
        get_analysis_history_registry().clear()
        super().setUp()

    def tearDown(self):
        super().tearDown()
        market_map_handler._RESULT_CACHE.clear()
        market_map_handler._INFLIGHT.clear()
        get_analysis_snapshot_registry().clear()
        get_analysis_history_registry().clear()
        self.engine_patch.stop()
        self.provider_patch.stop()

    def get_app(self):
        return tornado.web.Application([
            (r"/api/v1/market-maps/snapshots", MarketMapSnapshotHandler),
        ])

    @gen_test
    async def test_concurrent_requests_share_analysis_and_keep_history(self):
        url = self.get_url("/api/v1/market-maps/snapshots?capacity=500&refresh=1")
        responses = await asyncio.gather(
            self.http_client.fetch(url),
            self.http_client.fetch(url),
        )

        assert all(response.code == 200 for response in responses)
        assert CountingMarketMapEngine.calls == 1
        cached = await self.http_client.fetch(
            self.get_url("/api/v1/market-maps/snapshots?capacity=500")
        )
        payload = json.loads(cached.body)
        assert payload["data"]["cache_hit"] is True
        assert payload["data"]["coverage"]["requested_capacity"] == 500
        history = get_analysis_history_registry().list("market-map")
        assert len(history) == 1
        assert history[0]["parameters"] == {"capacity": 500}
