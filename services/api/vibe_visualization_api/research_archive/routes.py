from typing import Annotated

from fastapi import APIRouter, Header, Request
from starlette.concurrency import run_in_threadpool

from vibe_visualization_api.research_archive.models import ResearchArchiveIndex


router = APIRouter(prefix="/api/research-archive", tags=["research archive"])

UserId = Annotated[
    str,
    Header(alias="X-User-Id", min_length=1, max_length=128),
]
WorkspaceId = Annotated[
    str,
    Header(alias="X-Workspace-Id", min_length=1, max_length=128),
]


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
