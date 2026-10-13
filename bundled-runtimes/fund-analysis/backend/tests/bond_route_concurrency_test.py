"""Slow bond synchronization/calculation must not freeze other requests."""
import asyncio
import os
import sys
import threading
from unittest.mock import patch

import httpx
from fastapi import FastAPI

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from routes.funds import router

app = FastAPI()
app.include_router(router)


@app.get("/probe")
async def probe():
    return {"ready": True}


async def main():
    cases = [
        ("GET", "/api/funds/isolated/bond-duration", "services.fund_bond_duration_service.FundBondDurationService.get"),
        ("POST", "/api/funds/isolated/bond-duration/calculate", "services.fund_bond_duration_service.FundBondDurationService.calculate"),
        ("GET", "/api/funds/isolated/bond-anomaly", "services.fund_bond_anomaly_service.FundBondAnomalyService.analyze"),
    ]
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        for method, url, target in cases:
            entered, release = threading.Event(), threading.Event()

            def slow_query(*args, **kwargs):
                entered.set()
                if not release.wait(2):
                    raise RuntimeError("Calculation blocked the event loop")
                return {"evidence": "isolated"}

            with patch(target, side_effect=slow_query):
                task = asyncio.create_task(client.request(method, url))
                try:
                    assert await asyncio.to_thread(entered.wait, 1), url
                    response = await asyncio.wait_for(client.get("/probe"), .5)
                    assert response.json() == {"ready": True}
                    assert not task.done()
                finally:
                    release.set()
                    result = await task
                assert result.status_code == 200 and result.json()["evidence"] == "isolated"
    print("PASS three bond routes allow concurrent requests (no network or database)")


asyncio.run(main())
