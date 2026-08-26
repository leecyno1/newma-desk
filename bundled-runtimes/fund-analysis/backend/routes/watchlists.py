"""普通用户自选基金 API。"""
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.exc import SQLAlchemyError

from repositories import get_fund_pool_repo, get_fund_repo
from services.fund_watchlist_service import FundWatchlistService


router = APIRouter(prefix="/api/watchlists", tags=["我的自选"])


class CreateWatchlistRequest(BaseModel):
    name: str
    description: Optional[str] = None


class AddWatchlistMemberRequest(BaseModel):
    fundId: str
    reason: Optional[str] = None


class UpdateWatchlistMemberRequest(BaseModel):
    reason: Optional[str] = None


@router.get("")
def list_watchlists() -> Dict[str, Any]:
    try:
        watchlists = FundWatchlistService().list_pools()
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=503, detail="自选基金数据库暂时不可用") from exc
    return {"watchlists": watchlists, "count": len(watchlists)}


@router.post("")
def create_watchlist(payload: CreateWatchlistRequest) -> Dict[str, Any]:
    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="分组名称不能为空")
    try:
        return get_fund_pool_repo().create_pool(
            name=name,
            description=(payload.description or "").strip() or None,
            created_by="watchlist-ui",
        )
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=503, detail="创建自选分组失败") from exc


@router.get("/{watchlist_id}/members")
def list_watchlist_members(
    watchlist_id: str,
    status: Optional[str] = Query(None),
) -> Dict[str, Any]:
    try:
        members = FundWatchlistService().list_members(watchlist_id, status=status)
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=503, detail="自选基金数据库暂时不可用") from exc
    return {"watchlistId": watchlist_id, "members": members, "count": len(members)}


@router.post("/{watchlist_id}/members")
def add_watchlist_member(watchlist_id: str, payload: AddWatchlistMemberRequest) -> Dict[str, Any]:
    fund = get_fund_repo().get_fund_by_identifier(payload.fundId.strip())
    if not fund:
        raise HTTPException(status_code=404, detail="基金不存在")
    wind_code = str(fund.get("wind_code") or payload.fundId).strip()
    try:
        member = get_fund_pool_repo().add_fund_to_pool(
            pool_id=watchlist_id,
            fund_id=wind_code,
            status="watch",
            reason=(payload.reason or "").strip() or None,
            created_by="watchlist-ui",
        )
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=503, detail="加入自选失败") from exc
    return {"memberId": member.get("id"), "poolId": member.get("pool_id"), "fundId": wind_code}


@router.patch("/members/{member_id}")
def update_watchlist_member(member_id: str, payload: UpdateWatchlistMemberRequest) -> Dict[str, Any]:
    try:
        member = get_fund_pool_repo().update_member_status(
            member_id=member_id,
            reason=(payload.reason or "").strip() or None,
            updated_by="watchlist-ui",
        )
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=503, detail="更新自选备注失败") from exc
    if not member:
        raise HTTPException(status_code=404, detail="自选基金不存在")
    return member


@router.delete("/members/{member_id}")
def delete_watchlist_member(member_id: str) -> Dict[str, Any]:
    try:
        member = get_fund_pool_repo().delete_member(member_id)
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=503, detail="移出自选失败") from exc
    if not member:
        raise HTTPException(status_code=404, detail="自选基金不存在")
    return {"deleted": True, "memberId": member.get("id")}
