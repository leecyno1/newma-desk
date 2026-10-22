import sqlite3

import pytest

from vibe_visualization_api.data_services.client import DataServiceClientError
from vibe_visualization_api.data_services.registry import DataServiceRegistryError


def test_desk_adapter_keeps_existing_forecast_database(client):
    settings = client.app.state.global_intelligence_settings
    assert client.post("/api/global-topics/fed-rates/forecast", json={"factors": {"inflation": 75}}).status_code == 200
    with sqlite3.connect(settings.database_path) as connection:
        assert connection.execute("SELECT topic_id FROM global_topic_forecasts").fetchall() == [("fed-rates",)]


@pytest.mark.asyncio
@pytest.mark.parametrize("error", [DataServiceClientError, DataServiceRegistryError])
async def test_desk_gateway_errors_still_become_missing_source_evidence(client, error):
    async def unavailable():
        raise error("host gateway unavailable")
    result = await client.app.state.global_topic_sources._source("test", "Host source", "", unavailable)
    assert result["status"] == "unavailable"
    assert result["data"] is None
    assert error.__name__ in result["reason"]
