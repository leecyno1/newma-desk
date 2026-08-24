from typing import Any

from fastapi import APIRouter, Depends, Request

from vibe_visualization_api.data_services.client import DataServiceClient
from vibe_visualization_api.data_services.registry import DataServiceRegistry


router = APIRouter(prefix="/api/crucix", tags=["crucix"])


def get_registry(request: Request) -> DataServiceRegistry:
    return request.app.state.data_service_registry


def get_client(request: Request) -> DataServiceClient:
    return request.app.state.data_service_client


async def _invoke(
    capability_id: str,
    registry: DataServiceRegistry,
    client: DataServiceClient,
) -> Any:
    service = registry.get("crucix")
    return await client.invoke(service, capability_id, {})


@router.get("/health")
async def crucix_health(
    registry: DataServiceRegistry = Depends(get_registry),
    client: DataServiceClient = Depends(get_client),
) -> Any:
    return await _invoke("crucix.health", registry, client)


@router.get("/snapshot")
async def crucix_snapshot(
    registry: DataServiceRegistry = Depends(get_registry),
    client: DataServiceClient = Depends(get_client),
) -> Any:
    return await _invoke("crucix.snapshot", registry, client)
