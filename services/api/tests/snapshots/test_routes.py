from pathlib import Path

from fastapi.testclient import TestClient

from vibe_visualization_api.config import Settings
from vibe_visualization_api.main import create_app
from vibe_visualization_api.snapshots.store import SnapshotStore


def test_snapshot_routes_return_latest_history_and_immutable_version(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "app.db"
    settings = Settings(runtime_dir=tmp_path, database_path=database_path)
    snapshot = SnapshotStore(tmp_path, database_path).write_success(
        "market-daily",
        {"asOf": "2026-07-18T15:00:00+08:00", "breadth": {"up": 3000}},
    )

    with TestClient(create_app(settings)) as client:
        latest = client.get("/api/modules/market-daily/snapshot")
        history = client.get("/api/modules/market-daily/snapshots")
        immutable = client.get(
            f"/api/modules/market-daily/snapshots/{snapshot.id}"
        )

    assert latest.status_code == 200
    assert latest.headers["cache-control"] == "no-store"
    assert latest.json()["id"] == snapshot.id
    assert latest.json()["moduleId"] == "market-daily"
    assert latest.json()["data"]["breadth"] == {"up": 3000}
    assert history.status_code == 200
    assert history.headers["cache-control"] == "no-store"
    assert history.json() == [
        {
            "id": snapshot.id,
            "moduleId": "market-daily",
            "createdAt": latest.json()["createdAt"],
            "url": f"/api/modules/market-daily/snapshots/{snapshot.id}",
        }
    ]
    assert immutable.status_code == 200
    assert immutable.headers["cache-control"] == "public, max-age=31536000, immutable"
    assert immutable.json() == latest.json()


def test_latest_snapshot_returns_404_before_first_success(tmp_path: Path) -> None:
    settings = Settings(
        runtime_dir=tmp_path,
        database_path=tmp_path / "app.db",
    )

    with TestClient(create_app(settings)) as client:
        response = client.get("/api/modules/market-daily/snapshot")

    assert response.status_code == 404
    assert response.json() == {"detail": "module snapshot not found"}
