"""Domain storage semantics; real Website authorization is tested separately."""
import json
import sqlite3
from types import SimpleNamespace

from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from vibe_visualization_api.global_topics.routes import router
from vibe_visualization_api.global_topics.store import GlobalTopicStore


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
