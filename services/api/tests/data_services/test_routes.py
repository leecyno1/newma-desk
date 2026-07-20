from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from vibe_visualization_api.config import Settings
from vibe_visualization_api.data_services.models import (
    DataServiceDescriptor,
    ServiceCapability,
)
from vibe_visualization_api.main import create_app


class FakeDataServiceClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, dict[str, Any]]] = []

    async def invoke(
        self,
        service: DataServiceDescriptor,
        capability_id: str,
        input_data: dict[str, Any],
    ) -> dict[str, object]:
        self.calls.append((service.id, capability_id, input_data))
        return {"ok": True, "serviceId": service.id}


@pytest.fixture
def market_service() -> DataServiceDescriptor:
    return DataServiceDescriptor(
        id="market-data",
        base_url="http://127.0.0.1:9000/api",
        transport="rest",
        allowed_hosts=["127.0.0.1"],
        auth_secret="MARKET_DATA_TOKEN",
        capabilities={
            "market.overview": ServiceCapability(
                method="POST",
                path="/overview",
                input_schema="MarketOverviewInput",
                output_schema="MarketOverviewOutput",
                permission="market.read",
            )
        },
    )


@pytest.fixture
def fake_client() -> FakeDataServiceClient:
    return FakeDataServiceClient()


@pytest.fixture
def client(
    tmp_path: Path,
    market_service: DataServiceDescriptor,
    fake_client: FakeDataServiceClient,
) -> Iterator[TestClient]:
    application = create_app(
        Settings(runtime_dir=tmp_path, database_path=tmp_path / "app.db"),
        data_services=[market_service],
        data_service_client=fake_client,
    )
    with TestClient(application) as test_client:
        yield test_client


def test_data_service_routes_discover_only_public_metadata(
    client: TestClient,
) -> None:
    response = client.get("/api/data-services")

    assert response.status_code == 200
    assert response.json()[0]["id"] == "market-data"
    assert "authSecret" not in response.json()[0]
    assert "baseUrl" not in response.json()[0]
    assert client.get("/api/data-services/capabilities").json() == ["market.overview"]


def test_data_service_route_invokes_registered_capability(
    client: TestClient,
    fake_client: FakeDataServiceClient,
) -> None:
    response = client.post(
        "/api/data-services/market-data/invoke/market.overview",
        json={"date": "2026-07-20"},
    )

    assert response.status_code == 200
    assert response.json() == {"ok": True, "serviceId": "market-data"}
    assert fake_client.calls == [
        ("market-data", "market.overview", {"date": "2026-07-20"})
    ]


def test_data_service_route_rejects_unregistered_service_and_capability(
    client: TestClient,
    fake_client: FakeDataServiceClient,
) -> None:
    missing_service = client.post(
        "/api/data-services/missing/invoke/market.overview",
        json={},
    )
    missing_capability = client.post(
        "/api/data-services/market-data/invoke/market.missing",
        json={},
    )

    assert missing_service.status_code == 404
    assert missing_capability.status_code == 404
    assert fake_client.calls == []
