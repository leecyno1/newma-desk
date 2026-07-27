from typing import Any

from typing import Annotated

from fastapi import APIRouter, Body, Depends, Header, HTTPException, Path, Request
from starlette.concurrency import run_in_threadpool

from vibe_visualization_api.data_services.client import (
    DataServiceClient,
    UnknownServiceCapability,
)
from vibe_visualization_api.data_services.registry import DataServiceRegistry
from vibe_visualization_api.data_services.models import (
    DataServicePreferences,
    DataServicePreferencesUpdate,
)
from vibe_visualization_api.data_services.preferences import (
    DataServicePreferenceStore,
)


router = APIRouter(prefix="/api/data-services", tags=["data-services"])
SuiteId = Annotated[str, Path(pattern=r"^[a-z][a-z0-9-]{1,63}$")]


def get_data_service_registry(request: Request) -> DataServiceRegistry:
    return request.app.state.data_service_registry


def get_data_service_client(request: Request) -> DataServiceClient:
    return request.app.state.data_service_client


def get_data_service_preference_store(request: Request) -> DataServicePreferenceStore:
    return request.app.state.data_service_preference_store


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


@router.get("/catalog")
def data_service_catalog(
    registry: DataServiceRegistry = Depends(get_data_service_registry),
) -> dict[str, object]:
    return registry.catalog()


@router.get(
    "/preferences/{suite_id}",
    response_model=DataServicePreferences,
)
async def data_service_preferences(
    suite_id: SuiteId,
    user_id: str = Header(default="local-user", alias="X-User-Id"),
    workspace_id: str = Header(
        default="local-workspace",
        alias="X-Workspace-Id",
    ),
    store: DataServicePreferenceStore = Depends(get_data_service_preference_store),
) -> DataServicePreferences:
    return await run_in_threadpool(
        store.get,
        user_id=user_id,
        workspace_id=workspace_id,
        suite_id=suite_id,
    )


@router.put(
    "/preferences/{suite_id}",
    response_model=DataServicePreferences,
)
async def update_data_service_preferences(
    suite_id: SuiteId,
    update: DataServicePreferencesUpdate,
    user_id: str = Header(default="local-user", alias="X-User-Id"),
    workspace_id: str = Header(
        default="local-workspace",
        alias="X-Workspace-Id",
    ),
    registry: DataServiceRegistry = Depends(get_data_service_registry),
    store: DataServicePreferenceStore = Depends(get_data_service_preference_store),
) -> DataServicePreferences:
    for capability_id, service_id in update.capability_services.items():
        if not any(
            provider.id == service_id
            for provider in registry.providers(capability_id)
        ):
            raise HTTPException(
                status_code=422,
                detail="selected data provider does not expose the capability",
            )
    return await run_in_threadpool(
        store.set,
        user_id=user_id,
        workspace_id=workspace_id,
        suite_id=suite_id,
        capability_services=update.capability_services,
    )


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
