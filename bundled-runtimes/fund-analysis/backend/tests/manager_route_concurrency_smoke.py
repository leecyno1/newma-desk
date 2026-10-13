"""A slow synchronous research query must not freeze health or other requests."""
import asyncio
import os
import sys
import threading
from unittest.mock import patch

import httpx
from fastapi import FastAPI

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from routes.managers import router

app = FastAPI()
app.include_router(router)


@app.get("/probe")
async def probe():
    return {"ready": True}


async def main():
    cases = [
        ("/api/managers/browser", "services.fund_manager_browser_service.FundManagerBrowserService.browse"),
        ("/api/managers/compare?manager_id=a&manager_id=b", "services.fund_manager_comparison_service.FundManagerComparisonService.build"),
        ("/api/managers/isolated", "services.fund_manager_research_service.FundManagerResearchService.build"),
        ("/api/managers/isolated/career", "services.fund_manager_career_service.FundManagerCareerService.build"),
    ]
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        for url, target in cases:
            entered, release = threading.Event(), threading.Event()

            def slow_query(*args, **kwargs):
                entered.set()
                if not release.wait(2):
                    raise RuntimeError("Query blocked the event loop")
                return {"evidence": "isolated"}

            with patch(target, side_effect=slow_query):
                task = asyncio.create_task(client.get(url))
                try:
                    assert await asyncio.to_thread(entered.wait, 1), url
                    response = await asyncio.wait_for(client.get("/probe"), 0.5)
                    assert response.json() == {"ready": True}
                    assert not task.done(), f"research query blocked concurrent requests: {url}"
                finally:
                    release.set()
                    result = await task
                assert result.status_code == 200 and result.json()["evidence"] == "isolated"
    print("PASS four manager research routes keep health responsive during slow queries (no DB)")


asyncio.run(main())
