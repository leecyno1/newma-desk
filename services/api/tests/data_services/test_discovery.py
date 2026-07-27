import json
from pathlib import Path

import pytest

from vibe_visualization_api.data_services.discovery import (
    DataServiceDiscoveryError,
    discover_data_services,
)


def _descriptor() -> dict[str, object]:
    return {
        "id": "market-data",
        "baseUrl": "http://127.0.0.1:8900",
        "healthPath": "/api/health",
        "transport": "rest",
        "capabilities": {
            "market.overview": {
                "method": "GET",
                "path": "/api/market/overview",
                "inputSchema": "EmptyInput",
                "outputSchema": "MarketOverview",
                "permission": "market.read",
            }
        },
        "allowedHosts": ["127.0.0.1"],
    }


def test_discovers_nested_data_service_descriptors(tmp_path: Path) -> None:
    descriptor_path = tmp_path / "vibe-research" / "data-service.json"
    descriptor_path.parent.mkdir()
    descriptor_path.write_text(
        json.dumps(_descriptor()),
        encoding="utf-8",
    )

    services = discover_data_services([tmp_path])

    assert [service.id for service in services] == ["market-data"]
    assert "market.overview" in services[0].capabilities


def test_missing_discovery_roots_are_ignored(tmp_path: Path) -> None:
    assert discover_data_services([tmp_path / "missing"]) == []


def test_applies_trusted_base_url_override_and_allowlists_its_host(
    tmp_path: Path,
) -> None:
    descriptor_path = tmp_path / "data-service.json"
    descriptor_path.write_text(json.dumps(_descriptor()), encoding="utf-8")

    services = discover_data_services(
        [tmp_path],
        base_url_overrides={
            "market-data": "http://market-service.test:9911/api/research",
        },
    )

    assert str(services[0].base_url) == (
        "http://market-service.test:9911/api/research"
    )
    assert "market-service.test" in services[0].allowed_hosts


def test_invalid_descriptor_fails_fast(tmp_path: Path) -> None:
    descriptor_path = tmp_path / "data-service.json"
    descriptor_path.write_text('{"id":"broken"}', encoding="utf-8")

    with pytest.raises(DataServiceDiscoveryError):
        discover_data_services([tmp_path])
