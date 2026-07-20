import pytest

from vibe_visualization_api.data_services.models import (
    DataServiceDescriptor,
    ServiceCapability,
)
from vibe_visualization_api.data_services.registry import DataServiceRegistry


@pytest.fixture
def market_service() -> DataServiceDescriptor:
    return DataServiceDescriptor(
        id="market-data",
        base_url="http://127.0.0.1:9000/api",
        health_path="/health",
        transport="rest",
        allowed_hosts=["127.0.0.1"],
        auth_secret="MARKET_DATA_TOKEN",
        capabilities={
            "market.indices": ServiceCapability(
                method="GET",
                path="/indices",
                input_schema="MarketIndicesInput",
                output_schema="MarketIndicesOutput",
                permission="market.read",
            ),
            "market.overview": ServiceCapability(
                method="POST",
                path="/overview",
                input_schema="MarketOverviewInput",
                output_schema="MarketOverviewOutput",
                permission="market.read",
            ),
        },
    )


def test_registry_discovers_capabilities(
    market_service: DataServiceDescriptor,
) -> None:
    registry = DataServiceRegistry([market_service])

    assert registry.capabilities() == ["market.indices", "market.overview"]
    assert registry.get("market-data") == market_service


def test_registry_public_descriptions_do_not_expose_secrets_or_network_policy(
    market_service: DataServiceDescriptor,
) -> None:
    registry = DataServiceRegistry([market_service])

    description = registry.describe()[0]

    assert description["id"] == "market-data"
    assert description["transport"] == "rest"
    assert "authSecret" not in description
    assert "allowedHosts" not in description
    assert "baseUrl" not in description


def test_registry_rejects_duplicate_service_ids(
    market_service: DataServiceDescriptor,
) -> None:
    with pytest.raises(ValueError):
        DataServiceRegistry([market_service, market_service])


@pytest.mark.parametrize(
    "path",
    [
        "indices",
        "//evil.example/collect",
        "/../secret",
        "/%2e%2e/secret",
        "/%ZZ",
        "/%00secret",
        "/indices?target=http://evil.example",
        "/indices#fragment",
    ],
)
def test_capability_rejects_unsafe_paths(path: str) -> None:
    with pytest.raises(ValueError):
        ServiceCapability(
            method="GET",
            path=path,
            input_schema="Input",
            output_schema="Output",
            permission="market.read",
        )
