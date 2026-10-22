import sqlite3

import httpx
import pytest
from fastapi.testclient import TestClient

from vibe_visualization_api.crucix.client import CrucixClient, CrucixUnavailable
from vibe_visualization_api.global_intel.app import create_app
from vibe_visualization_api.global_intel.runtime import Settings


def test_unconfigured_engines_are_unavailable_without_contacting_desk(tmp_path):
    client = TestClient(create_app(Settings(database_path=tmp_path / "topics.sqlite3")))
    assert client.get("/api/health").json()["sources"] == {"worldIntelConfigured": False, "crucixConfigured": False}
    for route in ("/api/global-intel/health", "/api/global-intel/overview", "/api/global-intel/stream", "/api/crucix/snapshot"):
        assert client.get(route).status_code == 503
    assert client.get("/api/agents").status_code == 404


def test_forecast_writes_only_project_database(tmp_path):
    database = tmp_path / "topics.sqlite3"
    client = TestClient(create_app(Settings(database_path=database)))
    response = client.post("/api/global-topics/fed-rates/forecast", json={"factors": {"inflation": 80}})
    assert response.status_code == 200
    with sqlite3.connect(database) as connection:
        assert connection.execute("SELECT topic_id FROM global_topic_forecasts").fetchall() == [("fed-rates",)]
    assert client.post("/api/global-topics/missing/forecast", json={}).status_code == 404


def test_four_entrypoints_keep_both_static_paths(tmp_path):
    (tmp_path / "index.html").write_text("<main>global</main>")
    client = TestClient(create_app(Settings(database_path=tmp_path / "topics.sqlite3"), str(tmp_path)))
    for root in ("/", "/mods/global-intelligence/"):
        for query in ("", "?topic=fed-rates", "?topic=hormuz", "?topic=us-china-trade"):
            assert client.get(root + query).text == "<main>global</main>"
    assert client.get("/api/missing").status_code == 404


@pytest.mark.asyncio
async def test_standalone_crucix_reader_preserves_shared_normalization():
    requests = []
    def handle(request):
        requests.append(str(request.url))
        return httpx.Response(200, json={"meta": {"timestamp": "2026-10-20T00:00:00Z"},
                                         "newsFeed": [{"headline": "Public source observation"}]})
    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
        result = await CrucixClient("http://engine.invalid", client=client).read("crucix.snapshot")
    assert requests == ["http://engine.invalid/api/data"]
    assert result["contract"] == "newma-desk.crucix-intelligence.v1"
    assert result["news"][0]["title"] == "Public source observation"
    with pytest.raises(CrucixUnavailable):
        await CrucixClient("").read("crucix.snapshot")
