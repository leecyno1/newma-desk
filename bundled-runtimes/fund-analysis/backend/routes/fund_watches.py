"""观察项 (Fund Watches) API — 任意基金+任意指标+阈值+夜扫。"""
from typing import Any, Dict

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from services.fund_watch_service import FundWatchService

router = APIRouter(prefix="/api/watches", tags=["观察项"])


def _svc() -> FundWatchService:
    return FundWatchService()


class WatchCreate(BaseModel):
    fund_wind_code: str = Field(min_length=1, max_length=24)
    metric_field: str = Field(min_length=1, max_length=100)
    operator: str = Field(default=">=")
    threshold: float
    note: str | None = None


class WatchStatusUpdate(BaseModel):
    status: str


@router.get("")
def list_watches(
    status: str | None = Query(None),
    fund_wind_code: str | None = Query(None, alias="fund"),
) -> Dict[str, Any]:
    try:
        rows = _svc().list_watches(status=status, fund_wind_code=fund_wind_code)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return {"data": rows, "total": len(rows)}


@router.post("")
def create_watch(payload: WatchCreate) -> Dict[str, Any]:
    try:
        return _svc().create_watch(payload.dict(exclude_none=True))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/{watch_id}")
def get_watch(watch_id: str) -> Dict[str, Any]:
    result = _svc().get_watch(watch_id)
    if not result:
        raise HTTPException(status_code=404, detail="watch not found")
    return result


@router.patch("/{watch_id}")
def update_watch_status(watch_id: str, payload: WatchStatusUpdate) -> Dict[str, Any]:
    try:
        result = _svc().update_status(watch_id, payload.status)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not result:
        raise HTTPException(status_code=404, detail="watch not found")
    return result


@router.delete("/{watch_id}")
def delete_watch(watch_id: str) -> Dict[str, Any]:
    deleted = _svc().delete_watch(watch_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="watch not found")
    return {"deleted": True}


@router.post("/scan")
def scan_watches() -> Dict[str, Any]:
    """触发夜扫：检查所有 active 观察项是否达到阈值。"""
    try:
        return _svc().scan()
    except Exception as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
