"""Domain storage semantics; real Website authorization is tested separately."""
import json
import sqlite3
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from vibe_visualization_api.global_topics.routes import router
from vibe_visualization_api.global_topics.store import GlobalTopicStore
from vibe_visualization_api.global_topics.service import TOPICS, forecast


def topic_client(database, scope=None):
    app = FastAPI()
    app.state.global_intelligence_settings = SimpleNamespace(database_path=database)
    app.state.global_topic_sources = SimpleNamespace(snapshot=AsyncMock(return_value={
        "metrics": [], "events": [], "observations": [], "series": [], "sources": [],
        "dataMode": "unavailable", "freshness": "unknown",
    }))
    if scope is not None:
        app.state.global_topic_authorizer = AsyncMock(return_value=scope)
    app.include_router(router)
    return TestClient(app)


@pytest.mark.parametrize("topic_id", TOPICS)
@pytest.mark.parametrize("scope", [None, ("reader", "workspace")])
def test_reopened_topic_recovers_saved_parameters_and_exact_result(tmp_path, topic_id, scope):
    database = tmp_path / "reopen.db"
    factors = {factor["id"]: value for factor, value in zip(TOPICS[topic_id]["factors"], [0, 80, 100])}
    with topic_client(database, scope) as client:
        assert client.get(f"/api/global-topics/{topic_id}").json()["forecastOrigin"] == "default"
        written = client.post(f"/api/global-topics/{topic_id}/forecast", json={"factors": factors})
        assert written.status_code == 200
    # A new application, not an in-memory frontend cache.
    with topic_client(database, scope) as reopened:
        response = reopened.get(f"/api/global-topics/{topic_id}")
        assert response.status_code == 200
        body = response.json()
        assert body["forecast"] == written.json()
        assert {factor["id"]: factor["value"] for factor in body["factors"]} == factors
        assert body["forecastOrigin"] == "saved"
        assert body["forecastSavedAt"] == written.json()["generatedAt"]
        assert body["dataMode"] == "unavailable" and body["freshness"] == "unknown"
        assert body["metrics"] == []  # Saving assumptions never invents source observations.
        assert response.headers["cache-control"] == "no-store"
    with sqlite3.connect(database) as connection:
        table = "global_topic_scoped_forecasts" if scope else "global_topic_forecasts"
        assert connection.execute(f"SELECT count(*) FROM {table}").fetchone()[0] == 1


def test_latest_forecast_never_falls_back_to_another_scope_or_topic(tmp_path):
    database = tmp_path / "isolated.db"
    store = GlobalTopicStore(database)
    for scope, value in [(None, 10), (("alice", "a"), 20), (("alice", "b"), 30), (("bob", "a"), 40), (("alice", "a"), 90)]:
        factors = {"inflation": value, "employment": 50, "financialStress": 50}
        store.save_forecast("fed-rates", "2026-10-26T10:00:00Z", factors, forecast("fed-rates", factors), scope=scope)
    for scope, expected in [(None, 10), (("alice", "a"), 90), (("alice", "b"), 30), (("bob", "a"), 40), (("alice", "empty"), 50)]:
        with topic_client(database, scope) as client:
            body = client.get("/api/global-topics/fed-rates", headers={"X-User-Id": "alice", "X-Workspace-Id": "a"}).json()
            assert body["factors"][0]["value"] == expected
            assert body["forecastOrigin"] == ("default" if expected == 50 else "saved")
            other = client.get("/api/global-topics/hormuz").json()
            assert other["forecastOrigin"] == "default" and other["forecastSavedAt"] is None


def test_scope_hook_preserves_legacy_records_and_separates_workspaces(tmp_path):
    database = tmp_path / "topics.db"
    store = GlobalTopicStore(database)
    store.save_forecast("fed-rates", "legacy", {}, {"original": True})
    app = FastAPI()
    app.state.global_intelligence_settings = SimpleNamespace(database_path=database)
    app.include_router(router)
    workspace = "workspace-a"

    async def scope(_request: Request):
        return "synthetic-user", workspace

    app.state.global_topic_authorizer = scope
    with TestClient(app) as client:
        first = client.post("/api/global-topics/fed-rates/forecast", json={"factors": {"inflation": 10}})
        assert first.status_code == 200
        workspace = "workspace-b"
        second = client.post("/api/global-topics/fed-rates/forecast", json={"factors": {"inflation": 90}})
        assert second.status_code == 200
        assert first.json()["probabilities"] != second.json()["probabilities"]
        assert client.post("/api/global-topics/fed-rates/forecast", json={"workspaceId": "forged", "factors": {}}).status_code == 422
    with sqlite3.connect(database) as connection:
        assert connection.execute("SELECT created_at,result_json FROM global_topic_forecasts").fetchall() == [("legacy", '{"original": true}')]
        rows = connection.execute("SELECT user_id,workspace_id,factors_json FROM global_topic_scoped_forecasts ORDER BY id").fetchall()
    assert [(row[0], row[1]) for row in rows] == [("synthetic-user", "workspace-a"), ("synthetic-user", "workspace-b")]
    assert [json.loads(row[2])["inflation"] for row in rows] == [10, 90]
    assert all(len(json.loads(row[2])) == 3 for row in rows)
