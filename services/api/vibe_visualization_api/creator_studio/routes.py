from __future__ import annotations

from collections.abc import Callable
from typing import Annotated, Any

from fastapi import APIRouter, Header, HTTPException, Path, Query, Request, status
from pydantic import ValidationError
from starlette.concurrency import run_in_threadpool
from starlette.responses import FileResponse

from vibe_visualization_api.creator_studio.models import (
    CreatorCommand,
    CreatorRunCreate,
    MarketplaceCompatibilityRequest,
    MarketplacePresetCreate,
    MarketplacePresetUpdate,
)
from vibe_visualization_api.creator_studio.editor_sessions import EditorSessionError
from vibe_visualization_api.creator_studio.registry import (
    CreatorDefinitionError,
    CreatorMaterialError,
    CreatorStudioUnavailableError,
)
from vibe_visualization_api.creator_studio.repository import (
    CreatorEditorSessionNotFoundError,
    CreatorJobNotFoundError,
    CreatorPresetNotFoundError,
    CreatorPresetConflictError,
    CreatorRunConflictError,
    CreatorRunNotFoundError,
)
from vibe_visualization_api.creator_studio.service import CreatorCommandError


router = APIRouter(prefix="/api/creator-studio", tags=["creator-studio"])

# Creator Studio 单机单用户模式：所有入口统一固定身份。
# Desk shell 的身份是浏览器首次打开时随机生成并持久化的（workspaceIdentity.ts），
# 而 Agent/CLI 直连使用 local-user/local-workspace——若按各自身份隔离，
# Agent 推进的任务在用户 UI 中不可见（EMPTY RUNWAY）。Creator Studio 是
# 单人创作工具，统一归一为固定身份，保证双入口共享同一份数据。
CREATOR_USER_ID = "local-user"
CREATOR_WORKSPACE_ID = "local-workspace"

UserId = Annotated[str, Header(alias="X-User-Id", min_length=1, max_length=128)]
WorkspaceId = Annotated[
    str,
    Header(alias="X-Workspace-Id", min_length=1, max_length=128),
]
RunId = Annotated[
    str,
    Path(pattern=r"^[A-Za-z0-9][A-Za-z0-9-]{2,79}$"),
]


async def execute(call: Callable[[], Any]) -> Any:
    try:
        return await run_in_threadpool(call)
    except CreatorRunNotFoundError as error:
        raise HTTPException(404, "Creator Studio run not found") from error
    except CreatorJobNotFoundError as error:
        raise HTTPException(404, "Creator execution job not found") from error
    except CreatorEditorSessionNotFoundError as error:
        raise HTTPException(404, "Creator editor session not found") from error
    except CreatorPresetNotFoundError as error:
        raise HTTPException(404, "Creator Marketplace preset not found") from error
    except CreatorPresetConflictError as error:
        raise HTTPException(409, "Creator Marketplace preset version is stale") from error
    except CreatorRunConflictError as error:
        raise HTTPException(409, "Creator Studio run revision is stale") from error
    except CreatorMaterialError as error:
        raise HTTPException(422, detail={"message": str(error), **error.report}) from error
    except (
        CreatorDefinitionError,
        CreatorCommandError,
        EditorSessionError,
        ValidationError,
    ) as error:
        raise HTTPException(422, str(error)) from error
    except CreatorStudioUnavailableError as error:
        raise HTTPException(503, str(error)) from error


@router.get("/registry")
async def get_creator_registry(request: Request):
    return await execute(request.app.state.creator_studio_service.registry_document)


@router.get("/system")
async def get_creator_system(request: Request):
    return await execute(request.app.state.creator_studio_service.system_info)


@router.get("/runs")
async def list_creator_runs(
    request: Request,
    user_id: UserId = "local-user",
    workspace_id: WorkspaceId = "local-workspace",
):
    return await execute(
        lambda: request.app.state.creator_studio_service.list_runs(
            user_id=CREATOR_USER_ID,
            workspace_id=CREATOR_WORKSPACE_ID,
        )
    )


@router.post("/runs", status_code=status.HTTP_201_CREATED)
async def create_creator_run(
    create: CreatorRunCreate,
    request: Request,
    user_id: UserId = "local-user",
    workspace_id: WorkspaceId = "local-workspace",
):
    return await execute(
        lambda: request.app.state.creator_studio_service.create_run(
            user_id=CREATOR_USER_ID,
            workspace_id=CREATOR_WORKSPACE_ID,
            request=create,
        )
    )


@router.get("/runs/{run_id}")
async def get_creator_run(
    run_id: RunId,
    request: Request,
    user_id: UserId = "local-user",
    workspace_id: WorkspaceId = "local-workspace",
):
    return await execute(
        lambda: request.app.state.creator_studio_service.get_snapshot(
            user_id=CREATOR_USER_ID,
            workspace_id=CREATOR_WORKSPACE_ID,
            run_id=run_id,
        )
    )


@router.post("/runs/{run_id}/commands")
async def execute_creator_command(
    run_id: RunId,
    command: CreatorCommand,
    request: Request,
    user_id: UserId = "local-user",
    workspace_id: WorkspaceId = "local-workspace",
):
    return await execute(
        lambda: request.app.state.creator_studio_service.execute_command(
            user_id=CREATOR_USER_ID,
            workspace_id=CREATOR_WORKSPACE_ID,
            run_id=run_id,
            command=command,
        )
    )


@router.get("/runs/{run_id}/events")
async def list_creator_events(
    run_id: RunId,
    request: Request,
    after: Annotated[int, Query(ge=0)] = 0,
    user_id: UserId = "local-user",
    workspace_id: WorkspaceId = "local-workspace",
):
    return await execute(
        lambda: request.app.state.creator_studio_service.list_events(
            user_id=CREATOR_USER_ID,
            workspace_id=CREATOR_WORKSPACE_ID,
            run_id=run_id,
            after=after,
        )
    )


@router.get("/runs/{run_id}/jobs")
async def list_creator_jobs(
    run_id: RunId,
    request: Request,
    user_id: UserId = "local-user",
    workspace_id: WorkspaceId = "local-workspace",
):
    return await execute(
        lambda: request.app.state.creator_studio_service.list_jobs(
            user_id=CREATOR_USER_ID,
            workspace_id=CREATOR_WORKSPACE_ID,
            run_id=run_id,
        )
    )


@router.get("/runs/{run_id}/editor-sessions")
async def list_creator_editor_sessions(
    run_id: RunId,
    request: Request,
    user_id: UserId = "local-user",
    workspace_id: WorkspaceId = "local-workspace",
):
    return await execute(
        lambda: request.app.state.creator_studio_service.list_editor_sessions(
            user_id=CREATOR_USER_ID,
            workspace_id=CREATOR_WORKSPACE_ID,
            run_id=run_id,
        )
    )


@router.post("/capabilities/detect")
async def detect_creator_capabilities(request: Request):
    return await execute(request.app.state.creator_studio_service.detect_capabilities)


@router.post("/capabilities/test")
async def test_creator_agent(request: Request):
    body = await request.json()
    return await execute(
        lambda: request.app.state.creator_studio_service.test_agent(
            agent_id=str(body.get("agentId") or ""),
            bin_override=str(body.get("binOverride") or ""),
        )
    )


@router.get("/artifacts/preview")
async def preview_creator_artifact(request: Request, path: str):
    return await execute(
        lambda: request.app.state.creator_studio_service.preview_artifact(path)
    )


@router.get("/marketplace")
async def get_creator_marketplace(request: Request):
    return await execute(request.app.state.creator_studio_service.marketplace)


@router.post("/marketplace/compatibility")
async def check_creator_marketplace_compatibility(
    check: MarketplaceCompatibilityRequest,
    request: Request,
):
    return await execute(
        lambda: request.app.state.creator_studio_service.marketplace_compatibility(check)
    )


@router.get("/marketplace/presets")
async def list_creator_marketplace_presets(
    request: Request,
    user_id: UserId = "local-user",
    workspace_id: WorkspaceId = "local-workspace",
):
    return await execute(
        lambda: request.app.state.creator_studio_service.list_marketplace_presets(
            user_id=CREATOR_USER_ID,
            workspace_id=CREATOR_WORKSPACE_ID,
        )
    )


@router.post("/marketplace/presets", status_code=status.HTTP_201_CREATED)
async def create_creator_marketplace_preset(
    create: MarketplacePresetCreate,
    request: Request,
    user_id: UserId = "local-user",
    workspace_id: WorkspaceId = "local-workspace",
):
    return await execute(
        lambda: request.app.state.creator_studio_service.create_marketplace_preset(
            user_id=CREATOR_USER_ID,
            workspace_id=CREATOR_WORKSPACE_ID,
            request=create,
        )
    )


@router.get("/marketplace/presets/{preset_id}/versions")
async def list_creator_marketplace_preset_versions(
    preset_id: Annotated[str, Path(pattern=r"^[A-Za-z0-9][A-Za-z0-9-]{2,79}$")],
    request: Request,
    user_id: UserId = "local-user",
    workspace_id: WorkspaceId = "local-workspace",
):
    return await execute(
        lambda: request.app.state.creator_studio_service.list_marketplace_preset_versions(
            user_id=CREATOR_USER_ID,
            workspace_id=CREATOR_WORKSPACE_ID,
            preset_id=preset_id,
        )
    )


@router.put("/marketplace/presets/{preset_id}")
async def update_creator_marketplace_preset(
    preset_id: Annotated[str, Path(pattern=r"^[A-Za-z0-9][A-Za-z0-9-]{2,79}$")],
    update: MarketplacePresetUpdate,
    request: Request,
    user_id: UserId = "local-user",
    workspace_id: WorkspaceId = "local-workspace",
):
    return await execute(
        lambda: request.app.state.creator_studio_service.update_marketplace_preset(
            user_id=CREATOR_USER_ID,
            workspace_id=CREATOR_WORKSPACE_ID,
            preset_id=preset_id,
            request=update,
        )
    )


@router.get("/marketplace/assets/{asset_path:path}")
async def get_creator_marketplace_asset(asset_path: str, request: Request):
    try:
        path = request.app.state.creator_studio_service.marketplace_asset(asset_path)
    except FileNotFoundError as error:
        raise HTTPException(404, "Marketplace preview asset not found") from error
    return FileResponse(path)
