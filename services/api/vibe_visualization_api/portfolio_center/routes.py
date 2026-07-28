from typing import Annotated

from fastapi import APIRouter, Header, Path, Query, Request, status
from starlette.concurrency import run_in_threadpool

from vibe_visualization_api.portfolio_center.models import (
    LegacyImportResult,
    PortfolioAccount,
    PortfolioAccountCreate,
    PortfolioActivity,
    PortfolioActivityCreate,
    PortfolioDashboard,
)


router = APIRouter(prefix="/api/portfolio-center", tags=["portfolio-center"])

UserId = Annotated[
    str,
    Header(alias="X-User-Id", min_length=1, max_length=128),
]
WorkspaceId = Annotated[
    str,
    Header(alias="X-Workspace-Id", min_length=1, max_length=128),
]
ActivityId = Annotated[
    str,
    Path(pattern=r"^[A-Za-z0-9][A-Za-z0-9-]{0,63}$"),
]


@router.get("", response_model=PortfolioDashboard)
async def get_portfolio_dashboard(
    request: Request,
    user_id: UserId = "local-user",
    workspace_id: WorkspaceId = "local-workspace",
    include_quotes: Annotated[bool, Query(alias="includeQuotes")] = True,
):
    return await request.app.state.portfolio_center_service.dashboard(
        user_id=user_id,
        workspace_id=workspace_id,
        include_quotes=include_quotes,
    )


@router.post(
    "/accounts",
    response_model=PortfolioAccount,
    status_code=status.HTTP_201_CREATED,
)
async def create_portfolio_account(
    account: PortfolioAccountCreate,
    request: Request,
    user_id: UserId = "local-user",
    workspace_id: WorkspaceId = "local-workspace",
):
    return await run_in_threadpool(
        request.app.state.portfolio_center_service.create_account,
        user_id=user_id,
        workspace_id=workspace_id,
        account=account,
    )


@router.post(
    "/activities",
    response_model=PortfolioActivity,
    status_code=status.HTTP_201_CREATED,
)
async def create_portfolio_activity(
    activity: PortfolioActivityCreate,
    request: Request,
    user_id: UserId = "local-user",
    workspace_id: WorkspaceId = "local-workspace",
):
    return await run_in_threadpool(
        request.app.state.portfolio_center_service.add_activity,
        user_id=user_id,
        workspace_id=workspace_id,
        activity=activity,
    )


@router.delete(
    "/activities/{activity_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_portfolio_activity(
    activity_id: ActivityId,
    request: Request,
    user_id: UserId = "local-user",
    workspace_id: WorkspaceId = "local-workspace",
):
    await run_in_threadpool(
        request.app.state.portfolio_center_service.delete_activity,
        user_id=user_id,
        workspace_id=workspace_id,
        activity_id=activity_id,
    )


@router.post("/import/legacy", response_model=LegacyImportResult)
async def import_legacy_portfolio(
    request: Request,
    user_id: UserId = "local-user",
    workspace_id: WorkspaceId = "local-workspace",
):
    return await run_in_threadpool(
        request.app.state.portfolio_center_service.import_legacy,
        user_id=user_id,
        workspace_id=workspace_id,
    )
