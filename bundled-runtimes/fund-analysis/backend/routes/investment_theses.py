"""投资论点 (Investment Thesis) API — 研究结论的结构化容器。

设计边界：
- 记录"为什么买 / 何时卖 / 有效期 / 支撑证据"，不参与任何交易执行
- 与自选(watchlist)独立：watchlist 是关注列表，thesis 是研究产出承诺
- 状态机：candidate → researching → observing → invalid|archived
- LLM 只能作为草稿助手，人工确认后才能保存（前端约束）
"""
from datetime import date
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.exc import SQLAlchemyError

from repositories.investment_thesis_repo import InvestmentThesisRepo, VALID_STATES


router = APIRouter(prefix="/api/theses", tags=["投资论点"])


def _repo() -> InvestmentThesisRepo:
    return InvestmentThesisRepo()


class ThesisCreate(BaseModel):
    fund_wind_code: str = Field(min_length=1, max_length=24)
    title: str = Field(min_length=1, max_length=200)
    state: Optional[str] = Field(default="candidate")
    core_reasoning: Optional[List[Dict[str, Any]]] = None
    sell_triggers: Optional[List[Dict[str, Any]]] = None
    one_liner: Optional[str] = None
    counter_view: Optional[str] = None
    risks: Optional[List[Dict[str, Any]]] = None
    valid_until: Optional[str] = None
    next_review_date: Optional[str] = None
    review_cadence_days: Optional[int] = Field(default=30, ge=1, le=365)
    evidence_snapshot: Optional[Dict[str, Any]] = None


class ThesisUpdate(BaseModel):
    title: Optional[str] = None
    one_liner: Optional[str] = None
    counter_view: Optional[str] = None
    core_reasoning: Optional[List[Dict[str, Any]]] = None
    sell_triggers: Optional[List[Dict[str, Any]]] = None
    risks: Optional[List[Dict[str, Any]]] = None
    valid_until: Optional[str] = None
    next_review_date: Optional[str] = None
    review_cadence_days: Optional[int] = None
    evidence_snapshot: Optional[Dict[str, Any]] = None


class ThesisTransition(BaseModel):
    state: str
    note: Optional[str] = None
    close_reason: Optional[str] = None
    close_verdict: Optional[str] = None


@router.get("")
def list_theses(
    state: Optional[str] = Query(None),
    fund: Optional[str] = Query(None, alias="fund_wind_code"),
    due_soon: bool = Query(False, description="只返回复查日期在今天或之前"),
    include_closed: bool = Query(False),
    limit: int = Query(200, ge=1, le=1000),
) -> Dict[str, Any]:
    if state and state not in VALID_STATES:
        raise HTTPException(status_code=400, detail=f"invalid state; allowed: {sorted(VALID_STATES)}")
    try:
        rows = _repo().list_theses(
            state=state,
            fund_wind_code=fund,
            due_before=date.today() if due_soon else None,
            include_closed=include_closed,
            limit=limit,
        )
        counts = _repo().count_by_state()
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=503, detail=f"theses store unavailable: {exc.__class__.__name__}") from exc
    return {"data": rows, "total": len(rows), "counts_by_state": counts}


@router.get("/{thesis_id}")
def get_thesis(thesis_id: str) -> Dict[str, Any]:
    try:
        thesis = _repo().get_thesis(thesis_id)
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    if not thesis:
        raise HTTPException(status_code=404, detail="thesis not found")
    return thesis


@router.post("")
def create_thesis(payload: ThesisCreate) -> Dict[str, Any]:
    try:
        return _repo().create_thesis(payload.dict(exclude_none=True))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.patch("/{thesis_id}")
def update_thesis(thesis_id: str, payload: ThesisUpdate) -> Dict[str, Any]:
    try:
        result = _repo().update_thesis(thesis_id, payload.dict(exclude_none=True))
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    if not result:
        raise HTTPException(status_code=404, detail="thesis not found")
    return result


@router.post("/{thesis_id}/transition")
def transition_thesis(thesis_id: str, payload: ThesisTransition) -> Dict[str, Any]:
    try:
        result = _repo().transition_state(
            thesis_id,
            payload.state,
            note=payload.note,
            close_reason=payload.close_reason,
            close_verdict=payload.close_verdict,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    if not result:
        raise HTTPException(status_code=404, detail="thesis not found")
    return result
