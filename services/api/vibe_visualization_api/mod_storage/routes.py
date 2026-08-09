from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, HTTPException, Path, Query, Request, Response
from starlette.concurrency import run_in_threadpool

from vibe_visualization_api.control_plane.repository import ModuleRepository
from vibe_visualization_api.control_plane.routes import get_repository
from vibe_visualization_api.control_plane.sessions import ModSessionError, bearer_token
from vibe_visualization_api.mod_storage.models import (
    ModStorageDocument,
    ModStorageDocumentList,
    ModStoragePut,
)


router = APIRouter(tags=["mod storage"])
ModuleId = Annotated[str, Path(pattern=r"^[a-z][a-z0-9-]{2,63}$")]
NamespaceId = Annotated[str, Path(pattern=r"^[a-z][a-z0-9-]{1,47}$")]
DocumentKey = Annotated[
    str,
    Path(pattern=r"^[A-Za-z0-9][A-Za-z0-9._:@-]{0,127}$"),
]


def _instance_id(
    current: str | None,
    legacy: str | None,
) -> str | None:
    if current is not None and legacy is not None and current != legacy:
        raise HTTPException(400, "conflicting Mod instance headers")
    return current or legacy


def _claims(
    request: Request,
    authorization: str | None,
    instance_id: str | None,
):
    try:
        claims = request.app.state.mod_session_service.validate(
            bearer_token(authorization)
        )
    except ModSessionError as error:
        raise HTTPException(401, "valid Mod session token is required") from error
    if instance_id is None or claims.instance_id != instance_id:
        raise HTTPException(403, "Mod session does not grant this instance")
    return claims


def _namespace_policy(
    manifest: dict[str, Any],
    namespace: str,
) -> dict[str, int]:
    storage = manifest.get("storage")
    if not isinstance(storage, dict) or storage.get("mode") != "desk-managed":
        raise HTTPException(403, "Mod does not declare Desk-managed storage")
    namespaces = storage.get("namespaces")
    if not isinstance(namespaces, list):
        raise HTTPException(403, "Mod storage namespace is not declared")
    declared = next(
        (
            item
            for item in namespaces
            if isinstance(item, dict) and item.get("id") == namespace
        ),
        None,
    )
    if declared is None:
        raise HTTPException(403, "Mod storage namespace is not declared")
    return {
        "schema_version": int(declared.get("schemaVersion", 1)),
        "quota_bytes": int(declared.get("quotaMb", 1)) * 1024 * 1024,
        "max_item_bytes": int(declared.get("maxItemKb", 256)) * 1024,
    }


async def _authorize(
    *,
    request: Request,
    repository: ModuleRepository,
    module_id: str,
    namespace: str,
    permission: str,
    authorization: str | None,
    instance_id: str | None,
):
    module = await run_in_threadpool(repository.get_published, module_id)
    claims = _claims(request, authorization, instance_id)
    if (
        claims.module_id != module_id
        or claims.revision != module.revision
        or permission not in claims.permissions
    ):
        raise HTTPException(403, "Mod session does not grant this storage operation")
    return claims, _namespace_policy(module.manifest, namespace)


@router.get(
    "/{module_id}/storage/{namespace}",
    response_model=ModStorageDocumentList,
    response_model_exclude_none=True,
)
async def list_mod_storage_documents(
    module_id: ModuleId,
    namespace: NamespaceId,
    request: Request,
    cursor: str | None = Query(
        default=None,
        min_length=1,
        max_length=128,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._:@-]{0,127}$",
    ),
    limit: int = Query(default=50, ge=1, le=100),
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
    repository: ModuleRepository = Depends(get_repository),
):
    claims, _ = await _authorize(
        request=request,
        repository=repository,
        module_id=module_id,
        namespace=namespace,
        permission="storage.read",
        authorization=authorization,
        instance_id=_instance_id(instance_id, legacy_instance_id),
    )
    return await run_in_threadpool(
        request.app.state.mod_storage_store.list_documents,
        user_id=claims.user_id,
        workspace_id=claims.workspace_id,
        module_id=module_id,
        namespace=namespace,
        cursor=cursor,
        limit=limit,
    )


@router.get(
    "/{module_id}/storage/{namespace}/{key}",
    response_model=ModStorageDocument,
)
async def get_mod_storage_document(
    module_id: ModuleId,
    namespace: NamespaceId,
    key: DocumentKey,
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
    repository: ModuleRepository = Depends(get_repository),
):
    claims, _ = await _authorize(
        request=request,
        repository=repository,
        module_id=module_id,
        namespace=namespace,
        permission="storage.read",
        authorization=authorization,
        instance_id=_instance_id(instance_id, legacy_instance_id),
    )
    return await run_in_threadpool(
        request.app.state.mod_storage_store.get,
        user_id=claims.user_id,
        workspace_id=claims.workspace_id,
        module_id=module_id,
        namespace=namespace,
        key=key,
    )


@router.put(
    "/{module_id}/storage/{namespace}/{key}",
    response_model=ModStorageDocument,
)
async def put_mod_storage_document(
    module_id: ModuleId,
    namespace: NamespaceId,
    key: DocumentKey,
    update: ModStoragePut,
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
    repository: ModuleRepository = Depends(get_repository),
):
    claims, policy = await _authorize(
        request=request,
        repository=repository,
        module_id=module_id,
        namespace=namespace,
        permission="storage.write",
        authorization=authorization,
        instance_id=_instance_id(instance_id, legacy_instance_id),
    )
    return await run_in_threadpool(
        request.app.state.mod_storage_store.put,
        user_id=claims.user_id,
        workspace_id=claims.workspace_id,
        module_id=module_id,
        namespace=namespace,
        key=key,
        schema_version=policy["schema_version"],
        expected_revision=update.expected_revision,
        value=update.value,
        quota_bytes=policy["quota_bytes"],
        max_item_bytes=policy["max_item_bytes"],
    )


@router.delete(
    "/{module_id}/storage/{namespace}/{key}",
    status_code=204,
)
async def delete_mod_storage_document(
    module_id: ModuleId,
    namespace: NamespaceId,
    key: DocumentKey,
    request: Request,
    expected_revision: int = Query(alias="expectedRevision", ge=1),
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
    repository: ModuleRepository = Depends(get_repository),
):
    claims, _ = await _authorize(
        request=request,
        repository=repository,
        module_id=module_id,
        namespace=namespace,
        permission="storage.write",
        authorization=authorization,
        instance_id=_instance_id(instance_id, legacy_instance_id),
    )
    await run_in_threadpool(
        request.app.state.mod_storage_store.delete,
        user_id=claims.user_id,
        workspace_id=claims.workspace_id,
        module_id=module_id,
        namespace=namespace,
        key=key,
        expected_revision=expected_revision,
    )
    return Response(status_code=204)
