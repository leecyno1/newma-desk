from typing import Annotated

from fastapi import APIRouter, Header, HTTPException, Request
from starlette.concurrency import run_in_threadpool

from vibe_visualization_api.research_archive.models import ResearchArchiveIndex
from vibe_visualization_api.mod_storage.store import ModStorageCorruptError


router = APIRouter(prefix="/api/research-archive", tags=["research archive"])

UserId = Annotated[
    str,
    Header(alias="X-User-Id", min_length=1, max_length=128),
]
WorkspaceId = Annotated[
    str,
    Header(alias="X-Workspace-Id", min_length=1, max_length=128),
]


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
