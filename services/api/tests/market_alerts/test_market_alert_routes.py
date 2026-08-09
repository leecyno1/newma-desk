from pathlib import Path

from fastapi.testclient import TestClient

from vibe_visualization_api.config import Settings
from vibe_visualization_api.main import create_app


def client(tmp_path: Path) -> TestClient:
    settings = Settings(
        database_path=tmp_path / "market-alerts.db",
        runtime_dir=tmp_path / "runtime",
        mod_session_secret="market-alert-test-secret",
        _env_file=None,
    )
    return TestClient(create_app(settings, data_services=[]))


def identity(user: str = "alice", workspace: str = "desk-a") -> dict[str, str]:
    return {"X-User-Id": user, "X-Workspace-Id": workspace}


def alert_payload(symbol: str = "AAPL") -> dict:
    return {
        "security": {
            "symbol": symbol,
            "name": "Apple",
            "market": "US",
            "exchange": "NASDAQ",
        },
        "direction": "above",
        "price": 250,
        "label": "突破观察位",
    }


def test_market_alert_crud_and_owner_isolation(tmp_path: Path):
    api = client(tmp_path)
    created = api.post(
        "/api/market-alerts",
        headers=identity(),
        json=alert_payload(),
    )
    assert created.status_code == 201
    alert = created.json()
    assert alert["security"]["symbol"] == "AAPL"
    assert alert["enabled"] is True

    listed = api.get("/api/market-alerts", headers=identity())
    assert listed.status_code == 200
    assert [item["id"] for item in listed.json()["items"]] == [alert["id"]]

    isolated = api.get(
        "/api/market-alerts",
        headers=identity(workspace="desk-b"),
    )
    assert isolated.status_code == 200
    assert isolated.json()["items"] == []

    updated = api.patch(
        f"/api/market-alerts/{alert['id']}",
        headers=identity(),
        json={"enabled": False, "price": 245.5},
    )
    assert updated.status_code == 200
    assert updated.json()["enabled"] is False
    assert updated.json()["price"] == 245.5

    enabled_only = api.get(
        "/api/market-alerts",
        headers=identity(),
        params={"enabled": "true"},
    )
    assert enabled_only.json()["items"] == []

    deleted = api.delete(
        f"/api/market-alerts/{alert['id']}",
        headers=identity(),
    )
    assert deleted.status_code == 200
    assert deleted.json() == {"id": alert["id"], "deleted": True}


def test_market_alert_validation_and_foreign_mutation(tmp_path: Path):
    api = client(tmp_path)
    invalid = api.post(
        "/api/market-alerts",
        headers=identity(),
        json={**alert_payload(), "price": 0},
    )
    assert invalid.status_code == 422

    alert_id = api.post(
        "/api/market-alerts",
        headers=identity(),
        json=alert_payload("MSFT"),
    ).json()["id"]
    foreign = api.patch(
        f"/api/market-alerts/{alert_id}",
        headers=identity(user="bob"),
        json={"enabled": False},
    )
    assert foreign.status_code == 404

    empty = api.patch(
        f"/api/market-alerts/{alert_id}",
        headers=identity(),
        json={},
    )
    assert empty.status_code == 422

    null_value = api.patch(
        f"/api/market-alerts/{alert_id}",
        headers=identity(),
        json={"price": None},
    )
    assert null_value.status_code == 422
