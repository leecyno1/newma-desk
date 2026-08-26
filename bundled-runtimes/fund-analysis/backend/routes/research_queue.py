"""研究队列 (Research Queue) API — 候选→研究→产出的工作流容器。"""
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from services.research_queue_service import ResearchQueueService

router = APIRouter(prefix="/api/research-queue", tags=["研究队列"])


def _svc() -> ResearchQueueService:
    return ResearchQueueService()


class QueueItemCreate(BaseModel):
    fund_wind_code: str = Field(min_length=1, max_length=24)
    priority: int = Field(default=3, ge=1, le=5)
    source: Optional[str] = None
    source_ref: Optional[str] = None
    next_review_date: Optional[str] = None
    notes: Optional[str] = None


class QueueItemUpdate(BaseModel):
    status: Optional[str] = None
    priority: Optional[int] = Field(default=None, ge=1, le=5)
    next_review_date: Optional[str] = None
    notes: Optional[str] = None
    conclusion: Optional[str] = None
    thesis_id: Optional[str] = None
    source_ref: Optional[str] = None


@router.get("")
def list_queue(
    status: Optional[str] = Query(None),
    due_soon: bool = Query(False),
    limit: int = Query(200, ge=1, le=1000),
) -> Dict[str, Any]:
    try:
        rows = _svc().list_items(status=status, due_soon=due_soon, limit=limit)
        counts = _svc().count_by_status()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return {"data": rows, "total": len(rows), "counts_by_status": counts}


@router.get("/{item_id}")
def get_item(item_id: str) -> Dict[str, Any]:
    result = _svc().get_item(item_id)
    if not result:
        raise HTTPException(status_code=404, detail="queue item not found")
    return result


@router.post("")
def add_item(payload: QueueItemCreate) -> Dict[str, Any]:
    try:
        return _svc().add_item(payload.dict(exclude_none=True))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.patch("/{item_id}")
def update_item(item_id: str, payload: QueueItemUpdate) -> Dict[str, Any]:
    try:
        result = _svc().update_item(item_id, payload.dict(exclude_none=True))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not result:
        raise HTTPException(status_code=404, detail="queue item not found")
    return result


@router.delete("/{item_id}")
def remove_item(item_id: str) -> Dict[str, Any]:
    deleted = _svc().remove_item(item_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="queue item not found")
    return {"deleted": True}
