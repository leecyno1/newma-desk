from pathlib import Path

from fastapi.testclient import TestClient

from vibe_visualization_api.config import Settings
from vibe_visualization_api.main import create_app


def client(tmp_path: Path) -> TestClient:
    settings = Settings(
        database_path=tmp_path / "watchlists.db",
        runtime_dir=tmp_path / "runtime",
        mod_session_secret="watchlist-test-secret",
        _env_file=None,
    )
    return TestClient(create_app(settings, data_services=[]))


def identity(user: str = "alice", workspace: str = "desk-a") -> dict[str, str]:
    return {
        "X-User-Id": user,
        "X-Workspace-Id": workspace,
    }


def test_returns_seeded_cross_market_watchlist(tmp_path: Path) -> None:
    response = client(tmp_path).get("/api/watchlists", headers=identity())

    assert response.status_code == 200
    payload = response.json()
    assert payload["revision"] == 0
    assert payload["userId"] == "alice"
    assert len(payload["groups"][0]["symbols"]) == 10
    assert {item["market"] for item in payload["groups"][0]["symbols"]} == {
        "CN",
        "HK",
        "US",
    }


def test_replaces_then_mutates_groups_and_securities(tmp_path: Path) -> None:
    api = client(tmp_path)
    headers = identity()
    replacement = api.put(
        "/api/watchlists",
        headers=headers,
        json={
            "revision": 0,
            "groups": [
                {
                    "id": "core",
                    "name": "核心组合",
                    "symbols": [
                        {
                            "symbol": "600519",
                            "name": "贵州茅台",
                            "market": "CN",
                        }
                    ],
                }
            ],
        },
    )
    assert replacement.status_code == 200
    assert replacement.json()["revision"] == 1

    created = api.post(
        "/api/watchlists/groups",
        headers=headers,
        json={"id": "overseas", "name": "海外观察"},
    )
    assert created.status_code == 201
    assert created.json()["revision"] == 2

    renamed = api.patch(
        "/api/watchlists/groups/overseas",
        headers=headers,
        json={"name": "海外核心"},
    )
    assert renamed.status_code == 200
    assert renamed.json()["groups"][1]["name"] == "海外核心"

    added = api.put(
        "/api/watchlists/groups/overseas/securities/US/NVDA",
        headers=headers,
        json={
            "symbol": "NVDA",
            "name": "NVIDIA",
            "market": "US",
            "exchange": "NASDAQ",
        },
    )
    assert added.status_code == 200
    assert added.json()["groups"][1]["symbols"][0]["symbol"] == "NVDA"

    removed = api.delete(
        "/api/watchlists/groups/overseas/securities/US/NVDA",
        headers=headers,
    )
    assert removed.status_code == 200
    assert removed.json()["groups"][1]["symbols"] == []

    deleted = api.delete(
        "/api/watchlists/groups/overseas",
        headers=headers,
    )
    assert deleted.status_code == 200
    assert [group["id"] for group in deleted.json()["groups"]] == ["core"]


def test_rejects_stale_replace_and_isolates_workspaces(tmp_path: Path) -> None:
    api = client(tmp_path)
    first = api.put(
        "/api/watchlists",
        headers=identity(),
        json={
            "revision": 0,
            "groups": [{"id": "mine", "name": "我的组合", "symbols": []}],
        },
    )
    assert first.status_code == 200

    stale = api.put(
        "/api/watchlists",
        headers=identity(),
        json={
            "revision": 0,
            "groups": [{"id": "stale", "name": "旧版本", "symbols": []}],
        },
    )
    assert stale.status_code == 409

    other_workspace = api.get(
        "/api/watchlists",
        headers=identity(workspace="desk-b"),
    )
    assert other_workspace.status_code == 200
    assert other_workspace.json()["revision"] == 0
    assert other_workspace.json()["groups"][0]["id"] == "sample"


def test_validates_security_identity_and_group_invariants(tmp_path: Path) -> None:
    api = client(tmp_path)
    mismatch = api.put(
        "/api/watchlists/groups/sample/securities/US/NVDA",
        headers=identity(),
        json={"symbol": "AAPL", "name": "Apple", "market": "US"},
    )
    assert mismatch.status_code == 422

    only_group = api.delete(
        "/api/watchlists/groups/sample",
        headers=identity(),
    )
    assert only_group.status_code == 409

