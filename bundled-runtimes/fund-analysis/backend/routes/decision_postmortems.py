"""决策复盘 (Decision Post-mortems) API — 论点关闭后强制复盘。"""
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from services.decision_postmortem_service import DecisionPostmortemService

router = APIRouter(prefix="/api/postmortems", tags=["决策复盘"])


def _svc() -> DecisionPostmortemService:
    return DecisionPostmortemService()


class ReasoningVerdict(BaseModel):
    point: str
    verdict: str  # 'confirmed' | 'falsified' | 'unverifiable'
    note: Optional[str] = None


class PostmortemCreate(BaseModel):
    thesis_id: str = Field(min_length=1)
    outcome: str  # validated | invalidated | inconclusive
    actual_return_pct: Optional[float] = None
    peer_median_return_pct: Optional[float] = None
    excess_return_pct: Optional[float] = None
    reasoning_verdicts: Optional[List[ReasoningVerdict]] = None
    trigger_fired: bool = False
    trigger_detail: Optional[str] = None
    lesson_learned: Optional[str] = None
    decision_bias: Optional[str] = None
    would_repeat: Optional[bool] = None


@router.get("")
def list_postmortems(
    outcome: Optional[str] = Query(None),
    fund_wind_code: Optional[str] = Query(None, alias="fund"),
    limit: int = Query(200, ge=1, le=1000),
) -> Dict[str, Any]:
    try:
        rows = _svc().list_postmortems(outcome=outcome, fund_wind_code=fund_wind_code, limit=limit)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return {"data": rows, "total": len(rows)}


@router.get("/stats")
def postmortem_stats() -> Dict[str, Any]:
    try:
        return _svc().stats()
    except Exception as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/patterns")
def postmortem_patterns(min_occurrences: int = Query(2, ge=1, le=10)) -> Dict[str, Any]:
    """决策模式识别 (#14)：从复盘中识别系统性决策偏差。"""
    try:
        return _svc().patterns(min_occurrences=min_occurrences)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/{postmortem_id}")
def get_postmortem(postmortem_id: str) -> Dict[str, Any]:
    result = _svc().get_postmortem(postmortem_id)
    if not result:
        raise HTTPException(status_code=404, detail="postmortem not found")
    return result


@router.post("")
def create_postmortem(payload: PostmortemCreate) -> Dict[str, Any]:
    try:
        data = payload.dict(exclude_none=True)
        if "reasoning_verdicts" in data:
            data["reasoning_verdicts"] = [v if isinstance(v, dict) else v.dict() for v in payload.reasoning_verdicts]
        return _svc().create_postmortem(data)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
