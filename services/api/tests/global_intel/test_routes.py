from collections.abc import AsyncIterator

from fastapi.testclient import TestClient

from vibe_visualization_api.global_intel.client import GlobalIntelUnavailable


class FakeGlobalIntelClient:
    def __init__(self, *, unavailable: bool = False) -> None:
        self.unavailable = unavailable
        self.requests: list[tuple[str, float]] = []

    async def get_json(self, path: str, *, timeout_seconds: float = 120.0) -> dict:
        self.requests.append((path, timeout_seconds))
        if self.unavailable:
            raise GlobalIntelUnavailable("World Intelligence service is unavailable")
        if path == "/api/health":
            return {"status": "ok", "service": "world-intel-mcp"}
        return {"path": path, "timestamp": "2026-08-09T12:00:00Z"}

    async def stream(self, path: str) -> AsyncIterator[bytes]:
        assert path == "/api/stream"
        yield b'data: {"timestamp":"2026-08-09T12:00:00Z"}\n\n'


def install_fake(client: TestClient, fake: FakeGlobalIntelClient) -> None:
    client.app.state.global_intel_client = fake


def test_health_wraps_upstream_identity(client: TestClient) -> None:
    fake = FakeGlobalIntelClient()
    install_fake(client, fake)

    response = client.get("/api/global-intel/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "world-intel-mcp",
        "upstream": {"status": "ok", "service": "world-intel-mcp"},
    }
    assert fake.requests == [("/api/health", 5.0)]


def test_snapshot_routes_use_bounded_upstream_timeouts(client: TestClient) -> None:
    fake = FakeGlobalIntelClient()
    install_fake(client, fake)

    static_response = client.get("/api/global-intel/static")
    overview_response = client.get("/api/global-intel/overview")

    assert static_response.status_code == 200
    assert overview_response.status_code == 200
    assert fake.requests == [
        ("/api/static", 10.0),
        ("/api/overview", 150.0),
    ]


def test_gateway_returns_503_when_world_intel_is_unavailable(
    client: TestClient,
) -> None:
    install_fake(client, FakeGlobalIntelClient(unavailable=True))

    response = client.get("/api/global-intel/overview")

    assert response.status_code == 503
    assert response.json()["detail"] == "World Intelligence service is unavailable"


def test_gateway_preserves_sse_transport_headers(client: TestClient) -> None:
    install_fake(client, FakeGlobalIntelClient())

    response = client.get("/api/global-intel/stream")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert response.headers["cache-control"] == "no-cache"
    assert response.text == 'data: {"timestamp":"2026-08-09T12:00:00Z"}\n\n'
