from typing import Any

from fastapi import APIRouter, Body, Depends, Request

from vibe_visualization_api.data_services.client import (
    DataServiceClient,
    UnknownServiceCapability,
)
from vibe_visualization_api.data_services.registry import DataServiceRegistry


router = APIRouter(prefix="/api/data-services", tags=["data-services"])


def get_data_service_registry(request: Request) -> DataServiceRegistry:
    return request.app.state.data_service_registry


def get_data_service_client(request: Request) -> DataServiceClient:
    return request.app.state.data_service_client


@router.get("")
def list_data_services(
    registry: DataServiceRegistry = Depends(get_data_service_registry),
) -> list[dict[str, object]]:
    return registry.describe()


@router.get("/capabilities")
def list_data_service_capabilities(
    registry: DataServiceRegistry = Depends(get_data_service_registry),
) -> list[str]:
    return registry.capabilities()


@router.post("/{service_id}/invoke/{capability_id}")
async def invoke_data_service(
    service_id: str,
    capability_id: str,
    input_data: dict[str, Any] = Body(default_factory=dict),
    registry: DataServiceRegistry = Depends(get_data_service_registry),
    client: DataServiceClient = Depends(get_data_service_client),
) -> Any:
    service = registry.get(service_id)
    if capability_id not in service.capabilities:
        raise UnknownServiceCapability(
            f"capability {capability_id!r} is not registered"
        )
    return await client.invoke(service, capability_id, input_data)
