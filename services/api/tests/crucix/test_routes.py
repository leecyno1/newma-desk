from typing import Any

from fastapi.testclient import TestClient

from vibe_visualization_api.data_services.models import DataServiceDescriptor
from vibe_visualization_api.data_services.registry import DataServiceRegistry


class FakeClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, dict[str, Any]]] = []

    async def invoke(
        self,
        service: DataServiceDescriptor,
        capability_id: str,
        input_data: dict[str, Any],
    ) -> dict[str, Any]:
        self.calls.append((service.id, capability_id, input_data))
        if capability_id == "crucix.health":
            return {
                "contract": "newma-desk.crucix-health.v1",
                "status": "ok",
                "service": "crucix",
                "sourceHealth": {"ok": 29, "failed": 0},
            }
        return {
            "contract": "newma-desk.crucix-intelligence.v1",
            "freshness": {"status": "fresh"},
            "sourceHealth": {"ok": 29, "failed": 0},
            "news": [],
            "macro": {},
            "global": {},
        }


def descriptor() -> DataServiceDescriptor:
    return DataServiceDescriptor.model_validate(
        {
            "id": "crucix",
            "baseUrl": "http://127.0.0.1:3117",
            "transport": "rest",
            "allowedHosts": ["127.0.0.1"],
            "capabilities": {
                "crucix.health": {
                    "method": "GET",
                    "path": "/api/health",
                    "inputSchema": {"type": "object"},
                    "outputSchema": {"type": "object"},
                    "permission": "market.read",
                },
                "crucix.snapshot": {
                    "method": "GET",
                    "path": "/api/data",
                    "inputSchema": {"type": "object"},
                    "outputSchema": {"type": "object"},
                    "permission": "market.read",
                },
            },
        }
    )


def install_fake(client: TestClient, fake: FakeClient) -> None:
    client.app.state.data_service_registry = DataServiceRegistry([descriptor()])
    client.app.state.data_service_client = fake


def test_crucix_routes_proxy_registered_read_capabilities(client: TestClient) -> None:
    fake = FakeClient()
    install_fake(client, fake)

    health = client.get("/api/crucix/health")
    snapshot = client.get("/api/crucix/snapshot")

    assert health.status_code == 200
    assert health.json()["service"] == "crucix"
    assert snapshot.status_code == 200
    assert snapshot.json()["contract"] == "newma-desk.crucix-intelligence.v1"
    assert fake.calls == [
        ("crucix", "crucix.health", {}),
        ("crucix", "crucix.snapshot", {}),
    ]
