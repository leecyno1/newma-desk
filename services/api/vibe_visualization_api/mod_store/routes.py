from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse

from vibe_visualization_api.control_plane.repository import ModuleRepository
from vibe_visualization_api.control_plane.routes import get_repository
from vibe_visualization_api.mod_store.schemas import (
    ModStoreResponse,
    StoreInstallResponse,
    StoreProjectInstallResponse,
)
from vibe_visualization_api.mod_store.service import ModStoreError, ModStoreService


router = APIRouter(prefix="/api/store", tags=["mod-store"])


def get_mod_store(request: Request) -> ModStoreService:
    return request.app.state.mod_store_service


@router.get(
    "/mods",
    response_model=ModStoreResponse,
    response_model_exclude_none=True,
)
async def list_store_mods(
    store: ModStoreService = Depends(get_mod_store),
    repository: ModuleRepository = Depends(get_repository),
) -> ModStoreResponse:
    try:
        return await store.list(repository)
    except ModStoreError as error:
        raise HTTPException(error.status_code, error.detail) from error


@router.post(
    "/sync",
    response_model=ModStoreResponse,
    response_model_exclude_none=True,
)
async def sync_store_mods(
    store: ModStoreService = Depends(get_mod_store),
    repository: ModuleRepository = Depends(get_repository),
) -> ModStoreResponse:
    try:
        return await store.sync(repository)
    except ModStoreError as error:
        raise HTTPException(error.status_code, error.detail) from error


@router.post(
    "/mods/{mod_id}/install",
    response_model=StoreInstallResponse,
    response_model_exclude_none=True,
)
async def install_store_mod(
    mod_id: str,
    store: ModStoreService = Depends(get_mod_store),
    repository: ModuleRepository = Depends(get_repository),
) -> JSONResponse:
    try:
        result = await store.install(mod_id, repository)
    except ModStoreError as error:
        raise HTTPException(error.status_code, error.detail) from error
    return JSONResponse(
        status_code=200 if result.action == "unchanged" else 201,
        content=result.model_dump(by_alias=True, exclude_none=True, mode="json"),
    )


@router.post(
    "/projects/{project_id}/install",
    response_model=StoreProjectInstallResponse,
    response_model_exclude_none=True,
)
async def install_store_project(
    project_id: str,
    store: ModStoreService = Depends(get_mod_store),
    repository: ModuleRepository = Depends(get_repository),
) -> JSONResponse:
    try:
        result = await store.install_project(project_id, repository)
    except ModStoreError as error:
        raise HTTPException(error.status_code, error.detail) from error
    return JSONResponse(
        status_code=200 if result.action == "unchanged" else 201,
        content=result.model_dump(by_alias=True, exclude_none=True, mode="json"),
    )
