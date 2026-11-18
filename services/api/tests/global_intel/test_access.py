import asyncio
import json
import sqlite3
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi import HTTPException, Request
from fastapi.testclient import TestClient

from vibe_visualization_api.global_intel.access import DeskScopeResolver, guard_stream
from vibe_visualization_api.global_intel.app import create_app
from vibe_visualization_api.global_intel.runtime import Settings


ENDPOINT = "http://127.0.0.1:18911/api/mods/runtime/global-scope"
HEADERS = {"Authorization": "Bearer synthetic-session", "X-Newma-Desk-Instance-Id": "page-one"}


@pytest.mark.parametrize("changes", [
    {"access_mode": "desk"},
    {"desk_scope_url": ENDPOINT},
    {"access_mode": "desk", "desk_scope_url": "https://example.com/api/mods/runtime/global-scope"},
    {"access_mode": "desk", "desk_scope_url": ENDPOINT + "?token=x"},
])
def test_invalid_access_configuration_fails_before_serving(changes):
    with pytest.raises(ValueError):
        Settings(**changes)


def test_local_api_does_not_treat_a_desk_session_as_anonymous(tmp_path):
    client = TestClient(create_app(Settings(database_path=tmp_path / "topics.db")))
    response = client.post("/api/global-topics/fed-rates/forecast", headers=HEADERS, json={})
    assert response.status_code == 503
    assert not (tmp_path / "topics.db").exists()


@pytest.mark.asyncio
async def test_independent_forecast_owner_comes_only_from_host(tmp_path):
    forwarded = []
    def check(request):
        forwarded.append(request)
        assert request.headers.get("cookie") is None
        assert request.headers.get("x-user-id") is None
        assert request.headers.get("x-workspace-id") is None
        target = json.loads(request.content)
        assert target["method"] in ("GET", "POST")
        assert target["path"].startswith("/api/global-topics/fed-rates")
        workspace = request.headers["authorization"].removeprefix("Bearer ")
        return httpx.Response(200, json={"userId": "real-owner", "workspaceId": workspace})

    database = tmp_path / "topics.db"
    app = create_app(Settings(database_path=database, access_mode="desk", desk_scope_url=ENDPOINT))
    app.state.global_topic_sources = SimpleNamespace(snapshot=AsyncMock(return_value={}))
    async with httpx.AsyncClient(transport=httpx.MockTransport(check)) as validator:
        app.state.global_topic_authorizer.client = validator
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://independent") as client:
            assert (await client.post("/api/global-topics/fed-rates/forecast", json={})).status_code == 401
            for workspace, value in (("a", 20), ("b", 80)):
                headers = {**HEADERS, "Authorization": "Bearer " + workspace, "X-User-Id": "forged", "X-Workspace-Id": "forged"}
                initial = await client.get("/api/global-topics/fed-rates", headers=headers)
                assert initial.json()["forecastOrigin"] == "default"
                saved = await client.post("/api/global-topics/fed-rates/forecast", headers=headers, json={"factors": {"inflation": value}})
                assert saved.status_code == 200
                read = await client.get("/api/global-topics/fed-rates", headers=headers)
                assert read.json()["forecast"] == saved.json()
                assert read.headers["cache-control"] == "no-store"
    assert len(forwarded) == 6
    with sqlite3.connect(database) as conn:
        assert conn.execute("SELECT user_id,workspace_id FROM global_topic_scoped_forecasts ORDER BY id").fetchall() == [("real-owner", "a"), ("real-owner", "b")]
        assert conn.execute("SELECT count(*) FROM global_topic_forecasts").fetchone()[0] == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("status,body,expected", [(401, {}, 401), (403, {}, 403), (500, {}, 503),
    (302, {}, 503), (200, {}, 503), (200, {"userId": "a", "workspaceId": ""}, 503)])
async def test_failed_validator_never_falls_back(status, body, expected):
    request = Request({"type": "http", "method": "GET", "path": "/api/global-topics/fed-rates",
                       "headers": [(k.lower().encode(), v.encode()) for k, v in HEADERS.items()], "query_string": b""})
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _: httpx.Response(status, json=body))) as client:
        with pytest.raises(HTTPException) as error:
            await DeskScopeResolver(ENDPOINT, client=client)(request)
    assert error.value.status_code == expected


@pytest.mark.asyncio
@pytest.mark.parametrize("failure,status", [(401, "unauthorized"), (503, "unavailable")])
async def test_silent_stream_closes_when_validator_revokes_or_disconnects(failure, status):
    closed = asyncio.Event()
    allowed = True
    async def authorize(_):
        if not allowed:
            raise HTTPException(failure)
    async def source():
        try:
            yield b"data: first\n\n"
            await asyncio.Event().wait()
        finally:
            closed.set()
    stream = guard_stream(None, source(), authorize, interval=0.01)
    assert await anext(stream) == b"data: first\n\n"
    pending = asyncio.create_task(anext(stream))
    await asyncio.sleep(0.02)
    allowed = False
    failure_frame = await asyncio.wait_for(pending, 1)
    assert status.encode() in failure_frame
    assert ('"code":"' + ("scope_denied" if failure == 401 else "scope_unavailable") + '"').encode() in failure_frame
    assert b'"stage":"domain_scope"' in failure_frame
    await stream.aclose()
    assert closed.is_set()
