import json
from pathlib import Path

import httpx
import pytest

from vibe_visualization_api.crucix.adapter import adapt_crucix_response
from vibe_visualization_api.data_services.client import DataServiceClient
from vibe_visualization_api.data_services.models import DataServiceDescriptor


@pytest.mark.asyncio
async def test_data_service_applies_crucix_adapter_before_contract_validation() -> None:
    descriptor_path = (
        Path(__file__).resolve().parents[4]
        / "integrations"
        / "crucix"
        / "data-service.json"
    )
    service = DataServiceDescriptor.model_validate(
        json.loads(descriptor_path.read_text(encoding="utf-8"))
    )
    http_client = httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                200,
                json={
                    "meta": {"timestamp": "2026-08-24T00:00:00Z"},
                    "newsFeed": [{"headline": "Structured headline"}],
                },
            )
        )
    )
    client = DataServiceClient(
        public_mode=False,
        response_adapters={"crucix": adapt_crucix_response},
        client=http_client,
    )

    try:
        result = await client.invoke(service, "crucix.snapshot", {})
    finally:
        await http_client.aclose()

    assert result["contract"] == "newma-desk.crucix-intelligence.v1"
    assert result["news"][0]["title"] == "Structured headline"
