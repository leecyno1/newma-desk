from fastapi.testclient import TestClient

from vibe_visualization_api.main import app


def test_health_reports_service_identity() -> None:
    response = TestClient(app).get("/api/health")

    assert response.status_code == 200
    assert response.json() == {
        "ok": True,
        "service": "vibe-visualization-api",
        "version": "0.1.0",
    }


def test_health_allows_configured_origin(client: TestClient) -> None:
    origin = "http://127.0.0.1:5888"

    response = client.get("/api/health", headers={"Origin": origin})

    assert response.headers["access-control-allow-origin"] == origin


def test_health_rejects_unconfigured_origin(client: TestClient) -> None:
    response = client.get(
        "/api/health", headers={"Origin": "https://evil.example"}
    )

    assert "access-control-allow-origin" not in response.headers
