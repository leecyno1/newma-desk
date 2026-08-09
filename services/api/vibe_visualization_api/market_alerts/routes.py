from typing import Annotated

from fastapi import APIRouter, Header, Path, Query, Request, status
from starlette.concurrency import run_in_threadpool

from vibe_visualization_api.market_alerts.models import (
    MarketAlert,
    MarketAlertCreate,
    MarketAlertDeleteResult,
    MarketAlertList,
    MarketAlertUpdate,
)


router = APIRouter(prefix="/api/market-alerts", tags=["market-alerts"])

UserId = Annotated[
    str,
    Header(alias="X-User-Id", min_length=1, max_length=128),
]
WorkspaceId = Annotated[
    str,
    Header(alias="X-Workspace-Id", min_length=1, max_length=128),
]
AlertId = Annotated[
    str,
    Path(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9._-]+$"),
]


@router.get("", response_model=MarketAlertList)
async def list_market_alerts(
    request: Request,
    user_id: UserId = "local-user",
    workspace_id: WorkspaceId = "local-workspace",
    enabled: bool | None = Query(default=None),
):
    return await run_in_threadpool(
        request.app.state.market_alert_store.list,
        user_id=user_id,
        workspace_id=workspace_id,
        enabled=enabled,
    )


@router.post(
    "",
    response_model=MarketAlert,
    status_code=status.HTTP_201_CREATED,
)
async def create_market_alert(
    alert: MarketAlertCreate,
    request: Request,
    user_id: UserId = "local-user",
    workspace_id: WorkspaceId = "local-workspace",
):
    return await run_in_threadpool(
        request.app.state.market_alert_store.create,
        user_id=user_id,
        workspace_id=workspace_id,
        alert=alert,
    )


@router.patch("/{alert_id}", response_model=MarketAlert)
async def update_market_alert(
    alert_id: AlertId,
    update: MarketAlertUpdate,
    request: Request,
    user_id: UserId = "local-user",
    workspace_id: WorkspaceId = "local-workspace",
):
    return await run_in_threadpool(
        request.app.state.market_alert_store.update,
        user_id=user_id,
        workspace_id=workspace_id,
        alert_id=alert_id,
        update=update,
    )


@router.delete("/{alert_id}", response_model=MarketAlertDeleteResult)
async def delete_market_alert(
    alert_id: AlertId,
    request: Request,
    user_id: UserId = "local-user",
    workspace_id: WorkspaceId = "local-workspace",
):
    return await run_in_threadpool(
        request.app.state.market_alert_store.delete,
        user_id=user_id,
        workspace_id=workspace_id,
        alert_id=alert_id,
    )
