"""研究决策记录 (Research Decision Logs) API。"""
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from services.research_decision_log_service import ResearchDecisionLogService

router = APIRouter(prefix="/api/decision-logs", tags=["研究决策记录"])


def _svc() -> ResearchDecisionLogService:
    return ResearchDecisionLogService()


class DecisionLogCreate(BaseModel):
    fund_wind_code: str = Field(min_length=1, max_length=24)
    conclusion: str = Field(min_length=1)
    decision_type: str = "observe"
    confidence: Optional[str] = None
    thesis_id: Optional[str] = None
    evidence_snapshot: Optional[Dict[str, Any]] = None
    review_after_days: int = Field(default=90, ge=1, le=365)
    review_due_date: Optional[str] = None


class DecisionLogReview(BaseModel):
    review_note: Optional[str] = None


@router.get("")
def list_logs(
    fund_wind_code: Optional[str] = Query(None, alias="fund"),
    due_soon: bool = Query(False),
    limit: int = Query(200, ge=1, le=1000),
) -> Dict[str, Any]:
    try:
        rows = _svc().list_logs(fund_wind_code=fund_wind_code, due_soon=due_soon, limit=limit)
        due = _svc().due_count()
    except Exception as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return {"data": rows, "total": len(rows), "due_count": due}


@router.post("")
def create_log(payload: DecisionLogCreate) -> Dict[str, Any]:
    try:
        return _svc().create_log(payload.dict(exclude_none=True))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/{log_id}")
def get_log(log_id: str) -> Dict[str, Any]:
    result = _svc().get_log(log_id)
    if not result:
        raise HTTPException(status_code=404, detail="decision log not found")
    return result


@router.post("/{log_id}/review")
def mark_reviewed(log_id: str, payload: DecisionLogReview) -> Dict[str, Any]:
    result = _svc().mark_reviewed(log_id, payload.review_note)
    if not result:
        raise HTTPException(status_code=404, detail="decision log not found")
    return result
