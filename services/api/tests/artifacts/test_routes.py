from pathlib import Path

from fastapi.testclient import TestClient

from vibe_visualization_api.config import Settings
from vibe_visualization_api.main import create_app


def graph_payload() -> dict[str, object]:
    return {
        "moduleId": "industry-map",
        "title": "AI 算力产业链",
        "subtitle": "Agent 生成，Archify 渲染",
        "nodes": [
            {
                "id": "demand",
                "label": "大模型需求",
                "subtitle": "训练与推理",
                "kind": "source",
            },
            {
                "id": "chips",
                "label": "AI 芯片",
                "subtitle": "GPU / ASIC / NPU",
                "kind": "component",
            },
            {
                "id": "optics",
                "label": "高速光互连",
                "subtitle": "800G / 1.6T / CPO",
                "kind": "infrastructure",
            },
        ],
        "edges": [
            {"source": "demand", "target": "chips", "kind": "flow"},
            {"source": "chips", "target": "optics", "kind": "supply"},
        ],
        "sourceText": "大模型需求 → AI 芯片 → 高速光互连",
    }


def test_archify_artifact_can_be_rendered_published_and_reloaded(
    tmp_path: Path,
) -> None:
    settings = Settings(
        runtime_dir=tmp_path,
        database_path=tmp_path / "app.db",
    )

    with TestClient(create_app(settings)) as client:
        created = client.post("/api/artifacts", json=graph_payload())
        artifact_id = created.json()["id"]
        view = client.get(f"/api/artifacts/{artifact_id}/view")
        published = client.post(f"/api/artifacts/{artifact_id}/publish")
        artifacts = client.get(
            "/api/artifacts",
            params={"module_id": "industry-map"},
        )
        latest = client.get(
            "/api/artifacts/latest",
            params={"module_id": "industry-map", "status": "published"},
        )

    assert created.status_code == 201
    assert created.json()["renderer"] == "archify"
    assert created.json()["status"] == "draft"
    assert created.json()["archifyIr"]["diagram_type"] == "architecture"
    assert view.status_code == 200
    assert "AI 算力产业链" in view.text
    assert "data-newma-archify-theme-adapter" in view.text
    assert "newma:artifact-theme" in view.text
    assert "default-src 'none'" in view.headers["content-security-policy"]
    assert published.status_code == 200
    assert published.json()["status"] == "published"
    assert artifacts.status_code == 200
    assert artifacts.json()[0]["spec"]["sourceText"].startswith("大模型需求")
    assert latest.status_code == 200
    assert latest.json()["id"] == artifact_id


def test_artifact_rejects_edges_to_unknown_nodes(client: TestClient) -> None:
    payload = graph_payload()
    payload["edges"] = [{"source": "demand", "target": "missing"}]

    response = client.post("/api/artifacts", json=payload)

    assert response.status_code == 422


def test_replay_session_is_persisted_as_a_vibedesk_artifact(
    tmp_path: Path,
) -> None:
    settings = Settings(
        runtime_dir=tmp_path,
        database_path=tmp_path / "app.db",
    )
    payload = {
        "moduleId": "trading-replay",
        "title": "贵州茅台日线回放",
        "security": {
            "symbol": "600519",
            "name": "贵州茅台",
            "market": "CN",
            "exchange": "SH",
        },
        "timeframe": "1d",
        "cursor": 80,
        "totalBars": 240,
        "replayTimestamp": 1_750_000_000_000,
        "orders": [
            {
                "id": "buy-1",
                "side": "buy",
                "index": 72,
                "timestamp": 1_749_000_000_000,
                "price": 1500.5,
            }
        ],
        "metrics": {"position": 1, "simulatedPnl": 12.4},
    }

    with TestClient(create_app(settings)) as client:
        created = client.post("/api/artifacts/replays", json=payload)
        artifact_id = created.json()["id"]
        listed = client.get(
            "/api/artifacts/replays",
            params={"module_id": "trading-replay"},
        )
        view = client.get(f"/api/artifacts/replays/{artifact_id}/view")

    assert created.status_code == 201
    assert created.json()["kind"] == "replay"
    assert listed.status_code == 200
    assert listed.json()[0]["spec"]["orders"][0]["side"] == "buy"
    assert view.status_code == 200
    assert "贵州茅台日线回放" in view.text
    assert "data-newma-replay-theme-adapter" in view.text
    assert "data-newma-archify-theme-adapter" in view.text
    assert "newma:artifact-theme" in view.text
    assert "prefers-color-scheme" not in view.text
    assert "script-src 'unsafe-inline'" in view.headers["content-security-policy"]
