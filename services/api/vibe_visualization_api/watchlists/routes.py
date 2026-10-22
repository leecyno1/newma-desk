from typing import Annotated, Literal

from fastapi import APIRouter, Path, Request, status
from starlette.concurrency import run_in_threadpool

from vibe_visualization_api.watchlists.access import StorageScope

from vibe_visualization_api.watchlists.models import (
    SecurityRef,
    WatchGroupCreate,
    WatchGroupUpdate,
    WatchlistDocument,
    WatchlistReplace,
)


router = APIRouter(prefix="/api/watchlists", tags=["watchlists"])

GroupId = Annotated[
    str,
    Path(pattern=r"^[a-z][a-z0-9-]{0,63}$"),
]


@router.get("", response_model=WatchlistDocument)
async def get_watchlists(
    request: Request,
    scope: StorageScope,
):
    return await run_in_threadpool(
        request.app.state.watchlist_store.get,
        user_id=scope.user_id,
        workspace_id=scope.workspace_id,
    )


@router.put("", response_model=WatchlistDocument)
async def replace_watchlists(
    update: WatchlistReplace,
    request: Request,
    scope: StorageScope,
):
    return await run_in_threadpool(
        request.app.state.watchlist_store.replace,
        user_id=scope.user_id,
        workspace_id=scope.workspace_id,
        expected_revision=update.revision,
        groups=update.groups,
    )


@router.post(
    "/groups",
    response_model=WatchlistDocument,
    status_code=status.HTTP_201_CREATED,
)
async def create_watchlist_group(
    group: WatchGroupCreate,
    request: Request,
    scope: StorageScope,
):
    return await run_in_threadpool(
        request.app.state.watchlist_store.create_group,
        user_id=scope.user_id,
        workspace_id=scope.workspace_id,
        group_id=group.id,
        name=group.name,
    )


@router.patch("/groups/{group_id}", response_model=WatchlistDocument)
async def rename_watchlist_group(
    group_id: GroupId,
    update: WatchGroupUpdate,
    request: Request,
    scope: StorageScope,
):
    return await run_in_threadpool(
        request.app.state.watchlist_store.rename_group,
        user_id=scope.user_id,
        workspace_id=scope.workspace_id,
        group_id=group_id,
        name=update.name,
    )


@router.delete("/groups/{group_id}", response_model=WatchlistDocument)
async def delete_watchlist_group(
    group_id: GroupId,
    request: Request,
    scope: StorageScope,
):
    return await run_in_threadpool(
        request.app.state.watchlist_store.delete_group,
        user_id=scope.user_id,
        workspace_id=scope.workspace_id,
        group_id=group_id,
    )


@router.put(
    "/groups/{group_id}/securities/{market}/{symbol}",
    response_model=WatchlistDocument,
)
async def put_watchlist_security(
    group_id: GroupId,
    market: Literal["CN", "HK", "US"],
    symbol: Annotated[str, Path(pattern=r"^[A-Z0-9][A-Z0-9.\-]{0,23}$")],
    security: SecurityRef,
    request: Request,
    scope: StorageScope,
):
    if security.market != market or security.symbol != symbol:
        from fastapi import HTTPException

        raise HTTPException(422, "security path and body must match")
    return await run_in_threadpool(
        request.app.state.watchlist_store.put_security,
        user_id=scope.user_id,
        workspace_id=scope.workspace_id,
        group_id=group_id,
        security=security,
    )


@router.delete(
    "/groups/{group_id}/securities/{market}/{symbol}",
    response_model=WatchlistDocument,
)
async def delete_watchlist_security(
    group_id: GroupId,
    market: Literal["CN", "HK", "US"],
    symbol: Annotated[str, Path(pattern=r"^[A-Z0-9][A-Z0-9.\-]{0,23}$")],
    request: Request,
    scope: StorageScope,
):
    return await run_in_threadpool(
        request.app.state.watchlist_store.delete_security,
        user_id=scope.user_id,
        workspace_id=scope.workspace_id,
        group_id=group_id,
        market=market,
        symbol=symbol,
    )
