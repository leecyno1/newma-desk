import sqlite3
from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile
from starlette.concurrency import run_in_threadpool

from vibe_visualization_api.config import Settings, get_settings
from vibe_visualization_api.control_plane.models import StoredModule
from vibe_visualization_api.control_plane.packages import (
    ModulePackageError,
    export_module_package,
    prepare_module_package,
)
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
    "/import",
    status_code=201,
    response_model=StoredModuleResponse,
    response_model_exclude_none=True,
)
async def import_module(
    package: Annotated[UploadFile, File()],
    settings: Settings = Depends(get_settings),
    repository: ModuleRepository = Depends(get_repository),
) -> StoredModule:
    prepared = None
    try:
        prepared = await prepare_module_package(
            package,
            settings.runtime_dir / "module-packages",
        )
        return await run_in_threadpool(
            repository.import_draft,
            prepared.manifest,
            prepared.install,
        )
    except ModulePackageError as error:
        raise HTTPException(
            status_code=error.status_code,
            detail=error.detail,
        ) from error
    finally:
        await package.close()
        if prepared is not None:
            prepared.discard()


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


@router.get("/{module_id}/revisions/{revision}/export")
def export_revision(
    module_id: str,
    revision: int,
    settings: Settings = Depends(get_settings),
    repository: ModuleRepository = Depends(get_repository),
) -> Response:
    stored_module = repository.get_revision(module_id, revision)
    try:
        package_bytes = export_module_package(
            settings.runtime_dir / "module-packages",
            stored_module.module_id,
            stored_module.revision,
            stored_module.manifest,
        )
    except ModulePackageError as error:
        raise HTTPException(
            status_code=error.status_code,
            detail=error.detail,
        ) from error
    repository.record_export(module_id, revision)
    return Response(
        content=package_bytes,
        media_type="application/zip",
        headers={
            "Content-Disposition": (
                f'attachment; filename="{module_id}-r{revision}.zip"'
            )
        },
    )
