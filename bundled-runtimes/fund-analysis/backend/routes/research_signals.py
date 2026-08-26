"""研究信号雷达 (Research Signals) API — 主动推送研究变化。"""
from typing import Any, Dict

from fastapi import APIRouter, HTTPException, Query

from services.research_signals_service import ResearchSignalsService

router = APIRouter(prefix="/api/research-signals", tags=["研究信号雷达"])


@router.get("/scan")
def scan_signals(days: int = Query(14, ge=1, le=90)) -> Dict[str, Any]:
    try:
        return ResearchSignalsService().scan(days=days)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"signal scan failed: {exc.__class__.__name__}") from exc
