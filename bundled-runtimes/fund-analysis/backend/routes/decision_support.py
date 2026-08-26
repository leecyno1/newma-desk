"""决策支持 (Decision Support) API — 反向证据 / 三选一 / 同类组回顾。"""
from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from services.decision_support_service import DecisionSupportService

router = APIRouter(prefix="/api/decision-support", tags=["决策支持"])


def _svc() -> DecisionSupportService:
    return DecisionSupportService()


class ForcedChoiceRequest(BaseModel):
    codes: List[str] = Field(min_length=2, max_length=5)


class PeerReviewRequest(BaseModel):
    codes: List[str] = Field(min_length=1, max_length=50)
    top_n: int = Field(default=5, ge=1, le=20)


@router.get("/counter-evidence/{wind_code}")
def counter_evidence(wind_code: str) -> Dict[str, Any]:
    """#5 反向证据：对单只基金强制输出看空理由。"""
    try:
        return _svc().counter_evidence(wind_code)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.post("/forced-choice")
def forced_choice(payload: ForcedChoiceRequest) -> Dict[str, Any]:
    """#8 三选一辅助：规则化选最强并给弃选理由。"""
    try:
        return _svc().forced_choice(payload.codes)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/peer-review")
def peer_review(payload: PeerReviewRequest) -> Dict[str, Any]:
    """#15 同类组基准回顾：最强基金 vs 关注但未选，机会成本。"""
    try:
        return _svc().peer_review(payload.codes, top_n=payload.top_n)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
