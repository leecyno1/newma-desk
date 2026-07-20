import sqlite3

from fastapi import APIRouter, Depends, HTTPException

from vibe_visualization_api.config import Settings, get_settings
from vibe_visualization_api.control_plane.models import StoredModule
from vibe_visualization_api.control_plane.repository import ModuleRepository
from vibe_visualization_api.control_plane.schemas import (
    ModuleManifest,
    StoredModuleResponse,
    manifest_repository_dict,
)


router = APIRouter(prefix="/api/modules", tags=["modules"])


def get_repository(settings: Settings = Depends(get_settings)) -> ModuleRepository:
    try:
        return ModuleRepository(settings.database_path)
    except sqlite3.Error as error:
        raise HTTPException(
            status_code=500, detail="module repository unavailable"
        ) from error


@router.get(
    "",
    response_model=list[StoredModuleResponse],
    response_model_exclude_none=True,
)
def list_modules(
    repository: ModuleRepository = Depends(get_repository),
) -> list[StoredModule]:
    return repository.list_published()


@router.post(
    "/drafts",
    status_code=201,
    response_model=StoredModuleResponse,
    response_model_exclude_none=True,
)
def create_draft(
    manifest: ModuleManifest,
    repository: ModuleRepository = Depends(get_repository),
) -> StoredModule:
    return repository.create_draft(manifest_repository_dict(manifest))


@router.post(
    "/{module_id}/revisions/{revision}/publish",
    response_model=StoredModuleResponse,
    response_model_exclude_none=True,
)
def publish(
    module_id: str,
    revision: int,
    repository: ModuleRepository = Depends(get_repository),
) -> StoredModule:
    return repository.publish(module_id, revision)


@router.post(
    "/{module_id}/disable",
    response_model=StoredModuleResponse,
    response_model_exclude_none=True,
)
def disable(
    module_id: str,
    repository: ModuleRepository = Depends(get_repository),
) -> StoredModule:
    return repository.disable(module_id)


@router.post(
    "/{module_id}/revisions/{revision}/rollback",
    response_model=StoredModuleResponse,
    response_model_exclude_none=True,
)
def rollback(
    module_id: str,
    revision: int,
    repository: ModuleRepository = Depends(get_repository),
) -> StoredModule:
    return repository.rollback(module_id, revision)


@router.get(
    "/{module_id}/revisions/{revision}",
    response_model=StoredModuleResponse,
    response_model_exclude_none=True,
)
def get_revision(
    module_id: str,
    revision: int,
    repository: ModuleRepository = Depends(get_repository),
) -> StoredModule:
    return repository.get_revision(module_id, revision)
