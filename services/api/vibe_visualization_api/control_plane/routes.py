import sqlite3
from typing import Annotated

from fastapi import (
    APIRouter,
    Body,
    Depends,
    File,
    Header,
    HTTPException,
    Request,
    Response,
    UploadFile,
)
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from vibe_visualization_api.agent_gateway.models import AgentTaskCreate
from vibe_visualization_api.control_plane.actions import payload_hash
from vibe_visualization_api.config import Settings, get_settings
from vibe_visualization_api.control_plane.models import StoredModule
from vibe_visualization_api.control_plane.packages import (
    ModulePackageError,
    export_module_package,
    prepare_module_package,
)
from vibe_visualization_api.control_plane.repository import ModuleRepository
from vibe_visualization_api.control_plane.permissions import authorize_action
from vibe_visualization_api.data_services.registry import DataServiceNotFoundError
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


@router.post("/{module_id}/actions/{action_id}")
async def invoke_module_action(
    module_id: str,
    action_id: str,
    request: Request,
    input_data: dict[str, object] = Body(default_factory=dict),
    user_id: str = Header(
        default="local-user",
        alias="X-User-Id",
        min_length=1,
        max_length=128,
    ),
    confirmation_token: str
    | None = Header(
        default=None,
        alias="X-Confirmation-Token",
    ),
    repository: ModuleRepository = Depends(get_repository),
):
    module = await run_in_threadpool(repository.get_published, module_id)
    hashed_payload = payload_hash(input_data)
    base_audit: dict[str, object] = {
        "user_id": user_id,
        "action": action_id,
        "payload_hash": hashed_payload,
        "task_id": None,
    }
    decision = authorize_action(module.manifest, action_id)

    if action_id == "trade.execute":
        if not decision.allowed:
            await run_in_threadpool(
                repository.record_action_audit,
                module_id,
                module.revision,
                {**base_audit, "decision": "denied"},
            )
            raise HTTPException(403, "module action is not declared")
        confirmation = request.app.state.trade_confirmation_service
        if not confirmation.validate(
            confirmation_token,
            user_id=user_id,
            module_id=module_id,
            action_id=action_id,
            payload_hash=hashed_payload,
        ):
            await run_in_threadpool(
                repository.record_action_audit,
                module_id,
                module.revision,
                {**base_audit, "decision": "confirmation_required"},
            )
            raise HTTPException(428, "trade confirmation is required")
        await run_in_threadpool(
            repository.record_action_audit,
            module_id,
            module.revision,
            {**base_audit, "decision": "blocked_mvp"},
        )
        raise HTTPException(501, "real trading is disabled in the MVP")

    if action_id == "market.refresh":
        if not decision.allowed:
            await run_in_threadpool(
                repository.record_action_audit,
                module_id,
                module.revision,
                {**base_audit, "decision": "denied"},
            )
            raise HTTPException(403, "module action is not declared")
        async with request.app.state.scheduler_service_lock:
            refresh_service = request.app.state.scheduler_service
            if refresh_service is None:
                refresh_service = await run_in_threadpool(
                    request.app.state.scheduler_service_factory
                )
                request.app.state.scheduler_service = refresh_service
        try:
            snapshot = await refresh_service.refresh_module(module_id)
        except Exception as error:
            await run_in_threadpool(
                repository.record_action_audit,
                module_id,
                module.revision,
                {**base_audit, "decision": "failed"},
            )
            raise HTTPException(502, "market refresh failed") from error
        snapshot_id = (
            snapshot.get("id")
            if isinstance(snapshot, dict)
            else getattr(snapshot, "id", None)
        )
        await run_in_threadpool(
            repository.record_action_audit,
            module_id,
            module.revision,
            {
                **base_audit,
                "decision": "allowed",
                "snapshot_id": snapshot_id,
            },
        )
        return JSONResponse(status_code=200, content=jsonable_encoder(snapshot))

    if decision.allowed:
        async with request.app.state.agent_task_service_lock:
            service = request.app.state.agent_task_service
            if service is None:
                service = await run_in_threadpool(
                    request.app.state.agent_task_service_factory
                )
                request.app.state.agent_task_service = service
        task = await service.create(
            AgentTaskCreate(
                module_id=module_id,
                capability=action_id,
                input=input_data,
            )
        )
        await run_in_threadpool(
            repository.record_action_audit,
            module_id,
            module.revision,
            {**base_audit, "decision": "allowed", "task_id": task.id},
        )
        return JSONResponse(status_code=202, content=task.model_dump(mode="json"))

    permissions = set(module.manifest.get("permissions", []))
    declared_services = module.manifest.get("dataServices", [])
    registry = request.app.state.data_service_registry
    for service_id in declared_services if isinstance(declared_services, list) else []:
        try:
            data_service = registry.get(service_id)
        except DataServiceNotFoundError:
            continue
        capability = data_service.capabilities.get(action_id)
        if capability is None or capability.permission not in permissions:
            continue
        await run_in_threadpool(
            repository.record_action_audit,
            module_id,
            module.revision,
            {**base_audit, "decision": "allowed"},
        )
        result = await request.app.state.data_service_client.invoke(
            data_service,
            action_id,
            input_data,
        )
        return result

    await run_in_threadpool(
        repository.record_action_audit,
        module_id,
        module.revision,
        {**base_audit, "decision": "denied"},
    )
    raise HTTPException(403, "module action is not declared")
