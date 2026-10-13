import asyncio
import sys
import threading
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import Mock, patch

import httpx
from fastapi import FastAPI

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import repositories
import service_registry
from routes.funds import router
from services import cache_service


class FundListConcurrencyTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.app = FastAPI()
        self.app.include_router(router)

        @self.app.get("/ping")
        async def ping():
            return {"status": "ok"}

        stack = ExitStack()
        self.addCleanup(stack.close)
        self.cache = Mock()
        self.cache.get.return_value = None
        stack.enter_context(patch.object(cache_service, "get_cache", return_value=self.cache))
        self.data_service = stack.enter_context(patch.object(service_registry, "get_data_service")).return_value
        stack.enter_context(patch.object(service_registry, "get_scoring_engine"))
        self.fund_repo = Mock()
        stack.enter_context(patch.object(repositories, "get_fund_repo", return_value=self.fund_repo))
        for getter in ("get_manager_repo", "get_research_profile_repo", "get_metric_snapshot_repo", "get_fund_classification_repo"):
            stack.enter_context(patch.object(repositories, getter))
        self.client = httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app), base_url="http://test")
        self.addAsyncCleanup(self.client.aclose)

    async def test_slow_database_does_not_block_other_requests(self):
        started = threading.Event()
        release = threading.Event()
        released_by_ping = []

        def list_funds(**kwargs):
            started.set()
            released_by_ping.append(release.wait(timeout=1))
            return {"total": 0, "funds": [], "summary": {}}

        self.fund_repo.list_funds.side_effect = list_funds
        request = asyncio.create_task(self.client.get("/api/funds/?keyword=NO_MATCH"))
        try:
            async with asyncio.timeout(3):
                while not started.is_set():
                    await asyncio.sleep(0)
                ping = await self.client.get("/ping")
                self.assertEqual(ping.status_code, 200)
                release.set()
                response = await request
        finally:
            release.set()
            await request
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["source"], "database")
        self.assertEqual(released_by_ping, [True], "Slow fund-list SQL blocked the event loop")
        self.data_service.get_fund_list.assert_not_called()

    async def test_database_error_still_returns_503(self):
        self.fund_repo.list_funds.side_effect = RuntimeError("unavailable")
        with self.assertLogs("routes.funds", level="ERROR"):
            response = await self.client.get("/api/funds/?keyword=NO_MATCH")
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["detail"]["code"], "database_unavailable")
        self.data_service.get_fund_list.assert_not_called()

    async def test_cache_hit_does_not_query_database(self):
        payload = {"total": 0, "funds": [], "source": "database"}
        self.cache.get.return_value = payload
        response = await self.client.get("/api/funds/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), payload)
        self.fund_repo.list_funds.assert_not_called()


if __name__ == "__main__":
    unittest.main()
