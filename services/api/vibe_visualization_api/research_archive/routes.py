from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response
from starlette.concurrency import run_in_threadpool

from vibe_visualization_api.research_archive.models import ResearchArchiveIndex
from vibe_visualization_api.mod_storage.store import ModStorageCorruptError
from vibe_visualization_api.mod_storage.routes import _claims
from vibe_visualization_api.control_plane.repository import ModuleRepository
from vibe_visualization_api.control_plane.routes import get_repository


router = APIRouter(prefix="/api/research-archive", tags=["research archive"])

UserId = Annotated[
    str,
    Header(alias="X-User-Id", min_length=1, max_length=128),
]
WorkspaceId = Annotated[
    str,
    Header(alias="X-Workspace-Id", min_length=1, max_length=128),
]


async def _authorized_claims(request, authorization, instance_id, repository, permissions):
    claims = _claims(request, authorization, instance_id)
    permission = permissions.get(claims.module_id)
    if not permission or permission not in claims.permissions:
        raise HTTPException(403, "Mod session does not grant research archive reading")
    module = await run_in_threadpool(repository.get_published, claims.module_id)
    if claims.revision != module.revision:
        raise HTTPException(403, "Mod session revision changed; reload this module")
    return claims


@router.get("/industry-inputs")
async def industry_inputs(
    request: Request, response: Response,
    authorization: str | None = Header(default=None),
    instance_id: str | None = Header(default=None, alias="X-Newma-Desk-Instance-Id"),
    repository: ModuleRepository = Depends(get_repository),
):
    claims = await _authorized_claims(request, authorization, instance_id, repository,
        {"industry-prosperity": "storage.read", "instock-industry-chain": "analysis.read"})
    response.headers["Cache-Control"] = "private, no-store"
    try:
        return await run_in_threadpool(request.app.state.research_archive_service.industry_inputs,
                                       user_id=claims.user_id, workspace_id=claims.workspace_id)
    except ModStorageCorruptError as exc:
        raise HTTPException(status_code=503, detail="财报底稿无法读取，请在财报研究中核验") from exc


@router.get("/earnings-inputs")
async def earnings_inputs(request: Request, user_id: UserId, workspace_id: WorkspaceId):
    try:
        return await run_in_threadpool(
            request.app.state.research_archive_service.earnings_inputs,
            user_id=user_id, workspace_id=workspace_id,
        )
    except ModStorageCorruptError as exc:
        raise HTTPException(status_code=503, detail="财报底稿无法读取，请先在财报研究中核验") from exc


@router.get("", response_model=ResearchArchiveIndex)
async def list_research_archive(
    request: Request,
    user_id: UserId = "local-user",
    workspace_id: WorkspaceId = "local-workspace",
):
    return await run_in_threadpool(
        request.app.state.research_archive_service.list,
        user_id=user_id,
        workspace_id=workspace_id,
    )
