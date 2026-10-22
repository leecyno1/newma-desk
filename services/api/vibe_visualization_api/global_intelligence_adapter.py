"""Keep the Desk registry, credentials and database in the owning host."""
from fastapi import FastAPI

from .config import Settings
from .data_services.client import DataServiceClientError
from .data_services.registry import DataServiceRegistryError
from .global_intel.client import GlobalIntelClient
from .global_topics.sources import TopicSources


def install_global_intelligence(app: FastAPI, settings: Settings) -> None:
    app.state.global_intelligence_settings = settings
    app.state.global_intel_client = GlobalIntelClient(settings.world_intel_url)

    async def read_crucix(capability_id: str):
        return await app.state.data_service_client.invoke(
            app.state.data_service_registry.get("crucix"), capability_id, {}
        )

    async def crucix_snapshot():
        return await read_crucix("crucix.snapshot")

    async def maritime_snapshot():
        return await app.state.global_intel_client.get_json("/api/maritime/warnings", timeout_seconds=15)

    app.state.crucix_reader = read_crucix
    app.state.global_topic_sources = TopicSources(
        tushare_token=settings.tushare_token.get_secret_value(),
        crucix_snapshot=crucix_snapshot,
        maritime_snapshot=maritime_snapshot,
        upstream_errors=(DataServiceClientError, DataServiceRegistryError),
    )
