import json
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
from vibe_visualization_api.control_plane.sessions import (
    ModSessionError,
    bearer_token,
)
from vibe_visualization_api.data_services.registry import DataServiceNotFoundError
from vibe_visualization_api.model_gateway.models import ModelResponseCreate
from vibe_visualization_api.schema_validation import validate_json_contract
from vibe_visualization_api.control_plane.schemas import (
    ModuleManifest,
    ModContextResponse,
    ModContextUpdate,
    ModSessionCreate,
    ModSessionResponse,
    StoredModuleResponse,
    manifest_repository_dict,
)


router = APIRouter(tags=["mods"])
MAX_CONTEXT_BYTES = 512 * 1024


def get_repository(request: Request) -> ModuleRepository:
    return request.app.state.resolve_module_repository()


def _manifest_action_ids(manifest: dict[str, object]) -> list[str]:
    if manifest.get("schemaVersion") == "1.1":
        actions = manifest.get("actions", {})
        return sorted(actions) if isinstance(actions, dict) else []
    declared = manifest.get("agentCapabilities", [])
    return sorted(item for item in declared if isinstance(item, str))


def _manifest_suite_id(manifest: dict[str, object], module_id: str) -> str:
    navigation = manifest.get("navigation")
    if isinstance(navigation, dict):
        directory = navigation.get("directory")
        if isinstance(directory, dict):
            directory_id = directory.get("id")
            if isinstance(directory_id, str):
                return directory_id
    return module_id


def _validate_session(
    request: Request,
    authorization: str | None,
    instance_id: str | None,
):
    try:
        token = bearer_token(authorization)
        claims = request.app.state.mod_session_service.validate(token)
    except ModSessionError as error:
        raise HTTPException(401, "valid Mod session token is required") from error
    if instance_id is None or claims.instance_id != instance_id:
        raise HTTPException(403, "Mod session does not grant this instance")
    return claims


def _instance_id_header(
    instance_id: str | None,
    legacy_instance_id: str | None,
) -> str | None:
    if (
        instance_id is not None
        and legacy_instance_id is not None
        and instance_id != legacy_instance_id
    ):
        raise HTTPException(400, "conflicting Mod instance headers")
    return instance_id or legacy_instance_id


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


@router.post(
    "/{module_id}/sessions",
    status_code=201,
    response_model=ModSessionResponse,
)
async def create_mod_session(
    module_id: str,
    session_request: ModSessionCreate,
    request: Request,
    user_id: str = Header(
        alias="X-User-Id",
        min_length=1,
        max_length=128,
    ),
    repository: ModuleRepository = Depends(get_repository),
) -> ModSessionResponse:
    module = await run_in_threadpool(repository.get_published, module_id)
    actions = _manifest_action_ids(module.manifest)
    permissions = [
        item
        for item in module.manifest.get("permissions", [])
        if isinstance(item, str)
    ]
    token, claims = request.app.state.mod_session_service.issue(
        instance_id=session_request.instance_id,
        user_id=user_id,
        workspace_id=session_request.workspace_id,
        module_id=module_id,
        revision=module.revision,
        actions=actions,
        permissions=permissions,
    )
    return ModSessionResponse(
        sessionId=claims.session_id,
        instanceId=claims.instance_id,
        accessToken=token,
        expiresAt=claims.expires_at_iso,
        userId=claims.user_id,
        workspaceId=claims.workspace_id,
        moduleId=claims.module_id,
        revision=claims.revision,
        grants={
            "permissions": list(claims.permissions),
            "actions": list(claims.actions),
        },
    )


@router.put(
    "/{module_id}/context",
    response_model=ModContextResponse,
)
async def update_mod_context(
    module_id: str,
    update: ModContextUpdate,
    request: Request,
    authorization: str | None = Header(default=None, alias="Authorization"),
    instance_id: str | None = Header(
        default=None,
        alias="X-Newma-Desk-Instance-Id",
        min_length=1,
        max_length=128,
    ),
    legacy_instance_id: str | None = Header(
        default=None,
        alias="X-Newma-Dock-Instance-Id",
        min_length=1,
        max_length=128,
    ),
) -> dict[str, object]:
    claims = _validate_session(
        request,
        authorization,
        _instance_id_header(instance_id, legacy_instance_id),
    )
    if claims.module_id != module_id:
        raise HTTPException(403, "Mod session does not grant this context")
    encoded = json.dumps(
        update.context,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    if len(encoded) > MAX_CONTEXT_BYTES:
        raise HTTPException(413, "Mod context is too large")
    return await run_in_threadpool(
        request.app.state.mod_context_store.put,
        user_id=claims.user_id,
        workspace_id=claims.workspace_id,
        module_id=module_id,
        revision=claims.revision,
        context=update.context,
    )


@router.get(
    "/{module_id}/context",
    response_model=ModContextResponse,
)
async def get_mod_context(
    module_id: str,
    request: Request,
    user_id: str = Header(
        alias="X-User-Id",
        min_length=1,
        max_length=128,
    ),
    workspace_id: str = Header(
        alias="X-Workspace-Id",
        min_length=1,
        max_length=128,
    ),
) -> dict[str, object]:
    result = await run_in_threadpool(
        request.app.state.mod_context_store.get,
        user_id=user_id,
        workspace_id=workspace_id,
        module_id=module_id,
    )
    if result is None:
        raise HTTPException(404, "Mod context is not available")
    return result


@router.post("/{module_id}/actions/{action_id}")
async def invoke_module_action(
    module_id: str,
    action_id: str,
    request: Request,
    input_data: dict[str, object] = Body(default_factory=dict),
    header_user_id: str | None = Header(
        default=None,
        alias="X-User-Id",
        min_length=1,
        max_length=128,
    ),
    header_workspace_id: str = Header(
        default="local-workspace",
        alias="X-Workspace-Id",
        min_length=1,
        max_length=128,
    ),
    authorization: str | None = Header(default=None, alias="Authorization"),
    instance_id: str | None = Header(
        default=None,
        alias="X-Newma-Desk-Instance-Id",
        min_length=1,
        max_length=128,
    ),
    legacy_instance_id: str | None = Header(
        default=None,
        alias="X-Newma-Dock-Instance-Id",
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
    decision = authorize_action(module.manifest, action_id)
    schema_version = module.manifest.get("schemaVersion")
    explicit_binding = schema_version == "1.1"
    if explicit_binding:
        claims = _validate_session(
            request,
            authorization,
            _instance_id_header(instance_id, legacy_instance_id),
        )
        if (
            claims.module_id != module_id
            or claims.revision != module.revision
            or action_id not in claims.actions
        ):
            raise HTTPException(403, "Mod session does not grant this action")
        user_id = claims.user_id
        workspace_id = claims.workspace_id
    else:
        user_id = header_user_id or "local-user"
        workspace_id = header_workspace_id
    base_audit: dict[str, object] = {
        "user_id": user_id,
        "action": action_id,
        "payload_hash": hashed_payload,
        "task_id": None,
    }
    action = decision.action or {}
    binding_value = action.get("binding")
    binding = binding_value if isinstance(binding_value, dict) else {}
    binding_type = binding.get("type")

    if explicit_binding:
        reserved = {
            "gatewayMode",
            "agentAdapter",
            "modelAdapter",
            "model",
        }
        if reserved.intersection(input_data):
            raise HTTPException(
                422,
                "Manifest 1.1 action routing cannot be overridden by the caller",
            )
        if decision.allowed:
            validate_json_contract(
                action.get("inputSchema"),
                input_data,
                direction="input",
            )

    if decision.allowed and decision.requires_confirmation:
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
            raise HTTPException(428, "action confirmation is required")

    if action_id == "trade.execute":
        if not decision.allowed:
            await run_in_threadpool(
                repository.record_action_audit,
                module_id,
                module.revision,
                {**base_audit, "decision": "denied"},
            )
            raise HTTPException(403, "module action is not declared")
        await run_in_threadpool(
            repository.record_action_audit,
            module_id,
            module.revision,
            {**base_audit, "decision": "blocked_mvp"},
        )
        raise HTTPException(501, "real trading is disabled in the MVP")

    if action_id == "market.refresh" and (
        not explicit_binding or binding_type == "local"
    ):
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
        encoded_snapshot = jsonable_encoder(snapshot)
        if explicit_binding:
            validate_json_contract(
                action.get("outputSchema"),
                encoded_snapshot,
                direction="output",
            )
        return JSONResponse(status_code=200, content=encoded_snapshot)

    if explicit_binding:
        if not decision.allowed:
            await run_in_threadpool(
                repository.record_action_audit,
                module_id,
                module.revision,
                {**base_audit, "decision": "denied"},
            )
            raise HTTPException(403, "module action is not declared")

        capability_value = binding.get("capability")
        capability = (
            capability_value if isinstance(capability_value, str) else action_id
        )
        prompt = input_data.get("prompt")
        prompt_text = prompt if isinstance(prompt, str) else ""
        clean_input = {
            key: value for key, value in input_data.items() if key != "prompt"
        }

        if binding_type == "model":
            service = request.app.state.model_gateway_service
            response = await service.create_response(
                ModelResponseCreate(
                    module_id=module_id,
                    capability=capability,
                    prompt=prompt_text,
                    input=clean_input,
                )
            )
            encoded_response = response.model_dump(mode="json")
            validate_json_contract(
                action.get("outputSchema"),
                encoded_response,
                direction="output",
            )
            await run_in_threadpool(
                repository.record_action_audit,
                module_id,
                module.revision,
                {
                    **base_audit,
                    "decision": "allowed",
                    "binding_type": "model",
                    "model_adapter": response.adapter,
                    "model": response.model,
                },
            )
            return JSONResponse(
                status_code=200,
                content=encoded_response,
            )

        if binding_type == "agent":
            async with request.app.state.agent_task_service_lock:
                service = request.app.state.agent_task_service
                if service is None:
                    service = await run_in_threadpool(
                        request.app.state.agent_task_service_factory
                    )
                    request.app.state.agent_task_service = service
            task = await service.create(
                AgentTaskCreate(
                    user_id=user_id,
                    module_id=module_id,
                    capability=capability,
                    memory_scope=str(binding.get("memoryScope", "task")),
                    prompt=prompt_text,
                    input=clean_input,
                ),
                workspace_id=workspace_id,
            )
            encoded_task = task.model_dump(mode="json")
            validate_json_contract(
                action.get("outputSchema"),
                encoded_task,
                direction="output",
            )
            await run_in_threadpool(
                repository.record_action_audit,
                module_id,
                module.revision,
                {
                    **base_audit,
                    "decision": "allowed",
                    "binding_type": "agent",
                    "task_id": task.id,
                },
            )
            return JSONResponse(
                status_code=202,
                content=encoded_task,
            )

        if binding_type == "data":
            service_id = binding.get("service")
            routing = "fixed"
            if isinstance(service_id, str):
                try:
                    data_service = request.app.state.data_service_registry.get(
                        service_id
                    )
                except DataServiceNotFoundError as error:
                    raise HTTPException(
                        503,
                        "declared data service is unavailable",
                    ) from error
            else:
                routing = "unified"
                suite_id = _manifest_suite_id(module.manifest, module_id)
                preferences = await run_in_threadpool(
                    request.app.state.data_service_preference_store.get,
                    user_id=user_id,
                    workspace_id=workspace_id,
                    suite_id=suite_id,
                )
                preferred_service_id = preferences.capability_services.get(
                    capability
                )
                data_service = request.app.state.data_service_registry.resolve(
                    capability,
                    preferred_service_id,
                )
                service_id = data_service.id
            service_capability = data_service.capabilities.get(capability)
            if (
                service_capability is None
                or service_capability.permission != action.get("permission")
            ):
                raise HTTPException(403, "data service capability is not granted")
            result = await request.app.state.data_service_client.invoke(
                data_service,
                capability,
                input_data,
            )
            validate_json_contract(
                action.get("outputSchema"),
                result,
                direction="output",
            )
            await run_in_threadpool(
                repository.record_action_audit,
                module_id,
                module.revision,
                {
                    **base_audit,
                    "decision": "allowed",
                    "binding_type": "data",
                    "service_id": service_id,
                    "routing": routing,
                },
            )
            return result

        if binding_type == "local":
            await run_in_threadpool(
                repository.record_action_audit,
                module_id,
                module.revision,
                {
                    **base_audit,
                    "decision": "unavailable",
                    "binding_type": "local",
                },
            )
            raise HTTPException(501, "local action handler is unavailable")

        raise HTTPException(500, "module action binding is invalid")

    if decision.allowed:
        raw_mode = input_data.get("gatewayMode", "agent")
        if raw_mode not in {"agent", "model"}:
            raise HTTPException(422, "gatewayMode must be 'agent' or 'model'")
        prompt = input_data.get("prompt")
        prompt_text = prompt if isinstance(prompt, str) else ""
        clean_input = {
            key: value
            for key, value in input_data.items()
            if key
            not in {
                "gatewayMode",
                "prompt",
                "agentAdapter",
                "modelAdapter",
                "model",
            }
        }
        if raw_mode == "model":
            model_adapter = input_data.get("modelAdapter")
            model = input_data.get("model")
            service = request.app.state.model_gateway_service
            response = await service.create_response(
                ModelResponseCreate(
                    module_id=module_id,
                    capability=action_id,
                    prompt=prompt_text,
                    input=clean_input,
                    adapter=(
                        model_adapter if isinstance(model_adapter, str) else None
                    ),
                    model=model if isinstance(model, str) else None,
                )
            )
            await run_in_threadpool(
                repository.record_action_audit,
                module_id,
                module.revision,
                {
                    **base_audit,
                    "decision": "allowed",
                    "gateway_mode": "model",
                    "model_adapter": response.adapter,
                    "model": response.model,
                },
            )
            return JSONResponse(
                status_code=200,
                content=response.model_dump(mode="json"),
            )

        agent_adapter = input_data.get("agentAdapter")
        async with request.app.state.agent_task_service_lock:
            service = request.app.state.agent_task_service
            if service is None:
                service = await run_in_threadpool(
                    request.app.state.agent_task_service_factory
                )
                request.app.state.agent_task_service = service
        task = await service.create(
            AgentTaskCreate(
                user_id=user_id,
                module_id=module_id,
                capability=action_id,
                prompt=prompt_text,
                input=clean_input,
                adapter=(
                    agent_adapter if isinstance(agent_adapter, str) else None
                ),
            ),
            workspace_id=workspace_id,
        )
        await run_in_threadpool(
            repository.record_action_audit,
            module_id,
            module.revision,
            {
                **base_audit,
                "decision": "allowed",
                "gateway_mode": "agent",
                "task_id": task.id,
            },
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
