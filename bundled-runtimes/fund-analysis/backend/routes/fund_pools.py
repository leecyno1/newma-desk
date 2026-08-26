"""
基金池 API
"""
from datetime import date
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.exc import SQLAlchemyError

from repositories import get_fund_pool_repo
from services.fund_watchlist_service import FundWatchlistService

router = APIRouter(prefix="/api/fund-pools", tags=["基金池"])


class CreatePoolRequest(BaseModel):
    name: str
    description: Optional[str] = None
    createdBy: Optional[str] = None
    isDefault: bool = False


class AddPoolMemberRequest(BaseModel):
    fundId: str
    status: str = "candidate"
    reason: Optional[str] = None
    latestConclusion: Optional[str] = None
    evidence: Optional[Dict[str, Any]] = None
    riskNotes: Optional[str] = None
    nextReviewDate: Optional[date] = None
    createdBy: Optional[str] = None


class UpdatePoolMemberRequest(BaseModel):
    status: Optional[str] = None
    reason: Optional[str] = None
    latestConclusion: Optional[str] = None
    nextReviewDate: Optional[date] = None
    evidence: Optional[Dict[str, Any]] = None
    riskNotes: Optional[str] = None
    updatedBy: Optional[str] = None


@router.get("")
def list_fund_pools() -> Dict[str, Any]:
    repo = get_fund_pool_repo()
    try:
        repo.ensure_default_research_pool()
        pools = repo.list_pools()
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=503, detail=f"Fund pool store unavailable: {exc.__class__.__name__}") from exc
    return {"pools": pools, "count": len(pools)}


@router.post("")
def create_fund_pool(payload: CreatePoolRequest) -> Dict[str, Any]:
    repo = get_fund_pool_repo()
    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="分组名称不能为空")
    try:
        pool = repo.create_pool(
            name=name,
            description=payload.description,
            created_by=payload.createdBy,
            is_default=payload.isDefault,
        )
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=503, detail=f"Fund pool store unavailable: {exc.__class__.__name__}") from exc
    return pool


@router.get("/{pool_id}/members")
def list_pool_members(pool_id: str, status: Optional[str] = Query(None)) -> Dict[str, Any]:
    repo = get_fund_pool_repo()
    try:
        members = repo.list_members(pool_id=pool_id, status=status)
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=503, detail=f"Fund pool store unavailable: {exc.__class__.__name__}") from exc
    return {"poolId": pool_id, "members": members, "count": len(members)}


@router.post("/{pool_id}/members")
def add_pool_member(pool_id: str, payload: AddPoolMemberRequest) -> Dict[str, Any]:
    repo = get_fund_pool_repo()
    try:
        member = repo.add_fund_to_pool(
            pool_id=pool_id,
            fund_id=payload.fundId,
            status=payload.status,
            reason=payload.reason,
            latest_conclusion=payload.latestConclusion,
            evidence=payload.evidence,
            risk_notes=payload.riskNotes,
            next_review_date=payload.nextReviewDate,
            created_by=payload.createdBy,
        )
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=503, detail=f"Fund pool store unavailable: {exc.__class__.__name__}") from exc
    return member


@router.patch("/members/{member_id}")
def update_pool_member(member_id: str, payload: UpdatePoolMemberRequest) -> Dict[str, Any]:
    repo = get_fund_pool_repo()
    try:
        member = repo.update_member_status(
            member_id=member_id,
            status=payload.status,
            reason=payload.reason,
            latest_conclusion=payload.latestConclusion,
            evidence=payload.evidence,
            risk_notes=payload.riskNotes,
            updated_by=payload.updatedBy,
            next_review_date=payload.nextReviewDate,
        )
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=503, detail=f"Fund pool store unavailable: {exc.__class__.__name__}") from exc
    if not member:
        raise HTTPException(status_code=404, detail="Pool member not found")
    return member


@router.delete("/members/{member_id}")
def delete_pool_member(member_id: str) -> Dict[str, Any]:
    repo = get_fund_pool_repo()
    try:
        member = repo.delete_member(member_id)
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=503, detail=f"Fund pool store unavailable: {exc.__class__.__name__}") from exc
    if not member:
        raise HTTPException(status_code=404, detail="Pool member not found")
    return {"deleted": True, **member}
