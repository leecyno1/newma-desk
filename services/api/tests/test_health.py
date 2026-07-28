from fastapi.testclient import TestClient

from vibe_visualization_api.config import Settings
from vibe_visualization_api.main import create_app


def test_health_reports_service_identity(client: TestClient) -> None:
    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {
        "ok": True,
        "service": "newma-desk-api",
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


def test_cors_preflight_allows_post_with_required_headers(
    client: TestClient,
) -> None:
    origin = "http://127.0.0.1:5888"

    response = client.options(
        "/api/health",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": (
                "Content-Type,Authorization,"
                "X-Newma-Desk-Instance-Id,X-Newma-Dock-Instance-Id"
            ),
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == origin
    assert "POST" in response.headers["access-control-allow-methods"].split(", ")
    allowed_headers = {
        header.strip().lower()
        for header in response.headers["access-control-allow-headers"].split(",")
    }
    assert {
        "content-type",
        "authorization",
        "x-newma-desk-instance-id",
        "x-newma-dock-instance-id",
    } <= allowed_headers


def test_app_factory_honors_settings_origin_override() -> None:
    custom_origin = "https://custom.example"
    test_settings = Settings(allowed_origins=custom_origin)

    with TestClient(create_app(test_settings)) as test_client:
        custom_response = test_client.get(
            "/api/health", headers={"Origin": custom_origin}
        )
        default_response = test_client.get(
            "/api/health", headers={"Origin": "http://127.0.0.1:5888"}
        )

    assert custom_response.headers["access-control-allow-origin"] == custom_origin
    assert "access-control-allow-origin" not in default_response.headers
